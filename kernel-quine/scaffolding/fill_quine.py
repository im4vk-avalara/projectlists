#!/usr/bin/env python3
# Bootstrap helper: substitute the byte-list into quine_template.asm.
# Reads template on stdin, writes final source on stdout.
# Does ONE thing: replace the line "        db __BYTES__\n" with
#   "        db <b1>, <b2>, ..., <bN>\n"
# where the bytes are (template - that line + a single SENTINEL byte 0).
import sys

template = sys.stdin.buffer.read()
marker = b"        db __BYTES__\n"
idx = template.find(marker)
if idx == -1:
    sys.exit("marker not found in template")

prefix = template[:idx]
suffix = template[idx + len(marker):]

data = prefix + b"\x00" + suffix
db_line = b"        db " + b", ".join(str(b).encode() for b in data) + b"\n"

sys.stdout.buffer.write(prefix + db_line + suffix)
