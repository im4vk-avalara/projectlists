#include "string.h"

void *memset(void *dst, int c, size_t n)
{
    u8 *d = (u8 *)dst;
    u8 v = (u8)c;

    while (n--) {
        *d++ = v;
    }
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
    u8 *d = (u8 *)dst;
    const u8 *s = (const u8 *)src;

    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    u8 *d = (u8 *)dst;
    const u8 *s = (const u8 *)src;

    if (d == s || n == 0) {
        return dst;
    }

    if (d < s) {
        while (n--) {
            *d++ = *s++;
        }
    } else {
        d += n;
        s += n;
        while (n--) {
            *--d = *--s;
        }
    }
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const u8 *p = (const u8 *)a;
    const u8 *q = (const u8 *)b;

    while (n--) {
        if (*p != *q) {
            return (int)*p - (int)*q;
        }
        p++;
        q++;
    }
    return 0;
}

size_t strlen(const char *s)
{
    size_t n = 0;
    while (s[n]) {
        n++;
    }
    return n;
}

int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (int)(u8)*a - (int)(u8)*b;
}

int strncmp(const char *a, const char *b, size_t n)
{
    while (n && *a && *a == *b) {
        a++;
        b++;
        n--;
    }
    if (n == 0) {
        return 0;
    }
    return (int)(u8)*a - (int)(u8)*b;
}

char *strcpy(char *dst, const char *src)
{
    char *p = dst;
    while ((*p++ = *src++)) {
    }
    return dst;
}
