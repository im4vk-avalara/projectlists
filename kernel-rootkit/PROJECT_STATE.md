# shadowfox + lighthouse — project state

_Short, current-only status. Read this first when resuming a session._

## Current stage
**Stages 1, 1.5, 2, 3, 4 — COMPLETE.** Code, smoke-tested, writeups landed. Ready to start **Stage 5** (`/proc/net` filtering for network port hiding + `tcp_hashinfo` walker) on user's go-ahead.

## Last update
2026-05-18 — Stage 4 written and smoke-tested end-to-end on the lab VM. shadowfox extends the Stage 3 `__x64_sys_getdents64` hook with a parallel filename filter (`hide_files.{h,c}`); debugfs gets `hide-file <name>` / `show-file <name>` / `clear-hidden-files` commands; exact-match only, refuses `.` and `..`. lighthouse adds `detect_files.{h,c}` — an iterate_dir-backed audit tool exposed via a new debugfs file `audit-dir` (write a path, get the true listing in dmesg, manually diff against userspace `ls`). The Stage 3 ftrace-ops walker continues to catch the underlying hook on every scan. VM is currently running.

---

## Stage 1 — what landed

### shadowfox (offensive side)
- `modules/shadowfox/symbols.{h,c}` — kprobe-trick kallsyms resolver caching `modules` + `module_mutex`.
- `modules/shadowfox/hide_module.{h,c}` — `sf_hide()` / `sf_restore()`. Snapshots `list.prev` and `mkobj.kobj.parent` before mutating; `list_del_init` + `kobject_del`; reverse on restore. Idempotent, mutex-guarded.
- `modules/shadowfox/main.c` — init/exit, `hidden=0|1` module param (default 0), debugfs control at `/sys/kernel/debug/shadowfox/ctl` accepting `hide`/`unhide`/`restore`.
- `modules/shadowfox/Makefile` — dual-mode kbuild; `shadowfox-y := main.o symbols.o hide_module.o`; `ccflags-y += -Wextra`.

### lighthouse (detection side)
- `modules/lighthouse/symbols.{h,c}` — mirror of shadowfox's resolver, also resolves `mod_tree`.
- `modules/lighthouse/kernel_internal.h` — replicated `struct mod_tree_root` + `struct mod_tree_node` layouts from `kernel/module/internal.h`, 6.6-pinned with loud version-coupling warning. `#ifdef CONFIG_MODULES_TREE_LOOKUP` guards match the kernel's.
- `modules/lighthouse/detect.{h,c}` — three-set cross-view detector. visible_set walks `modules` list under `module_mutex`. addr_set scans `[MODULES_VADDR, MODULES_END)` via `__module_address()` with `preempt_disable` per call and `cond_resched` between iterations. tree_set walks `mod_tree.root.tree[0]` via `rb_first`/`rb_next` + `container_of` chain (conditional on `CONFIG_MODULES_TREE_LOOKUP`). Diff each candidate set against visible_set; emit `KERN_WARNING` per hidden module per method; flag detector disagreement.
- `modules/lighthouse/main.c` — init/exit, debugfs trigger at `/sys/kernel/debug/lighthouse/scan` (write triggers detection), one auto-pass on load.
- `modules/lighthouse/Makefile` — dual-mode kbuild; `lighthouse-y := main.o symbols.o detect.o`.

### Documentation
- `docs/techniques/01-module-list-concealment.md` — full 8-section writeup per PROMPT.md template. Covers both sides, version matrix, references, mitigations, lessons learned.

---

## Stage 1 fixes during smoke test

Two pre-tested assumptions turned out to be wrong on real 6.6.138 and were fixed inline:

1. **`__module_address` is NOT `EXPORT_SYMBOL_GPL` in 6.6.** The declaration in `<linux/module.h>` misled me; `modpost` flagged it as undefined at link time. Fix: resolve it through the kallsyms / kprobe-trick path like every other private symbol. Added `lh_module_address` function pointer in `lighthouse/symbols.{h,c}`; `detect.c` calls through that. Writeup section 8 ("Lessons learned") now leads with this.
2. **`kobject_del()` cannot be paired with a clean restore from out-of-tree code.** It recursively destroys child kobjects (`holders/`, `refcnt`, `sections/`, `parameters/`), and a bare `kobject_add` only resurrects the parent. Consequences observed in the VM: `libkmod` refused `rmmod`, and `delete_module(2)` emitted two `WARN_ON_ONCE` traces during `sysfs_remove_group`. Fix: dropped the `kobject_del`/`kobject_add` half of the hide/restore technique entirely. Stage 1 now hides only from the `modules` linked list (and therefore `lsmod` / `/proc/modules`), leaving `/sys/module/<name>` visible. Writeup section 3 has a new "Scope choice" subsection covering this; revisit in Stage 6 when we have the integrity-layer infrastructure.

Secondary cleanup applied at the same time:
- `kernel_internal.h`: trimmed `struct mod_tree_root` to just the `root` field (the only one we read). The kernel's struct has additional fields after `root`, but we never reference them, so post-`root` layout drift cannot affect us. Also removed the `struct mod_tree_node` replica because `<linux/module.h>` in 6.6 exposes it publicly.
- Both Makefiles: added `-Wno-unused-parameter` alongside `-Wextra` — the kernel build normally suppresses this, but our `-Wextra` was overriding it and flooding the output with warnings from kernel headers and from stock `file_operations` callback signatures.

## Stage 1 smoke-test result (recorded 2026-05-18)

End-to-end demo (list-only mode, default) passes against `6.6.138-0606138-generic`:

| Step | Expected | Observed |
|---|---|---|
| insmod shadowfox (default hidden=0, permanent_hide=0) | lsmod + /sys/module both visible | ✅ |
| `echo hide > /sys/kernel/debug/shadowfox/ctl` | lsmod hidden; /sys/module visible (list-only scope) | ✅ |
| `rmmod shadowfox` while hidden | fails with ENOENT | ✅ |
| insmod lighthouse; auto-pass | no hidden modules detected (shadowfox was visible) | ✅ |
| `echo 1 > /sys/kernel/debug/lighthouse/scan` while shadowfox hidden | both methods name shadowfox | ✅ |
| Detector disagreement | none | ✅ |
| `echo unhide > .../shadowfox/ctl` then rmmod both | clean unload, no WARN traces | ✅ |

Detection cycle measured at ~12 ms on the TCG-emulated VM.

## Stage 4 smoke-test result (recorded 2026-05-18)

End-to-end demo of filename concealment + audit tool on `6.6.138-0606138-generic`:

| Step | Expected | Observed |
|---|---|---|
| Build shadowfox + lighthouse with Stage 4 additions | clean | ✅ (no errors, no own-code warnings) |
| Drop `~/victim/secret.txt` + `~/victim/visible.txt` | both visible to `ls` | ✅ |
| Load shadowfox; load lighthouse; initial scan | shadowfox flagged by ftrace-ops walker | ✅ "ftrace hook by module shadowfox" |
| `echo hide-file secret.txt > ctl` | "hiding file name 'secret.txt'..." | ✅ |
| `ls ~/victim/` | only `visible.txt` | ✅ |
| `cat ~/victim/secret.txt` (direct access, Stage 4 scope) | "secret content" | ✅ |
| `echo /home/researcher/victim > /sys/kernel/debug/lighthouse/audit-dir` | dmesg lists all 4 entries via iterate_dir | ✅ ., .., visible.txt, secret.txt |
| Stage 3 ftrace-ops walker re-trigger via scan | flags shadowfox again | ✅ |
| `show-file secret.txt` + clean rmmod both | no WARN traces, hook removed | ✅ "ftrace hook removed from __x64_sys_getdents64" |

Educational moment captured in dmesg side-by-side: lighthouse audit returned 4 entries (., .., visible.txt, secret.txt); userspace `ls /home/researcher/victim` returned only `visible.txt`. The discrepancy is the hidden file. The ftrace-ops walker flags the hook independently — without enumerating the specific hidden filenames.

## Stage 3 smoke-test result (recorded 2026-05-18)

End-to-end demo of process concealment + dual detection on `6.6.138-0606138-generic`:

| Step | Expected | Observed |
|---|---|---|
| Build shadowfox after API fixes (`ftrace_regs_set_instruction_pointer` + types.h before dirent.h) | clean | ✅ after 2 inline fixes documented in writeup |
| Load shadowfox; ftrace hook installed | "ftrace hook installed on __x64_sys_getdents64" in dmesg | ✅ |
| `ls /proc/ \| grep <victim_pid>` before hide | victim present | ✅ |
| `echo hide-pid <pid> > ctl` | success | ✅ "hiding pid=4638 from /proc/ getdents64 enumeration" |
| `ls /proc/ \| grep <victim_pid>` after hide | NOT-LISTED | ✅ |
| `ps -p <victim_pid>` after hide | empty | ✅ |
| `cat /proc/<victim_pid>/comm` after hide (Stage 3 scope: direct access still works) | "sleep" | ✅ |
| Lighthouse cross-view detector | NO findings (by design — iterate_dir bypasses syscall hook) | ✅ "no process-concealment anomalies detected via cross-view" |
| Lighthouse ftrace-ops detector | flags shadowfox | ✅ "ftrace hook by module shadowfox (handler at sf_ftrace_callback+0x0/0x150 [shadowfox])" |
| Clean rmmod of both modules | no WARN traces; hook removed; hidden-PID list freed | ✅ "ftrace hook removed from __x64_sys_getdents64", "cleared 1 hidden pid entries" |

Two build-time API issues caught during the smoke test, both fixed inline and recorded as Stage 3 "Lessons learned" in the writeup:

1. `ftrace_instruction_pointer_set` → `ftrace_regs_set_instruction_pointer` (renamed in 6.x).
2. `<linux/dirent.h>` references u64/s64 without including `<linux/types.h>` itself; fixed by reordering our includes.

## Stage 2 smoke-test result (recorded 2026-05-18)

End-to-end demo of cred-modification + detector on `6.6.138-0606138-generic`:

| Step | Expected | Observed |
|---|---|---|
| Build both modules with Stage 2 additions | clean, no warnings on our files | ✅ |
| Load both modules; initial lighthouse pass | finds pre-existing sudo/sshd false-positives | ✅ (sshd pid=1809, insmod pid=1890 flagged with uid=0 loginuid=1000) |
| `echo escalate > ctl` from researcher shell | shell becomes uid=0; loginuid stays 1000 | ✅ (id: uid=0(root); loginuid still 1000) |
| Lighthouse scan after escalation | flags the bash shell with same format as sudo | ✅ (pid=1975 comm=bash uid=0 loginuid=1000) |
| Supplementary groups preserved (prepare_creds + stomp) | groups still include 1000(researcher) | ✅ |
| Clean rmmod of both modules | no WARN traces | ✅ |

Key teaching moment captured in dmesg history: identical warning format flagged sshd (PAM), insmod (sudo), bash (shadowfox), and sleep (sudo) — the detector cannot distinguish legitimate from rootkit escalation from this signal alone. Writeup section 7 names the Stage-4-class refinement (walk `task->mm->exe_file` for setuid-root bit).

## Stage 1.5 smoke-test result (recorded 2026-05-18)

Full-surface permanent hide via the new `permanent_hide=1` opt-in:

| Step | Expected | Observed |
|---|---|---|
| insmod shadowfox `permanent_hide=1` | params reflect mode, module visible | ✅ |
| `echo hide > .../ctl` | lsmod AND /sys/module both hidden | ✅ |
| `echo unhide > .../ctl` | refused with -EPERM | ✅ (tee: Operation not permitted) |
| Lighthouse detection while permanently hidden | both methods name shadowfox | ✅ |
| `rmmod shadowfox` | fails (not on modules list) | ✅ |
| `rmmod lighthouse` | clean | ✅ |
| Recovery | reboot the VM | ✅ (VM cleanly powered off) |

## Decision still deferred from Stage 0
- Keep `kernel-scratch/` (archived old HTB project) gitignored or commit it. Re-decide before `git init`.

---

## Lab VM cheatsheet (unchanged)
- **Boot**: `./vm/launch.sh` (Ctrl-A then X to terminate QEMU)
- **SSH**: `ssh shadowfox-lab`
- **Reset to clean state** (VM off): `cp vm/baseline-6.6.qcow2 vm/ubuntu-24.04-amd64.img`
- **Serial-console login fallback**: user `researcher`, password `12345`
- **Unattended-upgrades** masked in the VM
- **VM is currently OFF** — verify with `pgrep qemu` before next session

## Pinned kernel reference
- Version: `6.6.138-0606138-generic`, build `202605080820`
- Source: `https://kernel.ubuntu.com/mainline/v6.6.138/amd64/`
- 4 .debs cached in VM at `/tmp/kernel-debs/` (re-download after baseline reset)
- GRUB default in VM: `"Advanced options for Ubuntu>Ubuntu, with Linux 6.6.138-0606138-generic"`

## Repository layout (after Stage 1)
```
kernel-scratch/                       ← repo root
├── PROMPT.md                         ← project brief (read first)
├── PROJECT_STATE.md                  ← this file (gitignored)
├── Makefile                          ← top-level orchestrator
├── .gitignore
├── LICENSE                           ← GPL v2
├── README.md
├── docs/
│   ├── setup/
│   │   └── lab-vm.md
│   └── techniques/
│       ├── .gitkeep
│       └── 01-module-list-concealment.md   ← Stage 1 writeup
├── modules/
│   ├── shadowfox/
│   │   ├── Makefile
│   │   ├── main.c
│   │   ├── hide_module.{h,c}
│   │   └── symbols.{h,c}
│   └── lighthouse/
│       ├── Makefile
│       ├── main.c
│       ├── detect.{h,c}
│       ├── symbols.{h,c}
│       └── kernel_internal.h
├── harness/
│   └── .gitkeep                       ← populated in Stage 7
├── kernel-scratch/                    ← archived old HTB project, .gitignored
└── vm/
    ├── launch.sh
    ├── cloud-init/{user-data,meta-data}
    └── (qcow2, seed.iso, qemu.log — all gitignored)
```

## Active tasks
- none. Stage 1 closed.

## Next action for next session
1. Read this file fully.
2. Confirm VM state (`pgrep qemu` on host) — if user wants to run new smoke tests it must be up.
3. Ask user the Stage 2 session-start framing per PROMPT.md §"SESSION START PROTOCOL":
   - Stage 2 is "cred-modification helper + cred-state detector".
   - Restate in 2–3 lines, ask clarifying questions, propose a 3–5 step sub-plan, **then wait for go-ahead before writing code**.
4. Likely Stage 2 sub-plan to propose (do not start without approval):
   - Define the offensive helper's trigger: a magic prctl, a kallsyms-located syscall hook, or a debugfs write. Recommend debugfs again for consistency with Stage 1.
   - Implement `commit_creds(prepare_kernel_cred(NULL))` against a target PID (or current task). Wire trigger → cred-swap.
   - Detector side: walk `for_each_process()`, snapshot expected vs observed UID/GID/CAP_*; flag anomalies (uid != 0 task with cap_setuid; init-time-uid-0 task with later UID change without setuid(); etc.).
   - Writeup `docs/techniques/02-cred-modification.md` covering both sides.
   - Manual smoke test in the VM.

---

## Decisions log (carried over)
- **Lab host**: local QEMU x86_64 with TCG software emulation on Apple Silicon.
- **Target kernel**: Linux 6.6.138-0606138-generic (Ubuntu mainline-builds, build 202605080820). Distro: Ubuntu 24.04 server cloud image.
- **Repo location**: `/Users/avinash.kumar/Downloads/Gen-AI/kernel-scratch/`. Old HTB project archived in-place at `./kernel-scratch/`.
- **Repo layout**: single monorepo (modules + harness + docs under one tree).
- **SSH key**: existing ed25519 key (`<ssh-key>` comment).
- **SSH alias**: `shadowfox-lab` → `localhost:2223`.
- **VM user**: `researcher` (NOPASSWD sudo), password `12345` for serial fallback.
- **License**: GPL v2.
- **Stage 1 detector approach**: Option C — both `__module_address()` address scan AND `mod_tree` direct walk run on every detection pass. Each prints findings with a method tag; disagreement between methods is itself logged.
- **Stage 1 unhide trigger**: Option A — debugfs file at `/sys/kernel/debug/shadowfox/ctl`, plus a `hidden=0|1` module param for hide-on-load (default 0).
- **kallsyms resolver**: each module carries its own kprobe-trick copy in `symbols.c`. Consider factoring into a shared helper at end of Stage 2 once a third user appears.
- **`-Werror`**: not yet on. Revisit at the end of each stage; enable globally when all stages build clean.

## Stage roadmap (from PROMPT.md)
- 0: Repo skeleton, build system, lab VM, README framing ← **COMPLETE ✅**
- 1: Module-list concealment + matching detector ← **COMPLETE ✅**
- 1.5: Optional `permanent_hide=1` for full-surface concealment ← **COMPLETE ✅**
- 2: Cred-modification helper + cred-state detector ← **COMPLETE ✅**
- 3: Process concealment via ftrace + cross-view PID detector ← **COMPLETE ✅**
- 4: getdents64 filtering for files + vfs_readdir comparator ← **COMPLETE ✅**
- 5: /proc/net filtering + tcp_hashinfo walker ← **next**
- 3: Process concealment via ftrace + cross-view PID detector
- 4: `getdents64` filtering + `vfs_readdir` audit
- 5: `/proc/net` filtering + `tcp_hashinfo` walker
- 6: Integrity layer (syscall-table hash, CR0 WP watch)
- 7: Userland test harness
- 8: Docs polish + demo script
