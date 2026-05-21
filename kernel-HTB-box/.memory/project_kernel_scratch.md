---
name: project-kernel-scratch
description: "Full context of the kernel-scratch project — Box 1 (vulndev, packaged) and Box 2 (vulndev_int, integer overflow, exploit working but not packaged). Where to resume."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4250b2ed-a69d-46bd-b94d-7dd6eea47bb1
---

## Project location
`/Users/avinash.kumar/Downloads/Gen-AI/kernel-scratch/`

## What this project is
A workbench for building HTB (Hack The Box) kernel-pwn challenge boxes from scratch on macOS ARM64 (Apple Silicon) via QEMU. Each box is built in 4 phases: (1) clean char-device skeleton, (2) introduce a vulnerability, (3) write a working privesc exploit, (4) package as an OVA with flags and systemd autoload.

The QEMU setup, Phase 1 skeleton, and Phase 4 packaging recipe stay the same across boxes — only Phase 2 (the bug) and Phase 3 (the exploit) change.

---

## Box 1 — `vulndev`: linear stack-like overflow into adjacent function pointer
**Status: COMPLETE through Phase 4 — OVA exported as `vm/htb-kernelpwn.ova`.**

- Phase 2 (`vulndev.c`): static `dev_state { char buf[64]; void (*callback)(); }`, `dev_write` has no bounds check on `count` → writing >64 bytes overflows `buf` into `callback`.
- Phase 3 (`exploit.c`): open device → `IOCTL_LEAK_ADDR` leaks `escalate()` kernel address → write 64 bytes 'A' + 8 bytes escalate addr → `IOCTL_TRIGGER` fires the overwritten callback → `escalate()` does `commit_creds(prepare_kernel_cred(&init_task))` → uid=0 → `execl /bin/bash`.
- Phase 4 (`setup.sh`): copies `vulndev.ko` to `/opt/vulndev/`, creates `vulndev.service` systemd unit (autoloads on boot), creates `player` user (password `player123`), drops user.txt + root.txt flags. SSH password auth was manually enabled in `/etc/ssh/sshd_config` after `setup.sh` ran. Exported to OVA via qemu-img → vmdk → ovf.

This box exists primarily as a working reference. The `player` user, flag files, and systemd autoload are in the OVA's filesystem snapshot.

---

## Box 2 — `vulndev_int`: integer overflow (u16 addition wraparound)
**Status: Phases 2 + 3 DONE and exploit verified end-to-end as `player`. Phase 4 NOT done — no setup script, no separate OVA, no flag files for this box.**

### The bug (vulndev_int.c)
- Heap-allocated per-open state: `kmalloc(sizeof(struct dev_state))`, stored in `file->private_data`. Same `{ char buf[64]; void (*callback)(); }` shape as Box 1, but on the heap (kmalloc-96 slab).
- Wire format: `[u16 user_size][user_size bytes of data]`.
- The check `total = user_size + sizeof(u16); if (total > BUF_SIZE) return -EINVAL;` wraps on u16. `user_size = 0xFFFE` makes `total = 0`, passes the check.
- The data copy is NOT `copy_from_user` — it's a hand-rolled `get_user` byte loop writing `st->buf[i] = b` directly. This deliberate choice is the whole point of the box; see below.
- ioctls unchanged in shape: `IOCTL_TRIGGER` fires callback, `IOCTL_LEAK_ADDR` leaks `escalate()` addr. Magic char is `'w'` (vs `'v'` for Box 1) to avoid collision when both modules load.

### The exploit (exploit_int.c)
- mmap 2 pages, **munmap the second** to create a fault-guard at the page boundary.
- Place the payload (74 bytes: `u16 0xFFFE` + 64 `'A'` + 8-byte `escalate_addr`) at `region + pagesize - 74` so the last byte sits exactly at the page edge.
- `IOCTL_LEAK_ADDR` → escalate addr → memcpy into payload.
- `write(fd, payload, 74)` — kernel reads the 2-byte u16 header, computes `total = 0xFFFE + 2 = 0` (u16 wrap), passes check, enters the byte loop. After 72 successful `get_user`s (filling buf[64] + clobbering callback[8]), the 73rd read crosses into the guard page and returns -EFAULT. Loop returns -EFAULT. write returns -1 errno=14 — we ignore it.
- `IOCTL_TRIGGER` → callback (now `escalate`) fires → uid=0 → `execl bash`.
- Verified: `id` returns `uid=0(root)`, reads `/root/root.txt`.

### Why a byte loop and not copy_from_user
The natural shape of this exploit — single `copy_from_user(st->buf, ubuf+2, 65534)` — does NOT work on modern kernels. It fights two separate mitigations that we discovered the hard way over three iterations. The byte loop bypasses both. The full mitigation/bypass picture is in [[kernel-mitigations-encountered]] — read that first before designing the next box.

The pedagogical lesson became: "Drivers that hand-roll their copy in a byte loop reintroduce vulnerabilities that the kernel's mitigation hardening removed from `copy_from_user`."

---

## Cross-box gotchas (apply to any future box)

**`prepare_kernel_cred(NULL)` is broken on kernel >= 6.2.** Must use `prepare_kernel_cred(&init_task)` and include `<linux/sched/task.h>`. Returns NULL and WARNs otherwise — exploit fails silently if you don't notice.

**Modern usercopy mitigations defeat the textbook int-overflow exploit shape.** See [[kernel-mitigations-encountered]] for the playbook on copy primitives to use/avoid.

**UBSAN is report-only.** `__ubsan_handle_out_of_bounds` appears in dmesg when our byte loop OOB-writes, but it doesn't block. Don't be alarmed by stack traces in dmesg — they're not always fatal.

**ioctl magic chars must differ between coexisting modules.** `'v'` for vulndev, `'w'` for vulndev_int.

---

## VM setup
- QEMU on macOS Apple Silicon (ARM64). Ubuntu 24.04 ARM64 cloud image. Kernel `6.8.0-117-generic`.
- KASLR disabled (confirmed in boot log: "KASLR disabled due to lack of seed").
- SSH alias `kernel-dev` (defined in ~/.ssh/config → localhost:2222).
- Two users in the VM:
  - `dev`: provisioned by cloud-init from `vm/cloud-init/user-data` at first boot. SSH key + passwordless sudo. The management/build account.
  - `player`: created by `setup.sh` via `useradd` + `chpasswd`. Password `player123`. The HTB-foothold account.
- Boot command in `QEMU_SETUP.md`. Uses `</dev/null > qemu.log 2>&1 &` to detach.
- Seed disk is FAT (label `cidata`), not ISO — `hdiutil makehybrid` doesn't work for cloud-init on macOS.

---

## File map (host)
```
kernel-scratch/
├── vulndev.c          — Box 1 vulnerable module (Phase 2/3 final)
├── exploit.c          — Box 1 exploit
├── vulndev_int.c      — Box 2 vulnerable module (u16 wrap + get_user loop)
├── exploit_int.c      — Box 2 exploit (page-guard payload)
├── hello.c            — original hello world module
├── Makefile           — builds hello.ko, vulndev.ko, vulndev_int.ko
├── setup.sh           — Box 1 packaging (runs in VM as dev)
├── HTB_KERNEL_PWN.md  — full Box 1 documentation (Phases 1-4)
├── QEMU_SETUP.md      — VM boot/SSH setup guide
└── vm/
    ├── ubuntu-24.04-arm64.img   — active VM disk (modified)
    ├── seed.img                 — cloud-init FAT disk
    ├── edk2-aarch64-code.fd     — UEFI firmware
    ├── edk2-varstore.fd         — UEFI variable store
    ├── htb-kernelpwn.ovf        — Box 1 OVA descriptor
    ├── htb-kernelpwn.vmdk       — Box 1 exported VMDK
    ├── htb-kernelpwn.ova        — Box 1 final HTB submission
    └── cloud-init/
        ├── user-data            — provisions `dev` user (SSH key, NOPASSWD sudo)
        └── meta-data            — instance-id: kernel-dev-vm
```

## Files inside the VM (as of last session, 2026-05-17)
- `/home/dev/`: `vulndev.c`, `exploit.c`, `vulndev_int.c`, `exploit_int.c`, `Makefile`, all compiled `.ko` and binaries
- `/tmp/exploit_int` (mode 755): the compiled Box 2 exploit, world-executable
- `/opt/vulndev/vulndev.ko`: installed by setup.sh (Box 1, systemd-loaded)
- `vulndev_int.ko` is NOT installed to /opt/ and is NOT in any systemd unit — it was manually `insmod`'d during testing

## Current VM state (end of last session, 2026-05-17)
- VM is **running** (QEMU still up, port 2222 listening). Was NOT cleanly powered off after the successful exploit run.
- Both modules loaded: `vulndev` (autoload via systemd) AND `vulndev_int` (manually `insmod`'d). User chose not to `rmmod vulndev_int` for cleanup at session end.
- VM disk has been modified since last OVA export — the OVA file does NOT reflect vulndev_int.

---

## What comes next
Avinash wants more HTB boxes. Original agreed complexity order:
1. ~~Stack buffer overflow~~ — skipped for now
2. ~~Use-After-Free~~
3. **Integer overflow** ← done (Phases 2+3 only)
4. Race condition / TOCTOU

Open follow-on tasks (none committed-to yet):
- **Phase 4 for Box 2** — write `setup_int.sh`, decide whether to add to existing OVA as a second challenge or export a separate OVA. Existing `htb-kernelpwn.ova` is Box 1 only.
- **Cleanup decision** — whether to `rmmod vulndev_int` and re-export OVA, or leave the VM dual-loaded.
- **Box 3+ direction** — return to stack BOF (the originally agreed #1), or pick UAF, or something else.

Before starting the next box, read [[kernel-mitigations-encountered]] — knowing the mitigation landscape upfront saves the 3-iteration debugging arc we went through this session.
