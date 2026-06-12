#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕工具 Pro 3.0
================
SRT 字幕处理工具（macOS 原生菜单栏版）

功能：
  - SRT ⇄ CSV 双向转换
  - 全程支持 UTF-8-SIG（带 BOM，Excel 直接打开中文不乱码）
  - 合并：文件 A 的时间轴 + 文件 B 的字幕文本 → 新 SRT
  - 原生 Mac 菜单栏（File / Tools / Help）
  - 内置预览表格，可直接双击编辑字幕文本

运行：python3 subtitle_tool.py
打包：见同目录 build_mac.sh
"""

import csv
import io
import os
import re
import sys
import platform
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "字幕工具 Pro 3.0"
APP_VERSION = "3.0.0"

# ----------------------------------------------------------------------
# 核心逻辑（与 GUI 解耦，便于测试）
# ----------------------------------------------------------------------

TIME_RE = re.compile(
    r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
)

ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "gb18030", "big5", "cp950"]


class Cue:
    """一条字幕：序号、开始、结束、文本"""

    __slots__ = ("index", "start", "end", "text")

    def __init__(self, index, start, end, text):
        self.index = index
        self.start = start  # 毫秒 (int)
        self.end = end      # 毫秒 (int)
        self.text = text    # 多行用 \n 分隔


def ms_to_srt_time(ms):
    """毫秒 → '00:01:23,456'"""
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def srt_time_to_ms(h, m, s, milli):
    milli = str(milli).ljust(3, "0")  # 处理 '5' → '500'
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(milli)


def _text_quality_score(text):
    """给解码结果打分：正常字符加分，乱码特征扣分。"""
    if not text:
        return 0.0
    good = 0
    bad = 0
    for ch in text:
        cp = ord(ch)
        if cp < 128:                              # ASCII（数字、时间轴、标点）
            good += 1
        elif 0x4E00 <= cp <= 0x9FFF:              # CJK 统一汉字
            good += 2
        elif 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF:  # 中文标点/全角
            good += 1
        elif 0xE000 <= cp <= 0xF8FF or ch == "\ufffd":          # 私用区/替换符 = 乱码
            bad += 5
        elif 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2FFFF:  # 生僻扩展区,正常文本罕见
            bad += 2
    return (good - bad) / max(1, len(text))


def read_text_auto(path):
    """自动识别编码读取文本文件，返回 (内容, 实际编码)。
    对每个候选编码解码并评分，选出最像正常中文/字幕的结果。"""
    raw = open(path, "rb").read()
    # UTF-16 只在有 BOM 时识别（否则任意字节都能"成功"解码造成误判）
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except (UnicodeDecodeError, UnicodeError):
            pass
    # UTF-8 系列能成功解码即基本可信（其字节结构有校验性）
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except (UnicodeDecodeError, UnicodeError):
            pass
    try:
        return raw.decode("utf-8"), "utf-8"
    except (UnicodeDecodeError, UnicodeError):
        pass
    # 传统编码：解码后评分取最优
    best = None
    for enc in ("gb18030", "big5", "cp950"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
        score = _text_quality_score(text)
        if best is None or score > best[2]:
            best = (text, enc, score)
    if best:
        return best[0], best[1]
    # 最后兜底：忽略错误
    return raw.decode("utf-8", errors="replace"), "utf-8 (有替换字符)"


def parse_srt(content):
    """解析 SRT 文本 → list[Cue]。容错处理：缺序号、空行不规范等。"""
    # 统一换行
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    blocks = re.split(r"\n\s*\n", content.strip())
    counter = 0
    for block in blocks:
        lines = [ln for ln in block.split("\n")]
        # 找到时间行
        time_line_idx = None
        for i, ln in enumerate(lines):
            if TIME_RE.search(ln):
                time_line_idx = i
                break
        if time_line_idx is None:
            continue
        m = TIME_RE.search(lines[time_line_idx])
        start = srt_time_to_ms(m.group(1), m.group(2), m.group(3), m.group(4))
        end = srt_time_to_ms(m.group(5), m.group(6), m.group(7), m.group(8))
        text = "\n".join(lines[time_line_idx + 1:]).strip()
        counter += 1
        cues.append(Cue(counter, start, end, text))
    return cues


def cues_to_srt(cues):
    """list[Cue] → SRT 文本（自动重新编号）"""
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{ms_to_srt_time(c.start)} --> {ms_to_srt_time(c.end)}")
        out.append(c.text)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


CSV_HEADERS = ["序号", "开始时间", "结束时间", "字幕内容"]


def cues_to_csv_text(cues):
    """list[Cue] → CSV 文本（不含 BOM；写文件时由编码参数决定）"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for i, c in enumerate(cues, 1):
        writer.writerow([i, ms_to_srt_time(c.start), ms_to_srt_time(c.end), c.text])
    return buf.getvalue()


def parse_csv(content):
    """CSV 文本 → list[Cue]。
    兼容：有/无表头；列顺序固定为 序号,开始,结束,文本。"""
    reader = csv.reader(io.StringIO(content))
    cues = []
    counter = 0
    for row in reader:
        if len(row) < 4:
            continue
        # 跳过表头
        if not TIME_RE.search(f"{row[1]} --> {row[2]}"):
            continue
        m = TIME_RE.search(f"{row[1]} --> {row[2]}")
        start = srt_time_to_ms(m.group(1), m.group(2), m.group(3), m.group(4))
        end = srt_time_to_ms(m.group(5), m.group(6), m.group(7), m.group(8))
        counter += 1
        cues.append(Cue(counter, start, end, row[3]))
    return cues


def merge_timeline_and_text(cues_a, cues_b):
    """文件 A 的时间轴 + 文件 B 的字幕文本 → 新 cues。
    按序号一一对应；条数不同时取较小值，返回 (merged, warning)。"""
    n = min(len(cues_a), len(cues_b))
    merged = [Cue(i + 1, cues_a[i].start, cues_a[i].end, cues_b[i].text) for i in range(n)]
    warning = None
    if len(cues_a) != len(cues_b):
        warning = (
            f"两个文件条数不一致：时间轴文件 A 有 {len(cues_a)} 条，"
            f"字幕文件 B 有 {len(cues_b)} 条。\n已按前 {n} 条合并，请检查结果。"
        )
    return merged, warning


def write_text(path, content, use_bom=True):
    enc = "utf-8-sig" if use_bom else "utf-8"
    with open(path, "w", encoding=enc, newline="") as f:
        f.write(content)
    return enc


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------

class SubtitleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x640")
        self.minsize(760, 480)

        self.cues = []           # 当前加载的字幕
        self.source_path = None  # 当前文件路径
        self.use_bom = tk.BooleanVar(value=True)  # UTF-8-SIG 开关

        self.is_mac = platform.system() == "Darwin"
        self._build_menubar()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self._bind_shortcuts()

    # ---------------- 菜单栏（macOS 下显示在屏幕顶部系统菜单栏） ----------------
    def _build_menubar(self):
        menubar = tk.Menu(self)
        mod = "Command" if self.is_mac else "Control"

        # macOS 应用菜单（关于）
        if self.is_mac:
            app_menu = tk.Menu(menubar, name="apple")
            app_menu.add_command(label=f"关于 {APP_NAME}", command=self.show_about)
            app_menu.add_separator()
            menubar.add_cascade(menu=app_menu)
            self.createcommand("tk::mac::Quit", self.quit_app)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开 SRT…", accelerator=f"{mod}+O",
                              command=self.open_srt)
        file_menu.add_command(label="打开 CSV…", accelerator=f"{mod}+Shift+O",
                              command=self.open_csv)
        file_menu.add_separator()
        file_menu.add_command(label="导出为 CSV…", accelerator=f"{mod}+E",
                              command=self.export_csv)
        file_menu.add_command(label="导出为 SRT…", accelerator=f"{mod}+S",
                              command=self.export_srt)
        file_menu.add_separator()
        file_menu.add_checkbutton(label="使用 UTF-8-SIG（带 BOM）导出",
                                  variable=self.use_bom)
        if not self.is_mac:
            file_menu.add_separator()
            file_menu.add_command(label="退出", command=self.quit_app)
        menubar.add_cascade(label="文件", menu=file_menu)

        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="合并：A 时间轴 + B 字幕…", accelerator=f"{mod}+M",
                               command=self.merge_files)
        tools_menu.add_separator()
        tools_menu.add_command(label="重新编号", command=self.renumber)
        tools_menu.add_command(label="清空列表", command=self.clear_all)
        menubar.add_cascade(label="工具", menu=tools_menu)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0, name="help" if self.is_mac else None)
        help_menu.add_command(label="使用说明", command=self.show_help)
        if not self.is_mac:
            help_menu.add_command(label=f"关于 {APP_NAME}", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.config(menu=menubar)

    def _bind_shortcuts(self):
        mod = "Command" if self.is_mac else "Control"
        self.bind(f"<{mod}-o>", lambda e: self.open_srt())
        self.bind(f"<{mod}-O>", lambda e: self.open_csv())
        self.bind(f"<{mod}-e>", lambda e: self.export_csv())
        self.bind(f"<{mod}-s>", lambda e: self.export_srt())
        self.bind(f"<{mod}-m>", lambda e: self.merge_files())

    # ---------------- 工具栏 ----------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")

        ttk.Button(bar, text="打开 SRT", command=self.open_srt).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="打开 CSV", command=self.open_csv).pack(side="left", padx=(0, 14))
        ttk.Button(bar, text="导出 CSV", command=self.export_csv).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="导出 SRT", command=self.export_srt).pack(side="left", padx=(0, 14))
        ttk.Button(bar, text="合并 A+B", command=self.merge_files).pack(side="left")

        ttk.Checkbutton(bar, text="UTF-8-SIG (BOM)", variable=self.use_bom).pack(side="right")

    # ---------------- 表格 ----------------
    def _build_table(self):
        frame = ttk.Frame(self, padding=(10, 0, 10, 0))
        frame.pack(fill="both", expand=True)

        cols = ("idx", "start", "end", "text")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("idx", text="序号")
        self.tree.heading("start", text="开始时间")
        self.tree.heading("end", text="结束时间")
        self.tree.heading("text", text="字幕内容（双击编辑）")
        self.tree.column("idx", width=60, anchor="center", stretch=False)
        self.tree.column("start", width=120, anchor="center", stretch=False)
        self.tree.column("end", width=120, anchor="center", stretch=False)
        self.tree.column("text", width=600, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.edit_cell)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="就绪 — 打开一个 SRT 或 CSV 文件开始")
        ttk.Label(self, textvariable=self.status, padding=(12, 6),
                  relief="flat", anchor="w").pack(fill="x", side="bottom")

    # ---------------- 表格刷新与编辑 ----------------
    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(self.cues, 1):
            display_text = c.text.replace("\n", " ⏎ ")
            self.tree.insert("", "end", iid=str(i - 1),
                             values=(i, ms_to_srt_time(c.start),
                                     ms_to_srt_time(c.end), display_text))

    def edit_cell(self, event):
        """双击字幕内容列 → 弹出编辑框"""
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#4":
            return
        idx = int(item)
        cue = self.cues[idx]

        win = tk.Toplevel(self)
        win.title(f"编辑第 {idx + 1} 条字幕")
        win.geometry("520x220")
        win.transient(self)

        txt = tk.Text(win, wrap="word", font=("Helvetica", 14))
        txt.insert("1.0", cue.text)
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        def save():
            cue.text = txt.get("1.0", "end").rstrip("\n")
            self.refresh_table()
            win.destroy()

        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text="保存", command=save).pack(side="right")
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="right", padx=8)
        txt.focus_set()

    # ---------------- 文件操作 ----------------
    def open_srt(self):
        path = filedialog.askopenfilename(
            title="打开 SRT 文件",
            filetypes=[("SRT 字幕", "*.srt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            content, enc = read_text_auto(path)
            self.cues = parse_srt(content)
            self.source_path = path
            self.refresh_table()
            self.status.set(
                f"已加载 {os.path.basename(path)} — {len(self.cues)} 条字幕（编码：{enc}）")
        except Exception as e:
            messagebox.showerror("打开失败", f"无法解析 SRT 文件：\n{e}")

    def open_csv(self):
        path = filedialog.askopenfilename(
            title="打开 CSV 文件",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            content, enc = read_text_auto(path)
            self.cues = parse_csv(content)
            self.source_path = path
            self.refresh_table()
            self.status.set(
                f"已加载 {os.path.basename(path)} — {len(self.cues)} 条字幕（编码：{enc}）")
        except Exception as e:
            messagebox.showerror("打开失败", f"无法解析 CSV 文件：\n{e}")

    def _default_name(self, ext):
        if self.source_path:
            base = os.path.splitext(os.path.basename(self.source_path))[0]
            return base + ext
        return "subtitles" + ext

    def export_csv(self):
        if not self.cues:
            messagebox.showinfo("没有数据", "请先打开一个 SRT 或 CSV 文件。")
            return
        path = filedialog.asksaveasfilename(
            title="导出为 CSV", defaultextension=".csv",
            initialfile=self._default_name(".csv"),
            filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        enc = write_text(path, cues_to_csv_text(self.cues), self.use_bom.get())
        self.status.set(f"已导出 CSV：{os.path.basename(path)}（{enc}，{len(self.cues)} 条）")

    def export_srt(self):
        if not self.cues:
            messagebox.showinfo("没有数据", "请先打开一个 SRT 或 CSV 文件。")
            return
        path = filedialog.asksaveasfilename(
            title="导出为 SRT", defaultextension=".srt",
            initialfile=self._default_name(".srt"),
            filetypes=[("SRT 字幕", "*.srt")])
        if not path:
            return
        enc = write_text(path, cues_to_srt(self.cues), self.use_bom.get())
        self.status.set(f"已导出 SRT：{os.path.basename(path)}（{enc}，{len(self.cues)} 条）")

    # ---------------- 合并 ----------------
    def merge_files(self):
        path_a = filedialog.askopenfilename(
            title="第 1 步：选择文件 A（提供时间轴）",
            filetypes=[("字幕/CSV", "*.srt *.csv"), ("所有文件", "*.*")])
        if not path_a:
            return
        path_b = filedialog.askopenfilename(
            title="第 2 步：选择文件 B（提供字幕文本）",
            filetypes=[("字幕/CSV", "*.srt *.csv"), ("所有文件", "*.*")])
        if not path_b:
            return
        try:
            cues_a = self._load_any(path_a)
            cues_b = self._load_any(path_b)
            merged, warning = merge_timeline_and_text(cues_a, cues_b)
            if warning:
                messagebox.showwarning("条数不一致", warning)
            self.cues = merged
            self.source_path = path_b  # 导出默认名跟随字幕文件
            self.refresh_table()
            self.status.set(
                f"合并完成：{os.path.basename(path_a)} 的时间轴 + "
                f"{os.path.basename(path_b)} 的字幕，共 {len(merged)} 条。请导出保存。")
        except Exception as e:
            messagebox.showerror("合并失败", str(e))

    @staticmethod
    def _load_any(path):
        content, _ = read_text_auto(path)
        if path.lower().endswith(".csv"):
            return parse_csv(content)
        return parse_srt(content)

    # ---------------- 其他 ----------------
    def renumber(self):
        for i, c in enumerate(self.cues, 1):
            c.index = i
        self.refresh_table()
        self.status.set("已重新编号。")

    def clear_all(self):
        self.cues = []
        self.source_path = None
        self.refresh_table()
        self.status.set("已清空。")

    def show_about(self):
        messagebox.showinfo(
            f"关于 {APP_NAME}",
            f"{APP_NAME}\n版本 {APP_VERSION}\n\n"
            "SRT ⇄ CSV 转换 · UTF-8-SIG · 时间轴合并\n"
            "为字幕校对与手动调整工作流设计")

    def show_help(self):
        messagebox.showinfo(
            "使用说明",
            "1. SRT → CSV：打开 SRT，点击「导出 CSV」。\n"
            "   CSV 默认 UTF-8-SIG 编码，Excel 直接打开不乱码。\n\n"
            "2. CSV → SRT：在 Excel/Numbers 中改完字幕后，\n"
            "   打开 CSV，点击「导出 SRT」。\n\n"
            "3. 合并：点击「合并 A+B」，先选时间轴来源（A），\n"
            "   再选字幕文本来源（B），按序号一一对应。\n"
            "   典型用途：修正后的繁体字幕 + 原始时间轴。\n\n"
            "4. 双击表格中的字幕内容可直接编辑。")

    def quit_app(self):
        self.destroy()


def main():
    app = SubtitleApp()
    app.mainloop()


if __name__ == "__main__":
    main()
