# 04 — File hiding via getdents64 filter + iterate_dir audit

_Stage 4 of the shadowfox + lighthouse project. Paired writeup for
the filename concealment in `modules/shadowfox/hide_files.c` (which
extends the Stage 3 getdents64 hook) and the iterate_dir audit tool
in `modules/lighthouse/detect_files.c`._

> **Status.** Built and smoke-tested on the lab VM against kernel
> `6.6.138-0606138-generic`. End-to-end demo verified: a victim
> file dropped in `~/victim/` is hidden from `ls` after
> `echo hide-file secret.txt > ctl`; `cat ~/victim/secret.txt`
> still works (Stage 4 scope); `lighthouse audit-dir
> /home/researcher/victim` returns all 4 entries via iterate_dir
> while userspace `ls` returns only the un-hidden ones; ftrace-ops
> walker catches the hook on every scan.

---

## 1. Overview

Userspace tools that enumerate files — `ls`, `find`, `cp -r`,
shell tab-completion — all bottom out in the `getdents64` syscall
on a directory file descriptor. Stage 3 installed an ftrace hook
on `__x64_sys_getdents64` for PID concealment in `/proc/`; Stage 4
adds a second filter on the *same* hook: drop any directory entry
whose name appears in a configurable hidden-file set. The hook
fires on every getdents64 call regardless of which filesystem the
directory lives on, so a file added to the set disappears from
enumeration in `/tmp`, `/home/researcher`, `/var/log`, and
anywhere else by name alone.

Direct access by typed-out path still works: `cat /tmp/secret.txt`
opens the file fine because `open()` does not go through
getdents64. Concealing direct access requires hooking the path-
lookup chain, which is materially deeper kernel work and out of
scope for Stage 4.

Detection is genuinely harder than for process-hiding because the
kernel has no global "all files that exist" registry comparable to
`for_each_process()`. lighthouse therefore ships an *audit tool*,
not a self-contained detector: `detect_files.c` walks a directory
via `iterate_dir()` (the VFS path, which bypasses the syscall
hook) and dumps the true entry list to dmesg. The user — or, in
Stage 7, an automated harness — diffs that against userspace `ls`.
The integrity detector built in Stage 3 (`detect_hooks.c`)
continues to flag the underlying ftrace hook on every scan.

## 2. Kernel internals involved

This stage reuses every internal touched in Stage 3 — the ftrace
hook on `__x64_sys_getdents64`, the `linux_dirent64` stream
returned to userspace, the `iterate_dir()` VFS entry point — and
adds one new touchpoint: `filp_open()` for the audit tool's
directory open.

### `filp_open()`

```c
struct file *filp_open(const char *filename, int flags, umode_t mode);
```

Opens a file from kernel context, returning a `struct file *` (or
an `ERR_PTR`). Unlike a userspace `open()`, this doesn't allocate
a file descriptor in any task's fd table — it gives us a raw file
handle we can pass to `iterate_dir()`. Released with
`filp_close()`. Both are `EXPORT_SYMBOL`'d.

### `iterate_dir()`

```c
int iterate_dir(struct file *file, struct dir_context *ctx);
```

Walks `file`'s directory by calling `file->f_op->iterate_shared`
under inode `i_rwsem`. The actor in `ctx->actor` is invoked once
per entry. iterate_dir() is `EXPORT_SYMBOL`.

For the audit detector, we provide an actor that just logs each
entry to dmesg. It returns `true` to keep iteration going.

### What we deliberately do NOT touch

- **Path-lookup (`path_lookupat`, `lookup_one_len`).** These are
  what `open()` uses. We do not hook them. A user who knows a
  file's name can still open it directly — Stage 4 hides from
  *enumeration*, not from *access*. Full file concealment is a
  Stage 6/7-class problem.
- **`stat()` and the various `*at` syscalls.** Same reasoning.
- **`readdir()` (the older single-entry variant).** Modern glibc
  routes through getdents64; the older API is essentially dead in
  the standard library, so we ignore it.

## 3. Implementation walkthrough

### `hide_files.c` — the pattern list

The list is a `LIST_HEAD` of `struct hidden_file` entries, each
kmalloc'd with a flexible-array name. Locking is a single
spinlock.

```c
struct hidden_file {
    struct list_head link;
    char name[];  /* kmalloc'd: sizeof + strlen + 1 */
};

bool sf_files_should_hide(const char *name, int namelen)
{
    struct hidden_file *h;
    bool found = false;

    spin_lock(&hidden_files_lock);
    list_for_each_entry(h, &hidden_files, link) {
        size_t hnlen = strlen(h->name);
        if (hnlen == (size_t)namelen &&
            memcmp(h->name, name, namelen) == 0) {
            found = true;
            break;
        }
    }
    spin_unlock(&hidden_files_lock);
    return found;
}
```

Pattern matching is exact and case-sensitive. Diamorphine's
"anything starting with `[hidden_prefix]`" gives more demo
flexibility but adds a layer of policy decisions; for Stage 4
educational purposes, byte-exact comparison is transparent and
correct.

`sf_files_hide()` refuses `.` and `..` (would break basic
directory listing for everyone) and refuses empty or
NAME_MAX-exceeding names.

### Integration into the Stage 3 getdents64 hook

One line of new logic in `hide_proc.c`'s filter:

```c
if (name_is_hidden_pid(ent->d_name, namelen) ||
    sf_files_should_hide(ent->d_name, namelen)) {
    memmove(ent, (char *)ent + reclen, total - offset - reclen);
    total -= reclen;
} else {
    offset += reclen;
}
```

The hook walks each `linux_dirent64` once, consults both filters,
and drops the entry if either matches. The cost of the additional
check is a single function call and (when the file list is empty,
the common case) zero list iterations.

### Debugfs control

```
echo hide-file secret.txt          > /sys/kernel/debug/shadowfox/ctl
echo show-file secret.txt          > /sys/kernel/debug/shadowfox/ctl
echo clear-hidden-files            > /sys/kernel/debug/shadowfox/ctl
```

The `ctl` command parser's buffer is bumped to 320 bytes to fit
`hide-file ` (10) plus a `NAME_MAX` (255) filename plus newline
and slack. Names are matched and stored verbatim, including any
trailing whitespace (a quirk worth knowing if you copy-paste names
with embedded spaces).

### `detect_files.c` — the audit tool

```c
int lh_audit_directory(const char *path)
{
    struct file *file = filp_open(path, O_RDONLY | O_DIRECTORY, 0);
    if (IS_ERR(file)) return PTR_ERR(file);

    struct audit_collector c = { .ctx.actor = audit_actor,
                                 .ctx.pos = 0,
                                 .path = path };
    int ret = iterate_dir(file, &c.ctx);
    filp_close(file, NULL);
    return ret;
}
```

The actor logs every entry:

```
lighthouse: audit /tmp: name='secret.txt' type=8 ino=12345
lighthouse: audit /tmp: name='.X11-unix' type=4 ino=98765
...
```

Triggered from userspace by writing the path:

```
echo /tmp > /sys/kernel/debug/lighthouse/audit-dir
```

The detector does NOT itself diff against userspace — it produces
half the data. The Stage 7 test harness will own the diff.

## 4. Kernel version compatibility matrix

| Kernel        | Status                  | Notes                                                                                   |
|---------------|-------------------------|-----------------------------------------------------------------------------------------|
| < 4.18        | Won't build             | Pre-mfentry; underlying ftrace hook story differs (covered in Stage 3 writeup).         |
| 4.18 – 5.6    | Should work             | Same caveats as Stage 3.                                                                |
| 5.7+          | Should work             | kallsyms_lookup_name unexport (handled in Stage 3 by the kprobe trick).                 |
| **6.6 LTS**   | **Target**              | Pinned: `6.6.138-0606138-generic`.                                                      |
| 6.8+          | Unverified              | `iterate_dir` and `filp_open` have been stable for many releases; should work.          |

The Stage 4 surface is essentially the existing Stage 3 surface
plus a `strcmp`. Anywhere Stage 3 builds and runs, Stage 4 should.

## 5. Detection counterpart

Two complementary signals, both familiar from Stage 3:

### `detect_files.c` — directory audit (NEW)

Reads a path, walks via iterate_dir, logs every entry. **This
does not flag anything by itself.** It produces the "ground truth"
list. The user (or Stage 7 harness) compares against userspace
`ls`. Discrepancies are hidden filenames.

### `detect_hooks.c` — ftrace-ops integrity walker (from Stage 3)

Already running on every scan. Flags shadowfox via:

```
lighthouse: ftrace hook by module shadowfox (handler at sf_ftrace_callback+0x0/0x150 [shadowfox], ftrace_ops at <addr>)
```

**The ftrace-ops walker is the actual rootkit detector for Stage
4.** It catches `shadowfox` regardless of whether you've added any
PIDs or filenames to the hidden sets — the hook itself is the
signal. The audit tool is an investigative supplement that helps
you find *which specific files* are being filtered, once you know
that something is.

### Why no cross-view detector?

For Stage 3 we shipped `detect_proc.c` (for_each_process vs
iterate_dir on /proc) as a teaching example, even though it
doesn't catch a syscall-level hook. For Stage 4 there is no
equivalent: the kernel has no global list of "all files that
should exist." File existence is per-filesystem, and walking each
mounted filesystem's inode tables is filesystem-specific and well
out of educational scope. The audit-tool model is the honest
substitute.

## 6. Real-world references

- **Diamorphine** by m0nad —
  [github.com/m0nad/Diamorphine](https://github.com/m0nad/Diamorphine).
  Same getdents64-hook pattern for file hiding; uses a magic
  prefix instead of an exact-name list.
- **Reptile** by f0rb1dd3n —
  [github.com/f0rb1dd3n/Reptile](https://github.com/f0rb1dd3n/Reptile).
  More elaborate file hiding, including hooks on `lstat` and
  `open` so even direct-by-path access fails. Stage 4 deliberately
  does not.
- **Volatility framework** —
  [github.com/volatilityfoundation/volatility3](https://github.com/volatilityfoundation/volatility3).
  Offline forensic equivalent: walks filesystem structures in a
  memory image to enumerate files that would be hidden on the
  live system.
- **LWN.net** — articles on `iterate_dir` semantics and the
  evolution from `readdir()` to `getdents64()`. Background reading
  on why the modern syscall is the right hook point.
- **Linux kernel source** — `fs/readdir.c`, `fs/open.c` for
  filp_open, `include/linux/fs.h` for struct file_operations.
- **Anti-rootkit checklists** (chkrootkit, rkhunter source code) —
  many run timing experiments and compare file listings from
  inside `/lib` vs `/proc/self/maps` and similar cross-views.

## 7. Mitigations

Same Stage-3 list applies — module signing, Lockdown, ftrace
disabled — plus a few that are more specific to file hiding:

- **Filesystem-level integrity checks (AIDE, tripwire,
  IMA/EVM).** These hash file metadata from kernel context with
  signed baselines. A rootkit that hides files from `getdents64`
  doesn't fool IMA because IMA reads inodes directly. EVM extends
  this to metadata.
- **Auditd with file-watch rules.** `auditctl -w /etc/passwd` and
  similar will surface file accesses regardless of whether
  `ls /etc/` lists the file. If the rootkit hides its own data
  file, audit on path will still record reads.
- **Memory forensics during incident response.** Volatility's
  Linux plugins can walk the dentry cache, inode tables, and
  filesystem metadata in a memory image — bypassing every live
  hook.
- **Periodic cross-view auditing.** lighthouse + Stage 7 harness
  approximates this; in production, LKRG and similar do it on a
  timer.

## 8. Lessons learned

- **Detection asymmetry between Stage 3 and Stage 4.** Process-
  hiding has a global ground-truth list (`for_each_process`); file-
  hiding does not. This forced the Stage 4 detector to drop the
  cross-view pattern and ship an audit tool plus the existing
  ftrace-ops walker. The honest framing (audit + integrity instead
  of "comprehensive detector") makes the writeup more useful, and
  primes Stage 7 to own the userspace-side diff.
- **Composing filters in the same hook.** Stage 3's hook walked
  dirents and called one filter; Stage 4 needs two. The natural
  refactor would be a filter chain (function-pointer array). For
  Stage 4 we kept the integration as a two-condition `if` —
  simpler, no abstraction overhead, the chain pattern can wait
  until a third filter shows up.
- **`PATH_MAX` on the stack is 4 KB.** The audit handler's path
  buffer was tempting to put on the stack; bumping a debugfs write
  handler's stack usage to 4 KB is rude. `kmalloc(GFP_KERNEL)` for
  the duration of the call costs almost nothing and keeps stack
  footprint sane.
- **`hide-file .` is a one-character mistake away from breaking
  everything.** Refusing `.` and `..` outright costs three lines
  and saves a future debugging session. The same pattern that
  protected PID 1 in Stage 3 applies here.
- **Trailing-whitespace gotcha in command parsing.** `echo "hide-
  file foo"` (note the space inside the quotes) hides the name
  `foo ` (trailing space) — not `foo`. Stage 4 documents this
  rather than fixing it; trim-whitespace policy is a Stage 8 docs-
  polish concern.

---

_Next technique: Stage 5 — `/proc/net` filtering for network port
hiding + `tcp_hashinfo` walker comparator._
