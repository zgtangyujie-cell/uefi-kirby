#!/usr/bin/env python3
"""Check that a kernel.macho.adt really carries memory-map/RAMDisk and TrustCache.

DarwinBoot 对这两个映射和 payload 里的文件是**双向强制**的（DarwinBoot.c:662-668、673-681）：

  ADT 有 RAMDisk 占位 + initrd 有文件      -> 正常
  ADT 有占位       + initrd 没文件         -> EFI_UNSUPPORTED（"boot refused: Unsupported"）
  ADT 无占位       + initrd 有文件         -> EFI_COMPROMISED_DATA
  占位非 0（本该由 DarwinBoot 填）         -> EFI_COMPROMISED_DATA

所以「ADT 里有没有那两个 16 字节映射」是一个能在本地完全验证的检查点，
它一旦错了，现象是板子停在 UEFI 菜单并打印 boot refused，和内核毫无关系。

用法：
    check_adt_ramdisk.py <kernel.macho.adt>
    check_adt_ramdisk.py <boot.img>        # 从 payload 卷的 FAT 里找 .adt

退出码：0 = 映射都在且为 0；1 = 缺映射或占位非 0；2 = 文件读不了
"""

import struct
import sys
import zlib
from pathlib import Path

LABEL = b"TB321FUESP"
ADT_NAMES = (b"KERNEL~1ADT", b"kernel.macho.adt", b"KERNEL  ADT", b"KERNEL~1.ADT")


class Volume:
    def __init__(self, data):
        self.data = data
        self.spc = data[13]
        self.reserved = struct.unpack_from("<H", data, 14)[0]
        self.fats = data[16]
        self.root_entries = struct.unpack_from("<H", data, 17)[0]
        spf = struct.unpack_from("<H", data, 22)[0]
        self.root_offset = (self.reserved + self.fats * spf) * 512
        self.data_start = (self.reserved + self.fats * spf +
                           (self.root_entries * 32) // 512)

    def cluster_offset(self, cluster):
        return (self.data_start + (cluster - 2) * self.spc) * 512

    def entries(self, offset):
        limit = self.root_entries if offset == self.root_offset else 1024
        out = []
        for index in range(limit):
            raw = self.data[offset + index * 32:offset + (index + 1) * 32]
            if len(raw) < 32 or raw[0] == 0:
                break
            out.append({"name": raw[0:11], "attr": raw[11],
                        "cluster": struct.unpack_from("<H", raw, 26)[0],
                        "size": struct.unpack_from("<I", raw, 28)[0]})
        return out

    def find(self, offset, name):
        for entry in self.entries(offset):
            if entry["attr"] in (0x10, 0x20) and entry["name"][:len(name)] == name:
                return entry
        return None


def adt_from(path: Path) -> bytes:
    raw = path.read_bytes()
    # 1) 直接给的 sidecar：ADT 是规范化的 property 表，通常以 0x01000000 开头
    if raw[:4] == b"\x01\x00\x00\x00" or raw.count(b"arm-io") > 0:
        return raw
    # 2) boot.img -> 解压 kernel 段 -> 找 payload 卷 -> FAT 里的 .adt
    try:
        size = struct.unpack_from("<I", raw, 8)[0]
        blob = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
            raw[4096:4096 + size])
    except (zlib.error, struct.error):
        raise SystemExit("neither an ADT sidecar nor a gzip boot image")
    mark = blob.find(LABEL)
    if mark < 0:
        raise SystemExit("no payload volume in the boot image")
    volume = Volume(blob[mark - 43:])
    offset = volume.root_offset
    for part in (b"EFI", b"UNIXNU", b"PAYLOADS"):
        entry = volume.find(offset, part)
        if entry is None:
            raise SystemExit("payload volume missing %r" % part)
        offset = volume.cluster_offset(entry["cluster"])
    for name in ADT_NAMES:
        entry = volume.find(offset, name)
        if entry is not None:
            start = volume.cluster_offset(entry["cluster"])
            return volume.data[start:start + entry["size"]]
    # 没有 .adt 时退化为列出目录，便于诊断
    names = [e["name"] for e in volume.entries(offset)]
    raise SystemExit("no .adt in Payloads/; entries: %r" % names)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    rc = 0
    for name in sys.argv[1:]:
        path = Path(name)
        try:
            data = adt_from(path)
        except (OSError, SystemExit) as error:
            print("%s: %s" % (path.name, error))
            rc = 2
            continue
        print("%s  (%d bytes)" % (path.name, len(data)))
        for key in (b"RAMDisk", b"PackedRAMDisk", b"TrustCache"):
            index = data.find(key)
            present = index >= 0
            if not present:
                print("    %-14s ABSENT" % key.decode())
                if key in (b"RAMDisk", b"TrustCache"):
                    rc = 1
                continue
            payload = data[index + len(key):index + len(key) + 16]
            zeros = payload == bytes(16)
            print("    %-14s at 0x%-6x payload=%s %s"
                  % (key.decode(), index, payload.hex(),
                     "OK (zero placeholder)" if zeros
                     else "**NON-ZERO -> EFI_COMPROMISED_DATA**"))
            if not zeros:
                rc = 1
        print()
    if rc == 0:
        print("PASS: every checked ADT carries the mappings DarwinBoot requires")
    elif rc == 1:
        print("FAIL: a mapping is missing or already filled in")
    return rc


if __name__ == "__main__":
    sys.exit(main())
