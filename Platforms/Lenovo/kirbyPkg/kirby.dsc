##
#
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
#
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = kirby
  PLATFORM_GUID                  = 3E5A7C91-8B2D-4F46-9A15-C7D0E62F4B83
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/kirbyPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = kirbyPkg/kirby.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

  #
  # 0 = SM8650-AA
  # 1 = SM8650-Q-AA
  # 2 = SM8650-AB
  # 3 = SM8650-Q-AB
  # 4 = SM8650-AC
  #
  SOC_TYPE                       = 2

!include LanaiPkg/LanaiPkg.dsc.inc

[PcdsFeatureFlag]
  #
  # EnglishDxe installs EFI_UNICODE_COLLATION2_PROTOCOL only when this flag is
  # set, and it never installs the v1 protocol at all:
  #     if (FeaturePcdGet (PcdUnicodeCollation2Support)) {
  #       gBS->InstallMultipleProtocolInterfaces (&mHandle,
  #         &gEfiUnicodeCollation2ProtocolGuid, &Unicode2Eng, NULL);
  #     }
  #     return Status;
  # With the flag clear the driver loads, runs, installs nothing and still
  # returns EFI_SUCCESS.  FatDriverBindingStart then fails on its very first
  # statement ("InitializeUnicodeCollationSupport" -> EFI_UNSUPPORTED) and never
  # opens the volume, which is indistinguishable from a rejected FAT image.
  # This is why SimpleFileSystem stayed at 0 for every payload variant.
  #
  gEfiMdeModulePkgTokenSpaceGuid.PcdUnicodeCollation2Support|TRUE

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0xA760D000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Lenovo"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"Lenovo Legion Y700 Gen3"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Lenovo Legion Y700 Gen3"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"TB321FU"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"TB321FU"

  #
  # Simple Frame Buffer
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1600
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2560
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

  #
  # Debug policy
  #
  # PcdDebugPropertyMask = 0x02 keeps DEBUG() text but turns ASSERT() into a
  # no-op.  The default (0x2F, matching caihong) enables
  # DEBUG_PROPERTY_ASSERT_DEADLOOP_ENABLED, and AutoGen.c ends every driver
  # entry point with ASSERT_EFI_ERROR (Status).  On real hardware it is entirely
  # normal for an optional driver to return EFI_NOT_FOUND -- EnvDxeEnhanced does
  # exactly that on this board -- and the dead loop then stops the boot at a
  # driver that DxeCore would otherwise have unloaded and moved past.
  #
  # PcdDebugPrintErrorLevel: ERROR|WARN only.
  # The INFO pass did its job -- it proved DEBUG output reaches the panel -- but
  # it also drowned KLOG in DXE core "Loading driver" lines, so the 600-byte QR
  # slice held nothing but noise and never reached the UniXNU drivers.  Back to
  # ERROR|WARN here; UniXNUDxe's own success line is promoted to DEBUG_ERROR in
  # scripts/build.sh for the duration of this investigation.
  #
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x02
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x80000002

  #
  # Variable store.
  #
  # This platform has no flash FVB.  VariableRuntimeDxe therefore has no NV
  # backend, rejects NV variables with EFI_INVALID_PARAMETER -- proven by the
  # UniXNUDxe probe, which printed attr=0x7 size=96 (both valid) and still got
  # 0x2 -- and BDS falls back to its default boot-device list because BootOrder
  # cannot be written either.
  #
  # EmuNvMode makes the driver emulate an NV store in RAM: NV semantics hold for
  # the session, nothing is written to any partition.  Dropping the NV attribute
  # from UniXNUDxe instead was tried and does not help (attr=0x6 still fails).
  #
  gEfiMdeModulePkgTokenSpaceGuid.PcdEmuVariableNvModeEnable|TRUE

  #
  # Boot manager menu.
  #
  # UniXNUDxe cannot register Boot0000 here: SetVariable returns
  # EFI_INVALID_PARAMETER with demonstrably valid arguments (attr=0x7, 96 bytes),
  # with the NV attribute removed (attr=0x6) and with EmuNvMode enabled -- so the
  # variable store itself is broken on this platform, and BDS falls back to its
  # default boot-device list for the same reason.
  #
  # BDS does not need Boot#### to start an application: it resolves
  # PcdBootManagerMenuFile in the firmware volume and boots that image.  Point it
  # at UniXNU.efi (FILE_GUID of UniXNUPkg/Application/UniXNU/UniXNU.inf) and BDS
  # starts UniXNU without touching the variable store at all.
  #
  #
  # Spelled as a byte array on purpose: {GUID("...")} is a .dec construct, the
  # DSC parser wants the raw EFI_GUID bytes (Data1..Data3 little endian).
  # 9B665204-A133-47A2-9396-9E2B370A4E25
  #
  gEfiMdeModulePkgTokenSpaceGuid.PcdBootManagerMenuFile|{0x04, 0x52, 0x66, 0x9B, 0x33, 0xA1, 0xA2, 0x47, 0x93, 0x96, 0x9E, 0x2B, 0x37, 0x0A, 0x4E, 0x25}

[Packages]
  #
  # UniXNU required integration.  DarwinBoot.inf consumes
  # gUniXNULoaderProtocolGuid from this package; the roots themselves are added
  # to the search path by kirbyPkg/DeviceBuild.py GetPackagesPath().
  #
  UniXNUPkg/UniXNUPkg.dec

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|kirbyPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QR encoder, used by QrLogDxe to put the debug log on screen
  #
  QrEncoderLib|MsGraphicsPkg/Library/QrEncoderLib/QrEncoderLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|kirbyPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

  #
  # UniXNU required integration: the shared drivers ask for these two by name
  # (unixnu.com/zh/porting/uefi-firmware#required-integration).
  #
  HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf
  FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf

  #
  # UniXNUPkg.dec declares UniXNULib as the boot-manager core shared by the
  # application and the DXE driver builds.  Without this mapping the build
  # stops at
  #   error 4000: Instance of library class [UniXNULib] is not found
  # for UniXNU.inf.  It is the only custom library class in that package --
  # every other class the four modules consume is a standard MdePkg one.
  #
  UniXNULib|UniXNUPkg/Library/UniXNULib/UniXNULib.inf

[Components]
  #
  # Bring-up diagnostics
  #
  # 读 0x81D00000 的前几个字打到屏幕上，用来判断 SMEM 到底有没有被 ABL 建起来。
  # 见 Drivers/SmemProbeDxe/SmemProbeDxe.c 里的说明。
  kirbyPkg/Drivers/SmemProbeDxe/SmemProbeDxe.inf

  #
  # Reads the GCC registers QcomXnuUsbDebug's inherited-state check looks at,
  # and appends them to the KLOG buffer so QrLogDxe draws them.  GCC only: it is
  # in an always-on power domain, so the reads cannot hang, whereas a read of
  # DWC3 with gated branch clocks can stall the interconnect.
  # See Drivers/UsbStateProbeDxe/UsbStateProbeDxe.c.
  #
  kirbyPkg/Drivers/UsbStateProbeDxe/UsbStateProbeDxe.inf

  #
  # Debug log as QR codes on the panel (no menu, no input, no host tool)
  #
  kirbyPkg/Drivers/QrLogDxe/QrLogDxe.inf

  #
  # UniXNU + DarwinBoot, the official required-integration list.
  # Matching FV lines live in Include/DXE.inc, dispatch order in
  # Include/APRIORI.inc; the package roots arrive through PACKAGES_PATH, which
  # scripts/build.sh appends to.
  #
  # UniXNU.inf is a UEFI_APPLICATION: it belongs here (so it is compiled) and in
  # DXE.inc (so it lands in the firmware volume).  It must NOT go into
  # APRIORI.inc -- APRIORI only accepts drivers.
  #
  MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  #
  # UniXNUPkg's UniXNURamDiskDxe is deliberately NOT used.  It treats
  # /chosen/linux,initrd-start as the first byte of the payload, and on this
  # boot path that property still holds the previous Android boot's range, so
  # the block device it publishes reads back as garbage.  KirbyInitrdDxe scans
  # for the volume label instead; it is the same approach UniXNU-caihong uses on
  # the same SoC family.
  #
  kirbyPkg/Drivers/KirbyInitrdDxe/KirbyInitrdDxe.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  DarwinBootPkg/Driver/DarwinBoot.inf

  #
  # ACPI Tables
  #
  #kirby/AcpiTables.inf
