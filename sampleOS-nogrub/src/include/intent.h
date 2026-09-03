#ifndef INTENT_H
#define INTENT_H

#include "types.h"

/*
 * AI control surface (S4: read-only verbs).
 *
 * The model may emit an *intent* as JSON data (never code):
 *   {"aios_intent":"1","verb":"meminfo","args":{},"reason":"..."}
 *
 * The kernel validates it against an enumerable, human-authored verb table and
 * executes only known, in-range verbs. Anything else is rejected -- the kernel
 * never acts on free-form model output. See DESIGN.md §5.
 *
 * S4 verbs are all read-only: uptime, meminfo, ps, peek (mutating verbs +
 * kernel_ctl permission arrive in S5).
 */

/* 1 if the text looks like an intent (contains the aios_intent tag). */
int intent_looks_like(const char *s);

/* Parse + validate + execute an intent, printing the result via kprintf.
 * Returns 0 on success, -1 if rejected (a reason is printed). */
int intent_execute(const char *json);

#endif
