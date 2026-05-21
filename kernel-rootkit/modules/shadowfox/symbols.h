/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_SYMBOLS_H
#define _SHADOWFOX_SYMBOLS_H

#include <linux/list.h>
#include <linux/mutex.h>

/*
 * Kernel symbols resolved from kallsyms during module init.
 *
 * Valid only after sf_symbols_init() has returned 0. Untouched on
 * failure — callers must check the return value before use.
 */
extern struct list_head *sf_modules_head;
extern struct mutex	*sf_module_mutex;

/*
 * Resolve every symbol this module needs and populate the externs
 * above. Returns 0 on success or a negative errno on the first symbol
 * that fails to resolve.
 *
 * Safe to call exactly once, from module init context.
 */
int sf_symbols_init(void);

/*
 * General-purpose kallsyms resolver. Returns the address of `name`
 * or NULL if the symbol could not be resolved. Only valid after
 * sf_symbols_init() has succeeded.
 *
 * Used by ftrace_hook.c and any other in-module code that needs to
 * look up a private kernel symbol at runtime.
 */
void *sf_kallsyms_lookup(const char *name);

#endif /* _SHADOWFOX_SYMBOLS_H */
