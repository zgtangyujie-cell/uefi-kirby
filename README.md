# uefi-kirby

联想拯救者 Y700 三代（**TB321FU** / bootloader 代号 **kirby** / SM8650 `pineapple`）的 UEFI 固件工程，基于 [Project-Silicium / Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium)。

由 `uefi-caihong`（一加平板 Pro，同为 SM8650）改名而来。目标产物 `Mu-kirby-0.img`，用 `fastboot boot` 内存启动，不写分区。

## 状态（2026-10-26）

| 项 | 状态 |
|---|---|
| 设备仓库结构 | ✅ 已搭好（`Platforms/Lenovo/kirbyPkg`、`Binaries/kirby`、`Resources`） |
| 板级 DTB | ✅ 已就位（`Resources/DTBs/kirby.dtb`，1259 节点，来自社区 Linux 移植，model = `Lenovo Legion Y700 (2025) / TB321FU`） |
| FD 基址 / 尺寸 | ✅ `0xA7100000` / `0x400000`（已用社区固件实测反推，与 caihong 同值） |
| 厂商 DXE 驱动 | ⚠️ 暂用 SM8650 通用集（源自 Device-Binaries），`DisplayDxe.efi` 内仍带 caihong 面板绑定 |
| **MemoryMapLib** | ❌ **仍是 caihong 的内存图，必须按 kirby 实机重写**（最大风险项） |
| CI 构建 | ❌ 未跑过 |
| 真机验证 | ❌ **没有任何 kirby 实机记录，不要当成能用的固件** |

## 关键输入（全部实测）

```
SoC          SM8650 / pineapple
GIC          0x17100000 (dist +0x10000)，redist 0x17180000 (+0x200000，8×0x40000)
Timer        0x17420000
UFS host     0x1d84000（IRQ 265）      PHY 0x1d80000
DSI0 / DSI1  0xae94000 / 0xae96000     MDSS 0xae00000
Panel        lenovo,tb321fu-kirby-nt36523-csot-dsc-vid（CSOT，DSC，video mode，1600×2560）
Touch        novatek,nt36523n-spi @ geni-spi 0xa90000，9.6 MHz，reset GPIO 161，irq 162
FD base      0xA7100000   size 0x400000 (4 MiB)
boot.img     header v4，page 4096，kernel 段 = gzip(BootShim + FV)
```

## 构建

CI（推荐）：

推到 GitHub 后 `build` workflow 自动跑（`workflow_dispatch` 也能手动触发），产物为 `Mu-kirby-RELEASE` artifact。

本地（需要 Linux/macOS + clang/lld/nasm/iasl/dtc）：

```bash
bash ./scripts/build.sh .work RELEASE
```

## 刷入验证

```bash
adb reboot bootloader
fastboot boot Mu-kirby-0.img
```

开机出现 logo 时按一次音量键才会进 BDS 菜单（Mu-Silicium 的既有行为，不按键会走「找不到可启动项」分支并关机）。

**失败不会变砖**：全程内存运行，长按电源即可回 Android。

## 下一步

1. 重写 `Platforms/Lenovo/kirbyPkg/Library/MemoryMapLib/MemoryMapLib.c`：按 kirby 实机内存图
2. 处理 `Binaries/kirby/QcomPkg/Drivers/DisplayDxe/DisplayDxe.efi` 的面板绑定（按 caihong 面板编的）
3. 跑通 CI，产出第一版 `Mu-kirby-0.img`
4. `fastboot boot` 验证能否出 BDS 菜单 → 记为 device-verified

采集与推导过程见 `../PORTING-RECORD.md`。
