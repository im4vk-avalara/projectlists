#!/usr/bin/env bash
# shadowfox-lab VM launcher.
# Boots the qcow2 disk image with cloud-init seed, pinned to kernel 6.6.138.
# SSH at localhost:2223 (alias: shadowfox-lab once sshd is up).
# Reset to clean baseline: cp baseline-6.6.qcow2 ubuntu-24.04-amd64.img
set -eu
cd "$(dirname "$0")"

exec qemu-system-x86_64 \
    -accel tcg,thread=multi \
    -cpu qemu64 \
    -smp 2 -m 2048 \
    -drive if=virtio,format=qcow2,file=ubuntu-24.04-amd64.img \
    -drive if=virtio,format=raw,file=seed.iso,readonly=on \
    -netdev user,id=net0,hostfwd=tcp::2223-:22 \
    -device virtio-net-pci,netdev=net0 \
    -nographic \
    "$@"
