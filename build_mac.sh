#!/bin/bash
# ============================================
#  字幕工具 Pro 3.0 — Mac 一键打包脚本
#  在 Mac 终端中运行：bash build_mac.sh
#  完成后 .app 在 dist/ 文件夹中
# ============================================
set -e

echo "==> 检查 Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "未找到 python3。请先安装：https://www.python.org/downloads/macos/"
    exit 1
fi
python3 --version

echo "==> 检查 tkinter..."
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "当前 Python 缺少 tkinter。"
    echo "建议从 python.org 官网安装 Python（自带 tkinter），"
    echo "或用 Homebrew：brew install python-tk"
    exit 1
fi

echo "==> 安装 PyInstaller（如已安装会跳过）..."
python3 -m pip install --quiet --upgrade pyinstaller

echo "==> 开始打包..."
python3 -m PyInstaller \
    --windowed \
    --noconfirm \
    --clean \
    --name "字幕工具 Pro 3.0" \
    --osx-bundle-identifier "com.pharmatalkstudio.subtitletool" \
    subtitle_tool.py

echo ""
echo "✅ 打包完成！"
echo "应用位置：dist/字幕工具 Pro 3.0.app"
echo ""
echo "可以直接双击运行，或拖入 /Applications 文件夹。"
echo "首次打开如提示「无法验证开发者」，请右键点击应用 → 打开，"
echo "或在 系统设置 → 隐私与安全性 中点击「仍要打开」。"
