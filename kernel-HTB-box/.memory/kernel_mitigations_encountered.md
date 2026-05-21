---
name: kernel-mitigations-encountered
description: "Linux kernel mitigations that gate copy_from_user-based heap-overflow exploits on kernel 6.8 ARM64, the primitives that bypass them, and the discovery story from the integer-overflow box"
metadata: 
  node_type: memory
  type: project
---

## Why this exists
Built during [[project-kernel-scratch]] Box 2 (integer overflow). The textbook "size wraps small, copy writes huge" shape fights three separate mitigations in modern kernels. We hit two of them in sequence before finding a bypass primitive that works. Future boxes that involve user-controlled-size copies should consult this first.

**Kernel context:** Ubuntu 24.04 ARM64, `6.8.0-117-generic`. CONFIG_HARDENED_USERCOPY=y, CONFIG_FORTIFY_SOURCE=y, CONFIG_UBSAN_BOUNDS=y. KASAN not enabled. KASLR disabled (off for box building).

## Mitigation 1 — INT_MAX rejection in `check_copy_size()`
**Where:** `include/linux/thread_info.h:249` — `WARN_ON_ONCE(bytes > INT_MAX)` inside the inline `check_copy_size()`.

**What it does:** Every `copy_from_user`/`copy_to_user` call routes through `check_copy_size`. If `bytes > 0x7FFFFFFF`, the macro WARNs once and returns `false`, which makes the copy_from_user wrapper skip the actual copy entirely (returns `n` = "all bytes uncopied").

**Why:** The first design used a u32 size field. `user_size + 4` wraps to 0 only when `user_size ∈ {0xFFFFFFFC..0xFFFFFFFF}` — all above INT_MAX. dmesg showed the WARN at `dev_write+0xfc`. No overwrite happened.

**How to apply:** Pick a wrap that keeps `bytes ≤ INT_MAX`. Switching the size field from u32 → u16 made the wrap require only ~65534, well under INT_MAX. The check let it through.

## Mitigation 2 — `__check_heap_object` (CONFIG_HARDENED_USERCOPY)
**Where:** `mm/usercopy.c:102`. Invoked from `__check_object_size` → `check_heap_object`.

**What it does:** When `copy_from_user` targets a heap address, the kernel resolves which slab object owns the destination and `BUG()`s if the requested byte count exceeds the slab object size. This is `BUG`, not `WARN` — process is killed, kernel panic stack trace, irrecoverable.

**Why:** After the u16 fix passed Mitigation 1, the 65534-byte copy into the 96-byte kmalloc-96 slab object tripped this. dmesg: `usercopy: Kernel memory overwrite attempt detected to SLUB object 'kmalloc-rnd-11-96' (offset 0, size 65534)!` followed by `kernel BUG at mm/usercopy.c:102!` and a trailing `ct_kernel_exit` WARN from the cleanup confusion.

**How to apply:** You CANNOT do a single-shot `copy_from_user` whose byte count exceeds the destination slab object's size. This essentially kills the "size wraps, copy huge" pattern for any heap target. Options:
- Static `.bss` destination (escapes `__check_heap_object`) — but FORTIFY_SOURCE will then catch it (see Mitigation 3).
- Different copy primitive that doesn't go through `__check_object_size` — see "Bypass primitives" below.

## Mitigation 3 — FORTIFY_SOURCE (compile-time `__builtin_object_size`)
**Where:** Same `check_copy_size`, the FIRST branch: `int sz = __builtin_object_size(addr, 0); if (sz >= 0 && sz < bytes) copy_overflow()`.

**What it does:** If gcc can statically determine the destination's enclosing-object size, the runtime check rejects copies that exceed it. `copy_overflow` is a WARN that returns false → copy skipped.

**Why:** Not directly hit in this session (we never tried the static-buffer route), but it would have blocked us if we had. Worth knowing because it shapes what alternatives exist.

**How to apply:** `__builtin_object_size` returns `-1` for opaque pointers — pointer-laundered through a `noinline` function, returned from a function with a `void *` cast, etc. Local variables of known type still resolve (so `char b; get_user(b, ...)` is fine). The destination needs to be opaque to gcc OR access needs to be raw array indexing (which isn't FORTIFY-wrapped at all).

## Mitigation 4 — UBSAN (report-only, no teeth)
**Where:** `__ubsan_handle_out_of_bounds` in the UBSAN runtime.

**What it does:** When the byte-loop bypass runs `st->buf[i] = b` with `i >= 64`, UBSAN notices the array OOB and dumps a stack trace to dmesg. **It does not block the write.**

**Why we care:** Easy to mistake the UBSAN trace for a failure. It isn't. The exploit succeeded with this trace in dmesg. Mental model: not every dmesg stack trace is a fatal abort — look for `BUG` vs `WARNING` keywords.

## Bypass primitives that worked

### get_user byte loop + raw C array indexing
```c
for (u32 i = 0; i < user_size; i++) {
    char b;
    if (get_user(b, ubuf + sizeof(u16) + i)) return -EFAULT;
    st->buf[i] = b;   // raw STR instruction, no mitigation hook
}
```
- `get_user(b, ptr)` reads 1 byte into a local. No destination-size check applies; the size is implicit in the type of `b`.
- `st->buf[i] = b` is raw C array indexing → compiles to a STR. No FORTIFY (only wraps copy/string funcs). No `__check_heap_object` (only fires inside `copy_from_user`/`copy_to_user`). Just UBSAN noise.
- User-side guard page makes `get_user` fault at exactly `i = 72`, leaving callback (offset 64-71) overwritten and the loop terminated.

### Other bypasses considered but not used
- `__copy_from_user` (double-underscore, unchecked variant) — would also work, exported for modules. One-line change instead of a loop. Same lesson: "trusted size paths" are how real CVEs survive.
- `memcpy` from an in-kernel staging buffer — also FORTIFY-wrapped via `fortify_memcpy`. Need `noinline` opacity to bypass.

## Cheat sheet for designing the next bug
| Want to corrupt this | Use this primitive | Watch for |
|---|---|---|
| Heap slab object | `get_user` byte loop OR `__copy_from_user` | UBSAN trace in dmesg (harmless) |
| Static .bss buffer | byte loop OR opaque-pointer-laundered copy | FORTIFY via `__builtin_object_size` |
| Stack buffer (future stack-BOF box) | normal stack frame, no usercopy mitigations | Stack canary (likely on), KASLR off in our VM |
| OOB index write (no linear copy) | Direct `arr[user_index] = value` | UBSAN if KASAN-style instrumentation, but normally just runs |

## Verified working as of 2026-05-17
The byte-loop design ran successfully end-to-end as `player`: `uid=1002` → `[+] uid=0 ROOT!` → read `/root/root.txt` containing `HTB{c0mm1t_cr3ds_g1v3s_y0u_th3_k3rn3l}`. dmesg confirmed `vulndev_int: trigger — callback=escalate [vulndev_int]`.
