# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""多库追加器（子模块）：多个源库依次全部追加进目标库。

从包根目录共享 db/config/fields.json —— 本目录不携带任何配置。
运行：python db_append/append_gui.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Database                       # noqa: E402
import append_core as core                     # noqa: E402


class AppendApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("多库追加器 v1.0.0")
        self.geometry("820x620")
        self._build()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        # 目标库
        top = tk.Frame(self)
        top.pack(fill="x", **pad)
        tk.Label(top, text="目标库（合并进这里）：").pack(side="left")
        self.path_t = tk.StringVar()
        tk.Entry(top, textvariable=self.path_t).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Button(top, text="浏览",
                  command=lambda: self._pick(self.path_t)).pack(side="left")

        # 源库列表
        mid = tk.LabelFrame(self, text="源库（依次全部追加；可多个）",
                            padx=6, pady=6)
        mid.pack(fill="both", expand=True, **pad)
        self.src_list = tk.Listbox(mid, font=("", 11))
        self.src_list.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(mid, orient="vertical",
                          command=self.src_list.yview)
        self.src_list.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        btns = tk.Frame(mid)
        btns.pack(side="left", fill="y", padx=8)
        tk.Button(btns, text="添加源库",
                  command=self._add_src).pack(fill="x", pady=4)
        tk.Button(btns, text="移除选中",
                  command=self._remove_src).pack(fill="x", pady=4)
        tk.Button(btns, text="预览",
                  command=self._preview).pack(fill="x", pady=4)
        tk.Button(btns, text="全部追加 ➡ 目标库", bg="#2e7d32", fg="white",
                  command=self._append).pack(fill="x", pady=(16, 4))

        # 日志
        self.log = tk.Text(self, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

    # ---------- 工具 ----------
    def _say(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pick(self, var):
        p = filedialog.askopenfilename(
            parent=self,
            filetypes=[("SQLite 数据库", "*.db"), ("所有", "*.*")])
        if p:
            var.set(p)

    def _add_src(self):
        ps = filedialog.askopenfilenames(
            parent=self,
            filetypes=[("SQLite 数据库", "*.db"), ("所有", "*.*")])
        for p in ps:
            if p and p not in self.src_list.get(0, "end"):
                self.src_list.insert("end", p)

    def _remove_src(self):
        for i in reversed(self.src_list.curselection()):
            self.src_list.delete(i)

    def _open_dbs(self):
        """打开目标+所有源库，做基础校验。失败返回 None。"""
        pt = self.path_t.get().strip()
        srcs = list(self.src_list.get(0, "end"))
        if not pt:
            messagebox.showwarning("提示", "请先选择目标库", parent=self)
            return None
        if not srcs:
            messagebox.showwarning("提示", "请至少添加一个源库", parent=self)
            return None
        try:
            t = Database(pt)
            dbs = []
            for p in srcs:
                if os.path.abspath(p) == os.path.abspath(pt):
                    messagebox.showwarning(
                        "提示", f"源库与目标库是同一个文件：\n{p}", parent=self)
                    return None
                d = Database(p)
                ok, msg = core.check_compatible(d, t)
                if not ok:
                    messagebox.showerror("配置不一致", f"{p}\n{msg}",
                                         parent=self)
                    return None
                dbs.append(d)
            return t, dbs
        except Exception as e:                          # noqa: BLE001
            messagebox.showerror("打开失败", str(e), parent=self)
            return None

    def _preview(self):
        opened = self._open_dbs()
        if not opened:
            return
        t, dbs = opened
        self._say("—— 预览 ——")
        for d, p in zip(dbs, self.src_list.get(0, "end")):
            rows = core.list_projects(d)
            ns = sum(r["snap_count"] for r in rows)
            self._say(f"  {os.path.basename(p)}：{len(rows)} 个项目，"
                      f"共 {ns} 条快照将追加")
        self._say(f"目标库现有 {len(core.list_projects(t))} 个项目"
                  f"（不会被修改/删除）")
        for d in dbs:
            d.close()
        t.close()

    def _append(self):
        opened = self._open_dbs()
        if not opened:
            return
        t, dbs = opened
        n_src = len(dbs)
        if not messagebox.askyesno(
                "确认追加",
                f"将把 {n_src} 个源库的全部项目（含历史快照）\n"
                f"依次追加到目标库。\n\n"
                f"目标库已有数据不会被修改或删除；\n"
                f"重复执行会产生重复项目（追加语义）。继续？",
                parent=self):
            for d in dbs:
                d.close()
            t.close()
            return
        self._say("—— 开始追加 ——")
        try:
            np_, ns, details = core.append_sources(t, dbs)
        except Exception as e:                          # noqa: BLE001
            messagebox.showerror("合并失败", str(e), parent=self)
            self._say(f"中断：{e}")
            return
        for name, p, s in details:
            self._say(f"  {name}：+{p} 项目 / +{s} 快照")
        self._say(f"✅ 合计追加 {np_} 个项目、{ns} 条快照。"
                  f"目标库现共 {len(core.list_projects(t))} 个项目。")
        for d in dbs:
            d.close()
        t.close()


if __name__ == "__main__":
    AppendApp().mainloop()
