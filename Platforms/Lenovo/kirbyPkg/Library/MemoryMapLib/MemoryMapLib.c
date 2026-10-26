#include <Library/MemoryMapLib.h>

/*
 * Memory map for the Lenovo Legion Y700 Gen 3 (TB321FU / "kirby", SM8650).
 *
 * Derivation (2026-10-26):
 *   - Reserved ranges come from the tablet's own reserved-memory node, read out
 *     of vendor_boot.img (pineapple v2 base DTB). Full dump:
 *     work/kirby-dtb/reserved-memory.txt
 *   - FD base 0xA7100000 / size 0x300000 is confirmed against the community
 *     boot.img: gzip(BootShim + FV), FvLength 0x400000 at offset 112.
 *   - Addresses above 0xFFE00000 are deliberately NOT described: the device is
 *     a 16 GiB SKU but this map only covers the low 4 GiB window, which is all
 *     the UEFI phase and the XNU handoff region need. Extending it needs a
 *     verified high-memory layout from a live FDT, not a guess.
 *
 * Differences from the caihong table this was derived from, all intentional:
 *   1. UEFI_Log moved out of 0x81CE4000 — that address sits inside kirby's
 *      aop_tme_uefi_merged_region (0x81C80000-0x81CF4000). Writing the UEFI log
 *      there would corrupt AOP state. It now lives at the tail of our own
 *      reserved block (0xA7FF0000).
 *   2. Low-memory reservations split to match kirby exactly: xbl_aop_merged,
 *      aop_cmd_db + aop_tme + chipinfo, adsp_mhi, global_sync + tz_stat, qdss.
 *   3. Reserved regions that caihong's table left undescribed (they were simply
 *      absent from its map) are now explicit: mpss_dsm, tz_merged,
 *      trust_ui_vm, oem_vm, llcc_lpi. Undescribed memory is never used, so this
 *      is documentation plus defence in depth rather than a behaviour fix.
 *   4. UFS MMIO (0x01D80000) added; caihong's map predates storage work and
 *      left the controller unmapped.
 *
 * Known gaps, do not treat as done:
 *   - High memory above 4 GiB is not mapped (see above).
 *   - The XNU handoff window below is inherited as a 256 MiB reservation; the
 *     payload placement must be checked against the real live FDT before the
 *     first kernel bring-up, not just the menu phase.
 */
STATIC
EFI_MEMORY_REGION_DESCRIPTOR
gMemoryDescriptor[] = {
  // Name, Address, Length, HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttribute

  // DDR Regions — low memory, mirrors kirby reserved-memory
  {"HYP",                 0x80000000, 0x01200000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},  // gunyah_hyp 14M + cpusys_vm 4M
  {"RSRV0",               0x816E0000, 0x00320000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},
  {"XBL_AOP",             0x81A00000, 0x00260000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},           // xbl_aop_merged -> 0x81C60000
  {"AOP",                 0x81C60000, 0x00095000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},  // cmd_db + tme + chipinfo -> 0x81CF5000
  {"SMEM",                0x81D00000, 0x00200000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"ADSP_MHI",            0x81F00000, 0x00020000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"PvmFw",               0x824A0000, 0x00100000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},
  {"GLOBAL_SYNC",         0x82600000, 0x00200000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},  // global_sync + tz_stat
  {"QDSS",                0x82800000, 0x02000000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"QLINK_LOGGING",       0x84800000, 0x00200000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"MPSS_DSM",            0x86B00000, 0x05100000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"PIL_Reserved",        0x8BC00000, 0x17580000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},  // mpss + adsp + cdsp + camera/video/cvp + ramoops
  {"DBI_Dump",            0xA6100000, 0x00F00000, NoHob,  MMAP_IO, INITIALIZED, Conv,   UNCACHED_UNBUFFERED_XN},
  {"FD_Reserved",         0xA7000000, 0x00100000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK},
  {"UEFI_FD",             0xA7100000, 0x00300000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK},
  {"UEFI_FD_Reserved",    0xA7400000, 0x00200000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK},
  {"Info_Blk",            0xA7601000, 0x00001000, AddMem, SYS_MEM, SYS_MEM_CAP, RtData, WRITE_BACK_XN},
  {"MMU_PageTables",      0xA7602000, 0x00003000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"Log_Buffer",          0xA7605000, 0x00008000, AddMem, SYS_MEM, SYS_MEM_CAP, RtData, WRITE_BACK_XN},
  {"UEFI_Stack",          0xA760D000, 0x00040000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"SEC_Heap",            0xA764D000, 0x0008C000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"Sched_Heap",          0xA76D9000, 0x00400000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"FV_Region",           0xA7AD9000, 0x00400000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"UEFI_RESV",           0xA7ED9000, 0x00117000, AddMem, SYS_MEM, SYS_MEM_CAP, BsData, WRITE_BACK_XN},
  {"UEFI_Log",            0xA7FF0000, 0x00010000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},  // moved: was 0x81CE4000 (inside AOP TME)
  {"Kernel",              0xA8000000, 0x10000000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, WRITE_BACK_XN},
  {"DXE_Heap",            0xB8000000, 0x1BA00000, AddMem, SYS_MEM, SYS_MEM_CAP, Conv,   WRITE_BACK_XN},
  {"HWFENCE",             0xD4E23000, 0x002DD000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_THROUGH_XN},
  {"Display_Reserved",    0xD5100000, 0x02B00000, AddMem, MEM_RES, SYS_MEM_CAP, Reserv, WRITE_THROUGH_XN},
  {"TZ_MERGED",           0xD8000000, 0x00800000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"TZApps_Reserved",     0xD8800000, 0x1B000000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"TRUST_UI_VM",         0xF3800000, 0x04400000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"OEM_VM",              0xF7C00000, 0x04C00000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},
  {"LLCC_LPI",            0xFF800000, 0x00600000, AddMem, MEM_RES, UNCACHEABLE, Reserv, UNCACHED_UNBUFFERED_XN},

  // Other Memory Regions
  {"IMEM_Base",           0x14680000, 0x0002A000, NoHob,  MMAP_IO, INITIALIZED, Conv,   NS_DEVICE},
  {"IMEM_Cookie_Base",    0x146AA000, 0x00016000, AddDev, MMAP_IO, INITIALIZED, Conv,   NS_DEVICE},

  // Register Regions
  {"IPC_ROUTER_TOP",      0x00400000, 0x00100000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"SECURITY_CONTROL",    0x00780000, 0x00007000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"QUP",                 0x00800000, 0x00300000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},  // GENI SE: SPI@0xA90000 (touch) lives here
  {"PRNG_CFG_PRNG",       0x010C0000, 0x0000C000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"CRYPTO0_CRYPTO",      0x01DC0000, 0x00040000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"UFS",                 0x01D80000, 0x00060000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},  // PHY 0x1D80000 + HC 0x1D84000
  {"CLK_TCSR_TCSR_REGS",  0x01F00000, 0x00100000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"PERIPH_SS",           0x08800000, 0x00100000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"USB",                 0x0A600000, 0x00200000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"AOSS",                0x0B000000, 0x04000000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},  // MDSS/DSI 0xAE00000, DSI0 0xAE94000, DSI1 0xAE96000
  {"TLMM",                0x0F000000, 0x01000000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},  // touch reset GPIO 161 / irq GPIO 162
  {"SMMU",                0x15000000, 0x00200000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE},
  {"APSS_HM",             0x17000000, 0x02000000, AddDev, MMAP_IO, UNCACHEABLE, MmIO,   NS_DEVICE}   // GIC 0x17100000, timer 0x17420000
};

VOID
GetMemoryMap (
  OUT EFI_MEMORY_REGION_DESCRIPTOR **MemoryDescriptor,
  OUT UINT8                         *MemoryDescriptorCount
  )
{
  // Pass Data
  *MemoryDescriptor      = gMemoryDescriptor;
  *MemoryDescriptorCount = ARRAY_SIZE (gMemoryDescriptor);
}
