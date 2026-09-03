#include "printf.h"
#include "io.h"
#include "string.h"

/* Output sink: when cap_buf is set, formatting goes to that buffer (ksnprintf);
 * otherwise it goes to the terminal (kprintf). Single-threaded kernel, so a
 * static sink is fine. */
static char *cap_buf;
static u32   cap_cap, cap_len;

static void pc(char c)
{
    if (cap_buf) {
        if (cap_len + 1 < cap_cap) { cap_buf[cap_len++] = c; cap_buf[cap_len] = 0; }
    } else {
        terminal_putchar(c);
    }
}

static int emit_str(const char *s)
{
    int n = 0;
    while (*s) {
        pc(*s++);
        n++;
    }
    return n;
}

static int emit_uint(u32 value, u32 base, int uppercase, int min_digits)
{
    static const char digits_l[] = "0123456789abcdef";
    static const char digits_u[] = "0123456789ABCDEF";
    const char *digits = uppercase ? digits_u : digits_l;

    char buf[32];
    int i = 0;

    if (value == 0) {
        buf[i++] = '0';
    } else {
        while (value > 0) {
            buf[i++] = digits[value % base];
            value /= base;
        }
    }

    while (i < min_digits) {
        buf[i++] = '0';
    }

    int n = i;
    while (i > 0) {
        pc(buf[--i]);
    }
    return n;
}

static int emit_int(i32 value)
{
    int n = 0;
    u32 u;

    if (value < 0) {
        pc('-');
        n++;
        u = (u32)(-(value + 1)) + 1u;
    } else {
        u = (u32)value;
    }

    return n + emit_uint(u, 10, 0, 0);
}

int kvprintf(const char *fmt, va_list ap)
{
    int n = 0;

    while (*fmt) {
        if (*fmt != '%') {
            pc(*fmt++);
            n++;
            continue;
        }

        fmt++;
        switch (*fmt) {
        case '\0':
            return n;
        case '%':
            pc('%');
            n++;
            break;
        case 'c': {
            char c = (char)va_arg(ap, int);
            pc(c);
            n++;
            break;
        }
        case 's': {
            const char *s = va_arg(ap, const char *);
            if (!s) s = "(null)";
            n += emit_str(s);
            break;
        }
        case 'd':
        case 'i':
            n += emit_int(va_arg(ap, i32));
            break;
        case 'u':
            n += emit_uint(va_arg(ap, u32), 10, 0, 0);
            break;
        case 'x':
            n += emit_uint(va_arg(ap, u32), 16, 0, 0);
            break;
        case 'X':
            n += emit_uint(va_arg(ap, u32), 16, 1, 0);
            break;
        case 'p': {
            u32 v = (u32)(unsigned long)va_arg(ap, void *);
            n += emit_str("0x");
            n += emit_uint(v, 16, 0, 8);
            break;
        }
        default:
            pc('%');
            pc(*fmt);
            n += 2;
            break;
        }
        fmt++;
    }

    return n;
}

int kprintf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int n = kvprintf(fmt, ap);
    va_end(ap);
    return n;
}

int ksnprintf(char *buf, u32 cap, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    cap_buf = buf;
    cap_cap = cap;
    cap_len = 0;
    if (cap) buf[0] = 0;
    int n = kvprintf(fmt, ap);
    cap_buf = 0;                 /* back to terminal output */
    va_end(ap);
    return n;
}
