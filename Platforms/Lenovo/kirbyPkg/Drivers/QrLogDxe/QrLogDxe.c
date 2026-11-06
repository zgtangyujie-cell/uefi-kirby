/** @file
  Renders the firmware debug log as a rotating sequence of QR codes.

  The log itself is captured by FrameBufferSerialPortLib, which tees every
  byte it draws to the Log_Buffer region MemoryMapLib already reserves at
  0xA7605000.  This driver re-reads the tail of that buffer on every timer
  tick -- the boot keeps printing long after the first tick -- slices it into
  chunks small enough to scan from a photograph, and paints one QR directly
  into the framebuffer.

  Drawing goes straight to GOP's FrameBufferBase instead of Gop->Blt: the
  platform's SimpleFbDxe is the same driver FrameBufferSerialPortLib already
  writes through, so raw writes are the known-good path, and Blt support
  (EfiBltBufferToVideo in particular) is not guaranteed there.

  Deliberately fail-safe: no GOP, no log, or an encoder refusal all return
  success without drawing.  It must never become the next thing that stalls
  the boot.

  Copyright (c) 2026, kirby bring-up. SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/CacheMaintenanceLib.h>
#include <Library/DebugLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/QrEncoderLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/GraphicsOutput.h>

//
// Must match the tee inside FrameBufferSerialPortLib and the "Log_Buffer"
// entry of kirbyPkg MemoryMapLib.
//
#define KIRBY_LOG_BASE   0xA7605000ULL
#define KIRBY_LOG_MAX    0x00008000U
#define KIRBY_LOG_MAGIC  0x474F4C4BU /* 'KLOG' */
#define KIRBY_LOG_HDR    8U

//
// 600 bytes per frame lands around version 23 at EC level L (109 modules);
// at 760 GOP pixels that is ~7 px per module, and the panel doubles it, so a
// photograph still resolves every module.
//
//
// 760 bytes per frame, matching UniXNU's AdvancedLogDxe (OneSend frames are
// 28 + 720 + 4 = 752).  A 2900 byte frame forced QR version 40 -- 177 modules
// -- and the modules came out too small to decode from a photograph.  At 760
// bytes the code is around version 25 and every module is comfortably wide.
//
#define QR_CHUNK_BYTES   760U

//
// Fixed version with an integer module pitch, and as few modules as the
// payload allows: a version 18 code is 85 modules and holds 762 bytes at EC
// level L, so the usual 670 byte buffer fits while every module gets 11
// pixels.  Auto-versioning produced 9.4 pixels per module and the photograph
// did not decode.
//
#define QR_VERSION       18U
#define QR_MODULES       85U
#define QR_SCALE         8U
#define QR_QUIET_MARGIN  48U
/* One frame only: a code that does not change is a code that can be
   photographed at leisure.  The tail is what matters after a hang. */
#define QR_TAIL_BYTES    (QR_CHUNK_BYTES)
#define QR_REGION_PX     (QR_MODULES * QR_SCALE)

//
// The console proves this address is the panel: FrameBufferSerialPortLib
// finds "Display Reserved" in MemoryMapLib and writes there, and its text is
// what we see.  Gop->Mode->FrameBufferBase reports 0x1B000000 instead, which
// is a different buffer entirely.
//
#define KIRBY_PANEL_BASE 0xD5100000ULL
#define KIRBY_PANEL_W    1600U
#define KIRBY_PANEL_H    2560U

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mGop;
STATIC UINTN                          mWidth;
STATIC UINTN                          mHeight;
STATIC UINTN                          mFrame;
STATIC BOOLEAN                        mTickReported;

STATIC
VOID
PaintPanel (
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Bitmap,
  IN UINTN                          Size
  )
{
  UINT32  *Panel = (UINT32 *)(UINTN)KIRBY_PANEL_BASE;
  UINTN   OriginX = (KIRBY_PANEL_W - Size) / 2;
  //
  // Centre it, and clear the whole panel first.  Centred is the framing that
  // actually decoded from a phone photograph; anchoring it at the bottom
  // pushed it into the corner where the camera is furthest away and least
  // sharp.  Clearing the rest removes the console text that would otherwise
  // bleed through and confuse the decoder.
  //
  UINTN   OriginY = (KIRBY_PANEL_H - Size) / 2;
  UINTN   Row;
  UINTN   Col;

  for (Row = 0; Row < KIRBY_PANEL_H; Row++) {
    UINT32 *Line = (UINT32 *)(UINTN)KIRBY_PANEL_BASE + Row * KIRBY_PANEL_W;
    for (Col = 0; Col < KIRBY_PANEL_W; Col++) {
      Line[Col] = 0;
    }
  }

  /* White quiet zone next -- decoders need at least four modules of it. */
  for (Row = 0; Row < Size + QR_QUIET_MARGIN * 2; Row++) {
    if ((OriginY < QR_QUIET_MARGIN) || ((OriginY + Row - QR_QUIET_MARGIN) >= KIRBY_PANEL_H)) {
      continue;
    }

    {
      UINT32 *Line = Panel + (OriginY + Row - QR_QUIET_MARGIN) * KIRBY_PANEL_W
                     + ((OriginX > QR_QUIET_MARGIN) ? OriginX - QR_QUIET_MARGIN : 0);
      UINTN  Width = Size + QR_QUIET_MARGIN * 2;

      if ((OriginX + Width) > KIRBY_PANEL_W) {
        Width = KIRBY_PANEL_W - OriginX + QR_QUIET_MARGIN;
      }

      for (Col = 0; Col < Width; Col++) {
        Line[Col] = 0xFFFFFFFF;
      }
    }
  }

  for (Row = 0; Row < Size; Row++) {
    CopyMem (
      Panel + (OriginY + Row) * KIRBY_PANEL_W + OriginX,
      Bitmap + Row * Size,
      Size * sizeof (*Bitmap)
      );
  }

  WriteBackInvalidateDataCacheRange (
    (VOID *)(UINTN)KIRBY_PANEL_BASE,
    (UINTN)KIRBY_PANEL_W * KIRBY_PANEL_H * 4
    );
}

STATIC
VOID
DrawFrame (
  VOID
  )
{
  EFI_STATUS                     Status;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Bitmap;
  volatile UINT32                *Header;
  UINT32                         Used;
  UINT8                          *Tail;
  UINTN                          TailLen;
  UINTN                          Frames;
  UINTN                          Offset;
  UINTN                          Length;

  if (mGop == NULL) {
    return;
  }

  /* The tee keeps appending; re-read the length every tick. */
  WriteBackInvalidateDataCacheRange ((VOID *)(UINTN)KIRBY_LOG_BASE, KIRBY_LOG_MAX);

  Header = (volatile UINT32 *)(UINTN)KIRBY_LOG_BASE;
  if (!mTickReported) {
    mTickReported = TRUE;
    DEBUG ((
      DEBUG_ERROR,
      "QrLog tick: magic=%08x used=%u\n",
      Header[0],
      Header[1]
      ));
  }

  if (Header[0] != KIRBY_LOG_MAGIC) {
    return;
  }

  Used = Header[1];
  if (Used > (KIRBY_LOG_MAX - KIRBY_LOG_HDR)) {
    Used = KIRBY_LOG_MAX - KIRBY_LOG_HDR;
  }

  if (Used == 0) {
    return;
  }

  Tail    = (UINT8 *)(UINTN)(KIRBY_LOG_BASE + KIRBY_LOG_HDR);
  TailLen = Used;
  if (TailLen > QR_TAIL_BYTES) {
    Tail   += TailLen - QR_TAIL_BYTES;
    TailLen = QR_TAIL_BYTES;
  }

  Frames = (TailLen + QR_CHUNK_BYTES - 1) / QR_CHUNK_BYTES;
  if (Frames == 0) {
    Frames = 1;
  }

  if (mFrame >= Frames) {
    mFrame = 0;
  }

  Offset = mFrame * QR_CHUNK_BYTES;
  Length = TailLen - Offset;
  if (Length > QR_CHUNK_BYTES) {
    Length = QR_CHUNK_BYTES;
  }

  Bitmap = NULL;
  Status = QrEncodeData (
             (UINT8)QR_VERSION,
             QrECLevel_L,
             QrByteMode,
             0,
             Tail + Offset,
             (UINT16)Length,
             QR_REGION_PX,
             &Bitmap
             );
  if (EFI_ERROR (Status) || (Bitmap == NULL)) {
    DEBUG ((DEBUG_ERROR, "QrLog: encode frame %u failed: %r\n", (UINT32)mFrame, Status));
    return;
  }

  /* Do not DEBUG() from inside DrawFrame(): FrameBufferSerialPortLib tees every
     debug byte back into KLOG, so a diagnostic printed here makes the NEXT
     frame longer and the QR quietly changes under the camera.  Keep KLOG frozen
     so every photograph decodes the same single static frame. */
  PaintPanel (Bitmap, QR_REGION_PX);

  /* One white square per frame at the bottom edge, current one highlighted. */
  {
    UINTN                          Index;
    UINTN                          CellW = 20;
    UINTN                          Gap   = 10;
    UINTN                          Total = Frames;
    UINTN                          Start;

    if (Total > 24) {
      Total = 24;
    }

    Start = (KIRBY_PANEL_W - (Total * (CellW + Gap))) / 2;
    for (Index = 0; Index < Total; Index++) {
      UINT32 *Line = (UINT32 *)(UINTN)KIRBY_PANEL_BASE
                     + (KIRBY_PANEL_H - 80) * KIRBY_PANEL_W
                     + Start + Index * (CellW + Gap);
      UINT32  Value = (Index == (mFrame % Total)) ? 0xFFFFFFFF : 0x00000000;
      UINTN   Col;

      for (Col = 0; Col < CellW; Col++) {
        Line[Col] = Value;
      }
    }
  }

  FreePool (Bitmap);

  mFrame = (mFrame + 1) % Frames;
}

//
// The timer interrupt never fires on this board: SetTimer returns Success and
// the callback is never entered (BDS's own menu timeout is dead for the same
// reason).  Nothing rotates any more -- QrLogDxeEntry paints a single frame
// with DrawFrame() and returns to BDS, so the old ShowRound()/6 s Stall pair
// is gone.  Keep this note: it is why no EVT_TIMER is used anywhere here.
//


EFI_STATUS
EFIAPI
QrLogDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;

  mGop      = NULL;
  mFrame    = 0;
  mTickReported = FALSE;

  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mGop);
  if (EFI_ERROR (Status) || (mGop == NULL)) {
    return EFI_SUCCESS;
  }

  //
  // Diagnostic only: report what the GOP actually says, so a photograph of the
  // console can be checked against the geometry this driver paints with.
  //
  mWidth  = mGop->Mode->Info->HorizontalResolution;
  mHeight = mGop->Mode->Info->VerticalResolution;

  DEBUG ((
    DEBUG_ERROR,
    "QrLog: gop %ux%u stride %u fb %lx size %u\n",
    (UINT32)mWidth,
    (UINT32)mHeight,
    (UINT32)mGop->Mode->Info->PixelsPerScanLine,
    (UINT64)mGop->Mode->FrameBufferBase,
    (UINT32)mGop->Mode->FrameBufferSize
    ));

  if ((KIRBY_PANEL_W < QR_REGION_PX) || (KIRBY_PANEL_H < QR_REGION_PX)) {
    DEBUG ((DEBUG_ERROR, "QrLog: panel too small for %u px QR\n", (UINT32)QR_REGION_PX));
    return EFI_SUCCESS;
  }

  //
  // Hand the firmware back to BDS.  The static QR above is the last frame this
  // driver paints; BDS will repaint the panel with its own GOP fills, and from
  // there on FrameBufferSerialPortLib writes every DEBUG byte straight to the
  // panel as text -- a photograph still reads the boot log, just not as a QR.
  //
  // Freezing the boot here was only ever a bring-up trick to make the QR the
  // single visible surface.  It also made BDS unreachable, and with it the
  // UniXNU required-integration drivers and the boot menu.  Revert this hunk
  // to restore the static-QR-only image if a QR capture is needed again.
  //
  // Call DrawFrame() directly rather than ShowRound(): the latter stalls for
  // QR_FRAME_DELAY_US (6 s) to hold each rotating frame on screen, which is
  // pointless for a single frame and would delay BDS for no reason.
  //
  DrawFrame ();
  WriteBackInvalidateDataCacheRange (
    (VOID *)(UINTN)KIRBY_PANEL_BASE,
    (UINTN)KIRBY_PANEL_W * KIRBY_PANEL_H * 4
    );

  return EFI_SUCCESS;
}
