# -*- coding: utf-8 -*-
"""库复制器（子模块）：A/B 双库对照视图。

从包根目录共享 db/config/fields.json —— 本目录不携带任何配置。
运行：python -m db_copy gui（或 python db_copy/copy_gui.py）
"""
import os
import sys

# 子模块定位：把包根目录加进 import 路径，共享主程序的 db/config
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from db import Database                       # noqa: E402
from config import CFG
import gui_fonts                 # noqa: E402                        # noqa: E402
import db_copy.copy_core as core              # noqa: E402


def _build_cols():
    """列定义按当前 fields.json 动态拼：id/项目 + 前几个显示列 + 快照数/更新。

    不硬编码 milestone——真实配置可能没这一列，硬编码会直接崩。

    :return: [(列名, 中文表头, 像素宽), ...]。
    :rtype: list
    """
    cols = [("id", "ID", 60), ("title", "项目", 260)]
    for name, head in CFG.display_cols:
        if name in ("id", "title"):
            continue
        cols.append((name, head, 110))
        if len(cols) >= 5:          # 列太多挤不下，取前几个显示列
            break
    cols += [("snaps", "快照数", 70), ("last_at", "最近更新", 150)]
    return cols


COLS = _build_cols()


def rowdict(r):
    """查询行 -> 表格行 dict（列值全部转字符串，id/snap_count 补键）。

    :param r: 查询结果行（sqlite3.Row）。
    :type r: sqlite3.Row
    :return: {列名: 显示值}。
    :rtype: dict
    """
    d = {c: ("" if r[c] is None else str(r[c])) for c, _h, _w in COLS}
    d["id"] = r["id"]
    d["snaps"] = r["snap_count"]
    return d


class FilterPopup(tk.Toplevel):
    """列筛选勾选清单（Excel 式）。on_apply(set 或 None)。"""

    def __init__(self, master, col_name, values, selected, on_apply):
        """列筛选勾选清单弹窗（Excel 式）。

        :param master: 父窗口。
        :type master: tk.Widget
        :param col_name: 列名。
        :type col_name: str
        :param values: 该列全部可选值。
        :type values: list
        :param selected: 当前勾选集合，None = 全选态。
        :type selected: set 或 None
        :param on_apply: 确定回调，接收 set（空集 = 全不显示）。
        :type on_apply: callable
        """
        super().__init__(master)
        self.on_apply = on_apply
        self.title(f"筛选 - {col_name}")
        frm = tk.Frame(self, padx=10, pady=10)
        frm.pack(fill="both", expand=True)
        self.vars = {}
        for v in values:
            var = tk.BooleanVar(value=(selected is None or v in selected))
            self.vars[v] = var
            tk.Checkbutton(frm, text=v or "(空)", variable=var,
                           anchor="w").pack(fill="x")
        ops = tk.Frame(frm)
        ops.pack(fill="x", pady=4)
        tk.Button(ops, text="全选",
                  command=lambda: self._all(True)).pack(side="left")
        tk.Button(ops, text="全不选",
                  command=lambda: self._all(False)).pack(side="left",
                                                         padx=4)
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="确定",
                  command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="取消",
                  command=self.destroy).pack(side="right")
        self.grab_set()
        self.transient(master)

    def _all(self, b):
        """全选 / 全不选。

        :param b: 目标布尔值。
        :type b: bool
        """
        for v in self.vars.values():
            v.set(b)

    def _ok(self):
        """确定：把勾选集合交给 on_apply 后关闭弹窗。"""
        checked = {v for v, var in self.vars.items() if var.get()}
        self.on_apply(checked if checked else set())   # 空集=全不显示
        self.destroy()


class RangePopup(tk.Toplevel):
    """日期区间筛选（工具内表格用）：从 ~ 到，留空=不限。"""

    def __init__(self, master, col_name, current, on_apply):
        """日期区间筛选弹窗：从 ~ 到，留空 = 不限。

        :param master: 父窗口。
        :type master: tk.Widget
        :param col_name: 列名。
        :type col_name: str
        :param current: 当前区间 (d1, d2)，None = 未筛选。
        :type current: tuple 或 None
        :param on_apply: 确定回调，接收 (d1, d2) 或 None（清除）。
        :type on_apply: callable
        """
        super().__init__(master)
        self.on_apply = on_apply
        self.title(f"筛选 - {col_name}")
        frm = tk.Frame(self, padx=14, pady=12)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text=f"{col_name}：日期区间（留空=不限）",
                 fg="#666666").pack(anchor="w")
        row = tk.Frame(frm)
        row.pack(fill="x", pady=6)
        cur = current or ("", "")
        self.v1 = tk.StringVar(value=cur[0] or "")
        self.v2 = tk.StringVar(value=cur[1] or "")
        tk.Entry(row, textvariable=self.v1, width=12).pack(side="left",
                                                           padx=2)
        tk.Label(row, text="~").pack(side="left")
        tk.Entry(row, textvariable=self.v2, width=12).pack(side="left",
                                                           padx=2)
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        tk.Button(btns, text="清除筛选",
                  command=self._clear).pack(side="left")
        tk.Button(btns, text="确定", width=8,
                  command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="取消", width=8,
                  command=self.destroy).pack(side="right")
        self.grab_set()
        self.transient(master)

    def _clear(self):
        """清除筛选：on_apply(None) 并关闭。"""
        self.on_apply(None)
        self.destroy()

    def _ok(self):
        """确定：两端 normalize_date 规范化后交给 on_apply（全空 = 清除）。"""
        from db import normalize_date
        a, b = self.v1.get().strip(), self.v2.get().strip()
        na = normalize_date(a) if a else ""
        nb = normalize_date(b) if b else ""
        self.on_apply((na, nb) if (na or nb) else None)
        self.destroy()


class SidePanel(tk.LabelFrame):
    """单侧库的项目表：搜索框 + 可排序/可筛选的 Treeview。"""

    def __init__(self, master, title):
        """单侧库的项目表面板：搜索框 + 可排序/可筛选 Treeview + 分页。

        :param master: 父容器。
        :type master: tk.Widget
        :param title: 面板标题（源库 A / 目标库 B）。
        :type title: str
        """
        super().__init__(master, text=title, padx=6, pady=6)
        self.rows_all = []
        self.filters = {c: None for c, _h, _w in COLS}
        self.sort_col = None
        self.sort_rev = False
        srow = tk.Frame(self)
        srow.pack(fill="x", pady=(0, 4))
        tk.Label(srow, text="搜索:", fg="#666666").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._search_changed())
        tk.Entry(srow, textvariable=self.search_var).pack(
            side="left", fill="x", expand=True)
        cols = [c for c, _h, _w in COLS]
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 selectmode="extended", height=18)
        for c, h, w in COLS:
            self.tree.heading(c, text=h, command=lambda cc=c: self.sort(cc))
            self.tree.column(c, width=w, anchor="w",
                             stretch=(c == "title"))
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Button-3>", self._header_menu)
        self.offset = 0
        self.limit_lbl = None
        lrow = tk.Frame(self)
        lrow.pack(fill="x", pady=(2, 0))
        self.limit_lbl = tk.Label(lrow, text="", fg="#8d6e00", anchor="w")
        self.limit_lbl.pack(side="left")
        self.next_btn = tk.Button(lrow, text="下一页 ▼", state="disabled",
                                  command=self.load_more)
        self.next_btn.pack(side="right")
        self.prev_btn = tk.Button(lrow, text="▲ 上一页", state="disabled",
                                  command=self.load_prev)
        self.prev_btn.pack(side="right", padx=4)
        self._refresh_headings()

    def _search_changed(self):
        """搜索词变化回调：回到第一页并重填表格。"""
        self.offset = 0
        self.refill()

    def load(self, db):
        """载入一个库的项目清单（重置筛选/排序/分页后重填）。

        :param db: 已打开的库。
        :type db: db.Database
        """
        self.rows_all = [rowdict(r) for r in core.list_projects(db)]
        self.sort_col = None
        self.filters = {c: None for c, _h, _w in COLS}
        self.offset = 0
        self.refill()

    def visible_rows(self):
        """当前 搜索+筛选+排序 口径下的全部可见行。

        :return: 行 dict 列表。
        :rtype: list
        """
        rows = list(self.rows_all)
        kw = self.search_var.get().strip().casefold()
        if kw:
            rows = [r for r in rows
                    if any(kw in str(v).casefold() for v in r.values())]
        for c, sel in self.filters.items():
            if sel is None:
                continue
            if isinstance(sel, tuple):        # 日期区间
                d1, d2 = sel
                def in_range(r, c=c, d1=d1, d2=d2):
                    """单行是否落在日期区间内（闭区间，任一端可省略）。

                    :param r: 行 dict。
                    :type r: dict
                    :param c: 列名。
                    :type c: str
                    :param d1: 区间起点，空 = 不限。
                    :type d1: str
                    :param d2: 区间终点，空 = 不限。
                    :type d2: str
                    :return: 是否命中。
                    :rtype: bool
                    """
                    v = str(r[c])[:10]
                    return bool(v) and (not d1 or v >= d1) \
                        and (not d2 or v <= d2)
                rows = [r for r in rows if in_range(r)]
            else:
                rows = [r for r in rows if str(r[c]) in sel]
        if self.sort_col:
            col = self.sort_col
            rows.sort(key=lambda r: (0, float(r[col]))
                      if str(r[col]).replace(".", "", 1).isdigit()
                      else (1, str(r[col]).casefold()),
                      reverse=self.sort_rev)
        return rows

    def refill(self):
        """按当前 offset/render_limit 重填表格并更新翻页控件状态。"""
        from config import CFG
        self.tree.delete(*self.tree.get_children())
        rows = self.visible_rows()          # 筛选+排序全量
        shown = rows[self.offset: self.offset + CFG.render_limit]
        for r in shown:
            self.tree.insert("", "end", iid=str(r["id"]),
                             values=[r[c] for c, _h, _w in COLS])
        # 翻页提示 + 上/下一页（与主程序共用 ui.render_limit）
        if self.limit_lbl is not None:
            start = self.offset + (1 if shown else 0)
            end = self.offset + len(shown)
            if len(rows) > len(shown) or self.offset > 0:
                self.limit_lbl.config(
                    text=f"第 {start} ~ {end} 条 / 共 {len(rows)} 条")
            else:
                self.limit_lbl.config(text=f"共 {len(rows)} 条")
            self.prev_btn.config(
                state="normal" if self.offset > 0 else "disabled")
            self.next_btn.config(
                state="normal" if end < len(rows) else "disabled")

    def load_more(self):
        """翻到下一页。"""
        from config import CFG
        self.offset += CFG.render_limit
        self.refill()

    def load_prev(self):
        """翻到上一页（不越过 0）。"""
        from config import CFG
        self.offset = max(0, self.offset - CFG.render_limit)
        self.refill()

    def sort(self, col):
        """按列排序：同列再点切换升降序，换列重置升序。

        :param col: 列名。
        :type col: str
        """
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, False
        self.offset = 0
        self._refresh_headings()
        self.refill()

    def _refresh_headings(self):
        """刷新表头：叠加排序箭头与筛选标记。"""
        for c, h, _w in COLS:
            mark = ""
            if c == self.sort_col:
                mark = " ▼" if self.sort_rev else " ▲"
            if self.filters.get(c) is not None:
                mark += " 🔽"
            self.tree.heading(c, text=h + mark,
                              command=lambda cc=c: self.sort(cc))

    def _header_menu(self, ev):
        """表头右键菜单：日期列出区间弹窗，其余列出勾选筛选弹窗。

        :param ev: 鼠标事件。
        :type ev: tk.Event
        """
        if self.tree.identify_region(ev.x, ev.y) != "heading":
            return
        col = self.tree.identify_column(ev.x)
        col = COLS[int(col.lstrip("#")) - 1][0]
        # 日期类列用区间筛选（与主程序一致）
        if col in ("last_at",):
            def apply_range(rng):
                """区间筛选弹窗的确定回调：写入该列筛选并重刷。

                :param rng: (d1, d2) 或 None（清除）。
                :type rng: tuple 或 None
                """
                self.filters[col] = rng
                self._refresh_headings()
                self.refill()
            RangePopup(self, dict((c, h) for c, h, _w in COLS)[col],
                       self.filters[col], apply_range)
            return
        values = sorted({str(r[col]) for r in self.rows_all})

        def apply(sel):
            """勾选筛选弹窗的确定回调：写入该列筛选并重刷（回第一页）。

            :param sel: 勾选值集合。
            :type sel: set
            """
            self.filters[col] = sel
            self.offset = 0
            self._refresh_headings()
            self.refill()

        FilterPopup(self, dict((c, h) for c, h, _w in COLS)[col], values,
                    self.filters[col], apply)

    def clear_filters(self):
        """清除全部列筛选与搜索词。"""
        self.filters = {c: None for c, _h, _w in COLS}
        self.search_var.set("")
        self.offset = 0
        self._refresh_headings()
        self.refill()

    def selected_ids(self):
        """当前勾选的行 id 列表。

        :return: 项目 id 列表。
        :rtype: list
        """
        return [int(i) for i in self.tree.selection()]


class CopierApp(tk.Tk):
    def __init__(self):
        """初始化 A/B 对照复制器主窗口（1280x640）并搭建界面。"""
        super().__init__()
        gui_fonts.apply(self, "db_copy")
        self.title("项目库复制器 v1.1.0")
        self.geometry("1280x640")
        self.db_a = None
        self.db_b = None
        self._build()

    def _build(self):
        """搭建主界面：A/B 路径 + 双侧 SidePanel + 复制按钮。"""
        pad = {"padx": 8, "pady": 4}
        top = tk.Frame(self)
        top.pack(fill="x", **pad)
        tk.Label(top, text="源库 A：").grid(row=0, column=0, sticky="e")
        self.path_a = tk.StringVar()
        tk.Entry(top, textvariable=self.path_a, width=48).grid(
            row=0, column=1, sticky="we")
        tk.Button(top, text="浏览",
                  command=lambda: self._pick(self.path_a)).grid(
            row=0, column=2, padx=4)
        tk.Label(top, text="目标库 B：").grid(row=1, column=0, sticky="e")
        self.path_b = tk.StringVar()
        tk.Entry(top, textvariable=self.path_b, width=48).grid(
            row=1, column=1, sticky="we")
        tk.Button(top, text="浏览",
                  command=lambda: self._pick(self.path_b)).grid(
            row=1, column=2, padx=4)
        tk.Button(top, text="加载两库", bg="#1565c0", fg="white",
                  command=self._load).grid(row=2, column=1, sticky="w",
                                           pady=4)
        top.columnconfigure(1, weight=1)

        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, **pad)
        self.panel_a = SidePanel(mid, "A 库（源，勾选后点箭头复制）")
        self.panel_a.pack(side="left", fill="both", expand=True)
        arrow = tk.Frame(mid, padx=10)
        arrow.pack(side="left", fill="y")
        self.arrow_btn = tk.Button(arrow, text="➡", font=("", 28),
                                   bg="#2e7d32", fg="white", padx=14,
                                   pady=10, command=self._copy)
        self.arrow_btn.pack(expand=True)
        self.sel_label = tk.Label(arrow, text="已选 0 项", fg="#666666")
        self.sel_label.pack()
        self.panel_a.tree.bind("<<TreeviewSelect>>",
                               lambda e: self._sel_changed())
        self.panel_b = SidePanel(mid, "B 库（目标，只增不改）")
        self.panel_b.pack(side="left", fill="both", expand=True)

        bot = tk.Frame(self)
        bot.pack(fill="x", **pad)
        tk.Button(bot, text="清除A筛选",
                  command=self.panel_a.clear_filters).pack(side="left",
                                                           padx=4)
        tk.Button(bot, text="清除B筛选",
                  command=self.panel_b.clear_filters).pack(side="left",
                                                           padx=4)
        tk.Button(bot, text="刷新B库显示",
                  command=self._reload_b).pack(side="left", padx=4)
        self.status = tk.Label(bot, text="选择两个数据库后点「加载两库」",
                               fg="#666666")
        self.status.pack(side="left", padx=12)

    def _pick(self, var):
        """文件浏览选择库路径并触发加载。

        :param var: 接收路径的 StringVar。
        :type var: tk.StringVar
        """
        p = filedialog.askopenfilename(
            parent=self,
            filetypes=[("SQLite 数据库", "*.db"), ("所有", "*.*")])
        if p:
            var.set(p)

    def _load(self):
        """加载 A/B 双侧库并刷新各自面板（兼容性预检失败弹错）。"""
        pa, pb = self.path_a.get().strip(), self.path_b.get().strip()
        if not pa or not pb:
            messagebox.showwarning("提示", "请先选择源库 A 和目标库 B",
                                   parent=self)
            return
        if os.path.abspath(pa) == os.path.abspath(pb):
            messagebox.showwarning("提示", "源库和目标库是同一个文件",
                                   parent=self)
            return
        try:
            self.db_a = Database(pa)
            self.db_b = Database(pb)
        except Exception as e:
            messagebox.showerror("打开失败", str(e), parent=self)
            return
        ok, msg = core.check_compatible(self.db_a, self.db_b)
        if not ok:
            messagebox.showerror("配置不一致", msg, parent=self)
            return
        self.panel_a.load(self.db_a)
        self._reload_b()
        self.status.config(
            text=f"A 库 {len(self.panel_a.rows_all)} 项 → B 库 "
                 f"{len(self.panel_b.rows_all)} 项：勾选 A 中项目，"
                 f"点中间箭头追加到 B（只新增）")

    def _reload_b(self):
        """复制完成后刷新 B 侧面板。"""
        if self.db_b:
            self.panel_b.load(self.db_b)

    def _sel_changed(self):
        """A 侧选择变化回调：更新可复制的选中计数。"""
        n = len(self.panel_a.tree.selection())
        self.sel_label.config(text=f"已选 {n} 项")

    def _copy(self):
        """执行复制：确认后把 A 侧选中项目复制到 B 库并刷新 B 面板。"""
        pids = self.panel_a.selected_ids()
        if not pids:
            messagebox.showinfo("提示", "请先在 A 库列表里选中项目",
                                parent=self)
            return
        if not messagebox.askyesno(
                "确认复制",
                f"将把 A 库选中的 {len(pids)} 个项目（含全部历史快照）\n"
                f"追加为 B 库的新项目。\n\n"
                f"B 库已有数据不会被修改或删除。继续？",
                parent=self):
            return
        try:
            np_, ns = core.copy_projects(self.db_a, self.db_b, pids)
        except Exception as e:
            messagebox.showerror("复制失败（已整体回滚）", str(e),
                                 parent=self)
            return
        self._reload_b()
        self.status.config(text=f"已复制 {np_} 个项目、{ns} 条快照到 B 库 ✓")


def run_gui():
    """GUI 入口：构造并进入 CopierApp 主循环。

    :return: run_gui 调用结果。
    """
    CopierApp().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run_gui())
