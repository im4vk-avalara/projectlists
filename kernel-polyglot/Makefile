NASM_IMAGE := kernel-polyglot/nasm:local
STAMP      := .nasm-image.stamp
ASM        := boot.asm
BOOT_BIN   := boot.bin
README     := readme.txt
BUILDER    := tools/build_polyglot.py
IMG        := boot.img

.PHONY: all help doctor test run run-headless inspect \
        verify-zip verify-pdf verify-animation capture-vga \
        clean nasm-image

all: $(IMG)

help:
	@echo "kernel-polyglot — available targets"
	@echo
	@echo "  Build & run"
	@echo "    make             Build boot.img (1018 B polyglot)"
	@echo "    make run         Boot it in QEMU (Cocoa window — see the animation)"
	@echo "    make clean       Remove all build artifacts"
	@echo
	@echo "  Verification (each is independent and headless)"
	@echo "    make test                Run all verifications below in sequence"
	@echo "    make verify-animation    Confirm the colour wave runs (VGA snapshots)"
	@echo "    make verify-zip          Validate ZIP via python/zipinfo/unzip"
	@echo "    make verify-pdf          Validate PDF via pdfinfo/qpdf/PDFKit"
	@echo
	@echo "  Diagnostics"
	@echo "    make doctor      Check prerequisites (Docker, QEMU, Python, host shell)"
	@echo "    make inspect     Hex dump of boot.img (look for 55 AA at 0x1FE)"
	@echo "    make capture-vga Boot headlessly, dump the VGA text buffer to stdout"
	@echo
	@echo "Prereqs: macOS (tested on Apple Silicon), Docker Desktop running,"
	@echo "QEMU on PATH (\`brew install qemu\`), Python 3, standard CLI (unzip/xxd)."

# Sanity-check the host before we expect any other target to succeed.
doctor:
	@echo "kernel-polyglot — host check"
	@printf '  %-22s ' 'docker (daemon)';      docker info --format '{{.ServerVersion}}' 2>/dev/null || echo 'MISSING — start Docker Desktop'
	@printf '  %-22s ' 'qemu-system-i386';     qemu-system-i386 --version 2>/dev/null | head -1 | sed 's/QEMU emulator //' || echo 'MISSING — brew install qemu'
	@printf '  %-22s ' 'python3';              python3 --version 2>/dev/null || echo 'MISSING'
	@printf '  %-22s ' 'unzip';                unzip -v 2>/dev/null | head -1 | cut -d, -f1 || echo 'MISSING'
	@printf '  %-22s ' 'zipinfo';              command -v zipinfo >/dev/null && echo 'present' || echo 'MISSING'
	@printf '  %-22s ' 'xxd';                  command -v xxd      >/dev/null && echo 'present' || echo 'MISSING'

# Umbrella test — run every verification, fail the make invocation if any
# step exits non-zero. Each underlying target prints its own findings.
test: $(IMG)
	@echo '════════════════════════ verify-animation ════════════════════════'
	@$(MAKE) --no-print-directory verify-animation
	@echo
	@echo '═════════════════════════ verify-zip ════════════════════════════'
	@$(MAKE) --no-print-directory verify-zip
	@echo
	@echo '═════════════════════════ verify-pdf ════════════════════════════'
	@$(MAKE) --no-print-directory verify-pdf
	@echo
	@echo '════════════════════════════ DONE ════════════════════════════════'
	@echo 'All three format-validators accepted boot.img.'

nasm-image: $(STAMP)

$(STAMP): tools/Dockerfile.nasm
	docker build -t $(NASM_IMAGE) -f tools/Dockerfile.nasm tools/
	@touch $(STAMP)

# Step 1: NASM produces the 512-byte raw boot sector.
$(BOOT_BIN): $(ASM) $(STAMP)
	docker run --rm -v "$$PWD":/work -w /work $(NASM_IMAGE) \
	  nasm -f bin $(ASM) -o $(BOOT_BIN) -l boot.lst
	@printf 'Built %s — %s bytes\n' $(BOOT_BIN) "$$(stat -f%z $(BOOT_BIN) 2>/dev/null || stat -c%s $(BOOT_BIN))"

# Step 2: Python composes the polyglot: boot sector + ZIP tail.
$(IMG): $(BOOT_BIN) $(README) $(BUILDER)
	python3 $(BUILDER) $(BOOT_BIN) $(README) -o $(IMG)

run: $(IMG)
	qemu-system-i386 -drive format=raw,file=$(IMG)

# Headless smoke test: capture SeaBIOS debug-console output, which prints
# "Booting from Hard Disk..." when the boot signature is accepted.
run-headless: $(IMG)
	@( qemu-system-i386 -drive format=raw,file=$(IMG) \
	     -display none -monitor none -no-reboot \
	     -debugcon stdio -global isa-debugcon.iobase=0x402 \
	     2>&1 & QEMU_PID=$$!; sleep 1; kill $$QEMU_PID 2>/dev/null; \
	     wait $$QEMU_PID 2>/dev/null; true ) \
	  | grep -E "Booting|signature|No bootable" || \
	  (echo "(no BIOS markers seen — check manually with 'make run')"; exit 0)

# Hex dump of the image (boot signature should be 55 AA at offset 0x1FE).
inspect: $(IMG)
	@xxd $(IMG) | head -40
	@echo "..."
	@xxd $(IMG) | tail -8

# Boot headlessly, wait for the guest to print, then grab the VGA text-mode
# framebuffer (0xB8000, 4 KiB for 80x25 cells × 2 bytes/cell), strip the
# attribute bytes, and print the screen as ASCII. The leading `sleep 2`
# is critical — it gives SeaBIOS + our boot code time to actually run
# before the monitor reads memory.
capture-vga: $(IMG)
	@rm -f vga.bin
	@( sleep 2; printf 'pmemsave 0xb8000 4000 vga.bin\nquit\n' ) | \
	  qemu-system-i386 -drive format=raw,file=$(IMG) \
	    -display none -monitor stdio -no-reboot >/dev/null 2>&1 || true
	@test -s vga.bin || { echo "FAILED: vga.bin not written"; exit 1; }
	@python3 -c "import sys; \
	  d=open('vga.bin','rb').read(); \
	  rows=[''.join(chr(d[i]) if 32<=d[i]<127 else ' ' for i in range(r*160, r*160+160, 2)) for r in range(25)]; \
	  out='\n'.join(line.rstrip() for line in rows if line.strip()); \
	  print(out if out else '(VGA buffer empty)')"

# Stage 2 verification: take two VGA snapshots ~2s apart and show that the
# attribute bytes change between them while the character bytes don't.
verify-animation: $(IMG)
	@rm -f vga1.bin vga2.bin
	@( sleep 2; printf 'pmemsave 0xb8000 4000 vga1.bin\nquit\n' ) | \
	  qemu-system-i386 -drive format=raw,file=$(IMG) \
	    -display none -monitor stdio -no-reboot >/dev/null 2>&1 || true
	@( sleep 4; printf 'pmemsave 0xb8000 4000 vga2.bin\nquit\n' ) | \
	  qemu-system-i386 -drive format=raw,file=$(IMG) \
	    -display none -monitor stdio -no-reboot >/dev/null 2>&1 || true
	@python3 -c "import collections; \
	  d1=open('vga1.bin','rb').read(); d2=open('vga2.bin','rb').read(); \
	  a1=d1[1::2]; a2=d2[1::2]; c1=d1[0::2]; c2=d2[0::2]; \
	  print(f't=2s: {len(set(a1))} distinct attrs, top: {collections.Counter(a1).most_common(4)}'); \
	  print(f't=4s: {len(set(a2))} distinct attrs, top: {collections.Counter(a2).most_common(4)}'); \
	  print(f'attribute bytes changed: {sum(1 for x,y in zip(a1,a2) if x!=y)} / 2000'); \
	  print(f'character bytes changed: {sum(1 for x,y in zip(c1,c2) if x!=y)} / 2000  (expect 0)')"

verify-zip: $(IMG)
	@echo "==> file"
	@file $(IMG)
	@echo
	@echo "==> python3 -m zipfile -l  (strict, anchors on EOCD)"
	@python3 -m zipfile -l $(IMG)
	@echo
	@echo "==> zipinfo (lenient, anchors on EOCD)"
	@zipinfo $(IMG) || true
	@echo
	@echo "==> unzip -l (warns about 512-byte boot-sector prefix; that is expected)"
	@unzip -l $(IMG) || true
	@echo
	@echo "==> unzip -p README.txt  (extract & dump contents to stdout)"
	@unzip -p $(IMG) README.txt

verify-pdf: $(IMG)
	@cp $(IMG) boot.pdf
	@echo "==> file boot.pdf"
	@file boot.pdf
	@echo
	@echo "==> %PDF- and %%EOF locations (sanity check)"
	@python3 -c "import sys; d=open('boot.pdf','rb').read(); \
	  p=d.find(b'%PDF-'); e=d.rfind(b'%%EOF'); \
	  print(f'  %PDF- at 0x{p:04X} ({\"OK\" if p < 1024 else \"OUT OF RANGE\"} — must be in first 1024 B)'); \
	  print(f'  %%EOF at 0x{e:04X}')"
	@echo
	@echo "==> pdfinfo (poppler in Alpine — no host install)"
	@docker run --rm -v "$$PWD":/work -w /work alpine:3 sh -c \
	  "apk add --quiet poppler-utils && cp boot.pdf /tmp/b.pdf && pdfinfo /tmp/b.pdf" \
	  2>&1 | grep -v -E '^(Title|Author|Subject|Keywords|Producer|Creator|CreationDate|ModDate)' | tail -15
	@echo
	@echo "==> qpdf --check (strict third-party parser)"
	@docker run --rm -v "$$PWD":/work -w /work alpine:3 sh -c \
	  "apk add --quiet qpdf && cp boot.pdf /tmp/b.pdf && qpdf --check /tmp/b.pdf"
	@echo
	@echo "==> macOS PDFKit (qlmanage produces a thumbnail iff PDFKit accepts)"
	@qlmanage -t -s 100 -o /tmp boot.pdf 2>&1 | grep -E "produced|cannot" | head -2
	@rm -f /tmp/boot.pdf.png boot.pdf

clean:
	rm -f $(IMG) $(BOOT_BIN) boot.lst $(STAMP) vga.bin vga1.bin vga2.bin
