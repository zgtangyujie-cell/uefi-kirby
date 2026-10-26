# 首次构建清单

## 目的

把 `Mu-kirby-0.img` 编出来，`fastboot boot` 试一次，确认 UEFI 能不能在真机上起来。
**不写任何分区**，失败长按电源即可回 Android。

## 推仓库

仓库在本地已经 commit 好了，只差 remote：

```bash
cd "D:/WorkBuddy AI/Y700/work/uefi-kirby"
git remote add origin https://github.com/<你的用户名>/uefi-kirby.git
git push -u origin main
```

推完打开仓库的 **Actions** 页，`build` 会自动跑（也可以手动 `Run workflow`）。

## 这一步会发生什么

1. apt 装 clang / lld / nasm / iasl / dtc / gcc-aarch64
2. `scripts/build.sh` 浅克隆 Mu-Silicium 到固定提交
3. 把 `Platforms/Lenovo/kirbyPkg`、`Resources/Configs/kirby.toml`、`Resources/DTBs/kirby.dtb`、`Binaries/kirby` 拷进去
4. 跑 `apply_binary_patches.py` 给厂商驱动打补丁
5. EDK2 编译（CLANGPDB，AArch64）
6. `build_uefi.py -d kirby -r RELEASE` 打包 → `Mu-kirby-0.img`

预计 10–20 分钟。

## 已做的静态预检（本地）

| 检查 | 结果 |
|---|---|
| `Binaries/kirby/**/*.inf` 里的 PE32 / DEPEX 引用（102 条） | ✅ 全部存在 |
| `kirby.dsc` 引用的文件 | ✅ 0 缺失 |
| `kirby.fdf` 引用的文件 | ✅ 0 缺失（`FdtBlob` 那行是注释） |
| 输出文件名 | ✅ `Mu-kirby-0.img`（因 `[status] model_count = 1` 才带 `-0` 后缀） |
| FV 输出路径 | ✅ `Build/kirbyPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd` |
| 改名残留 | ✅ `caihong` / `oneplus` 0 处（`DisplayDxe.efi` 二进制内除外） |

## 第一次跑，重点看这几处失败

按可能性排序，都写在日志里：

1. **`kirby.dsc` / `kirby.fdf` 里的 APRIORI 或 DXE 列表**
   caihong 的平台包里可能引用了它自己新增、而我们没有的驱动/库。日志会写 `not found` 或 `Module ... not found`。

2. **`apply_binary_patches.py` 的字节校验**
   它按偏移对 caihong 的二进制做 `orig_hex` 比对，不匹配会直接抛错。我们整份复制了 Binaries，理论上一致。

3. **FV 尺寸超限**
   `kirby.toml` 给的是 `0x400000`（4 MiB）。如果 RELEASE 编出来超过，日志会报 FV 溢出；可以把 `[uefi_fd] size` 提到 `0x500000`（分区正好 5 MiB），但要同步确认 `UEFI_FD_Reserved` 的窗口。

4. **`MemoryMapLib` 的新增条目**
   这是唯一被我改过逻辑的文件。如果 EDK2 在初始化阶段报内存描述符相关断言，先怀疑这里。

## 编出来之后

```bash
adb reboot bootloader
fastboot boot Mu-kirby-0.img
```

- 出现 logo 时**按一次音量键**才会进 BDS 菜单（Mu-Silicium 的既有行为，不按会走「找不到可启动项」分支并关机）
- 画面亮 = Phase 1 通过，可以记为 device-verified
- 黑屏 = 显示没点起来，走 `docs/DISPLAY.md` 第 5 节的方案 B
- 完全无反应 / 直接回 Android = BootShim 或 FV 基址问题，回来看 `0xA7100000` 是否被正确加载
