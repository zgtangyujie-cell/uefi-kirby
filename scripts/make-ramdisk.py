#!/usr/bin/env python3
"""Extract the RestoreRamDisk from an IPSW as a bare APFS container.

The ramdisk is what makes /chosen/memory-map/RAMDisk useful: IOFindBSDRoot hands
that range to the filesystem layer as a root-device candidate, so a real APFS
container in memory is enough to find out whether APFS can actually mount
anything on this board - no partition writes, no userdata, no lzfse.

Why this is plain Python: the IPSW member is an IM4P wrapper, not an encrypted
disk image.  Measured on 044-75545-038.dmg (iPad7,1 17.7.11 21H461):

    offset  0  30 84 0b 00   ASN.1 DER sequence
    offset  8  "IM4P"
    offset 14  "rdsk"
    offset 21  04 84 0b 00 00 00   OCTET STRING, length
    offset 59  "NXSB"              APFS container object map

    184,549,403 - 59 = 184,549,344  == the extracted size byte for byte

So the payload is already the raw container; only the wrapper has to go.  The
offset is found by searching for NXSB rather than hardcoding 59, because the
DER length field width is not guaranteed across builds.
"""

import argparse
import sys
import zipfile
from pathlib import Path

MAGIC = b"NXSB"
SEARCH = 4096


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipsw", required=True, type=Path)
    parser.add_argument("--member", default="044-75545-038.dmg",
                        help="IPSW member carrying the restore ramdisk")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.ipsw.is_file():
        print(f"IPSW not found: {args.ipsw}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.ipsw) as archive:
        try:
            info = archive.getinfo(args.member)
        except KeyError:
            names = [n for n in archive.namelist() if n.endswith(".dmg")]
            print(f"{args.member} not in {args.ipsw.name}; dmg members: {names}", file=sys.stderr)
            return 1
        with archive.open(info) as source:
            head = source.read(SEARCH)
            offset = head.find(MAGIC)
            if offset < 0:
                print(f"no {MAGIC!r} in the first {SEARCH} bytes of {args.member}; "
                      "this member is not a wrapped APFS container", file=sys.stderr)
                return 1
            with args.output.open("wb") as target:
                target.write(head[offset:])
                while True:
                    chunk = source.read(8 << 20)
                    if not chunk:
                        break
                    target.write(chunk)

    size = args.output.stat().st_size
    expected = info.file_size - offset
    if size != expected:
        print(f"short write: {size} != {expected}", file=sys.stderr)
        return 1

    with args.output.open("rb") as check:
        magic = check.read(4)
        block_size = int.from_bytes(check.read(4), "little")
        block_count = int.from_bytes(check.read(8), "little")
    print(f"ramdisk: {args.member} -{offset} bytes -> {args.output} "
          f"({size} bytes = {size / 2**20:.1f} MiB)")
    print(f"ramdisk: magic={magic!r} block_size={block_size} block_count={block_count}"
          f" -> {block_size * block_count / 2**20:.1f} MiB of container")
    return 0


if __name__ == "__main__":
    sys.exit(main())
