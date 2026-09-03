# AIOS — AI-Native OS Design

> Status: **DRAFT for review.** This is the target architecture. It is *not* yet
> built. See `STATUS.md` for what actually exists today (Phase 10: kernel with
> paging + allocator, ring 0 only, no userland/FS/network).

## 0. Guiding principles (the non-negotiables)

1. **AI lives in user space, never the kernel.** Intelligence is a user-space
   daemon (`ai-daemon`). The kernel never links an AI SDK and never parses model
   output.
2. **AI output is untrusted data, never code.** The model emits an *app
   definition* (declarative JSON/DSL). It is validated, then interpreted by a
   sandboxed runtime. The model never produces machine code, kernel code, or raw
   syscalls.
3. **Kernel stability is independent of AI correctness.** A hallucinated, huge,
   or malformed AI response can only cause a rejected app — never a kernel fault.
4. **Cloud first, local later.** The AI backend is behind one interface
   (`ai_backend`). v1 calls a cloud API *through a host bridge*; a local model
   runtime can replace it later without touching the rest of the OS.

### Honest constraint note

The original brief assumed GRUB/Multiboot, optional x86_64, optional Rust, and a
TCP/IP+TLS stack. AIOS today is **32-bit x86, custom boot sector (no GRUB), pure
C, ring 0 only.** This design keeps those choices and deliberately **avoids
writing a TCP/IP + TLS stack** — see §9 for the host-bridge decision, which is
the single most important pragmatic call in this document.

---

## 1. High-level architecture (text diagram)

```
┌──────────────────────────── AIOS image (QEMU) ────────────────────────────┐
│                                                                            │
│  RING 3 (user space)                                                       │
│  ┌──────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │  shell   │   │ ai-daemon  │   │ app runtime  │   │ generated apps   │   │
│  │ (NL +    │──▶│ app-builder│──▶│  (DSL/byte-  │──▶│ calc, notes, ... │   │
│  │  cmds)   │   │ + validator│   │   code VM)   │   │ (sandboxed)      │   │
│  └────┬─────┘   └─────┬──────┘   └──────┬───────┘   └────────┬─────────┘   │
│       │               │                 │                    │             │
│       │        ai_backend iface         │  app syscall API (restricted)    │
│       │               │                 │                    │             │
│  ═════╪═══════════════╪═════════════════╪════════════════════╪═══ syscall ═│
│       ▼               ▼                 ▼                    ▼   boundary   │
│  RING 0 (kernel)                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ syscall dispatch │ scheduler │ VFS │ sandbox/perm manager │ IPC (ports)│ │
│  │ paging/frames    │ kmalloc   │ IDT/PIC/PIT │ keyboard │ serial/bridge  │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                   │                                        │
│                          virtio-serial / COM2                              │
└───────────────────────────────────┼────────────────────────────────────────┘
                                     ▼   (QEMU chardev → host process)
                          ┌────────────────────────┐
                          │  host ai-bridge proc    │  ← holds API key, does
                          │  (Python/Node on macOS) │     HTTPS/TLS to cloud
                          └───────────┬─────────────┘
                                      ▼
                              Cloud AI API (Claude)
```

The AI backend talks to the cloud **from the host**, not from inside the kernel.
The OS sends a request frame over a serial/virtio channel; the host bridge does
the TLS call and returns the response. This removes the need for an in-kernel
network + TLS stack for the prototype, while keeping the OS-side interface
identical to what a future in-OS network path would expose.

---

## 2. Module breakdown

| Module | Ring | Responsibility | Talks to |
| ------ | ---- | -------------- | -------- |
| **kernel** | 0 | syscalls, scheduling, memory, IPC, VFS, sandbox enforcement, device drivers (kbd, serial, bridge) | everything via syscalls |
| **shell** | 3 | Reads user input. Distinguishes NL ("create a...") from builtins (`ls`, `run`, `ps`). Forwards NL to `ai-daemon` via IPC. Renders app output. | ai-daemon, runtime, VFS |
| **ai-daemon** | 3 | Owns the `ai_backend` interface. Builds prompts, sends via bridge, receives raw model output. Hands output to app-builder. Persistent service. | bridge (kernel), app-builder, VFS |
| **app-builder** | 3 (lib in ai-daemon) | Turns model output into a candidate app definition (parse, normalize, fill defaults). | validator |
| **validator** | 3 (lib) | Hard gate. Schema-checks the app def, enforces resource/permission limits, rejects anything outside the allowed grammar. Pure, deterministic, no I/O. | app-builder, runtime |
| **app runtime** | 3 | Interprets a validated app definition: a small VM/interpreter for the AIOS App DSL. Enforces per-app permissions at call sites. | kernel (restricted syscalls), VFS |
| **sandbox manager** | 0 + 3 | Per-app address space (own page directory), permission descriptor, resource quotas (mem, instr budget, syscall allowlist). Kernel enforces; runtime cooperates. | kernel paging, syscall dispatch |
| **filesystem (VFS)** | 0 | Namespaced storage. Apps confined to `/apps/<id>/data`. Persists app defs in `/apps`. | runtime, ai-daemon, shell |
| **networking** | 0 (deferred) | v1 = host bridge only (no IP stack). v2 = real driver + minimal stack, same `ai_backend` interface. | ai-daemon |

---

## 3. Phased roadmap (boot → AI-generated apps)

Phases P0–P10 already exist (kernel base). New work starts at **A-phases**.
Each A-phase is independently demoable.

| Phase | Deliverable | Gate / demo |
| ----- | ----------- | ----------- |
| **A1 — Userland & syscalls** | Ring 3, TSS, `int 0x80` gate, syscall table (`write`, `exit`, `yield`, `getpid`). One hardcoded ring-3 program. | A user-mode program prints via syscall and exits cleanly; bad syscall → killed, kernel survives. |
| **A2 — Cooperative scheduler + IPC** | Multiple tasks, `yield()`, message ports (kernel-mediated mailboxes). | shell task ↔ echo daemon round-trip over a port. |
| **A3 — In-memory VFS** | RAM filesystem, path namespace, `open/read/write/close` syscalls, `/apps` tree. | Write a file, read it back from another task. |
| **A4 — Host AI bridge** | `bridge` device (virtio-serial/COM2) + framing protocol; host `ai-bridge` process. | Kernel sends a string, host echoes via Claude, OS prints reply. |
| **A5 — ai-daemon (passthrough)** | Daemon owns `ai_backend`, prompt templating, request/response over bridge. shell `ask "..."` returns model text. | NL question → model answer in shell. |
| **A6 — App DSL + runtime (no AI)** | Define the App DSL (§5), write the interpreter, run a *hand-written* calculator app def. | Hand-written calc.json runs sandboxed. |
| **A7 — Validator** | Schema + rule engine (§7). Reject malformed/over-limit defs. | Fuzz/garbage defs all rejected; kernel never faults. |
| **A8 — End-to-end generation** | ai-daemon: NL → prompt → model → app-builder → validator → runtime. | "create a calculator app" produces a running app. |
| **A9 — Persistence & modify** | Save app defs to `/apps`; "modify the notes app to add search" reloads, re-prompts with current def, re-validates. | Edit-existing-app loop works. |
| **A10 — Sandbox hardening** | Per-app page dir, instruction/mem budgets, syscall allowlist per permission set, crash isolation + "debug this crash" using captured fault info. | Malicious/looping app is contained and killed; kernel + other apps unaffected. |

First prototype target = **through A8** (see §4).

---

## 4. Recommended first-prototype scope

Smallest thing that demonstrates the core thesis ("NL → validated → sandboxed
app"), cutting everything not essential:

**In scope (A1→A8, simplified):**
- Ring-3 userland + minimal syscalls (`write`, `read`, `exit`, `yield`, `open`, `ipc_send`, `ipc_recv`).
- Cooperative scheduler (no preemption yet).
- RAM-only VFS (no disk persistence yet).
- Host AI bridge over serial — **no in-OS networking, no TLS.**
- App DSL limited to a **calculator-class app**: declarative UI widgets + a
  restricted expression evaluator. No loops, no arbitrary memory, no raw syscalls.
- Validator enforcing the schema + a fixed resource budget.

**Explicitly deferred:** preemption, disk FS, real network stack, WASM, multiple
permission tiers, "debug this crash," local model.

**Definition of done:** typing `create a calculator app` in the shell results in
a sandboxed calculator running, and feeding the model deliberate garbage results
in a clean rejection with the kernel still alive.

---

## 5. AI app format (the App DSL)

A declarative JSON document. **No imperative code from the model.** Behavior is
expressed as a constrained widget tree + an expression grammar the runtime
interprets. This is the security keystone: the grammar is small enough to fully
validate.

```jsonc
{
  "aios_app": "1",                 // schema version (string, exact match)
  "id": "calculator",              // [a-z0-9-]{1,32}, unique
  "title": "Calculator",
  "permissions": {                 // default-deny; absent = false
    "fs_read":  false,
    "fs_write": false,             // notes app would request true (scoped to its dir)
    "network":  false,
    "spawn":    false
  },
  "limits": {                      // validator clamps to system maxima
    "max_widgets": 32,
    "max_mem_kb":  64,
    "max_steps":   100000          // interpreter instruction budget
  },
  "state": { "acc": 0, "input": "" },   // typed initial state, scalars/strings only
  "ui": [                          // widget tree, fixed widget vocabulary
    { "type": "label",  "id": "display", "bind": "input" },
    { "type": "grid", "cols": 4, "children": [
      { "type": "button", "label": "7", "on_click": "press('7')" },
      { "type": "button", "label": "+", "on_click": "press('+')" },
      { "type": "button", "label": "=", "on_click": "evaluate()" }
      /* ... */
    ]}
  ],
  "actions": {                     // named handlers, body = restricted expr only
    "press":    "input = input + arg",
    "evaluate": "acc = calc(input); input = to_str(acc)"
  }
}
```

**Restricted expression grammar** (what `actions` bodies may contain):
- assignment to declared `state` keys only
- arithmetic `+ - * /`, comparison, string concat
- a fixed builtin allowlist: `calc()` (safe arithmetic parser), `to_str()`,
  `len()`, plus permission-gated `fs_get()/fs_put()` for storage apps
- **no** loops, no recursion, no function defs, no raw memory, no syscall names,
  no imports. Bounded by `max_steps` at runtime regardless.

Format alternatives considered: WASM (too heavy for v1), raw bytecode (harder to
validate by eye), full scripting language (unbounded → unsafe). JSON + tiny
expr DSL is the sweet spot for a hobby prototype.

---

## 6. Example: AI-generated calculator app

```json
{
  "aios_app": "1",
  "id": "calculator",
  "title": "Calculator",
  "permissions": { "fs_read": false, "fs_write": false, "network": false, "spawn": false },
  "limits": { "max_widgets": 32, "max_mem_kb": 32, "max_steps": 50000 },
  "state": { "input": "", "result": "0" },
  "ui": [
    { "type": "label", "id": "screen", "bind": "input" },
    { "type": "label", "id": "out",    "bind": "result" },
    { "type": "grid", "cols": 4, "children": [
      { "type": "button", "label": "7", "on_click": "push('7')" },
      { "type": "button", "label": "8", "on_click": "push('8')" },
      { "type": "button", "label": "9", "on_click": "push('9')" },
      { "type": "button", "label": "/", "on_click": "push('/')" },
      { "type": "button", "label": "4", "on_click": "push('4')" },
      { "type": "button", "label": "5", "on_click": "push('5')" },
      { "type": "button", "label": "6", "on_click": "push('6')" },
      { "type": "button", "label": "*", "on_click": "push('*')" },
      { "type": "button", "label": "C", "on_click": "clear()" },
      { "type": "button", "label": "=", "on_click": "eq()" }
    ]}
  ],
  "actions": {
    "push":  "input = input + arg",
    "clear": "input = ''; result = '0'",
    "eq":    "result = to_str(calc(input))"
  }
}
```

The runtime renders the widget tree, and on each button click runs the
associated action through the bounded expression interpreter. `calc()` is a
kernel-/runtime-provided safe arithmetic evaluator, never `eval`.

---

## 7. Example validator rules

The validator is pure and deterministic. It runs **before** the runtime ever
sees a def. Order = cheapest/most-fatal first.

```
R1  Parse: must be valid JSON < 64 KB. (else REJECT: malformed)
R2  Top-level "aios_app" == "1". (else REJECT: bad version)
R3  "id" matches ^[a-z0-9-]{1,32}$. (else REJECT)
R4  Only known top-level keys present. Unknown key → REJECT (no silent ignore).
R5  permissions: only known booleans; any true value must be in the set the
    shell/user authorized for this request. Unrequested escalation → REJECT.
R6  limits: each ≤ system max (max_widgets≤128, max_mem_kb≤256, max_steps≤1e6).
    Over → CLAMP to max (warn), not reject.
R7  ui: every node "type" in widget vocabulary {label,button,grid,input,list}.
    Unknown type → REJECT. Tree depth ≤ 8, total nodes ≤ max_widgets.
R8  Every "bind"/state reference names a key declared in "state". Dangling → REJECT.
R9  actions + on_click bodies: tokenize against the expr grammar. Any token
    that is not {declared state key, allowlisted builtin, literal, operator,
    'arg'} → REJECT. No identifier may match a syscall name or 'eval'.
R10 fs_*/network builtins used in actions but permission false → REJECT.
R11 Size after normalization still < limits → else REJECT.

On any REJECT: return structured error to ai-daemon. Nothing is executed.
```

The validator is the **trust boundary in user space**; the kernel sandbox (§10)
is the trust boundary that assumes the validator might *also* be wrong.

---

## 8. Syscall / API surface for sandboxed apps

Two tiers. Apps **cannot** call kernel syscalls directly — they call runtime
intrinsics, and the runtime makes the (allowlisted) syscalls on their behalf.

**Kernel syscalls (`int 0x80`, eax = number):**

| # | Name | Args | Notes |
| - | ---- | ---- | ----- |
| 0 | `sys_exit` | code | always allowed |
| 1 | `sys_write` | fd, buf, len | fd restricted to app's own console handle |
| 2 | `sys_read` | fd, buf, len | input events only |
| 3 | `sys_yield` | — | cooperative |
| 4 | `sys_open` | path, mode | **kernel rewrites path into `/apps/<id>/` jail** |
| 5 | `sys_close` | fd | |
| 6 | `sys_ipc_send` | port, msg, len | only to ports app is granted |
| 7 | `sys_ipc_recv` | port, buf, len | |
| 8 | `sys_getpid` | — | |

Permission-gated (kernel checks the calling task's permission descriptor; denied
→ `-EPERM`, never a fault): `sys_open` write mode (needs `fs_write`),
networking syscalls (needs `network`, deferred), `sys_spawn` (needs `spawn`).

**Runtime intrinsics available inside the DSL** (these compile down to the above
or to pure computation): `push/clear/eq`-style state ops, `calc`, `to_str`,
`len`, and — only if permitted — `fs_get(key)`, `fs_put(key, val)`. The DSL has
**no** way to name a raw syscall number.

---

## 9. How `ai-daemon` communicates

```
shell  ──IPC port "ai.req"──▶  ai-daemon
       ◀─IPC port "ai.resp"──

ai-daemon ──VFS syscalls──▶  /apps/*           (read/write app defs)
ai-daemon ──app-builder──▶  validator ──▶ runtime (spawn validated app)
ai-daemon ──bridge syscall──▶ kernel bridge dev ──serial──▶ host ai-bridge ──HTTPS──▶ Cloud AI
```

- **with shell:** kernel-mediated IPC ports. shell sends
  `{intent, text, context_app_id?}`; daemon replies `{status, app_id|error}`.
- **with filesystem:** ordinary VFS syscalls, jailed to `/apps`. Stores both the
  app def and conversation/context for "modify" requests.
- **with app runtime:** after validation, daemon asks runtime to instantiate the
  def in a new sandbox; gets back a task id.
- **with network / AI SDK:** through the `ai_backend` interface. v1
  implementation = **bridge transport**: daemon serializes a request frame
  (`{model, system, messages, max_tokens}`), writes it to the bridge device; the
  **host** `ai-bridge` process holds the API key, performs the TLS HTTPS call to
  the cloud API, streams the response back as frames. The kernel never sees the
  API key and never does TLS. A future v2 swaps this implementation for an
  in-OS network stack behind the *same* `ai_backend` interface.

**Bridge frame format (host ↔ OS, over chardev):**
```
MAGIC(4) | type(1) | seq(2) | len(4) | payload(len) | crc32(4)
type: 0=req 1=resp 2=err 3=stream-chunk 4=stream-end
```
Length-prefixed + CRC so a noisy/garbage frame is detectable and dropped, never
parsed blindly.

---

## 10. Security & safety model

Defense in depth — three independent layers, each assuming the one above failed:

1. **Generation layer (ai-daemon):** constrained prompt + the model can only
   ever emit the DSL. Output treated as hostile text.
2. **Validation layer (validator, §7):** deterministic gate. Default-deny
   permissions, closed widget/expr vocabulary, size/limit clamps. Pure function,
   itself unit-/fuzz-tested.
3. **Runtime + kernel sandbox (assumes 1&2 can be buggy):**
   - **Address-space isolation:** each app gets its own page directory; cannot
     read/write kernel or other apps' memory (page fault → only that app dies).
   - **Permission descriptor** per task; kernel checks on every gated syscall.
   - **Resource quotas:** instruction budget (`max_steps`), heap cap
     (`max_mem_kb`), wall-clock/yield budget. Exceed → app killed, resources
     reclaimed.
   - **Path jail:** `sys_open` rewrites all paths under `/apps/<id>/`. No `..`
     escape (kernel canonicalizes).
   - **No code injection path:** apps are data; there is no syscall to map
     executable memory or run native code from user space.
   - **API key isolation:** key lives only in the host bridge process, never in
     the OS image or on the guest disk.

**Threat → mitigation quick table:**

| Threat | Mitigation |
| ------ | ---------- |
| Model emits kernel/native code | Impossible to express in DSL; validator rejects unknown tokens |
| App reads another app's data | Separate page dir + path jail |
| App exhausts memory/CPU | Quotas + instruction budget; kernel kills |
| Privilege escalation via syscall | Permission descriptor, default-deny, `-EPERM` not fault |
| Malformed AI/bridge data | Length+CRC framing; validator size/parse checks |
| Leaked API key | Key only on host bridge |

---

## 11. Failure handling for hallucinated / invalid output

Every failure is **recoverable and surfaced**, never a kernel event:

| Failure | Detection | Response |
| ------- | --------- | -------- |
| Non-JSON / truncated model output | parser (R1) | ai-daemon retries once with a "return only valid JSON" reprompt; second failure → user-facing "couldn't build that, try rephrasing." |
| Schema/grammar violation | validator R2–R11 | reject with structured reason; optionally feed the reason back to the model for one repair attempt. |
| Over-limit resources | R6 | clamp + warn; app still runs. |
| Permission escalation | R5/R10 | reject; tell user the app "asked for X which wasn't allowed." |
| App faults at runtime (bad logic) | kernel page fault / instruction budget | kill *that app only*, capture fault context (eip, fault addr, last action). |
| "Debug this app crash" | uses captured fault context | ai-daemon sends crash context + app def to model, gets a patched def, re-validates, re-runs. |
| Bridge/host unavailable | timeout on bridge frame | ai-daemon returns "AI backend offline"; shell still works for builtins. |

Retry policy is **bounded** (max 1–2 model repair attempts) to avoid loops and
runaway cloud cost.

---

## 12. Suggested file/directory structure

Additive to today's layout (existing kernel files unchanged in spirit):

```
AIOS/
├── bootloader.s            # existing, no GRUB
├── loader.s  kernelmain.c  # existing
├── link.ld  Makefile  Dockerfile
├── include/                # existing kernel headers + new:
│   ├── syscall.h           # syscall numbers + ABI
│   ├── ipc.h               # port API
│   ├── vfs.h               # filesystem API
│   ├── sandbox.h           # permission descriptor, quotas
│   └── bridge.h            # AI bridge frame format
├── lib/                    # existing kernel impls + new:
│   ├── syscall.c  task.c  sched.c  ipc.c  vfs.c  sandbox.c  bridge.c
├── user/                   # NEW — ring-3 components (built as flat binaries)
│   ├── crt0.s              # user entry, syscall stubs
│   ├── shell/              # NL + builtin shell
│   ├── ai-daemon/          # ai_backend iface, prompt build, bridge client
│   │   ├── builder.c       # app-builder
│   │   └── validator.c     # validator (pure)
│   └── runtime/            # DSL interpreter + widget renderer
├── apps/                   # app defs at runtime (in VFS), seeded examples:
│   └── calculator.json
├── host/                   # NEW — runs on macOS, NOT in the image
│   └── ai-bridge/          # holds API key, does TLS to cloud (python or node)
├── docs/
│   ├── DESIGN.md           # this file
│   └── app-dsl.md          # DSL spec + schema
├── STATUS.md  README.md  PROMPT.md
```

---

## 13. Build / run commands (QEMU)

Existing flow is preserved; bridge adds one QEMU chardev wired to the host
bridge process.

```bash
# build (Docker cross-toolchain, unchanged)
make docker-image
make docker-build              # produces AIOS.img

# run plain kernel (today's behavior)
make docker-run

# run WITH AI bridge: start host bridge, then QEMU with a second serial
# wired to it (pty or unix socket chardev).
export AIOS_AI_API_KEY=sk-...                # key stays on host only
python host/ai-bridge/bridge.py --socket /tmp/aios-ai.sock &

qemu-system-i386 \
  -drive format=raw,file=AIOS.img \
  -chardev stdio,id=ch0,logfile=aios.log,signal=off -serial chardev:ch0 \
  -chardev socket,id=ai,path=/tmp/aios-ai.sock -serial chardev:ai
# COM1 = console/log (existing), COM2 = AI bridge (new)
```

A `make docker-run-ai` target will wrap the bridge + QEMU invocation.

---

## 14. What NOT to do

- **Do not** let the model emit C, asm, machine code, bytecode the kernel runs,
  or raw syscall sequences. Apps are *declarative data only.*
- **Do not** link any AI SDK / HTTP / JSON-of-untrusted-size parsing into ring 0.
- **Do not** `eval` model expressions. Use the bounded `calc()` parser.
- **Do not** give a generated app blanket filesystem/network access. Default-deny;
  jail every path; gate every capability.
- **Do not** put the API key in the OS image or on the guest disk. Host bridge only.
- **Do not** trust bridge/model bytes: always length+CRC framed, size-capped,
  schema-validated before use.
- **Do not** retry the model unboundedly (cost + loop risk). Cap repair attempts.
- **Do not** skip the kernel sandbox because "the validator already checked it."
  Assume each layer is fallible.
- **Do not** block the whole OS on a cloud call — bridge I/O is async; shell
  builtins must work offline.

---

## 15. Future upgrade path to local / offline AI

The `ai_backend` interface is the seam. Swap implementations without touching
shell/validator/runtime/kernel:

1. **v1 — host cloud bridge** (this design): TLS on host, key on host.
2. **v2 — host local model bridge:** same bridge protocol, but the host process
   runs a local model (e.g. a quantized GGUF via llama.cpp) instead of calling
   the cloud. Zero OS-side change. This is the cheapest path to "offline."
3. **v3 — in-OS network stack:** implement a real NIC driver (virtio-net) +
   minimal TCP/IP, do the API call from inside AIOS. The `ai_backend` interface
   stays; only its transport changes from bridge to socket.
4. **v4 — in-OS local inference (research):** a tiny quantized model running in
   a user-space inference service inside AIOS. Requires SSE/FP support, much
   more RAM, and likely 64-bit — a long-horizon goal, explicitly out of scope
   for the hobby prototype but unblocked by keeping the backend behind one iface.

---

## Open questions for review

1. **Bridge transport:** COM2 serial (simplest) vs virtio-serial (cleaner, needs
   a driver). Recommendation: start with COM2.
2. **Scheduler:** stay cooperative through A8, or bring preemption forward? (It
   makes sandbox CPU-quota enforcement stronger but is more work.)
3. **DSL scope for v1:** calculator-class only, or include `input`/`list`
   widgets so the notes app is reachable in the first prototype?
4. **Persistence:** RAM-only FS for prototype (lose apps on reboot) vs writing a
   simple block driver to persist `/apps` to the disk image.
5. **Language:** stay pure C for userland too, or introduce a constrained C++/
   Rust for the runtime/validator where memory safety matters most?
```