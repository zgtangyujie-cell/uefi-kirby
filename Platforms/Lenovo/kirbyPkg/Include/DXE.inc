  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf

  # EnvDxeEnhanced 也移出固件卷，不只是移出 APRIORI：如果只从调度表里删掉，
  # DxeCore 仍会在 BDS 阶段按依赖关系把它加载起来，然后一样撞 ASSERT。
  # 它在 UEFI 阶段只负责把 Android env 分区参数转交 OS，菜单与 XNU 交接都用不到。
  # INF Binaries/kirby/QcomPkg/Drivers/EnvDxe/EnvDxeEnhanced.inf

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TzDxe/TzDxeLA.inf

  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/HWIODxe/HWIODxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf

  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf

  INF FatPkg/EnhancedFatDxe/Fat.inf
  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

  # UFSDxe is back. It was left out of the image for one round as a
  # single-variable test; the fault at 0x09800000 did not move, so this driver
  # is not the module touching that address and there is no reason to drop it.
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UFSDxe/UFSDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ClockDxe/ClockDxe.inf
  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/SPMIDxe/SPMIDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
  # SmemDxe 同 APRIORI.inc：移出固件卷，避免 BDS 阶段被重新加载后撞同一个 ASSERT。
  # INF Binaries/kirby/QcomPkg/Drivers/SmemDxe/SmemDxe.inf

  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RscDxe/RscDxe.inf

  INF EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/CPRDxe/CPRDxe.inf
!endif
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/FeatureEnablerDxe/FeatureEnablerDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DisplayDxe/DisplayDxe.inf
  # Re-enable (power-cycle) the panel after DXE display resets.
  # Same pattern used by enchilada / miatoll / equuleus / lavender.
  INF QcomPkg/Drivers/DisplayReEnablerDxe/DisplayReEnablerDxe.inf
!else
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
!endif

  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/Smp2pDxe/Smp2pDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SSRDxe/SSRDxe.inf
  # Crashes
  # INF Binaries/kirby/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/OcdtDxe/OplusProject.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TsensDxe/TsensDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/LimitsDxe/LimitsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/XhciDxe/XhciDxe.inf

  INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbInitDxe/UsbInitDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UCDxe/UCDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RNGDxe/RngDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PILDxe/PILDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
