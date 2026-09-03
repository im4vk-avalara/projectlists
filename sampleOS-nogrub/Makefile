# AIOS build. All generated files live under build/ ; sources under src/.
#
#   src/boot/     bootloader.s, loader.s, link.ld
#   src/kernel/   kernelmain.c
#   src/lib/      kernel library (drivers, mm, AI bridge/intent/app vm)
#   src/include/  headers
#   host/         host-side AI bridge (not part of the image)
#   build/        *.o *.d *.bin *.elf *.img *.log  (git-ignored; `make clean` nukes it)

# ---- generated artifacts -------------------------------------------------
BUILD      = build
IMG        = $(BUILD)/AIOS.img
BOOTLOADER = $(BUILD)/bootloader.bin
KERNEL_ELF = $(BUILD)/kernel.elf
KERNEL_BIN = $(BUILD)/kernel.bin
LOG        = $(BUILD)/aios.log

# ---- source locations ----------------------------------------------------
VPATH      = src/boot src/kernel src/lib
INCLUDE    = src/include
LINKSCRIPT = src/boot/link.ld

# ---- QEMU ----------------------------------------------------------------
QEMU = qemu-system-i386
QEMU_FLAGS = -drive format=raw,file=$(IMG) \
             -chardev stdio,id=ch0,logfile=$(LOG),signal=off \
             -serial chardev:ch0

# AI bridge on COM2 (start host/ai-bridge/bridge.py first; QEMU is the client).
AI_SOCK = /tmp/aios-ai.sock
QEMU_AI_FLAGS = -chardev socket,id=ai,path=$(AI_SOCK),server=off \
                -serial chardev:ai

# ---- toolchain (overridden for the Docker cross-toolchain) ---------------
CC = i686-elf-gcc
AS = i686-elf-as
LD = i686-elf-ld
OBJCOPY = i686-elf-objcopy

CFLAGS = -std=gnu99 -ffreestanding -O2 -Wall -Wextra \
         -I$(INCLUDE) -MMD -MP -fno-pic -fno-pie -fno-stack-protector
LDFLAGS = -T $(LINKSCRIPT) -nostdlib

# ---- object list (names only; resolved via VPATH, emitted into build/) ---
KOBJS = loader kernelmain io string printf kbd idt isr pic pit paging \
        e820 frame kmalloc gdt usermode syscall usertest bridge intent control \
        appvm vfs task taskswitch

ifeq ($(DEMO),1)
    CFLAGS += -DDEMO_BUILD
    AS_FLAGS_BOOT = --defsym DEMO=1
    KOBJS += fb anim
endif

KERNEL_OBJS = $(addprefix $(BUILD)/,$(addsuffix .o,$(KOBJS)))
DEPS = $(KERNEL_OBJS:.o=.d)

# ---- Docker cross-toolchain ----------------------------------------------
DOCKER_IMAGE = aios-toolchain
DOCKER_RUN = docker run --rm -u $(shell id -u):$(shell id -g) -v "$(CURDIR)":/src $(DOCKER_IMAGE)
DOCKER_MAKE_FLAGS = CC=i686-linux-gnu-gcc AS=i686-linux-gnu-as LD=i686-linux-gnu-ld OBJCOPY=i686-linux-gnu-objcopy

.PHONY: all clean run run-ai docker-image docker-build docker-clean \
        docker-run docker-run-ai docker-build-demo docker-run-demo

all: $(IMG)

$(BUILD):
	mkdir -p $(BUILD)

$(BOOTLOADER): src/boot/bootloader.s | $(BUILD)
	$(AS) $(AS_FLAGS_BOOT) src/boot/bootloader.s -o $(BUILD)/bootloader.o
	$(LD) -Ttext 0x7C00 --oformat binary -o $(BOOTLOADER) $(BUILD)/bootloader.o

$(KERNEL_ELF): $(KERNEL_OBJS) $(LINKSCRIPT)
	$(LD) $(LDFLAGS) -o $(KERNEL_ELF) $(KERNEL_OBJS)

$(KERNEL_BIN): $(KERNEL_ELF)
	$(OBJCOPY) -O binary $(KERNEL_ELF) $(KERNEL_BIN)

$(BUILD)/%.o: %.s | $(BUILD)
	$(AS) $< -o $@

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(IMG): $(BOOTLOADER) $(KERNEL_BIN) | $(BUILD)
	dd if=/dev/zero of=$(IMG) bs=512 count=2880
	dd if=$(BOOTLOADER) of=$(IMG) bs=512 count=1 conv=notrunc
	dd if=$(KERNEL_BIN) of=$(IMG) bs=512 seek=1 conv=notrunc

run: $(IMG)
	$(QEMU) $(QEMU_FLAGS)

# Re-run last image with the AI bridge on COM2 (start bridge.py first).
run-ai: $(IMG)
	$(QEMU) $(QEMU_FLAGS) $(QEMU_AI_FLAGS)

clean:
	rm -rf $(BUILD)

docker-image:
	docker build -t $(DOCKER_IMAGE) -f Dockerfile .

docker-build: docker-image
	$(DOCKER_RUN) make $(DOCKER_MAKE_FLAGS)

docker-clean:
	rm -rf $(BUILD)

docker-run: docker-build
	$(QEMU) $(QEMU_FLAGS)

# Build in Docker, then run with the AI bridge on COM2 (start bridge.py first).
docker-run-ai: docker-build
	$(QEMU) $(QEMU_FLAGS) $(QEMU_AI_FLAGS)

docker-build-demo: docker-image
	$(DOCKER_RUN) make clean
	$(DOCKER_RUN) make $(DOCKER_MAKE_FLAGS) DEMO=1

docker-run-demo: docker-build-demo
	$(QEMU) $(QEMU_FLAGS)

-include $(DEPS)
