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
  # PcdDebugPrintErrorLevel: ERROR|WARN|INFO for the UniXNU integration pass.
  # 0x80000002 (ERROR|WARN) hid every UniXNUDxe line: that driver logs success
  # at DEBUG_INFO, and only its two failure paths use DEBUG_ERROR.  With no
  # output at all there was no way to tell "never dispatched" (depex waiting on
  # the variable protocols) from "dispatched and failed".  0x40 adds INFO.
  # Put it back once the boot option registers -- the default level prints one
  # "Memory Allocation" line per pool allocation and pushes the interesting
  # part off the screen.
  #
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x02
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x80000042

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
  UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
  UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  UniXNUPkg/Application/UniXNU/UniXNU.inf
  DarwinBootPkg/Driver/DarwinBoot.inf

  #
  # ACPI Tables
  #
  #kirby/AcpiTables.inf
