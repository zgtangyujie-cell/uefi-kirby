APRIORI DXE {
  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf
  INF QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf

  # EnvDxeEnhanced 已移除。它的入口点在这台机器上返回 EFI_NOT_FOUND（找不到 env
  # 分区），而 AutoGen.c 会在入口点末尾 ASSERT_EFI_ERROR(Status)，DEBUG 构建里
  # 直接 CpuDeadLoop —— 整个固件钉死在这里，后面的驱动一个都加载不到。
  #
  # 试过四轮改 PcdDebugPropertyMask / DebugAssertEnabled / ASSERT 宏，全部无效
  # （见 scripts/build.sh 的注释）。这个驱动在 UEFI 阶段也没有用处：它只是把
  # Android 的 env 分区参数转交给操作系统，BDS 菜单和 XNU 交接都不需要它。
  # INF Binaries/kirby/QcomPkg/Drivers/EnvDxe/EnvDxeEnhanced.inf

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf

  # SmemDxe 暂时移出。它在这台机器上返回 EFI_NOT_FOUND，理由是
  # "SMEM is not initialized by Boot." —— 也就是 0x81D00000 那块内容无效。
  # 地址和缓存属性都已核对过：ABL 的 DTS 里 memory@81D00000 标着
  # mem-label = "SMEM"、reg = <0x00 0x81d00000 0x00 0x200000>、
  # cache-attributes = [0x25]，与 AOP / UEFI_Log 相同，我们表里写的也一致。
  # 所以不是我们映射错了，是那块内存本身没有有效的 SMEM header。
  #
  # 它后面挂着一整串 depex 依赖它的驱动（IPCCDxe / Smp2pDxe / NpaDxe / RpmhDxe
  # / ClockDxe ...）。移掉它之后这些驱动的 depex 永远不满足，DxeCore 会安静地
  # 跳过它们，不会 NOT_FOUND、不会 ASSERT，启动可以一路走到 BDS。
  # 这是为了先把菜单逼出来；SMEM 本身的问题之后单独修。
  # 【探测】单变量实验：走 boot_a 正常启动流程后，SMEM 是否已被 ABL 初始化。
  # 若这次不再报 "SMEM is not initialized by Boot."，说明换启动路径就是解，
  # 整条 Qualcomm 栈都可以加回来；若仍报错，则 SMEM 与启动路径无关。
  INF Binaries/kirby/QcomPkg/Drivers/SmemDxe/SmemDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/HWIODxe/HWIODxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/Smp2pDxe/Smp2pDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SSRDxe/SSRDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ClockDxe/ClockDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/SPMIDxe/SPMIDxe.inf

  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf

  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf

  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
  # UFSDxe is back. It was removed from the image for one round as a
  # single-variable test and the fault at 0x09800000 did not move, so this
  # driver is not what touches that address.
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UFSDxe/UFSDxe.inf

  INF FatPkg/EnhancedFatDxe/Fat.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TzDxe/TzDxeLA.inf

  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/OcdtDxe/OplusProject.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/FeatureEnablerDxe/FeatureEnablerDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PILDxe/PILDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf

  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  INF MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  INF Binaries/kirby/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  INF Binaries/kirby/QcomPkg/Drivers/XhciDxe/XhciDxe.inf

  INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  INF Binaries/kirby/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  INF Binaries/kirby/QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.inf
  # 退回：SPMI 需要 SPMI 控制器时钟，而时钟来自 ClockDxe -> RpmhDxe -> SMEM。
  # SMEM 未修好之前这条链是死的，加载它只会让启动停在 SPMI 而不是进菜单。
  # INF Binaries/kirby/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/TsensDxe/TsensDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/DisplayDxe/DisplayDxe.inf
!else
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
!endif

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/LimitsDxe/LimitsDxe.inf
!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/CPRDxe/CPRDxe.inf
!endif
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UCDxe/UCDxe.inf
  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RNGDxe/RngDxe.inf

  INF EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/RscDxe/RscDxe.inf
}
