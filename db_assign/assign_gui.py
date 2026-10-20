# -*- coding: utf-8 -*-
"""批量赋值器（子模块）：对**整个库**统一给一列赋值，带只读预览。

设计哲学：克制 + 可预览。
- 作用域永远是"库内全部项目"，无选择、无筛选、无搜索
- 上表 = 现状预览（只读）；下表 = 赋值后预览/执行结果（只读）
- 预览是纯内存模拟，不触碰数据库；执行才写库（每项目一条新快照）

典型场景：JSON 加新列后整库补值；某列全库统一改口径。
运行：python db_assign/assign_gui.py
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
import db_assign.assign_core as core          # noqa: E402


class AssignApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("批量赋值器 v1.2.0")
        self.geometry("720x640")
        self.db = None
        self.rows = []          # [(pid, 项目名, 当前值)]
        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 4}
        top = tk.Frame(self)
        top.pack(fill="x", **pad)
        tk.Label(top, text="数据库：").pack(side="left")
        self.path_var = tk.StringVar()
        tk.Entry(top, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True, padx=4)
        tk.Button(top, text="浏览", command=self._pick).pack(side="left")
        tk.Button(top, text="加载", bg="#1565c0", fg="white",
                  command=self._load).pack(side="left", padx=4)
        self.db_stat = tk.Label(self, text="选择数据库后点「加载」",
                                fg="#666666", anchor="w")
        self.db_stat.pack(fill="x", padx=14)

        mid = tk.Frame(self)
        mid.pack(fill="x", **pad)
        tk.Label(mid, text="赋值列：").pack(side="left")
        self.col_var = tk.StringVar()
        self.col_box = ttk.Combobox(mid, textvariable=self.col_var,
                                    state="readonly", width=20)
        self.col_box.pack(side="left", padx=4)
        self.col_box.bind("<<ComboboxSelected>>",
                          lambda e: self._fill_current())
        tk.Label(mid, text="新值：").pack(side="left", padx=(10, 0))
        self.val_var = tk.StringVar()
        tk.Entry(mid, textvariable=self.val_var, width=22).pack(
            side="left", padx=4)
        tk.Button(mid, text="预览结果", command=self._preview
                  ).pack(side="left", padx=6)
        tk.Button(mid, text="执行赋值", bg="#2e7d32", fg="white",
                  command=self._apply).pack(side="left", padx=4)

        up = tk.LabelFrame(self, text="现状预览（只读）", padx=6, pady=6)
        up.pack(fill="both", expand=True, **pad)
        self.tree_up = self._mk_tree(up)

        low = tk.LabelFrame(self, text="赋值后预览（只读，执行后变为结果）",
                            padx=6, pady=6)
        low.pack(fill="both", expand=True, **pad)
        self.tree_low = self._mk_tree(low)
        lrow = tk.Frame(self)
        lrow.pack(fill="x", padx=10)
        self.limit_lbl = tk.Label(lrow, text="", fg="#8d6e00", anchor="w")
        self.limit_lbl.pack(side="left")
        self.next_btn = tk.Button(lrow, text="下一页 ▼", state="disabled",
                                  command=self._load_more)
        self.next_btn.pack(side="right")
        self.prev_btn = tk.Button(lrow, text="▲ 上一页", state="disabled",
                                  command=self._load_prev)
        self.prev_btn.pack(side="right", padx=4)
        self.offset = 0

        tk.Label(self, text="作用域 = 库内全部项目 ｜ 预览不写库，执行才写"
                            "（每项目一条新快照，历史可对比）",
                 fg="#888888").pack(side="bottom", pady=4)

    def _mk_tree(self, parent):
        tree = ttk.Treeview(parent, show="headings", height=8,
                            selectmode="none")   # 不可选中=不可误操作
        tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        return tree

    # ---------- 数据 ----------
    def _pick(self):
        p = filedialog.askopenfilename(
            parent=self,
            filetypes=[("SQLite 数据库", "*.db"), ("所有", "*.*")])
        if p:
            self.path_var.set(p)

    def _field(self):
        label = self.col_var.get()
        cols = [c for c, _h in CFG.display_cols if c != "id"]
        return next((c for c in cols
                     if CFG.labels.get(c, c) == label), None)

    def _load(self):
        p = self.path_var.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning("提示", "请选择存在的数据库", parent=self)
            return
        try:
            self.db = Database(p)
        except Exception as e:                          # noqa: BLE001
            messagebox.showerror("打开失败", str(e), parent=self)
            return
        # 项目名取 projects.title（与日历同口径），快照行附带给预览用
        self.rows = []
        self.offset = 0
        for pid in core.all_project_ids(self.db):
            cur = self.db.get_current(pid)
            proj = self.db.get_project(pid)
            name = proj["title"]
            self.rows.append((pid, name, cur))
        cols = [c for c, _h in CFG.display_cols if c != "id"]
        self.col_box.configure(values=[CFG.labels.get(c, c) for c in cols])
        if cols:
            self.col_box.current(0)
        self.db_stat.config(
            text=f"{os.path.basename(p)} ｜ 共 {len(self.rows)} 个项目 ｜ "
                 f"赋值将作用于全部")
        self._fill_current()
        self._clear(self.tree_low)

    def _fill_current(self):
        field = self._field()
        if not self.rows:
            return
        label = self.col_var.get() or "列"
        self._setup(self.tree_up, ("项目", f"当前{label}"))
        for _pid, name, cur in self._shown():
            v = cur[field] if (cur is not None and field in cur.keys()) \
                else None
            self.tree_up.insert("", "end",
                                values=(name, "" if v is None else v))
        shown_n = len(self._shown())
        start = self.offset + (1 if shown_n else 0)
        end = self.offset + shown_n
        if len(self.rows) > shown_n or self.offset > 0:
            self.limit_lbl.config(
                text=f"第 {start} ~ {end} 条 / 共 {len(self.rows)} 条")
        else:
            self.limit_lbl.config(text=f"共 {len(self.rows)} 条")
        self.prev_btn.config(state="normal" if self.offset > 0
                             else "disabled")
        self.next_btn.config(state="normal" if end < len(self.rows)
                             else "disabled")

    def _shown(self):
        """当前页的行（翻页式，与主程序共用 ui.render_limit）。"""
        from config import CFG
        return self.rows[self.offset: self.offset + CFG.render_limit]

    def _load_more(self):
        from config import CFG
        self.offset += CFG.render_limit
        self._fill_current()
        if str(self.tree_low.cget("columns")) != "()":
            self._preview()

    def _load_prev(self):
        from config import CFG
        self.offset = max(0, self.offset - CFG.render_limit)
        self._fill_current()
        if str(self.tree_low.cget("columns")) != "()":
            self._preview()

    def _preview(self):
        field = self._field()
        if not self.rows or field is None:
            return
        value = self.val_var.get().strip()
        label = self.col_var.get()
        self._setup(self.tree_low, ("项目", f"新{label}"))
        for _pid, name, _cur in self._shown():
            self.tree_low.insert("", "end",
                                 values=(name, value or "(清空)"))

    def _apply(self):
        if self.db is None:
            messagebox.showwarning("提示", "请先加载数据库", parent=self)
            return
        field = self._field()
        if field is None:
            messagebox.showwarning("提示", "请选择赋值列", parent=self)
            return
        value = self.val_var.get().strip()
        n = len(self.rows)
        if not messagebox.askyesno(
                "确认赋值（全库）",
                f"将对库内全部 {n} 个项目赋值：\n\n"
                f"    {self.col_var.get()} = {value or '(清空)'}\n\n"
                f"每个项目生成一条新快照（不覆盖旧数据）。\n"
                f"此操作不可一键撤销（历史里可查可对比）。继续？",
                parent=self):
            return
        ok, fails = core.assign_value(
            self.db, [pid for pid, _n, _c in self.rows], field, value)
        # 执行后下表刷新为实际结果
        self._load()
        self._preview()
        msg = f"已赋值 {ok} / {n} 个项目"
        if fails:
            msg += f"，失败 {len(fails)}：{fails[:3]}"
        self.db_stat.config(text=self.db_stat.cget("text")
                            + f" ｜ {msg} ✓")
        messagebox.showinfo("完成", msg, parent=self)

    @staticmethod
    def _setup(tree, heads):
        tree.delete(*tree.get_children())      # 先清旧行，防换列后残留
        tree.configure(columns=list(range(len(heads))))
        for i, h in enumerate(heads):
            tree.heading(i, text=h)
            tree.column(i, width=330 if i == 0 else 200,
                        anchor="w", stretch=False)

    @staticmethod
    def _clear(tree):
        tree.delete(*tree.get_children())


if __name__ == "__main__":
    AssignApp().mainloop()
