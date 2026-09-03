#include "intent.h"
#include "string.h"
#include "printf.h"
#include "control.h"
#include "app.h"
#include "vfs.h"
#include "bridge.h"

/* ---- tiny JSON helpers (only what the intent schema needs) ------------ */

static const char *find_sub(const char *h, const char *n)
{
    for (; *h; h++) {
        const char *a = h, *b = n;
        while (*a && *b && *a == *b) { a++; b++; }
        if (!*b) return h;
    }
    return 0;
}

/* Extract the value for "key" into out. Handles both "quoted" and bare tokens.
 * Returns 0 on success, -1 if the key is absent / malformed. */
static int json_value(const char *json, const char *key, char *out, u32 max)
{
    char pat[40];
    u32 k = 0;
    pat[k++] = '"';
    for (const char *p = key; *p && k < sizeof(pat) - 2; p++) pat[k++] = *p;
    pat[k++] = '"';
    pat[k] = 0;

    const char *q = find_sub(json, pat);
    if (!q) return -1;
    q += k;

    while (*q == ' ' || *q == '\t' || *q == '\n') q++;
    if (*q != ':') return -1;
    q++;
    while (*q == ' ' || *q == '\t' || *q == '\n') q++;

    u32 i = 0;
    if (*q == '"') {
        q++;
        while (*q && *q != '"' && i + 1 < max) out[i++] = *q++;
    } else {
        while (*q && *q != ',' && *q != '}' && *q != ' ' && *q != '\n' && i + 1 < max)
            out[i++] = *q++;
    }
    out[i] = 0;
    return 0;
}

static u32 parse_u32(const char *s)
{
    u32 v = 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        s += 2;
        for (;;) {
            char c = *s++;
            u32 d;
            if (c >= '0' && c <= '9') d = (u32)(c - '0');
            else if (c >= 'a' && c <= 'f') d = (u32)(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') d = (u32)(c - 'A' + 10);
            else break;
            v = v * 16 + d;
        }
    } else {
        while (*s >= '0' && *s <= '9') { v = v * 10 + (u32)(*s - '0'); s++; }
    }
    return v;
}

/* ---- control surface --------------------------------------------------- */

int intent_looks_like(const char *s)
{
    return find_sub(s, "aios_intent") != 0;
}

static int verb_is_mutating(const char *v)
{
    return strcmp(v, "map") == 0 || strcmp(v, "unmap") == 0
        || strcmp(v, "alloc") == 0 || strcmp(v, "free") == 0
        || strcmp(v, "frame") == 0 || strcmp(v, "unframe") == 0
        || strcmp(v, "kill") == 0;
}

/* Print one saved-app id for the `apps` verb (skips /apps/<id>/data/<key>). */
static void app_list_cb(const char *path)
{
    const char *id = path + 6;            /* skip "/apps/" */
    for (const char *c = id; *c; c++)
        if (*c == '/') return;            /* a /data/ file, not an app def */
    char name[40];
    u32 i = 0;
    for (const char *c = id; *c && *c != '.' && i < sizeof(name) - 1; c++)
        name[i++] = *c;                   /* strip ".json" */
    name[i] = 0;
    kprintf("[ai]   %s\n", name);
}

int intent_execute(const char *json)
{
    char ver[8], verb[24], reason[64], arg[20];

    if (json_value(json, "aios_intent", ver, sizeof(ver)) < 0 || strcmp(ver, "1") != 0) {
        kprintf("[intent] rejected: missing/bad \"aios_intent\" version\n");
        return -1;
    }
    if (json_value(json, "verb", verb, sizeof(verb)) < 0) {
        kprintf("[intent] rejected: missing \"verb\"\n");
        return -1;
    }
    if (json_value(json, "reason", reason, sizeof(reason)) < 0) reason[0] = 0;

    /* conversational narration: the model's one-sentence reply, shown first */
    char say[160];
    if (json_value(json, "say", say, sizeof(say)) == 0 && say[0])
        kprintf("[ai] %s\n", say);

    kprintf("[intent] verb=%s\n", verb);

    /* Read-only verbs: always allowed. */
    if (strcmp(verb, "uptime") == 0)  { ctl_uptime();  return 0; }
    if (strcmp(verb, "meminfo") == 0) { ctl_meminfo(); return 0; }
    if (strcmp(verb, "ps") == 0)      { ctl_ps();      return 0; }
    if (strcmp(verb, "peek") == 0) {
        if (json_value(json, "addr", arg, sizeof(arg)) < 0) {
            kprintf("[intent] rejected: peek needs args.addr\n");
            return -1;
        }
        return ctl_peek(parse_u32(arg));
    }
    if (strcmp(verb, "calc") == 0) {
        char expr[80];
        if (json_value(json, "expr", expr, sizeof(expr)) < 0) {
            /* fallback: the model sometimes emits {"a","b","op"} */
            char a[24], b[24], op[8];
            op[0] = 0;
            if (json_value(json, "a", a, sizeof(a)) == 0 &&
                json_value(json, "b", b, sizeof(b)) == 0) {
                json_value(json, "op", op, sizeof(op));
                char sym = '+';
                if (op[0] == 's' || op[0] == '-') sym = '-';
                else if (op[0] == 'm' || op[0] == '*') sym = '*';
                else if (op[0] == 'd' || op[0] == '/') sym = '/';
                u32 i = 0, j = 0;
                while (a[j] && i < sizeof(expr) - 3) expr[i++] = a[j++];
                expr[i++] = sym;
                j = 0;
                while (b[j] && i < sizeof(expr) - 1) expr[i++] = b[j++];
                expr[i] = 0;
            } else {
                kprintf("[intent] rejected: calc needs args.expr\n");
                return -1;
            }
        }
        return ctl_calc(expr);
    }
    if (strcmp(verb, "apps") == 0) {           /* list saved apps */
        kprintf("[ai] saved apps:\n");
        vfs_list("/apps/", app_list_cb);
        return 0;
    }
    if (strcmp(verb, "open") == 0) {           /* relaunch a saved app (no model) */
        char id[33];
        if (json_value(json, "id", id, sizeof(id)) < 0) {
            kprintf("[intent] rejected: open needs args.id\n");
            return -1;
        }
        char path[80];
        u32 i = 0;
        for (const char *s = "/apps/"; *s; s++) path[i++] = *s;
        for (const char *s = id; *s && i < sizeof(path) - 6; s++) path[i++] = *s;
        for (const char *s = ".json"; *s; s++) path[i++] = *s;
        path[i] = 0;
        static char appbuf[2048];
        if (vfs_read(path, appbuf, sizeof(appbuf)) < 0) {
            kprintf("[ai] no saved app '%s' (try the 'apps' verb)\n", id);
            return -1;
        }
        app_run(appbuf);                       /* interactive; returns on Enter */
        return 0;
    }
    if (strcmp(verb, "fix") == 0) {            /* self-healing: AI repairs an app */
        char id[33], problem[160];
        if (json_value(json, "id", id, sizeof(id)) < 0) {
            kprintf("[intent] rejected: fix needs args.id\n");
            return -1;
        }
        if (json_value(json, "problem", problem, sizeof(problem)) < 0) problem[0] = 0;

        char path[80];
        u32 i = 0;
        for (const char *s = "/apps/"; *s; s++) path[i++] = *s;
        for (const char *s = id; *s && i < sizeof(path) - 6; s++) path[i++] = *s;
        for (const char *s = ".json"; *s; s++) path[i++] = *s;
        path[i] = 0;

        static char cur[2048];
        if (vfs_read(path, cur, sizeof(cur)) < 0) {
            kprintf("[ai] no saved app '%s' to fix\n", id);
            return -1;
        }

        /* hand the AI the *actual* current definition + the reported problem */
        static char prompt[3072];
        ksnprintf(prompt, sizeof(prompt),
            "Here is an AIOS app definition:\n%s\nThe user reports this problem: %s\n"
            "Output ONLY the corrected app JSON (same aios_app format), fixing the "
            "issue. No commentary, no markdown.",
            cur, problem);

        static char patched[2048];
        int n = bridge_request(prompt, (u32)strlen(prompt), patched, sizeof(patched));
        if (n <= 0) { kprintf("[ai] fix failed (no reply from model)\n"); return -1; }

        char err[80];
        if (app_looks_like(patched) && app_load(patched, err, sizeof(err)) == 0) {
            kprintf("[ai] fixed '%s' -- relaunching it.\n", id);
            app_run(patched);                  /* validated patch auto-saved + run */
            return 0;
        }
        kprintf("[ai] couldn't apply a valid fix: %s\n",
                app_looks_like(patched) ? err : "model returned no app");
        return -1;
    }

    /* Mutating verbs: require user-granted kernel_ctl (the AI can't self-grant). */
    if (verb_is_mutating(verb)) {
        if (!control_granted()) {
            kprintf("[intent] rejected: '%s' needs kernel_ctl -- the user must type "
                    "/grant at the console\n", verb);
            return -1;
        }
        control_audit(verb, reason);   /* record + print before acting */

        if (strcmp(verb, "map") == 0)     return ctl_map();
        if (strcmp(verb, "unmap") == 0)   return ctl_unmap();
        if (strcmp(verb, "alloc") == 0)   return ctl_alloc();
        if (strcmp(verb, "free") == 0)    return ctl_free();
        if (strcmp(verb, "frame") == 0)   return ctl_frame();
        if (strcmp(verb, "unframe") == 0) return ctl_unframe();
        if (strcmp(verb, "kill") == 0) {
            u32 id = 0;
            if (json_value(json, "id", arg, sizeof(arg)) >= 0) id = parse_u32(arg);
            return ctl_kill(id);
        }
    }

    kprintf("[intent] rejected: unknown verb '%s'\n", verb);
    return -1;
}
