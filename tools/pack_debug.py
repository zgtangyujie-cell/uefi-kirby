#!/usr/bin/env python3
"""Pack the already-built DEBUG FV into a bootable image.

build_uefi.py's post-build step currently fails with
  "Plugin Failed: Fd Size Report Generator returned -1"
because the DEBUG build does not produce BUILD_REPORT.TXT.  The FV itself is
built fine, so this script reproduces the remaining packaging steps:
  BootShim.bin + FD -> gzip -> + kirby.dtb -> mkbootimg (header v4)
"""
import gzip, subprocess, sys, struct
from pathlib import Path

ROOT = Path("D:/uefi")
FD   = ROOT / "Build/kirbyPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"
BS   = ROOT / "BootShim/BootShim.bin"
DTB  = ROOT / "Resources/DTBs/kirby.dtb"
RD   = ROOT / "Resources/ramdisk"
MK   = ROOT / "Resources/Scripts/mkbootimg.py"
KER  = ROOT / "Build/kirbyPkg/DEBUG_CLANGPDB/FV/kirby-kernel"
OUT  = ROOT / "Mu-kirby-DEBUG.img"

fd  = FD.read_bytes()
bs  = BS.read_bytes()
dtb = DTB.read_bytes()
print(f"FD={len(fd)}  BootShim={len(bs)}  DTB={len(dtb)}")

KER.write_bytes(gzip.compress(bs + fd, 9) + dtb)

cmd = [sys.executable, str(MK),
       "--kernel", str(KER), "--ramdisk", str(RD), "-o", str(OUT),
       "--header_version", "4",
       "--os_version", "16.0.0", "--os_patch_level", "2026-07"]
r = subprocess.run(cmd, cwd=ROOT)
if r.returncode != 0:
    sys.exit("mkbootimg failed")

d = OUT.read_bytes()
f = [struct.unpack('<I', d[8+i*4:12+i*4])[0] for i in range(11)]
print(f"OK  {OUT.name}  {len(d)} bytes  header_version={f[8]}  header_size={f[3]}")
