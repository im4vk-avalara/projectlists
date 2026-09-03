#!/usr/bin/env python3
"""
AIOS host AI bridge.

Listens on a UNIX socket (QEMU connects to it as a serial chardev = the guest's
COM2), reads framed requests from the AIOS kernel, runs the prompt through the
model, and writes a framed response back.

Frame layout (little-endian), matching include/bridge.h:
    MAGIC(4="AIOS") | type(1) | seq(2) | len(4) | payload(len) | crc32(4)
    type: 0=req 1=resp 2=err ; crc32 = zlib.crc32(payload)

Model: mlx-community/Qwen2.5-14B-Instruct-4bit, run via Apple MLX (4-bit, GPU).
Long-term memory: TurboVec + local MiniLM embeddings (see memory.py), persisted
under .memory/ -- disable with --no-memory.
Needs the venv (`pip install mlx-lm turbovec sentence-transformers`).
No API key, no cloud, no TLS.

Usage (run with the venv python; no activation needed):
    .venv/bin/python host/ai-bridge/bridge.py
"""
import argparse
import json
import os
import socket
import struct
import sys
import zlib

MAGIC = b"AIOS"
REQ, RESP, ERR = 0, 1, 2
MAX_PAYLOAD = 1 << 20  # 1 MiB sanity cap

# Teaches a real model the AIOS control-surface + app-DSL schemas so it emits the
# same JSON the kernel validates. (The mock backend hardcodes this instead.)
SYSTEM_PROMPT = (
    "You are the AI that controls AIOS, a tiny operating system. Decide how to "
    "answer the user's request and reply in exactly ONE of these forms, with no "
    "markdown, no code fences, and no extra commentary:\n"
    "1) To inspect or change the machine, output ONLY a single-line JSON intent:\n"
    '   {\"aios_intent\":\"1\",\"verb\":\"<verb>\",\"args\":{...},'
    '\"say\":\"<one friendly sentence>\"}\n'
    "   The \"say\" field is OPTIONAL and ONLY for intents (a one-sentence reply, "
    "e.g. \"Sure, checking your free memory now.\"). NEVER put a \"say\" field or "
    "any prose inside an app definition -- apps are pure JSON in the app schema "
    "below.\n"
    "   Read-only verbs (always allowed): uptime, meminfo, ps, "
    'peek (args.addr as a hex string like "0x10000"), '
    'calc (args.expr as an arithmetic string like "2+3*4"), '
    "apps (list saved apps), "
    'open (args.id to relaunch a saved app, e.g. "open the calculator"), '
    'fix (args.id + args.problem -- when the user says an app is broken or '
    'doesn\'t work, emit a fix intent describing the problem; the OS gives you '
    'the app to repair). '
    "For ANY arithmetic question use the calc verb -- do NOT compute it yourself.\n"
    "   Mutating verbs (need permission): map, unmap, alloc, free, frame, "
    'unframe, kill (args.id as a string).\n'
    "2) To create an app, output ONLY a JSON app definition:\n"
    '   {\"aios_app\":\"1\",\"id\":\"<id>\",\"title\":\"<title>\",'
    '\"state\":{\"<var>\":\"<initial>\"},\"keys\":{\"<char>\":\"<action>\"}}\n'
    "   Each key maps a single pressed character to an action expression over the "
    "state vars: assignment with '=', string concat with '+', single-quoted "
    "literals, and the builtins calc(), to_str(), len(). Example calculator "
    "action: \"input=input+'7'\" or \"result=calc(input)\". No loops or other "
    "functions are allowed.\n"
    "   For an app that SAVES data, set permissions {\"fs_read\":true,"
    "\"fs_write\":true} and use fs_put('key', value) to save and fs_get('key') to "
    "load. Example notes app: letter keys do \"note=note+'a'\" etc., a save key "
    "does \"saved=fs_put('note', note)\", a load key does \"note=fs_get('note')\". "
    "Include the letter keys the user needs.\n"
    "3) Otherwise, reply with one short plain-text sentence.\n"
    "When you emit an intent or app, output ONLY the JSON object."
)


# ---- backend -----------------------------------------------------------

# A reference calculator app in the AIOS app-DSL, used as a few-shot example in
# the system prompt so the model emits a complete, valid app.
CALCULATOR_APP = (
    '{"aios_app":"1","id":"calculator","title":"Calculator",'
    '"permissions":{"fs_write":false,"network":false},'
    '"limits":{"max_steps":2000},'
    '"state":{"input":"","result":"0"},'
    '"keys":{'
    '"0":"input=input+\'0\'","1":"input=input+\'1\'","2":"input=input+\'2\'",'
    '"3":"input=input+\'3\'","4":"input=input+\'4\'","5":"input=input+\'5\'",'
    '"6":"input=input+\'6\'","7":"input=input+\'7\'","8":"input=input+\'8\'",'
    '"9":"input=input+\'9\'","+":"input=input+\'+\'","-":"input=input+\'-\'",'
    '"*":"input=input+\'*\'","/":"input=input+\'/\'",'
    '"=":"result=calc(input)","c":"input=\'\';result=\'0\'"}}'
)

# Few-shot the app schema: small models copy a full example far better than they
# follow an abstract spec. Append a complete, working calculator to the prompt.
SYSTEM_PROMPT += (
    "\n\nWhen asked to create a calculator, output EXACTLY an app like this "
    "(include ALL digit keys 0-9, the operators, '=' and 'c'):\n" + CALCULATOR_APP
)


# MLX: Apple's framework for M-series. Runs 4-bit quantized models on the GPU --
# least RAM, fastest. Needs `pip install mlx-lm` in the venv.
_MLX = {}

# Long-term semantic memory (TurboVec + local embeddings, see memory.py).
# None when disabled (--no-memory) or when its deps aren't installed.
MEMORY = None

# Conversation history (multi-turn memory) for the current QEMU session, so the
# model remembers earlier turns -- e.g. "create a calculator" then "add a % key".
# Reset per connection (a new QEMU run = a fresh conversation). Bounded so the
# context (and prefill time) can't grow without limit.
HISTORY = []          # list of {"role": "user"|"assistant", "content": str}
HISTORY_MAX_MSGS = 16  # keep the last 8 exchanges


def reset_history():
    HISTORY.clear()


# ---- long-term memory (TurboVec) ----------------------------------------

def memory_context(prompt):
    """Past records relevant to this prompt, as a block for the system prompt."""
    if MEMORY is None:
        return ""
    hits = MEMORY.recall(prompt, k=3)
    if not hits:
        return ""
    return ("\n\nRelevant past interactions (long-term memory, possibly from "
            "earlier sessions):\n" + "\n".join("- " + t for _, t in hits))


def memory_store(prompt, reply):
    """Persist a compact record of this exchange for future recall."""
    if MEMORY is None:
        return
    # Skip OS-generated event prompts (S8 fault reports): they aren't user
    # requests and would pollute recall.
    if prompt.startswith("A user task in AIOS"):
        return
    summary = reply
    try:
        obj = json.loads(reply)
        if "aios_app" in obj:
            summary = (f"generated app id='{obj.get('id')}' "
                       f"title='{obj.get('title')}'")
        elif "aios_intent" in obj:
            summary = f"ran the '{obj.get('verb')}' verb"
    except (ValueError, TypeError):
        pass
    try:
        MEMORY.add(f"user asked: {prompt} -> assistant: {summary[:300]}")
    except Exception as e:  # memory failure must never break a reply
        print(f"[memory] store failed: {e}", file=sys.stderr)


def backend_mlx(prompt, args):
    from mlx_lm import load, generate
    name = args.model or "mlx-community/Qwen2.5-14B-Instruct-4bit"
    if _MLX.get("name") != name:
        print(f"[bridge] loading {name} (MLX) ...", file=sys.stderr)
        model, tok = load(name)
        _MLX.update(name=name, model=model, tok=tok)
    model, tok = _MLX["model"], _MLX["tok"]

    messages = [{"role": "system", "content": SYSTEM_PROMPT + memory_context(prompt)}]
    messages += HISTORY
    messages += [{"role": "user", "content": prompt}]

    p = tok.apply_chat_template(messages, add_generation_prompt=True)
    reply = generate(model, tok, p, max_tokens=512, verbose=False).strip()

    # remember this turn for follow-ups, then trim to the recent window
    HISTORY.append({"role": "user", "content": prompt})
    HISTORY.append({"role": "assistant", "content": reply})
    del HISTORY[:-HISTORY_MAX_MSGS]
    memory_store(prompt, reply)
    return reply


# ---- framing ------------------------------------------------------------

def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return buf


def read_frame(sock):
    # resync to MAGIC
    window = b""
    while window != MAGIC:
        window = (window + recvn(sock, 1))[-4:]
    type_ = recvn(sock, 1)[0]
    seq = struct.unpack("<H", recvn(sock, 2))[0]
    (length,) = struct.unpack("<I", recvn(sock, 4))
    if length > MAX_PAYLOAD:
        raise ValueError(f"payload too large: {length}")
    payload = recvn(sock, length) if length else b""
    (crc,) = struct.unpack("<I", recvn(sock, 4))
    ok = (crc == (zlib.crc32(payload) & 0xFFFFFFFF))
    return type_, seq, payload, ok


def send_frame(sock, type_, payload, seq):
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    frame = (MAGIC + bytes([type_]) + struct.pack("<H", seq)
             + struct.pack("<I", len(payload)) + payload + struct.pack("<I", crc))
    sock.sendall(frame)


# ---- server loop --------------------------------------------------------

def serve_conn(conn, backend, args):
    while True:
        try:
            type_, seq, payload, ok = read_frame(conn)
        except (ConnectionError, OSError):
            return
        if type_ != REQ:
            continue
        if not ok:
            print("[bridge] bad CRC on request, sending err", file=sys.stderr)
            send_frame(conn, ERR, b"bad crc", seq)
            continue
        prompt = payload.decode("utf-8", "replace")
        print(f"[bridge] req#{seq}: {prompt!r}", file=sys.stderr)
        try:
            reply = backend(prompt, args)
            send_frame(conn, RESP, reply.encode("utf-8"), seq)
            print(f"[bridge] resp#{seq}: {reply[:80]!r}", file=sys.stderr)
        except Exception as e:  # backend failure must not kill the bridge
            msg = f"backend error: {e}"
            print("[bridge]", msg, file=sys.stderr)
            send_frame(conn, ERR, msg.encode("utf-8"), seq)


def main():
    ap = argparse.ArgumentParser(description="AIOS host AI bridge (Apple MLX)")
    ap.add_argument("--socket", default="/tmp/aios-ai.sock", help="UNIX socket path")
    ap.add_argument("--model", default=None,
                    help="MLX model id (default mlx-community/Qwen2.5-14B-Instruct-4bit)")
    ap.add_argument("--no-memory", action="store_true",
                    help="disable long-term memory (TurboVec)")
    ap.add_argument("--memory-dir",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         ".memory"),
                    help="where the memory index + texts persist")
    args = ap.parse_args()

    backend = backend_mlx

    if not args.no_memory:
        global MEMORY
        try:
            from memory import Memory
            MEMORY = Memory(args.memory_dir)
        except Exception as e:  # missing deps etc. -- run without memory
            print(f"[bridge] long-term memory disabled: {e}", file=sys.stderr)

    if os.path.exists(args.socket):
        os.unlink(args.socket)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(args.socket)
    srv.listen(1)
    print(f"[bridge] listening on {args.socket} "
          f"(MLX: {args.model or 'mlx-community/Qwen2.5-14B-Instruct-4bit'})",
          file=sys.stderr)

    try:
        while True:
            conn, _ = srv.accept()
            print("[bridge] QEMU connected", file=sys.stderr)
            reset_history()   # fresh conversation per QEMU session
            with conn:
                serve_conn(conn, backend, args)
            print("[bridge] QEMU disconnected", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        if os.path.exists(args.socket):
            os.unlink(args.socket)


if __name__ == "__main__":
    main()
