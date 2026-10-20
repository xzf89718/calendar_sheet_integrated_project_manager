# -*- coding: utf-8 -*-
"""阅读 UI：项目详情 = 当前状态 + 快照时间线（日记/追溯）+ 任意两版对比。

对比差异用红色高亮。本模块只读数据库，不写。
跟进历史列表只显示每次的改动摘要；最新一条跟进记录单独展示。
"""
import tkinter as tk
from tkinter import ttk, messagebox

from db import SNAPSHOT_FIELDS
from editor import SnapshotEditor, LABELS

DIFF_IGNORE = {"id", "project_id", "snapshot_at", "changed_by",
               "change_summary"}  # 跟进记录纳入统一对比


class ProjectReader(tk.Toplevel):
    def __init__(self, master, db, project_id, on_changed=None):
        super().__init__(master)
        self.db = db
        self.project_id = project_id
        self.on_changed = on_changed
        p = db.get_project(project_id)
        self.title(f"项目详情 - {p['title']}")
        self.transient(master)
        self._build()
        self._load()
        self.grab_set()

    def _build(self):
        self.geometry("1300x760")      # 默认窗口更宽，富余宽度全给当前状态
        root = tk.Frame(self, padx=8, pady=8)
        root.pack(fill="both", expand=True)
        # 左：当前状态（可滚动：文本再多也能滚到底部按钮）
        left_wrap = tk.LabelFrame(root, text="当前状态", padx=6, pady=6)
        left_wrap.pack(side="left", fill="both", expand=True)
        # 查看历史版本时的横幅（默认隐藏）
        self.banner = tk.Frame(left_wrap, bg="#fff8e1")
        self.banner_lbl = tk.Label(self.banner, bg="#fff8e1", fg="#8d6e00")
        self.banner_lbl.pack(side="left", padx=6)
        tk.Button(self.banner, text="回到最新", command=self._show_latest
                  ).pack(side="right", padx=6, pady=2)
        self.banner.pack(fill="x", pady=(0, 6))   # 占位顶部位置
        self.banner.pack_forget()                 # 默认隐藏
        self.viewing_hist = False
        canvas = tk.Canvas(left_wrap, highlightthickness=0)
        vsb = tk.Scrollbar(left_wrap, orient="vertical",
                           command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        left = tk.Frame(canvas)
        win = canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: self._reflow(canvas, win, e))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-e.delta / 120), "units"))
        left.columnconfigure(1, weight=1)     # 值列吃掉全部富余宽度
        # 可滚动区：只有字段标签；按钮固定在面板底部，任何文本长度都可达
        self.cur_labels = {}     # 普通字段 -> Label
        self.cur_texts = {}      # 限高字段(max_lines) -> Text+滚动条
        from config import CFG
        for i, f in enumerate(SNAPSHOT_FIELDS):
            tk.Label(left, text=LABELS[f], fg="#666666").grid(
                row=i, column=0, sticky="nw", padx=4, pady=1)
            if f in CFG.max_lines:
                # 限高显示：固定行数 + 竖向滚动条。
                # width=4 是最小值，靠 column 权重拉伸到可视宽度——
                # 不设 width 时 Text 默认索要 80 字符宽，超出画布被裁，
                # 滚动条也会被顶出可视区（右截断/看不到条的真凶）
                box = tk.Frame(left)
                box.columnconfigure(0, weight=1)
                txt = tk.Text(box, height=CFG.max_lines[f], width=4,
                              wrap="word", state="disabled",
                              relief="sunken")
                sb = tk.Scrollbar(box, orient="vertical", command=txt.yview)
                txt.configure(yscrollcommand=sb.set)
                txt.grid(row=0, column=0, sticky="nsew")
                sb.grid(row=0, column=1, sticky="ns")
                box.grid(row=i, column=1, sticky="we", padx=4, pady=1)
                self.cur_texts[f] = txt
            else:
                lbl = tk.Label(left, text="", wraplength=360,
                               justify="left")
                lbl.grid(row=i, column=1, sticky="w", padx=4, pady=1)
                self.cur_labels[f] = lbl
        # 按钮跟在字段后自然排布：长文本都有换行+限高兜底，内容高度
        # 有界，按钮始终够得着；失败原因下不再留大片空白
        btns = tk.Frame(left)
        btns.grid(row=len(SNAPSHOT_FIELDS), column=0, columnspan=2,
                  sticky="w", pady=8)
        tk.Button(btns, text="编辑/添加跟进",
                  command=self._edit).pack(side="left", padx=4)
        tk.Button(btns, text="删除项目", fg="#c62828",
                  command=self._delete).pack(side="left", padx=4)
        # 右：快照时间线（固定自然宽度，富余宽度让给当前状态）
        right = tk.LabelFrame(root, text="跟进历史（选择两条可对比）",
                              padx=6, pady=6)
        right.pack(side="left", fill="y", padx=(8, 0))
        self.listbox = tk.Listbox(right, width=44, selectmode="extended",
                                  exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        btns = tk.Frame(right)
        btns.pack(pady=4)
        tk.Button(btns, text="查看选中版本",
                  command=self._view_selected).pack(side="left", padx=4)
        tk.Button(btns, text="对比选中两条",
                  command=self._diff).pack(side="left", padx=4)
        # 最新跟进记录（不逐条展示历史笔记）
        tk.Label(right, text="最新跟进记录", fg="#666666",
                 anchor="w").pack(fill="x")
        self.note_lbl = tk.Label(right, text="", justify="left",
                                 anchor="nw", wraplength=380,
                                 bg="#f5f5f5", relief="sunken")
        self.note_lbl.pack(fill="x", pady=(2, 0))
        self.snap_rows = []

    def _reflow(self, canvas, win, e):
        """画布宽度变化：内容窗跟着宽，字段值换行宽度跟随实际宽度。

        不换行的病根：wraplength 写死 360，窗口拉窄时长行超出画布
        边缘被裁掉。改为 wraplength = 画布宽 - 标签列宽，文字永远在
        可视区内换行。
        """
        canvas.itemconfigure(win, width=e.width)
        wrap = max(120, e.width - 150)
        for lbl in self.cur_labels.values():
            lbl.config(wraplength=wrap)

    def _load(self):
        self._show_snapshot(self.db.get_current(self.project_id))
        self.viewing_hist = False
        self.banner.pack_forget()

    def _show_latest(self):
        self._load()
        self.listbox.selection_clear(0, "end")

    def _view_selected(self):
        """查看选中条目对应的历史版本（按钮触发，与多选对比互不干扰）。"""
        sel = self.listbox.curselection()
        if len(sel) != 1:
            messagebox.showinfo("提示", "请先在历史列表里选中一条记录",
                                parent=self)
            return
        snap = self.snap_rows[sel[0]]
        latest = self.snap_rows[-1]
        if snap["id"] == latest["id"]:
            self._show_latest()
            return
        self._show_snapshot(snap)
        self.viewing_hist = True
        idx = sel[0] + 1
        self.banner_lbl.config(
            text=f"⏳ 正在查看历史版本（{idx}/{len(self.snap_rows)}）"
                 f"  {snap['snapshot_at']}  —  编辑按钮基于最新状态")
        self.banner.pack(fill="x", pady=(0, 6))

    def _show_snapshot(self, cur):
        """把某条快照（或当前状态）填进左侧面板。"""
        for f, lbl in self.cur_labels.items():
            lbl.config(text="" if cur is None or cur[f] is None
                       else str(cur[f]))
        for f, txt in self.cur_texts.items():
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            if cur is not None and cur[f] is not None:
                txt.insert("1.0", str(cur[f]))
            txt.configure(state="disabled")
        self.listbox.delete(0, "end")
        self.snap_rows = self.db.get_snapshots(self.project_id)
        for s in self.snap_rows:
            self.listbox.insert(
                "end", f"{s['snapshot_at']}  {s['change_summary']}")
        # 只展示最新一次跟进记录；超长截断防止把窗口撑爆，
        # 完整内容在"编辑/添加跟进"和两版对比里可见
        latest_note = self.snap_rows[-1]["followup_note"] \
            if self.snap_rows else None
        if latest_note and len(latest_note) > 400:
            latest_note = latest_note[:400] + " …（截断，点编辑看全文）"
        self.note_lbl.config(text=latest_note or "（无）")

    def _edit(self):
        SnapshotEditor(self, self.db, self.project_id,
                       on_saved=lambda pid: self._reload())

    def _delete(self):
        p = self.db.get_project(self.project_id)
        ok = ConfirmDialog(self, "删除项目",
                           f"确定要删除项目「{p['title']}」吗？\n\n"
                           f"该项目的全部跟进历史和快照将一并删除，"
                           f"此操作不可恢复。").result
        if not ok:
            return
        self.db.delete_project(self.project_id)
        if self.on_changed:
            self.on_changed()
        self.destroy()

    def _reload(self):
        self._load()
        if self.on_changed:
            self.on_changed()

    def _diff(self):
        sel = self.listbox.curselection()
        if len(sel) != 2:
            messagebox.showinfo("提示", "请选中两条记录", parent=self)
            return
        a, b = self.snap_rows[sel[0]], self.snap_rows[sel[1]]
        DiffWindow(self, a, b)


class ConfirmDialog(tk.Toplevel):
    """屏幕居中的确认弹窗。result 为 True/False。"""

    def __init__(self, master, title, message):
        super().__init__(master)
        self.title(title)
        self.result = False
        self.transient(master)
        frm = tk.Frame(self, padx=20, pady=16)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text=message, justify="left",
                 font=("", 11)).pack(anchor="w")
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        tk.Button(btns, text="确定", width=8, bg="#c62828", fg="white",
                  command=self._yes).pack(side="right", padx=4)
        tk.Button(btns, text="取消", width=8,
                  command=self._no).pack(side="right")
        self.grab_set()
        # 屏幕居中
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")
        self.lift()
        self.wait_window()          # 模态等待，返回时 result 已定

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.result = False
        self.destroy()


def _one_line(s):
    """多行文本压成一行显示，换行处标 ↵。"""
    return "" if s is None else str(s).replace("\n", " ↵ ")


class DiffWindow(tk.Toplevel):
    """两版快照逐字段对比（含跟进记录），不同标红，长行可横滚。"""

    def __init__(self, master, snap_a, snap_b):
        super().__init__(master)
        self.title(f"对比  #{snap_a['id']} ↔ #{snap_b['id']}")
        cols = ("field", "a", "b")
        area = tk.Frame(self)
        area.pack(fill="both", expand=True, padx=8, pady=8)
        tree = ttk.Treeview(area, columns=cols, show="headings", height=18)
        tree.heading("field", text="字段")
        tree.heading("a", text=f"A {snap_a['snapshot_at']}")
        tree.heading("b", text=f"B {snap_b['snapshot_at']}")
        tree.column("field", width=110, stretch=False)
        tree.column("a", width=300)
        tree.column("b", width=300)
        ysb = tk.Scrollbar(area, orient="vertical", command=tree.yview)
        xsb = tk.Scrollbar(self, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="left", fill="y")
        xsb.pack(fill="x", padx=8)
        tree.tag_configure("diff", foreground="#c62828")
        for f in SNAPSHOT_FIELDS:
            if f in DIFF_IGNORE:
                continue
            va = _one_line(snap_a[f])
            vb = _one_line(snap_b[f])
            tag = ("diff",) if va != vb else ()
            tree.insert("", "end", values=(LABELS[f], va, vb), tags=tag)
