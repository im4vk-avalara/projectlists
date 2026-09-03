# AIOS — AI-Native OS Design

> Status: **DRAFT for review.** Target architecture; not yet built. See
> `STATUS.md` for what exists today (Phase 10: kernel with paging + allocator,
> ring 0 only, single-keypress demo dispatch, no userland/FS/network).

## 0. The thesis

AIOS is an OS where **the AI *is* the interface**. There is no traditional
fixed-command shell as the primary UX. You boot, and you *talk to the OS*. The
AI — its SDK burned into the OS image — is the **universal control plane** for
user space and (safely) for the kernel: it answers, inspects machine state,
performs actions, and builds apps. The user holds **full authority** over the
whole machine *through* the AI.

App generation ("create a calculator app") is **one capability** among many, not
the headline. The headline is: the AI runs the user's whole experience.

### The four non-negotiables

1. **AI is the user-space interface.** The boot prompt is a natural-language AI
   console. Everything the user does flows through `ai-daemon` (ring 3).
2. **AI authority is real but bounded — never raw kernel code.** The AI has full
   *visibility* into the kernel and full *authority via a closed, validated
   command/intent surface* (enumerable verbs like `meminfo`, `map`, `kill`). The
   AI emits **structured intents (data)**, the OS validates them, then executes.
   The AI never emits or runs machine/kernel code.
3. **Kernel stability is independent of AI correctness.** A hallucinated,
   oversized, or malformed AI response can only produce a *rejected intent* or a
   *rejected app* — never a kernel fault.
4. **Local model, offline by default — no cloud, no API keys.** The AI backend
   sits behind one `ai_backend` interface. v1 runs a capable local model on the
   **host** (llama.cpp/Ollama) reached over a **host bridge** — no internet, no
   key, no in-kernel TCP/TLS. A tiny model embedded *inside* AIOS is a later
   "purist" milestone; both swap in behind the same interface with zero
   OS-side change.

### Honest constraint note

AIOS is **32-bit x86, custom boot sector (no GRUB), pure C, ring 0 today.** This
design keeps those choices and deliberately **does not** build a TCP/IP+TLS
stack (the AI is a *local model*, reached over a host bridge — no cloud, so no
networking/crypto needed; see §9). A capable model good enough to emit valid
DSL needs GBs of RAM + SSE/FP + (realistically) 64-bit, which is why v1 runs it
on the host and the in-AIOS embedded model is a later milestone (§15).

---

## 1. High-level architecture (text diagram)

```
┌──────────────────────────── AIOS image (QEMU) ────────────────────────────┐
│ RING 3 (user space)                                                        │
│                                                                            │
│   keyboard ─▶ ┌───────────────┐  the ONLY prompt is the AI console         │
│               │  AI console   │  (line editor; '/' = dev cmd escape)        │
│               │  (input loop) │                                            │
│               └──────┬────────┘                                            │
│                      │ natural language                                    │
│                      ▼                                                      │
│               ┌───────────────┐    ai_backend iface                        │
│               │   ai-daemon   │───────────────────┐                        │
│               │ prompt build  │                   │                        │
│               │ + dispatch    │◀──────────────────┘ (model reply)          │
│               └──┬────────┬───┘                                            │
│         intent JSON│      │ app-DSL JSON                                    │
│                    ▼      ▼                                                 │
│            ┌──────────┐ ┌──────────────┐  ┌──────────────────────────┐     │
│            │ intent   │ │ app-builder  │  │ app runtime (DSL interp.) │     │
│            │ validator│ │ + validator  │─▶│ + sandboxed generated apps│     │
│            └────┬─────┘ └──────────────┘  └─────────────┬─────────────┘     │
│                 │ validated verb                        │ restricted        │
│ ════════════════╪═══════════════════════════════════════╪═══════ syscall ══│
│                 ▼                                        ▼     boundary     │
│ RING 0 (kernel)                                                            │
│  ┌───────────────────────────────────────────────────────────────────────┐│
│  │ syscall dispatch │ CONTROL SURFACE (enumerable validated verbs) │ sched ││
│  │ paging/frames │ kmalloc │ IDT/PIC/PIT │ keyboard │ serial / AI bridge   ││
│  └───────────────────────────────────────────────────────────────────────┘│
│                                   │ COM2 / virtio-serial                    │
└───────────────────────────────────┼────────────────────────────────────────┘
                                     ▼   (QEMU chardev → host process)
                          ┌────────────────────────┐
                          │  host ai-bridge proc    │  thin adapter, no key,
                          │  (python / node)        │  no internet, no TLS
                          └───────────┬─────────────┘
                                      ▼  local model on host
                          ┌────────────────────────┐
                          │ llama.cpp / Ollama (8B) │  fully offline
                          └────────────────────────┘
```

Two kinds of structured output the model can emit, both **validated as data**
before anything happens:
- **Intent** → a verb against the kernel **control surface** (read or, if
  permitted, mutate machine state).
- **App-DSL** → a declarative app definition, run by the sandboxed interpreter.

Everything else from the model is just text shown to the user.

---

## 2. Module breakdown

| Module | Ring | Responsibility |
| ------ | ---- | -------------- |
| **kernel** | 0 | syscalls, the **control surface** (validated verb dispatch), scheduling, memory, device drivers (kbd, serial, AI bridge). Never links AI/HTTP/untrusted parsing. |
| **AI console** | 3 | The only prompt. Line editor (buffer until Enter, backspace, echo). Plain line → ai-daemon; `/`-prefixed line → dev-command table (scaffolding). |
| **ai-daemon** | 3 | Owns `ai_backend`. Builds prompts, calls the bridge, classifies the model reply into {text, intent, app-DSL}, routes each to its validator. The "SDK burned into the OS" lives here. |
| **intent validator** | 3 (pure lib) | Hard gate for control-surface verbs: known verb? args in range? permission held? Rejects anything else. |
| **app-builder + app validator** | 3 (pure lib) | Normalizes + schema/grammar-checks generated app definitions (§6/§7). |
| **app runtime** | 3 | Interprets a *validated* app-DSL (small VM). Re-runs the validator at load time (consumer-side gate). Enforces `max_steps`/mem budget in the interpret loop. |
| **control surface** | 0 | The enumerable set of kernel verbs (§5) the AI may invoke via syscall, each kernel-side permission-checked. The bridge between "AI authority" and "kernel safety." |
| **AI bridge** | 0 + host | Kernel serial device + framing; host process forwards to a local model (llama.cpp/Ollama). No key/TLS/internet. |
| **filesystem (VFS)** | 0 (deferred) | RAM namespace for persisting apps/intents. Off the v1 critical path. |
| **networking** | 0 (not needed) | Local model ⇒ no network stack required for v1, possibly ever. |

*Sandbox model (v1): interpreter-based isolation.* Generated apps are
interpreted DSL data living inside the runtime task — they cannot express raw
memory or syscalls, so no per-app page directory is needed. The kernel isolates
the **runtime task** from itself (ring 3 + its own address space); the
interpreter isolates **apps** from each other via the bounded grammar +
`max_steps`. Per-process isolation is a v2 concern only if native apps are ever
introduced (the design says they never are).

---

## 3. Roadmap — S1→S6 (boot → AI runs the machine)

Phases P0–P10 (kernel base) already exist. New work below. Each step is
independently demoable; v1 prototype = **through S6**.

| Step | Deliverable | Demo / gate |
| ---- | ----------- | ----------- |
| **S1 — Ring 3 + syscalls** | Extend GDT (user code/data segs), add a **TSS** (ring-0 stack for interrupts), `int 0x80` gate, minimal syscalls (`write`, `read`, `exit`, `yield`). One ring-3 program. | User-mode program prints via syscall + exits; a bad syscall kills only that task, kernel survives. |
| **S2 — AI console (line editor)** | Replace single-key dispatch in `kernelmain.c` with a **line buffer** (echo, backspace, Enter). Lines route: plain → (stub) AI; `/cmd` → dev-command table calling the existing kernel functions. Refactor the old `switch` arms into named functions shared by both paths. | Type `/meminfo`, `/uptime`, `/map` etc. and get the old demo behavior via *typed words*, not single keys. |
| **S3 — AI bridge + ai-daemon passthrough** | COM2 framed bridge (§9) + host `ai-bridge` adapter to a **local** llama.cpp/Ollama model (offline, no key); ai-daemon sends prompt, shows reply. Plain console lines now reach the model. | Boot → type "what can you do?" → local model answers. **The AI is now the interface.** |
| **S4 — Control surface (read-only)** | Define the intent schema (§5). Model may emit a read intent (`uptime`, `meminfo`, `ps`, `peek`). intent-validator gates it; kernel executes; result fed back to the model to phrase for the user. | "How much memory is free?" → AI emits `meminfo` intent → real kernel stats → AI explains them. Zero mutation risk. |
| **S5 — Control surface (mutating)** | Add validated *mutating* verbs reusing existing demo actions (`map`/`unmap`, `alloc`/`free`, `frame`/`unframe`, `kill`). Permission-checked kernel-side. | "Map a page at 0x80000000 and write to it" → validated verbs → real effect, narrated by the AI. **User has authority, safely.** |
| **S6 — App generation (one capability)** | app-DSL + interpreter + app-validator (run in the runtime). NL → app-DSL → validate → interpret in sandbox. | "Create a calculator app" → sandboxed calculator runs; garbage model output → clean rejection, kernel alive. |

**Post-prototype (not on critical path):** VFS + persistence ("modify the notes
app"), IPC-separated services, preemption, real network stack, local model.

---

## 4. First-prototype scope

**In (S1→S6, simplified):** ring 3 + a handful of syscalls; AI console as the
only prompt; host bridge (no in-OS net/TLS); read + a small set of mutating
control verbs reusing today's paging/alloc demo functions; app-DSL limited to a
**calculator-class app**; both validators (intent + app) as pure libs run at the
consumer.

**Out (deferred):** filesystem/persistence, IPC service split, preemption, real
networking, WASM, multiple permission tiers, local model.

**Definition of done:**
1. Boot AIOS → the prompt is a natural-language AI console (no command keys).
2. "How much free memory?" → AI reports *real* kernel stats via a validated intent.
3. "Map a page and write 0xDEADBEEF" → happens for real, narrated by the AI.
4. "Create a calculator app" → a sandboxed calculator runs.
5. Feeding the model deliberate garbage (bad intent or bad app) → clean
   rejection, kernel and console still alive.

---

## 5. The control surface (AI → kernel authority, as data)

This is the keystone of "AI controls the machine without running kernel code."
The model emits an **intent** (JSON); the intent-validator and kernel gate it.

```jsonc
{
  "aios_intent": "1",
  "verb": "map",                 // must be in the enumerable verb table
  "args": { "vaddr": "0x80000000", "flags": "rw" },
  "reason": "user asked to map a test page"   // for the audit log / narration
}
```

**Verb table (v1)** — each maps to an existing kernel function; nothing else is
callable:

| Verb | Kind | Maps to | Permission |
| ---- | ---- | ------- | ---------- |
| `uptime` | read | PIT uptime | always |
| `meminfo` | read | heap + frame stats | always |
| `ps` | read | task list | always |
| `peek` | read | read mapped u32 (fault-safe) | always |
| `map` / `unmap` | mutate | `paging_map`/`paging_unmap` | `kernel_ctl` |
| `alloc` / `free` | mutate | `kmalloc`/`kfree` | `kernel_ctl` |
| `frame` / `unframe` | mutate | `frame_alloc`/`frame_free` | `kernel_ctl` |
| `kill` | mutate | terminate a task by id | `kernel_ctl` |
| `fault` | mutate | trigger test exception (debug) | `kernel_ctl` |

Rules: unknown verb → reject. Args out of range/format → reject. Mutating verb
without `kernel_ctl` permission → reject (the *user* grants this to the session;
the AI can't self-grant). Every executed intent is logged (verb + args + reason)
so the user can audit what the AI did. The verb table is **append-only and
human-authored** — the AI can never extend it.

---

## 6. The app-DSL (one capability) + calculator example

Declarative JSON; the model never emits imperative code. Closed widget
vocabulary + a bounded expression grammar (assignment to declared state,
arithmetic/compare/concat, a fixed builtin allowlist `calc/to_str/len`; **no
loops, recursion, function defs, raw memory, or syscall names**; hard
`max_steps` budget). UI is **key-driven** (text console, no mouse): buttons get
auto-assigned hotkeys and use `on_key`.

```json
{
  "aios_app": "1",
  "id": "calculator",
  "title": "Calculator",
  "permissions": { "fs_read": false, "fs_write": false, "network": false },
  "limits": { "max_widgets": 32, "max_mem_kb": 32, "max_steps": 50000 },
  "state": { "input": "", "result": "0" },
  "ui": [
    { "type": "label", "id": "screen", "bind": "input" },
    { "type": "label", "id": "out",    "bind": "result" },
    { "type": "buttons", "items": [
      { "key": "0-9", "action": "push(key)" },
      { "key": "+",   "action": "push('+')" },
      { "key": "*",   "action": "push('*')" },
      { "key": "c",   "action": "clear()" },
      { "key": "=",   "action": "eq()" }
    ]}
  ],
  "actions": {
    "push":  "input = input + arg",
    "clear": "input = ''; result = '0'",
    "eq":    "result = to_str(calc(input))"
  }
}
```

---

## 7. Validator rules (apply to both intents and apps)

Pure, deterministic, run at the **consumer** (intent-validator before kernel
dispatch; app-validator in the runtime at load time — never trust the producer).

```
Common
 C1 Valid JSON, < 64 KB.                              else REJECT(malformed)
 C2 Correct schema tag (aios_intent / aios_app == "1"). else REJECT(version)
 C3 Only known top-level keys (no silent ignore).     else REJECT(unknown-key)

Intents
 I1 verb ∈ verb table.                                else REJECT(bad-verb)
 I2 args match the verb's arg spec (types/ranges).    else REJECT(bad-args)
 I3 mutating verb ⇒ session holds kernel_ctl.         else REJECT(eperm)

Apps
 A1 id matches ^[a-z0-9-]{1,32}$.                      else REJECT
 A2 permissions: only known booleans; any 'true' must be user-authorized. else REJECT
 A3 limits ≤ system maxima.                            else CLAMP (warn)
 A4 every ui.type ∈ widget vocab; depth ≤ 8; nodes ≤ max_widgets. else REJECT
 A5 every bind/state ref declared in state.            else REJECT
 A6 action bodies tokenize to {state key, allowlisted builtin, literal,
    operator, 'arg'/'key'} only; no identifier == syscall/verb name or 'eval'. else REJECT
 A7 fs_*/network builtin used but permission false.    else REJECT

On any REJECT: structured error returned to ai-daemon; nothing executes.
```

---

## 8. Syscall / API surface for sandboxed apps

Apps never call kernel syscalls directly — they call runtime intrinsics; the
runtime makes the allowlisted syscall on their behalf.

| # | syscall | notes |
| - | ------- | ----- |
| 0 | `sys_exit` | always |
| 1 | `sys_write` | only the app's own console handle |
| 2 | `sys_read` | input events only |
| 3 | `sys_yield` | cooperative |
| 4 | `sys_open` | path rewritten into `/apps/<id>/` jail (post-VFS) |
| 5 | `sys_close` | |
| 6 | `sys_getpid` | |

DSL intrinsics: state ops, `calc`, `to_str`, `len`, and — only if permitted —
`fs_get/fs_put`. The DSL has **no** way to name a raw syscall number or a
control-surface verb.

---

## 9. How `ai-daemon` communicates

```
keyboard ─▶ AI console ─(plain line)─▶ ai-daemon
                       ◀─(text reply / narration)─

ai-daemon ─prompt─▶ bridge syscall ─▶ kernel bridge dev ─COM2─▶ host ai-bridge ─▶ local model (llama.cpp/Ollama)
ai-daemon ─model reply─▶ classify ─▶ { text → console
                                       intent → intent-validator → control surface (syscall)
                                       app-DSL → app-builder → app-validator → runtime }
```

- **AI backend:** behind `ai_backend`. v1 = **bridge to a host-local model**:
  ai-daemon serializes `{model, system, messages, max_tokens}`; the **host**
  ai-bridge is a thin adapter that forwards it to a local llama.cpp/Ollama model
  and streams the reply back. No API key, no internet, no TLS — fully offline.
  Later milestones (§15) swap the backend for an embedded in-AIOS model behind
  the same interface.
- **Structured output:** ask the model to return intent/app JSON via the SDK's
  structured-output / tool-use mechanism to minimize parse failures; the bounded
  repair loop (§11) is the backup.

**Bridge frame format (host ↔ OS):**
```
MAGIC(4) | type(1) | seq(2) | len(4) | payload(len) | crc32(4)
type: 0=req 1=resp 2=err 3=stream-chunk 4=stream-end
```
Length-prefixed + CRC so noisy/garbage frames are detected and dropped, never
parsed blindly.

---

## 10. Security & safety model

Defense in depth — each layer assumes the one above is buggy:

1. **Generation:** constrained prompts; the model can only usefully emit text,
   an intent, or app-DSL. All treated as hostile input.
2. **Validation:** deterministic gates (§7) at the consumer. Default-deny
   permissions; closed verb table + closed widget/expr vocab; size/limit clamps.
3. **Kernel + runtime enforcement (assumes 1&2 fallible):**
   - Control surface is **append-only, human-authored**; the AI cannot add verbs.
   - Mutating verbs require `kernel_ctl`, granted by the *user* per session, not
     self-grantable by the AI. Every executed intent is **audit-logged**.
   - Ring 3 + separate address space isolates the runtime task from the kernel.
   - Interpreter enforces `max_steps` + memory cap; the DSL cannot express raw
     memory or syscalls, so a bad app can only spin within its budget then die.
   - Model runs locally and offline — no API key, no data leaves the machine,
     no network attack surface.

| Threat | Mitigation |
| ------ | ---------- |
| AI emits kernel/native code | Not expressible; only intents/DSL accepted, both validated |
| AI escalates kernel control | Closed verb table + `kernel_ctl` user-granted + audit log |
| App reads other app / kernel memory | Ring 3 + bounded interpreter (no raw memory in DSL) |
| App exhausts CPU/RAM | `max_steps` + mem cap in interpret loop |
| Malformed AI/bridge data | CRC framing + size cap + schema validation |
| Data exfiltration / network attack | Local model, offline; no internet, no key |

---

## 11. Failure handling for hallucinated / invalid output

Every failure is recoverable and surfaced — never a kernel event:

| Failure | Detection | Response |
| ------- | --------- | -------- |
| Non-JSON / truncated | parser (C1) | one reprompt ("return only valid JSON/intent"); 2nd fail → "couldn't do that, rephrase." |
| Unknown/over-range intent | I1–I2 | reject; AI tells user it can't do that verb. |
| Unauthorized mutation | I3/A2 | reject; AI says it needs `kernel_ctl`/permission the user hasn't granted. |
| App schema/grammar violation | A1–A7 | reject; optional one model repair attempt with the reason. |
| Over-limit app resources | A3 | clamp + warn; app still runs. |
| App faults at runtime | interpreter error / budget exceeded | kill that app only; capture context (last action, error). |
| "Debug this app crash" | uses captured context | AI gets context + def, returns a patched def, re-validated, re-run. |
| Bridge/host offline | bridge frame timeout | "AI backend offline"; `/` dev commands still work locally. |

Repair attempts are **bounded** (max 1–2) to avoid loops and wasted inference time.

---

## 12. Directory structure

```
AIOS/
├── bootloader.s loader.s kernelmain.c link.ld Makefile Dockerfile   # existing
├── include/                 # existing kernel headers + new:
│   ├── syscall.h  task.h  control.h   # control-surface verb table + dispatch
│   ├── bridge.h               # AI bridge frame format
│   └── (vfs.h sandbox.h ipc.h — post-prototype)
├── lib/                      # existing kernel impls + new:
│   ├── syscall.c task.c control.c bridge.c
├── user/                     # NEW — ring-3 components (flat binaries)
│   ├── crt0.s                 # user entry + syscall stubs
│   ├── console/               # AI console: line editor + dev-command table
│   ├── ai-daemon/             # ai_backend iface, prompt build, reply classify
│   │   ├── intent.c           # intent validator
│   │   ├── builder.c          # app-builder
│   │   └── appval.c           # app validator
│   └── runtime/               # app-DSL interpreter + key-driven widgets
├── apps/                     # seeded app defs (calculator.json)
├── host/ai-bridge/           # NEW — runs on macOS, forwards to local model (no key/TLS)
├── docs/{DESIGN.md, intent-schema.md, app-dsl.md}
└── STATUS.md README.md PROMPT.md
```

---

## 13. Build / run (QEMU)

```bash
make docker-image
make docker-build              # produces AIOS.img

# plain kernel (today)
make docker-run

# with AI: run a local model, start the bridge adapter, then QEMU with COM2 → bridge
ollama serve &                                   # or llama.cpp server — fully offline
python host/ai-bridge/bridge.py --model llama3.1:8b --socket /tmp/aios-ai.sock &
qemu-system-i386 \
  -drive format=raw,file=AIOS.img \
  -chardev stdio,id=ch0,logfile=aios.log,signal=off -serial chardev:ch0 \
  -chardev socket,id=ai,path=/tmp/aios-ai.sock -serial chardev:ai
# COM1 = console/log (existing), COM2 = AI bridge (new). No API key, no internet.
```
A `make docker-run-ai` target will wrap the model + bridge + QEMU invocation.

---

## 14. What NOT to do

- **Do not** let the model emit C/asm/machine code, bytecode the kernel runs, or
  raw syscall/verb sequences. AI output is *data* (text, intent, or app-DSL).
- **Do not** let the AI extend the control-surface verb table at runtime. It is
  human-authored and append-only.
- **Do not** let the AI self-grant `kernel_ctl` or app permissions — the user grants.
- **Do not** link any AI SDK / HTTP / unbounded parsing into ring 0.
- **Do not** `eval` model expressions; use the bounded `calc()` parser.
- **Do not** reintroduce a cloud/API-key dependency for v1 — the model is local
  and offline. (Cloud can be an *optional* alternate backend later, never required.)
- **Do not** trust bridge/model bytes: CRC-framed, size-capped, schema-validated.
- **Do not** retry the model unboundedly (cost + loops). Cap repair attempts.
- **Do not** block the OS on a model call; `/` dev commands work without the AI.
- **Do not** skip the kernel/interpreter enforcement because a validator "already
  checked." Assume each layer can be wrong.

---

## 15. Model backend path (local-first)

`ai_backend` is the seam — swap implementations, nothing else changes:

1. **v1 — host local model** (this design): llama.cpp/Ollama on the host (e.g.
   an 8B), reached over the bridge. Offline, no key, no TLS, no internet. Model
   is capable enough to emit valid intents + app-DSL.
2. **v2 — embedded tiny model inside AIOS (the "purist" milestone):** port a
   llama2.c-style model (~15M–110M params) to run *literally inside AIOS* — zero
   host help. Prereqs: FPU/SSE init, hundreds of MB of RAM (so real memory mgmt
   + likely a 64-bit move), and a filesystem/large image to hold weights.
   Capability is toy-grade — great as a "the OS thinks by itself" showcase, but
   too weak to be the app-generation workhorse. Same `ai_backend` interface.
3. **Optional — bigger embedded model / 64-bit AIOS:** only worthwhile after a
   64-bit + SSE/AVX + paging-for-GBs foundation exists. Long-horizon research.
4. **Optional — cloud backend:** could be added as an *alternate* backend behind
   the same interface, but is never required (would reintroduce keys/TLS/net).

---

## Decisions locked for v1 (from review)

- **AI is the sole user interface;** kernel authority via a validated,
  append-only **control-surface verb table** (AI emits intents as data, never
  kernel code). ✔ confirmed
- **Sandbox = interpreter-based isolation** (no per-app page dirs in v1). ✔
- **Validators run at the consumer** (intent before kernel dispatch; app in the
  runtime). ✔
- **VFS + IPC service-split are post-prototype;** v1 may co-locate
  console+daemon+runtime and use in-memory state. ✔
- **Input model = line editor + `/` dev-command escape;** old single-key demo
  actions become control-surface verbs (and `/` dev commands). ✔
- **Text-mode UI is key-driven** (`on_key`, auto-assigned hotkeys). (default;
  revisit if a framebuffer UI is wanted later)
- **AI backend = host-local model now, embedded-in-AIOS later.** v1 runs
  llama.cpp/Ollama on the host via the bridge — offline, no API key, no cloud,
  no TLS. Embedding a tiny model inside AIOS is a later purist milestone (§15).
  ✔ confirmed
```