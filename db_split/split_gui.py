# -*- coding: utf-8 -*-
"""split_by_key 分拆器（子模块）：主库按"负责人"等键列拆成每人一个文件。

团队轮转的分发环节。全量分拆（含归档）、空值进"未分配.db"、
目标已存在拒绝执行。运行：python -m db_split --gui（或 python db_split/split_gui.py）
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db import Database                       # noqa: E402
from config import CFG                        # noqa: E402
import db_split.split_core as core            # noqa: E402


class SplitApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("按键分拆器 v1.0.0")
        self.geometry("620x420")
        self.db = None
        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        frm = tk.Frame(self, padx=6, pady=6)
        frm.pack(fill="both", expand=True)
        r0 = tk.Frame(frm); r0.pack(fill="x", **pad)
        tk.Label(r0, text="源库：", width=8, anchor="e").pack(side="left")
        self.src_var = tk.StringVar()
        tk.Entry(r0, textvariable=self.src_var).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Button(r0, text="浏览", command=self._pick_src).pack(side="left")
        tk.Button(r0, text="加载", command=self._load).pack(
            side="left", padx=4)

        r1 = tk.Frame(frm); r1.pack(fill="x", **pad)
        tk.Label(r1, text="键列：", width=8, anchor="e").pack(side="left")
        self.key_var = tk.StringVar()
        self.key_box = ttk.Combobox(r1, textvariable=self.key_var,
                                    state="readonly", width=20)
        self.key_box.pack(side="left", padx=4)
        tk.Button(r1, text="预览", command=self._preview).pack(
            side="left", padx=6)

        r2 = tk.Frame(frm); r2.pack(fill="x", **pad)
        tk.Label(r2, text="输出目录：", width=8, anchor="e").pack(side="left")
        self.dir_var = tk.StringVar()
        tk.Entry(r2, textvariable=self.dir_var).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Button(r2, text="浏览", command=self._pick_dir).pack(side="left")

        self.preview_box = tk.Listbox(frm, font=("", 11))
        self.preview_box.pack(fill="both", expand=True, padx=10, pady=4)

        r3 = tk.Frame(frm); r3.pack(fill="x", **pad)
        tk.Button(r3, text="执行分拆", bg="#2e7d32", fg="white",
                  font=("", 12), padx=14, pady=5,
                  command=self._run).pack(side="left", padx=4)
        self.stat = tk.Label(r3, text="全量分拆（含归档）｜空值→未分配.db"
                                    "｜目标已存在则拒绝", fg="#666666")
        self.stat.pack(side="left", padx=8)

    def _pick_src(self):
        p = filedialog.askopenfilename(
            parent=self,
            filetypes=[("SQLite 数据库", "*.db"), ("所有", "*.*")])
        if p:
            self.src_var.set(p)

    def _pick_dir(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            self.dir_var.set(d)

    def _load(self):
        p = self.src_var.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning("提示", "请选择源库", parent=self)
            return
        try:
            self.db = Database(p)
        except Exception as e:                          # noqa: BLE001
            messagebox.showerror("打开失败", str(e), parent=self)
            return
        keys = [c for c, _h in CFG.display_cols if c != "id"]
        self.key_box.configure(values=[CFG.labels.get(c, c) for c in keys])
        if keys:
            self.key_box.current(0)
        self.stat.config(text="源库已加载，选键列后点「预览」")

    def _key_field(self):
        label = self.key_var.get()
        return next((c for c, _h in CFG.display_cols
                     if c != "id" and CFG.labels.get(c, c) == label), None)

    def _preview(self):
        if self.db is None or self._key_field() is None:
            return
        from datetime import datetime
        counts = core.preview(self.db, self._key_field())
        label = self.key_var.get()
        sample_t = datetime(2000, 1, 1, 0, 0, 0)
        self.preview_box.delete(0, "end")
        for k, n in counts.items():
            fname = core.build_filename(k, label, when=sample_t)
            self.preview_box.insert("end", f"{fname}：{n} 个项目")
        self.stat.config(text=f"将生成 {len(counts)} 个文件（时间以执行时为准）")

    def _run(self):
        if self.db is None:
            return
        field = self._key_field()
        dest = self.dir_var.get().strip()
        if field is None or not dest:
            messagebox.showwarning("提示", "请选择键列和输出目录",
                                   parent=self)
            return
        try:
            counts = core.preview(self.db, field)
        except Exception as e:                            # noqa: BLE001
            messagebox.showerror("错误", str(e), parent=self)
            return
        if not messagebox.askyesno(
                "确认分拆",
                f"将把源库全部 {sum(counts.values())} 个项目按「"
                f"{self.key_var.get()}」拆为 {len(counts)} 个文件：\n"
                + "\n".join(f"  {(k or '未分配')}：{n} 个"
                            for k, n in counts.items())
                + "\n\n文件名 = 列名_键值_时间（JSON 的 split 段可改）。"
                  "\n目标已存在则中止。继续？",
                parent=self):
            return
        try:
            result = core.split_by_key(self.db, dest, field)
        except FileExistsError as e:
            messagebox.showerror("已存在，中止", str(e), parent=self)
            return
        except Exception as e:                            # noqa: BLE001
            messagebox.showerror("分拆失败", str(e), parent=self)
            return
        msg = "\n".join(f"{f}：{p} 项目 / {s} 快照" for f, (p, s)
                        in result.items())
        self.stat.config(text=f"完成：{len(result)} 个文件 ✓")
        messagebox.showinfo("完成", msg, parent=self)


def run_gui():
    SplitApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run_gui())
