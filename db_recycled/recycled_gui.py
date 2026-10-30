# -*- coding: utf-8 -*-
"""回收站（子模块）：浏览 / 恢复 / 红色永久删除。

从包根目录共享 db/config/fields.json —— 本目录不携带任何配置。
运行：python db_recycled/recycled_gui.py <xxx.db>
（或命令行 python -m db_recycled <xxx.db> --gui）
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import tkinter as tk
from tkinter import ttk, messagebox

import db as _db                             # noqa: E402
import db_recycled.recycled_core as core     # noqa: E402


def run_gui(db, db_path=""):
    root = tk.Tk()
    root.title(f"回收站 - {db_path}")
    root.geometry("760x480")
    root.minsize(640, 400)

    cols = ("id", "title", "at", "cnt")
    tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="browse")
    tree.heading("id", text="ID")
    tree.heading("title", text="项目名")
    tree.heading("at", text="回收时间")
    tree.heading("cnt", text="快照数")
    tree.column("id", width=60, anchor="e")
    tree.column("title", width=280)
    tree.column("at", width=170)
    tree.column("cnt", width=70, anchor="e")
    tree.pack(fill="both", expand=True, padx=8, pady=8)

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=8, pady=(0, 8))

    def refresh():
        tree.delete(*tree.get_children())
        for pid, title, at, cnt in core.list_recycled(db):
            tree.insert("", "end", iid=str(pid),
                        values=(pid, title, at, cnt))

    def selected_id():
        sel = tree.selection()
        return int(sel[0]) if sel else None

    def do_view():
        pid = selected_id()
        if pid is None:
            return
        snaps = core.snapshots_of(db, pid)
        win = tk.Toplevel(root)
        win.title(f"回收项目历史 - #{pid}")
        win.geometry("640x420")
        lb = tk.Listbox(win, width=30)
        lb.pack(side="left", fill="y", padx=(8, 0), pady=8)
        txt = tk.Text(win, wrap="word")
        txt.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        def show(_e=None):
            s = snaps[lb.curselection()[0]]
            txt.delete("1.0", "end")
            txt.insert("end", f"时间: {s['snapshot_at']}\n"
                              f"记录人: {s['changed_by'] or '-'}\n"
                              f"说明: {s['change_summary'] or '-'}\n\n")
            for f in _db.SNAPSHOT_FIELDS:
                v = s[f]
                if v not in (None, ""):
                    txt.insert("end", f"{f}: {v}\n")
        for s in snaps:
            lb.insert("end", f"{s['snapshot_at']}  {s['change_summary'] or ''}")
        lb.bind("<<ListboxSelect>>", show)
        if snaps:
            lb.selection_set(0)
            show()

    def do_restore():
        pid = selected_id()
        if pid is None:
            return
        nid, changed = core.restore_project(db, pid)
        messagebox.showinfo(
            "已恢复", f"项目已恢复（id={nid}）"
                      + ("\n原 id 被占用，已分配新 id。" if changed else ""),
            parent=root)
        refresh()

    def do_purge():
        """永久删除：与原删除确认同设计——二次确认弹窗。"""
        pid = selected_id()
        if pid is None:
            return
        title = tree.item(str(pid), "values")[1]
        ok = messagebox.askyesno(
            "永久删除", f"确定要永久删除「{title}」吗？\n\n"
                       f"该项目及其全部快照历史将被物理销毁，"
                       f"此操作不可恢复。", icon="warning", parent=root)
        if not ok:
            return
        core.purge_project(db, pid)
        refresh()

    def do_empty():
        n = len(core.list_recycled(db))
        if n == 0:
            return
        ok = messagebox.askyesno(
            "清空回收站", f"确定要永久删除回收站里的全部 {n} 个项目吗？\n\n"
                         f"物理销毁，不可恢复。", icon="warning", parent=root)
        if not ok:
            return
        core.empty_recycle(db)
        refresh()

    tk.Button(btns, text="查看历史", command=do_view).pack(side="left", padx=4)
    tk.Button(btns, text="恢复", command=do_restore).pack(side="left", padx=4)
    # 永久删除 = 红色按钮 + 二次确认弹窗（危险操作的标准形态）
    tk.Button(btns, text="永久删除", fg="#c62828",
              command=do_purge).pack(side="left", padx=4)
    tk.Button(btns, text="清空回收站", fg="#c62828",
              command=do_empty).pack(side="left", padx=4)
    tk.Button(btns, text="刷新", command=refresh).pack(side="right", padx=4)

    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python db_recycled/recycled_gui.py <xxx.db>")
        sys.exit(1)
    from db import Database
    _db_obj = Database(sys.argv[1])
    try:
        sys.exit(run_gui(_db_obj, sys.argv[1]))
    finally:
        _db_obj.close()
