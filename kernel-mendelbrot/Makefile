# ============================================================================
# Mandelbrot sizecoding project — toolchain Makefile
# ============================================================================
# Zero-install pipeline:
#   NASM      → Alpine container (built once via `make image`)
#   FreeDOS   → 1.44MB floppy image, patched for auto-boot to C:\>
#   File copy → QEMU vvfat driver (no mtools, no disk-image surgery)
#   Emulator  → qemu-system-i386 (pre-installed)
#
# Typical workflow:
#   make image            # one-time: build dockerized NASM
#   make dos.img          # one-time: patch the FreeDOS floppy
#   make run-hello        # build hello.asm and boot it in QEMU
#   make sizes            # show byte counts of every built .COM
#
# Naming convention:
#   *.asm           — sources in project root, lowercase 8.3-friendly names
#   build/*.com     — assembled .COM files (DOS shows them as *.COM)
# ============================================================================

NASM_IMAGE  := mandel-nasm
DOCKER      := docker
PYTHON      := python3
QEMU        := qemu-system-i386

# Docker invocation that runs nasm inside the container, cwd mounted at /work
DOCKER_RUN  := $(DOCKER) run --rm -v "$$PWD":/work $(NASM_IMAGE)

# QEMU args used for every run target. snapshot=on keeps the host build/ dir
# read-only from the guest's perspective (guest writes go to a temp overlay).
QEMU_FLAGS  := -m 16 \
               -drive file=dos.img,format=raw,if=floppy,index=0 \
               -drive file=fat:./build,format=raw,if=ide,index=0,snapshot=on \
               -boot a -display cocoa -no-reboot

# FreeDOS 1.3 Floppy Edition (only fetched if freedos.img is missing)
FREEDOS_URL := https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.3/official/FD13-FloppyEdition.zip
FREEDOS_ZIP := /tmp/fd13-fe.zip

# Auto-discover *.asm sources in project root
SRCS := $(wildcard *.asm)
COMS := $(patsubst %.asm,build/%.com,$(SRCS))

# ----------------------------------------------------------------------------
# Default target: help
# ----------------------------------------------------------------------------

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo 'Mandelbrot sizecoding — make targets:'
	@echo ''
	@echo '  Setup (run once):'
	@echo '    make image            Build the dockerized NASM image'
	@echo '    make freedos.img      Download FreeDOS 1.3 boot floppy (~21MB zip)'
	@echo '    make dos.img          Patch freedos.img → clean auto-boot to C:\\'
	@echo ''
	@echo '  Build & run:'
	@echo '    make all              Assemble every *.asm in project root'
	@echo '    make build/<x>.com    Assemble x.asm only'
	@echo '    make run-<x>          Build + boot x.asm in QEMU'
	@echo '    make sizes            Show byte counts of all built .com files'
	@echo ''
	@echo '  Cleanup:'
	@echo '    make clean            Remove build/ artifacts'
	@echo '    make distclean        Also remove dos.img + Docker image'
	@echo '    make nuke             distclean + remove freedos.img (force re-DL)'
	@echo ''
	@echo 'Detected sources: $(SRCS)'

# ----------------------------------------------------------------------------
# Toolchain setup
# ----------------------------------------------------------------------------

# Build the NASM Docker image. Only rebuilds when Dockerfile changes.
.PHONY: image
image: .image.stamp
.image.stamp: Dockerfile
	$(DOCKER) build -t $(NASM_IMAGE) .
	@touch $@

# Download + extract the FreeDOS boot floppy from the official mirror
freedos.img:
	@echo 'Downloading FreeDOS 1.3 Floppy Edition (~21MB)...'
	curl -fsSL -o $(FREEDOS_ZIP) "$(FREEDOS_URL)"
	unzip -j -o $(FREEDOS_ZIP) "144m/x86BOOT.img" -d .
	mv x86BOOT.img $@
	rm -f $(FREEDOS_ZIP)
	@echo 'Got $@ ($$(wc -c < $@) bytes)'

# Derive the patched dos.img — boots straight to C:\> with no installer
dos.img: freedos.img tools/patch_fdauto.py
	cp freedos.img $@
	$(PYTHON) tools/patch_fdauto.py $@

# ----------------------------------------------------------------------------
# Build rules — assemble *.asm → build/*.com
# ----------------------------------------------------------------------------

build listings:
	@mkdir -p $@

# Pattern rule: source.asm → build/source.com (in vvfat) + listings/source.lst
# Listings live outside build/ so they don't clutter the DOS DIR view.
build/%.com: %.asm .image.stamp | build listings
	$(DOCKER_RUN) -f bin $< -o $@ -l listings/$*.lst
	@printf '  built %s = %d bytes\n' '$@' $$(wc -c < $@)

.PHONY: all
all: $(COMS)

.PHONY: sizes
sizes:
	@if ls build/*.com >/dev/null 2>&1; then \
	   printf '  %-30s %6s\n' 'file' 'bytes'; \
	   printf '  %-30s %6s\n' '----' '-----'; \
	   for f in build/*.com; do \
	     printf '  %-30s %6d\n' "$$f" "$$(wc -c < $$f)"; \
	   done; \
	 else \
	   echo 'No .com files yet — run "make all" or "make build/<name>.com".'; \
	 fi

# ----------------------------------------------------------------------------
# Run rules — build + boot in QEMU
# ----------------------------------------------------------------------------

# run-<x>: ensures build/<x>.com and dos.img are up-to-date, then boots QEMU.
# Not a real file target, so `make run-hello` always re-evaluates dependencies.
run-%: build/%.com dos.img
	@echo 'Booting QEMU (close window or Cmd-Q to quit)...'
	$(QEMU) $(QEMU_FLAGS)

# ----------------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------------

.PHONY: clean distclean nuke
clean:
	rm -rf build listings

distclean: clean
	rm -f dos.img .image.stamp
	-$(DOCKER) rmi $(NASM_IMAGE) 2>/dev/null

nuke: distclean
	rm -f freedos.img
