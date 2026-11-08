/** @file
  Read the GCC registers that QcomXnuUsbDebug inspects, one stage before the
  kernel does, and append them to the KLOG buffer so QrLogDxe draws them.

  Why this exists: qcom_usb_debug_init() refuses the hardware silently.  It runs
  from PE_init_kprintf, where the only output sink is the USB device that just
  refused, PE_kputc is not yet pointed at the video console, and
  boot_progress_persist does not exist in this UniXNU revision
  (build-boot-progress.py is absent, which is why caihong also pins
  CONFIG_XNU_BOOT_PROGRESS=n).  Reading the same registers here -- while UEFI
  still owns a working framebuffer and QrLogDxe's QR channel -- is the only way
  to see the values that decide the refusal.

  Only GCC is read on purpose.  GCC sits in an always-on power domain, so a
  volatile read of it cannot stall.  DWC3 (0x0A600000) is deliberately NOT read:
  if its branch clocks are gated, that read can hang the interconnect and take
  the firmware down before anything is drawn.  These seven values already answer
  the question that matters:
    BCR        bit0 BLK_ARES      must be 0
    GDSCR      bit1 HW_CONTROL    must be 0
    CFG_GDSCR  bit16 POWER_UP     must be 1
    CBCR[0..4] bit31 CLK_OFF      must be 0 on every branch
    CBCR[0..4] bit0  CLK_ENABLE   what QcomUsbResumeClocks() sets

**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/UefiBootServicesTableLib.h>

//
// Must match QrLogDxe.c and the "Log_Buffer" entry of MemoryMapLib.
//
#define KIRBY_LOG_BASE   0xA7605000ULL
#define KIRBY_LOG_MAX    0x00008000U
#define KIRBY_LOG_MAGIC  0x474F4C4BU /* 'KLOG' */
#define KIRBY_LOG_HDR    8U

//
// Must match soc/Sm8650.h in the QcomXnuUsbDebug module.
//
#define PROBE_GCC_BASE       0x00100000U
#define PROBE_GCC_BCR        0x39000U
#define PROBE_GCC_GDSCR      0x39004U
#define PROBE_GCC_CFG_GDSCR  0x39008U
#define PROBE_GCC_CBCR0      0x39018U   /* master */
#define PROBE_GCC_CBCR1      0x39088U   /* cfg_noc_axi */
#define PROBE_GCC_CBCR2      0x3908CU   /* aggre_axi */
#define PROBE_GCC_CBCR3      0x39028U   /* utmi */
#define PROBE_GCC_CBCR4      0x39024U   /* sleep */

//
// Volatile pointer read, the same way SmemProbeDxe reads SMEM: no IoLib, so
// this driver needs only BaseLib and UefiDriverEntryPoint from MdePkg.
//
static UINT32
ReadGcc (
  IN UINT32  Offset
  )
{
  return *(volatile UINT32 *)(UINTN)(PROBE_GCC_BASE + Offset);
}

static CHAR8 *
AppendText (
  CHAR8        *Cursor,
  CHAR8        *End,
  CONST CHAR8  *Text
  )
{
  while ((*Text != '\0') && (Cursor < End)) {
    *Cursor++ = *Text++;
  }

  return Cursor;
}

static CHAR8 *
AppendHex (
  CHAR8  *Cursor,
  CHAR8  *End,
  UINT32  Value,
  UINTN   Digits
  )
{
  STATIC CONST CHAR8  Hex[] = "0123456789abcdef";
  INTN                Index;

  for (Index = (INTN)Digits - 1; Index >= 0; --Index) {
    if (Cursor < End) {
      *Cursor++ = Hex[(Value >> (Index * 4)) & 0xFU];
    }
  }

  return Cursor;
}

EFI_STATUS
EFIAPI
UsbStateProbeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  volatile UINT32  *Header;
  CHAR8            *Data;
  CHAR8            *Cursor;
  CHAR8            *End;
  UINT32           Used;

  Header = (volatile UINT32 *)(UINTN)KIRBY_LOG_BASE;
  if (Header[0] != KIRBY_LOG_MAGIC) {
    //
    // Nobody has teed anything yet, so QrLogDxe would not read this buffer
    // either.  Do not invent a log: a half-initialised KLOG changes what the
    // QR shows for every later frame.
    //
    return EFI_SUCCESS;
  }

  Used = Header[1];
  if (Used > (KIRBY_LOG_MAX - KIRBY_LOG_HDR - 320U)) {
    return EFI_SUCCESS;
  }

  Data   = (CHAR8 *)(UINTN)(KIRBY_LOG_BASE + KIRBY_LOG_HDR);
  Cursor = Data + Used;
  End    = Cursor + 300;

  Cursor = AppendText (Cursor, End, "\nUSBSTATE bcr=");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_BCR), 8);
  Cursor = AppendText (Cursor, End, " gdscr=");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_GDSCR), 8);
  Cursor = AppendText (Cursor, End, " cfg=");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CFG_GDSCR), 8);
  Cursor = AppendText (Cursor, End, " clk=");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CBCR0), 8);
  Cursor = AppendText (Cursor, End, ",");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CBCR1), 8);
  Cursor = AppendText (Cursor, End, ",");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CBCR2), 8);
  Cursor = AppendText (Cursor, End, ",");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CBCR3), 8);
  Cursor = AppendText (Cursor, End, ",");
  Cursor = AppendHex (Cursor, End, ReadGcc (PROBE_GCC_CBCR4), 8);
  Cursor = AppendText (Cursor, End, "\n");

  Header[1] = Used + (UINT32)(Cursor - (Data + Used));
  return EFI_SUCCESS;
}
