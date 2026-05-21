// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: educational kernel detector module for the shadowfox +
 * lighthouse project. Stage 1 detects modules that have been hidden
 * from the kernel's "modules" linked list (the technique implemented
 * by shadowfox commit 2).
 *
 * This commit wires the detector in:
 *
 *   - One detection pass runs automatically on module load.
 *   - Further passes can be triggered any time by writing to
 *     /sys/kernel/debug/lighthouse/scan (the file content does not
 *     matter; any successful write triggers a pass).
 *
 * Detection logic lives in detect.c; symbol resolution in symbols.c.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/debugfs.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/limits.h>
#include <linux/module.h>
#include <linux/printk.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "detect.h"
#include "detect_cred.h"
#include "detect_files.h"
#include "detect_hooks.h"
#include "detect_proc.h"
#include "symbols.h"

static struct dentry *lh_debugfs_dir;

static ssize_t lh_scan_write(struct file *f, const char __user *ubuf,
			     size_t len, loff_t *off)
{
	int ret;

	ret = lh_detect_hidden_modules();
	if (ret < 0)
		return ret;

	ret = lh_detect_cred_anomalies();
	if (ret < 0)
		return ret;

	ret = lh_detect_proc_anomalies();
	if (ret < 0)
		return ret;

	ret = lh_detect_ftrace_hooks();
	if (ret < 0)
		return ret;

	return len;
}

static const struct file_operations lh_scan_fops = {
	.owner		= THIS_MODULE,
	.write		= lh_scan_write,
	.llseek		= no_llseek,
};

static ssize_t lh_audit_write(struct file *f, const char __user *ubuf,
			      size_t len, loff_t *off)
{
	char *buf;
	size_t n;
	int ret;

	if (len == 0)
		return 0;

	n = min(len, (size_t)PATH_MAX - 1);
	buf = kmalloc(n + 1, GFP_KERNEL);
	if (!buf)
		return -ENOMEM;

	if (copy_from_user(buf, ubuf, n)) {
		kfree(buf);
		return -EFAULT;
	}
	buf[n] = '\0';

	if (n > 0 && buf[n - 1] == '\n')
		buf[n - 1] = '\0';

	ret = lh_audit_directory(buf);
	kfree(buf);

	if (ret < 0)
		return ret;
	return len;
}

static const struct file_operations lh_audit_fops = {
	.owner		= THIS_MODULE,
	.write		= lh_audit_write,
	.llseek		= no_llseek,
};

static int __init lighthouse_init(void)
{
	struct dentry *scan;
	int ret;

	pr_info("loading (stage 1: detector)\n");

	ret = lh_symbols_init();
	if (ret < 0) {
		pr_err("symbol resolution failed: %d\n", ret);
		return ret;
	}

	lh_debugfs_dir = debugfs_create_dir(KBUILD_MODNAME, NULL);
	if (IS_ERR(lh_debugfs_dir)) {
		ret = PTR_ERR(lh_debugfs_dir);
		pr_err("debugfs_create_dir failed: %d\n", ret);
		return ret;
	}

	scan = debugfs_create_file("scan", 0200, lh_debugfs_dir, NULL,
				   &lh_scan_fops);
	if (IS_ERR(scan)) {
		ret = PTR_ERR(scan);
		pr_err("debugfs_create_file(scan) failed: %d\n", ret);
		debugfs_remove_recursive(lh_debugfs_dir);
		return ret;
	}

	{
		struct dentry *audit = debugfs_create_file("audit-dir", 0200,
							   lh_debugfs_dir, NULL,
							   &lh_audit_fops);
		if (IS_ERR(audit)) {
			ret = PTR_ERR(audit);
			pr_err("debugfs_create_file(audit-dir) failed: %d\n",
			       ret);
			debugfs_remove_recursive(lh_debugfs_dir);
			return ret;
		}
	}

	pr_info("loaded; running initial detection pass\n");
	/*
	 * Failure of the initial pass is logged inside each detector;
	 * it does not abort module init — debugfs is up and the user
	 * can retry by writing to /sys/kernel/debug/lighthouse/scan.
	 */
	lh_detect_hidden_modules();
	lh_detect_cred_anomalies();
	lh_detect_proc_anomalies();
	lh_detect_ftrace_hooks();
	pr_info("re-trigger via: echo 1 > /sys/kernel/debug/%s/scan\n",
		KBUILD_MODNAME);
	return 0;
}

static void __exit lighthouse_exit(void)
{
	debugfs_remove_recursive(lh_debugfs_dir);
	pr_info("unloading\n");
}

module_init(lighthouse_init);
module_exit(lighthouse_exit);

MODULE_LICENSE("GPL v2");
MODULE_AUTHOR("avinash.kumar");
MODULE_DESCRIPTION("Educational kernel concealment detector (lighthouse)");
MODULE_VERSION("0.5.0");
