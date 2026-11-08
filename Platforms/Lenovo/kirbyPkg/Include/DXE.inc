  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf

  # 探针：读 0x81D00000 前 32 字节，判断 SMEM 是否真的没被建。放在 PcdDxe 之后、
  # 其它一切之前，越早越能反映 ABL 交接时的原始状态。
  INF kirbyPkg/Drivers/SmemProbeDxe/SmemProbeDxe.inf

  # 读 GCC 的 BCR/GDSCR/CFG_GDSCR 和 5 个 CBCR，写进 KLOG，由 QrLogDxe 画成二维码。
  # 为什么在 UEFI 阶段读：内核里 qcom_usb_debug_init() 拒绝硬件时，唯一的输出通道就是
  # 那个刚拒绝它的 USB，而 PE_kputc 要等它返回后才指向视频控制台，boot_progress 在这个
  # UniXNU 版本里又不存在。只读 GCC（常开电源域，读它不会挂总线），不读 DWC3——
  # 分支时钟被 gate 时读 DWC3 可能 stall 住连接。见 Drivers/UsbStateProbeDxe/。
  INF kirbyPkg/Drivers/UsbStateProbeDxe/UsbStateProbeDxe.inf

  # 把调试日志画成二维码轮播，见 Drivers/QrLogDxe/QrLogDxe.c
  INF kirbyPkg/Drivers/QrLogDxe/QrLogDxe.inf

  # EnvDxeEnhanced 也移出固件卷，不只是移出 APRIORI：如果只从调度表里删掉，
  # DxeCore 仍会在 BDS 阶段按依赖关系把它加载起来，然后一样撞 ASSERT。
  # 它在 UEFI 阶段只负责把 Android env 分区参数转交 OS，菜单与 XNU 交接都用不到。
  # INF Binaries/kirby/QcomPkg/Drivers/EnvDxe/EnvDxeEnhanced.inf

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf

  # SCM 三件套已撤回：821cacd / 2b1704a 实测都因 TZ/QSEE 不可用而
  # 入口点返回 Not Found，撞厂商二进制自带的 ASSERT 死循环。见 APRIORI.inc。
  # INF Binaries/kirby/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  # INF Binaries/kirby/QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf
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

  #
  # UniXNU required integration
  # (unixnu.com/zh/porting/uefi-firmware#required-integration).
  # FV order does not decide dispatch -- DxeCore uses the depex plus
  # APRIORI.inc -- but keep the payload chain readable: KirbyInitrdDxe
  # publishes the payload volume, DiskIoDxe wraps it, Fat publishes the
  # volume UniXNU reads \EFI\UniXNU\unixnu.toml from.
  #
  # kirbyPkg's KirbyInitrdDxe replaces UniXNUPkg/Driver/UniXNURamDiskDxe here.
  # That driver reads the volume from /chosen/linux,initrd-start, but on this
  # boot path the property still holds the previous Android boot's ramdisk
  # range, so the block device it published returned garbage ("jmp=02
  # bps=12343 spc=55") and Fat never produced a SimpleFileSystem.
  #
  INF MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  INF kirbyPkg/Drivers/KirbyInitrdDxe/KirbyInitrdDxe.inf
  INF UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
  INF UniXNUPkg/Application/UniXNU/UniXNU.inf
  INF DarwinBootPkg/Driver/DarwinBoot.inf

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
  # 【结论，2026-11-06】SmemDxe 的 boot_a 单变量实验已经做完：SmemProbeDxe 在
  # DXE 早期读到 0x81D00000 前四个字全是 0，magic 不是 534d454d，说明 ABL 在
  # fastboot boot 这条路径上根本没有初始化 SMEM，换启动路径也救不回来。
  # SmemDxe 随后返回 EFI_NOT_FOUND 并在 AutoGen 的 ASSERT_EFI_ERROR 上死循环，
  # 把 DXE 卡死在菜单之前。它必须留在固件卷外面，直到 SMEM 本身被修好。
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

  # 【单变量实验结论 2026-11-06 16:15，b8b90bc 实测】放开 ButtonsDxe 后它自己撞
  # ASSERT_EFI_ERROR (Status = Not Found)，屏幕 ERROR 行
  # C9000002:V03000007 TO 5BD181DB-0487-4F1A-AE73-820E165611B3
  # （该 GUID 正是 ButtonsDxe.inf 的 FILE_GUID），ASSERT AutoGen.c +469。
  # 原因同 SCM 三件套：ButtonsDxe 运行时依赖 TZ/QSEE（PMIC SDAM / PON），
  # fastboot boot 路径下不可用；二进制自带 ASSERT，改 DebugLib 宏够不着。
  # apply_binary_patches.py 只有电源键→ENTER 两处补丁，绕不过这个 ASSERT。
  # 按官方第 6 步「仅选择必需输入已满足的实现」退回。
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
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  # INF Binaries/kirby/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  # INF Binaries/kirby/QcomPkg/Drivers/XhciDxe/XhciDxe.inf

  # INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  # INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  # INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

  # bring-up: 先摘掉厂商驱动（SMEM 无效导致整条链都不稳），稍后按依赖顺序加回
  # INF Binaries/kirby/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
  # INF Binaries/kirby/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  # USB 栈：xHCI 直接操作控制器，depex=TRUE，不经 SMEM/Clock。
  # fastboot 本身走 USB，说明 ABL 已把控制器带起来，值得一试。
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
