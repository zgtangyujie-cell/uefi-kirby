/** @file
  Renders the firmware debug log as a rotating sequence of QR codes.

  The log itself is captured by FrameBufferSerialPortLib, which tees every
  byte it draws to the Log_Buffer region MemoryMapLib already reserves at
  0xA7605000.  This driver picks the tail of that buffer up, slices it into
  chunks small enough to scan from a photograph, and blits one QR per timer
  tick.

  Deliberately fail-safe: if there is no GOP, no log, or the encoder refuses
  a chunk, it draws nothing and returns success.  It must never become the
  next thing that stalls the boot.

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
// which is 121 modules: about 11 pixels per module on a 1400 pixel square,
// comfortably readable from a tablet photograph.
//
#define QR_CHUNK_BYTES   900U
#define QR_REGION_PX     1360

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mGop;
STATIC UINT8                         *mLog;
STATIC UINT32                        mLogLen;
STATIC UINTN                          mFrameCount;
STATIC UINTN                          mFrame;

STATIC
VOID
DrawProgress (
  IN UINTN  Current,
  IN UINTN  Total
  )
{
  UINTN                          Index;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  On  = { 0xFF, 0xFF, 0xFF, 0 };
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Off = { 0x20, 0x20, 0x20, 0 };
  UINTN                          Width;
  UINTN                          Start;

  if ((Total == 0) || (Total > 32)) {
    return;
  }

  Width = 24;
  Start = (mGop->Mode->Info->HorizontalResolution - (Total * (Width + 8))) / 2;

  for (Index = 0; Index < Total; Index++) {
    mGop->Blt (
             mGop,
             (Index == Current) ? &On : &Off,
             EfiBltVideoFill,
             0,
             0,
             Start + Index * (Width + 8),
             mGop->Mode->Info->VerticalResolution - 60,
             Width,
             24,
             0
             );
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
  UINT8                          *Chunk;
  UINTN                          Offset;
  UINTN                          Length;
  UINTN                          X;
  UINTN                          Y;

  if ((mGop == NULL) || (mLogLen == 0) || (mFrameCount == 0)) {
    return;
  }

  Offset = mFrame * QR_CHUNK_BYTES;
  if (Offset >= mLogLen) {
    mFrame = 0;
    Offset = 0;
  }

  Length = mLogLen - Offset;
  if (Length > QR_CHUNK_BYTES) {
    Length = QR_CHUNK_BYTES;
  }

  Chunk  = mLog + Offset;
  Bitmap = NULL;

  Status = QrEncodeData (
             0,                     /* version: auto */
             QrECLevel_L,
             QrByteMode,
             0,
             Chunk,
             (UINT16)Length,
             QR_REGION_PX,
             &Bitmap
             );
  if (EFI_ERROR (Status) || (Bitmap == NULL)) {
    DEBUG ((DEBUG_ERROR, "QrLog: encode frame %u failed: %r\n", mFrame, Status));
    return;
  }

  X = (mGop->Mode->Info->HorizontalResolution - QR_REGION_PX) / 2;
  Y = (mGop->Mode->Info->VerticalResolution   - QR_REGION_PX) / 2;
  if (Y > 40) {
    Y -= 40;
  }

  mGop->Blt (
           mGop,
           Bitmap,
           EfiBltBufferToVideo,
           0,
           0,
           X,
           Y,
           QR_REGION_PX,
           QR_REGION_PX,
           0
           );

  DrawProgress (mFrame, mFrameCount);

  FreePool (Bitmap);

  mFrame = (mFrame + 1) % mFrameCount;
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
  UINT32      *Header;
  UINT32      Used;

  mGop = NULL;
  Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mGop);
  if (EFI_ERROR (Status) || (mGop == NULL)) {
    return EFI_SUCCESS;
  }

  Header = (UINT32 *)(UINTN)KIRBY_LOG_BASE;

  /* The tee ran from SEC/PEI with the MMU off; make sure DXE does not read a
     stale cache line before trusting the header. */
  WriteBackInvalidateDataCacheRange ((VOID *)(UINTN)KIRBY_LOG_BASE, KIRBY_LOG_MAX);

  if (Header[0] != KIRBY_LOG_MAGIC) {
    DEBUG ((DEBUG_ERROR, "QrLog: no KLOG header (%08x), nothing to show\n", Header[0]));
    return EFI_SUCCESS;
  }

  Used = Header[1];
  if (Used > (KIRBY_LOG_MAX - KIRBY_LOG_HDR)) {
    Used = KIRBY_LOG_MAX - KIRBY_LOG_HDR;
  }

  /* Keep the tail: when the firmware dies, the last lines are the story. */
  if (Used > (QR_CHUNK_BYTES * 8)) {
    mLog    = (UINT8 *)(UINTN)KIRBY_LOG_BASE + KIRBY_LOG_HDR + (Used - QR_CHUNK_BYTES * 8);
    mLogLen = QR_CHUNK_BYTES * 8;
  } else {
    mLog    = (UINT8 *)(UINTN)KIRBY_LOG_BASE + KIRBY_LOG_HDR;
    mLogLen = Used;
  }

  if (mLogLen == 0) {
    return EFI_SUCCESS;
  }

  mFrameCount = (mLogLen + QR_CHUNK_BYTES - 1) / QR_CHUNK_BYTES;
  mFrame      = 0;

  DEBUG ((DEBUG_ERROR, "QrLog: %u bytes, %u frames\n", mLogLen, mFrameCount));

  Status = gBS->CreateEvent (EVT_TIMER, TPL_CALLBACK, OnTimer, NULL, &Timer);
  if (EFI_ERROR (Status)) {
    return EFI_SUCCESS;
  }

  gBS->SetTimer (Timer, TimerPeriodic, 2 * 1000 * 1000);

  return EFI_SUCCESS;
}
