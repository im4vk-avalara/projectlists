// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: reusable ftrace function-hook infrastructure.
 *
 * Mechanism (modern Linux, >= 5.x with -mfentry):
 *
 *   1. ftrace tracks every function-entry call site (mcount/__fentry__)
 *      in its dyn_ftrace table.
 *   2. We register an ftrace_ops with FTRACE_OPS_FL_SAVE_REGS and
 *      FTRACE_OPS_FL_IPMODIFY for the target function's IP.
 *   3. When the function is called, ftrace_caller saves all
 *      registers and invokes our handler. Our handler rewrites the
 *      saved instruction pointer (fregs->regs.ip) to point at our
 *      replacement function. ftrace_caller restores registers and
 *      jumps to the new IP — so our replacement runs in place of
 *      the original, with identical calling convention.
 *
 * Recursion guard: if a replacement function calls the original
 * via the stored function pointer, the ftrace hook fires again.
 * The handler detects this by checking whether parent_ip is inside
 * our own module's text — if so it does NOT redirect, allowing the
 * original to execute (the "call through" pattern). without this
 * check, every replacement that wraps the original would infinite-
 * loop.
 *
 * The design borrows from Reptile's hook helper and from the
 * livepatch infrastructure that landed in 4.7. We keep the API
 * minimal so this file stays a foundation for stages 3, 4, and 5.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/ftrace.h>
#include <linux/module.h>
#include <linux/printk.h>

#include "ftrace_hook.h"
#include "symbols.h"

static void sf_ftrace_callback(unsigned long ip, unsigned long parent_ip,
			       struct ftrace_ops *ops,
			       struct ftrace_regs *fregs)
{
	struct sf_ftrace_hook *hook =
		container_of(ops, struct sf_ftrace_hook, ops);

	/*
	 * If the caller of the hooked function is in our own module,
	 * that means our replacement is calling the original through
	 * the stored pointer. Do not redirect — let the original run.
	 */
	if (within_module(parent_ip, THIS_MODULE))
		return;

	ftrace_regs_set_instruction_pointer(fregs, (unsigned long)hook->replacement);
}

int sf_ftrace_hook_install(struct sf_ftrace_hook *hook)
{
	int ret;

	hook->target = (unsigned long)sf_kallsyms_lookup(hook->name);
	if (!hook->target) {
		pr_err("ftrace hook: cannot resolve %s\n", hook->name);
		return -ENOENT;
	}

	if (hook->original_pp)
		*hook->original_pp = (void *)hook->target;

	hook->ops.func = sf_ftrace_callback;
	hook->ops.flags = FTRACE_OPS_FL_SAVE_REGS | FTRACE_OPS_FL_IPMODIFY;

	ret = ftrace_set_filter_ip(&hook->ops, hook->target, 0, 0);
	if (ret) {
		pr_err("ftrace_set_filter_ip(%s) failed: %d\n",
		       hook->name, ret);
		return ret;
	}

	ret = register_ftrace_function(&hook->ops);
	if (ret) {
		pr_err("register_ftrace_function(%s) failed: %d\n",
		       hook->name, ret);
		ftrace_set_filter_ip(&hook->ops, hook->target, 1, 0);
		return ret;
	}

	pr_info("ftrace hook installed on %s\n", hook->name);
	return 0;
}

void sf_ftrace_hook_remove(struct sf_ftrace_hook *hook)
{
	int ret;

	ret = unregister_ftrace_function(&hook->ops);
	if (ret)
		pr_warn("unregister_ftrace_function(%s) failed: %d\n",
			hook->name, ret);

	ret = ftrace_set_filter_ip(&hook->ops, hook->target, 1, 0);
	if (ret)
		pr_warn("ftrace_set_filter_ip remove(%s) failed: %d\n",
			hook->name, ret);

	pr_info("ftrace hook removed from %s\n", hook->name);
}
