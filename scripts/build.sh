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

# 关掉 ASSERT 的死循环。AutoGen.c 在每个驱动入口点末尾都有
# ASSERT_EFI_ERROR (Status)，而"可选设备不存在"让驱动返回 EFI_NOT_FOUND 是完全
# 正常的（kirby 上是 EnvDxeEnhanced），DxeCore 本来会卸载它继续走 —— 但
# ASSERT 会先进 CpuDeadLoop，整个固件就钉死在一个不该管的驱动上。
#
# 为什么不去调 PCD：试过三轮，全部无效。
#   - kirby.dsc 的 [PcdsFixedAtBuild] 段给 PcdDebugPropertyMask 赋 0x02  —— 无效
#   - SiliciumPkg.dsc.inc:69（同样在 [PcdsFixedAtBuild] 段）改成 0x02   —— 无效
#   - MdePkg.dec 的默认值是 0（不是常见的 0x0f），改它也无从谈起
# PcdDebugPropertyMask 在 MdePkg.dec 里声明为 [PcdsFixedAtBuild,PcdsPatchableInModule]
# 双类型，而 DebugLib 到底解析哪一份，在看不到 CI 日志的情况下无法确认。
#
# 所以改成直接动函数：ASSERT 宏的第一句就是 if (DebugAssertEnabled())，
# 让它恒返回 FALSE，则无论 PCD 读到什么值，ASSERT 都进不去，
# 而 DEBUG() 走的是另一个函数 DebugPrintEnabled()，调试输出完全不受影响。
log "patching BaseDebugLibSerialPort: DebugAssertEnabled() -> FALSE"
DBC=Mu_Basecore/MdePkg/Library/BaseDebugLibSerialPort/DebugLib.c
python3 - "$DBC" <<'PYEOF'
import re
import sys
import pathlib

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# 容忍空白差异：mu_basecore 的 submodule 指向的具体 commit 未必与 release 分支
# HEAD 逐字相同，写死缩进容易在几周后失效。
pattern = re.compile(
    r"return\s*\(\s*BOOLEAN\s*\)\s*\(\s*\(\s*PcdGet8\s*\(\s*PcdDebugPropertyMask\s*\)"
    r"\s*&\s*DEBUG_PROPERTY_DEBUG_ASSERT_ENABLED\s*\)\s*!=\s*0\s*\)\s*;"
)
hits = pattern.findall(text)
if len(hits) != 1:
    print(f"DebugAssertEnabled body matched {len(hits)} times, expected 1", file=sys.stderr)
    sys.exit(1)

replacement = "return FALSE; /* kirby: ASSERT no-op for bring-up, see scripts/build.sh */"
text = pattern.sub(lambda _m: replacement, text, count=1)
path.write_text(text, encoding="utf-8")
print("patched DebugAssertEnabled")
PYEOF
grep -n -A3 "DebugAssertEnabled (" "$DBC" | head -8

# dsc 里的两处 0x02 保留：不改行为，但让两种 PCD 类型的取值一致，
# 将来若换成真实的 Release 构建不必再回头找。
log "patching SiliciumPkg.dsc.inc: keep PcdDebugPropertyMask consistent at 0x02"
SCD=Silicon/Silicium/SiliciumPkg/SiliciumPkg.dsc.inc
sed -i 's/PcdDebugPropertyMask|0x2F/PcdDebugPropertyMask|0x02/' "$SCD"
grep -n "PcdDebugPropertyMask|" "$SCD"

# 内存表打印已撤掉。它把整张 49 行表打到屏幕上，正好占满一屏，把之后异常转储
# 的开头——PC、符号回溯 [0]/[1]、X0..X14——全挤出了屏幕顶部（满屏时
# AdvanceNewLine 会 ZeroMem 清屏重画），崩溃现场最关键的那几行反而拍不到。
log "skipping the MemoryInitPei map dump (removed: it scrolled the fault dump off screen)"

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
