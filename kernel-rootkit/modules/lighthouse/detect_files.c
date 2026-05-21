// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: directory audit via iterate_dir.
 *
 * Opens a path with filp_open() and walks the directory via
 * iterate_dir(). Each entry is logged to dmesg at KERN_INFO. This
 * bypasses any rootkit hook on __x64_sys_getdents64 because
 * iterate_dir() invokes file->f_op->iterate_shared directly,
 * without going through the syscall entry point.
 *
 * Use case: user writes a path to /sys/kernel/debug/lighthouse/
 * audit-dir, lighthouse logs the true directory contents, the user
 * compares against userspace's `ls <path>` to surface anything
 * filtered out at the syscall layer.
 *
 * The Stage 7 test harness will turn this into an automated diff.
 * For now it is an honest audit tool whose limitation — "we cannot
 * see userspace's filtered view from kernel context" — is
 * documented up front.
 *
 * Verbose by design: every entry is logged. Spam is the cost of an
 * honest audit. Filter via `dmesg | grep "audit "` if needed.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/errno.h>
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/printk.h>

#include "detect_files.h"

struct audit_collector {
	struct dir_context	ctx;
	const char		*path;
	int			count;
};

static bool audit_actor(struct dir_context *ctx, const char *name,
			int namelen, loff_t offset, u64 ino,
			unsigned int d_type)
{
	struct audit_collector *c =
		container_of(ctx, struct audit_collector, ctx);

	pr_info("audit %s: name='%.*s' type=%u ino=%llu\n",
		c->path, namelen, name, d_type, ino);
	c->count++;
	return true;
}

int lh_audit_directory(const char *path)
{
	struct file *file;
	struct audit_collector c;
	int ret;

	pr_info("auditing directory %s (iterate_dir, bypasses syscall hook)\n",
		path);

	file = filp_open(path, O_RDONLY | O_DIRECTORY, 0);
	if (IS_ERR(file)) {
		ret = PTR_ERR(file);
		pr_err("filp_open(%s) failed: %d\n", path, ret);
		return ret;
	}

	c.ctx.actor = audit_actor;
	c.ctx.pos = 0;
	c.path = path;
	c.count = 0;

	ret = iterate_dir(file, &c.ctx);
	filp_close(file, NULL);

	if (ret < 0) {
		pr_err("iterate_dir(%s) failed: %d\n", path, ret);
		return ret;
	}

	pr_info("audit %s complete: %d entries (compare against userspace `ls %s`)\n",
		path, c.count, path);
	return 0;
}
