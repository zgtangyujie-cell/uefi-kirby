/** @file
  SmemProbeDxe -- read the raw bytes at the SMEM region and print them.

  Why this exists: SmemDxe reports "SMEM is not initialized by Boot." and the
  only way to tell "the ABL never built it" apart from "we read it at the wrong
  time or from the wrong place" is to look at the memory itself.

  Android's /dev/mem is compiled out on this device (mknod succeeds, dd returns
  ENXIO), and qcom-smem in Linux reads the same region only after the kernel is
  up.  So the probe runs inside UEFI, as early as the APRIORI list allows, and
  dumps the first words of the region to the framebuffer console.

  What to look for: a valid SMEM table starts with the 'SMEM' magic
  0x534D454D.  If it is there, the blob exists and the problem is on our side
  (mapping attribute, ordering, wrong region name).  If the region reads as all
  zeroes or as garbage, the ABL never brought SMEM up on this boot path and no
  amount of driver shuffling will help.

  Deliberately reads through a volatile pointer and does not touch anything:
  this driver must never be able to fault, so it stays inside a region
  MemoryMapLib already describes.
**/

#include <Uefi.h>
#include <Library/DebugLib.h>

//
// MemoryMapLib describes 0x81D00000 as "SMEM", 0x200000 long, and ABL's own
// device tree carries the same pair under memory@81D00000.
//
#define SMEM_PROBE_BASE  0x81D00000ULL
#define SMEM_PROBE_WORDS 8

EFI_STATUS
EFIAPI
SmemProbeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  volatile UINT32  *Base;
  UINTN            Index;

  Base = (volatile UINT32 *)(UINTN)SMEM_PROBE_BASE;

  //
  // One line per four words: the panel is 88 columns wide at font scale 3, so
  // four %08x plus a prefix fits comfortably and cannot wrap.
  //
  DEBUG ((DEBUG_ERROR, "SMEM probe: base=0x%08x\n", (UINT32)SMEM_PROBE_BASE));

  for (Index = 0; Index < SMEM_PROBE_WORDS; Index += 4) {
    DEBUG ((
      DEBUG_ERROR,
      "SMEM +%02x: %08x %08x %08x %08x\n",
      (UINT32)(Index * sizeof (UINT32)),
      Base[Index + 0],
      Base[Index + 1],
      Base[Index + 2],
      Base[Index + 3]
      ));
  }

  //
  // The first word is the table's magic. Echo the verdict so the answer does
  // not depend on the reader recognising 0x534D454D by sight.
  //
  DEBUG ((
    DEBUG_ERROR,
    "SMEM magic=%08x expected=534d454d -> %a\n",
    Base[0],
    (Base[0] == 0x534D454D) ? "VALID" : "NOT INITIALISED"
    ));

  //
  // Keep going regardless: a failed probe must not become the next stall.
  //
  return EFI_SUCCESS;
}
