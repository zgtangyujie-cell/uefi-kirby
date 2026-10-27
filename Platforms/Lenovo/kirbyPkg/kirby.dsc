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
  # PcdDebugPrintErrorLevel keeps ERROR|WARN|LOAD only.  The default level makes
  # DxeCore print one "Memory Allocation" line per pool allocation, which filled
  # 60 of the 71 rows on screen and pushed the interesting part off the bottom.
  #
  gEfiMdePkgTokenSpaceGuid.PcdDebugPropertyMask|0x02
  gEfiMdePkgTokenSpaceGuid.PcdDebugPrintErrorLevel|0x80000006

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|kirbyPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|kirbyPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  #
  # Bring-up diagnostics
  #
  # 读 0x81D00000 的前几个字打到屏幕上，用来判断 SMEM 到底有没有被 ABL 建起来。
  # 见 Drivers/SmemProbeDxe/SmemProbeDxe.c 里的说明。
  kirbyPkg/Drivers/SmemProbeDxe/SmemProbeDxe.inf

  #
  # ACPI Tables
  #
  #kirby/AcpiTables.inf
