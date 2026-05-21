// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: cross-view hidden-module detector.
 *
 * Two independent enumerators identify loaded modules and the result
 * is diffed against the kernel's "modules" linked list (the surface
 * shadowfox conceals by unlinking THIS_MODULE):
 *
 *   1. __module_address() address-range scan
 *      Walks [MODULES_VADDR, MODULES_END) at PAGE_SIZE granularity
 *      and asks the kernel which module owns each address. The
 *      symbol is unexported in 6.6, so we resolve it through
 *      kallsyms (lh_module_address); the underlying lookup logic is
 *      the kernel's, so this path is robust against changes in
 *      mod_tree's struct layout — those would only affect detector
 *      #2 below.
 *
 *   2. mod_tree direct walk (CONFIG_MODULES_TREE_LOOKUP only)
 *      Walks the latch RB-tree at &mod_tree.root.tree[0] using the
 *      replicated struct layout in kernel_internal.h. Tightly coupled
 *      to the 6.6 kernel layout; included as the pedagogical
 *      "look inside" counterpart to detector #1.
 *
 * Both detectors should agree. Disagreement is itself logged — that
 * is the signal we would see if a hypothetical future rootkit
 * unlinked from one tree but not the other.
 *
 * References:
 *   Volatility "lsmod" plugin (offline equivalent of this scan)
 *   Diamorphine README discusses the same list-vs-tree asymmetry
 *   LWN "Loading modules" series for the mod_tree design
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/err.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/preempt.h>
#include <linux/printk.h>
#include <linux/rbtree.h>
#include <linux/sched.h>
#include <linux/slab.h>

#include <asm/page.h>		/* MODULES_VADDR, MODULES_END on x86_64 */

#include "detect.h"
#include "kernel_internal.h"
#include "symbols.h"

/*
 * Module set: simple unsorted linked list with O(N²) membership check.
 * Real systems carry ~100-200 loaded modules; the linear scan is fast
 * enough that a hash set is not warranted.
 */
struct mod_entry {
	struct module	*mod;
	struct list_head link;
};

static bool set_contains(struct list_head *set, struct module *mod)
{
	struct mod_entry *e;

	list_for_each_entry(e, set, link) {
		if (e->mod == mod)
			return true;
	}
	return false;
}

static int set_add(struct list_head *set, struct module *mod)
{
	struct mod_entry *e;

	if (set_contains(set, mod))
		return 0;

	e = kzalloc(sizeof(*e), GFP_KERNEL);
	if (!e)
		return -ENOMEM;

	e->mod = mod;
	list_add(&e->link, set);
	return 0;
}

static void set_free(struct list_head *set)
{
	struct mod_entry *e, *tmp;

	list_for_each_entry_safe(e, tmp, set, link) {
		list_del(&e->link);
		kfree(e);
	}
}

/* visible_set: walk the modules linked list under module_mutex. */
static int build_visible_set(struct list_head *set)
{
	struct module *mod;
	int ret = 0;

	mutex_lock(lh_module_mutex);

	list_for_each_entry(mod, lh_modules_head, list) {
		ret = set_add(set, mod);
		if (ret < 0)
			break;
	}

	mutex_unlock(lh_module_mutex);
	return ret;
}

/*
 * addr_set: scan kernel module-address range page-by-page and ask
 * __module_address() which module owns each address.
 *
 * Locking: __module_address() requires the caller to hold either
 * module_mutex or to have preemption disabled (or RCU-sched). We use
 * preempt_disable around each call — cheap, scoped narrowly. Between
 * calls we cond_resched() so a multi-millisecond scan doesn't starve
 * higher-priority work.
 *
 * Step size: PAGE_SIZE is sufficient since every module mapping is at
 * least page-aligned.
 */
static int build_addr_set(struct list_head *set)
{
	unsigned long addr;
	int ret;

	for (addr = MODULES_VADDR; addr < MODULES_END; addr += PAGE_SIZE) {
		struct module *mod;

		preempt_disable();
		mod = lh_module_address(addr);
		preempt_enable();

		if (!mod)
			goto next;

		ret = set_add(set, mod);
		if (ret < 0)
			return ret;
next:
		cond_resched();
	}

	return 0;
}

#ifdef CONFIG_MODULES_TREE_LOOKUP
/*
 * tree_set: walk mod_tree directly via the replicated struct layout.
 *
 * mod_tree.root is a latch_tree_root with two parallel rb-trees
 * (tree[0], tree[1]) — the latching is for lock-free reader coherence
 * under concurrent insert/remove. Either tree contains the full
 * working set; we pick tree[0].
 *
 * Container chain: rb_node -> latch_tree_node (via .node[0])
 *                          -> mod_tree_node (via .node)
 *                          -> struct module * (.mod)
 *
 * Each loaded module has up to two mod_tree_node entries (text + data
 * mappings), so the caller dedupes by mod pointer through set_add.
 *
 * Locking: no explicit lock taken; the latch tree's seqcount bounds
 * reader-vs-writer races. Worst case we miss one entry on a tear; the
 * next detection pass picks it up.
 */
static int build_tree_set(struct list_head *set)
{
	struct rb_node *rbn;

	for (rbn = rb_first(&lh_mod_tree->root.tree[0]); rbn;
	     rbn = rb_next(rbn)) {
		struct latch_tree_node *ltn =
			container_of(rbn, struct latch_tree_node, node[0]);
		struct mod_tree_node *mtn =
			container_of(ltn, struct mod_tree_node, node);
		int ret = set_add(set, mtn->mod);

		if (ret < 0)
			return ret;
	}

	return 0;
}
#else
static int build_tree_set(struct list_head *set)
{
	(void)set;
	return 0;
}
#endif /* CONFIG_MODULES_TREE_LOOKUP */

/*
 * For every entry in `candidates` that is not in `visible`, emit a
 * KERN_WARNING line and bump the counter. Returns the hidden-module
 * count for this detector.
 */
static int diff_and_log(struct list_head *candidates,
			struct list_head *visible,
			const char *method)
{
	struct mod_entry *e;
	int count = 0;

	list_for_each_entry(e, candidates, link) {
		if (!set_contains(visible, e->mod)) {
			pr_warn("hidden module detected via %s: %s\n",
				method, e->mod->name);
			count++;
		}
	}

	return count;
}

int lh_detect_hidden_modules(void)
{
	LIST_HEAD(visible);
	LIST_HEAD(addr);
	LIST_HEAD(tree);
	int ret;
	int hidden_addr = 0;
	int hidden_tree = 0;

	pr_info("running detection pass\n");

	ret = build_visible_set(&visible);
	if (ret < 0) {
		pr_err("build_visible_set failed: %d\n", ret);
		goto out;
	}

	ret = build_addr_set(&addr);
	if (ret < 0) {
		pr_err("build_addr_set failed: %d\n", ret);
		goto out;
	}

	ret = build_tree_set(&tree);
	if (ret < 0) {
		pr_err("build_tree_set failed: %d\n", ret);
		goto out;
	}

	hidden_addr = diff_and_log(&addr, &visible, "__module_address");

	if (IS_ENABLED(CONFIG_MODULES_TREE_LOOKUP)) {
		hidden_tree = diff_and_log(&tree, &visible, "mod_tree");

		if (hidden_tree != hidden_addr)
			pr_warn("detector disagreement: __module_address=%d mod_tree=%d (a future technique may be unlinking from only one surface)\n",
				hidden_addr, hidden_tree);
	} else {
		pr_info("mod_tree detector skipped: CONFIG_MODULES_TREE_LOOKUP unset\n");
	}

	if (hidden_addr == 0 && hidden_tree == 0)
		pr_info("no hidden modules detected\n");

	ret = 0;
out:
	set_free(&visible);
	set_free(&addr);
	set_free(&tree);
	return ret;
}
