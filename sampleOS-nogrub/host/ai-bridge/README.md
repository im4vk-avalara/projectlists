# AIOS host AI bridge

`bridge.py` is the host-side adapter for the AI bridge. AIOS (the guest) talks to
it over COM2 using a small framed protocol (see `include/bridge.h`); this process
forwards each prompt to the model and frames the reply back. Everything is local
— **no API key, no cloud, no TLS**.

The model is **`mlx-community/Qwen2.5-14B-Instruct-4bit`**, a 4-bit quantized LLM
run via **Apple MLX** on the GPU — low RAM, fast, and reliable at emitting valid
intents and a complete, working calculator app.

**Long-term memory (`memory.py`):** past exchanges are embedded
(sentence-transformers `all-MiniLM-L6-v2`, ~90 MB, local) and indexed with
**TurboVec** (Rust vector index, TurboQuant 4-bit compression). On every prompt
the top matching past records (score ≥ 0.30) are injected into the system
prompt, so the OS remembers across QEMU sessions and bridge restarts — e.g.
*"open that app I made for writing things down"* finds the notes app from last
week. The index + texts persist in `host/ai-bridge/.memory/`. Disable with
`--no-memory`; delete the `.memory/` dir to forget everything. Per-session
`HISTORY` (last 16 messages, reset per QEMU connection) remains the short-term
layer. Still fully offline.

## Setup + run

```bash
# one-time: venv + deps  (Python <= 3.13; mlx has no 3.14 wheels)
python3.12 -m venv .venv
.venv/bin/pip install mlx-lm turbovec sentence-transformers

# run the bridge in the venv  (no `activate` needed — just call .venv/bin/python)
.venv/bin/python host/ai-bridge/bridge.py

# after the first run the model is cached; skip all network with HF_HUB_OFFLINE:
HF_HUB_OFFLINE=1 .venv/bin/python host/ai-bridge/bridge.py
```

- **No activation step**: the system `python3` has no mlx; only `.venv/bin/python`
  does. Always launch the bridge with `.venv/bin/python`.
- **Model location**: weights cache in `~/.cache/huggingface/hub`. The 14B-4bit is
  ~8 GB. (`--model <other-mlx-id>` would download a different model on first use.)
- **Speed (M-series, 4-bit 14B)**: load ~8 s once; intents ~4–5 s; app generation
  ~14 s. The kernel bridge timeout is ~180 s so a cold load never trips it.
- **Behind a corporate proxy** (TLS interception), the first model download needs
  your Mac's CA bundle:
  ```bash
  security find-certificate -a -p /System/Library/Keychains/SystemRootCertificates.keychain >  /tmp/aios-cas.pem
  security find-certificate -a -p /Library/Keychains/System.keychain                          >> /tmp/aios-cas.pem
  REQUESTS_CA_BUNDLE=/tmp/aios-cas.pem CURL_CA_BUNDLE=/tmp/aios-cas.pem \
    .venv/bin/python host/ai-bridge/bridge.py
  ```

## Wiring it to AIOS

Two terminals (the bridge must stay running; QEMU connects to it as a client):

```bash
# terminal 1 — bridge (stays running)
.venv/bin/python host/ai-bridge/bridge.py

# terminal 2 — build + run AIOS with COM2 wired to the bridge
make docker-run-ai
```

Then in the AIOS console, e.g.:
- `how much memory is free?` · `what is 347*892` (calc verb)
- `/grant` then `map a page` (mutating verbs, audited)
- `create a calculator app` → then `add a percent key` (multi-turn modify)
- `list my apps` · `open the calculator` (saved-app library)
- `create a notes app that saves my notes` (uses fs_get/fs_put storage)
- after a QEMU restart: `open the app I made for writing things down`
  (long-term memory recalls the notes app from the previous session)

The kernel's bridge timeout is ~180 s so a cold model load doesn't trip it.
