#!/usr/bin/env python3
"""Build the FAT16 payload volume that UniXNU reads from the boot image ramdisk.

Windows has no mtools, so the filesystem is written by hand. The layout is a
plain FAT16 volume with 4 KiB clusters and VFAT long file names, which both the
EDK2 FAT driver and the UniXNU payload reader accept.

    python mkpayload.py --output payload.img \
        --add EFI/UniXNU/unixnu.toml=unixnu.toml

Paths given to --add are the on-image path and the local source file, separated
by '='. Directories are created as needed.
"""
import argparse
import struct
from pathlib import Path

SECTOR = 512
SECTORS_PER_CLUSTER = 8
RESERVED_SECTORS = 1
NUM_FATS = 2
ROOT_ENTRIES = 512
MEDIA = 0xF8

ATTR_DIR = 0x10
ATTR_ARCHIVE = 0x20
ATTR_LFN = 0x0F


def lfn_checksum(short_name):
    total = 0
    for byte in short_name:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


def short_name_for(name):
    """Return an 8.3 short name for a long name, unique enough for our tree."""
    if "." in name:
        base, ext = name.rsplit(".", 1)
    else:
        base, ext = name, ""
    base = base.upper()
    ext = ext.upper()
    if len(base) <= 8 and len(ext) <= 3:
        return (base.ljust(8) + ext.ljust(3)).encode("ascii")
    short_base = base[:6] + "~1" if len(base) > 8 or len(ext) > 3 else base
    short_ext = ext[:3]
    return (short_base.ljust(8) + short_ext.ljust(3)).encode("ascii")


def _short_spelling(short_name):
    """The name an 8.3 entry spells, e.g. b"UNIXNU  TOM" -> "UNIXNU.TOM"."""
    text = short_name.decode()
    base = text[:8].rstrip()
    ext = text[8:].rstrip()
    return base + ("." + ext if ext else "")


def lfn_entries(name, short_name):
    """Build the VFAT long-name entries that precede the short entry.

    The comparison has to be case *sensitive*.  An earlier version asked
    `name.upper() == short`, which drops the entry for "UniXNU" because the 8.3
    name is "UNIXNU" -- and this firmware's Fat does not fold case, so UniXNU's
    open of "\\EFI\\UniXNU\\unixnu.toml" then fails with Not Found while the
    uppercase 8.3 path succeeds.  Measured on the tablet:
    `QrLog: toml lo=Not Found up=Success`.
    """
    if name == _short_spelling(short_name):
        return []
    chars = name.encode("utf-16-le")
    units = [chars[i:i + 2] for i in range(0, len(chars), 2)]
    if len(units) % 13:
        units.append(b"\x00\x00")
    while len(units) % 13:
        units.append(b"\xff\xff")
    checksum = lfn_checksum(short_name)
    count = len(units) // 13
    entries = []
    for seq in range(count, 0, -1):
        chunk = units[(seq - 1) * 13:seq * 13]
        e = bytearray(32)
        e[0] = seq | (0x40 if seq == count else 0)
        e[1:11] = b"".join(chunk[0:5])
        e[11] = ATTR_LFN
        e[12] = 0
        e[13] = checksum
        e[14:26] = b"".join(chunk[5:11])
        e[26:28] = b"\x00\x00"
        e[28:32] = b"".join(chunk[11:13])
        entries.append(bytes(e))
    return entries


class Fat16:
    def __init__(self, size_bytes, label="CAIHONGESP", sectors_per_cluster=None):
        self.spc = sectors_per_cluster or SECTORS_PER_CLUSTER
        self.total_sectors = size_bytes // SECTOR
        self.root_dir_sectors = (ROOT_ENTRIES * 32 + SECTOR - 1) // SECTOR
        self.fat_sectors = self._fat_size()
        self.data_start = (RESERVED_SECTORS + NUM_FATS * self.fat_sectors +
                           self.root_dir_sectors)
        self.cluster_count = (self.total_sectors - self.data_start) // self.spc
        if not 4085 <= self.cluster_count < 65525:
            raise SystemExit(
                f"{self.cluster_count} clusters is outside FAT16 range; "
                "pick a different image size or cluster size")
        self.cluster_bytes = SECTOR * self.spc
        self.image = bytearray(self.total_sectors * SECTOR)
        self.fat = [0] * (self.cluster_count + 2)
        self.fat[0] = 0xFFF8
        self.fat[1] = 0xFFFF
        self.next_free = 2
        self.label = label
        self.dirs = {0: []}          # cluster -> list of directory entries
        self._write_boot_sector()

    def _fat_size(self):
        fat_secs = 1
        while True:
            data = (self.total_sectors - RESERVED_SECTORS - NUM_FATS * fat_secs -
                    self.root_dir_sectors)
            clusters = data // self.spc
            need = ((clusters + 2) * 2 + SECTOR - 1) // SECTOR
            if need <= fat_secs:
                return fat_secs
            fat_secs = need

    def _write_boot_sector(self):
        bs = bytearray(SECTOR)
        bs[0:3] = b"\xEB\x3C\x90"
        bs[3:11] = b"MSWIN4.1"
        struct.pack_into("<H", bs, 0x0B, SECTOR)
        bs[0x0D] = self.spc
        struct.pack_into("<H", bs, 0x0E, RESERVED_SECTORS)
        bs[0x10] = NUM_FATS
        struct.pack_into("<H", bs, 0x11, ROOT_ENTRIES)
        struct.pack_into("<H", bs, 0x13, 0)
        bs[0x15] = MEDIA
        struct.pack_into("<H", bs, 0x16, self.fat_sectors)
        struct.pack_into("<H", bs, 0x18, 32)
        struct.pack_into("<H", bs, 0x1A, 64)
        struct.pack_into("<I", bs, 0x1C, 0)
        struct.pack_into("<I", bs, 0x20, self.total_sectors)
        bs[0x24] = 0x80
        bs[0x26] = 0x29
        struct.pack_into("<I", bs, 0x27, 0x20261022)
        bs[0x2B:0x36] = self.label.upper().ljust(11)[:11].encode()
        bs[0x36:0x3E] = b"FAT16   "
        bs[0x1FE:0x200] = b"\x55\xAA"
        self.image[0:SECTOR] = bs

    # ---------------------------------------------------------------- helpers
    def _alloc(self, count=1):
        start = self.next_free
        if start + count > self.cluster_count + 1:
            raise SystemExit("payload image is full")
        for i in range(count):
            self.fat[start + i] = start + i + 1
        self.fat[start + count - 1] = 0xFFFF
        self.next_free += count
        return start

    def _cluster_offset(self, cluster):
        return (self.data_start + (cluster - 2) * self.spc) * SECTOR

    @staticmethod
    def _entry(short_name, attr, cluster, size):
        e = bytearray(32)
        e[0:11] = short_name
        e[11] = attr
        struct.pack_into("<H", e, 20, (cluster >> 16) & 0xFFFF)
        struct.pack_into("<H", e, 26, cluster & 0xFFFF)
        struct.pack_into("<I", e, 28, size)
        return bytes(e)

    def _add_entry(self, cluster, name, attr, child, size):
        short = short_name_for(name)
        entries = self.dirs[cluster]
        entries.extend(lfn_entries(name, short))
        entries.append(self._entry(short, attr, child, size))

    def _find(self, cluster, name):
        short = short_name_for(name)
        for e in self.dirs.get(cluster, []):
            if e[0:11] == short:
                return struct.unpack_from("<H", e, 26)[0]
        return None

    def mkdir(self, path):
        current = 0
        for part in [p for p in path.split("/") if p]:
            found = self._find(current, part)
            if found is not None:
                current = found
                continue
            child = self._alloc(1)
            self._add_entry(current, part, ATTR_DIR, child, 0)
            self.dirs[child] = [
                self._entry(b".".ljust(11), ATTR_DIR, child, 0),
                self._entry(b"..".ljust(11), ATTR_DIR, current, 0),
            ]
            current = child
        return current

    def add_file(self, path, data):
        parts = [p for p in path.split("/") if p]
        parent = self.mkdir("/".join(parts[:-1])) if len(parts) > 1 else 0
        clusters = max(1, (len(data) + self.cluster_bytes - 1) // self.cluster_bytes)
        first = self._alloc(clusters)
        for i in range(clusters):
            off = self._cluster_offset(first + i)
            chunk = data[i * self.cluster_bytes:(i + 1) * self.cluster_bytes]
            self.image[off:off + len(chunk)] = chunk
        self._add_entry(parent, parts[-1], ATTR_ARCHIVE, first, len(data))

    def finish(self):
        root_off = (RESERVED_SECTORS + NUM_FATS * self.fat_sectors) * SECTOR
        blob = b"".join(self.dirs[0])[:ROOT_ENTRIES * 32]
        self.image[root_off:root_off + len(blob)] = blob
        for cluster, entries in self.dirs.items():
            if cluster == 0:
                continue
            off = self._cluster_offset(cluster)
            blob = b"".join(entries)[:self.cluster_bytes]
            self.image[off:off + len(blob)] = blob
        fat_bytes = b"".join(struct.pack("<H", v) for v in self.fat)
        fat_bytes = fat_bytes.ljust(self.fat_sectors * SECTOR, b"\x00")
        for i in range(NUM_FATS):
            off = (RESERVED_SECTORS + i * self.fat_sectors) * SECTOR
            self.image[off:off + len(fat_bytes)] = fat_bytes
        return bytes(self.image)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--size-mib", type=int, default=32)
    p.add_argument("--label", default="CAIHONGESP")
    p.add_argument("--cluster-sectors", type=int, default=SECTORS_PER_CLUSTER,
                   help="sectors per cluster; small images need 1")
    p.add_argument("--add", action="append", default=[],
                   metavar="IMAGE_PATH=LOCAL_FILE")
    args = p.parse_args()

    fs = Fat16(args.size_mib * 1024 * 1024, label=args.label,
               sectors_per_cluster=args.cluster_sectors)
    for spec in args.add:
        if "=" not in spec:
            raise SystemExit(f"--add expects IMAGE_PATH=LOCAL_FILE, got {spec}")
        image_path, local = spec.split("=", 1)
        data = Path(local).read_bytes()
        fs.add_file(image_path, data)
        print(f"  + {image_path} ({len(data)} bytes)")
    blob = fs.finish()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    print(f"payload: {args.output} {len(blob)} bytes, {fs.cluster_count} clusters, FAT16")


if __name__ == "__main__":
    main()
