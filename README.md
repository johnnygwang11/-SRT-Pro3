# 字幕工具 Pro 3.0

为字幕校对工作流设计的 macOS 桌面工具。

## 功能

- **SRT ⇄ CSV 双向转换** — 导出 CSV 后可在 Excel / Numbers 中批量编辑字幕，改完再转回 SRT
- **UTF-8-SIG 支持** — 导出默认带 BOM，Excel 直接打开中文不乱码；读取时自动识别 UTF-8 / UTF-8-SIG / UTF-16 / GB18030 / Big5 等编码
- **时间轴合并** — 文件 A 提供时间轴 + 文件 B 提供字幕文本，按序号一一对应生成新 SRT（典型用途：修正后的繁体字幕套回原始时间轴，时间戳零改动）
- **原生 Mac 菜单栏** — 文件 / 工具 / 帮助菜单显示在屏幕顶部系统菜单栏，支持 ⌘O ⌘E ⌘S ⌘M 快捷键
- **内置预览表格** — 双击任意一条字幕可直接编辑文本

## 两种使用方式

### 方式一：直接运行（最快，30 秒上手）

需要 Mac 上装有 Python 3（[python.org 官网版](https://www.python.org/downloads/macos/)自带图形库）。

```bash
python3 subtitle_tool.py
```

### 方式二：打包成独立 .app（一次打包，永久双击使用）

在终端中进入本文件夹，运行：

```bash
bash build_mac.sh
```

完成后 `dist/字幕工具 Pro 3.0.app` 就是独立应用，可拖入"应用程序"文件夹。

> 首次打开如提示"无法验证开发者"：右键点击应用 → 打开，或到
> 系统设置 → 隐私与安全性 → 点击"仍要打开"。这是因为应用未经
> Apple 付费签名，属正常现象。

## 典型工作流示例

**校对字幕（保持时间轴不动）：**

1. 打开原始 SRT → 导出 CSV
2. 在 Excel 中修改字幕列（转繁体、改错字）
3. 工具 → 合并：A 选原始 SRT（时间轴），B 选改好的 CSV（文本）
4. 导出 SRT — 时间戳与原文件完全一致

**注意：** 合并按"序号一一对应"，所以编辑时不要增删行。如果两个文件条数不同，软件会警告并按较短的合并。

## 自动构建（GitHub Actions）

本仓库内置自动打包流程（`.github/workflows/build.yml`）。推送版本标签即可触发 GitHub 在 macOS 云端机器上自动构建 `.app` 并发布到 Releases：

```bash
git tag v3.0.0
git push origin v3.0.0
```

几分钟后，仓库的 Releases 页面会出现 `字幕工具Pro-macOS.zip`，下载解压即得 `.app`。也可以在 Actions 页面手动触发构建。

## 文件清单

| 文件 | 说明 |
|---|---|
| `subtitle_tool.py` | 主程序（单文件，无第三方依赖） |
| `build_mac.sh` | Mac 本地一键打包脚本 |
| `.github/workflows/build.yml` | GitHub Actions 自动打包配置 |
| `LICENSE` | MIT 开源协议 |
| `README.md` | 本说明 |
