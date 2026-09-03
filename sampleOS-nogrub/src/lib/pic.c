#include "pic.h"
#include "asm.h"

#define PIC1_CMD  0x20
#define PIC1_DATA 0x21
#define PIC2_CMD  0xA0
#define PIC2_DATA 0xA1

#define ICW1_INIT 0x11
#define ICW4_8086 0x01
#define PIC_EOI   0x20

void pic_init(void)
{
    outb(PIC1_CMD, ICW1_INIT); io_wait();
    outb(PIC2_CMD, ICW1_INIT); io_wait();

    outb(PIC1_DATA, PIC_VECTOR_BASE);     io_wait();
    outb(PIC2_DATA, PIC_VECTOR_BASE + 8); io_wait();

    outb(PIC1_DATA, 0x04); io_wait();
    outb(PIC2_DATA, 0x02); io_wait();

    outb(PIC1_DATA, ICW4_8086); io_wait();
    outb(PIC2_DATA, ICW4_8086); io_wait();

    outb(PIC1_DATA, 0xFF);
    outb(PIC2_DATA, 0xFF);
}

void pic_mask(u8 irq)
{
    u16 port = (irq < 8) ? PIC1_DATA : PIC2_DATA;
    u8 bit = irq & 7;
    outb(port, inb(port) | (u8)(1 << bit));
}

void pic_unmask(u8 irq)
{
    u16 port = (irq < 8) ? PIC1_DATA : PIC2_DATA;
    u8 bit = irq & 7;
    outb(port, inb(port) & (u8)~(1 << bit));

    if (irq >= 8) {
        outb(PIC1_DATA, inb(PIC1_DATA) & (u8)~(1 << 2));
    }
}

void pic_eoi(u8 irq)
{
    if (irq >= 8) {
        outb(PIC2_CMD, PIC_EOI);
    }
    outb(PIC1_CMD, PIC_EOI);
}
