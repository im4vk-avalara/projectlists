#include "bridge.h"
#include "asm.h"
#include "pit.h"

#define COM2 0x2F8

#define FRAME_REQ  0
#define FRAME_RESP 1
#define FRAME_ERR  2

#define BRIDGE_TIMEOUT_TICKS 18000 /* ~180s at 100 Hz: a real model on CPU can be slow */

static const u8 MAGIC[4] = { 'A', 'I', 'O', 'S' };
static u16 tx_seq = 0;

/* ---- low-level COM2 (polled) ------------------------------------------ */

void bridge_init(void)
{
    outb(COM2 + 1, 0x00);   /* disable interrupts (we poll)        */
    outb(COM2 + 3, 0x80);   /* DLAB on                             */
    outb(COM2 + 0, 0x01);   /* divisor low  = 1 (115200 baud)      */
    outb(COM2 + 1, 0x00);   /* divisor high                        */
    outb(COM2 + 3, 0x03);   /* 8 bits, no parity, 1 stop, DLAB off */
    outb(COM2 + 2, 0xC7);   /* enable + clear FIFOs                */
    outb(COM2 + 4, 0x0B);   /* DTR, RTS, OUT2                      */
}

static void put_byte(u8 b)
{
    while (!(inb(COM2 + 5) & 0x20)) { /* wait for THR empty */ }
    outb(COM2, b);
}

/* Returns the byte (0..255) or -1 on timeout. */
static int get_byte(void)
{
    u32 deadline = timer_ticks() + BRIDGE_TIMEOUT_TICKS;
    while (!(inb(COM2 + 5) & 0x01)) {
        if (timer_ticks() >= deadline) return -1;
    }
    return inb(COM2);
}

/* ---- CRC-32 (IEEE, reflected, poly 0xEDB88320) ------------------------ */

static u32 crc32(const u8 *data, u32 len)
{
    u32 crc = 0xFFFFFFFFu;
    for (u32 i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++) {
            u32 mask = (crc & 1u) ? 0xEDB88320u : 0u;
            crc = (crc >> 1) ^ mask;
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

/* ---- framing ----------------------------------------------------------- */

static void send_frame(u8 type, const u8 *payload, u32 len)
{
    u32 crc = crc32(payload, len);
    for (int i = 0; i < 4; i++) put_byte(MAGIC[i]);
    put_byte(type);
    put_byte((u8)(tx_seq & 0xFF));
    put_byte((u8)(tx_seq >> 8));
    tx_seq++;
    put_byte((u8)(len & 0xFF));
    put_byte((u8)((len >> 8) & 0xFF));
    put_byte((u8)((len >> 16) & 0xFF));
    put_byte((u8)((len >> 24) & 0xFF));
    for (u32 i = 0; i < len; i++) put_byte(payload[i]);
    put_byte((u8)(crc & 0xFF));
    put_byte((u8)((crc >> 8) & 0xFF));
    put_byte((u8)((crc >> 16) & 0xFF));
    put_byte((u8)((crc >> 24) & 0xFF));
}

/* Receive a frame into buf. Returns payload length, or -1 on timeout/error.
 * On success, *type_out holds the frame type. */
static int recv_frame(u8 *type_out, u8 *buf, u32 max)
{
    int c;

    /* Resync to the 4-byte magic so a stray byte can't desync us forever. */
    int matched = 0;
    while (matched < 4) {
        c = get_byte();
        if (c < 0) return -1;
        if ((u8)c == MAGIC[matched]) {
            matched++;
        } else {
            matched = ((u8)c == MAGIC[0]) ? 1 : 0;
        }
    }

    c = get_byte(); if (c < 0) return -1;
    u8 type = (u8)c;

    int s0 = get_byte(), s1 = get_byte();          /* seq (ignored) */
    if (s0 < 0 || s1 < 0) return -1;

    int l0 = get_byte(), l1 = get_byte(), l2 = get_byte(), l3 = get_byte();
    if (l0 < 0 || l1 < 0 || l2 < 0 || l3 < 0) return -1;
    u32 len = (u32)l0 | ((u32)l1 << 8) | ((u32)l2 << 16) | ((u32)l3 << 24);

    if (len > max) return -1;                      /* desync rather than overflow */

    for (u32 i = 0; i < len; i++) {
        c = get_byte(); if (c < 0) return -1;
        buf[i] = (u8)c;
    }

    int x0 = get_byte(), x1 = get_byte(), x2 = get_byte(), x3 = get_byte();
    if (x0 < 0 || x1 < 0 || x2 < 0 || x3 < 0) return -1;
    u32 crc = (u32)x0 | ((u32)x1 << 8) | ((u32)x2 << 16) | ((u32)x3 << 24);

    if (crc != crc32(buf, len)) return -1;

    *type_out = type;
    return (int)len;
}

int bridge_request(const char *prompt, u32 prompt_len, char *out, u32 out_max)
{
    if (out_max == 0) return -1;

    send_frame(FRAME_REQ, (const u8 *)prompt, prompt_len);

    u8 type = 0;
    int n = recv_frame(&type, (u8 *)out, out_max - 1);
    if (n < 0) return -1;          /* timeout / framing error */
    out[n] = 0;
    if (type == FRAME_ERR) return -2;  /* bridge ran; backend failed (msg in out) */
    return n;
}
