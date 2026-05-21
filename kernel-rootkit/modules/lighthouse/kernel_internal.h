/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_KERNEL_INTERNAL_H
#define _LIGHTHOUSE_KERNEL_INTERNAL_H

/*
 * Replica of the kernel-internal struct mod_tree_root layout.
 *
 * The authoritative definition lives in kernel/module/internal.h —
 * a private header not exported to out-of-tree modules. struct
 * mod_tree_node, on the other hand, IS exposed publicly via
 * <linux/module.h> in 6.6, so we use the kernel's definition for
 * that one directly.
 *
 *   *** THIS COUPLES LIGHTHOUSE TIGHTLY TO KERNEL 6.6.x LAYOUT. ***
 *
 * Strategy: we only declare the prefix of mod_tree_root that we
 * actually dereference (the `root` latch tree). The kernel's struct
 * likely has additional fields after `root` (addr_min/addr_max and
 * possibly per-region bounds for 6.6's multi-memory-region modules),
 * but we never read them, so their offsets do not matter to us.
 * Layout-wise, only the first field — `root` — must align with the
 * kernel's definition. In 6.6 (CONFIG_MODULES_TREE_LOOKUP=y) it does.
 *
 * If a future kernel reorders the struct so that `root` is no longer
 * at offset 0, the detector's tree walker would read garbage on the
 * first rb_node deref. The paired __module_address-based detector is
 * layout-independent and would catch the disagreement.
 *
 * Verified against: linux-6.6.138-0606138-generic.
 * Reference: include/linux/rbtree_latch.h (struct latch_tree_root,
 *            struct latch_tree_node — these are public headers).
 */

#include <linux/rbtree_latch.h>

struct mod_tree_root {
#ifdef CONFIG_MODULES_TREE_LOOKUP
	struct latch_tree_root root;
	/* Real struct has more fields after `root`; we do not read them. */
#else
	/* Without the config, the kernel struct has no `root` field at
	 * all and the detector's tree walker is compiled out, so the
	 * struct as we see it is effectively unused. */
	unsigned long _placeholder;
#endif
};

#endif /* _LIGHTHOUSE_KERNEL_INTERNAL_H */
