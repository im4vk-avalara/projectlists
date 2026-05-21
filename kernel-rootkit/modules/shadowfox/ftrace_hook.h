/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_FTRACE_HOOK_H
#define _SHADOWFOX_FTRACE_HOOK_H

#include <linux/ftrace.h>

/*
 * Reusable ftrace function-hook wrapper.
 *
 * Modern Linux (>= 5.x with -mfentry instrumentation) lets out-of-
 * tree code redirect kernel function calls without modifying any
 * instruction in the running kernel image. We use ftrace's
 * IPMODIFY flag to rewrite the saved instruction pointer inside an
 * ftrace_caller frame, so when ftrace_caller returns it jumps to
 * our replacement instead of the original function.
 *
 * Recursion guard: callers may invoke the original from inside
 * their replacement (the "call through" pattern). The handler
 * checks whether the caller (parent_ip) is inside our module's
 * text; if so it does NOT redirect, letting the original run.
 *
 * Typical use:
 *
 *   static long (*orig_foo)(args);
 *   static long my_foo(args) { ... return orig_foo(args); }
 *
 *   static struct sf_ftrace_hook foo_hook = {
 *       .name        = "foo",
 *       .replacement = my_foo,
 *       .original_pp = (void **)&orig_foo,
 *   };
 *
 *   ret = sf_ftrace_hook_install(&foo_hook);
 *
 * Both install and remove are NOT re-entrant on the same hook;
 * callers must serialise them. Concurrent calls through the hooked
 * function are safe — that is what ftrace is designed for.
 *
 * Pre-condition: sf_symbols_init() has succeeded (we use the
 * kallsyms resolver to translate `name` to an address).
 */
struct sf_ftrace_hook {
	/* Caller-filled */
	const char	*name;
	void		*replacement;
	void		**original_pp;

	/* Internal — do not touch */
	unsigned long	target;
	struct ftrace_ops ops;
};

int sf_ftrace_hook_install(struct sf_ftrace_hook *hook);
void sf_ftrace_hook_remove(struct sf_ftrace_hook *hook);

#endif /* _SHADOWFOX_FTRACE_HOOK_H */
