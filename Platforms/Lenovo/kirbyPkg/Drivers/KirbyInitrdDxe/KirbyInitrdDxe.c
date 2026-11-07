/** @file
  Publish the UniXNU payload (a FAT16 volume) as a read-only block device.

  Ported from UniXNU-caihong's CaihongInitrdDxe -- same SoC family, same
  problem -- after a capture showed why UniXNUPkg's UniXNURamDiskDxe cannot
  work on kirby:

    QrLog: blk0 bs=512 last=21754 rd=Success jmp=02 bps=12343 spc=55

  UniXNURamDiskDxe treats /chosen/linux,initrd-start as the first byte of the
  volume.  On this tablet the bootloader leaves the *previous Android boot's*
  initrd range in the device tree the fastboot path hands over, so reading that
  address returns whatever was there before -- a valid block device full of
  garbage.  Fat then (correctly) refuses the volume, and SimpleFileSystem never
  appears, which looks exactly like a broken FAT image.

  So the range is treated as a *search window*, not as an answer:

    1. scan the /chosen range for a FAT16 boot sector carrying our volume label,
    2. if that fails, scan the backed memory regions the memory map describes,
    3. if that fails too, print one line and let the boot continue.

  Step 2 deliberately skips EfiReservedMemoryType and the MMIO types: an
  earlier version of the caihong driver dereferenced a mapped-but-unbacked
  range and took the tablet down with a data abort.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/FdtLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>
#include <Protocol/FirmwareVolume2.h>

//
// Mu-Silicium SEC stores the incoming x0 (device tree pointer) here.  Local
// copy on purpose: the GUID is declared in SiliciumPkg.dec by a build.sh patch,
// and a driver in kirbyPkg should not depend on that patch having run.
//
STATIC CONST EFI_GUID  mEntryArgHobGuid = {
  0xDAEE82E6, 0x8090, 0x4E72, { 0xBF, 0xB9, 0x78, 0xC1, 0x3C, 0xD4, 0xE3, 0x59 }
};

#define RAM_BLOCK_SIZE   512
#define FAT_LABEL_OFF    43
#define FAT_LABEL_LEN    11
#define FAT_TYPE_OFF     54
#define FAT_SECTORS_OFF  32
#define FAT_SECTORS16_OFF  19

//
// A region has to be at least this big before the memory scan bothers with it;
// the payload is 8 MiB and nothing smaller can hold it.
//
#define SCAN_MIN_REGION  (8ULL * 1024 * 1024)

//
// Must match payload.img, which work/make_payload.py builds with
// `--label TB321FUESP`.  The trailing space is part of the 11-byte field.
//
STATIC CONST CHAR8  mLabel[FAT_LABEL_LEN] = {
  'T', 'B', '3', '2', '1', 'F', 'U', 'E', 'S', 'P', ' '
};

//
// Must match FILE FREEFORM in kirby.fdf.  The embedded payload is a 32 KiB
// FAT12 volume; FAT12 rather than FAT16 because FAT16 needs at least 4085
// clusters, which is 2 MiB even at one sector per cluster, and the firmware
// volume has no room for that.
//
//
// EFI_FIRMWARE_VOLUME2_PROTOCOL, spelled out for the same reason the
// UnicodeCollation GUIDs are: the symbolic name is not declared in any .dec
// this platform includes, and the link fails with
// "undefined symbol: gEfiFirmwareVolume2ProtocolGuid".
//
STATIC EFI_GUID  mFirmwareVolume2Guid = {
  0x220E73B6, 0x6BDB, 0x4413, { 0x84, 0x05, 0xB9, 0x74, 0xB8, 0xBA, 0x6B, 0x08 }
};

STATIC CONST EFI_GUID  mPayloadGuid = {
  0x7B1E4C62, 0x2D5A, 0x4F83, { 0x9E, 0x71, 0x3C, 0x8A, 0x5D, 0x0B, 0x6F, 0x24 }
};

#pragma pack(1)
typedef struct {
  VENDOR_DEVICE_PATH          Vendor;
  EFI_DEVICE_PATH_PROTOCOL    End;
} RAM_BLOCK_DEVICE_PATH;
#pragma pack()

STATIC RAM_BLOCK_DEVICE_PATH  mDevicePath = {
  {
    { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { (UINT8)sizeof (VENDOR_DEVICE_PATH), (UINT8)(sizeof (VENDOR_DEVICE_PATH) >> 8) } },
    { 0x5E3C2A91, 0x7B48, 0x4F16, { 0x8D, 0x2C, 0x6A, 0x91, 0xF4, 0x05, 0xBB, 0x37 } }
  },
  { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (EFI_DEVICE_PATH_PROTOCOL), 0 } }
};

STATIC UINT8                 *mRamBase;
STATIC EFI_BLOCK_IO_MEDIA     mMedia;

STATIC
EFI_STATUS
EFIAPI
RamBlockReset (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN BOOLEAN                ExtendedVerification
  )
{
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockRead (
  IN  EFI_BLOCK_IO_PROTOCOL  *This,
  IN  UINT32                 MediaId,
  IN  EFI_LBA                Lba,
  IN  UINTN                  BufferSize,
  OUT VOID                   *Buffer
  )
{
  if (Buffer == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  if (MediaId != mMedia.MediaId) {
    return EFI_MEDIA_CHANGED;
  }

  if ((BufferSize % RAM_BLOCK_SIZE) != 0) {
    return EFI_BAD_BUFFER_SIZE;
  }

  if ((Lba > mMedia.LastBlock) || ((BufferSize / RAM_BLOCK_SIZE) > (mMedia.LastBlock + 1 - Lba))) {
    return EFI_INVALID_PARAMETER;
  }

  CopyMem (Buffer, mRamBase + Lba * RAM_BLOCK_SIZE, BufferSize);
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockWrite (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  IN VOID                   *Buffer
  )
{
  return EFI_WRITE_PROTECTED;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockFlush (
  IN EFI_BLOCK_IO_PROTOCOL  *This
  )
{
  return EFI_SUCCESS;
}

STATIC EFI_BLOCK_IO_PROTOCOL  mBlockIo = {
  EFI_BLOCK_IO_PROTOCOL_REVISION,
  &mMedia,
  RamBlockReset,
  RamBlockRead,
  RamBlockWrite,
  RamBlockFlush
};

STATIC
UINT64
ReadAddress (
  IN CONST VOID  *Property,
  IN INT32       Length
  )
{
  //
  // Device tree properties are big-endian.
  //
  if (Length == 8) {
    return SwapBytes64 (ReadUnaligned64 ((CONST UINT64 *)Property));
  }

  return SwapBytes32 (ReadUnaligned32 ((CONST UINT32 *)Property));
}

STATIC
EFI_STATUS
InstallVolume (
  IN UINT64  At,
  IN UINT64  Bytes
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;

  mRamBase            = (UINT8 *)(UINTN)At;
  mMedia.MediaId      = 1;
  mMedia.MediaPresent = TRUE;
  mMedia.ReadOnly     = TRUE;
  mMedia.BlockSize    = RAM_BLOCK_SIZE;
  mMedia.IoAlign      = 1;
  mMedia.LastBlock    = Bytes / RAM_BLOCK_SIZE - 1;

  Handle = NULL;
  Status = gBS->InstallMultipleProtocolInterfaces (
                  &Handle,
                  &gEfiDevicePathProtocolGuid,
                  &mDevicePath,
                  &gEfiBlockIoProtocolGuid,
                  &mBlockIo,
                  NULL
                  );
  DEBUG ((DEBUG_ERROR, "KIRBYINITRD: volume at 0x%lx size 0x%lx %r\n", At, Bytes, Status));
  return Status;
}

/**
  Return the size of the FAT16 volume that starts at Sector, or 0 when this is
  not our volume.  Limit is how many bytes are known to be readable from Sector.
**/
STATIC
UINT64
VolumeSizeAt (
  IN UINT8   *Sector,
  IN UINT64  Limit
  )
{
  UINT64  Bytes;

  if (Limit < RAM_BLOCK_SIZE) {
    return 0;
  }

  //
  // Signature, then the label: the signature alone matches every FAT volume in
  // memory, and the point is to find *our* payload.
  //
  if ((Sector[510] != 0x55) || (Sector[511] != 0xAA)) {
    return 0;
  }

  if (ReadUnaligned16 ((CONST UINT16 *)(Sector + 11)) != RAM_BLOCK_SIZE) {
    return 0;
  }

  if (CompareMem (Sector + FAT_LABEL_OFF, mLabel, FAT_LABEL_LEN) != 0) {
    return 0;
  }

  //
  // The embedded bring-up payload is FAT12 -- FAT16 cannot be made small
  // enough for the firmware volume -- while an external payload is FAT16.
  // Accept either, or the embedded volume is rejected as "not ours".
  //
  if ((CompareMem (Sector + FAT_TYPE_OFF, "FAT1", 4) != 0) ||
      ((Sector[FAT_TYPE_OFF + 4] != '2') && (Sector[FAT_TYPE_OFF + 4] != '6')))
  {
    return 0;
  }

  Bytes = (UINT64)ReadUnaligned32 ((CONST UINT32 *)(Sector + FAT_SECTORS_OFF));
  //
  // Volumes under 32 MiB store the sector count in the 16-bit field at 19 and
  // leave the 32-bit one at 32 zero.  The embedded 32 KiB payload is one of
  // those: reading only the 32-bit field would size it as zero bytes and the
  // volume would be thrown away as "not ours".
  //
  if (Bytes == 0) {
    Bytes = ReadUnaligned16 ((CONST UINT16 *)(Sector + FAT_SECTORS16_OFF));
  }

  Bytes *= RAM_BLOCK_SIZE;
  if ((Bytes == 0) || (Bytes > Limit)) {
    return 0;
  }

  return Bytes;
}

STATIC
EFI_STATUS
FindVolume (
  IN UINT64  Start,
  IN UINT64  End
  )
{
  UINT64  At;
  UINT64  Bytes;

  if (End <= Start) {
    return EFI_NOT_FOUND;
  }

  for (At = ALIGN_VALUE (Start, RAM_BLOCK_SIZE); At + RAM_BLOCK_SIZE <= End; At += RAM_BLOCK_SIZE) {
    Bytes = VolumeSizeAt ((UINT8 *)(UINTN)At, End - At);
    if (Bytes != 0) {
      return InstallVolume (At, Bytes);
    }
  }

  return EFI_NOT_FOUND;
}

/**
  Look for the volume in the backed regions the memory map describes.  The
  bootloader aligns a ramdisk to at least 2 MiB, so the coarse pass almost
  always hits; the finer passes only run when it does not.  Every 512 bytes from
  the start would take long enough to look like a hang.
**/
STATIC
EFI_STATUS
ScanMemory (
  IN EFI_MEMORY_DESCRIPTOR  *Map,
  IN UINTN                  Size,
  IN UINTN                  DescriptorSize
  )
{
  STATIC CONST UINT64  Steps[] = { 2 * 1024 * 1024, 64 * 1024, 4 * 1024 };
  UINTN                Step;
  UINTN                At;
  UINT64               Start;
  UINT64               End;
  UINT64               Address;
  UINT64               Bytes;
  UINTN                Regions;
  UINT64               Scanned;

  Regions = 0;
  Scanned = 0;

  for (Step = 0; Step < ARRAY_SIZE (Steps); Step++) {
    for (At = 0; At + DescriptorSize <= Size; At += DescriptorSize) {
      EFI_MEMORY_DESCRIPTOR  *Entry = (EFI_MEMORY_DESCRIPTOR *)((UINT8 *)Map + At);

      //
      // Back to the safe set.  Accepting every non-MMIO type was tried and it
      // took the tablet down: one of the reserved ranges the memory map
      // describes is not actually backed, and reading it produced a data abort
      // before this driver could even publish a device.  The map is now only
      // *reported* (ReportRegions) and never dereferenced outside these types.
      //
      if ((Entry->Type != EfiConventionalMemory) &&
          (Entry->Type != EfiBootServicesData) &&
          (Entry->Type != EfiBootServicesCode) &&
          (Entry->Type != EfiLoaderData) &&
          (Entry->Type != EfiLoaderCode) &&
          (Entry->Type != EfiACPIReclaimMemory))
      {
        continue;
      }

      Start = Entry->PhysicalStart;
      End   = Start + EFI_PAGES_TO_SIZE (Entry->NumberOfPages);
      if ((End - Start) < SCAN_MIN_REGION) {
        continue;
      }

      if (Step == 0) {
        Regions++;
        Scanned += End - Start;
      }

      for (Address = ALIGN_VALUE (Start, Steps[Step]); Address + RAM_BLOCK_SIZE <= End; Address += Steps[Step]) {
        Bytes = VolumeSizeAt ((UINT8 *)(UINTN)Address, End - Address);
        if (Bytes != 0) {
          return InstallVolume (Address, Bytes);
        }
      }
    }
  }

  DEBUG ((
    DEBUG_ERROR,
    "KIRBYINITRD: none, %u regs, %u MB scanned\n",
    (UINT32)Regions,
    (UINT32)(Scanned / (1024 * 1024))
    ));
  return EFI_NOT_FOUND;
}

/**
  Print the regions that could hold an 8 MiB payload, without touching them.

  Reading the memory map is always safe; dereferencing what it describes is
  not, which is exactly how the previous build died.  If the bootloader
  reserved the ramdisk's pages, the entry shows up here as type 0 with a start
  address, and the next build can go straight to it instead of searching.

  Two passes so reserved ranges win the three available lines over the
  conventional ones.
**/
STATIC
VOID
ReportRegions (
  IN EFI_MEMORY_DESCRIPTOR  *Map,
  IN UINTN                  Size,
  IN UINTN                  DescriptorSize
  )
{
  UINTN  At;
  UINTN  Shown;
  UINTN  Pass;

  Shown = 0;
  for (Pass = 0; (Pass < 2) && (Shown < 2); Pass++) {
    for (At = 0; (At + DescriptorSize <= Size) && (Shown < 2); At += DescriptorSize) {
      EFI_MEMORY_DESCRIPTOR  *Entry = (EFI_MEMORY_DESCRIPTOR *)((UINT8 *)Map + At);
      UINT64                 Bytes = EFI_PAGES_TO_SIZE (Entry->NumberOfPages);

      if ((Bytes < SCAN_MIN_REGION) || (Bytes > 64ULL * 1024 * 1024)) {
        continue;
      }

      if (Pass == 0) {
        if (Entry->Type != EfiReservedMemoryType) {
          continue;
        }
      } else if ((Entry->Type != EfiConventionalMemory) &&
                 (Entry->Type != EfiBootServicesData) &&
                 (Entry->Type != EfiBootServicesCode) &&
                 (Entry->Type != EfiLoaderData) &&
                 (Entry->Type != EfiLoaderCode) &&
                 (Entry->Type != EfiACPIReclaimMemory))
      {
        continue;
      }

      DEBUG ((
        DEBUG_ERROR,
        "KIRBYINITRD: mm t=%u 0x%lx n=0x%lx\n",
        (UINT32)Entry->Type,
        Entry->PhysicalStart,
        Bytes
        ));
      Shown++;
    }
  }
}

/**
  Fall back to the payload embedded in the firmware volume.

  This is the path that actually works on kirby.  The boot image does carry an
  8 MiB FAT16 payload in its ramdisk field -- ramdisk_size 0x800000 at offset
  0x87000 -- but the bootloader never loads it: the initrd range left in the
  device tree still points at the previous Android boot's cpio archive, the
  440 MB of conventional memory holds no such volume, and reading the reserved
  ranges to look for it aborts the boot three times over.

  So the bring-up payload rides inside the firmware volume as a FREEFORM file
  (kirby.fdf) and is read back with the volume's own protocol.  Nothing is
  dereferenced that the firmware does not already own.
**/
STATIC
EFI_STATUS
FindEmbedded (
  VOID
  )
{
  EFI_STATUS                     Status;
  EFI_FIRMWARE_VOLUME2_PROTOCOL  *Fv;
  EFI_HANDLE                     *Handles;
  UINTN                          Count;
  UINTN                          Index;
  VOID                           *Buffer;
  UINTN                          BufferSize;
  UINT32                         AuthenticationStatus;
  UINT64                         Bytes;

  Status = gBS->LocateHandleBuffer (
                  ByProtocol,
                  &mFirmwareVolume2Guid,
                  NULL,
                  &Count,
                  &Handles
                  );
  if (EFI_ERROR (Status)) {
    return Status;
  }

  for (Index = 0; Index < Count; Index++) {
    Status = gBS->HandleProtocol (Handles[Index], &mFirmwareVolume2Guid, (VOID **)&Fv);
    if (EFI_ERROR (Status)) {
      continue;
    }

    Buffer     = NULL;
    BufferSize = 0;
    Status     = Fv->ReadSection (
                       Fv,
                       (EFI_GUID *)&mPayloadGuid,
                       EFI_SECTION_RAW,
                       0,
                       &Buffer,
                       &BufferSize,
                       &AuthenticationStatus
                       );
    if (EFI_ERROR (Status) || (Buffer == NULL)) {
      continue;
    }

    Bytes = VolumeSizeAt ((UINT8 *)Buffer, BufferSize);
    if (Bytes == 0) {
      FreePool (Buffer);
      continue;
    }

    //
    // The block device points straight at this buffer, so it is deliberately
    // never freed.
    //
    Status = InstallVolume ((UINT64)(UINTN)Buffer, Bytes);
    FreePool (Handles);
    return Status;
  }

  FreePool (Handles);
  return EFI_NOT_FOUND;
}

STATIC
EFI_STATUS
ScanMemoryMap (
  VOID
  )
{
  EFI_STATUS             Status;
  EFI_MEMORY_DESCRIPTOR  *Map;
  UINTN                  Size;
  UINTN                  Key;
  UINTN                  DescriptorSize;
  UINT32                 Version;

  Size = 0;
  Status = gBS->GetMemoryMap (&Size, NULL, &Key, &DescriptorSize, &Version);
  if (Status != EFI_BUFFER_TOO_SMALL) {
    return Status;
  }

  //
  // GetMemoryMap can need more room the second time; the slack keeps it from
  // failing on the retry.
  //
  Size += 8 * DescriptorSize;
  Map   = AllocatePool (Size);
  if (Map == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }

  Status = gBS->GetMemoryMap (&Size, Map, &Key, &DescriptorSize, &Version);
  if (EFI_ERROR (Status)) {
    FreePool (Map);
    return Status;
  }

  ReportRegions (Map, Size, DescriptorSize);


  Status = ScanMemory (Map, Size, DescriptorSize);
  FreePool (Map);
  return Status;
}

EFI_STATUS
EFIAPI
KirbyInitrdDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_HOB_GUID_TYPE  *Hob;
  CONST VOID         *Fdt;
  CONST VOID         *StartProp;
  CONST VOID         *EndProp;
  INT32              Chosen;
  INT32              StartLength;
  INT32              EndLength;
  UINT64             Dtb;
  UINT64             Start;
  UINT64             End;

  Dtb = 0;

  Hob = GetFirstGuidHob (&mEntryArgHobGuid);
  if ((Hob == NULL) || (GET_GUID_HOB_DATA_SIZE (Hob) < sizeof (UINT64))) {
    DEBUG ((DEBUG_ERROR, "KIRBYINITRD: no entry argument HOB\n"));
  } else {
    Dtb = ReadUnaligned64 ((CONST UINT64 *)GET_GUID_HOB_DATA (Hob));
    if ((Dtb == 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
      DEBUG ((DEBUG_ERROR, "KIRBYINITRD: x0 0x%lx is not a device tree\n", Dtb));
      Dtb = 0;
    }
  }

  if (Dtb != 0) {
    Fdt    = (CONST VOID *)(UINTN)Dtb;
    Chosen = FdtPathOffset (Fdt, "/chosen");
    if (Chosen >= 0) {
      StartProp = FdtGetProp (Fdt, Chosen, "linux,initrd-start", &StartLength);
      EndProp   = FdtGetProp (Fdt, Chosen, "linux,initrd-end", &EndLength);
      if ((StartProp != NULL) && (EndProp != NULL) &&
          ((StartLength == 4) || (StartLength == 8)) &&
          ((EndLength == 4) || (EndLength == 8)))
      {
        Start = ReadAddress (StartProp, StartLength);
        End   = ReadAddress (EndProp, EndLength);
        DEBUG ((DEBUG_ERROR, "KIRBYINITRD: fdt range 0x%lx-0x%lx\n", Start, End));

        if (!EFI_ERROR (FindVolume (Start, End))) {
          return EFI_SUCCESS;
        }

        DEBUG ((DEBUG_ERROR, "KIRBYINITRD: range holds no payload, scanning memory\n"));
      } else {
        DEBUG ((DEBUG_ERROR, "KIRBYINITRD: /chosen has no initrd range\n"));
      }
    } else {
      DEBUG ((DEBUG_ERROR, "KIRBYINITRD: device tree has no /chosen\n"));
    }
  }

  if (!EFI_ERROR (FindEmbedded ())) {
    return EFI_SUCCESS;
  }

  //
  // Never fatal.  A missing payload degrades to UniXNU's built-in
  // configuration, which still tells us the rest of the boot chain works.
  //
  ScanMemoryMap ();
  return EFI_SUCCESS;
}
