// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: kallsyms-based symbol resolver.
 *
 * Mirror of the resolver in modules/shadowfox/symbols.c. Both modules
 * carry their own copy for now; we will consider factoring into a
 * shared helper once a third user appears (Stage 2+).
 *
 * kallsyms_lookup_name() was unexported in 5.7 (commit 0bd476e6c671).
 * The standard workaround — registering a kprobe on the symbol name
 * and reading kp.addr — gives us the function address without ever
 * letting the probe fire.
 *
 * Symbols resolved for Stage 1:
 *
 *   "modules"      - struct list_head, head of the loaded-module list.
 *   "module_mutex" - serialises module-list mutation; held across
 *                    the visible-set walk.
 *   "mod_tree"     - the kernel's address-keyed RB-tree of loaded
 *                    modules. Resolved unconditionally; the consumer
 *                    (detect.c) only walks it when CONFIG_MODULES_TREE_LOOKUP
 *                    is set.
 *   "__module_address" - returns the struct module *owning an address.
 *                    Declared in <linux/module.h> but NOT exported in
 *                    6.6, so we resolve it through kallsyms and call
 *                    via the function pointer below.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/kprobes.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/printk.h>

#include "symbols.h"

struct list_head	*lh_modules_head;
struct mutex		*lh_module_mutex;
struct mod_tree_root	*lh_mod_tree;
struct module		*(*lh_module_address)(unsigned long addr);

/* Resolved via the kprobe trick; not exposed outside this TU. */
static unsigned long (*lh_kallsyms_lookup_name)(const char *name);

/*
 * Some kernels reject register_kprobe() with a NULL pre_handler. Give
 * it a no-op so the call is portable; the probe is unregistered before
 * it ever has a chance to fire.
 */
static int lh_noop_pre(struct kprobe *p, struct pt_regs *regs)
{
	(void)p;
	(void)regs;
	return 0;
}

static int resolve_kallsyms_lookup_name(void)
{
	struct kprobe kp = {
		.symbol_name = "kallsyms_lookup_name",
		.pre_handler = lh_noop_pre,
	};
	int ret;

	ret = register_kprobe(&kp);
	if (ret < 0) {
		pr_err("register_kprobe(kallsyms_lookup_name) failed: %d\n",
		       ret);
		return ret;
	}

	lh_kallsyms_lookup_name = (void *)kp.addr;
	unregister_kprobe(&kp);

	if (!lh_kallsyms_lookup_name) {
		pr_err("kallsyms_lookup_name address came back NULL\n");
		return -ENOENT;
	}

	return 0;
}

void *lh_kallsyms_lookup(const char *name)
{
	unsigned long addr;

	if (!lh_kallsyms_lookup_name)
		return NULL;

	addr = lh_kallsyms_lookup_name(name);
	if (!addr) {
		pr_err("kallsyms could not resolve %s\n", name);
		return NULL;
	}
	return (void *)addr;
}

int lh_symbols_init(void)
{
	int ret;

	ret = resolve_kallsyms_lookup_name();
	if (ret < 0)
		return ret;

	lh_modules_head = lh_kallsyms_lookup("modules");
	if (!lh_modules_head)
		return -ENOENT;

	lh_module_mutex = lh_kallsyms_lookup("module_mutex");
	if (!lh_module_mutex)
		return -ENOENT;

	lh_mod_tree = lh_kallsyms_lookup("mod_tree");
	if (!lh_mod_tree)
		return -ENOENT;

	lh_module_address = lh_kallsyms_lookup("__module_address");
	if (!lh_module_address)
		return -ENOENT;

	pr_info("symbol resolution complete\n");
	return 0;
}
