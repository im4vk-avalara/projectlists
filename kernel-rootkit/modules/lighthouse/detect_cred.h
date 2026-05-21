/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LIGHTHOUSE_DETECT_CRED_H
#define _LIGHTHOUSE_DETECT_CRED_H

/*
 * Walk all tasks under RCU and flag any task whose cred->uid is the
 * root UID while task->loginuid is a real non-root user (i.e. a real
 * user logged in via PAM/audit, but the task now runs as root with
 * no audit record of the transition).
 *
 * Known false positives — kept on purpose for Stage 2:
 *
 *   sudo, su, login children all have cred->uid == 0 with the
 *   original user's loginuid. A real detector walks
 *   task->mm->exe_file to verify the elevation came from a setuid-
 *   root binary; this detector does not. The false positives are
 *   themselves the teaching moment of the technique writeup.
 *
 * Returns 0 on success or a negative errno on internal failure.
 * The count of flagged tasks is logged, not returned.
 *
 * Must be called in process context.
 */
int lh_detect_cred_anomalies(void);

#endif /* _LIGHTHOUSE_DETECT_CRED_H */
