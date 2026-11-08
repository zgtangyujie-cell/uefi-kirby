"""Inspect the APFS container and volume superblocks in a restore ramdisk.

`caihong/board.toml:141-147` requires `root_match_volume_uuid` to be the GUID of the
partition carrying the root image, and `nx769j.md:75` warns that it is the *volume*
UUID, not the container UUID (the container's belongs to the synthesized whole-disk
IOMedia, which never mounts).

Checksums are not validated here; this only reports field values at the offsets APFS
defines, so a wrong offset shows up immediately as an implausible number.
"""

import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")

NXSB = b"NXSB"
APSB = b"APSB"


def pretty(raw):
    if len(raw) != 16:
        return raw.hex()
    return "%s-%s-%s-%s-%s" % (
        raw[0:4].hex().upper(), raw[4:6].hex().upper(), raw[6:8].hex().upper(),
        raw[8:10].hex().upper(), raw[10:16].hex().upper())


def show(block, base, label):
    print(f"  {label} magic at +0x{base - 0:02x}"
          if base else f"  {label}")
    block_size = struct.unpack_from("<I", block, base + 4)[0]
    block_count = struct.unpack_from("<Q", block, base + 8)[0]
    print(f"    block_size   {block_size}")
    print(f"    block_count  {block_count:,}")


def main() -> int:
    path = sys.argv[1]
    data = open(path, "rb").read()
    print(f"{path}  {len(data):,} bytes")

    nx = data.find(NXSB)
    print(f"NXSB offset      {nx}")
    if nx < 0:
        return 1

    # NXSB lives inside an object header; the block starts 32 bytes before the magic.
    block = nx - 32
    print()
    print("=== container superblock (NXSB) ===")
    print(f"  object header at 0x{block:x}")
    block_size = struct.unpack_from("<I", data, block + 32 + 4)[0]
    block_count = struct.unpack_from("<Q", data, block + 32 + 8)[0]
    print(f"  block_size    {block_size}")
    print(f"  block_count   {block_count:,}")
    if block_size:
        print(f"  container size {block_count * block_size:,} bytes")
    container_uuid = data[block + 32 + 0x20:block + 32 + 0x30]
    print(f"  container UUID {pretty(container_uuid)}")
    print("  ^ nx769j.md:75 says root-matching does NOT use this one.")

    print()
    print("=== scanning for APSB (volume superblocks) ===")
    found = 0
    for offset in range(0, len(data) - 4096, 4096):
        window = data[offset:offset + 4096]
        if window[32:36] != APSB:
            continue
        volume_uuid = window[32 + 0xF0:32 + 0x100]
        name = window[32 + 0x160:32 + 0x160 + 256].split(b"\0")[0].decode("utf-8", "replace")
        found += 1
        print(f"  block {offset // 4096:>7}  vol_uuid {pretty(volume_uuid)}  name={name!r}")
        if found >= 8:
            break
    if not found:
        print("  no APSB found")
        return 1
    print()
    print("caihong/board.toml:141-147 wants the volume UUID above, and the same value")
    print("passed as --os-guid to the userdata builder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
