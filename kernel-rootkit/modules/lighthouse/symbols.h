/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_SYMBOLS_H
#define _LIGHTHOUSE_SYMBOLS_H

#include <linux/list.h>
#include <linux/mutex.h>

/*
 * Kernel symbols resolved from kallsyms during module init.
 *
 * Valid only after lh_symbols_init() has returned 0. Untouched on
 * failure — callers must check the return value before use.
 *
 * lh_mod_tree points at the kernel's global "mod_tree" instance and
 * is only meaningful when CONFIG_MODULES_TREE_LOOKUP is set (without
 * that config the struct has no rb-tree to walk; see kernel_internal.h).
 * Consumers that dereference it through the layout-replicated struct
 * must include "kernel_internal.h".
 */
struct mod_tree_root;  /* forward decl; full definition in kernel_internal.h */
struct module;         /* forward decl; full definition in <linux/module.h> */

extern struct list_head		*lh_modules_head;
extern struct mutex		*lh_module_mutex;
extern struct mod_tree_root	*lh_mod_tree;

/*
 * Function pointer to the kernel's internal __module_address(). The
 * symbol is declared in <linux/module.h> but NOT exported in 6.6;
 * we resolve it through kallsyms like every other private symbol.
 */
extern struct module *(*lh_module_address)(unsigned long addr);

/*
 * Resolve every symbol this module needs and populate the externs
 * above. Returns 0 on success or a negative errno on the first symbol
 * that fails to resolve.
 *
 * Safe to call exactly once, from module init context.
 */
int lh_symbols_init(void);

/*
 * General-purpose kallsyms resolver. Returns the address of `name`
 * or NULL if the symbol could not be resolved. Only valid after
 * lh_symbols_init() has succeeded.
 *
 * Used by detectors that need to inspect kernel-internal data
 * structures (e.g., ftrace_ops_list).
 */
void *lh_kallsyms_lookup(const char *name);

#endif /* _LIGHTHOUSE_SYMBOLS_H */
