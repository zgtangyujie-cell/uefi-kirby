#!/usr/bin/env python3
"""Unpack an EDK2 firmware volume and search it for UTF-16 / ASCII strings.

Why this exists: `SILICIUM_UEFI-DEBUG.fd` is not a flat blob.  The main
firmware lives in an FFS file whose GUID is FFS3_GUID (FVMAIN_COMPACT), inside
a GUID_DEFINED section compressed with LZMA.  Searching the raw .fd for text
returns nothing even for strings that demonstrably reach the panel
(`DARWINBOOT: hand-off to the kernel`), which made me believe a patch had not
landed when it had (CHANNEL #502-#504).

Correct path:

    .fd  ->  FV header (_FVH)  ->  FFS files  ->  sections
         ->  GUID_DEFINED (98584EEE-1439-5942-9D6E-DC7BD79403CF)
         ->  LZMA (FORMAT_ALONE)  ->  decompressed firmware  ->  search

Usage:
    dump_fv.py <firmware.fd> [needle ...]
    dump_fv.py <firmware.fd> --list        # just the FFS/section tree

Each needle is searched as ASCII and as UTF-16LE, and matching offsets are
reported in the decompressed image.  Exit 0 when every needle was found,
1 when at least one is missing, 2 when the file cannot be parsed.
"""

import lzma
import struct
import sys
import uuid

FV_SIGNATURE_OFFSET = 40                      # `_FVH` sits at FV header + 40
FFS3_GUID_LZMA = "ee4e5898-3914-4259-9d6e-dc7bd79403cf"
FFS3_GUID = "9e21fd93-9c72-4c15-8c4b-e77f1db2d792"
SECTION_COMPRESSION = 0x01
SECTION_GUID_DEFINED = 0x02
SECTION_RAW = 0x19


def guids(data, offset):
    return str(uuid.UUID(bytes_le=data[offset:offset + 16]))


def walk_sections(data, start, end, depth, out):
    """Append (depth, kind, guid_or_type, offset, size) for each section."""
    off = start
    while off + 4 <= end:
        size = struct.unpack_from("<I", data, off)[0] & 0xFFFFFF
        kind = data[off + 3]
        if size < 4 or off + size > end:
            break
        if kind == SECTION_GUID_DEFINED:
            data_off = struct.unpack_from("<H", data, off + 20)[0]
            out.append((depth, "GUID_DEFINED", guids(data, off + 4), off, size))
            inner_start = off + data_off
            inner_end = off + size
            # An LZMA section has no nested sections; a plain GUID_DEFINED may.
            if guids(data, off + 4) == FFS3_GUID_LZMA:
                out.append((depth + 1, "LZMA_PAYLOAD", "", inner_start,
                            inner_end - inner_start))
            else:
                walk_sections(data, inner_start, inner_end, depth + 1, out)
        elif kind == SECTION_COMPRESSION:
            uncompressed = struct.unpack_from("<I", data, off + 4)[0]
            out.append((depth, "COMPRESSION", "uncompressed=%d" % uncompressed,
                        off, size))
        else:
            names = {0x03: "PEI", 0x0A: "FIRMWARE_VOLUME_IMAGE",
                     SECTION_RAW: "RAW", 0x14: "VERSION", 0x15: "UI"}
            out.append((depth, names.get(kind, "type_0x%02X" % kind), "", off, size))
        off = (off + size + 3) & ~3


def unpack(data):
    """Return (decompressed_blobs, listing_lines)."""
    blobs = []
    lines = []
    fvh = data.find(b"_FVH")
    if fvh < 0:
        raise SystemExit("no _FVH: this file is not a firmware volume")
    fv = fvh - FV_SIGNATURE_OFFSET
    fv_length = struct.unpack_from("<Q", data, fv + 32)[0]
    header_len = struct.unpack_from("<H", data, fv + 48)[0]
    lines.append("FV      off=0x%-6x length=%d (%.2f MB) header_len=%d"
                 % (fv, fv_length, fv_length / 2**20, header_len))
    fv_end = min(fv + fv_length, len(data))

    off = fv + header_len
    count = 0
    while off + 24 <= fv_end:
        name = data[off:off + 16]
        if name == bytes(16):
            break
        size = struct.unpack_from("<I", data, off + 20)[0] & 0xFFFFFF
        kind = data[off + 18]
        if size < 24 or off + size > fv_end:
            break
        g = guids(data, off)
        lines.append("  FFS   off=0x%-6x type=0x%02X size=%7d guid=%s"
                     % (off, kind, size, g))
        sections = []
        walk_sections(data, off + 24, off + size, 1, sections)
        for depth, what, extra, soff, ssize in sections:
            lines.append("  %s%-14s off=0x%-6x size=%7d %s"
                         % ("    " * depth, what, soff, ssize, extra))
            if what == "LZMA_PAYLOAD":
                blob = data[soff:soff + ssize]
                try:
                    decoded = lzma.decompress(blob, format=lzma.FORMAT_ALONE)
                except lzma.LZMAError as error:
                    lines.append("  %sLZMA decode failed: %s"
                                 % ("    " * (depth + 1), error))
                    continue
                lines.append("  %s-> decoded %d bytes (%.2f MB)"
                             % ("    " * (depth + 1), len(decoded),
                                len(decoded) / 2**20))
                blobs.append(decoded)
        off = (off + size + 7) & ~7
        count += 1
    lines.insert(1, "  %d FFS file(s)" % count)
    return blobs, lines


def search(blobs, needle):
    hits = []
    for label, blob in blobs:
        for encoding, tag in ((needle.encode("ascii"), "ascii"),
                              (needle.encode("utf-16-le"), "utf16")):
            index = blob.find(encoding)
            while index >= 0:
                hits.append((label, tag, index))
                index = blob.find(encoding, index + 1)
                if len(hits) > 12:
                    return hits
    return hits


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    try:
        data = open(path, "rb").read()
    except OSError as error:
        print("%s: %s" % (path, error))
        return 2
    print("%s  %d bytes" % (path, len(data)))
    try:
        blobs, lines = unpack(data)
    except SystemExit as error:
        print(error)
        return 2
    print("\n".join(lines))
    labelled = [("vfmain[%d]" % i, blob) for i, blob in enumerate(blobs)]
    if not labelled:
        print("no compressed firmware found")
        return 1
    if len(sys.argv) == 2 or "--list" in sys.argv[2:]:
        return 0
    print()
    missing = 0
    for needle in [a for a in sys.argv[2:] if a != "--list"]:
        hits = search(labelled, needle)
        if hits:
            where = ", ".join("%s@%s0x%X" % (label, tag, off)
                              for label, tag, off in hits[:4])
            print("FOUND    %-30s %s" % (needle, where))
        else:
            print("MISSING  %-30s" % needle)
            missing += 1
    print()
    if missing:
        print("FAIL: %d needle(s) missing from the decompressed firmware"
              % missing)
        return 1
    print("PASS: every needle found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
