// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: ftrace-hook integrity walker.
 *
 * The kernel maintains a global list of registered ftrace_ops at
 * the symbol "ftrace_ops_list" (head) terminated by
 * "ftrace_list_end" (a static sentinel). Each ftrace_ops carries a
 * .func pointer to the callback the kernel will dispatch to when
 * the hooked function fires.
 *
 * Detection signal: walk the list, and for each op resolve the
 * module that owns the .func address via __module_address(). If
 * the owner is a module other than ourselves, the module has
 * registered an ftrace hook — flag it.
 *
 * This catches shadowfox's __x64_sys_getdents64 hook, which the
 * cross-view PID detector cannot catch because iterate_dir bypasses
 * the syscall path. It also catches any other module-owned ftrace
 * op — including any other rootkit using the same primitive — so
 * the signal is genuinely useful, not specific to our offense.
 *
 * Kernel-internal ftrace_ops (perf, kprobes, ftrace itself) have
 * .func pointers in vmlinux text. __module_address returns NULL for
 * those, so they are skipped without need for an allowlist.
 *
 * Locking: rcu_read_lock for the list walk; preempt_disable around
 * each __module_address call (its lockdep assertion requires either
 * module_mutex or preempt-disabled).
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/ftrace.h>
#include <linux/module.h>
#include <linux/preempt.h>
#include <linux/printk.h>
#include <linux/rcupdate.h>

#include "detect_hooks.h"
#include "symbols.h"

int lh_detect_ftrace_hooks(void)
{
	struct ftrace_ops **head_addr;
	struct ftrace_ops *list_end;
	struct ftrace_ops *op;
	int count = 0;

	pr_info("running ftrace-hook integrity pass\n");

	head_addr = lh_kallsyms_lookup("ftrace_ops_list");
	if (!head_addr) {
		pr_err("could not resolve ftrace_ops_list\n");
		return -ENOENT;
	}

	list_end = lh_kallsyms_lookup("ftrace_list_end");
	if (!list_end) {
		pr_err("could not resolve ftrace_list_end\n");
		return -ENOENT;
	}

	rcu_read_lock();
	op = rcu_dereference_raw(*head_addr);
	while (op && op != list_end) {
		struct module *owner;

		preempt_disable();
		owner = lh_module_address((unsigned long)op->func);
		preempt_enable();

		if (owner && owner != THIS_MODULE) {
			pr_warn("ftrace hook by module %s (handler at %pS, ftrace_ops at %p)\n",
				owner->name, (void *)op->func, op);
			count++;
		}

		op = rcu_dereference_raw(op->next);
	}
	rcu_read_unlock();

	if (count == 0)
		pr_info("no out-of-tree ftrace hooks detected\n");
	else
		pr_info("ftrace-hook integrity pass complete: %d flagged\n",
			count);

	return 0;
}
