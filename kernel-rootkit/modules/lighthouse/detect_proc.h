/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_DETECT_PROC_H
#define _LIGHTHOUSE_DETECT_PROC_H

/*
 * Cross-view PID detector.
 *
 * Builds two sets of PIDs and diffs them:
 *
 *   - Kernel ground truth: for_each_process() walk, under RCU.
 *   - "Userspace view": iterate_dir() on /proc, capturing every
 *     directory entry whose name parses as a PID.
 *
 * A PID present in the kernel set but missing from the /proc set
 * has been hidden from /proc/ enumeration.
 *
 * KNOWN LIMITATION — kept on purpose for educational clarity:
 *
 *   This detector uses iterate_dir(), which is the VFS-level
 *   enumeration API. It calls file->f_op->iterate_shared directly,
 *   bypassing __x64_sys_getdents64. If a rootkit hooks the syscall
 *   path (shadowfox's Stage 3 default), this detector sees the
 *   true list and reports nothing. It catches rootkits that hook
 *   at the proc-filesystem layer (proc_pid_readdir or below). The
 *   paired detector lh_detect_ftrace_hooks() catches syscall-level
 *   hooks via a different signal.
 *
 * Returns 0 on success or a negative errno on internal failure.
 * Findings are logged at KERN_WARNING.
 *
 * Must be called in process context (sleeps in iterate_dir).
 */
int lh_detect_proc_anomalies(void);

#endif /* _LIGHTHOUSE_DETECT_PROC_H */
