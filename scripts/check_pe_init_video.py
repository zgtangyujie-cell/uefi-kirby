"""Disassemble _PE_init_platform and decide whether it writes PE_state.video.

`_PE_init_platform` starts by loading `PE_state.initialized` at `PE_state + 0x8D0`,
because `_PE_state` itself sits at page offset 0x8D0 inside the page
0xFFFFFFF0071FC000.  After that test it builds `x8 = _PE_state` and then writes
several fields through `[x8, #off]`.  The question this answers is whether one of
those stores lands on `PE_state.video` (offset +0x08).

Usage: check_pe_init_video.py <boot.img | kernel.macho>
"""

import struct
import sys
import zlib

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PE_STATE = 0xFFFFFFF0071FC8D0
PAGE = PE_STATE & ~0xFFF
PAGE_OFF = PE_STATE & 0xFFF


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
    raise SystemExit("kernel.macho not found")


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    kernel = load_kernel(sys.argv[1])
    ncmds = struct.unpack_from("<I", kernel, 16)[0]
    offset = 32
    segs = []
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", kernel, offset)
        if cmd == 0x19:
            name = kernel[offset + 8:offset + 24].decode("ascii", "replace").strip("\x00")
            vm, vs, fo, fs = struct.unpack_from("<QQQQ", kernel, offset + 24)
            segs.append((name, vm, vs, fo, fs))
        elif cmd == 0x2:
            symtab = struct.unpack_from("<IIII", kernel, offset + 8)
        offset += size

    def file_offset(va):
        for _name, vm, vs, fo, fs in segs:
            if vm <= va < vm + min(vs, fs):
                return fo + (va - vm)
        return None

    symoff, nsyms, stroff, strsize = symtab
    target = None
    for index in range(nsyms):
        strx, ntype, _sect, _desc, value = struct.unpack_from(
            "<IBBHQ", kernel, symoff + index * 16)
        if (ntype & 0x0E) != 0x0E or not value or strx >= strsize:
            continue
        end = kernel.find(b"\0", stroff + strx)
        if kernel[stroff + strx:end].decode("utf-8", "replace") == "_PE_init_platform":
            target = value
            break
    if target is None:
        raise SystemExit("_PE_init_platform not in the symbol table")

    print("_PE_init_platform = %#x" % target)
    print("_PE_state         = %#x   (page %#x + %#x)" % (PE_STATE, PAGE, PAGE_OFF))
    print()
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    base = None          # register holding _PE_state
    page = None
    hits = []
    for ins in md.disasm(kernel[file_offset(target):file_offset(target) + 0x100], target):
        text = ins.op_str
        if ins.mnemonic == "adrp":
            try:
                page = int(text.split("#")[1], 16)
            except (IndexError, ValueError):
                page = None
        elif ins.mnemonic == "add" and page is not None and "#0x" in text:
            try:
                imm = int(text.split("#")[1], 16)
            except ValueError:
                imm = 0
            reg = text.split(",")[0].strip()
            if page + imm == PE_STATE:
                base = reg
                print("  %#x  %-6s %-26s → %s = _PE_state" % (ins.address, ins.mnemonic, text, reg))
        elif ins.mnemonic in ("str", "strb", "stur", "stp") and base and base + "," in text:
            following = text.split(",", 1)[1]
            if "[" + base in following:
                try:
                    imm = int(following.split("#")[1].split("]")[0], 16) if "#0x" in following else 0
                except ValueError:
                    imm = -1
                field = {0x00: "initialized", 0x08: "★ video", 0x98: "deviceTreeHead",
                         0xA0: "bootArgs", 0xA8: "deviceTreeSize"}.get(imm, "")
                print("  %#x  %-6s %-26s → PE_state + %#04x  %s"
                      % (ins.address, ins.mnemonic, text, imm, field))
                if imm == 0x08:
                    hits.append(ins.address)
    print()
    if hits:
        print("RESULT: _PE_init_platform DOES write PE_state.video at %s"
              % ", ".join("%#x" % a for a in hits))
        return 0
    print("RESULT: _PE_init_platform does NOT write PE_state.video (+0x08)")
    print("        So _initialize_screen receives a zero PE_Video unless someone else fills it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
