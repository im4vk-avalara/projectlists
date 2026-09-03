# AIOS — project status

Snapshot of what's built and what's next. Update as you go.

## Where things stand

32-bit x86 kernel that boots from a custom boot sector (no GRUB), runs in QEMU,
and has reached the point of having a real memory allocator. The kernel is
interactive via PS/2 keyboard.

**Last working build:** E820 memory map (real RAM detection) on top of the
complete S1–S11 stack. **The S1–S6 v1 prototype is complete** — natural
language → AI emits app-DSL → validated → interpreted in a sandbox → running
app — plus S7–S10 (VFS, fault responder, self-heal, TUI windows) and S11
(host-side long-term semantic memory via TurboVec). See `DESIGN.md` for the
roadmap.

## How to build and run

Toolchain runs in Docker (cross-compiler image), QEMU runs on macOS host. See
`README.md` for full details.

```bash
make docker-image            # one-time: build the cross-toolchain image
make docker-run              # text-mode kernel: build in Docker, run in host QEMU
make docker-run-demo         # DEMO build: VGA mode 13h + plasma animation
make run                     # re-run the last-built image (no rebuild)
```

To run with the AI bridge (the `aios>` console reaches the AI), start the host
adapter first, then launch QEMU with COM2 wired to it:

```bash
# terminal 1 — host bridge (Apple MLX, 4-bit on the GPU, no key; see host/ai-bridge/README.md)
#   one-time: python3.12 -m venv .venv && .venv/bin/pip install mlx-lm turbovec sentence-transformers
.venv/bin/python host/ai-bridge/bridge.py            # MLX Qwen2.5-14B-Instruct-4bit

# terminal 2 — build + run with COM2 → bridge socket
make docker-run-ai           # (or: make run-ai, to reuse the last build)
```

Everything is local: no API key, no cloud, no TLS. See `host/ai-bridge/README.md`
(includes the corporate-proxy CA fix for Ollama). Serial output is captured to
`build/aios.log`.

## Project layout

```
src/boot/      bootloader.s, loader.s, link.ld
src/kernel/    kernelmain.c
src/lib/       kernel library (drivers, mm, gdt/usermode/syscall, bridge/intent/control/appvm)
src/include/   headers
host/ai-bridge/ host AI bridge (bridge.py) — not part of the image
docs/          STATUS.md (this file), DESIGN.md, PROMPT.md, archive/
build/         all generated files (git-ignored; `make clean` removes it)
```

## Current capabilities

### Text-mode kernel (`make docker-run`)

Boot output exercises every library (kprintf %s/%c/%d/%u/%x/%X/%p/%%, memset,
strlen). After init, the kernel **drops to ring 3** and runs a user-mode demo
(`lib/usertest.c`): it prints via `int 0x80` syscalls, gets `-1` from a bogus
syscall (survives), then executes a privileged `hlt` → `#GP` which the kernel
**contains** (terminates the task, keeps running). Control then returns to ring
0 and the **AI console** (`aios>` prompt, line editor with backspace/echo):

- A line **not** starting with `/` is sent to the AI (`ai_send`) over the COM2
  **bridge** to the host adapter, which forwards it to a local model and returns
  the reply (blocks up to ~180 s for slow CPU inference, then reports an error if
  no host bridge is running).
  If the reply is a JSON **intent** (control surface, S4), the kernel validates
  it and executes the read-only verb instead of printing text:

| Verb | Kind | Result |
| ---- | ---- | ------ |
| `uptime` | read | ms + ticks since boot |
| `meminfo` | read | heap + frame usage |
| `ps` | read | task list (cooperative kernel tasks: id, name, state) |
| `peek` | read | read u32 at `args.addr` (validated to the safe <4 MB identity map) |
| `calc` | read | evaluate `args.expr` (`+ - * /`, parens) in the kernel — exact arithmetic, not the LLM guessing |
| `apps` | read | list saved apps (the app library in the RAM VFS) |
| `open` | read | relaunch a saved app by `args.id` — no model call |
| `fix` | read | self-heal: load the app's saved DSL, ask the AI to patch it for `args.problem`, validate, hot-reload |
| `map` / `unmap` | mutate | map/unmap the test page |
| `alloc` / `free` | mutate | `kmalloc(256)` / `kfree` most-recent slot |
| `frame` / `unframe` | mutate | `frame_alloc` / `frame_free` most-recent |
| `kill` | mutate | mark a ready background task `args.id` dead (never task 0) |

  Read verbs are always allowed. **Mutating verbs require `kernel_ctl`**, which
  the *user* grants at the console with `/grant` (the AI can't self-grant) and
  revokes with `/revoke`; every executed mutating intent is **audit-logged**
  (`/audit` lists them). Unknown verbs, out-of-range addresses, bad schema
  versions, and ungranted mutations are **rejected** — the kernel never acts on
  free-form model output.

**AI first responder (S8):** when a **ring-3 task faults**, the kernel contains
it (as before) but also records the context (exception, `eip`, `cr2`) and, at the
next console prompt, **the AI automatically explains the crash** in plain language
— *unprompted*. Event-driven: the OS reacts to its own events, not a chat turn.
(Try it: `/ring3` re-runs the faulting demo → the AI responds.) **Kernel-mode
faults** (panics) now also get a **best-effort AI diagnosis**: the register dump
prints, then the AI explains the panic in plain language, then the kernel halts
(guarded against recursion; needs the bridge — otherwise it waits out the
timeout before halting).

Intents may carry a **`say`** field — a one-sentence conversational reply the
model includes in the same response; the kernel prints it before executing, so
the OS *talks* (`[ai] Sure, checking your free memory now.`) and then shows the
real result. (Intent-level narration, zero extra latency.)

The bridge keeps **conversation history per QEMU session** (multi-turn memory),
so follow-ups work: *"create a calculator app"* then *"add a key 'a' that clears
the input"* re-generates the app **with** the new key. History resets when QEMU
reconnects.

**Long-term memory (S11, host-side):** the bridge also keeps a **persistent
semantic memory** (`host/ai-bridge/memory.py`) — each exchange is embedded
locally (sentence-transformers MiniLM) and indexed with **TurboVec** (Rust
vector index, TurboQuant 4-bit). Relevant past records are recalled into the
system prompt on every turn, so memory **survives QEMU restarts and bridge
restarts**: *"open the app I made for writing things down"* finds the notes app
from a previous session. Persists in `host/ai-bridge/.memory/`; `--no-memory`
disables; still fully offline. No kernel/image change.

If the reply is an app definition (contains `aios_app`, S6), the kernel runs it
as a sandboxed **interpreted app**: a request like *"create a calculator app"*
yields an app-DSL, which is **validated** (closed expression grammar, declared
state vars, default-deny permissions, `max_steps` budget — no loops/memory/
syscalls expressible) then **interpreted** as a key-driven widget. The
calculator runs as a **TUI window** (S10): a bordered, colored window (title bar,
state fields, a highlighted key row, `Enter = exit`) drawn over the console via
positioned VGA writes; the window is wiped and the console restored on exit.
Digit/operator keys build `input`, `=` runs `calc(input)`, `c` clears. Malicious or malformed app bodies are
**rejected** by the validator (e.g. `system(...)` → "illegal token").

**Persistence (S7):** a RAM VFS (`lib/vfs.c`) gives durable-within-a-session
storage. Generated apps are **auto-saved** to `/apps/<id>.json`, so the `apps`
verb lists them and `open` relaunches one **without the model**. Apps that
request `fs_read`/`fs_write` permission get **`fs_get(key)` / `fs_put(key,val)`**
builtins, jailed to `/apps/<id>/data/<key>` — so a notes app can save and reload
its notes. `fs_*` used without the permission is rejected by the validator.
(RAM-only: lost on QEMU restart; disk-backed persistence is a later phase.)
- A line starting with `/` runs a **dev command** (scaffolding; these same
  kernel functions become validated AI control-surface verbs in S4/S5):

| Command | Action |
| ------- | ------ |
| `/help` | List dev commands |
| `/uptime` | Uptime (ms + ticks) from PIT |
| `/meminfo` | Heap + frame allocator stats |
| `/map` | `paging_map(0x80000000, &test_page, RW)` + write 0xDEADBEEF + read back |
| `/unmap` | `paging_unmap(0x80000000)` |
| `/peek` | Read `*(u32*)0x80000000` (page-faults if unmapped) |
| `/alloc` / `/free` | `kmalloc(256)` / `kfree` most-recent slot (max 8) |
| `/frame` / `/unframe` | `frame_alloc()` / `frame_free` most-recent (max 8) |
| `/spawn` | Spawn a background demo task (5 steps, ~0.5 s each, runs while the console idles) |
| `/ps` | List tasks (id, name, state) |
| `/grant` / `/revoke` | Grant / revoke `kernel_ctl` (lets the AI run mutating verbs) |
| `/audit` | List mutating actions the AI has performed this session |
| `/ring3` | Re-run the ring-3 user demo |
| `/panic` | Trigger divide-by-zero → IDT panic with register dump |

Dev commands are **direct user action and are not gated** — the console user
already has full authority. Only the AI's intent path is gated by `kernel_ctl`.

### Graphics demo (`make docker-run-demo`)

Bootloader switches to VGA mode 13h (320×200×256) via BIOS `int 0x10`.
Kernel fills with white (sanity check), then runs palette-cycling plasma
forever.

## Architecture snapshot

```
bootloader.s         16-bit boot sector. BIOS int 0x13 LBA read → load kernel.
                     Enables A20, captures E820 memory map to 0x8000, loads
                     GDT, far-jumps to PM.
                     With DEMO=1: sets VGA mode 13h before PM jump.
loader.s             32-bit entry: set kernel stack, push args, call kernel_main.
kernelmain.c         Boot sequence + interactive key dispatch.

include/
  asm.h              inb/outb/hlt/cli/sti inline helpers
  types.h            u8/u16/u32, size_t, NULL
  io.h               Terminal + serial API
  string.h           memset, memcpy, memmove, memcmp, strlen, strcmp/ncmp, strcpy
  printf.h           kprintf, kvprintf, va_list (wraps GCC builtins)
  kbd.h              Keyboard API (IRQ-driven)
  idt.h              IDT entry/ptr/regs structs, idt_init, irq_install
  pic.h              8259 PIC remap, mask/unmask, EOI
  pit.h              8253 PIT init, msleep, uptime
  paging.h           paging_init, paging_map/unmap, read_cr2
  e820.h             BIOS E820 map access (count/entries/usable_top/print)
  frame.h            frame_alloc/free, total/used/base
  kmalloc.h          kmalloc/kfree, total/used
  task.h             Cooperative tasks: create/yield/exit/kill/ps
  fb.h               Framebuffer (mode 13h) primitives [DEMO only]
  anim.h             Plasma animation [DEMO only]

lib/
  io.c               VGA text driver @ 0xB8000 (80×25 w/ scroll + HW cursor),
                     8250 UART @ COM1, output mirrored.
  string.c           libk helpers
  printf.c           kprintf/kvprintf implementation
  kbd.c              IRQ-driven keyboard with 64-byte scancode ring buffer
  idt.c              IDT setup, exception dispatch + IRQ dispatch w/ EOI
  isr.s              32 CPU exception stubs + 16 IRQ stubs, common epilogue
  pic.c              8259 ICW1-4 sequence, vector base 0x20
  pit.c              100 Hz tick, msleep (hlt-based), timer IRQ on IRQ0
  paging.c           Identity-map first 4 MB. paging_map/unmap w/ invlpg.
                     New page tables come from frame_alloc (identity-mapped
                     <4 MB frames only, so up to 768 PTs).
  e820.c             Parse the E820 map the bootloader stashed at 0x8000
  frame.c            Bitmap frame allocator over [1 MB, E820 usable top),
                     capacity 128 MB (32768 frames)
  kmalloc.c          256 KB BSS heap, first-fit free list, forward coalesce
  task.c             Cooperative task table (8 slots, kmalloc'd 8 KB stacks),
                     round-robin task_yield, dead-slot reuse
  taskswitch.s       ctx_switch: save/restore callee-saved regs + ESP swap
  fb.c               [DEMO] 320×200×8 fb at 0xA0000, palette via DAC ports
  anim.c             [DEMO] Sine LUT + plasma + palette cycling

link.ld              Kernel at 0x10000, 4 KB section alignment, exposes _end
Makefile             Native + Docker build paths, DEMO=1 flag
Dockerfile           Debian + gcc-i686-linux-gnu + binutils-i686-linux-gnu
```

## Phase history

| Phase | What it added | Files touched |
| ----- | ------------- | ------------- |
| 0 | Initial scaffold: boot sector, PM jump, VGA text print | `bootloader.s` `loader.s` `kernelmain.c` `lib/io.c` |
| Build | Docker cross-toolchain, mirrored Make targets | `Dockerfile` `Makefile` |
| 1 | Hardware cursor + scrolling (CRTC ports 0x3D4/0x3D5) | `lib/io.c` |
| 2 | libk (mem/str) + kprintf with %s/%d/%u/%x/%p/%% | `lib/string.c` `lib/printf.c` |
| 3+4 | VGA mode 13h framebuffer + plasma palette cycle (DEMO build) | `bootloader.s` `lib/fb.c` `lib/anim.c` |
| 5 | Polled PS/2 keyboard echo loop (interim) | `lib/kbd.c` |
| 6 | IDT + 32 exception stubs, panic w/ register dump | `lib/isr.s` `lib/idt.c` |
| 7 | 8259 PIC remap, IRQ stubs, PIT @ 100 Hz, IRQ-driven keyboard | `lib/pic.c` `lib/pit.c` `lib/idt.c` `lib/kbd.c` `lib/isr.s` |
| 8 | Paging: identity-map first 4 MB, CR2 in page-fault panic | `lib/paging.c` `lib/idt.c` |
| 9 | Dynamic `paging_map`/`paging_unmap` + invlpg; roundtrip demo | `lib/paging.c` `kernelmain.c` |
| 10 | Bitmap frame allocator + 256 KB heap (`kmalloc`/`kfree`) | `lib/frame.c` `lib/kmalloc.c` `link.ld` |
| A1 (S1) | Ring 3 + syscalls: C-built GDT w/ user segs + TSS, `int 0x80` gate (DPL3) reusing `isr_common`, syscall dispatch (`write`/`exit`/`getpid`/`yield`), ring-3 entry/teardown, user-fault containment | `lib/gdt.c` `lib/usermode.s` `lib/syscall.c` `lib/usertest.c` `lib/idt.c` `lib/isr.s` `lib/paging.c` `kernelmain.c` |
| A2 (S2) | AI console: line editor (`read_line`, backspace/echo) replaces single-key dispatch; plain lines → `ai_send` stub, `/`-prefixed → `dev_command` table (old demo keys re-homed as `/uptime`,`/meminfo`,`/map`,…) | `kernelmain.c` |
| A3 (S3) | AI bridge: polled COM2 (0x2F8) UART + framed protocol (`AIOS\|type\|seq\|len\|payload\|crc32`, payload CRC-32, ~3s timeout); `bridge_request` round-trips a prompt; `ai_send` wired to it. Host adapter `host/ai-bridge/bridge.py` (pluggable: canned default / ollama / llamacpp). `make run-ai` / `docker-run-ai` wire COM2 to the bridge socket | `lib/bridge.c` `include/bridge.h` `kernelmain.c` `Makefile` `host/ai-bridge/bridge.py` |
| A4 (S4) | AI control surface (read-only): intent JSON parser + validator + enumerable verb table (`uptime`/`meminfo`/`ps`/`peek`); `ai_send` routes model replies that look like intents → validate → execute → real result; rejects unknown verbs / out-of-range peek / bad version. Host `--backend mock` emits intents for testing | `lib/intent.c` `include/intent.h` `kernelmain.c` `host/ai-bridge/bridge.py` |
| A5 (S5) | AI control surface (mutating): centralized executors + `kernel_ctl` permission gate + audit ring in new `control.c` (both dev commands and AI intents call it); verbs `map`/`unmap`/`alloc`/`free`/`frame`/`unframe`/`kill` require user-granted `kernel_ctl` (AI can't self-grant), each audit-logged; `/grant`,`/revoke`,`/audit` console commands. Mock backend emits mutating intents | `lib/control.c` `include/control.h` `lib/intent.c` `kernelmain.c` `host/ai-bridge/bridge.py` |
| A6 (S6) | AI app generation: keymap-based app-DSL + validator (closed expression grammar, declared-var check, default-deny perms, `max_steps`) + bounded interpreter (string concat, `calc`/`to_str`/`len`, key-driven widgets) in new `appvm.c`; `ai_send` routes `aios_app` replies → validate → run sandboxed; rejects illegal tokens. **Completes the S1–S6 prototype** | `lib/appvm.c` `include/app.h` `kernelmain.c` `host/ai-bridge/bridge.py` |
| S10 | TUI windows for apps: positioned/colored VGA drawing helpers (`terminal_put_at`/`str_at`/`fill`/`box`, CP437 borders) in `io.c`; `app_render` rewritten to draw a bordered, colored window (title bar, state fields, key row); `app_run` clears on exit. No DSL/model change. `app_state_summary` added for tests | `lib/io.c` `include/io.h` `lib/appvm.c` `include/app.h` |
| S9 | Self-healing software: `fix` verb (`args.id`+`problem`) loads the app's saved DSL from VFS, asks the AI to patch it (real def + problem in the prompt, 2nd round-trip), validates the patch, and hot-reloads on success (rejects invalid/malicious patches). The OS repairs its own programs | `lib/intent.c` `kernelmain.c` `host/ai-bridge/bridge.py` |
| S8 | AI first responder to faults (event-driven): `idt.c` records contained ring-3 fault context (`fault_take`); console loop auto-invokes `ai_fault_report` → AI explains the crash unprompted. Added `ksnprintf` (printf-to-buffer) in `printf.c`. Intent `say` field (conversational narration). Kernel panics unchanged | `lib/idt.c` `include/idt.h` `lib/printf.c` `include/printf.h` `lib/intent.c` `kernelmain.c` `host/ai-bridge/bridge.py` |
| Coop-MT | Cooperative multitasking: task table (8 slots, 8 KB kmalloc'd stacks, dead-slot reuse) + asm `ctx_switch` (callee-saved regs + ESP swap); `task_create` prebuilds the stack so the first switch enters the task and a return lands in `task_exit`; round-robin `task_yield`; `kbd_read_scancode` yields while waiting so background tasks run when the console idles (hlt parks empty rotations); `ps`/`kill` verbs now real; `/spawn`+`/ps` dev commands demo interleaving | `lib/task.c` `include/task.h` `lib/taskswitch.s` `lib/kbd.c` `lib/control.c` `kernelmain.c` `Makefile` |
| PT-alloc | Page tables from the frame allocator: `paging_map` allocates new PTs via `frame_alloc` instead of the static 16-entry pool (64 KB BSS freed); PTs must be identity-map reachable (<4 MB), giving up to 768. Requires `frame_init` before the first dynamic map (boot order guarantees it) | `lib/paging.c` |
| E820 | BIOS E820 memory map: bootloader captures the map in real mode (int 0x15/EAX=E820 → 0x8000); kernel parses + prints it at boot and sizes the frame allocator from real RAM (127 MB usable in QEMU vs the old hardcoded 4 MB). Also fixes the allocator handing out the 0xA0000-0xFFFFF VGA/ROM hole: frames now start at 1 MB | `bootloader.s` `lib/e820.c` `include/e820.h` `lib/frame.c` `include/frame.h` `kernelmain.c` `Makefile` |
| S7 | Persistence (RAM VFS): `lib/vfs.c` path→blob store (bounded); auto-save generated apps to `/apps/<id>.json`; `apps`/`open` verbs (app library, relaunch without model); `fs_get`/`fs_put` DSL builtins gated by `fs_read`/`fs_write` permission, jailed to `/apps/<id>/data/` → notes app that saves. Multi-turn memory (bridge keeps per-session history) enables "modify the app" | `lib/vfs.c` `include/vfs.h` `lib/appvm.c` `lib/intent.c` `kernelmain.c` `host/ai-bridge/bridge.py` |
| S11 | Long-term semantic memory (host-side only): TurboVec (TurboQuant 4-bit vector index) + local MiniLM embeddings; every exchange stored as a compact record (apps/intents summarized, S8 fault prompts excluded), top-3 relevant records (score ≥ 0.30) injected into the system prompt per turn; persists in `host/ai-bridge/.memory/` across QEMU + bridge restarts; `--no-memory` flag. Fully offline; zero kernel change | `host/ai-bridge/memory.py` `host/ai-bridge/bridge.py` |

## Roadmap

In rough order of natural progression. Pick any; some are independent.

1. **Higher-half kernel** — relink at `0xC0000000`, map kernel virtual addresses
   to low physical. Frees the low 768 MB of virtual space for userland.
2. **Preemptive multitasking** — timer IRQ calls a scheduler that picks the next
   task. Per-task page directory (swap CR3 on context switch).
3. **In-kernel scrollback** — ring buffer of N lines, PgUp/PgDn cycles through
   history. Resolves the "QEMU window has no scrollback" complaint.
4. **Mini-shell** — line buffer + command parser + dispatch table. Exposes
   `sleep`, `uptime`, `clear`, `panic`, `meminfo` etc. as typed commands.
5. **Bitmap font + text on framebuffer** (DEMO) — render a console in mode 13h
   so DEMO builds get text output too.
6. **Userland + syscalls** — set up ring 3, IDT gate for `int 0x80`, a tiny
   syscall table (write, exit, getpid).

## Known limitations / shortcuts

- **BSS not zeroed** — relying on QEMU initializing RAM to zero on cold boot.
  Real hardware would need a zeroing loop in `loader.s`.
- **Frame allocator capacity is 128 MB** — `MAX_FRAMES` caps the bitmap; RAM
  beyond that (per E820) is detected but not managed.
- **Page tables must sit below 4 MB** — they are written through the identity
  map, so `paging_map` only accepts PT frames under 4 MB (up to 768 PTs; a
  recursive page-directory mapping would lift this).
- **kmalloc** does forward-merge coalescing only, no full pass; fragmentation
  grows over long-running workloads.
- **Identity map = 4 MB** — anything above that needs explicit `paging_map`.
- **No FPU init** — kernel doesn't use FP, so `CR0.EM` defaults are fine for
  now. Would matter for SSE.
- **Single CPU** — no SMP, no APIC; using the legacy 8259 PIC and 8253 PIT.
- **Ring 3 has no memory isolation yet (S1 shortcut)** — `paging_enable_user_lowmem`
  marks the whole identity-mapped low 4 MB user-accessible so the in-image ring-3
  demo can run in place. A user task can therefore still reach kernel memory.
  Real isolation is deferred: the final design uses interpreter-based sandboxing
  (apps are DSL data, not native ring-3 code) — see `DESIGN.md`.
- **Cooperative only, kernel tasks only** — tasks switch at explicit
  `task_yield` points (a spinning task starves the rest until preemption
  lands); the ring-3 user demo (`usermode_run`/`usermode_exit`) is still a
  one-shot enter/teardown, not a resident task.
- **No deadline for graphics + text mix** — switching from mode 13h back to
  text mode requires real-mode BIOS calls, deferred indefinitely.

## File counts (for sanity)

- Source files: ~22 (C + asm + headers)
- Kernel binary (text build): ~16 KB
- Runtime BSS: ~300 KB (page tables, PT pool, heap, stack, ring buffers)
- Total in image (text build): ~16 KB kernel + 512 B bootloader

## Resuming work

When you come back:

1. Read this file.
2. `make docker-run` to confirm the current build still boots and the prompt works.
3. Try the demo keys (`a`, `d`, `f`, `r`, `s`, `m`, `u`, `p`, `?`, `!`) to refresh memory of what's there.
4. Pick a phase from **Roadmap**, or revisit a **Known limitations** item.
