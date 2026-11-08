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

//
// Encode the six bits that decide QcomUsbInspectInherited() as a boot delay.
//
// The kernel module cannot report its refusal: at that moment the only sink is
// the USB device that just refused.  Writing to the panel would need a
// photograph, and a photograph is not an automated read.  A delay is: the host
// script measures "fastboot boot returned" -> "device is back", subtracts the
// fixed 10 s, divides by 3 s, and gets `bad` back.
//
//   bit0      CFG_GDSCR.POWER_UP_COMPLETE (bit 16) is CLEAR  <- power domain off
//   bit1..5   CBCR[0..4].CLK_OFF (bit 31) is SET             <- branch gated
//
// bad == 0 means every precondition QcomUsbInspectInherited() checks was already
// satisfied, so the refusal (if any) is past those checks: reset/role/DWC3 ID.
//
#define PROBE_STEP_SECONDS  3U
#define PROBE_BASE_SECONDS  10U
#define PROBE_MAX_BAD       63U

static UINT32
BadMask (
  VOID
  )
{
  STATIC CONST UINT32  Cbcr[5] = {
    PROBE_GCC_CBCR0, PROBE_GCC_CBCR1, PROBE_GCC_CBCR2, PROBE_GCC_CBCR3, PROBE_GCC_CBCR4
  };
  UINT32  Bad;
  UINTN   Index;

  Bad = 0;
  if ((ReadGcc (PROBE_GCC_CFG_GDSCR) & (1U << 16)) == 0) {
    Bad |= 1U;
  }
  for (Index = 0; Index < 5; ++Index) {
    if ((ReadGcc (Cbcr[Index]) & 0x80000000U) != 0) {
      Bad |= (1U << (Index + 1));
    }
  }
  if (Bad > PROBE_MAX_BAD) {
    Bad = PROBE_MAX_BAD;
  }
  return Bad;
}

EFI_STATUS
EFIAPI
UsbStateProbeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  UINT32  Bad;

  Bad = BadMask ();
  gBS->Stall ((PROBE_BASE_SECONDS + Bad * PROBE_STEP_SECONDS) * 1000000U);
  return EFI_SUCCESS;
}
