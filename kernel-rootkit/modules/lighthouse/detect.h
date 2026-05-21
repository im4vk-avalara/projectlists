/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_DETECT_H
#define _LIGHTHOUSE_DETECT_H

/*
 * Run a single hidden-module detection pass.
 *
 * Builds three sets of loaded modules:
 *
 *   visible_set  - walks the "modules" linked list under module_mutex.
 *                  This is the surface shadowfox-style concealment
 *                  removes from.
 *   addr_set     - scans the kernel module-address range via
 *                  __module_address() (EXPORT_SYMBOL_GPL). Layout
 *                  independent — survives kernel-internal changes.
 *   tree_set     - direct rb-tree walk over mod_tree using the
 *                  replicated layout in kernel_internal.h. Only
 *                  compiled when CONFIG_MODULES_TREE_LOOKUP is set.
 *
 * Any module present in addr_set or tree_set but missing from
 * visible_set is concealed; each finding is logged at KERN_WARNING.
 *
 * Returns 0 on success or a negative errno on internal failure. The
 * count of hidden modules is conveyed via dmesg, not the return value.
 *
 * Must be called in process context (sleeps).
 */
int lh_detect_hidden_modules(void);

#endif /* _LIGHTHOUSE_DETECT_H */
