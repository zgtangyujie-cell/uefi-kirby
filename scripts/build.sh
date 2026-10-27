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

log "installing the kirby device package"
cp -r "$ROOT/Platforms/Lenovo/kirbyPkg" Platforms/Lenovo/
cp    "$ROOT/Resources/Configs/kirby.toml" Resources/Configs/
# 用我们自己的最小设备树覆盖 kirby.dtb（ButtonsDxe 需要 /soc/buttons 节点）
cp    "$ROOT/Resources/DTBs/kirby.dtb"     Resources/DTBs/
if [ -f "$ROOT/Resources/DTBs/kirby-buttons.dts" ]; then
  dtc -I dts -O dtb -o Resources/DTBs/kirby.dtb "$ROOT/Resources/DTBs/kirby-buttons.dts"
  log "compiled kirby-buttons.dts -> kirby.dtb ($(stat -c%s Resources/DTBs/kirby.dtb) bytes)"
fi
  mkdir -p Platforms/Lenovo/kirbyPkg/FdtBlob
  cp Resources/DTBs/kirby.dtb Platforms/Lenovo/kirbyPkg/FdtBlob/lanai-lenovo-kirby.dtb
  log "staged FdtBlob for FV embedding"
mkdir -p Binaries
cp -r "$ROOT/Binaries/kirby" Binaries/

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

# 把 MemoryMapLib 实际生效的整张表打到屏幕上。崩溃时 adb/fastboot 都没了、
# pstore 是空的、异常 dump 只有寄存器和栈，拿不到页表；把表本身打出来，
# 就能拿 FAR 直接对照，不必再猜。
#
# 打印放在 MemoryInitPei.c 而不是 MemoryMapLib 自己里面：MemoryMapLib 一旦
# 依赖 DebugLib，就会和 SerialPortLib 形成环 ——
#   MemoryMapLib -> DebugLib -> FrameBufferSerialPortLib
#                -> MemoryMapHelperLib -> GetMemoryMap (MemoryMapLib)
# MemoryInitPei 本来就依赖 DebugLib，并且已经拿到了 GetMemoryMap 的返回值，
# 从那里打不会引入任何新依赖。
log "patching MemoryInitPei: dump the memory map before the MMU is configured"
python3 - <<'PY'
import pathlib

# cwd is $WORK/uefi -- the Mu-Silicium checkout, not this repo.
src = pathlib.Path("Silicon/Silicium/SiliciumPkg/Library/MemoryInitPeiLib/MemoryInitPei.c")
s = src.read_text()

needle = "  GetMemoryMap (&MemoryDescriptor, &MemoryDescriptorCount);"
assert needle in s, "GetMemoryMap call not found in MemoryInitPei.c"

dump = """
#ifndef MDEPKG_NDEBUG
  // Dump the map that is about to become the page tables, so a later crash can
  // be matched against what was actually mapped instead of guessed at.
  //
  // This block keeps its own counter and its own scope on purpose. The function
  // already has `Index`, initialised to 0 at declaration and incremented by the
  // memory-table loop below without ever being reset -- reusing it here left
  // the table empty and ArmConfigureMmu ran on all-zero descriptors, which hung
  // the firmware silently right after this point.
  {
    UINT8  DumpIndex;

    DEBUG ((EFI_D_WARN, "\\nMemoryMap: %u regions\\n", (UINT32)MemoryDescriptorCount));
    for (DumpIndex = 0; DumpIndex < MemoryDescriptorCount; DumpIndex++) {
      DEBUG ((
        EFI_D_WARN,
        "  %2u %a 0x%08lx + 0x%08lx%a\\n",
        (UINT32)DumpIndex,
        MemoryDescriptor[DumpIndex].Name,
        (UINT64)MemoryDescriptor[DumpIndex].Address,
        (UINT64)MemoryDescriptor[DumpIndex].Length,
        (MemoryDescriptor[DumpIndex].HobOption == AddDev) ? "  [dev]" : ""
        ));
    }
    DEBUG ((EFI_D_WARN, "\\n"));
  }
#endif
"""

if "MemoryMap: %u regions" not in s:
    s = s.replace(needle, needle + "\n" + dump, 1)
    src.write_text(s)

ok = "MemoryMap: %u regions" in src.read_text()
print("MemoryInitPei: map dump injected =", ok)
PY

# build_uefi.py takes a pagesize argument and must not treat 0 as "unset".
if ! git apply --reverse --check "$ROOT/patches/uefi-parent.diff" 2>/dev/null; then
  git apply "$ROOT/patches/uefi-parent.diff"
fi

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

log "building $TARGET"
# EDK2's CLANGPDB toolchain wants the aarch64 binutils prefix on Linux hosts.
if [ "$(uname -s)" = "Linux" ]; then
  export CLANGPDB_AARCH64_PREFIX=${CLANGPDB_AARCH64_PREFIX:-aarch64-linux-gnu-}
fi
"$WORK/.venv/bin/python" build_uefi.py -d kirby -r "$TARGET"

OUT=$(ls -1 Mu-kirby*.img 2>/dev/null | head -1 || true)
if [ -z "$OUT" ]; then
  echo "build finished but no Mu-kirby*.img was produced" >&2
  exit 1
fi

log "result"
ls -l "$OUT"
sha256sum "$OUT"
printf '\nflash with: fastboot boot %s\n' "$OUT"
