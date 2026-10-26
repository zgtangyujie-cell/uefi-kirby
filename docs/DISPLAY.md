# 显示（DisplayDxe）现状与风险

> 结论先说：**显示是 Phase 1 唯一没有把握的环节**。固件能编、BootShim 能跑、内存表能对，
> 但屏幕能不能亮，取决于一个我们拿不到源码的预编译驱动。

## 1. 为什么这块最难

| 事实 | 依据 |
|---|---|
| Mu-Silicium **没有可编译的 DisplayDxe 源码**，只有 `DisplayReEnablerDxe`（辅助用） | `Mu-Silicium/Silicon/Qualcomm/QcomPkg/Drivers` 目录只有两项 |
| 显示必须用厂商预编译的 `Binaries/<device>/QcomPkg/Drivers/DisplayDxe/DisplayDxe.efi` | caihong 就是这么做的 |
| caihong 那份是 **OnePlus/OPPO 的构建**：含 `oplus_bsp_tp_custom`、`dsi_display0`、`SMEM_PROJECT` 等 | 二进制字符串 |
| 它从 `RawFiles/Panel_*.xml` 读面板参数，固件里内置 **18 个面板节点名**（编译期固定） | `qcom,mdss_dsi_panel_*` 字符串表 + `GetPanelConfigFromFile` |
| Lenovo 原厂 UEFI **不走 XML**：`uefi.elf` 里 0 个 `Panel` 字符串，是设备树驱动 | 全文件字符串扫描 |
| `Device-Binaries` 里**没有 kirby/tb321fu**，联想只有 9707f、j706f（且不同 SoC） | 仓库目录 |

## 2. kirby 面板的权威参数（来自平刷包 dtbo）

DTBO 里就是这块屏的完整定义，三份变体：

```
qcom,mdss_dsi_kirby_nt36523_csot_dsc_vid
qcom,mdss_dsi_kirby_nt36523_boe_dsc_vid
qcom,mdss_dsi_kirby_nt36523_boe_dsc_hyper_vid
```

公共参数（`timing@0` 节点，45 个属性）：

| 项 | 值 |
|---|---|
| 分辨率 | 800 × 2560 **每链路** → 双 DSI 合成 **1600 × 2560** |
| 前后廊 | H: 283 / 54 / 20　V: 30 / 256 / 4 |
| 帧率 | 120 Hz（设备上限 165 Hz，HDR，峰值 420 nit） |
| 时钟 | 0x2CA04160 ≈ 748.7 MHz |
| DSC | 开，slice 800×20，2 slice/pkt，8bpc / 8bpp，block prediction |
| 初始化码 | on-command 470 B / off-command 106 B |

> 实机 `ro.vendor.display.paneltype = 1`，屏幕 1600×2560、支持 30/60/90/120/144/165 Hz，与上表一致。

**跨固件版本复核（2026-10-26）**：手头三份不同的平刷包
（`TB321FU_ZUX_1.5.10.184`、`TB321FU_ZUI_16.1.10.027`、`E:\123pan\Downloads\images` 2026-01）
里的 `dtbo` 全部包含同样三个 kirby 面板节点，参数逐字段一致（800×2560、120 Hz）。
也就是说，**这份 XML 不依赖固件版本**，不必为每个 ZUI 版本重做。

## 3. 已经做了什么

`tools/make_panel_xml.py`（在 `Y700/tools/`）把 DTBO 面板节点转成 oplus DisplayDxe 要的 XML 格式，
产出三份文件到 `Binaries/kirby/RawFiles/`：

```
Panel_kirby_nt36523_csot_dsc_vid.xml         120 行，50 条初始化命令
Panel_kirby_nt36523_boe_dsc_vid.xml          117 行，47 条
Panel_kirby_nt36523_boe_dsc_hyper_vid.xml    117 行，47 条
```

转换器的 DSI 命令帧解析是**严格校验**的：470 字节必须正好解析出 50 条、
106 字节正好 12 条，否则报错退出，不会静默产出半截序列。这一步通过了。

## 4. **仍然没解决的关键一环**

驱动怎么选中面板，目前无法从二进制里确定：

- 候选一：按设备树里的节点名匹配（驱动内嵌了 18 个名字的列表）
- 候选二：按 `RawFiles/` 里的 XML 文件名匹配

而我们的 `Resources/DTBs/kirby.dtb` 是 **Linux 主线风格**的树，面板节点是：

```
soc@0/display-subsystem@ae00000/dsi@ae94000/panel@0
  compatible = lenovo,tb321fu-kirby-nt36523-csot-dsc-vid
```

**没有 `qcom,mdss_dsi_*` 这样的节点名**，两种匹配方式都可能落空。

## 5. 两条路

### A. 先按现状出一版，跑一次看（推荐先做）

成本最低。oplus 驱动在找不到面板时会退到内置的 `VirtioDSI 640×480` 兜底模式 ——
如果 DSI PHY 能锁上，哪怕画面是拉伸的，也足够看到 BDS 菜单，Phase 1 就算过。

黑屏的话至少能确定问题在这一层，再走 B。

### B. 把面板节点注入 DTB / 借用已知面板名

需要写一个 FDT 写入工具，把 DTBO 里那份 `qcom,mdss_dsi_kirby_nt36523_csot_dsc_vid`
挂到 `kirby.dtb` 的 `mdss_mdp@ae00000` 下（带 `qcom,mdss-dsi-display-timings/timing@0`）。

或者更省事的变通：把我们生成的 XML **改名成驱动编译期已知的某个面板名**
（例如 `Panel_csot_nt36532_2120_3000_dual_dsc_144hz_vid.xml`）并覆盖其内容，
再让 DTB 里出现对应的节点名。这是 hack，但在没有源码时是可接受的推进方式。

## 6. 未验证项（不要当成已知）

- `DSILanes = 4`（每链路）是按常规填的，DTBO 参数里没有直接给出
- `DSIDSCProfileID = 0x14` 沿用 caihong，未按 kirby 的 bpp/bpc 复核
- `DSIRefreshRate` 编码不确定（caihong 的 XML 里 144 Hz 面板写的是 `0x3C0000`，即 60<<16）
- 面板供电时序（iovdd / enp / enn）在 XML 里没有对应字段，由 DTB 或驱动默认处理
