#include "vfs.h"
#include "kmalloc.h"
#include "string.h"

#define VFS_MAX_FILES 32
#define VFS_NAME      64
#define VFS_FILE_CAP  4096          /* per-file cap */
#define VFS_TOTAL_CAP (64 * 1024)   /* total cap (shares the 256 KB heap) */

struct vfile {
    char  name[VFS_NAME];
    char *data;
    u32   len;
    int   used;
};

static struct vfile vf[VFS_MAX_FILES];
static u32 vfs_total;

void vfs_init(void)
{
    for (int i = 0; i < VFS_MAX_FILES; i++) {
        vf[i].used = 0;
        vf[i].data = 0;
        vf[i].len = 0;
    }
    vfs_total = 0;
}

static struct vfile *find(const char *path)
{
    for (int i = 0; i < VFS_MAX_FILES; i++)
        if (vf[i].used && strcmp(vf[i].name, path) == 0)
            return &vf[i];
    return 0;
}

int vfs_write(const char *path, const char *data, u32 len)
{
    if (len > VFS_FILE_CAP || strlen(path) >= VFS_NAME)
        return -1;

    struct vfile *f = find(path);
    u32 oldlen = f ? f->len : 0;
    if (vfs_total - oldlen + len > VFS_TOTAL_CAP)
        return -1;

    if (!f) {
        for (int i = 0; i < VFS_MAX_FILES; i++)
            if (!vf[i].used) { f = &vf[i]; break; }
        if (!f) return -1;                 /* file table full */
    }

    char *buf = (char *)kmalloc(len ? len : 1);
    if (!buf) return -1;
    memcpy(buf, data, len);

    if (f->used) {
        kfree(f->data);                    /* overwrite existing */
    } else {
        f->used = 1;
        strcpy(f->name, path);
    }
    f->data = buf;
    f->len = len;
    vfs_total = vfs_total - oldlen + len;
    return 0;
}

int vfs_read(const char *path, char *out, u32 max)
{
    if (max == 0) return -1;
    struct vfile *f = find(path);
    if (!f) return -1;
    u32 n = f->len;
    if (n > max - 1) n = max - 1;
    memcpy(out, f->data, n);
    out[n] = 0;
    return (int)n;
}

int vfs_exists(const char *path)
{
    return find(path) != 0;
}

void vfs_list(const char *prefix, void (*cb)(const char *path))
{
    u32 plen = (u32)strlen(prefix);
    for (int i = 0; i < VFS_MAX_FILES; i++) {
        if (vf[i].used && strncmp(vf[i].name, prefix, plen) == 0)
            cb(vf[i].name);
    }
}
