#!/usr/bin/env python3
"""Seed PE_state.video from DarwinBoot, because the kernel never does.

Measured across the whole 51,695,616-byte kernel that this board builds:
nothing writes PE_state.video or PE_state.boot_args.  Three spellings were
scanned and all came back empty - `adrp + add + str`, a `movz/movk` constant
build, and a direct `str xT, [xN, #off]` whose base came from `adrp`. The only
reference to PE_state.video is _PE_create_console forwarding the address to
_initialize_screen.

PE_state.video is an INLINE PE_Video struct at PE_state+8, not a pointer.
Disassembly of _k_4f4e91c.macho (2026-11-09):

    _PE_create_console   adrp x0,#0x71fc000 ; add x0,x0,#0x8d8  -> x0 = PE_state+8
                         ldr  x8,[x0,#0x28]                      (v_display)
                         mov  w1,#5 ; b _initialize_screen       (tail call)
    _initialize_screen   cbz  x0,... ; ldr w24,[x20,#8] ; ldr w28,[x20,#0x10]
                         ldr w26,[x20,#0x18] ; ldr w10,[x20,#0x20]
                         (rowBytes / width / height / depth)
    PE_get_video-style   0x90-byte ldp/stp copy from PE_state+8, ending exactly
                         at deviceTreeHead (PE_state+0x98) -> sizeof = 0x90.

Source of truth for the same layout (xnu-full tree, 2026-11-09):

    pexpert/pexpert/pexpert.h:334-340   PE_state.video is an INLINE PE_Video
    pexpert/pexpert/pexpert.h:285-303   PE_Video field order; sizeof = 0x90
    pexpert/arm/pe_init.c:528-532       PE_create_console passes &PE_state.video
    osfmk/kern/startup.c:716            initialize_screen(NULL, kPEAcquireScreen)
    osfmk/console/video_console.c:2804  if (boot_vinfo) wraps gc_initialize (:2929)

DarwinBoot holds the real numbers: Video[] comes from GOP in BootVideo.h and
is printed at hand-off.  Its field order is ABI, not PE_Video - Video[1] is
the constant 1 and Video[2..5] are rowBytes, width, height, depth - and this
script writes them into the kernel's own PE_Video in the right order.

Three things the first version of this seed got wrong (collab/INBOX.md
2026-11-09; elden.md:152 names the same missing marker):

  * bit0 of v_baseAddr is initialize_screen's physical-address marker:
    makeMapping = (kernel_map == VM_MAP_NULL) || (0 != (1 & newVideoVirt))
    (video_console.c:2843).  Video[0] = 0xD5100000 has bit0 = 0, so the
    framebuffer was never mapped, vinfo kept the physical address, and
    gc_putchar wrote it as a virtual address - the T-gfx round reset 220 s
    in with the seed already proven landed.  With bit0 set, :2880
    ml_io_map_unmappable maps the panel and :2929 arms the console.
  * the remaining 13 lanes were left uninitialised; v_display must stay 0
    (kPETextMode, not kPEGraphicsMode) and v_offset must stay 0 or the draw
    address shifts (video_console.c:2882).  All 18 lanes are zeroed first.
  * a POINTER written at PE_state+8 is not an option: it lands in v_baseAddr
    and leaves v_rowBytes..v_depth zero (pexpert.h:334-340), i.e. a 0x0
    console.  The struct is seeded in place.

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
        UINT8        Type = *(CONST UINT8 *)(Data + SymOff + Symbol * 16 + 4);
        CONST CHAR8  *Text;

        if (StrX >= StrSize) { continue; }
        //
        // Skip N_UNDF.  _PE_state appears twice in this kernel's symtab: index
        // 249883 is undefined with value 0, index 253359 is N_SECT with the real
        // 0xFFFFFFF0071FC8D0.  Returning the first match handed DarwinBoot a
        // zero, its range check rejected it, and the seed silently wrote nothing
        // (measured: the panel read "seed: PE_state 0 bas...").
        //
        if ((Type & 0x0e) == 0x00) { continue; }
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
  // PE_state.video is an INLINE struct at PE_state+8 (pexpert.h:334-340) and
  // PE_create_console passes &PE_state.video (pe_init.c:528-532), so the 18
  // lanes below ARE the struct.  A pointer here would land in v_baseAddr and
  // leave the geometry zero.
  //
  {
    UINT64  PeState;
    UINT64  PeVideo;

    if (KirbyFindSymbol (Image, ImageSize, "_PE_state", &PeState)) {
      CHAR16  KirbySeedText[96];

      PeVideo = PeState + 8;
      UnicodeSPrint (KirbySeedText, sizeof (KirbySeedText), L"seed: PE_state %lx video %lx", PeState, PeVideo);
      DiagDraw (KirbySeedText, 12);
      if ((PeVideo >= Kernel.Base) && (PeVideo + 0x90 <= Kernel.Base + (Kernel.End - Kernel.Base))) {
        UINT64  *Pv = (UINT64 *)(UINTN)(Address + (PeVideo - Kernel.Base));

        ZeroMem (Pv, 0x90);        // 18 lanes: v_display / v_offset / v_length stay 0
        Pv[0] = Video[0] | 1ULL;   // v_baseAddr  - bit0: physical-address marker
        Pv[1] = Video[2];          // v_rowBytes  - Video[1] is the constant 1, not this
        Pv[2] = Video[3];          // v_width
        Pv[3] = Video[4];          // v_height
        Pv[4] = Video[5];          // v_depth
        Pv[5] = 0;                 // v_display = 0 -> kPETextMode (ZeroMem already did)
        Print (L"seed: PE_state.video <- pa %lx va %lx %lux%lu row %lu depth %lu\\n",
               Video[0] | 1ULL, (UINT64)(UINTN)Pv, Video[3], Video[4], Video[2], Video[5]);
        UnicodeSPrint (KirbySeedText, sizeof (KirbySeedText), L"seed: b=%lx w=%lx h=%lx r=%lx d=%lx",
                       Video[0], Video[3], Video[4], Video[2], Video[5]);
        DiagDraw (KirbySeedText, 13);
        UnicodeSPrint (KirbySeedText, sizeof (KirbySeedText), L"written: %lx %lx %lx %lx %lx",
                       Pv[0], Pv[1], Pv[2], Pv[3], Pv[4]);
        DiagDraw (KirbySeedText, 14);
      } else {
        UnicodeSPrint (KirbySeedText, sizeof (KirbySeedText), L"seed: PE_state %lx outside window", PeState);
        DiagDraw (KirbySeedText, 12);
      }
    } else {
      CHAR16  KirbySeedText[96];

      UnicodeSPrint (KirbySeedText, sizeof (KirbySeedText), L"seed: _PE_state NOT FOUND in symtab");
      DiagDraw (KirbySeedText, 12);
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
