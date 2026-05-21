/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_DETECT_HOOKS_H
#define _LIGHTHOUSE_DETECT_HOOKS_H

/*
 * ftrace-hook integrity walker.
 *
 * Walks the kernel's registered ftrace_ops linked list (head:
 * kallsyms-resolved ftrace_ops_list; terminator: ftrace_list_end)
 * and flags any op whose .func pointer lives inside an out-of-tree
 * module — i.e. a kernel function is being redirected by a module-
 * owned handler.
 *
 * Catches what lh_detect_proc_anomalies() does NOT: rootkits that
 * hook at the syscall layer (or any layer below iterate_dir),
 * including shadowfox's Stage 3 default of __x64_sys_getdents64.
 * The signal here is "an out-of-tree module has an active ftrace
 * hook," not "PID X is hidden" — different shape, but it does
 * catch the specific rootkit.
 *
 * lighthouse's own ftrace_ops (if any are ever registered in future
 * stages) are skipped via a THIS_MODULE comparison.
 *
 * Returns 0 on success or a negative errno on resolver failure.
 *
 * Must be called in process context.
 */
int lh_detect_ftrace_hooks(void);

#endif /* _LIGHTHOUSE_DETECT_HOOKS_H */
