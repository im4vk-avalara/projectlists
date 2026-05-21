# shadowfox + lighthouse

A paired educational Linux kernel security project: an offensive module
that demonstrates classical concealment techniques, and a detector module
that finds them. Every offensive capability ships with a matching
detection capability and a written explanation of both sides.

> **Scope.** This is a teaching artifact intended for a disposable
> research VM. It is not designed to evade modern endpoint security and
> contains no anti-forensics, no exfiltration, and no production-stealth
> code. The project will not accept contributions that move it in that
> direction — see [`PROMPT.md`](PROMPT.md) for the hard constraints.

## Modules

- **shadowfox** (`modules/shadowfox/`) — implements published, well-known
  kernel concealment techniques: module list manipulation, ftrace-based
  syscall interception for hiding processes and files, `/proc/net`
  hooking for network entries, and a credential-modification helper that
  illustrates how kernel-mode code can elevate a userspace task.
- **lighthouse** (`modules/lighthouse/`) — paired detection: cross-view
  reconciliation of kernel structures against userspace-visible state,
  syscall-table integrity hashing, CR0 write-protect monitoring, and
  direct walks of `tcp_hashinfo` / process trees that bypass the hooked
  paths.

Both modules are GPL v2 (required for access to the GPL-only exported
kernel symbols they use).

## Target environment

- Linux kernel **6.6 LTS** (specifically `6.6.138-0606138-generic`),
  x86_64
- Ubuntu 24.04 server inside QEMU
- macOS Apple Silicon host using QEMU TCG software emulation

Other kernel versions are noted where APIs diverge but are not actively
supported.

## Repository layout

```
.
├── PROMPT.md                # project brief and hard constraints
├── PROJECT_STATE.md         # current-status scratchpad (not committed)
├── LICENSE                  # GPL v2
├── Makefile                 # top-level: build/clean both modules
├── modules/
│   ├── shadowfox/           # offensive module (kbuild)
│   └── lighthouse/          # detector module (kbuild)
├── harness/                 # userland test runner (Stage 7)
├── docs/
│   ├── setup/
│   │   └── lab-vm.md        # QEMU lab reproducibility guide
│   └── techniques/          # one writeup per technique, paired offense + detection
└── vm/
    ├── launch.sh            # QEMU boot wrapper
    └── cloud-init/          # NoCloud datasource (user-data, meta-data)
```

## Quick start

Build the lab VM (one-time setup, ~30 min including kernel pin):

```sh
# Follow docs/setup/lab-vm.md end-to-end:
#   1. install qemu + cdrtools + cloud-image-utils on the host
#   2. download Ubuntu 24.04 cloud image, build seed.iso
#   3. boot, install kernel 6.6.138, snapshot baseline
```

Day-to-day:

```sh
./vm/launch.sh             # boot the VM in this terminal (Ctrl-A X to quit)
ssh shadowfox-lab          # SSH in (alias for researcher@localhost:2223)
```

Build the modules (from inside the VM, against the running kernel):

```sh
make                       # builds both
make shadowfox             # builds the offensive module only
make lighthouse            # builds the detector module only
make clean                 # cleans both
```

Reset the VM to a known-clean state any time (with the VM powered off):

```sh
cp vm/baseline-6.6.qcow2 vm/ubuntu-24.04-amd64.img
```

## Stage roadmap

Work is sequenced into stages. Each stage adds one offensive technique
and its matched detector together — neither half is committed without the
other.

| Stage | Topic                                                            |
|-------|------------------------------------------------------------------|
| 0     | Repo skeleton, build system, lab VM, README framing              |
| 1     | Module-list concealment + module-list integrity detector         |
| 2     | Credential-modification helper + cred-state detector             |
| 3     | Process concealment via ftrace + cross-view PID detector         |
| 4     | Directory-entry filtering on `getdents64` + `vfs_readdir` audit  |
| 5     | `/proc/net` filtering + direct `tcp_hashinfo` walker             |
| 6     | Integrity layer: syscall-table hashing + CR0 WP monitor          |
| 7     | Userland test harness (assert detection fires for each stage)    |
| 8     | Documentation polish + demo script                               |

The current stage is recorded in `PROJECT_STATE.md` (not committed).

## Documentation

Every technique gets a corresponding writeup under `docs/techniques/`.
Each writeup follows the same structure:

1. Overview
2. Kernel internals involved
3. Implementation walkthrough
4. Kernel version compatibility matrix
5. Detection counterpart (in `lighthouse`)
6. Real-world references (Diamorphine, Reptile, LWN, Phrack, academic
   papers — cited inline)
7. Mitigations (kernel hardening features that defeat the technique)
8. Lessons learned

See [`docs/setup/lab-vm.md`](docs/setup/lab-vm.md) for the VM build
guide.

## License

GPL v2. See [`LICENSE`](LICENSE).

## References

The implementation draws on published educational rootkit/anti-rootkit
work, cited per-technique in the `docs/techniques/` files. Notable
recurring references:

- Diamorphine — m0nad
- Reptile — f0rb1dd3n
- suterusu
- LWN.net kernel-development articles (linked inline where used)
- Phrack issues on kernel-mode concealment
- Linux kernel source — primary reference, version-pinned to 6.6 LTS
