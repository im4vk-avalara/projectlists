# Lab VM — reproducibility guide

This document describes how to build the disposable QEMU VM used for all
kernel work in this repository. Every command below has been exercised on
the project author's host; if you reproduce on a different host, adjust
paths and package names as needed.

## 1. Target

| Property        | Value                                              |
|-----------------|----------------------------------------------------|
| Host OS         | macOS (Apple Silicon)                              |
| Hypervisor      | QEMU `qemu-system-x86_64`, TCG software emulation  |
| Guest distro    | Ubuntu 24.04 server (cloud image)                  |
| Guest kernel    | `6.6.138-0606138-generic` (Ubuntu mainline build)  |
| Guest user      | `researcher`, NOPASSWD sudo                        |
| Networking      | user-mode, host-forward `tcp:2223 -> guest:22`     |

Apple Silicon hosts cannot use HVF acceleration to run an x86_64 guest,
hence the `-accel tcg,thread=multi` flag in `vm/launch.sh`. Boot is slow
(several minutes) but functional.

## 2. Host prerequisites

Install the tools used to build and boot the VM. On macOS with Homebrew:

```sh
brew install qemu cdrtools cloud-image-utils
# cdrtools provides mkisofs; cloud-image-utils provides cloud-localds
```

(`cloud-localds` is convenient but not strictly required; the seed.iso
can be produced with `mkisofs` directly, which is what the section below
shows.)

## 3. Layout

All VM artifacts live under `vm/`. The build artifacts (`*.qcow2`,
`*.img`, `seed.iso`, `qemu.log`) are gitignored — only the source-of-truth
inputs are committed:

```
vm/
├── launch.sh                 # QEMU boot wrapper (committed)
├── cloud-init/
│   ├── user-data             # researcher user, ssh key, base packages
│   └── meta-data             # instance-id + hostname
├── ubuntu-24.04-amd64.img    # working disk (gitignored)
├── baseline-6.6.qcow2        # post-kernel-install snapshot (gitignored)
├── seed.iso                  # NoCloud datasource (gitignored)
└── qemu.log                  # latest serial log (gitignored)
```

## 4. Build the working disk

Download the Ubuntu 24.04 server cloud image, rename to the path
`launch.sh` expects, and grow it to 20 GiB so kernel installs fit:

```sh
cd vm/
curl -LO https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img
mv ubuntu-24.04-server-cloudimg-amd64.img ubuntu-24.04-amd64.img
qemu-img resize ubuntu-24.04-amd64.img 20G
```

## 5. Build the cloud-init seed

`vm/cloud-init/user-data` is already in the repo. It provisions the
`researcher` user with the project SSH key and installs base build
packages (`build-essential`, `kmod`, `linux-headers-generic`, `git`,
`curl`, `ca-certificates`).

Bundle the two cloud-init files into a NoCloud-format ISO:

```sh
cd vm/
mkisofs -output seed.iso -volid cidata -joliet -rock \
    cloud-init/user-data cloud-init/meta-data
```

QEMU mounts `seed.iso` read-only on the second virtio drive (see
`launch.sh`); cloud-init detects it on first boot and provisions the
guest.

## 6. First boot

```sh
./vm/launch.sh
```

The VM boots on serial console (`-nographic`). You can attach with
`Ctrl-A` then `C` to reach the QEMU monitor, or `Ctrl-A` then `X` to
terminate the VM. First boot runs cloud-init; once you see
`shadowfox-lab login:` the user is provisioned. SSH from the host:

```sh
ssh -p 2223 researcher@localhost
```

The project uses an `~/.ssh/config` alias to shorten this:

```
Host shadowfox-lab
    HostName        localhost
    Port            2223
    User            researcher
    UserKnownHostsFile  ~/.ssh/known_hosts.shadowfox-lab
    StrictHostKeyChecking accept-new
```

After which `ssh shadowfox-lab` works.

## 7. Set a fallback password for serial console

If SSH is ever broken from a misconfigured module, you need a way back in
on the serial console. Set a password for `researcher` from inside the
VM:

```sh
sudo passwd researcher
# pick anything; this project used "12345" — DO NOT reuse on anything real
```

This password is never written to a committed file.

## 8. Pin kernel 6.6.138

The Ubuntu 24.04 cloud image ships a newer kernel by default. We pin to
6.6 LTS so all techniques in this repo build and behave consistently.

Inside the VM:

```sh
mkdir -p /tmp/kernel-debs && cd /tmp/kernel-debs
BASE=https://kernel.ubuntu.com/mainline/v6.6.138/amd64
for f in \
    linux-headers-6.6.138-0606138_6.6.138-0606138.202605080820_all.deb \
    linux-headers-6.6.138-0606138-generic_6.6.138-0606138.202605080820_amd64.deb \
    linux-image-unsigned-6.6.138-0606138-generic_6.6.138-0606138.202605080820_amd64.deb \
    linux-modules-6.6.138-0606138-generic_6.6.138-0606138.202605080820_amd64.deb; do
    curl -LO "$BASE/$f"
done
sudo dpkg -i *.deb
```

Then make 6.6 the default boot entry in GRUB:

```sh
sudo sed -i 's|^GRUB_DEFAULT=.*|GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.6.138-0606138-generic"|' /etc/default/grub
sudo update-grub
sudo reboot
```

After reboot, confirm:

```sh
uname -r
# 6.6.138-0606138-generic
```

## 9. Quiet apt so it does not fight the work

Unattended-upgrades will grab the dpkg lock at the worst moments. Mask it
inside the VM:

```sh
sudo systemctl mask --now unattended-upgrades.service
sudo systemctl mask --now apt-daily.timer apt-daily-upgrade.timer
```

## 10. Take the baseline snapshot

After the kernel is pinned, reboot tested, and the VM is in a clean
state, **shut the VM down cleanly** (`sudo poweroff`), then on the host:

```sh
cp vm/ubuntu-24.04-amd64.img vm/baseline-6.6.qcow2
```

This is the rollback point. Any time the working image is wrecked by a
bad module load, restore with:

```sh
cp vm/baseline-6.6.qcow2 vm/ubuntu-24.04-amd64.img
```

(The VM must be off when you copy — qcow2 files are not safe to clobber
while QEMU has them open.)

## 11. Day-to-day cheatsheet

| Action                   | Command                                              |
|--------------------------|------------------------------------------------------|
| Boot VM                  | `./vm/launch.sh`                                     |
| SSH in                   | `ssh shadowfox-lab`                                  |
| Terminate QEMU           | `Ctrl-A` then `X` on the serial console              |
| Reset to baseline        | `cp vm/baseline-6.6.qcow2 vm/ubuntu-24.04-amd64.img` |
| Check if VM is running   | `pgrep qemu`                                         |
| Tail serial log          | `tail -f vm/qemu.log`                                |

## 12. Known limitations

- TCG emulation on Apple Silicon is slow. Kernel compile inside the VM
  takes minutes, not seconds. Plan accordingly.
- The `qemu64` CPU model exposes a deliberately conservative feature set;
  some CPU-feature-gated kernel code paths will not exercise. If you
  need a specific x86 feature, switch the `-cpu` flag and document it.
- KASLR is on by default in this kernel build. Stages that need it off
  for inspection should boot with `nokaslr` on the kernel cmdline — do
  this from the GRUB menu, do not persist it to `/etc/default/grub`.
- The `seed.iso` is consumed only on first boot. Editing
  `cloud-init/user-data` after first boot has no effect; you must rebuild
  the working disk from the cloud image to re-run cloud-init.
