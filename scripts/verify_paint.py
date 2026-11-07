#!/usr/bin/env python3
"""Check that a probe image paints a band instead of resetting.

`--paint-after` is a different animal from `--reset-after`: the cave must end
with `bl <callee>` + `ret` and must contain framebuffer stores, and it must NOT
contain the PSCI reset sequence (`movz w0, #0x9` / `movk w0, #0x8400` / `smc #0`).

Us the same cave locations the probe uses, so this works on the boot image the
same way `verify_all_sites.py` does.

Usage:
    verify_paint.py <boot.img> [--band N]

Exit status 0 only when the cave paints, calls and returns and contains no
reset sequence.
"""

import io
import struct
import sys
import zlib
from pathlib import Path

TEXT_EXEC_VM = 0xFFFFFFF007238000
TEXT_EXEC_FILEOFF = 0x234000
CAVE4 = 0xFFFFFFF0073F0620

# Encodings taken from a real cave in Mu-kirby-cc887b0.img:
#   0x52800120  mov  w0, #9
#   0x72B08000  movk w0, #0x8400, lsl #16
#   0xD4000003  smc  #0
#   0xD65F03C0  ret
MOVZ_W0_9 = 0x52800120
MOVK_W0_8400 = 0x72B08000
SMC_0 = 0xD4000003
RET = 0xD65F03C0

# stp wN, wN, [xN], #8 (post-index, 32-bit pair) — the paint inner loop.
STP_W_POST8 = (0x28807C00, 0xFFE07C00)


class Volume:
    def __init__(self, data):
        self.data = data
        self.spc = data[13]
        reserved = struct.unpack_from("<H", data, 14)[0]
        fats = data[16]
        self.root_entries = struct.unpack_from("<H", data, 17)[0]
        spf = struct.unpack_from("<H", data, 22)[0]
        self.data_start = reserved + fats * spf + (self.root_entries * 32) // 512
        self.root_offset = (reserved + fats * spf) * 512

    def cluster_offset(self, c):
        return (self.data_start + (c - 2) * self.spc) * 512

    def entries(self, offset):
        out = []
        for i in range(self.root_entries if offset == self.root_offset else 1024):
            raw = self.data[offset + i * 32:offset + (i + 1) * 32]
            if len(raw) < 32 or raw[0] == 0:
                break
            out.append({"name": raw[0:11], "attr": raw[11],
                        "cluster": struct.unpack_from("<H", raw, 26)[0],
                        "size": struct.unpack_from("<I", raw, 28)[0]})
        return out

    def find(self, offset, name):
        for e in self.entries(offset):
            if e["attr"] in (0x10, 0x20) and e["name"][:len(name)] == name:
                return e
        return None


def load_kernel(blob):
    comp = struct.unpack_from("<I", blob, 8)[0]
    stream = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
        blob[4096:4096 + comp])
    mark = stream.find(b"TB321FUESP")
    if mark < 0:
        raise SystemExit("no payload volume in the boot image")
    vol = Volume(stream[mark - 43:])
    off = vol.root_offset
    e = None
    for part in (b"EFI", b"UNIXNU", b"PAYLOADS", b"KERNEL~1MAC"):
        e = vol.find(off, part)
        if e is None:
            raise SystemExit("payload volume missing %r" % part)
        off = vol.cluster_offset(e["cluster"])
    s = vol.cluster_offset(e["cluster"])
    return vol.data[s:s + e["size"]]


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    img = Path(sys.argv[1])
    kernel = load_kernel(img.read_bytes())
    off = TEXT_EXEC_FILEOFF + (CAVE4 - TEXT_EXEC_VM)
    words = [struct.unpack_from("<I", kernel, off + i * 4)[0] for i in range(24)]

    print("%s : cave4 at %#x" % (img.name, CAVE4))
    print("  " + " ".join("%08X" % w for w in words[:12]))

    has_smc = SMC_0 in words
    has_movz9 = MOVZ_W0_9 in words
    has_movk = MOVK_W0_8400 in words
    has_ret = RET in words
    has_store = any((w & STP_W_POST8[1]) == STP_W_POST8[0] for w in words)
    has_bl = any((w >> 26) == 0b100101 for w in words)

    print()
    print("  framebuffer store (stp w,w,[x],#8): %s" % ("yes" if has_store else "NO"))
    print("  bl <callee>                       : %s" % ("yes" if has_bl else "NO"))
    print("  ret                               : %s" % ("yes" if has_ret else "NO"))
    print("  PSCI reset (smc #0)               : %s" % ("present" if has_smc else "absent"))
    print("  reset preamble (movz/movk 0x84000009): %s"
          % ("present" if (has_movz9 and has_movk) else "absent"))

    print()
    if has_smc or (has_movz9 and has_movk):
        print("RESULT: this cave RESETS, not paints -- wrong probe mode")
        return 1
    if not (has_store and has_bl and has_ret):
        print("RESULT: cave is neither a clean paint nor a reset -- inspect it")
        return 2
    print("RESULT: paint confirmed (paints a band, calls the target, returns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
