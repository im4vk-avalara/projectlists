#!/usr/bin/env python3
"""Assemble a polyglot file: 512-byte MBR + minimal PDF + ZIP archive.

Layout (1024-byte budget):

  0x000..0x067   boot code + banner string  (from boot.bin, NASM output)
  0x068..0x???   PDF body  (overlaid onto the boot sector's zero pad)
  0x???..0x1FD   leftover zero pad
  0x1FE..0x1FF   55 AA boot signature
  0x200..end     ZIP archive  (Local File Header + data + CD + EOCD)

ZIP record layout (PKZIP APPNOTE):

  Local File Header   PK\\3\\4   30 B + filename + extra
  File data                     raw bytes, method 0 (stored)
  Central Directory   PK\\1\\2   46 B + filename + extra + comment
  End of CD record    PK\\5\\6   22 B + comment

All ZIP numbers little-endian.  Compression is "stored" (method 0) so that
the data is byte-identical to readme.txt and we don't need a deflate codec.

PDF body is a 3-object minimum-viable PDF:
  obj 1: /Catalog
  obj 2: /Pages with one /Kid
  obj 3: /Page  (100x100 MediaBox)
  xref + trailer + startxref + %%EOF
Cross-reference offsets are PDF-relative (counted from %PDF-, not from
byte 0 of the containing image).  This works cleanly for pdfinfo, qpdf,
and macOS PDFKit even though the PDF sits behind a 104-byte boot-code
prefix.  See build_pdf() for the empirical comparison.
"""
import argparse, struct, sys, zlib

LFH_SIG  = 0x04034B50    # "PK\3\4"
CDFH_SIG = 0x02014B50    # "PK\1\2"
EOCD_SIG = 0x06054B50    # "PK\5\6"

# 1980-01-01 00:00:00 — arbitrary fixed timestamp so builds are reproducible.
DOS_TIME = 0
DOS_DATE = (0 << 9) | (1 << 5) | 1     # year-1980=0, month=1, day=1

# Where the PDF body lands inside the boot sector.  Just past the last
# byte of executable boot code (0x067) — replaces the temporary zero pad
# that Stage 2 left.  Bytes 0x1FE..0x1FF (boot signature) stay untouched.
PDF_FILE_OFFSET = 0x068

def build_lfh(name: bytes, data: bytes, crc: int) -> bytes:
    return struct.pack(
        "<IHHHHHIIIHH",
        LFH_SIG,
        20,                 # version needed = 2.0
        0,                  # general-purpose bit flag
        0,                  # method = stored
        DOS_TIME,
        DOS_DATE,
        crc,
        len(data),          # compressed size
        len(data),          # uncompressed size
        len(name),
        0,                  # extra field length
    ) + name

def build_cdfh(name: bytes, data: bytes, crc: int, lfh_offset: int) -> bytes:
    return struct.pack(
        "<IHHHHHHIIIHHHHHII",
        CDFH_SIG,
        20,                 # version made by  = 2.0
        20,                 # version needed   = 2.0
        0,                  # flag
        0,                  # method = stored
        DOS_TIME,
        DOS_DATE,
        crc,
        len(data),
        len(data),
        len(name),
        0,                  # extra field length
        0,                  # file comment length
        0,                  # disk number start
        0,                  # internal file attributes
        0,                  # external file attributes
        lfh_offset,         # offset of LFH relative to start of archive
    ) + name

def build_eocd(cd_offset: int, cd_size: int) -> bytes:
    return struct.pack(
        "<IHHHHIIH",
        EOCD_SIG,
        0,                  # number of this disk
        0,                  # disk where CD starts
        1,                  # CD records on this disk
        1,                  # total CD records
        cd_size,
        cd_offset,
        0,                  # comment length
    )

def build_pdf() -> bytes:
    """Build a minimal valid PDF body — 3 objects (Catalog + Pages + Page),
    xref table, trailer, %%EOF.

    Offsets in the xref table and the startxref value are **PDF-relative**
    (counted from the %PDF- header, not from byte 0 of the containing file).
    This is the interpretation that makes every major parser happy when the
    PDF is preceded by a non-PDF prefix:

      tool      file-relative offsets    PDF-relative offsets
      --------  --------------------     ---------------------
      pdfinfo   clean                    clean
      PDFKit    3 debug warnings         silent
      qpdf      "file is damaged",       "No syntax or stream
                reconstructs xref         encoding errors found"

    Returned bytes are intended to be SPLICED into the image at some offset
    (not appended).  All line endings are LF.
    """
    header = b"%PDF-1.4\n"
    obj1   = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    obj2   = b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    obj3   = b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"

    o1 = len(header)
    o2 = o1 + len(obj1)
    o3 = o2 + len(obj2)
    xref_offset = o3 + len(obj3)

    # xref entries are exactly 20 bytes each (10-digit offset, space,
    # 5-digit gen, space, 'n'/'f', space, LF).  Object 0 is the head of
    # the free list (gen=65535, offset=0).
    xref = (
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        + f"{o1:010d} 00000 n \n".encode("ascii")
        + f"{o2:010d} 00000 n \n".encode("ascii")
        + f"{o3:010d} 00000 n \n".encode("ascii")
    )
    trailer = b"trailer<</Size 4/Root 1 0 R>>\n"
    tail = (
        b"startxref\n"
        + f"{xref_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )
    return header + obj1 + obj2 + obj3 + xref + trailer + tail

def overlay(buf: bytes, at: int, payload: bytes) -> bytes:
    """Return a copy of `buf` with `payload` spliced in at offset `at`."""
    end = at + len(payload)
    if end > len(buf):
        sys.exit(f"PDF (size {len(payload)}) overflows boot sector at "
                 f"offset 0x{at:X} (would reach 0x{end:X}, max 0x{len(buf):X})")
    return buf[:at] + payload + buf[end:]

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("boot_bin",  help="512-byte boot sector from NASM")
    p.add_argument("readme",    help="text file to embed as the ZIP entry")
    p.add_argument("-o", "--out", default="boot.img", help="output polyglot")
    p.add_argument("--name", default="README.txt", help="filename inside ZIP")
    args = p.parse_args()

    boot = open(args.boot_bin, "rb").read()
    data = open(args.readme,   "rb").read()

    if len(boot) != 512:
        sys.exit(f"boot sector must be 512 B, got {len(boot)}")
    if boot[-2:] != b"\x55\xAA":
        sys.exit("boot signature 55 AA missing at offset 0x1FE")

    # ── overlay PDF body onto the boot-sector zero pad ────────────────
    pdf = build_pdf()
    boot = overlay(boot, PDF_FILE_OFFSET, pdf)
    # Re-confirm the signature survived (it must — PDF ends well before 0x1FE).
    assert boot[-2:] == b"\x55\xAA", "PDF overlay clobbered the boot signature"

    name = args.name.encode("ascii")
    crc  = zlib.crc32(data) & 0xFFFFFFFF

    lfh_offset  = len(boot)                       # 0x200
    lfh         = build_lfh(name, data, crc)
    data_offset = lfh_offset + len(lfh)
    cd_offset   = data_offset + len(data)
    cdfh        = build_cdfh(name, data, crc, lfh_offset)
    eocd_offset = cd_offset + len(cdfh)
    eocd        = build_eocd(cd_offset, len(cdfh))

    out = boot + lfh + data + cdfh + eocd
    open(args.out, "wb").write(out)

    pdf_end = PDF_FILE_OFFSET + len(pdf)
    print(
        f"Wrote {args.out}: {len(out)} bytes\n"
        f"  boot code    0x{0:04X}..0x{PDF_FILE_OFFSET-1:04X}   "
        f"({PDF_FILE_OFFSET} B)\n"
        f"  PDF body     0x{PDF_FILE_OFFSET:04X}..0x{pdf_end-1:04X}   "
        f"({len(pdf)} B, %PDF-1.4 ... %%EOF)\n"
        f"  zero pad     0x{pdf_end:04X}..0x01FD   "
        f"({0x1FE - pdf_end} B leftover)\n"
        f"  boot sig     0x01FE..0x01FF   (2 B, 55 AA)\n"
        f"  LFH          0x{lfh_offset:04X}..0x{data_offset-1:04X}   "
        f"({len(lfh)} B, PK\\3\\4)\n"
        f"  file data    0x{data_offset:04X}..0x{cd_offset-1:04X}   "
        f"({len(data)} B, stored, CRC32 0x{crc:08X})\n"
        f"  CDFH         0x{cd_offset:04X}..0x{eocd_offset-1:04X}   "
        f"({len(cdfh)} B, PK\\1\\2)\n"
        f"  EOCD         0x{eocd_offset:04X}..0x{len(out)-1:04X}   "
        f"({len(eocd)} B, PK\\5\\6)",
        file=sys.stderr,
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
