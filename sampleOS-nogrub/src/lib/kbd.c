#include "kbd.h"
#include "asm.h"
#include "idt.h"
#include "task.h"

#define KBD_DATA_PORT   0x60
#define KBD_STATUS_PORT 0x64
#define KBD_STATUS_OBF  0x01

#define KBD_BUF_SIZE 64
static volatile u8  kbd_buf[KBD_BUF_SIZE];
static volatile u32 kbd_head = 0;
static volatile u32 kbd_tail = 0;

static const char scancode_to_ascii[128] = {
    [0x02] = '1', [0x03] = '2', [0x04] = '3', [0x05] = '4', [0x06] = '5',
    [0x07] = '6', [0x08] = '7', [0x09] = '8', [0x0A] = '9', [0x0B] = '0',
    [0x0C] = '-', [0x0D] = '=', [0x0E] = '\b', [0x0F] = '\t',
    [0x10] = 'q', [0x11] = 'w', [0x12] = 'e', [0x13] = 'r', [0x14] = 't',
    [0x15] = 'y', [0x16] = 'u', [0x17] = 'i', [0x18] = 'o', [0x19] = 'p',
    [0x1A] = '[', [0x1B] = ']', [0x1C] = '\n',
    [0x1E] = 'a', [0x1F] = 's', [0x20] = 'd', [0x21] = 'f', [0x22] = 'g',
    [0x23] = 'h', [0x24] = 'j', [0x25] = 'k', [0x26] = 'l',
    [0x27] = ';', [0x28] = '\'', [0x29] = '`', [0x2B] = '\\',
    [0x2C] = 'z', [0x2D] = 'x', [0x2E] = 'c', [0x2F] = 'v', [0x30] = 'b',
    [0x31] = 'n', [0x32] = 'm', [0x33] = ',', [0x34] = '.', [0x35] = '/',
    [0x39] = ' ',
};

static const char scancode_to_ascii_shift[128] = {
    [0x02] = '!', [0x03] = '@', [0x04] = '#', [0x05] = '$', [0x06] = '%',
    [0x07] = '^', [0x08] = '&', [0x09] = '*', [0x0A] = '(', [0x0B] = ')',
    [0x0C] = '_', [0x0D] = '+', [0x0E] = '\b', [0x0F] = '\t',
    [0x10] = 'Q', [0x11] = 'W', [0x12] = 'E', [0x13] = 'R', [0x14] = 'T',
    [0x15] = 'Y', [0x16] = 'U', [0x17] = 'I', [0x18] = 'O', [0x19] = 'P',
    [0x1A] = '{', [0x1B] = '}', [0x1C] = '\n',
    [0x1E] = 'A', [0x1F] = 'S', [0x20] = 'D', [0x21] = 'F', [0x22] = 'G',
    [0x23] = 'H', [0x24] = 'J', [0x25] = 'K', [0x26] = 'L',
    [0x27] = ':', [0x28] = '"', [0x29] = '~', [0x2B] = '|',
    [0x2C] = 'Z', [0x2D] = 'X', [0x2E] = 'C', [0x2F] = 'V', [0x30] = 'B',
    [0x31] = 'N', [0x32] = 'M', [0x33] = '<', [0x34] = '>', [0x35] = '?',
    [0x39] = ' ',
};

static u8 modifier_state = 0;

int kbd_has_data(void)
{
    return kbd_head != kbd_tail;
}

u8 kbd_read_scancode(void)
{
    /* Cooperative: let background tasks run while the console waits for a
     * key; hlt afterwards so an empty rotation parks until the next IRQ
     * (PIT @ 100 Hz) instead of busy-spinning. */
    while (!kbd_has_data()) {
        task_yield();
        if (!kbd_has_data())
            __asm__ volatile ("hlt");
    }
    u8 sc = kbd_buf[kbd_tail];
    kbd_tail = (kbd_tail + 1) % KBD_BUF_SIZE;
    return sc;
}

static void kbd_irq(struct regs *r)
{
    (void)r;
    u8 sc = inb(KBD_DATA_PORT);
    u32 next = (kbd_head + 1) % KBD_BUF_SIZE;
    if (next != kbd_tail) {
        kbd_buf[kbd_head] = sc;
        kbd_head = next;
    }
}

void kbd_init(void)
{
    while (inb(KBD_STATUS_PORT) & KBD_STATUS_OBF) {
        (void)inb(KBD_DATA_PORT);
    }
    kbd_head = kbd_tail = 0;
    irq_install(1, kbd_irq);
}

char kbd_getchar(void)
{
    while (1) {
        u8 sc = kbd_read_scancode();
        u8 released = sc & 0x80;
        u8 code = sc & 0x7F;

        if (code == 0x2A) {
            if (released) modifier_state &= ~KBD_LSHIFT;
            else          modifier_state |=  KBD_LSHIFT;
            continue;
        }
        if (code == 0x36) {
            if (released) modifier_state &= ~KBD_RSHIFT;
            else          modifier_state |=  KBD_RSHIFT;
            continue;
        }

        if (released) {
            continue;
        }

        char c = (modifier_state & KBD_SHIFT)
            ? scancode_to_ascii_shift[code]
            : scancode_to_ascii[code];

        if (c) return c;
    }
}
