APRIORI DXE {
  INF MdeModulePkg/Core/Dxe/DxeMain.inf
  INF MdeModulePkg/Universal/PCD/Dxe/Pcd.inf
  INF QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/EnvDxe/EnvDxeEnhanced.inf

  INF MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf
  INF MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf
  INF MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf
  INF ArmPkg/Drivers/CpuDxe/CpuDxe.inf
  INF ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf
  INF EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf
  INF ArmPkg/Drivers/TimerDxe/TimerDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/SmemDxe/SmemDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/HWIODxe/HWIODxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/Smp2pDxe/Smp2pDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/SSRDxe/SSRDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ClockDxe/ClockDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
  INF Binaries/kirby/QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf
  INF Binaries/kirby/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/SPMIDxe/SPMIDxe.inf

  INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/PmicDxe/PmicDxeLa.inf
  INF Binaries/kirby/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf
  INF Binaries/kirby/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf

  INF MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
  # UFSDxe is temporarily NOT in this early list. The crash report names this
  # module, and removing it from APRIORI is the cleanest single-variable test
  # available: if the fault at 0x09800000 disappears, UFSDxe really is the
  # caller and the fix belongs in the map or in that driver. If the same fault
  # still happens, then something else touches that address and UFSDxe was only
  # the module that happened to be executing.
  # It is still in DXE.inc, so the image still contains it.
  # INF Binaries/kirby/QcomPkg/Drivers/UFSDxe/UFSDxe.inf

  INF FatPkg/EnhancedFatDxe/Fat.inf

  INF Binaries/kirby/QcomPkg/Drivers/TzDxe/TzDxeLA.inf

  INF MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/OcdtDxe/OplusProject.inf
  INF Binaries/kirby/QcomPkg/Drivers/FeatureEnablerDxe/FeatureEnablerDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/PILDxe/PILDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf

  INF MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf
  INF MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf
  INF EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf
  INF EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf
  INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
  INF MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf
  INF MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf
  INF MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf
  INF MdeModulePkg/Universal/BdsDxe/BdsDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
  INF Binaries/kirby/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/XhciDxe/XhciDxe.inf

  INF MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf
  INF MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/UsbConfigDxe/UsbConfigDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/TsensDxe/TsensDxe.inf

!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  INF Binaries/kirby/QcomPkg/Drivers/DisplayDxe/DisplayDxe.inf
!else
  INF SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
!endif

  INF Binaries/kirby/QcomPkg/Drivers/LimitsDxe/LimitsDxe.inf
!if $(USE_CUSTOM_DISPLAY_DRIVER) == 1
  INF Binaries/kirby/QcomPkg/Drivers/CPRDxe/CPRDxe.inf
!endif
  INF Binaries/kirby/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/UCDxe/UCDxe.inf
  INF Binaries/kirby/QcomPkg/Drivers/RNGDxe/RngDxe.inf

  INF EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf
  INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
  INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
  INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

  INF Binaries/kirby/QcomPkg/Drivers/RscDxe/RscDxe.inf
}
