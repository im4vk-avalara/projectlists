// SPDX-License-Identifier: GPL-2.0
/*
 * lighthouse: cred-anomaly detector.
 *
 * Detects tasks running as UID 0 whose loginuid does not match —
 * the classical signal of in-kernel privilege escalation that
 * bypasses the audit subsystem. commit_creds() swaps a task's
 * struct cred but never touches task->loginuid, which is only
 * updated by audit via PAM/login. A task whose cred->uid disagrees
 * with its loginuid is either:
 *
 *   (a) a legitimate setuid-root exec descendant (sudo, su, login,
 *       a setuid binary), in which case the elevation is audit-
 *       trail-justifiable but does not show up in this cheap signal;
 *
 *   (b) an in-kernel cred-swap (what shadowfox does), in which case
 *       no audit trail exists at all.
 *
 * Stage 2 reports both with the same warning line. Distinguishing
 * (a) from (b) requires walking task->mm->exe_file and checking the
 * inode for setuid-root bits, which depends on the file/inode work
 * that belongs to Stage 4. The educational value of the unfiltered
 * signal is that it surfaces a real surveillance trade-off.
 *
 * Locking: rcu_read_lock() is sufficient for read-only iteration of
 * for_each_process() and for the __task_cred() dereference. We do
 * not take tasklist_lock — that is for mutators.
 *
 * Performance: a few hundred tasks on a typical Ubuntu 24.04 system,
 * two kuid_eq() comparisons each. Microseconds.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/audit.h>
#include <linux/cred.h>
#include <linux/printk.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/uidgid.h>

#include "detect_cred.h"

int lh_detect_cred_anomalies(void)
{
	struct task_struct *task;
	int count = 0;

	pr_info("running cred-anomaly detection pass\n");

	rcu_read_lock();
	for_each_process(task) {
		const struct cred *c = __task_cred(task);
		kuid_t uid;
		kuid_t loginuid;

		if (!c)
			continue;

		uid = c->uid;
		loginuid = audit_get_loginuid(task);

		/*
		 * Anomaly: cred says root, but the audit-set loginuid is
		 * a real non-root user. Either a setuid-root exec or an
		 * in-kernel cred swap; we cannot tell from this signal
		 * alone.
		 */
		if (uid_eq(uid, GLOBAL_ROOT_UID) &&
		    !uid_eq(loginuid, INVALID_UID) &&
		    !uid_eq(loginuid, GLOBAL_ROOT_UID)) {
			pr_warn("cred anomaly: pid=%d comm=%s uid=0 loginuid=%u (sudo/su or in-kernel escalation)\n",
				task->pid, task->comm,
				from_kuid(&init_user_ns, loginuid));
			count++;
		}
	}
	rcu_read_unlock();

	if (count == 0)
		pr_info("no cred anomalies detected\n");
	else
		pr_info("cred-anomaly pass complete: %d flagged\n", count);

	return 0;
}
