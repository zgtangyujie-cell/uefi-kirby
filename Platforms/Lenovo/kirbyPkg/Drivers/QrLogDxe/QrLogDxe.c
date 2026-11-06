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
// QR payload per frame.  ~900 bytes lands around version 26 at EC level L,
// which is 121 modules: about 11 pixels per module on a 1360 pixel square,
// comfortably readable from a tablet photograph.
//
#define QR_CHUNK_BYTES   900U
#define QR_TAIL_BYTES    (QR_CHUNK_BYTES * 8U)
#define QR_REGION_PX     1360U

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mGop;
STATIC UINT8                         *mFb;
STATIC UINTN                          mStride;
STATIC UINTN                          mWidth;
STATIC UINTN                          mHeight;
STATIC UINTN                          mFrame;

/*
  The console shares this framebuffer, so the QR is repainted every tick and
  simply wins once the boot stops printing.
*/
STATIC
VOID
FillRect (
  IN UINTN                          X,
  IN UINTN                          Y,
  IN UINTN                          Width,
  IN UINTN                          Height,
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Color
  )
{
  UINT32  Value;
  UINT32  *Line;
  UINTN   Row;
  UINTN   Col;

  Value = *(UINT32 *)Color;

  for (Row = 0; Row < Height; Row++) {
    if ((Y + Row) >= mHeight) {
      break;
    }

    Line = (UINT32 *)(mFb + (Y + Row) * mStride * 4) + X;
    for (Col = 0; Col < Width; Col++) {
      if ((X + Col) >= mWidth) {
        break;
      }

      Line[Col] = Value;
    }
  }
}

STATIC
VOID
PaintQr (
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Bitmap,
  IN UINTN                          Size,
  IN UINTN                          OriginX,
  IN UINTN                          OriginY
  )
{
  UINT32  *Line;
  UINTN   Row;

  for (Row = 0; Row < Size; Row++) {
    if ((OriginY + Row) >= mHeight) {
      break;
    }

    Line = (UINT32 *)(mFb + (OriginY + Row) * mStride * 4) + OriginX;
    CopyMem (Line, Bitmap + Row * Size, Size * 4);
  }
}

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
    return;
  }

  OriginX = (mWidth  > QR_REGION_PX) ? (mWidth  - QR_REGION_PX) / 2 : 0;
  OriginY = (mHeight > QR_REGION_PX) ? (mHeight - QR_REGION_PX) / 2 : 0;

  FillRect (OriginX, OriginY, QR_REGION_PX, QR_REGION_PX, &White);
  PaintQr (Bitmap, QR_REGION_PX, OriginX, OriginY);

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
      FillRect (
               Start + Index * (CellW + Gap),
               mHeight - 40,
               CellW,
               20,
               (Index == (mFrame % Total)) ? &White : &Black
               );
    }
  }

  WriteBackInvalidateDataCacheRange (
    (VOID *)(mFb + OriginY * mStride * 4),
    QR_REGION_PX * mStride * 4
    );

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

  mGop   = NULL;
  mFrame = 0;

  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mGop);
  if (EFI_ERROR (Status) || (mGop == NULL)) {
    return EFI_SUCCESS;
  }

  mFb     = (UINT8 *)(UINTN)mGop->Mode->FrameBufferBase;
  mStride = mGop->Mode->Info->PixelsPerScanLine;
  //
  // scripts/build.sh patches SimpleFb so the GOP *reports* half the panel
  // (800x1280) while PixelsPerScanLine stays at the real 1600, which is how
  // the console gets 2x characters.  The QR is painted into the real panel,
  // so take the width from the stride and the height from the buffer size --
  // using Info->HorizontalResolution would clamp us to 800 and then bail out.
  //
  mWidth  = mStride;
  mHeight = (mStride == 0) ? 0 : (mGop->Mode->FrameBufferSize / (mStride * 4U));

  if ((mFb == NULL) || (mStride < mWidth) || (mWidth < QR_REGION_PX) || (mHeight < QR_REGION_PX)) {
    return EFI_SUCCESS;
  }

  Status = gBS->CreateEvent (EVT_TIMER, TPL_CALLBACK, OnTimer, NULL, &Timer);
  if (EFI_ERROR (Status)) {
    return EFI_SUCCESS;
  }

  gBS->SetTimer (Timer, TimerPeriodic, 2 * 1000 * 1000);

  return EFI_SUCCESS;
}
