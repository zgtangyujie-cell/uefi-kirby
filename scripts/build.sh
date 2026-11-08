#!/usr/bin/env bash
# Build the kirby (Lenovo Legion Y700 Gen3) UEFI firmware from a clean Mu-Silicium tree.
#
#   ./scripts/build.sh [workdir] [RELEASE|DEBUG]
#
# The workdir is created if missing and reused on later runs. Everything the
# board adds lives in this repository; the Mu-Silicium checkout stays untouched
# apart from the copied-in files and the build patches.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$ROOT/.work}
TARGET=${2:-RELEASE}

MU_URL=${MU_URL:-https://github.com/Project-Silicium/Mu-Silicium.git}
MU_COMMIT=${MU_COMMIT:-3aa95a72d469234755e2bcf2841ec6c0e83863e9}

log() { printf '\n=== %s\n' "$*"; }

log "workspace $WORK (target $TARGET)"
mkdir -p "$WORK"

if [ ! -d "$WORK/uefi/.git" ]; then
  log "cloning Mu-Silicium"
  git clone "$MU_URL" "$WORK/uefi"
fi

cd "$WORK/uefi"

log "checking out $MU_COMMIT"
git fetch --depth 1 origin "$MU_COMMIT" 2>/dev/null || git fetch origin
git checkout -f "$MU_COMMIT"
git submodule update --init --recursive --depth 1

#
# SEC entry-argument handoff, copied from UniXNU-caihong's
# patches/uefi-integration.patch (same Mu-Silicium base: the index line of
# ModuleEntryPoint.S matches).  Without it x0 -- the FDT pointer the bootloader
# passes in -- is overwritten by EL1_OR_EL2 before anything saves it, so no
# gSiliciumEntryArgHobGuid HOB is ever built, and UniXNURamDiskDxe can only
# report "UNIXNURAMDISK: no entry argument HOB" while UniXNU stays on its
# built-in configuration.
#
log "applying the SEC entry-argument patch"
git -C Silicon/Silicium checkout -f .
#
# Plain text edits instead of git apply: the patch (copied from
# UniXNU-caihong's uefi-integration.patch) made git apply report "Skipped
# patch" for all four files and change nothing, and the resulting build looked
# exactly like a patch that applied and did not help.  These edits are
# idempotent and print what they did.
#
python3 - <<'SECEOF'
import pathlib, sys

base = pathlib.Path("Silicon/Silicium/SiliciumPkg")

# 1. ModuleEntryPoint.S -- keep x0 (the FDT pointer) before platform code uses it.
p = base / "Sec/AArch64/ModuleEntryPoint.S"
text = p.read_text(encoding="utf-8")
if "gSecEntryArg0" in text:
    print("ModuleEntryPoint.S already patched")
else:
    anchor = "ASM_FUNC (_ModuleEntryPoint)\n"
    if anchor not in text:
        sys.exit("ModuleEntryPoint.S: anchor not found")
    ins = (anchor
           + "  // Preserve the bootloader's FDT pointer before platform code uses x0.\n"
           + "  adr   x1, ASM_PFX (gSecEntryArg0)\n"
           + "  str   x0, [x1]\n"
           + "  // SecEntry invalidates the FD cache; commit this slot before that happen.\n"
           + "  dc    cvac, x1\n"
           + "  dsb   sy\n")
    text = text.replace(anchor, ins, 1)
    text = text.rstrip("\n") + "\n\n  .align 3\n  .global ASM_PFX (gSecEntryArg0)\nASM_PFX (gSecEntryArg0):\n  .quad 0\n"
    p.write_text(text, encoding="utf-8")
    print("patched ModuleEntryPoint.S")

# 2. Sec.c -- publish that slot as a GUID HOB.
p = base / "Sec/Sec.c"
text = p.read_text(encoding="utf-8")
if "gSecEntryArg0" in text:
    print("Sec.c already patched")
else:
    anchor = '#include "Sec.h"\n'
    if anchor not in text:
        sys.exit("Sec.c: include anchor not found")
    text = text.replace(anchor, anchor + "\nextern UINT64 gSecEntryArg0;\n", 1)
    anchor2 = "  // Run Library Cconstructors\n"
    if anchor2 not in text:
        sys.exit("Sec.c: constructor anchor not found")
    ins = ("  // Publish the bootloader supplied argument (x0 = FDT pointer) for later phases.\n"
           + "  BuildGuidDataHob (&gSiliciumEntryArgHobGuid, &gSecEntryArg0, sizeof (gSecEntryArg0));\n\n")
    text = text.replace(anchor2, ins + anchor2, 1)
    p.write_text(text, encoding="utf-8")
    print("patched Sec.c")

# 3. Sec.inf / SiliciumPkg.dec -- declare the GUID.
p = base / "Sec/Sec.inf"
text = p.read_text(encoding="utf-8")
if "gSiliciumEntryArgHobGuid" in text:
    print("Sec.inf already patched")
else:
    anchor = "[Guids]\n"
    if anchor not in text:
        sys.exit("Sec.inf: [Guids] not found")
    p.write_text(text.replace(anchor, anchor + "  gSiliciumEntryArgHobGuid\n", 1), encoding="utf-8")
    print("patched Sec.inf")

p = base / "SiliciumPkg.dec"
text = p.read_text(encoding="utf-8")
if "gSiliciumEntryArgHobGuid" in text:
    print("SiliciumPkg.dec already patched")
else:
    anchor = "[Guids]\n"
    if anchor not in text:
        sys.exit("SiliciumPkg.dec: [Guids] not found")
    line = ("  gSiliciumEntryArgHobGuid            = { 0xDAEE82E6, 0x8090, 0x4E72, "
            "{ 0xBF, 0xB9, 0x78, 0xC1, 0x3C, 0xD4, 0xE3, 0x59 } }\n")
    p.write_text(text.replace(anchor, anchor + line, 1), encoding="utf-8")
    print("patched SiliciumPkg.dec")
SECEOF

#
# Fail loudly if the edit did not take.  A silent no-op here costs a full
# build + reboot + photograph cycle and then shows the same
# "no entry argument HOB" as before.
#
if ! grep -q gSecEntryArg0 Silicon/Silicium/SiliciumPkg/Sec/AArch64/ModuleEntryPoint.S; then
  echo "ERROR: SEC entry-argument patch did not apply" >&2
  exit 1
fi
git -C Silicon/Silicium diff --stat

log "installing the kirby device package"
cp -r "$ROOT/Platforms/Lenovo/kirbyPkg" Platforms/Lenovo/
cp    "$ROOT/Resources/Configs/kirby.toml" Resources/Configs/

#
# Build the UniXNU payload volume.
#
# 8 MiB FAT16, one file: EFI/UniXNU/unixnu.toml.  FAT16 rather than the FAT12
# the driver compiles in, because this copy rides in the kernel section and has
# room; 8 MiB is the largest the ramdisk window would ever allow and costs
# nothing here.
#
# The names carry VFAT long-file entries with the exact case UniXNU asks for.
# mkpayload.py used to skip the long entry whenever the upper-cased name matched
# the 8.3 spelling, so "UniXNU" was stored as plain "UNIXNU" -- and this
# firmware's Fat does not fold case (measured: `toml lo=Not Found up=Success`).
#
#
# The payload step needs scripts from the UniXNU tree (patch-pe-console lives
# here, patch-xnu-entry-probe lives there).  Clone it before the payload block
# rather than at the firmware stage further down, otherwise the entry probe
# check sees no script yet and silently skips.  The later clone is guarded by
# the same .git test, so this only moves the first clone earlier.
#
UNIXNU_URL=${UNIXNU_URL:-https://github.com/UniXNU/UniXNU.git}
if [ ! -d "$WORK/unixnu/.git" ]; then
  log "cloning UniXNU early for the payload scripts"
  git clone "$UNIXNU_URL" "$WORK/unixnu"
fi

log "building the payload volume"
#
# The kernel is not committed: it is a 52 MB Apple-derived binary.  Take it from
# the kernel-out branch, which the macOS job writes when a build succeeds, so a
# new kernel is picked up by the next firmware build without touching git.
#
KERNEL_TMP="$ROOT/Platforms/Lenovo/kirbyPkg/Resources/kernel.macho"
ADT_TMP="$ROOT/Platforms/Lenovo/kirbyPkg/Resources/kernel.macho.adt"
rm -f "$KERNEL_TMP" "$ADT_TMP"
if git -C "$ROOT" fetch -q --depth 1 origin kernel-out 2>/dev/null; then
  git -C "$ROOT" show FETCH_HEAD:kernel.macho > "$KERNEL_TMP" 2>/dev/null
  log "kernel from kernel-out: $(wc -c < "$KERNEL_TMP") bytes"
  #
  # PE_create_console reads the iBoot video console handoff at PA 0x3C0FC000
  # before it looks at boot_args->Video.  That page is uninitialised under
  # `fastboot boot`, so the load faults and the tablet resets right after
  # DarwinEnter -- the sequence measured on 8f79eb6/d80c6fd.  UniXNU's elden
  # record measured the same fault and found that returning from the function
  # immediately lets arm_init reach machine_startup.  The script resolves the
  # symbol through LC_SYMTAB, so a kernel rebuild that moves the address still
  # gets patched.
  #
  if [ -s "$KERNEL_TMP" ]; then
    python3 "$ROOT/scripts/patch-pe-console.py" "$KERNEL_TMP" ||
      { log "PE_create_console patch failed; refusing to ship an unpatched kernel"; exit 1; }
    #
    # XNU's own console: point _printf at scripts/xnu-console.c so every kernel
    # message is drawn on the panel instead of going to a serial port that does
    # not exist here.  Taken from UniXNU-caihong, which is the same SoC family.
    #
    # MUST run before the entry probe: xnu-console.c checks the entry sequence
    # of _printf, and the probe rewrites call sites.  It also scans for padding
    # backwards from the end of the segment, so it will not claim the cave the
    # probe keeps for its stage code.
    #
    python3 "$ROOT/scripts/patch-xnu-console.py" "$KERNEL_TMP" ||
      { log "xnu-console patch failed; refusing to ship a kernel with no console"; exit 1; }
    #
    # Official entry probe: stage code goes into the zero padding after `_start`
    # (which is a single `b`), displaced instructions are re-executed there.
    # It draws a blue bar once the kernel entry actually runs and a magenta bar
    # just before the MMU comes on, so the panel answers "how far did the
    # kernel get" instead of "did printf print anything".  UNIXNU_UEFI supplies
    # Mu-Silicium's Font.h for the panic screen.
    #
    #
    # Vendored copy, not $WORK/unixnu/scripts: this block runs about seventy
    # lines before the UniXNU checkout is cloned, so the tree path does not
    # exist yet and the guard below silently took the else branch on every
    # run -- which is why 9d2c207, 5e9a0f3 and 35405bd all shipped an
    # untouched _start while the build kept succeeding.
    #
    ENTRY_PROBE="$WORK/unixnu/scripts/patch-xnu-entry-probe.py"
    if [ -f "$ENTRY_PROBE" ]; then
      #
      # The probe shells out to llvm-nm / clang / ld.lld / llvm-objcopy /
      # llvm-size / llvm-readelf and falls back to the macOS Homebrew prefix
      # when they are not on PATH.  On this Ubuntu runner they live under
      # /usr/lib/llvm-*/bin, so put that on PATH first or the script dies with
      # FileNotFoundError and leaves _start untouched.
      #
      for _llvmbin in /usr/lib/llvm-*/bin; do
        if [ -d "$_llvmbin" ]; then PATH="$_llvmbin:$PATH"; fi
      done
      export PATH
      echo "PROBE: script $ENTRY_PROBE"
      echo "PROBE: kernel $KERNEL_TMP ($(wc -c < "$KERNEL_TMP") bytes)"
      echo "PROBE: llvm-nm=$(command -v llvm-nm || echo MISSING) clang=$(command -v clang || echo MISSING)"
      #
      # Progress so far, each step measured without a screen:
      #   c5d38a4  --reset-delay 6                       CPU got through the MMU
      #   d1a26d7  after _PE_init_platform (1st call)     returned
      #   dc76c75  before _machine_startup                NO reset
      #   fceb11f  after _PE_create_console               NO reset
      #  78067bf  after _serial_init                      NO reset
      #
      # 78067bf is the important one: serial_init was never reached, so the
      # death is between arm_vm_init returning and that call.  Only two calls
      # live there:
      #   0x79b3c70  patch_low_glo                 (guarded by cbz w8, may not run)
      #   0x79b3c74  PE_consistent_debug_inherit   (unconditional)
      #   0x79b3c78  serial_init
      #
      # The patch_low_glo round proved the method has a hole: it is called only
      # when the flag at 0x715c518 is non-zero (cbz at 0x79b3c6c), so a missing
      # reset could mean "not called" rather than "died before it".
      # PE_consistent_debug_inherit is an unconditional bl, so the signal is
      # A checkpoint that returns resets; one that does not never resets, and
      # the tablet goes completely dark (XNU never brings USB up).  That is the
      # whole signal, so the probe must not depend on anything else.
      #
      # --reset-delay 30 instead of the default 6: a return is not the only way
      # to get a reset.  panic() would also restart the tablet if panic_reboot
      # were set (it is not, so panic parks) - but to prove which one happened,
      # the deliberate 30 s wait makes the two distinguishable by time: a probe
      # reset moves ~24 s later, a panic restart does not move at all.
      #
      UNIXNU_UEFI="$WORK/uefi" python3 "$ENTRY_PROBE" "$KERNEL_TMP" \
        --reset-after _PE_create_console --in _arm_init --reset-before --reset-delay 6 ||
        { echo "PROBE: install failed"; exit 1; }
      echo "PROBE: installed; verifying _start"
      python3 - "$KERNEL_TMP" <<'PY' || { log "entry probe did not change _start"; exit 1; }
import struct, sys
# _start is the single `b` to _start_first_cpu.  The probe replaces it with a
# branch into the stage-1 cave, which sits 0x78 bytes later: `b +0x78` is
# 0x1400001E.  The stage code starts at the cave itself -- va
# 0xFFFFFFF0073F0500, file 0x3EC500 -- while the 0x74 bytes between _start+4
# and the cave stay zero.  Look for the code at the cave, not right after
# _start: the first version of this check read 0x3EC48C and failed a build
# whose probe had in fact been installed.
d = open(sys.argv[1], 'rb').read()
word = struct.unpack_from('<I', d, 0x3EC488)[0]
if word == 0x140006F5:
    sys.exit("_start is still the original branch")
if word != 0x1400001E:
    sys.exit("_start is %#010x, the stage-1 branch is 0x1400001e" % word)
if not any(struct.unpack_from('<8I', d, 0x3EC500)):
    sys.exit("the stage-1 cave at 0x3EC500 is empty")
print(f"_start now {word:#010x}, stage-1 cave written")
PY
    else
      log "entry probe script missing at $ENTRY_PROBE; refusing to ship a kernel without colour bars"
      exit 1
    fi
    #
    # PE_consistent_debug_inherit never returns on this board.  It looks up
    # /chosen and then the 'consistent-debug-root' property; our ADT has no
    # such property, so both SecureDT calls should fall into the clean -1 path,
    # yet the probe placed after this call never fires.
    #
    # This NOP must run AFTER the probe: the probe script verifies that
    # _arm_init contains exactly one call to the symbol, and refuses to install
    # once the call is gone.  Ordering it first failed build ba83ecb.
    #
    python3 "$ROOT/scripts/patch-debug-inherit.py" "$KERNEL_TMP" ||
      { log "debug-inherit NOP failed"; exit 1; }
  fi
else
  log "no kernel-out branch; the payload will carry the config only"
fi
#
# DarwinBoot.c:648-650 unconditionally opens <KernelPath>.adt and returns
# EFI_NOT_FOUND when it is missing -- unlike .trustcache/.gpuaddon/.vroot,
# which all tolerate NOT_FOUND.  So this sidecar is mandatory, not optional.
# The adt job builds it on adt-out from the board DTS alone (scripts/gen-adt.py),
# which keeps kernel-out from having to carry it through every kernel rebuild.
#
if git -C "$ROOT" fetch -q --depth 1 origin adt-out 2>/dev/null &&
   git -C "$ROOT" show FETCH_HEAD:kernel.macho.adt > "$ADT_TMP" 2>/dev/null; then
  log "ADT from adt-out: $(wc -c < "$ADT_TMP") bytes"
else
  rm -f "$ADT_TMP"
  log "no adt-out:kernel.macho.adt; DarwinBoot will report Not Found"
fi
#
# Root filesystem test without touching any partition.
#
# IOFindBSDRoot treats the range under /chosen/memory-map/RAMDisk as a root
# device candidate, so a real APFS container loaded into memory is enough to
# learn whether APFS can mount anything at all on this board.  That needs three
# things in place: this ramdisk, an ADT that declares the RAMDisk mapping
# (gen-adt.py --data), and an entry that names the file (initrd in unixnu.toml).
#
# The file is 176.0 MiB, which is over GitHub's 100 MiB per-file limit, so
# ramdisk-out carries it in 44 MiB parts that get concatenated here.  It is
# already a bare container: the IPSW member is an IM4P/DER wrapper with NXSB at
# offset 59, nothing compressed, so scripts/make-ramdisk.py can rebuild it from
# the IPSW without lzfse when this branch is stale.
#
#
# Diagnostic build: a 1 MiB placeholder instead of the 176 MiB container.
#
# Two independent walls were measured on real hardware on 2026-11-08:
#
#   boot.img 139 MiB (the real 176 MiB container) -> Booting OKAY, then the
#       tablet drops to the charging screen.  ABL never reached UEFI.
#   boot.img 9 MiB (240 MiB payload, 176 MiB of zeroes inside) -> Booting OKAY,
#       then the firmware died after 124 s and ABL returned to fastboot.
#
# The second is the informative one: the gzip stream was small enough that ABL
# accepted it, yet the firmware still died, which points at the 240 MiB payload
# volume rather than at the boot image size.  KirbyInitrdDxe publishes that
# volume out of the kernel window, and 240 MiB is far past the 64 MiB that has
# always worked here.
#
# So this build asks a different question: with a payload the firmware is known
# to accept, does the console finally draw the kernel's own log?  The ramdisk is
# 1 MiB of zeroes - enough for memory-map/RAMDisk to be filled and for
# IOFindBSDRoot to be reached, but not an APFS container, so the mount is
# expected to fail.  That failure message is the whole point: it proves the
# console path works, and then the container can come back at a size the
# firmware tolerates.
#
RAMDISK_TMP="$WORK/restore_apfs.img"
rm -f "$RAMDISK_TMP"
python3 - "$RAMDISK_TMP" <<'PY'
import sys
from pathlib import Path
Path(sys.argv[1]).write_bytes(bytes(1 << 20))
print("ramdisk: 1 MiB of zeroes (diagnostic placeholder, not a container)")
PY
PAYLOAD_ARGS=(--output Platforms/Lenovo/kirbyPkg/Resources/payload.bin
              --size-mib 64 --cluster-sectors 8 --label TB321FUESP
              --add "EFI/UniXNU/unixnu.toml=Platforms/Lenovo/kirbyPkg/Resources/payload-tree/EFI/UniXNU/unixnu.toml")
if [ -s "$KERNEL_TMP" ]; then
  PAYLOAD_ARGS+=(--add "EFI/UniXNU/Payloads/kernel.macho=$KERNEL_TMP")
fi
if [ -s "$ADT_TMP" ]; then
  PAYLOAD_ARGS+=(--add "EFI/UniXNU/Payloads/kernel.macho.adt=$ADT_TMP")
fi
if [ -s "$RAMDISK_TMP" ]; then
  PAYLOAD_ARGS+=(--add "EFI/UniXNU/Payloads/restore_apfs.img=$RAMDISK_TMP")
fi
#
# DarwinBoot reads <KernelPath>.trustcache and rejects the boot with
# EFI_COMPROMISED_DATA when the ADT declares a TrustCache mapping but no such
# file exists (DarwinBoot.c:671-681).  The ADT carries that mapping because
# gen-adt.py runs with --trust, so this file has to be in every payload - a
# build without it boots straight into "Kernel '<XNU>' returned: CompromisedData".
#
# The 59,504-byte file is the IPSW's RestoreTrustCache, unchanged; it is
# committed under Resources/ because the CI job never fetches the IPSW.
#
TRUSTCACHE_SRC="$ROOT/Resources/payload/kernel.macho.trustcache"
if [ -s "$TRUSTCACHE_SRC" ]; then
  PAYLOAD_ARGS+=(--add "EFI/UniXNU/Payloads/kernel.macho.trustcache=$TRUSTCACHE_SRC")
  log "trustcache: $(wc -c < "$TRUSTCACHE_SRC") bytes"
else
  log "trustcache: missing at $TRUSTCACHE_SRC; the kernel entry will be refused"
fi
python3 "$ROOT/scripts/mkpayload.py" "${PAYLOAD_ARGS[@]}"

#
# UniXNU required integration
# (unixnu.com/zh/porting/uefi-firmware#required-integration).
#
# UniXNU publishes its package roots as {tree}/package and
# {tree}/drivers/DarwinBoot, so PACKAGES_PATH is what has to carry them -- the
# official build does exactly that and never copies packages around.  Appended,
# never replaced: WORKSPACE still has to resolve MdePkg and the Mu packages.
#
UNIXNU_URL=${UNIXNU_URL:-https://github.com/UniXNU/UniXNU.git}
UNIXNU_COMMIT=${UNIXNU_COMMIT:-13e5973748a8447cbb90520c9a2dd5e65e272435}

if [ ! -d "$WORK/unixnu/.git" ]; then
  log "cloning UniXNU"
  git clone "$UNIXNU_URL" "$WORK/unixnu"
fi
log "checking out UniXNU $UNIXNU_COMMIT"
git -C "$WORK/unixnu" fetch --depth 1 origin "$UNIXNU_COMMIT" 2>/dev/null || git -C "$WORK/unixnu" fetch origin
git -C "$WORK/unixnu" checkout -f "$UNIXNU_COMMIT"

#
# drivers/DarwinBoot is a git submodule, not a directory in the tree: a plain
# clone leaves it empty, and the build then dies with
#   Failed to convert Edk2Relative Path to an Absolute Path
#   Relative Path: DarwinBootPkg/Driver/DarwinBoot.inf
# Only this submodule is needed -- UniXNUPkg itself lives in the main
# repository.  --init is idempotent, so this is safe on every run.
#
log "initialising the DarwinBoot submodule"
git -C "$WORK/unixnu" submodule update --init drivers/DarwinBoot

#
# Diagnostic only.  With PcdDebugPrintErrorLevel back at ERROR|WARN, UniXNUDxe's
# one and only success line ("Boot%04x first in BootOrder") is DEBUG_INFO and
# would be invisible, so the QR capture could not tell "registered" from "never
# dispatched".  Promote that file's lines to DEBUG_ERROR while investigating.
#
UNIXNU_DXE_C="$WORK/unixnu/package/UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.c"
if [ -f "$UNIXNU_DXE_C" ]; then
  sed -i 's/DEBUG ((DEBUG_INFO, "UniXNUDxe:/DEBUG ((DEBUG_ERROR, "UniXNUDxe:/g' "$UNIXNU_DXE_C"
  log "promoted UniXNUDxe DEBUG_INFO lines to DEBUG_ERROR"
fi

#
# Diagnostic hold, one round only, and deliberately NOT a dead loop: the owner
# does not want the tablet parked on a debug screen.  DarwinBoot's Fail path
# prints "DARWINBOOT: boot refused: <status>" and returns to UniXNU, whose
# repaint covers the line immediately.  Hold the panel for twenty seconds so
# the status can be read, then let it return and retry.
#
DARWINBOOT_C="$WORK/unixnu/drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c"
if [ -f "$DARWINBOOT_C" ]; then
  python3 -c '
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
if "KirbyHold" in t:
    sys.exit(0)
needle = "Print (L\"DARWINBOOT: boot refused: %r; firmware retained\\n\", Status);"
if needle not in t:
    sys.exit("boot-refused print not found in DarwinBoot.c")
hold = "\n  for (UINTN KirbyHold = 0; KirbyHold < 20; KirbyHold++) { gBS->Stall (1000000); }"
t = t.replace(needle, needle + hold, 1)
p.write_text(t)
print("DarwinBoot: Fail path holds 20 s, then returns")
' "$DARWINBOOT_C" || { log "DarwinBoot diagnostic hold patch failed"; exit 1; }
fi

#
# Diagnostic only: paint the framebuffer base DarwinBoot actually handed over.
# The dark question is whether boot_args->Video[0] is zero (GOP lookup failed)
# or a real address; the console chain depends on it, and the Print line that
# carries it gets truncated in photographs.  DiagDraw writes straight to the
# framebuffer in large glyphs, right before ExitBootServices.
#
if [ -f "$DARWINBOOT_C" ]; then
  python3 -c '
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
if "KirbyDiag" in t:
    sys.exit(0)
needle = "DEBUG ((DEBUG_ERROR, \"\\nExiting boot services. A green bar across the top\\nmarks the loader handoff before the kernel branch.\\n\"));"
if needle not in t:
    sys.exit("hand-off DEBUG line not found in DarwinBoot.c")
paint = "\n  { CHAR16 KirbyDiag[96]; UnicodeSPrint (KirbyDiag, sizeof (KirbyDiag), L\"video0 0x%lx  video1 0x%lx  video2 0x%lx\", Video[0], Video[1], Video[2]); DiagDraw (KirbyDiag, 6); }"
t = t.replace(needle, needle + paint, 1)
p.write_text(t)
print("DarwinBoot: paints video0/1/2 before ExitBootServices")
' "$DARWINBOOT_C" || { log "DarwinBoot video diagnostic patch failed"; exit 1; }
fi

#
# KirbyPeVideo: hand the kernel the panel geometry it cannot find itself.
#
# Measured on the 51,695,616-byte kernel this board builds: nothing writes
# PE_state.video or PE_state.boot_args.  adrp+add+str, movz/movk constant builds
# and direct str-to-[adrp,#off] were all scanned and all came back empty.  The
# only reference to PE_state.video is _PE_create_console forwarding the address
# to _initialize_screen, so _initialize_screen sees an all-zero PE_Video, leaves
# _vinfo zero, and every console guard refuses - a kernel that runs for 130
# seconds paints nothing.
#
# DarwinBoot already holds the real numbers (Video[] from GOP, printed at
# hand-off), so write PE_Video into the kernel's own address space before the
# branch.  The symbol comes from LC_SYMTAB: prelink moves _PE_state by 0xA8
# between builds.
#
# KirbyPeVideo rolled back (default OFF, 2026-11-08 16:3x).
#
# The isolation round is complete and the answer is: the seed is harmful.
#   - K-noseed baseline: reaches _IOFindBSDRoot, alive ~130 s.
#   - J2 (probe + seed + trustcache), 10:44 boot: charging screen at 94 s.
#   - The before-call control (D630c9 / 583f05, art7) did NOT fire either, so
#     with the seed the kernel dies BEFORE the console call site - i.e. the
#     seed moves the death point earlier, it does not add observability.
#
# Turning it back on for one round is a one-liner: KIRBY_PE_VIDEO_SEED=1
# (e.g. in the workflow's env: block).  Default stays 0: shipping a build that
# dies earlier to paint PE_Video is a net loss while the USB console port is
# the actual fix (collab/CHANNEL.md #640).
#
KIRBY_PE_VIDEO_SEED=${KIRBY_PE_VIDEO_SEED:-0}
if [ -f "$DARWINBOOT_C" ] && [ "$KIRBY_PE_VIDEO_SEED" = "1" ]; then
  python3 "$ROOT/scripts/patch-darwinboot-pe-video.py" "$DARWINBOOT_C" ||
    { log "DarwinBoot PE_state.video seed failed"; exit 1; }
  _seed_marks=$(grep -c "KirbyPeVideo" "$DARWINBOOT_C" 2>/dev/null | tr -d '[:space:]')
  _seed_marks=${_seed_marks:-0}
  log "seed: KirbyPeVideo markers in DarwinBoot.c = $_seed_marks (need >= 2)"
  if [ "$_seed_marks" -lt 2 ]; then
    log "seed: patch did not land; refusing to ship a build that cannot report"
    exit 1
  fi
else
  log "seed: KIRBY_PE_VIDEO_SEED=$KIRBY_PE_VIDEO_SEED -> no PE_state.video seed this round"
fi

#
# vcputc refuses to draw unless BSS dword 0xfffffff007b20e04 is non-zero:
#
#   0xfffffff0073be7b0  ldr w8, [x19, #0xe04]
#   0xfffffff0073be7b4  cbz w8, 0xfffffff0073bedb0     <- no draw
#
# The only writer is vc_progress_set (0xfffffff0073c1340):
#   eor w8, w20, #1 ; str w8, [x9, #0xe04]
# and that path only runs when the progress bar timer is armed, which needs
# _PE_initialize_console -- a function with zero call sites in this kernel.
# So the gate stays at its BSS value 0 and every printf is swallowed.
#
# Set it once from DarwinBoot, before ExitBootServices.  Address:
#   PA = Address + (0xFFFFFFF007B20E04 - Kernel.Base)
#
if [ -f "$DARWINBOOT_C" ]; then
  python3 -c '
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
if "kirby: open the vcputc gate" in t:
    sys.exit(0)
needle = "DiagDraw (KirbyDiag, 6); }"
if needle not in t:
    sys.exit("KirbyDiag paint block not found in DarwinBoot.c")
gate = "\n  /* kirby: open the vcputc gate (b20e04) */\n  *(volatile UINT32 *)(UINTN)(Address + (0xFFFFFFF007B20E04ULL - Kernel.Base)) = 1;"
t = t.replace(needle, needle + gate, 1)
p.write_text(t)
print("DarwinBoot: opens the vcputc gate at b20e04")
' "$DARWINBOOT_C" || { log "DarwinBoot vcputc gate patch failed"; exit 1; }
fi

#
# Menu.c: after a failed boot the menu must not wait forever.  BDS leaves a
# ConIn handle behind even when "Connect ConIn" failed, so CountInputDevices()
# reports > 0; Main.c:169 then sets Countdown = FALSE and Menu.c:114 hands
# RemainingMs = -1, i.e. an unconditional wait.  That is the "stuck on the
# menu" the owner kept hitting.  Use fallback_timeout in that branch too.
#
MENU_C="$WORK/unixnu/package/UniXNUPkg/Library/UniXNULib/Menu.c"
if [ -f "$MENU_C" ]; then
  python3 -c '
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
old = "RemainingMs = HasInput ? -1 : (INTN)Config->FallbackTimeout * 1000;"
new = "RemainingMs = (INTN)Config->FallbackTimeout * 1000;"
if old not in t:
    sys.exit("expected RemainingMs line not found in Menu.c")
p.write_text(t.replace(old, new))
print("Menu.c: failed-boot menu retries every fallback_timeout")
' "$MENU_C" || { log "Menu.c retry patch failed"; exit 1; }
fi

#
# The SetVariable probe that used to sit here is gone.  It answered its
# question -- attr=0x7 size=96 is perfectly valid and SetVariable still
# returns EFI_INVALID_PARAMETER, so this platform's variable store simply
# cannot be written -- and every build since then spent four lines of the
# 600-byte QR slice repeating settled news.  The payload chain needs that
# room for its own diagnostics.
#

#
# Diagnostic only.  The probe proved the arguments are valid -- attr=0x7
# (NV|BS|RT) and size=96 -- yet SetVariable still returns EFI_INVALID_PARAMETER.
# This platform's VariableRuntimeDxe has no flash FVB, so it refuses
# EFI_VARIABLE_NON_VOLATILE outright; that is also why BDS keeps falling back to
# its default boot-device list.  Write the option as volatile instead:
# BootOrder then lives for one power cycle, which is all `fastboot boot` needs.
# Revert once the platform has a real NV store.
#
#
# Dropping EFI_VARIABLE_NON_VOLATILE from UniXNUDxe was the wrong guess: the
# probe then printed attr=0x6 and SetVariable still returned EFI_INVALID_PARAMETER.
# Keep the option's normal NV|BS|RT attributes and fix the store instead --
# PcdEmuVariableNvModeEnable = TRUE in kirby.dsc (see the comment there).
#

# stuart does not read PACKAGES_PATH from the environment: kirbyPkg's
# DeviceBuild.GetPackagesPath() is the list it actually uses, and that is where
# the two UniXNU roots are appended.  Exported here only for documentation.
log "UniXNU tree: $WORK/unixnu"

log "regenerating the patched vendor drivers"
python3 "$ROOT/tools/apply_binary_patches.py" "$WORK/uefi"

log "preparing the python environment"
if [ ! -x "$WORK/.venv/bin/python" ]; then
  python3 -m venv "$WORK/.venv"
fi
"$WORK/.venv/bin/pip" install --quiet --upgrade pip
"$WORK/.venv/bin/pip" install --quiet -r pip-requirements.txt

log "applying the build patches"

# 让 BDS 菜单无条件进入：KeyCallback 里 mEnterBootManager 初值改为 TRUE。
# 原逻辑只有检测到按键设备（gKeypadDeviceProtocolGuid）上的 SCAN_UP 才进菜单，
# 而我们的按键驱动因缺少 /soc/buttons 设备树节点起不来，永远等不到这个键。
log "patching BootManagerLib: enter menu without a key press"
KC=Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/KeyCallback.c
sed -i 's/\(mEnterBootManager[[:space:]]*=[[:space:]]*\)FALSE/\1TRUE/' "$KC"
grep -n "mEnterBootManager.*=" "$KC" | head -3

# 关掉 ASSERT 的死循环。AutoGen.c 在每个驱动入口点末尾都有
# ASSERT_EFI_ERROR (Status)，而"可选设备不存在"让驱动返回 EFI_NOT_FOUND 是完全
# 正常的（kirby 上是 EnvDxeEnhanced），DxeCore 本来会卸载它继续走 —— 但
# ASSERT 会先进死循环，整个固件就钉死在一个不该管的驱动上。
#
# 前四轮为什么都没成功（记录下来，别再来第五次）：
#   1. kirby.dsc [PcdsFixedAtBuild] PcdDebugPropertyMask=0x02       无效
#   2. kirby.dsc 再加 PcdDebugPrintErrorLevel 降级                    只治了刷屏
#   3. SiliciumPkg.dsc.inc:69 0x2F->0x02（同在 FixedAtBuild 段）      无效
#   4. BaseDebugLibSerialPort 的 DebugAssertEnabled() 改成 return FALSE 无效
#
# 第 4 轮无效这件事本身就是证据：ASSERT 宏的第一句就是 if (DebugAssertEnabled())，
# 只要它返回 FALSE，屏幕上根本不该出现 "ASSERT [AutoGen.c:648]" 这一行。
# 这行还在，说明改的那个函数不是编译进固件的那一份 —— 于是不再猜了。
#
# 死循环的真正位置在 DebugAssert() 内部：PcdDebugPropertyMask 的 0x20 位
# (ASSERT_DEADLOOP_ENABLED) 会让它调 CpuDeadLoop()，而 0x2F 正好带着这一位。
# 与其继续追这个 PCD 到底解析成哪一份，直接把 ASSERT 宏本身抹平：
# 编译期展开成空，任何模块、任何 PCD 取值都绕不过去。
#
# 保留 if (FALSE) { (VOID)(Expression); } 的形状是为了不触发 unused 警告，
# 和 EDK2 自己在 MDEPKG_NDEBUG 分支里的写法一致。ASSERT_EFI_ERROR 里包着的
# DEBUG((DEBUG_ERROR, "ASSERT_EFI_ERROR (Status = %r)")) 不受影响，仍然会打印，
# 所以"哪个驱动失败了"这条信息一点不少。
log "patching DebugLib: ASSERT becomes a no-op, DEBUG() untouched"
DBC=Mu_Basecore/MdePkg/Library/BaseDebugLibSerialPort/DebugLib.c
DLH=Mu_Basecore/MdePkg/Include/Library/DebugLib.h
python3 - "$DBC" "$DLH" <<'PYEOF'
import re
import sys
import pathlib

dbc = pathlib.Path(sys.argv[1])
dlh = pathlib.Path(sys.argv[2])

# A cached mu_basecore may still carry the previous run's edits (submodule
# checkout does not always discard them), so every patch below has to be
# idempotent and INDEPENDENT.  Never skip the whole script because one file
# was already patched: that was the bug on 821cacd -- DebugLib.c carried the
# marker, the script raised SystemExit(0), DebugLib.h got restored by the
# submodule refresh, and AutoGen.c ASSERT_EFI_ERROR dead-looped again
# ("ASSERT AutoGen.c:389: !EFI_ERROR (Status)" on screen).

# --- 1. DebugAssertEnabled() -> FALSE -------------------------------------
text = dbc.read_text(encoding="utf-8")
if "kirby: ASSERT no-op" in text:
    print("DebugAssertEnabled already patched")
else:
    gate = re.compile(
        r"return\s*\(\s*BOOLEAN\s*\)\s*\(\s*\(\s*PcdGet8\s*\(\s*PcdDebugPropertyMask\s*\)"
        r"\s*&\s*DEBUG_PROPERTY_DEBUG_ASSERT_ENABLED\s*\)\s*!=\s*0\s*\)\s*;"
    )
    hits = gate.findall(text)
    if len(hits) != 1:
        print(f"DebugAssertEnabled body matched {len(hits)} times, expected 1", file=sys.stderr)
        sys.exit(1)
    text = gate.sub(
        "return FALSE; /* kirby: ASSERT no-op for bring-up, see scripts/build.sh */",
        text,
        count=1,
    )
    dbc.write_text(text, encoding="utf-8")
    print("patched DebugAssertEnabled")

# --- 2. Override ASSERT / ASSERT_EFI_ERROR at the END of DebugLib.h -------
# Use #undef + #define instead of a shape-sensitive regex: a cached basecore
# may ship a differently formatted macro, and a failed regex used to abort
# the whole build.  ASSERT becomes a no-op; ASSERT_EFI_ERROR keeps the
# informative DEBUG(ERROR) line but drops the dead-loop assertion, so a
# driver that legitimately returns EFI_NOT_FOUND (TZ/QSEE unavailable on the
# fastboot boot path) no longer pins the firmware in CpuDeadLoop().
text = dlh.read_text(encoding="utf-8")
if "kirby: ASSERT overrides" not in text:
    text += (
        "\n/* kirby: ASSERT overrides (see scripts/build.sh) */\n"
        "#undef ASSERT\n"
        "#define ASSERT(Expression)  do { if (FALSE) { (VOID)(Expression); } } while (FALSE)\n"
        "#undef ASSERT_EFI_ERROR\n"
        "#define ASSERT_EFI_ERROR(Status)  do { if (EFI_ERROR (Status)) { "
        "DEBUG ((DEBUG_ERROR, \"ASSERT_EFI_ERROR (Status = %r)\\n\", Status)); } } while (FALSE)\n"
    )
    dlh.write_text(text, encoding="utf-8")
    print("patched ASSERT + ASSERT_EFI_ERROR overrides")
else:
    print("ASSERT overrides already patched")
PYEOF
grep -n -A3 "DebugAssertEnabled (" "$DBC" | head -6
grep -n "define ASSERT(Expression)" "$DLH"

# dsc 里的两处 0x02 保留：不改行为，但让两种 PCD 类型的取值一致，
# 将来若换成真实的 Release 构建不必再回头找。
log "patching SiliciumPkg.dsc.inc: keep PcdDebugPropertyMask consistent at 0x02"
SCD=Silicon/Silicium/SiliciumPkg/SiliciumPkg.dsc.inc
sed -i 's/PcdDebugPropertyMask|0x2F/PcdDebugPropertyMask|0x02/' "$SCD"
grep -n "PcdDebugPropertyMask|" "$SCD"

# BDS 菜单在 1600x2560 上小到看不清。GraphicsConsoleDxe 用固定 8x19 点阵、不做
# 任何缩放，于是 1600 像素宽折成 200 列字符，屏幕上就是个指甲盖大的方框。
#
# 关键点：GraphicsConsole 算列数用 HorizontalResolution，画行偏移用
# PixelsPerScanLine —— 这两个字段允许不一致。所以让 GOP 报一半的可见区
# (800x1280)、stride 仍用真实宽度 1600，就能得到两倍大小的字符，而且不会斜切
# （斜切正是「分辨率与 stride 不匹配」的典型症状，这里刻意避开）。
#
# FrameBufferSize 保持 Width*Height*4 不变，buffer 仍是整块 1600x2560。
# FrameBufferSerialPortLib 直接写 framebuffer、不走 GOP，所以早期文本输出
# 不受影响，还是铺满全屏。
# 不再把 GOP 分辨率减半。这个补丁当初是为了让字符大一点，但它让 BDS 菜单按
# 800x1280 绘制，在 1600x2560 的面板上只占中间一小块；控制台文字同时被放大
# 两倍，和二维码挤在一起，整屏看起来就是乱的。现在恢复真实分辨率，这一段只
# 负责把以前打过的补丁还原回去（缓存树里可能还留着改过的文件）。
log "restoring SimpleFb.c to the real GOP resolution (undo the earlier halving)"
SFB=Silicon/Silicium/SiliciumPkg/SimpleFbDxe/SimpleFb.c
if [ -f "$SFB" ]; then
  python3 - "$SFB" <<'SFBEOF'
import pathlib
import sys

p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
if "HorizontalResolution = Width  / 2" not in text:
    print("SimpleFb already at full resolution")
    raise SystemExit(0)
text = text.replace("HorizontalResolution = Width  / 2;", "HorizontalResolution = Width;")
text = text.replace("VerticalResolution   = Height / 2;", "VerticalResolution   = Height;")
text = text.replace("VerticalResolution = Height / 2;", "VerticalResolution = Height;")
p.write_text(text, encoding="utf-8")
print("restored full resolution")
SFBEOF
fi

# 内存表打印已撤掉。它把整张 49 行表打到屏幕上，正好占满一屏，把之后异常转储
# 的开头——PC、符号回溯 [0]/[1]、X0..X14——全挤出了屏幕顶部（满屏时
# AdvanceNewLine 会 ZeroMem 清屏重画），崩溃现场最关键的那几行反而拍不到。
log "skipping the MemoryInitPei map dump (removed: it scrolled the fault dump off screen)"

# build_uefi.py takes a pagesize argument and must not treat 0 as "unset".
if ! git apply --reverse --check "$ROOT/patches/uefi-parent.diff" 2>/dev/null; then
  git apply "$ROOT/patches/uefi-parent.diff"
fi

#
# Ride along in the kernel section.
#
# The bootloader does not load the boot image's ramdisk on this tablet -- the
# initrd range in the device tree still points at the previous Android boot's
# cpio archive, 440 MB of conventional memory holds no TB321FUESP volume, and
# neither does the 256 MB "Kernel" window ABL loads the boot image into.  What
# it *does* load is the kernel section, verbatim, into that window.
#
# So append the payload after the firmware volume inside the kernel section:
# BootShim + FD + payload, all gzipped as one stream by mkbootimg.  At runtime
# it sits right after the FD copy and is found by scanning the kernel window for
# the volume label -- no ramdisk, no FV2, no partition writes, and unlike the
# compiled-in blob it is not limited to a few kilobytes.
#
python3 - <<'KERNELEOF'
import pathlib
p = pathlib.Path("build_uefi.py")
text = p.read_text(encoding="utf-8")
needle = "            combined_data = boot_shim_payload.read_bytes () + uefi_fd.read_bytes ()"
extra = (
    needle + "\n"
    "            _kirby_pad = (-len (combined_data)) % 4096\n"
    "            combined_data += b\"\\0\" * _kirby_pad\n"
    "            _kirby_payload = Path (\"Platforms/Lenovo/kirbyPkg/Resources/payload.bin\")\n"
    "            if _kirby_payload.is_file ():\n"
    "                combined_data += _kirby_payload.read_bytes ()\n"
    "                logger.info (f\"kirby: appended {_kirby_payload.stat ().st_size} payload bytes after the FD\")\n"
)
if "_kirby_payload" in text:
    print("kernel payload already patched")
elif needle not in text:
    print("ERROR: kernel-section needle not found")
    raise SystemExit(1)
else:
    p.write_text(text.replace(needle, extra, 1), encoding="utf-8")
    print("kernel payload appended after the FD")
KERNELEOF

# The AArch64 CLANGPDB toolchain never invokes nasm, but the EDK2 self
# describing environment still insists on fetching it through NuGet, which runs
# on mono here and fails. Dropping the extdep removes the requirement.
if [ "$(uname -s)" = "Linux" ]; then
  rm -f Mu_Basecore/BaseTools/Bin/nasm_ext_dep.yaml
fi

# EDK2's build report reads sources with the locale codec, which aborts on
# non-UTF-8 bytes. Only Windows/cp936 is affected, so the patch is applied there
# and skipped everywhere else.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    if ! git -C Mu_Basecore apply --reverse --check "$ROOT/patches/Mu_Basecore-BuildReport.patch" 2>/dev/null; then
      git -C Mu_Basecore apply "$ROOT/patches/Mu_Basecore-BuildReport.patch"
    fi
    ;;
  *)
    echo "skipping the Windows-only build report patch"
    ;;
esac

# 屏幕是这块板子在 USB 栈起来之前唯一的输出口：固件一旦 ASSERT 死循环，
# 只能拍照。为了让照片能机读（而不是靠人眼/OCR 猜），把 SerialPortLib 的每个
# 字节同时 tee 到 MemoryMapLib 已经预留好的 Log_Buffer（0xA7605000，32 KB），
# 再由 kirbyPkg/Drivers/QrLogDxe 把这段文本切成块、画成轮播的二维码。
#
# 这里改的是库、不是驱动：SEC/PEI/DXE 所有模块共用同一个物理缓冲，所以
# 连最早期的输出也能留下来。
log "patching FrameBufferSerialPortLib: tee debug bytes into Log_Buffer"
FBS=Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib/FrameBufferSerialPortLib.c
python3 - "$FBS" <<'PYEOF'
import pathlib
import sys

p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")

if "KirbyLogAppend" in text:
    print("already teed")
    raise SystemExit(0)

helper = '''//
// kirby: tee every debug byte into Log_Buffer so QrLogDxe can render the log
// as QR codes while the panel is the only output device.
//
#define KIRBY_LOG_BASE   0xA7605000ULL
#define KIRBY_LOG_MAX    0x00008000U
#define KIRBY_LOG_MAGIC  0x474F4C4BU  /* 'KLOG' */
#define KIRBY_LOG_HDR    8U

STATIC
VOID
KirbyLogAppend (
  IN CONST UINT8  *Data,
  IN UINTN         Len
  )
{
  volatile UINT32  *Header = (volatile UINT32 *)(UINTN)KIRBY_LOG_BASE;
  volatile UINT8   *Body   = (volatile UINT8 *)(UINTN)(KIRBY_LOG_BASE + KIRBY_LOG_HDR);
  UINT32            Used;
  UINTN             Index;

  if (Header[0] != KIRBY_LOG_MAGIC) {
    Header[0] = KIRBY_LOG_MAGIC;
    Header[1] = 0;
  }

  Used = Header[1];

  //
  // Keep the NEWEST bytes, not the oldest.  UniXNUDxe is dispatched late in
  // APRIORI: with a plain "stop when full" buffer the 32 KiB fills during
  // early DXE and every UniXNU line lands in the discarded tail -- exactly the
  // part that has to be read.  When the write would overflow, drop the older
  // half in one shift, so this costs one move per 16 KiB of output.
  //
  if (Used + Len > (KIRBY_LOG_MAX - KIRBY_LOG_HDR)) {
    UINTN  Half = (KIRBY_LOG_MAX - KIRBY_LOG_HDR) / 2;
    UINTN  Move;

    if (Used > Half) {
      Move = Used - Half;
      for (Index = 0; Index < Half; Index++) {
        Body[Index] = Body[Move + Index];
      }
      Used = Half;
    }
  }

  for (Index = 0; (Index < Len) && ((Used + Index) < (KIRBY_LOG_MAX - KIRBY_LOG_HDR)); Index++) {
    Body[Used + Index] = Data[Index];
  }

  Header[1] = Used + (UINT32)Index;
}

'''

marker = "UINTN\nEFIAPI\nSerialPortWrite ("
if marker not in text:
    print("SerialPortWrite marker not found", file=sys.stderr)
    sys.exit(1)
text = text.replace(marker, helper + marker, 1)

body = (
    "  EFI_STATUS           Status;\n"
    "  EFI_PHYSICAL_ADDRESS FbBase;\n"
    "  UINT64               FbLength;\n"
)
if body not in text:
    print("SerialPortWrite body marker not found", file=sys.stderr)
    sys.exit(1)
text = text.replace(body, body + "\n  KirbyLogAppend (Buffer, NumberOfBytes);\n", 1)

p.write_text(text, encoding="utf-8")
print("teed SerialPortWrite into Log_Buffer")
PYEOF
grep -n -A2 "KirbyLogAppend (Buffer" "$FBS"

# BDS 的启动菜单一进来就 ClearScreen，把 QrLogDxe 画好的二维码整屏抹掉——这就是
# 照片里只有菜单、没有码的原因。把这三处清屏注释掉，二维码就能留在菜单底下，
# 两者同屏：菜单在中间，码在左下角，控制台文字在上方。
# BDS 的菜单一进来就 ClearScreen，把 QrLogDxe 画好的二维码整屏抹掉——照片里只有
# 菜单没有码就是这个原因。PcdBootManagerMenuFile 指向的是 UiApp，所以真正的清屏
# 在 MdeModulePkg/Application/UiApp/FrontPage.c；BootManagerMenuApp 里也有三处，
# 一并关掉。关掉后菜单照样画，只是不再擦背景，二维码就留在左下角。
log "patching UiApp/FrontPage.c and BootManagerMenuApp: keep the screen for the QR log"
python3 - <<'UIAEOF'
import pathlib

targets = [
    "MdeModulePkg/Application/UiApp/FrontPage.c",
    "MdeModulePkg/Application/BootManagerMenuApp/BootManagerMenu.c",
    # BdsEntry itself clears the screen right before it hands over to the boot
    # manager, which is what wipes every DEBUG line emitted by drivers that ran
    # earlier (VariableRuntimeDxe, UniXNUDxe...).  Without this the screen only
    # ever shows "[Bds] Connect ConIn failed", and "driver never dispatched"
    # cannot be told apart from "driver dispatched and failed".
    "MdeModulePkg/Universal/BdsDxe/BdsEntry.c",
]
needle = "gST->ConOut->ClearScreen (gST->ConOut);"
for rel in targets:
    p = pathlib.Path(rel)
    if not p.exists():
        print(f"skip {rel} (not present)")
        continue
    text = p.read_text(encoding="utf-8")
    if needle not in text:
        print(f"{rel}: already patched")
        continue
    p.write_text(text.replace(needle, "/* kirby: keep the QR log on screen */ (VOID)0;"),
                 encoding="utf-8")
    print(f"{rel}: clear-screen disabled")
UIAEOF

log "building $TARGET"
# EDK2's CLANGPDB toolchain wants the aarch64 binutils prefix on Linux hosts.
if [ "$(uname -s)" = "Linux" ]; then
  export CLANGPDB_AARCH64_PREFIX=${CLANGPDB_AARCH64_PREFIX:-aarch64-linux-gnu-}
fi
"$WORK/.venv/bin/python" build_uefi.py -d kirby -r "$TARGET"

#
# Fat.efi is the one module whose absence looks exactly like a rejected volume:
# BlockIo and DiskIo both bind, SimpleFileSystem never appears, and Fat prints
# nothing when it declines a device.  FVMAIN reports 99% full, so check the GUID
# cross-reference instead of guessing which of the two it is.
#
GUIDXREF="Build/kirbyPkg/${TARGET}_CLANGPDB/FV/Guid.xref"
if [ -f "$GUIDXREF" ]; then
  log "Fat.efi (961578FE-B6B7-44C3-AF35-6BC705CD2B1F) in Guid.xref:"
  grep -i 961578FE "$GUIDXREF" || echo "  Fat.efi NOT PRESENT in the firmware volume"
  log "EnglishDxe in Guid.xref:"
  grep -i english "$GUIDXREF" || echo "  EnglishDxe NOT PRESENT in the firmware volume"
else
  log "no Guid.xref at $GUIDXREF"
fi

OUT=$(ls -1 Mu-kirby*.img 2>/dev/null | head -1 || true)
if [ -z "$OUT" ]; then
  echo "build finished but no Mu-kirby*.img was produced" >&2
  exit 1
fi

log "result"
ls -l "$OUT"
sha256sum "$OUT"
printf '\nflash with: fastboot boot %s\n' "$OUT"
