// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: cross-view PID detector.
 *
 * Two enumerators, diffed:
 *
 *   1. for_each_process under rcu_read_lock — the kernel's
 *      authoritative task list.
 *   2. iterate_dir() on a filp_open()'d /proc — the VFS-level
 *      directory walk, which calls f_op->iterate_shared and
 *      ultimately proc_pid_readdir.
 *
 * A rootkit that hooks proc_pid_readdir (or anything below
 * iterate_dir in the call chain) will appear in (1) but not (2),
 * and gets flagged. A rootkit that hooks __x64_sys_getdents64
 * (shadowfox's Stage 3 default) bypasses this detector entirely —
 * iterate_dir() does not flow through the syscall entry. The
 * companion lh_detect_ftrace_hooks() catches syscall-level hooks
 * via the ftrace_ops_list walk instead.
 *
 * Locking and races:
 *
 *   The two enumerations run in separate windows (we cannot hold
 *   rcu_read_lock across iterate_dir because the latter may sleep).
 *   A process that forks/exits between windows could create a one-
 *   pass false signal — flagged but not actually hidden. Real-world
 *   detectors run multiple passes and intersect findings; the Stage
 *   3 version logs a single pass and documents the race in the
 *   writeup.
 *
 * Memory: GFP_ATOMIC for the rcu-locked phase 1; GFP_KERNEL inside
 * the iterate_dir actor (no rcu held there). On a typical Ubuntu
 * 24.04 system with ~200 processes, allocation count is in the
 * low hundreds.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/kernel.h>
#include <linux/list.h>
#include <linux/printk.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/slab.h>
#include <linux/string.h>

#include "detect_proc.h"

struct pid_entry {
	pid_t			pid;
	struct list_head	link;
};

static int pid_set_add(struct list_head *set, pid_t pid, gfp_t flags)
{
	struct pid_entry *e;

	e = kzalloc(sizeof(*e), flags);
	if (!e)
		return -ENOMEM;
	e->pid = pid;
	list_add(&e->link, set);
	return 0;
}

static void pid_set_free(struct list_head *set)
{
	struct pid_entry *e, *tmp;

	list_for_each_entry_safe(e, tmp, set, link) {
		list_del(&e->link);
		kfree(e);
	}
}

static bool pid_set_contains(struct list_head *set, pid_t pid)
{
	struct pid_entry *e;

	list_for_each_entry(e, set, link) {
		if (e->pid == pid)
			return true;
	}
	return false;
}

struct proc_collector {
	struct dir_context	ctx;
	struct list_head	*out;
	int			err;
};

static bool proc_collect_actor(struct dir_context *ctx, const char *name,
			       int namelen, loff_t offset, u64 ino,
			       unsigned int d_type)
{
	struct proc_collector *c =
		container_of(ctx, struct proc_collector, ctx);
	char buf[16];
	int pid;
	int i;

	if (namelen <= 0 || namelen >= (int)sizeof(buf))
		return true;

	/* PID directories in /proc/ have all-digit names. */
	for (i = 0; i < namelen; i++) {
		if (name[i] < '0' || name[i] > '9')
			return true;
	}

	memcpy(buf, name, namelen);
	buf[namelen] = '\0';
	if (kstrtoint(buf, 10, &pid) || pid <= 0)
		return true;

	if (pid_set_add(c->out, pid, GFP_KERNEL) < 0) {
		c->err = -ENOMEM;
		return false;
	}
	return true;
}

int lh_detect_proc_anomalies(void)
{
	LIST_HEAD(kernel_pids);
	LIST_HEAD(proc_pids);
	struct task_struct *task;
	struct file *file = NULL;
	struct pid_entry *e;
	struct proc_collector c;
	int count = 0;
	int ret = 0;

	pr_info("running process cross-view detection pass\n");

	/* Phase 1: kernel ground truth via for_each_process. */
	rcu_read_lock();
	for_each_process(task) {
		ret = pid_set_add(&kernel_pids, task_pid_nr(task), GFP_ATOMIC);
		if (ret < 0)
			break;
	}
	rcu_read_unlock();
	if (ret < 0) {
		pr_err("kernel pid set: %d\n", ret);
		goto out;
	}

	/* Phase 2: /proc view via iterate_dir. */
	file = filp_open("/proc", O_RDONLY | O_DIRECTORY, 0);
	if (IS_ERR(file)) {
		ret = PTR_ERR(file);
		file = NULL;
		pr_err("filp_open(/proc) failed: %d\n", ret);
		goto out;
	}

	c.ctx.actor = proc_collect_actor;
	c.ctx.pos = 0;
	c.out = &proc_pids;
	c.err = 0;

	ret = iterate_dir(file, &c.ctx);
	if (ret < 0) {
		pr_err("iterate_dir(/proc) failed: %d\n", ret);
		goto out;
	}
	if (c.err) {
		ret = c.err;
		pr_err("proc collector: %d\n", ret);
		goto out;
	}

	/* Phase 3: diff. */
	list_for_each_entry(e, &kernel_pids, link) {
		if (!pid_set_contains(&proc_pids, e->pid)) {
			pr_warn("process anomaly (cross-view): pid=%d in kernel task list but not in /proc/ enumeration\n",
				e->pid);
			count++;
		}
	}

	if (count == 0)
		pr_info("no process-concealment anomalies detected via cross-view\n");
	else
		pr_info("cross-view pass complete: %d flagged\n", count);

	ret = 0;
out:
	if (file)
		filp_close(file, NULL);
	pid_set_free(&kernel_pids);
	pid_set_free(&proc_pids);
	return ret;
}
