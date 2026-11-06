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
# UniXNU payload.  build_uefi.py:331 passes "--ramdisk Resources/ramdisk" to
# mkbootimg, so this file becomes the boot image's ramdisk field.  On a GKI
# target that is the only way the payload can ride along with `fastboot boot`:
# the boot partition itself has no ramdisk, and we never write vendor_boot.
# UniXNURamDiskDxe then turns it into a read-only block device via the Mu FDT
# initrd handover.
#
if [ -f "$ROOT/Resources/ramdisk" ]; then
  cp "$ROOT/Resources/ramdisk" Resources/ramdisk
  log "staged payload ramdisk ($(stat -c%s Resources/ramdisk) bytes)"
fi
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
# Diagnostic only: SetVariable("Boot0000") returns EFI_INVALID_PARAMETER and the
# two candidate causes are indistinguishable from the outside -- OptionSize == 0
# (DataSize 0 with non-zero attributes is an invalid delete) versus this
# memory-only variable store rejecting EFI_VARIABLE_NON_VOLATILE.  Print both.
#
python3 - "$UNIXNU_DXE_C" <<'DXEEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    print("skip: %s not present" % p)
    raise SystemExit(0)
text = p.read_text(encoding="utf-8")
needle = "    Status = gRT->SetVariable (Name, &gEfiGlobalVariableGuid, OPTION_ATTRIBUTES, OptionSize, Option);"
probe = (
    '    DEBUG ((DEBUG_ERROR, "UniXNUDxe: write %s attr=0x%x size=%u\\n", '
    'Name, (UINT32)OPTION_ATTRIBUTES, (UINT32)OptionSize));\n'
    '    {\n'
    '      UINT32      KirbyProbeValue = 0x4B495242;\n'
    '      EFI_STATUS  KirbyProbeStatus;\n'
    '      KirbyProbeStatus = gRT->SetVariable (L"KirbyProbeNv", &gEfiGlobalVariableGuid,\n'
    '                                           EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_NON_VOLATILE,\n'
    '                                           sizeof (KirbyProbeValue), &KirbyProbeValue);\n'
    '      DEBUG ((DEBUG_ERROR, "UniXNUDxe: probe nv=%r\\n", KirbyProbeStatus));\n'
    '      KirbyProbeStatus = gRT->SetVariable (L"KirbyProbeBs", &gEfiGlobalVariableGuid,\n'
    '                                           EFI_VARIABLE_BOOTSERVICE_ACCESS,\n'
    '                                           sizeof (KirbyProbeValue), &KirbyProbeValue);\n'
    '      DEBUG ((DEBUG_ERROR, "UniXNUDxe: probe bs=%r\\n", KirbyProbeStatus));\n'
    '    }\n'
)
if needle not in text:
    print("SetVariable needle not found")
elif probe in text:
    print("already probed")
else:
    p.write_text(text.replace(needle, probe + needle, 1), encoding="utf-8")
    print("added SetVariable probe")
DXEEOF

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

OUT=$(ls -1 Mu-kirby*.img 2>/dev/null | head -1 || true)
if [ -z "$OUT" ]; then
  echo "build finished but no Mu-kirby*.img was produced" >&2
  exit 1
fi

log "result"
ls -l "$OUT"
sha256sum "$OUT"
printf '\nflash with: fastboot boot %s\n' "$OUT"
