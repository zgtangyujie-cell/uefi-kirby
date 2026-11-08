#!/usr/bin/env python3
"""Seed PE_state.video from DarwinBoot, because the kernel never does.

Measured across the whole 51,695,616-byte kernel that this board builds:
nothing writes PE_state.video or PE_state.boot_args.  Three spellings were
scanned and all came back empty - `adrp + add + str`, a `movz/movk` constant
build, and a direct `str xT, [xN, #off]` whose base came from `adrp`.  The only
reference to PE_state.video is _PE_create_console forwarding the address to
_initialize_screen:

    0x794aa9c  adrp x0, 0x71fc000
    0x794aaa0  add  x0, x0, #0x8d8      PE_state.video
    0x794aabc  b    _initialize_screen  (tail call, w1 = 5)

so _initialize_screen receives an all-zero PE_Video, leaves _vinfo zero, and
every console guard (`v->v_baseaddr == 0`) refuses.  That is why a kernel that
runs for 130 seconds paints nothing.

DarwinBoot, on the other hand, holds the real numbers: Video[] comes from GOP in
BootVideo.h and is printed at hand-off.  Its field order is ABI, not PE_Video -
Video[1] is the constant 1 and Video[2..5] are rowBytes, width, height, depth -
and this script writes them into the kernel's own PE_Video in the right order.

The address is resolved from the kernel's LC_SYMTAB rather than hardcoded:
prelink moves _PE_state by 0xA8 between a 19.1 MiB and a 49.3 MiB build
(0xFFFFFFF0071FC828 vs 0xFFFFFFF0071FC8D0).
"""

import sys
from pathlib import Path

MARKER = "KirbyPeVideo"

FINDER = '''
//
// KirbyPeVideo: resolve a symbol from the kernel's LC_SYMTAB.
//
// DarwinBoot already parses the Mach-O segments (ParseKernel); this walks the
// load commands for LC_SYMTAB and matches one name.  It exists so that nothing
// below needs a hardcoded address: prelink moves _PE_state by 0xA8 between a
// 19.1 MiB and a 49.3 MiB build.
//
STATIC
BOOLEAN
KirbyFindSymbol (
  CONST UINT8  *Data,
  UINTN        Size,
  CONST CHAR8  *Name,
  UINT64       *Value
  )
{
  UINTN  Offset;
  UINTN  Commands;
  UINTN  Index;

  if ((Data == NULL) || (Size < 32) || (Name == NULL) || (Value == NULL)) { return FALSE; }
  Commands = ReadUnaligned32 ((CONST UINT32 *)(Data + 16));
  Offset   = 32;
  for (Index = 0; Index < Commands; Index++) {
    UINT32  Command;
    UINT32  Length;

    if (Offset + 8 > Size) { return FALSE; }
    Command = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset));
    Length  = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset + 4));
    if ((Length < 8) || (Offset + Length > Size)) { return FALSE; }
    if (Command == 0x2) {
      UINTN  SymOff  = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset + 8));
      UINTN  Symbols = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset + 12));
      UINTN  StrOff  = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset + 16));
      UINTN  StrSize = ReadUnaligned32 ((CONST UINT32 *)(Data + Offset + 20));
      UINTN  Symbol;

      if ((SymOff + Symbols * 16 > Size) || (StrOff + StrSize > Size)) { return FALSE; }
      for (Symbol = 0; Symbol < Symbols; Symbol++) {
        UINTN        StrX = ReadUnaligned32 ((CONST UINT32 *)(Data + SymOff + Symbol * 16));
        CONST CHAR8  *Text;

        if (StrX >= StrSize) { continue; }
        Text = (CONST CHAR8 *)(Data + StrOff + StrX);
        if (AsciiStrCmp (Text, Name) == 0) {
          *Value = ReadUnaligned64 ((CONST UINT64 *)(Data + SymOff + Symbol * 16 + 8));
          return TRUE;
        }
      }
      return FALSE;
    }
    Offset += Length;
  }
  return FALSE;
}
'''

SEED = '''  //
  // KirbyPeVideo: seed PE_state.video before the kernel branch.
  //
  // Nothing in the kernel writes this field, so _initialize_screen gets an empty
  // PE_Video and every console guard refuses.  Video[] here is the real thing,
  // measured from GOP; write it in PE_Video's order, not Video[]'s.
  //
  {
    UINT64  PeState;
    UINT64  PeVideo;

    if (KirbyFindSymbol (Image, ImageSize, "_PE_state", &PeState)) {
      PeVideo = PeState + 8;
      if ((PeVideo >= Kernel.Base) && (PeVideo < Kernel.Base + (Kernel.End - Kernel.Base))) {
        UINT64  *Pv = (UINT64 *)(UINTN)(Address + (PeVideo - Kernel.Base));

        Pv[0] = Video[0];   // v_baseAddr
        Pv[1] = Video[2];   // v_rowBytes  - Video[1] is the constant 1, not this
        Pv[2] = Video[3];   // v_width
        Pv[3] = Video[4];   // v_height
        Pv[4] = Video[5];   // v_depth
        Print (L"DARWINBOOT: PE_state.video <- 0x%lx %lux%lu row %lu depth %lu\\n",
               Video[0], Video[3], Video[4], Video[2], Video[5]);
      }
    }
  }
'''


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARKER in text:
        print("DarwinBoot: PE_state.video seed already applied")
        return 0

    anchor = "STATIC\nEFI_STATUS\nParseKernel ("
    if anchor not in text:
        raise SystemExit("ParseKernel declaration not found")
    text = text.replace(anchor, FINDER.strip("\n") + "\n\n" + anchor, 1)

    seed_anchor = "  CopyMem ((VOID *)(UINTN)TreeAddress, Tree, TreeSize);"
    if seed_anchor not in text:
        raise SystemExit("TreeAddress CopyMem anchor not found")
    text = text.replace(seed_anchor, seed_anchor + "\n" + SEED, 1)

    path.write_text(text, encoding="utf-8")
    print("DarwinBoot: PE_state.video seed inserted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
