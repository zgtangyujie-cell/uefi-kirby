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
# idempotent: detect the marker, print, and carry on.
if "kirby: ASSERT no-op" in dbc.read_text(encoding="utf-8"):
    print("DebugLib already patched, skipping")
    raise SystemExit(0)

# --- 1. DebugAssertEnabled() -> FALSE -------------------------------------
text = dbc.read_text(encoding="utf-8")
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

# --- 2. ASSERT(Expression) macro -> empty ---------------------------------
text = dlh.read_text(encoding="utf-8")
macro = re.compile(
    r"#define\s+ASSERT\s*\(\s*Expression\s*\)\s*\\[ \t]*\r?\n"
    r"(?:[^\n]*\\[ \t]*\r?\n)*"
    r"[^\n]*while\s*\(\s*FALSE\s*\)"
)
hits = macro.findall(text)
if len(hits) < 1:
    print("ASSERT(Expression) macro not found", file=sys.stderr)
    sys.exit(1)
text = macro.sub(
    "#define ASSERT(Expression)  do { if (FALSE) { (VOID)(Expression); } } while (FALSE)",
    text,
)
dlh.write_text(text, encoding="utf-8")
print(f"patched: DebugAssertEnabled + {len(hits)} ASSERT macro block(s)")
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
log "patching SimpleFb.c: halve the GOP visible area so the menu is readable"
SFB=Silicon/Silicium/SiliciumPkg/Drivers/SimpleFbDxe/SimpleFb.c
python3 - "$SFB" <<'PYEOF'
import re
import sys
import pathlib

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "HorizontalResolution = Width  / 2" in text:
    print("SimpleFb already halved, skipping")
    raise SystemExit(0)

pattern = re.compile(
    r"(mFrameBuffer\.Mode->Info->HorizontalResolution\s*=\s*)Width(\s*;)"
    r"(\s*\n\s*mFrameBuffer\.Mode->Info->VerticalResolution\s*=\s*)Height(\s*;)"
)
hits = pattern.findall(text)
if len(hits) != 1:
    print(f"GOP resolution assignment matched {len(hits)} times, expected 1", file=sys.stderr)
    sys.exit(1)

text = pattern.sub(
    r"\1Width  / 2\2\3Height / 2\4",
    text,
    count=1,
)
path.write_text(text, encoding="utf-8")
print("patched GOP resolution: visible area halved, PixelsPerScanLine untouched")
PYEOF
grep -n -B1 -A2 "HorizontalResolution = Width" "$SFB"

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
  if (Used >= (KIRBY_LOG_MAX - KIRBY_LOG_HDR)) {
    return;
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
