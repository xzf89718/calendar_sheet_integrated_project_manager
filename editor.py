# -*- coding: utf-8 -*-
"""编辑 UI：新建项目 / 保存一次跟进。

保存 = 生成一条完整快照（db.add_snapshot 或 db.create_project）。
本模块只负责收集字段，不认识日历和历史展示。
"""
import re
import tkinter as tk
from tkinter import ttk, messagebox

from db import SNAPSHOT_FIELDS, normalize_date as _norm_date
from config import CFG

# 全部由 fields.json 配置驱动
LABELS = CFG.labels
TEXT_FIELDS = CFG.multiline
COMBO_FIELDS = dict(CFG.choice_fields)
COMBO_FIELDS[CFG.status_field] = CFG.status_options
DATE_FIELDS = tuple(CFG.date_fields)
INT_FIELDS = set(CFG.int_fields)
FLOAT_FIELDS = set(CFG.float_fields)


class SnapshotEditor(tk.Toplevel):
    """project_id 为 None 表示新建项目（项目名自动生成：厂家-客户-产品）。

    整个表单放在可滚动容器里，右侧滚动条，长文本框给足高度。
    """

    def __init__(self, master, db, project_id=None, on_saved=None):
        super().__init__(master)
        self.db = db
        self.project_id = project_id
        self.on_saved = on_saved
        self.title("新建项目" if project_id is None else "编辑/添加跟进")
        eui = CFG.editor_ui
        self.geometry(f"{eui.get('width', 840)}x{eui.get('height', 940)}")
        self.vars = {}
        self.texts = {}
        self._build()
        self.grab_set()

    def _build(self):
        # 可滚动外框：Canvas + 右侧滚动条
        canvas = tk.Canvas(self, highlightthickness=0)
        vsb = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frm = tk.Frame(canvas, padx=12, pady=12)
        win = canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(
            win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-e.delta / 120), "units"))

        self.frm = frm
        r = 0
        # 预填当前值（编辑跟随时）
        cur = (self.db.get_current(self.project_id)
               if self.project_id else None)
        for f in SNAPSHOT_FIELDS:
            tk.Label(frm, text=LABELS[f]).grid(row=r, column=0, sticky="nw",
                                               pady=2)
            if cur is None or cur[f] is None:
                # 新建预填优先级：字段 default > choice 建议值第一个 > 空
                if f in CFG.field_defaults:
                    val = str(CFG.field_defaults[f])
                elif f in COMBO_FIELDS:
                    val = (COMBO_FIELDS.get(f) or [""])[0]
                else:
                    val = ""
            else:
                val = str(cur[f])
            if f in TEXT_FIELDS:
                w = tk.Frame(frm)          # Text + 专属滚动条
                txt = tk.Text(w, width=50, height=TEXT_FIELDS[f],
                              wrap="word")
                sb = tk.Scrollbar(w, orient="vertical",
                                  command=txt.yview)
                txt.configure(yscrollcommand=sb.set)
                txt.pack(side="left", fill="both", expand=True)
                sb.pack(side="right", fill="y")
                if val:
                    txt.insert("1.0", val)
                self.texts[f] = txt
                w.grid(row=r, column=1, sticky="nsew", pady=2)
                r += 1
                continue
            elif f in COMBO_FIELDS:
                v = tk.StringVar(value=val)
                self.vars[f] = v
                # 里程碑/状态下拉给建议值，但允许输入任意字符串
                w = ttk.Combobox(frm, textvariable=v,
                                 values=COMBO_FIELDS[f],
                                 width=49)
            else:
                v = tk.StringVar(value=val)
                self.vars[f] = v
                w = tk.Entry(frm, textvariable=v, width=52)
            w.grid(row=r, column=1, sticky="we", pady=2)
            r += 1
        tk.Label(frm, text="改动说明(可空,自动对比生成)").grid(
            row=r, column=0, sticky="nw", pady=2)
        self.summary_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.summary_var, width=52).grid(
            row=r, column=1, sticky="we", pady=2)
        r += 1
        btns = tk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=2, pady=10)
        tk.Button(btns, text="保存",
                  command=self._save).pack(side="left", padx=5)
        tk.Button(btns, text="取消",
                  command=self.destroy).pack(side="left")

    def _field(self, f):
        if f in self.texts:
            return self.texts[f].get("1.0", "end").strip()
        return self.vars[f].get().strip()

    def _save(self):
        fields = {f: self._field(f) for f in SNAPSHOT_FIELDS}
        for f in DATE_FIELDS:
            if fields[f]:
                fields[f] = _norm_date(fields[f])
        try:
            for f in INT_FIELDS:
                if fields[f]:
                    fields[f] = int(float(str(fields[f]).rstrip("%")))
            for f in FLOAT_FIELDS:
                if fields[f]:
                    fields[f] = float(fields[f])
        except ValueError:
            bad = "、".join(INT_FIELDS | FLOAT_FIELDS)
            messagebox.showwarning("提示", f"{bad} 必须是数字", parent=self)
            return
        if self.project_id is None:
            pid = self.db.create_project(**fields)
        else:
            pid = self.project_id
            self.db.add_snapshot(pid, change_summary=
                                 self.summary_var.get().strip(), **fields)
        if self.on_saved:
            self.on_saved(pid)
        self.destroy()
