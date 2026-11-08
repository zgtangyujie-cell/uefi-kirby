"""Dump every symbol-table entry for a given name, with raw Mach-O fields.

Mach-O `nlist_64` layout (16 bytes):
    uint32 n_strx
    uint8  n_type
    uint8  n_sect
    uint16 n_desc
    uint64 n_value

`n_type` bit layout:
    N_STAB = 0xe0   debugger symbol table entry
    N_PEXT = 0x10   private external
    N_TYPE = 0x0e   type mask: 0x00=N_UNDF, 0x02=N_ABS, 0x0a=N_INDR, 0x0e=N_SECT
    N_EXT  = 0x01   external

So the "32" I once wrote down as N_UNDF is really the `n_sect` byte (section index),
not a `n_type` value at all.
"""

import struct
import sys
import zlib


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
                continue                      # long-filename slot
            out.append((raw[0:11], raw[11],
                        struct.unpack_from("<H", raw, 26)[0],
                        struct.unpack_from("<I", raw, 28)[0]))
        return out

    offset = cluster_offset(3)               # EFI
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
    path = sys.argv[1]
    wanted = sys.argv[2] if len(sys.argv) > 2 else "_PE_state"
    kernel = load_kernel(path)
    ncmds = struct.unpack_from("<I", kernel, 16)[0]
    offset = 32
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", kernel, offset)
        if cmd == 0x2:
            symtab = struct.unpack_from("<IIII", kernel, offset + 8)
        offset += size
    if symtab is None:
        raise SystemExit("no LC_SYMTAB")
    symoff, nsyms, stroff, strsize = symtab

    print("%s  (kernel %d bytes)" % (path, len(kernel)))
    print("entries for %r:" % wanted)
    print("  %-6s %-22s %-6s %-8s %-6s %-8s %s"
          % ("idx", "n_strx", "n_type", "(bits)", "n_sect", "n_desc", "n_value"))
    found = 0
    for index in range(nsyms):
        strx, ntype, nsect, ndesc, value = struct.unpack_from(
            "<IBBHQ", kernel, symoff + index * 16)
        if strx >= strsize:
            continue
        end = kernel.find(b"\0", stroff + strx)
        name = kernel[stroff + strx:end].decode("utf-8", "replace")
        if name != wanted:
            continue
        found += 1
        kind = ntype & 0x0E
        label = {0x00: "N_UNDF", 0x02: "N_ABS", 0x0A: "N_INDR",
                 0x0E: "N_SECT"}.get(kind, "type_0x%02X" % kind)
        bits = label + ("|N_EXT" if ntype & 0x01 else "")
        print("  %-6d %-22d 0x%02X    %-6s %-8d 0x%04X   0x%X"
              % (index, strx, ntype, bits, nsect, ndesc, value))
    print()
    if not found:
        print("NOT FOUND in the symbol table")
        return 1
    print("%d entr%s for %s" % (found, "y" if found == 1 else "ies", wanted))
    print()
    print("n_type bit layout: N_STAB=0xe0  N_PEXT=0x10  N_TYPE=0x0e  N_EXT=0x01")
    print("  N_UNDF=0x00  N_ABS=0x02  N_INDR=0x0a  N_SECT=0x0e")
    print("  n_sect is a SECTION INDEX, unrelated to n_type.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
