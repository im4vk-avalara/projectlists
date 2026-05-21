#!/usr/bin/env python3
"""
patch_fdauto.py — neutralize FDAUTO.BAT inside a FreeDOS 1.3 boot floppy.

The pristine FreeDOS 1.3 boot floppy (x86BOOT.img) launches the installer
from FDAUTO.BAT. We don't want the installer; we want a bare DOS prompt
sitting at C:\\ so we can run our sizecoded .COM files.

This script overwrites FDAUTO.BAT's contents (in place) with a tiny stub:
    @ECHO OFF
    C:
    <DOS-EOF>

After patching, COMMAND.COM still honors the FDCONFIG.SYS SHELL= directive
which auto-runs FDAUTO.BAT, but the stub does no work and exits straight
to C:\\>.

Pure standard-library — no pip installs needed.

Usage: python3 tools/patch_fdauto.py dos.img
"""
import struct
import sys

NEW_CONTENT = b'@ECHO OFF\r\nC:\r\n\x1A'

def main(path: str) -> None:
    with open(path, 'r+b') as f:
        img = bytearray(f.read())

    # Parse the FAT12 BIOS Parameter Block from the boot sector
    bps   = struct.unpack('<H', img[11:13])[0]   # bytes per sector
    spc   = img[13]                              # sectors per cluster
    rsv   = struct.unpack('<H', img[14:16])[0]   # reserved sectors
    nfats = img[16]                              # number of FATs
    nroot = struct.unpack('<H', img[17:19])[0]   # root dir entries
    spf   = struct.unpack('<H', img[22:24])[0]   # sectors per FAT

    fat_off  = rsv * bps
    root_off = (rsv + nfats * spf) * bps
    data_off = root_off + nroot * 32

    def fat12(c: int) -> int:
        pos = fat_off + (c * 3) // 2
        val = img[pos] | (img[pos+1] << 8)
        return (val >> 4) if (c & 1) else (val & 0x0FFF)

    def chain(start: int) -> list[int]:
        out, c = [], start
        while 2 <= c < 0xFF8:
            out.append(c)
            c = fat12(c)
        return out

    # Locate FDAUTO.BAT in the root directory
    target = None
    for i in range(nroot):
        base = root_off + i * 32
        if img[base] == 0:
            break
        if img[base] == 0xE5:
            continue
        name = bytes(img[base:base+8]).decode('ascii', 'replace').rstrip()
        ext  = bytes(img[base+8:base+11]).decode('ascii', 'replace').rstrip()
        full = f'{name}.{ext}' if ext else name
        if full == 'FDAUTO.BAT':
            target = base
            break

    if target is None:
        sys.exit('FDAUTO.BAT not found in root directory of ' + path)

    first  = struct.unpack('<H', img[target+26:target+28])[0]
    oldsz  = struct.unpack('<I', img[target+28:target+32])[0]
    clist  = chain(first)
    print(f'FDAUTO.BAT: first_cluster={first}, old_size={oldsz}, clusters={clist}')

    # Zero every cluster the file occupies, then write the stub into cluster 0
    for c in clist:
        sec = data_off + (c - 2) * spc * bps
        img[sec:sec + spc * bps] = b'\x00' * (spc * bps)

    sec0 = data_off + (clist[0] - 2) * spc * bps
    img[sec0:sec0 + len(NEW_CONTENT)] = NEW_CONTENT

    # Update directory-entry size so DOS reads only our stub
    img[target+28:target+32] = struct.pack('<I', len(NEW_CONTENT))

    with open(path, 'wb') as f:
        f.write(img)
    print(f'Patched {path}: FDAUTO.BAT now {len(NEW_CONTENT)} bytes (stub)')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: python3 tools/patch_fdauto.py <dos.img>')
    main(sys.argv[1])
