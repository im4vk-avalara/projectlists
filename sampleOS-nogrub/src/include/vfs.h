#ifndef VFS_H
#define VFS_H

#include "types.h"

/*
 * S7: a tiny in-RAM filesystem (a flat map of path -> blob, kmalloc-backed).
 * Durable within a boot, NOT across reboots (that needs a disk driver). Used to
 * save generated app definitions (/apps/<id>.json) and per-app key-value data
 * (/apps/<id>/data/<key>). Bounded so it can't exhaust the heap.
 */
void vfs_init(void);

/* Write (create or overwrite). Returns 0 on success, -1 on error/limit. */
int  vfs_write(const char *path, const char *data, u32 len);

/* Read into out (NUL-terminated). Returns length, or -1 if absent. */
int  vfs_read(const char *path, char *out, u32 max);

int  vfs_exists(const char *path);

/* Call cb(path) for every file whose path starts with `prefix`. */
void vfs_list(const char *prefix, void (*cb)(const char *path));

#endif
