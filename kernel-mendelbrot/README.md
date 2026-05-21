# Mandelbrot in 170 bytes

A demoscene-style sizecoded Mandelbrot renderer: a hand-written x86 16-bit
real-mode DOS `.COM` file that draws the canonical bulb-and-tendril shape
in VGA mode 13h (320×200×256), with palette colors indicating
escape-iteration count.

Final binary: **`build/mandq12.com` — 170 bytes.**

![Mandelbrot — Q4.12 fixed-point, 170 bytes](listings/screenshot-mandq12.png)
*(Screenshot lives in your scratch dir from the verification runs.)*

---

## Byte budget — every milestone

| Stage | File | Bytes | Δ | Technique introduced |
|-------|------|------:|---:|----------------------|
| 0 | `hello.com` | 16 | — | Toolchain proof: smallest valid `.COM` |
| 1 | `gradient.com` | 29 | — | VGA mode 13h init, direct framebuffer write |
| 2 (FPU) | `mandfpu.com` | 220 | — | Naive Mandelbrot via x87 (`FLD`/`FMUL`/`FCOMIP`) |
| 2 (fixed) | `mandfix.com` | 252 | +32 | Same algorithm in 32-bit Q16.16 (every op pays the 0x66 prefix tax) |
| 3 | (initial Q4.12) | 202 | −18 vs FPU | 16-bit Q4.12 with `IMUL + SHRD AX, DX, 12`; overflow guard via `CMP DH, 4` |
| 4 pass 1 | (mandq12) | 192 | −10 | `STOSB`, merged in-set/escape paths, byte-comparison for overflow check |
| 4 pass 2 | (mandq12) | — | combined | `IMUL AX` for squaring (2 B vs 4 B), `zi_new` eliminated by reordering writes |
| 4 pass 3 | (mandq12) | — | combined | Incremental `cr`/`ci` (per-pixel multiplication → single `ADD` immediate) |
| 4 pass 4 | (mandq12) | — | combined | Countdown outer loops, `x_step`/`y_step` baked into `ADD imm8` |
| **Final** | **`mandq12.com`** | **170** | **−32** vs Stage 3 | **All Stage 4 passes bundled** |

Real goal of **256 bytes beaten by 86 bytes**. The 128-byte stretch goal is
42 bytes away and reachable with more aggressive techniques (see "What's
left on the table" below).

---

## How it works

### The escape-time algorithm

For each screen pixel `(X, Y)`:

```
c = cr + i·ci          where  cr = -2.5 + X · (3.5/320)
                              ci = -1.0 + Y · (2.0/200)
z = 0
for k = ITERS..1:
    if |z|² > 4: break               ← "escaped"; the pixel is outside the set
    z = z² + c                       ← the only Mandelbrot operation that matters
plot(X, Y) = k                       ← k > 0 if escaped; k = 0 if "in set" → black
```

`z² + c` expanded into real-valued components:

```
zr_new = zr² − zi² + cr
zi_new = 2·zr·zi  + ci
```

### Q4.12 fixed-point in 16 bits

Every numeric value lives in a 16-bit signed integer split as:

```
    [ s | iii | ffff ffff ffff ]
      │   │     └─ 12 fractional bits
      │   └────── 3 integer bits
      └────────── sign bit

  real_value = stored_int / 4096

  Range:     [-8.0, +8.0)
  Precision: 1/4096 ≈ 2.4 × 10⁻⁴   (way finer than 1/320 pixel grid)
```

Examples (16-bit hex):

| Real | Q4.12 hex |
|----:|----:|
| 0.0 | `0x0000` |
| 1.0 | `0x1000` |
| 2.0 | `0x2000` |
| 4.0 | `0x4000` *(escape threshold)* |
| -1.0 | `0xF000` |
| -2.5 | `0xD800` |

Multiplication: `IMUL r/m16` produces a signed 32-bit product in `DX:AX`.
For two Q4.12 inputs the product is Q8.24; `SHRD AX, DX, 12` shifts it back
to Q4.12 in `AX`.

### The Q4.12 overflow trap (and the cheap fix)

The recurrence can briefly produce `|zr_new| > 2` (when `cr` is large
negative). Squaring 3.0 → 9.0 which does **not** fit Q4.12. The raw 32-bit
IMUL is fine, but `SHRD` to 16-bit silently wraps, and the escape compare
sees a small negative number and never fires.

Fix: inspect `DX` directly **before** `SHRD`. For any positive square `P`,
`|z|² ≥ 4 ⟺ raw_product ≥ 4 · 4096² = 0x04000000 ⟺ DH ≥ 4`. A
single `CMP DH, 4 / JAE .escape` after each square catches the overflow
case without needing wider arithmetic.

### Mode 13h essentials

- `INT 10h, AX=0013h` switches to 320×200 256-color graphics
- Framebuffer is one flat byte-per-pixel array at segment `0xA000`
- Pixel color is just an index into the default VGA palette (which already
  cycles through blacks, blues, greens, browns, reds, grays — perfect for
  visualizing iteration depth without configuring our own palette)

### Initial register state (the freebie)

DOS hands a `.COM` program a known register state at entry:

```
AX = 0x0000     CX = 0x00FF     DX = CS         SI = 0x0100
DI = 0xFFFE     BP = 0x091C     CS = DS = ES = SS
SP = 0xFFFE     and [SS:SP] = 0x0000 (preloaded for RET-as-exit)
```

We exploit `AX = 0` for `MOV AL, 0x13` (1 byte saved vs `MOV AX, 0x0013`)
and the `[SS:SP] = 0` invariant for `RET` as the program-terminate
instruction (1 byte vs the 4 bytes of `MOV AH, 0x4C / INT 21h`).

---

## Sizecoding techniques catalog (with byte savings)

| Technique | Used where | Save |
|-----------|-----------|-----:|
| Exploit `AX = 0` on entry | `MOV AL, 0x13` for mode set | 1 B |
| `PUSH imm16 / POP ES` for segment load | Setting `ES = 0xA000` | 1 B |
| `STOSB` instead of `MOV/INC` | Pixel write to VGA | 3 B |
| Merge in-set & escape exit paths via `CX = 0` after `LOOP` | Coloring code | 4 B |
| Byte compare instead of word compare | Overflow guard `CMP DH, 4` (vs `CMP DX, 0x400`) | 1 B × 2 |
| Single-operand `IMUL AX` for squaring | `zr²` and `zi²` | 2 B × 2 |
| Direct-write `zi_new` (eliminate temp variable) | Iteration body | 8 B |
| Incremental `cr` / `ci` per pixel (no per-pixel `IMUL`) | Inner-loop coordinate update | ~14 B |
| Countdown loops (`DEC/JNZ`) instead of `INC/CMP imm16/JB` | Both outer loops | ~6 B |
| `RET` as program exit (DOS-preloaded `0` on stack jumps to PSP `INT 20h`) | Program tail | 3 B |

---

## Build & run

This project does **zero host-system installs** beyond Docker, QEMU, and
Python 3 (all of which the host already had). All assembly happens inside
an Alpine container, and FreeDOS file injection uses QEMU's built-in
`vvfat` driver — no `mtools`, no disk-image surgery.

```bash
# One-time setup
make image              # build the Alpine + NASM Docker image
make dos.img            # downloads FreeDOS 1.3 floppy (~21 MB zip),
                        # extracts the 1.44 MB boot image, and patches
                        # FDAUTO.BAT so it boots straight to C:\>
                        # instead of running the installer

# Build & run
make run-mandq12        # build mandq12.com and boot it in QEMU
make sizes              # show byte counts of all built .com files
make all                # assemble every *.asm in the project root

# Cleanup
make clean              # remove build/ + listings/
make distclean          # also remove dos.img and the Docker image
```

Inside the QEMU window:
1. Wait ~10 s at the FreeDOS boot menu (or press `1` for English)
2. Land at `C:\>`
3. Type `MANDQ12` (or `HELLO`, `GRADIENT`, `MANDFPU`, `MANDFIX`)
4. The program draws, waits for a keypress, restores text mode, returns to `C:\>`

---

## Project layout

```
kernel-mendelbrot/
├── README.md              # this file
├── PROMPT.md              # original brief / quality bar / anti-patterns
├── Makefile               # complete toolchain orchestration
├── Dockerfile             # 4-line Alpine image with NASM 2.16
├── hello.asm              # Stage 0 — 16-byte "Hi$" .COM
├── gradient.asm           # Stage 1 — 29-byte mode-13h fill
├── mandfpu.asm            # Stage 2 — 220-byte x87 Mandelbrot
├── mandfix.asm            # Stage 2 — 252-byte Q16.16 Mandelbrot
├── mandq12.asm            # Stages 3-4 — 170-byte Q4.12 Mandelbrot (final)
├── freedos.img            # pristine FreeDOS 1.3 boot floppy (downloaded)
├── dos.img                # patched copy (auto-boots to C:\>)
├── tools/
│   └── patch_fdauto.py    # FAT12 surgery that neutralizes the installer
├── build/                 # .com binaries (exposed to FreeDOS via vvfat)
└── listings/              # NASM listings (.lst) — for byte-level audits
```

---

## What's left on the table

Stretch goal of 128 bytes is 42 bytes away. Plausible paths:

| Pass | Tactic | Estimated savings | Cost |
|------|--------|------------------:|------|
| 5 | Drop the mode-3 restore at exit | ~5 B | DOS prompt becomes invisible (still in mode 13h) |
| 6 | Keep `zr`, `zi` register-resident (BX, BP) | ~10–20 B | Register pressure; tricky around `IMUL` clobber |
| 7 | Single-counter pixel walk (`DI: 0..63999`, derive `(X, Y)` only at row boundary) | ~5–10 B | Loop topology rewrite |
| 8 | Self-modifying immediate operands | varies | Highest risk; hardest to debug |

A pure-FPU rewrite at 256-byte budget can come in around 100 bytes when
done by experts (see [pouet.net 256-byte intros][pouet]). Hitting <128
typically requires algorithmic changes (lower iteration count, palette
tricks, eliminating multiplications via per-row dx/dy difference updates,
etc.) — which would be a different project from this educational
"see-every-byte-saved" walkthrough.

[pouet]: https://www.pouet.net/prodlist.php?type%5B%5D=256b&platform%5B%5D=MS-Dos

---

## References used while building this

- [Sizecoding wiki](http://www.sizecoding.org/) — canonical primer on x86
  sizecoding tricks
- [pouet.net 256-byte intros](https://www.pouet.net/) — the scene archive
- Intel x86 reference for instruction encoding sizes (especially the
  shorter `A1`/`A3` mem moves and one-operand `IMUL`)
- The PROMPT.md brief in this repo (working protocol, anti-patterns,
  quality bar)
