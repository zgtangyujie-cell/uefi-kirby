/* SPDX-License-Identifier: MIT
 * Kalama-family GCC + QSMMUv500 + DWC3.  SM8650 (cape/pineapple) transpose.
 *
 * Every value below is copied from one of two sources; nothing is guessed:
 *
 *   1. Live device tree, read on the target TB321FU with `su`:
 *        /soc@0/usb@a600000        reg = <0x0 0x0a600000 0x0 0x100000>
 *                                  dr_mode = "otg"
 *        /soc@0/clock-controller@100000
 *                                  reg = <0x0 0x00100000 0x0 0x1f4200>
 *        /soc@0/iommu@15000000     reg = <0x0 0x15000000 0x0 0x100000>
 *                                  compatible = "qcom,qsmmu-v500"
 *        iommus = <... SID 0x40 ...>, iova window 0x90000000/0x60000000
 *
 *   2. Pinned mainline sources for the same silicon:
 *        drivers/clk/qcom/gcc-sm8650.c   BCR 0x39000, GDSCR 0x39004,
 *                                        master 0x39018, sleep 0x39024,
 *                                        utmi 0x39028, cfg_noc_axi 0x39088,
 *                                        aggre_axi 0x3908c  (byte-identical
 *                                        to gcc-sm8550.c)
 *        include/dt-bindings/clock/qcom,sm8650-gcc.h
 *                                        the five USB clock indexes used by
 *                                        the CBCR list below are
 *                                        0xb0 master / 0xb2 cfg_noc_axi /
 *                                        0xb5 aggre_axi / 0x0a sleep /
 *                                        0x03 mock_utmi
 *        drivers/usb/dwc3/dwc3-qcom.c    QSCRATCH = DWC3 + 0xf8800,
 *                                        HS_PHY_CTRL = QSCRATCH + 0x10,
 *                                        VBUS mask (1 << 20) | (1 << 28)
 *
 * `QUD_GCC_CFG_GDSCR_OFFSET` is not a per-SoC constant: the GDSC framework
 * defines CFG_GDSCR as GDSCR + 4 (drivers/clk/qcom/gdsc.c:35), which yields
 * 0x39008 here and matches Sm8550.h.  The module only reads bit 16 of it to
 * confirm the USB GDSC is already powered by firmware.
 *
 * `QUD_PSCI_SMC_RESET` is 0 because this board's PSCI SYSTEM_RESET through
 * SMC has never been qualified.  docs/porting-other-socs.md:41 requires 0
 * until it is; the reboot path then reports an error instead of resetting.
 *
 * Inherited PHY/power only, exactly like Sm8550.h: firmware has already
 * brought the controller up in DEVICE mode, and this header only tells the
 * backend where to look, not how to cold-start anything.
 */
#ifndef QUD_SM8650_H
#define QUD_SM8650_H
#define QUD_SOC_NAME "sm8650-inherited"
/* Development IDs inherited from m1n1, not a new product allocation. */
#define QUD_USB_VID 0x1209u
#define QUD_USB_PID 0x316du
#define QUD_USB_SERIAL "QcomXnuUsbDebug"
#define QUD_USB_PRODUCT "Qualcomm XNU Debug"
#define QUD_GCC_BASE 0x00100000ULL
/* Live DT says 0x1f4200; the largest offset used here is 0x3908c. */
#define QUD_GCC_BYTES 0x40000u
#define QUD_DWC3_BASE 0x0a600000ULL
#define QUD_DWC3_BYTES 0x100000u
#define QUD_SMMU_BASE 0x15000000ULL
#define QUD_SMMU_BYTES 0x100000ULL
#define QUD_STREAM_ID 0x40u
#define QUD_DMA_IOVA 0x90000000ULL
#define QUD_GCC_CBCR_OFFSETS {0x39018u, 0x39088u, 0x3908cu, 0x39028u, 0x39024u}
#define QUD_GCC_BCR_OFFSET 0x39000u
#define QUD_GCC_GDSCR_OFFSET 0x39004u
#define QUD_GCC_CFG_GDSCR_OFFSET 0x39008u
#define QUD_QSCRATCH_HS_PHY_CTRL_OFFSET 0xf8810u
#define QUD_QSCRATCH_VBUS_MASK ((1u << 20) | (1u << 28))
/* Only set after the board's PSCI SYSTEM_RESET through SMC is qualified. */
#define QUD_PSCI_SMC_RESET 0
#endif
