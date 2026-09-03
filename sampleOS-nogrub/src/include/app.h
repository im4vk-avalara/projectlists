#ifndef APP_H
#define APP_H

#include "types.h"

/*
 * S6: AI-generated app runtime + validator (interpreter-based sandbox).
 *
 * Apps are declarative DSL data, never code. Format (keymap-based so it parses
 * without arrays-of-objects):
 *
 *   {
 *     "aios_app":"1", "id":"calculator", "title":"Calculator",
 *     "permissions":{"fs_write":false,"network":false},
 *     "limits":{"max_steps":2000},
 *     "state":{"input":"","result":"0"},
 *     "keys":{ "7":"input=input+'7'", "=":"result=calc(input)", "c":"input='';result='0'" }
 *   }
 *
 * Action bodies are a bounded expression language: assignment to declared state
 * vars; '+' string concat; literals; the builtins calc()/to_str()/len(); and
 * 'key'. No loops, recursion, raw memory, or syscalls are expressible, and a
 * max_steps budget bounds every action. The validator rejects anything else.
 * See DESIGN.md §5/§6/§7/§10.
 */

/* 1 if the text looks like an app definition (contains the aios_app tag). */
int app_looks_like(const char *s);

/* Validate + load an app. Returns 0 on success, -1 if rejected (err filled). */
int app_load(const char *json, char *err, u32 errmax);

/* Render the loaded app as a TUI window (positioned, colored). */
void app_render(void);

/* Feed a keypress to the loaded app (runs the bound action, if any). */
void app_key(char c);

/* Compact "var=val ..." summary of the loaded app's state (for tests). */
void app_state_summary(char *out, u32 max);

/* Validate + load + run interactively (reads the keyboard) until Enter. */
void app_run(const char *json);

#endif
