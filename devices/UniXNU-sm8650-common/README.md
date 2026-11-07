# UniXNU-sm8650-common

Qualcomm **SM8650**（pineapple / kirby）的共享 SoC 层。

## 状态

第 0 阶段：骨架。只包含 CPU 拓扑、PSCI、GICv3、UFS 控制器与 GMU 节点，
全部 `status = "disabled"`，用于先把 `./unixnu fetch` 和 DT 编译跑通。

## 数据来源

| 项 | 来源 |
|---|---|
| CPU 拓扑与频率 | 本机 `/sys/devices/system/cpu/cpu*/cpu_capacity` + `cpuinfo_max_freq` |
| GIC 基址 | `/proc/device-tree/soc/interrupt-controller@17100000` |
| UFS HC / PHY | `/proc/device-tree/soc/ufshc@1d84000`、`ufsphy_mem@1d80000` |
| GMU 基址 | `/proc/device-tree/soc/qcom,gmu@3d69000` |

## 与 SM8550 的差异

- CPU：A510/A715/A710/X3 → **A520/A720/X4**
- GMU：`0x3d6a000` → **`0x3d69000`**
- GPU：Adreno 740 → **Adreno 750**（组件表暂无对应组件）

## 待办

- [ ] 固定 upstream `source_revision`
- [ ] 补 GPU 组件（Adreno 750）
- [ ] RTC / 串口 / 时钟控制器节点
- [ ] SM8650 专属 XNU 补丁
