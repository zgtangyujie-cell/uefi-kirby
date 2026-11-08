"""Follow the two early-exit branches inside _initialize_screen.

_initialize_screen reads PE_state.video (x20) and then:

    0x3c0cb4  cbz  x21, 0x3c0d24     ; x21 = v_baseAddr
    0x3c0ce8  cbz  x23, 0x3c0d68     ; x23 = v_length

If either target skips the stores that build _vinfo, the console's
`v->v_baseaddr == 0` guard rejects every message and the panel stays blank -
no matter how correct PE_state.video itself is.

Usage: follow_branches.py <boot.img>
"""

import struct
import sys
import zlib

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM


def load_kernel(path):
    data = open(path, "rb").read()
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
    raise SystemExit("kernel.macho not found")


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    kernel = load_kernel(sys.argv[1])
    ncmds = struct.unpack_from("<I", kernel, 16)[0]
    offset = 32
    segs = []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", kernel, offset)
        if cmd == 0x19:
            name = kernel[offset + 8:offset + 24].decode("ascii", "replace").strip("\x00")
            vm, vs, fo, fs = struct.unpack_from("<QQQQ", kernel, offset + 24)
            segs.append((name, vm, vs, fo, fs))
        offset += size

    def file_offset(va):
        for _name, vm, vs, fo, fs in segs:
            if vm <= va < vm + min(vs, fs):
                return fo + (va - vm)
        return None

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True

    def show(start, length, label):
        print("=" * 70)
        print(label)
        print("=" * 70)
        base = None
        page = None
        for ins in md.disasm(kernel[file_offset(start):file_offset(start) + length], start):
            note = ""
            if ins.mnemonic == "adrp":
                try:
                    page = int(ins.op_str.split("#")[1], 16)
                except (IndexError, ValueError):
                    page = None
            elif ins.mnemonic == "add" and page is not None and "#0x" in ins.op_str:
                try:
                    imm = int(ins.op_str.split("#")[1], 16)
                except ValueError:
                    imm = 0
                reg = ins.op_str.split(",")[0].strip()
                if page + imm == 0xFFFFFFF007AB6970:
                    base = reg
                    note = "   ← %s = _vinfo" % reg
            elif ins.mnemonic in ("str", "strb", "stur", "stp") and base and base + "," in ins.op_str:
                if "[" + base in ins.op_str.split(",", 1)[1]:
                    note = "   ← ★ writes _vinfo"
            elif ins.mnemonic == "ret":
                note = "   ← RETURNS HERE"
            print("  0x%x  %-8s %-30s%s" % (ins.address, ins.mnemonic, ins.op_str, note))
        print()

    show(0xFFFFFFF0073C0D24, 0x44, "branch taken when PE_state.video.v_baseAddr == 0  (0x3c0cb4 cbz x21)")
    show(0xFFFFFFF0073C0D68, 0x4C, "branch taken when PE_state.video.v_length == 0     (0x3c0ce8 cbz x23)")
    print("Interpretation: a branch that reaches `ret` without writing _vinfo means the")
    print("console guard will reject every message, even with a correct PE_state.video.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
