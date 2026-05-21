#!/usr/bin/env bash
# Boot a raw disk image under QEMU using legacy BIOS.
# Usage: ./run-qemu.sh [image]  (defaults to boot.img)
set -euo pipefail
IMG="${1:-boot.img}"
exec qemu-system-i386 \
  -drive format=raw,file="$IMG" \
  -name "kernel-polyglot" \
  "${@:2}"
