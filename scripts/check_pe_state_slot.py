"""Identify what lives at PE_state + 0x10A0, the slot elden patched.

The v50 console pokes write 0xFFFFFFF0073BB01C into `_PE_state + 0x10A0`.  If that
slot is a function pointer the kernel calls, knowing which function stores it and
which function calls it explains why poking it made text appear.

Usage: check_pe_state_slot.py <boot.img | kernel.macho> [--offset 0x10a0]
"""

import struct
import sys
import zlib

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PE_STATE = 0xFFFFFFF0071FC8D0
DEFAULT_OFFSET = 0x10A0


def load_kernel(path):
    data = open(path, "rb").read()
    if data[:4] == b"\xcf\xfa\xed\xfe":
        return data
    size = struct.unpack_from("<I", data, 8)[0]
    blob = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data[4096:4096 + size])
    mark = blob.find(b"TB321FUESP")
    volume = blob[mark - 43:]
    spc = volume[13]
    reserved = struct.unpack_from("<H", volume, 14)[0]
    fats = volume[16]
    root_entries = struct.unpack_from("<H", volume, 17)[0]
    spf = struct.unpack_from("<H", volume, 22)[0]
    data_start = reserved + fats * spf + (root_entries * 32) // 512

    def cluster_offset(cluster):
        return (data_start + (cluster - 2) * spc) * 512

    def entries(offset, n=64):
        out = []
        for index in range(n):
            raw = volume[offset + index * 32:offset + (index + 1) * 32]
            if len(raw) < 32 or raw[0] == 0:
                break
            if raw[11] & 0x0F:
                continue
            out.append((raw[0:11], raw[11],
                        struct.unpack_from("<H", raw, 26)[0],
                        struct.unpack_from("<I", raw, 28)[0]))
        return out

    offset = cluster_offset(3)
    for want in ("UNIXNU", "PAYLOADS"):
        for name, attr, cluster, size in entries(offset):
            if attr == 0x10 and name[:len(want)] == want.encode():
                offset = cluster_offset(cluster)
                break
    for name, attr, cluster, size in entries(offset):
        if attr == 0x20 and size > 1000000:
            return volume[cluster_offset(cluster):cluster_offset(cluster) + size]
    raise SystemExit("kernel.macho not found in payload")


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    offset = DEFAULT_OFFSET
    for index, item in enumerate(sys.argv):
        if item == "--offset" and index + 1 < len(sys.argv):
            offset = int(sys.argv[index + 1], 0)
    kernel = load_kernel(sys.argv[1])

    ncmds = struct.unpack_from("<I", kernel, 16)[0]
    cursor = 32
    segs = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", kernel, cursor)
        if cmd == 0x19:
            name = kernel[cursor + 8:cursor + 24].decode("ascii", "replace").strip("\x00")
            vm, vs, fo, fs = struct.unpack_from("<QQQQ", kernel, cursor + 24)
            segs.append((name, vm, vs, fo, fs))
        cursor += size

    def file_offset(va):
        for _name, vm, vs, fo, fs in segs:
            if vm <= va < vm + min(vs, fs):
                return fo + (va - vm)
        return None

    slot = PE_STATE + offset
    print(f"_PE_state        = {PE_STATE:#x}")
    print(f"slot             = {slot:#x}  (_PE_state + {offset:#x})")

    raw = file_offset(slot)
    if raw is None:
        print("  slot is outside any file-backed segment (BSS or padding)")
    else:
        value = struct.unpack_from("<Q", kernel, raw)[0]
        print(f"  current 8 bytes = {value:#018x}")

    print()
    print("=== instructions that reference this slot (adrp+add or adrp+ldr/st) ===")
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    found = 0
    for name, vm, vs, fo, fs in segs:
        if fs == 0:
            continue
        page = None
        for step in range(0, fs - 3, 4):
            word = struct.unpack_from("<I", kernel, fo + step)[0]
            if (word & 0x9F000000) == 0x90000000:          # adrp
                immlo = (word >> 29) & 3
                immhi = (word >> 5) & 0x7FFFF
                imm = (immhi << 2) | immlo
                if imm & (1 << 20):
                    imm -= 1 << 21
                page = ((vm + step) & ~0xFFF) + imm * 4096
                continue
            if page is None:
                continue
            # ADD (immediate) 64-bit: 1001000100 shift imm12 Rn Rd
            if (word & 0xFF800000) == 0x91000000:
                imm12 = (word >> 10) & 0xFFF
                if page + imm12 == slot:
                    va = vm + step
                    print(f"  {va:#x}  {name}  add  → slot")
                    found += 1
            # LDR/STR (unsigned offset) 64-bit with imm12*8
            if (word & 0xFFC00000) == 0xF9400000 or (word & 0xFFC00000) == 0xF9000000:
                imm12 = ((word >> 10) & 0xFFF) * 8
                if page + imm12 == slot:
                    va = vm + step
                    kind = "ldr" if (word & 0xFFC00000) == 0xF9400000 else "str"
                    print(f"  {va:#x}  {name}  {kind}  → slot")
                    found += 1
            if found > 20:
                break
        if found > 20:
            break
    if not found:
        print("  no direct adrp-based reference (the slot may be reached through a base register)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
