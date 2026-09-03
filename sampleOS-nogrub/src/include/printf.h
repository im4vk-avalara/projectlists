#ifndef PRINTF_H
#define PRINTF_H

#include "types.h"

typedef __builtin_va_list va_list;
#define va_start(ap, last) __builtin_va_start(ap, last)
#define va_arg(ap, type)   __builtin_va_arg(ap, type)
#define va_end(ap)         __builtin_va_end(ap)
#define va_copy(d, s)      __builtin_va_copy(d, s)

int kprintf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
int kvprintf(const char *fmt, va_list ap);

/* Format into a buffer (NUL-terminated, bounded by cap). Like snprintf. */
int ksnprintf(char *buf, u32 cap, const char *fmt, ...) __attribute__((format(printf, 3, 4)));

#endif
