# =============================================================================
#  PYRO OS - Makefile
#  -----------------------------------------------------------------------------
#  Build:  make                # produces build/pyro.img (1.44 MB floppy)
#  Run  :  make run            # boots it in QEMU
#  Run+ :  make debug          # boots with GDB stub on :1234, waits to attach
#  Clean:  make clean
#
#  NASM lives in a Docker image (no host install needed). QEMU is expected to
#  be installed locally (it already was on this machine).
# =============================================================================

PROJ_DIR  := $(shell pwd)
BUILD_DIR := build
SRC_DIR   := src

BOOT_BIN  := $(BUILD_DIR)/boot.bin
STAGE2_BIN:= $(BUILD_DIR)/stage2.bin
FLOPPY    := $(BUILD_DIR)/pyro.img

NASM_IMG  := kernel-bootloaders/nasm:latest
DOCKER    := docker run --rm -v $(PROJ_DIR):/work -w /work $(NASM_IMG)

QEMU      := qemu-system-i386

.PHONY: all run debug clean nasm-image

all: $(FLOPPY)

# Build the docker image once (idempotent because of the conditional check)
nasm-image:
	@docker image inspect $(NASM_IMG) >/dev/null 2>&1 || \
	docker build -t $(NASM_IMG) -f docker/Dockerfile.nasm docker/

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BOOT_BIN): $(SRC_DIR)/boot.asm | $(BUILD_DIR) nasm-image
	$(DOCKER) nasm -f bin $< -o $@

$(STAGE2_BIN): $(SRC_DIR)/stage2.asm | $(BUILD_DIR) nasm-image
	$(DOCKER) nasm -f bin $< -o $@

$(FLOPPY): $(BOOT_BIN) $(STAGE2_BIN)
	# 1.44 MB blank floppy
	dd if=/dev/zero of=$@ bs=512 count=2880 status=none
	# Sector 1 = boot, sectors 2.. = stage 2
	dd if=$(BOOT_BIN)   of=$@ conv=notrunc status=none
	dd if=$(STAGE2_BIN) of=$@ bs=512 seek=1 conv=notrunc status=none
	@echo "Built $(FLOPPY)  (boot=$$(stat -f%z $(BOOT_BIN)) bytes, stage2=$$(stat -f%z $(STAGE2_BIN)) bytes)"

run: $(FLOPPY)
	$(QEMU) -fda $(FLOPPY) -boot a

debug: $(FLOPPY)
	$(QEMU) -fda $(FLOPPY) -boot a -s -S

clean:
	rm -rf $(BUILD_DIR)
