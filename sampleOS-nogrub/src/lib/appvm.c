#include "app.h"
#include "string.h"
#include "printf.h"
#include "kbd.h"
#include "io.h"
#include "vfs.h"

#define APP_JSON_MAX 2048
#define APP_MAXVARS  12
#define APP_NAMELEN  16
#define APP_VALLEN   64
#define STEP_CAP     100000u

static char app_json[APP_JSON_MAX];
static char app_title[32];
static char app_id[33];
static int  app_fs_read, app_fs_write;   /* storage permissions (S7) */
static char var_name[APP_MAXVARS][APP_NAMELEN];
static char var_val[APP_MAXVARS][APP_VALLEN];
static int  n_vars;
static u32  step_budget;

/* Build "a b c d" (NULLs skipped) into dst, bounded. Used for VFS jail paths. */
static void make_path(char *dst, u32 max, const char *a, const char *b,
                      const char *c, const char *d)
{
    const char *parts[4] = { a, b, c, d };
    u32 i = 0;
    for (int k = 0; k < 4; k++) {
        const char *s = parts[k];
        while (s && *s && i + 1 < max) dst[i++] = *s++;
    }
    dst[i] = 0;
}

/* ===================== tiny JSON helpers ============================== */

static const char *skip_ws(const char *p)
{
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    return p;
}

static const char *find_sub(const char *h, const char *n)
{
    for (; *h; h++) {
        const char *a = h, *b = n;
        while (*a && *b && *a == *b) { a++; b++; }
        if (!*b) return h;
    }
    return 0;
}

/* Scalar value for "key" (quoted or bare) into out. 0 ok / -1 absent. */
static int json_scalar(const char *json, const char *key, char *out, u32 max)
{
    char pat[40];
    u32 k = 0;
    pat[k++] = '"';
    for (const char *p = key; *p && k < sizeof(pat) - 2; p++) pat[k++] = *p;
    pat[k++] = '"';
    pat[k] = 0;

    const char *q = find_sub(json, pat);
    if (!q) return -1;
    q = skip_ws(q + k);
    if (*q != ':') return -1;
    q = skip_ws(q + 1);

    u32 i = 0;
    if (*q == '"') {
        q++;
        while (*q && *q != '"' && i + 1 < max) out[i++] = *q++;
    } else {
        while (*q && *q != ',' && *q != '}' && *q != ' ' && i + 1 < max) out[i++] = *q++;
    }
    out[i] = 0;
    return 0;
}

/* Pointer to the '{' of the object value for "key", or NULL. */
static const char *find_object(const char *json, const char *key)
{
    char pat[24];
    u32 k = 0;
    pat[k++] = '"';
    for (const char *p = key; *p && k < sizeof(pat) - 2; p++) pat[k++] = *p;
    pat[k++] = '"';
    pat[k] = 0;

    const char *q = find_sub(json, pat);
    if (!q) return 0;
    q = skip_ws(q + k);
    if (*q != ':') return 0;
    q = skip_ws(q + 1);
    return (*q == '{') ? q : 0;
}

/* Iterate "k":"v" string members of an object. `p` starts at '{' or after a
 * member. Returns pointer past the member (for the next call) or NULL at end. */
static const char *next_member(const char *p, char *kbuf, u32 kmax, char *vbuf, u32 vmax)
{
    if (*p == '{') p++;
    p = skip_ws(p);
    while (*p == ',') p = skip_ws(p + 1);
    if (*p == '}' || *p == 0) return 0;
    if (*p != '"') return 0;
    p++;
    u32 i = 0;
    while (*p && *p != '"') { if (i + 1 < kmax) kbuf[i++] = *p; p++; }
    kbuf[i] = 0;
    if (*p == '"') p++;
    p = skip_ws(p);
    if (*p != ':') return 0;
    p = skip_ws(p + 1);
    i = 0;
    if (*p == '"') {
        p++;
        while (*p && *p != '"') { if (i + 1 < vmax) vbuf[i++] = *p; p++; }
        vbuf[i] = 0;
        if (*p == '"') p++;
    } else {
        while (*p && *p != ',' && *p != '}') { if (i + 1 < vmax) vbuf[i++] = *p; p++; }
        vbuf[i] = 0;
    }
    return p;
}

/* ===================== state vars ===================================== */

static int find_var(const char *name)
{
    for (int i = 0; i < n_vars; i++)
        if (strcmp(var_name[i], name) == 0) return i;
    return -1;
}

static const char *get_var(const char *name)
{
    int i = find_var(name);
    return (i >= 0) ? var_val[i] : "";
}

static void set_var(const char *name, const char *val)
{
    int i = find_var(name);
    if (i < 0) return;
    u32 j = 0;
    while (val[j] && j < APP_VALLEN - 1) { var_val[i][j] = val[j]; j++; }
    var_val[i][j] = 0;
}

/* ===================== calc(): integer arithmetic ===================== */

static int calc_expr(const char **p, int *err);

static int calc_factor(const char **p, int *err)
{
    *p = skip_ws(*p);
    int sign = 1;
    while (**p == '+' || **p == '-') { if (*(*p)++ == '-') sign = -sign; *p = skip_ws(*p); }
    if (**p == '(') {
        (*p)++;
        int v = calc_expr(p, err);
        *p = skip_ws(*p);
        if (**p == ')') (*p)++; else *err = 1;
        return sign * v;
    }
    if (**p < '0' || **p > '9') { *err = 1; return 0; }
    int v = 0;
    while (**p >= '0' && **p <= '9') { v = v * 10 + (**p - '0'); (*p)++; }
    return sign * v;
}

static int calc_term(const char **p, int *err)
{
    int v = calc_factor(p, err);
    for (;;) {
        *p = skip_ws(*p);
        char op = **p;
        if (op != '*' && op != '/') break;
        (*p)++;
        int r = calc_factor(p, err);
        if (op == '*') v *= r;
        else { if (r == 0) { *err = 1; return 0; } v /= r; }
    }
    return v;
}

static int calc_expr(const char **p, int *err)
{
    int v = calc_term(p, err);
    for (;;) {
        *p = skip_ws(*p);
        char op = **p;
        if (op != '+' && op != '-') break;
        (*p)++;
        int r = calc_term(p, err);
        v += (op == '+') ? r : -r;
    }
    return v;
}

static void itoa_(int v, char *out)
{
    char tmp[16];
    int i = 0, neg = (v < 0);
    unsigned uv = neg ? (unsigned)(-v) : (unsigned)v;
    if (uv == 0) tmp[i++] = '0';
    while (uv) { tmp[i++] = (char)('0' + uv % 10); uv /= 10; }
    int o = 0;
    if (neg) out[o++] = '-';
    while (i) out[o++] = tmp[--i];
    out[o] = 0;
}

/* ===================== action interpreter ============================= */

static void str_append(char *out, u32 max, const char *s)
{
    u32 o = 0;
    while (out[o]) o++;
    while (*s && o + 1 < max) out[o++] = *s++;
    out[o] = 0;
}

/* Evaluate an expression at *p into out. Stops at ';', ')', or end. */
static void eval_expr(const char **p, char key, char *out, u32 max, int *steps)
{
    out[0] = 0;
    for (;;) {
        if (--(*steps) < 0) { str_append(out, max, "!budget"); return; }
        *p = skip_ws(*p);
        char term[APP_VALLEN];
        term[0] = 0;

        if (**p == '\'') {                       /* 'string literal' */
            (*p)++;
            u32 i = 0;
            while (**p && **p != '\'' && i + 1 < sizeof(term)) term[i++] = *(*p)++;
            term[i] = 0;
            if (**p == '\'') (*p)++;
        } else if (**p >= '0' && **p <= '9') {   /* bare number literal */
            u32 i = 0;
            while (**p >= '0' && **p <= '9' && i + 1 < sizeof(term)) term[i++] = *(*p)++;
            term[i] = 0;
        } else if ((**p >= 'a' && **p <= 'z') || (**p >= 'A' && **p <= 'Z') || **p == '_') {
            char name[APP_NAMELEN];
            u32 i = 0;
            while (((**p >= 'a' && **p <= 'z') || (**p >= 'A' && **p <= 'Z') ||
                    (**p >= '0' && **p <= '9') || **p == '_') && i + 1 < sizeof(name))
                name[i++] = *(*p)++;
            name[i] = 0;
            const char *after = skip_ws(*p);
            if (*after == '(') {                  /* builtin call: 1 or 2 args */
                *p = after + 1;
                char a1[APP_VALLEN], a2[APP_VALLEN];
                eval_expr(p, key, a1, sizeof(a1), steps);
                a2[0] = 0;
                *p = skip_ws(*p);
                if (**p == ',') { (*p)++; eval_expr(p, key, a2, sizeof(a2), steps); *p = skip_ws(*p); }
                if (**p == ')') (*p)++;
                if (strcmp(name, "calc") == 0) {
                    const char *cp = a1;
                    int err = 0;
                    int v = calc_expr(&cp, &err);
                    cp = skip_ws(cp);
                    if (err || *cp) strcpy(term, "ERR");
                    else itoa_(v, term);
                } else if (strcmp(name, "to_str") == 0) {
                    strcpy(term, a1);
                } else if (strcmp(name, "len") == 0) {
                    itoa_((int)strlen(a1), term);
                } else if (strcmp(name, "fs_get") == 0) {
                    char path[96];
                    make_path(path, sizeof(path), "/apps/", app_id, "/data/", a1);
                    if (vfs_read(path, term, sizeof(term)) < 0) term[0] = 0;
                } else if (strcmp(name, "fs_put") == 0) {
                    char path[96];
                    make_path(path, sizeof(path), "/apps/", app_id, "/data/", a1);
                    vfs_write(path, a2, (u32)strlen(a2));
                    strcpy(term, a2);
                }
            } else if (strcmp(name, "key") == 0 || strcmp(name, "arg") == 0) {
                term[0] = key; term[1] = 0;
            } else {                              /* state variable */
                str_append(term, sizeof(term), get_var(name));
            }
        }

        str_append(out, max, term);
        *p = skip_ws(*p);
        if (**p == '+') { (*p)++; continue; }
        break;
    }
}

static void run_body(const char *body, char key)
{
    int steps = (int)step_budget;
    const char *p = body;
    while (*p) {
        p = skip_ws(p);
        char name[APP_NAMELEN];
        u32 i = 0;
        while (((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
                (*p >= '0' && *p <= '9') || *p == '_') && i + 1 < sizeof(name))
            name[i++] = *p++;
        name[i] = 0;
        p = skip_ws(p);
        if (*p != '=') break;
        p++;
        char val[APP_VALLEN];
        eval_expr(&p, key, val, sizeof(val), &steps);
        set_var(name, val);
        p = skip_ws(p);
        if (*p == ';') { p++; continue; }
        break;
    }
}

/* ===================== validation ===================================== */

static int is_ident_start(char c)
{
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}
static int is_ident_char(char c)
{
    return is_ident_start(c) || (c >= '0' && c <= '9');
}

/* Verify an action body uses only the bounded grammar: assignment to declared
 * vars; '+' concat; literals; builtins calc/to_str/len; 'key'/'arg'. Any other
 * identifier or character is rejected (this is the security gate). */
static int validate_action(const char *body, char *err, u32 errmax)
{
    const char *p = body;
    while (*p) {
        char c = *p;
        if (c == ' ' || c == '=' || c == '+' || c == ';' || c == '(' || c == ')' ||
            c == ',') {                       /* ',' separates fs_put's two args */
            p++;
        } else if (c == '\'') {                  /* string literal: skip */
            p++;
            while (*p && *p != '\'') p++;
            if (*p == '\'') p++;
        } else if (c >= '0' && c <= '9') {
            while (*p >= '0' && *p <= '9') p++;
        } else if (is_ident_start(c)) {
            char name[APP_NAMELEN];
            u32 i = 0;
            while (is_ident_char(*p) && i + 1 < sizeof(name)) name[i++] = *p++;
            name[i] = 0;
            const char *after = skip_ws(p);
            int ok;
            if (*after == '(') {
                ok = (strcmp(name, "calc") == 0 || strcmp(name, "to_str") == 0 ||
                      strcmp(name, "len") == 0 ||
                      (strcmp(name, "fs_get") == 0 && app_fs_read) ||
                      (strcmp(name, "fs_put") == 0 && app_fs_write));
            } else {
                ok = (strcmp(name, "key") == 0 || strcmp(name, "arg") == 0 ||
                      find_var(name) >= 0);
            }
            if (!ok) {
                u32 j = 0;
                for (const char *m = "illegal token: "; *m && j + 1 < errmax; m++) err[j++] = *m;
                for (u32 t = 0; name[t] && j + 1 < errmax; t++) err[j++] = name[t];
                err[j] = 0;
                return -1;
            }
        } else {
            u32 j = 0;
            for (const char *m = "illegal character in action"; *m && j + 1 < errmax; m++) err[j++] = *m;
            err[j] = 0;
            return -1;
        }
    }
    return 0;
}

/* ===================== load / render / key ============================ */

int app_looks_like(const char *s)
{
    return find_sub(s, "aios_app") != 0;
}

int app_load(const char *json, char *err, u32 errmax)
{
    char buf[24];

    if (json_scalar(json, "aios_app", buf, sizeof(buf)) < 0 || strcmp(buf, "1") != 0) {
        strcpy(err, "missing/bad aios_app version");
        return -1;
    }

    /* network can't be honored (no stack); fs_read/fs_write are honored via the
     * RAM VFS, jailed to /apps/<id>/data/ (default-deny if absent). */
    if (json_scalar(json, "network", buf, sizeof(buf)) == 0 && strcmp(buf, "true") == 0) {
        strcpy(err, "requests network permission (denied)");
        return -1;
    }
    app_fs_read  = (json_scalar(json, "fs_read",  buf, sizeof(buf)) == 0 && strcmp(buf, "true") == 0);
    app_fs_write = (json_scalar(json, "fs_write", buf, sizeof(buf)) == 0 && strcmp(buf, "true") == 0);

    const char *state = find_object(json, "state");
    const char *keys  = find_object(json, "keys");
    if (!state) { strcpy(err, "missing \"state\" object"); return -1; }
    if (!keys)  { strcpy(err, "missing \"keys\" object");  return -1; }

    /* keep our own copy; the app json is referenced while the app runs */
    u32 jl = 0;
    while (json[jl] && jl < APP_JSON_MAX - 1) { app_json[jl] = json[jl]; jl++; }
    app_json[jl] = 0;

    if (json_scalar(json, "title", app_title, sizeof(app_title)) < 0)
        strcpy(app_title, "app");
    if (json_scalar(json, "id", app_id, sizeof(app_id)) < 0 || app_id[0] == 0)
        strcpy(app_id, "app");

    u32 ms = 2000;
    if (json_scalar(json, "max_steps", buf, sizeof(buf)) == 0) {
        ms = 0;
        for (u32 i = 0; buf[i] >= '0' && buf[i] <= '9'; i++) ms = ms * 10 + (u32)(buf[i] - '0');
    }
    if (ms == 0 || ms > STEP_CAP) ms = STEP_CAP;   /* clamp */
    step_budget = ms;

    /* parse state vars (from our stored copy so pointers stay valid) */
    n_vars = 0;
    const char *st = find_object(app_json, "state");
    const char *p = st;
    char k[APP_NAMELEN], v[APP_VALLEN];
    while ((p = next_member(p, k, sizeof(k), v, sizeof(v))) != 0) {
        if (n_vars >= APP_MAXVARS) { strcpy(err, "too many state vars"); return -1; }
        strcpy(var_name[n_vars], k);
        u32 j = 0; while (v[j] && j < APP_VALLEN - 1) { var_val[n_vars][j] = v[j]; j++; }
        var_val[n_vars][j] = 0;
        n_vars++;
    }
    if (n_vars == 0) { strcpy(err, "no state vars"); return -1; }

    /* validate every action body against the bounded grammar */
    const char *ky = find_object(app_json, "keys");
    p = ky;
    while ((p = next_member(p, k, sizeof(k), v, sizeof(v))) != 0) {
        if (validate_action(v, err, errmax) < 0) return -1;
    }

    /* persist the validated app so it can be reopened without the model (S7) */
    {
        char path[80];
        make_path(path, sizeof(path), "/apps/", app_id, ".json", 0);
        vfs_write(path, app_json, (u32)strlen(app_json));
    }
    return 0;
}

/* TUI window geometry (fits 80x25). */
#define WIN_X 16
#define WIN_Y 4
#define WIN_W 48
#define WIN_H 17
#define COL_WIN   0x1F   /* white on blue   (body/border) */
#define COL_TITLE 0x70   /* black on grey   (title bar)   */
#define COL_KEY   0x1E   /* yellow on blue  (key hints)   */
#define COL_VAL   0x1F   /* white on blue   (fields)      */

void app_render(void)
{
    terminal_fill(WIN_X, WIN_Y, WIN_W, WIN_H, ' ', COL_WIN);
    terminal_box(WIN_X, WIN_Y, WIN_W, WIN_H, COL_WIN);

    /* title bar */
    terminal_fill(WIN_X + 1, WIN_Y + 1, WIN_W - 2, 1, ' ', COL_TITLE);
    char title[48];
    ksnprintf(title, sizeof(title), " %s", app_title);
    terminal_str_at(WIN_X + 2, WIN_Y + 1, title, COL_TITLE);

    /* state fields */
    for (int i = 0; i < n_vars && i < WIN_H - 6; i++) {
        char line[WIN_W - 3];
        ksnprintf(line, sizeof(line), "%s: %s", var_name[i], var_val[i]);
        terminal_str_at(WIN_X + 2, WIN_Y + 3 + i, line, COL_VAL);
    }

    /* key/button row near the bottom */
    char keys[WIN_W];
    u32 kl = 0;
    keys[kl++] = 'k'; keys[kl++] = 'e'; keys[kl++] = 'y'; keys[kl++] = 's';
    keys[kl++] = ':'; keys[kl++] = ' ';
    const char *p = find_object(app_json, "keys");
    char k[APP_NAMELEN], v[APP_VALLEN];
    while ((p = next_member(p, k, sizeof(k), v, sizeof(v))) != 0) {
        if (kl + 2 < sizeof(keys)) { keys[kl++] = k[0]; keys[kl++] = ' '; }
    }
    keys[kl] = 0;
    terminal_str_at(WIN_X + 2, WIN_Y + WIN_H - 3, keys, COL_KEY);
    terminal_str_at(WIN_X + 2, WIN_Y + WIN_H - 2, "Enter = exit", COL_WIN);
}

/* Compact state summary to a buffer (for tests / inspection). */
void app_state_summary(char *out, u32 max)
{
    out[0] = 0;
    u32 used = 0;
    for (int i = 0; i < n_vars; i++) {
        char line[APP_VALLEN + APP_NAMELEN + 4];
        ksnprintf(line, sizeof(line), "%s=%s ", var_name[i], var_val[i]);
        for (u32 j = 0; line[j] && used + 1 < max; j++) out[used++] = line[j];
    }
    out[used] = 0;
}

void app_key(char c)
{
    const char *p = find_object(app_json, "keys");
    char k[APP_NAMELEN], v[APP_VALLEN];
    while ((p = next_member(p, k, sizeof(k), v, sizeof(v))) != 0) {
        if (k[0] == c && k[1] == 0) {
            run_body(v, c);
            return;
        }
    }
    /* no binding for this key: ignore */
}

void app_run(const char *json)
{
    char err[80];
    if (app_load(json, err, sizeof(err)) < 0) {
        kprintf("[app] rejected: %s\n", err);
        return;
    }
    for (;;) {
        app_render();                 /* draws the TUI window */
        char c = kbd_getchar();
        if (c == '\n') break;
        app_key(c);
    }
    terminal_clear();                 /* wipe the window, hand the screen back */
    kprintf("[app] closed '%s'\n", app_title);
}
