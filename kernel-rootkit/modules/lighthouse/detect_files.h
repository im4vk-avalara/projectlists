/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_DETECT_FILES_H
#define _LIGHTHOUSE_DETECT_FILES_H

/*
 * Directory audit tool.
 *
 * lh_audit_directory(path) opens the given path with filp_open and
 * walks it via iterate_dir(), logging every directory entry to
 * dmesg at KERN_INFO. The returned list is what the VFS sees —
 * iterate_dir bypasses the __x64_sys_getdents64 syscall path, so
 * a rootkit that hooks getdents64 (shadowfox's Stage 3/4 default)
 * cannot filter these results.
 *
 * Intended use: trigger from userspace by writing the path to
 * /sys/kernel/debug/lighthouse/audit-dir, then in another shell
 * run `ls <path>` (which goes through the hooked syscall). Diff
 * the two outputs to surface anything hidden from userspace.
 *
 * This is an audit tool, not a self-contained detector. The Stage
 * 3 ftrace-ops walker (detect_hooks.c) continues to catch the
 * underlying syscall hook on every scan; the Stage 7 test harness
 * will eventually automate the diff.
 *
 * Must be called in process context (iterate_dir may sleep).
 *
 * Returns 0 on success or a negative errno (filp_open failure,
 * iterate_dir failure, etc.).
 */
int lh_audit_directory(const char *path);

#endif /* _LIGHTHOUSE_DETECT_FILES_H */
