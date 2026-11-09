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
    pexpert/arm/pe_init.c:520-533       PE_create_console passes &PE_state.video
    pexpert/arm/pe_init.c:192           PE_initialize_console -> initialize_screen
    osfmk/kern/startup.c:716            initialize_screen(NULL, kPEAcquireScreen)
    osfmk/console/video_console.c:2797  if (boot_vinfo) wraps gc_initialize (:2929)

Call order (xnu-full source, 2026-11-09): PE_create_console is called from
osfmk/arm/arm_init.c:577.  startup.c:716's initialize_screen(NULL,
kPEAcquireScreen) lives in kernel_bootstrap_thread (startup.c:600), which
arm_init starts only afterwards.  So the NON-NULL call -- the one this seed
feeds -- happens FIRST, and the NULL one merely arms kPEAcquireScreen after
it.  (An earlier comment claimed the reverse, "bsd_init"; the call site is
arm_init.c:577, before the bootstrap thread.)  Nothing writes
PE_state.video in the kernel (scanned all 51,695,616 bytes), so without
the seed even that first call sees an empty struct and gc_initialize never
runs -- a zero v_baseAddr takes the "No video" branch and v_depth drops to
0 ("vc routines are nop", video_console.c), which is exactly the silent
console the panel photos showed.

DarwinBoot holds the real numbers: Video[] comes from GOP in BootVideo.h and
is printed at hand-off.  Its field order is ABI, not PE_Video - Video[1] is
the constant 1 and Video[2..5] are rowBytes, width, height, depth - and this
script writes them into the kernel's own PE_Video in the right order.

REPORT PLACEMENT (2026-11-09, panel photo of the efca92d round):

The first version reported with DiagDraw rows 12/13/14 at the seed site.
DarwinBoot.c:797 fires "\fDARWINBOOT: hand-off to the kernel" AFTER the seed,
which clears the console; and the hand-off DEBUG family (:798-812) repaints
the console band over screen y~1259-1836, which covers rows 12-14
(1312/1368/1424).  Measured on the photo: only tail glyphs of row 12 showed
through between DEBUG lines; rows 13/14 and the Print line were gone.  The
T-gfx paint at row 6 DID survive, which proves DiagDraw+GOP itself works.

So the seed now splits: the WRITE stays at :754 (Image is alive there; it is
FreePool'd at :779), and the REPORT moves after the last hand-off DEBUG line
but BEFORE the ExitBootServices loop -- gBS dies with ExitBootServices and
DiagDraw would silently return.  A file-scope triple carries the values
across.  Report rows are 25/26/27 (screen y 2040/2096/2152): the photo's
console band ends ~y1836 and the boot menu sits ~y2245, so rows 23-28 are
the measured-empty gap.  The Print line rides the live console tail, the one
channel nothing drawn later can cover.

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

FINDER = '''
//
// KirbyPeVideo: hand-off between the seed site and the report site.
//
// The seed runs at :754, where Image is still alive (FreePool at :779).  The
// report runs after the last hand-off DEBUG line, past the :797 form feed --
// by then Image is gone, so the values the report needs ride here.
//
STATIC BOOLEAN  mKirbyPeVideoSeeded = FALSE;
STATIC UINT64   mKirbyPeVideoState  = 0;
STATIC UINT64   *mKirbyPeVideoPv    = NULL;
STATIC UINT64   mKirbyPeVideoArgs   = 0;   /* boot_args->Video base, 0 = not written */

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
  // PE_create_console passes &PE_state.video (pe_init.c:520-533), so the 18
  // lanes below ARE the struct.  A pointer here would land in v_baseAddr and
  // leave the geometry zero.
  //
  // This site only WRITES; the report lives after the last hand-off DEBUG
  // line (REPORT below), because the :797 form feed and the DEBUG family
  // erase anything painted here -- measured on the efca92d panel photo.
  //
  {
    UINT64  PeState;
    UINT64  PeVideo;

    mKirbyPeVideoSeeded = FALSE;
    mKirbyPeVideoState  = 0;
    mKirbyPeVideoPv     = NULL;
    if (KirbyFindSymbol (Image, ImageSize, "_PE_state", &PeState)) {
      mKirbyPeVideoState = PeState;
      PeVideo = PeState + 8;
      if ((PeVideo >= Kernel.Base) && (PeVideo + 0x90 <= Kernel.Base + (Kernel.End - Kernel.Base))) {
        UINT64  *Pv = (UINT64 *)(UINTN)(Address + (PeVideo - Kernel.Base));

        ZeroMem (Pv, 0x90);        // 18 lanes: v_display / v_offset / v_length stay 0
        Pv[0] = Video[0] | 1ULL;   // v_baseAddr  - bit0: physical-address marker
        Pv[1] = Video[2];          // v_rowBytes  - Video[1] is the constant 1, not this
        Pv[2] = Video[3];          // v_width
        Pv[3] = Video[4];          // v_height
        Pv[4] = Video[5];          // v_depth
        Pv[5] = 0;                 // v_display = 0 -> kPETextMode (ZeroMem already did)
        mKirbyPeVideoPv     = Pv;
        mKirbyPeVideoSeeded = TRUE;
      }
    }
    //
    // KirbyPeVideo: ALSO write boot_args->Video, because the block above is
    // discarded.  pe_init.c:413-430 (PE_init_platform) copies boot_args->Video
    // over PE_state.video, and arm_init.c:371 calls PE_init_platform with the
    // real boot_args long before PE_create_console at :577.  So boot_args is the
    // SOURCE and PE_state.video is the derived copy: writing only PE_state is a
    // no-op by the time _initialize_screen reads it.
    //
    // Boot_Video is six u64 at boot_args+0x28 (DarwinBoot's BootArgs.h asserts
    // OFFSET_OF (DARWIN_BOOT_ARGS, Video) == 0x28), and Boot_Video's member order
    // is v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth.  So the
    // second word -- boot_args+0x30 -- is v_display, and 0 selects kPETextMode.
    //
    // This is not cosmetic.  v_display decides the op that _PE_create_console's
    // `cinc w1, w20, eq` computes, and that op is recorded in gc_graphics_boot:
    //   op == 1 (graphics) -> gc_graphics_boot TRUE  -> startup.c:716 sees
    //        graphics_now TRUE -> gc_enable(FALSE) -> gc_enabled stays FALSE
    //        -> vcputc_options refuses every character, forever.
    //   op == 2 (text)     -> gc_graphics_boot FALSE -> graphics_now FALSE
    //        -> gc_enable(TRUE) -> gc_enabled TRUE -> the console can paint.
    // DarwinBootVideoFromGop writes the literal 1 into Video[1] (BootVideo.h:31),
    // which is this slot, so without this write v_display is always 1.
    //
    if ((ArgsAddress != 0) && (ArgsAddress >= Kernel.Base)) {
      UINT64  *Bv = (UINT64 *)(UINTN)(ArgsAddress + 0x28);

      Bv[0] = Video[0] | 1ULL;   // v_baseAddr  - bit0: physical-address marker
      Bv[1] = 0;                 // v_display   - 0 -> kPETextMode
      Bv[2] = Video[2];          // v_rowBytes
      Bv[3] = Video[3];          // v_width
      Bv[4] = Video[4];          // v_height
      Bv[5] = Video[5];          // v_depth     - packed depth|rotate|scale
      mKirbyPeVideoArgs = (UINT64)(UINTN)Bv;
    }
  }
'''

REPORT = '''  //
  // KirbyPeVideo: report what the seed wrote, past the form feed.
  //
  // Sits between the last hand-off DEBUG line and the ExitBootServices loop:
  // the console has been cleared and refilled by then (so this is the first
  // thing that actually stays), and gBS is still alive so DiagDraw's
  // LocateProtocol works.  Rows 25/26/27 land in the measured-empty gap
  // between the console band (ends ~y1836) and the boot menu (~y2245);
  // screen y = 640 + Row*56, so 2040/2096/2152.  The Print line rides the
  // console tail itself -- the one channel later painting cannot cover.
  //
  if (mKirbyPeVideoSeeded) {
    CHAR16  KirbyReportText[96];

    Print (L"seed: PE_state.video <- pa %lx va %lx %lux%lu row %lu depth %lu\\n",
           mKirbyPeVideoPv[0] & ~1ULL, (UINT64)(UINTN)mKirbyPeVideoPv,
           mKirbyPeVideoPv[2], mKirbyPeVideoPv[3], mKirbyPeVideoPv[1], mKirbyPeVideoPv[4]);
    UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText), L"seed: PE_state %lx video %lx",
                   mKirbyPeVideoState, mKirbyPeVideoState + 8);
    DiagDraw (KirbyReportText, 25);
    UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText), L"seed: b=%lx w=%lx h=%lx r=%lx d=%lx",
                   mKirbyPeVideoPv[0], mKirbyPeVideoPv[2], mKirbyPeVideoPv[3],
                   mKirbyPeVideoPv[1], mKirbyPeVideoPv[4]);
    DiagDraw (KirbyReportText, 26);
    UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText), L"written: %lx %lx %lx %lx %lx",
                   mKirbyPeVideoPv[0], mKirbyPeVideoPv[1], mKirbyPeVideoPv[2],
                   mKirbyPeVideoPv[3], mKirbyPeVideoPv[4]);
    DiagDraw (KirbyReportText, 27);
    //
    // boot_args->Video is the copy PE_init_platform actually propagates, so
    // report Bv[1] (v_display) explicitly: 0 there is what opens gate two.
    // Row 28 sits at y 2208..2264, still under the boot menu at ~2245.
    //
    if (mKirbyPeVideoArgs != 0) {
      UINT64  *Bv = (UINT64 *)(UINTN)mKirbyPeVideoArgs;

      Print (L"seed: boot_args.Video <- pa %lx base %lx display %lx row %lx\\n",
             mKirbyPeVideoArgs, Bv[0], Bv[1], Bv[2]);
      UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText),
                     L"bargs %lx disp %lx base %lx",
                     mKirbyPeVideoArgs, Bv[1], Bv[0]);
      DiagDraw (KirbyReportText, 28);
    } else {
      UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText),
                     L"bargs NOT WRITTEN");
      DiagDraw (KirbyReportText, 28);
    }
  } else {
    CHAR16  KirbyReportText[96];

    UnicodeSPrint (KirbyReportText, sizeof (KirbyReportText), L"seed: NOT SEEDED state %lx", mKirbyPeVideoState);
    DiagDraw (KirbyReportText, 25);
    Print (L"seed: PE_state.video NOT seeded (state %lx)\\n", mKirbyPeVideoState);
  }
'''


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8", errors="replace")

    anchor = "STATIC\nEFI_STATUS\nParseKernel ("
    if anchor not in text:
        raise SystemExit("ParseKernel declaration not found")
    if "mKirbyPeVideoSeeded" not in text:
        text = text.replace(anchor, FINDER.strip("\n") + "\n\n" + anchor, 1)

    seed_anchor = "  CopyMem ((VOID *)(UINTN)TreeAddress, Tree, TreeSize);"
    if seed_anchor not in text:
        raise SystemExit("TreeAddress CopyMem anchor not found")
    if "KirbyPeVideo: seed PE_state.video" not in text:
        text = text.replace(seed_anchor, seed_anchor + "\n" + SEED, 1)

    report_anchor = "  for (Attempt = 0; Attempt < 3; Attempt++) {\n    MapSize = Capacity;"
    if report_anchor not in text:
        raise SystemExit("ExitBootServices loop anchor not found")
    if "KirbyPeVideo: report what the seed wrote" not in text:
        text = text.replace(report_anchor, REPORT.strip("\n") + "\n\n" + report_anchor, 1)

    path.write_text(text, encoding="utf-8")
    print("DarwinBoot: PE_state.video seed inserted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
