#ifndef CONTROL_H
#define CONTROL_H

#include "types.h"

/*
 * Control-surface implementation: the actual kernel actions behind the AI's
 * verbs (S4 read + S5 mutating). Both the console dev commands (direct user
 * action) and the AI intent path call these. The verb *table* and validation
 * live in lib/intent.c; this module is the executors + the permission gate +
 * the audit log. See DESIGN.md §5/§10.
 */
void control_init(void);

/* kernel_ctl permission: required for the AI to run mutating verbs. Granted by
 * the USER at the console (/grant), never by the AI itself. Direct dev commands
 * are not gated -- the user at the console already has full authority. */
void control_grant(void);
void control_revoke(void);
int  control_granted(void);

/* Audit log of mutating actions the AI performed (record + print). */
void control_audit(const char *verb, const char *reason);
void control_audit_list(void);

/* Read verbs. */
void ctl_uptime(void);
void ctl_meminfo(void);
void ctl_ps(void);
int  ctl_peek(u32 addr);     /* guarded to the safe <4 MB identity map */
void ctl_peek_test(void);    /* dev: read the test vaddr (may page-fault) */
int  ctl_calc(const char *expr);  /* deterministic integer arithmetic (+ - * / and parens) */

/* Mutating verbs (caller checks permission first). Return 0 ok, -1 on failure. */
int ctl_map(void);
int ctl_unmap(void);
int ctl_alloc(void);
int ctl_free(void);
int ctl_frame(void);
int ctl_unframe(void);
int ctl_kill(u32 id);

#endif
