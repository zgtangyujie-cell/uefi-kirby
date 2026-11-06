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
#define QR_CHUNK_BYTES   600U
#define QR_TAIL_BYTES    (QR_CHUNK_BYTES * 8U)
#define QR_REGION_PX     760U

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mGop;
STATIC UINTN                          mWidth;
STATIC UINTN                          mHeight;
STATIC UINTN                          mFrame;
STATIC BOOLEAN                        mReported;

STATIC
VOID
DrawFrame (
  VOID
  )
{
  EFI_STATUS                     Status;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Bitmap;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Black = { 0, 0, 0, 0 };
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  White = { 0xFF, 0xFF, 0xFF, 0 };
  volatile UINT32                *Header;
  UINT32                         Used;
  UINT8                          *Tail;
  UINTN                          TailLen;
  UINTN                          Frames;
  UINTN                          Offset;
  UINTN                          Length;
  UINTN                          OriginX;
  UINTN                          OriginY;

  if (mGop == NULL) {
    return;
  }

  /* The tee keeps appending; re-read the length every tick. */
  WriteBackInvalidateDataCacheRange ((VOID *)(UINTN)KIRBY_LOG_BASE, KIRBY_LOG_MAX);

  Header = (volatile UINT32 *)(UINTN)KIRBY_LOG_BASE;
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
             0, /* version: auto */
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

  OriginX = (mWidth  > QR_REGION_PX) ? (mWidth  - QR_REGION_PX) / 2 : 0;
  OriginY = (mHeight > QR_REGION_PX) ? (mHeight - QR_REGION_PX) / 2 : 0;

  if (!mReported) {
    mReported = TRUE;
    DEBUG ((
      DEBUG_ERROR,
      "QrLog: log %u bytes, %u frames, first chunk %u bytes\n",
      (UINT32)Used,
      (UINT32)Frames,
      (UINT32)Length
      ));
  }

  Status = mGop->Blt (
                    mGop,
                    Bitmap,
                    EfiBltBufferToVideo,
                    0,
                    0,
                    OriginX,
                    OriginY,
                    QR_REGION_PX,
                    QR_REGION_PX,
                    0
                    );

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

    Start = (mWidth - (Total * (CellW + Gap))) / 2;
    for (Index = 0; Index < Total; Index++) {
      mGop->Blt (
                 mGop,
                 (Index == (mFrame % Total)) ? &White : &Black,
                 EfiBltVideoFill,
                 0,
                 0,
                 Start + Index * (CellW + Gap),
                 mHeight - 40,
                 CellW,
                 20,
                 0
                 );
    }
  }

  FreePool (Bitmap);

  mFrame = (mFrame + 1) % Frames;
}

STATIC
VOID
EFIAPI
OnTimer (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  DrawFrame ();
}

EFI_STATUS
EFIAPI
QrLogDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  EFI_EVENT   Timer;

  mGop      = NULL;
  mFrame    = 0;
  mReported = FALSE;

  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mGop);
  if (EFI_ERROR (Status) || (mGop == NULL)) {
    return EFI_SUCCESS;
  }

  //
  // Blt speaks GOP coordinates, and scripts/build.sh deliberately makes those
  // half the panel (800x1280) so the console gets 2x characters.  The BDS menu
  // draws through the same coordinates and lands correctly, so the QR does too.
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

  if ((mWidth < QR_REGION_PX) || (mHeight < QR_REGION_PX)) {
    DEBUG ((DEBUG_ERROR, "QrLog: gop too small for %u px QR\n", (UINT32)QR_REGION_PX));
    return EFI_SUCCESS;
  }

  Status = gBS->CreateEvent (EVT_TIMER, TPL_CALLBACK, OnTimer, NULL, &Timer);
  if (EFI_ERROR (Status)) {
    return EFI_SUCCESS;
  }

  gBS->SetTimer (Timer, TimerPeriodic, 2 * 1000 * 1000);

  return EFI_SUCCESS;
}
