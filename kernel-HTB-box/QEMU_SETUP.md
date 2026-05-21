# Linux Kernel Dev on macOS via QEMU

Tested on: macOS (Apple Silicon, ARM64), QEMU 9.x, Ubuntu 24.04

---

## Prerequisites

```bash
brew install qemu
```

Verify:

```bash
qemu-system-aarch64 --version
ls /opt/homebrew/share/qemu/edk2-aarch64-code.fd   # UEFI firmware
```

---

## 1. Download Ubuntu ARM64 Cloud Image

```bash
mkdir -p ~/kernel-dev/vm && cd ~/kernel-dev/vm

curl -L "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-arm64.img" \
  -o ubuntu-24.04-arm64.img

qemu-img resize ubuntu-24.04-arm64.img 10G
```

---

## 2. Create Cloud-Init Config

Cloud-init configures the VM on first boot (user, SSH key, packages).

```bash
mkdir -p cloud-init
```

**cloud-init/meta-data**

```yaml
instance-id: kernel-dev-vm
local-hostname: kernel-dev
```

**cloud-init/user-data** — replace the SSH key with your own (`cat ~/.ssh/id_ed25519.pub`)

```yaml
#cloud-config
users:
  - name: dev
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - ssh-ed25519 AAAA... your-key-here

packages:
  - build-essential
  - kmod
  - linux-headers-generic

package_update: true
package_upgrade: false
```

---

## 3. Create the Seed Disk Image

> **Important:** Must be a FAT filesystem labeled exactly `cidata` — cloud-init won't detect ISO hybrids on Linux VMs.

```bash
dd if=/dev/zero of=seed.img bs=1k count=2048
DISK=$(hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount seed.img | awk '{print $1}')
newfs_msdos -F 12 -v cidata $DISK
mkdir -p /tmp/cidata-mount
mount -t msdos $DISK /tmp/cidata-mount
cp cloud-init/user-data cloud-init/meta-data /tmp/cidata-mount/
umount /tmp/cidata-mount
hdiutil detach $DISK
```

---

## 4. Set Up UEFI Firmware

```bash
cp /opt/homebrew/share/qemu/edk2-aarch64-code.fd .
dd if=/dev/zero bs=1m count=64 of=edk2-varstore.fd
```

---

## 5. Set Up SSH Config (one-time)

Add this to `~/.ssh/config` so you can SSH in with just `ssh kernel-dev` — no flags, no key warnings:

```
Host kernel-dev
    HostName localhost
    Port 2222
    User dev
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
```

---

## 6. Boot the VM

```bash
qemu-system-aarch64 \
  -M virt \
  -cpu host \
  -accel hvf \
  -m 2048 \
  -smp 2 \
  -drive if=pflash,format=raw,file=edk2-aarch64-code.fd,readonly=on \
  -drive if=pflash,format=raw,file=edk2-varstore.fd \
  -drive if=virtio,format=qcow2,file=ubuntu-24.04-arm64.img \
  -drive if=virtio,format=raw,file=seed.img \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device virtio-net-pci,netdev=net0 \
  -nographic \
  </dev/null > qemu.log 2>&1 &
```

**First boot takes ~2 minutes** for cloud-init to install packages. Poll until SSH is up:

```bash
until ssh -o BatchMode=yes -o ConnectTimeout=3 kernel-dev "echo ready" 2>/dev/null | grep -q ready
do sleep 10 && echo "waiting..."; done
```

---

## 7. SSH Into the VM

```bash
ssh kernel-dev
```

To stop the VM (shuts down the OS and exits QEMU):

```bash
ssh kernel-dev "sudo poweroff"
```

---

## 8. Build and Load Your First Kernel Module

**hello.c**

```c
#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>

MODULE_LICENSE("GPL");

static int __init hello_init(void) {
    printk(KERN_INFO "Hello, kernel world!\n");
    return 0;
}

static void __exit hello_exit(void) {
    printk(KERN_INFO "Goodbye, kernel world!\n");
}

module_init(hello_init);
module_exit(hello_exit);
```

**Makefile**

```makefile
obj-m += hello.o
KDIR := /lib/modules/$(shell uname -r)/build

all:
	make -C $(KDIR) M=$(PWD) modules
clean:
	make -C $(KDIR) M=$(PWD) clean
```

Copy files and build inside the VM:

```bash
scp hello.c Makefile kernel-dev:~/
ssh kernel-dev "make -C /lib/modules/\$(uname -r)/build M=\$HOME modules"
```

Load, test, unload:

```bash
ssh kernel-dev "sudo insmod ~/hello.ko && sudo dmesg | tail -3"
ssh kernel-dev "sudo rmmod hello && sudo dmesg | tail -3"
```

---

## Iterating on Changes

After editing `hello.c` on your Mac:

```bash
scp hello.c kernel-dev:~/ && \
ssh kernel-dev "sudo rmmod hello 2>/dev/null; \
  make -C /lib/modules/\$(uname -r)/build M=\$HOME modules && \
  sudo insmod ~/hello.ko && sudo dmesg | tail -3"
```

---

## Gotchas

| Problem | Cause | Fix |
|---|---|---|
| `hdiutil makehybrid` seed not detected | ISO hybrid label not read by cloud-init | Use FAT image (`newfs_msdos -v cidata`) instead |
| `No such file or directory` for kernel headers | `linux-headers-generic` not installed | Add to `packages:` in user-data |
| `suspended (tty output)` in zsh | QEMU reads stdin from terminal | Add `</dev/null` before `> qemu.log 2>&1 &` |
| `Failed to get "write" lock` on disk image | Another QEMU process holds the image | Run `kill $(pgrep qemu-system-aarch64)` then retry |
| Cloud-init doesn't re-run on second boot | Same instance-id cached | Change `instance-id` in meta-data or run `sudo cloud-init clean` in VM |
