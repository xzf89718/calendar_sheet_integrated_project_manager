# -*- coding: utf-8 -*-
"""回收站管理（v3.1.0）：查看 / 恢复 / 彻底删除。

主程序只管"删除 = 搬进回收站"（db.py delete_project 分支）；
本模块负责回收站里的一切：
  - 命令行：python db_recycled.py <xxx.db>                列出回收站
            python db_recycled.py <xxx.db> --restore 12   恢复项目
            python db_recycled.py <xxx.db> --restore all  全部恢复
            python db_recycled.py <xxx.db> --purge 12     永久删除单个
            python db_recycled.py <xxx.db> --empty        清空回收站
  - GUI：  python db_recycled.py <xxx.db> --gui

恢复语义：项目原 id 空闲则原样放回（收藏夹索引一并带回）；id 已被
新项目占用才发新 id，收藏夹索引指向新 id。快照 id 一律重新分配
（回收期间主表可能已增长），projects.current_id 同步修正。
彻底删除 = 物理销毁，红色按钮 + 二次确认弹窗（与原删除确认同设计）。
"""
import argparse
import sys

import db as _db
from db import Database

# SNAPSHOT_FIELDS 通过 _db 动态取：db.py 在 import 时
# 按 fields.json 冻结它，测试/多形态下会被替换，绑定死会拿到错配置


# ---------- 核心（纯逻辑，CLI 与 GUI 共用） ----------

def list_recycled(db):
    """回收站清单 [(id, 项目名, 回收时间, 快照数)]，新回收在前。"""
    return db.conn.execute(
        "SELECT r.id, r.title, r.recycled_at,"
        "       (SELECT COUNT(*) FROM recycled_snapshots s"
        "         WHERE s.project_id = r.id)"
        " FROM recycled_projects r ORDER BY r.recycled_at DESC, r.id"
    ).fetchall()


def snapshots_of(db, project_id):
    return db.conn.execute(
        "SELECT * FROM recycled_snapshots WHERE project_id=? "
        "ORDER BY snapshot_at, id", (project_id,)).fetchall()


def restore_project(db, project_id):
    """把回收项目搬回主表。返回 (新项目id, 是否换了新id)。"""
    rp = db.conn.execute(
        "SELECT * FROM recycled_projects WHERE id=?",
        (project_id,)).fetchone()
    if rp is None:
        raise ValueError(f"回收站里没有项目 {project_id}")
    snaps = snapshots_of(db, project_id)
    items = db.conn.execute(
        "SELECT collection_id, position FROM recycled_collection_items "
        "WHERE project_id=?", (project_id,)).fetchall()
    with db.conn:
        new_id = project_id
        id_changed = db.conn.execute(
            "SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() \
            is not None
        if id_changed:
            cur = db.conn.execute(
                "INSERT INTO projects(title, status, created_at)"
                " VALUES (?, ?, ?)",
                (rp["title"], rp["status"], rp["created_at"]))
            new_id = cur.lastrowid
        else:
            db.conn.execute(
                "INSERT INTO projects(id, title, status, created_at)"
                " VALUES (?, ?, ?, ?)",
                (rp["id"], rp["title"], rp["status"], rp["created_at"]))
        # 快照搬回：id 重新分配，维护 old_id -> new_id 映射
        sid_map = {}
        cols = ["project_id", "snapshot_at", "changed_by",
                "change_summary"] + _db.SNAPSHOT_FIELDS
        for s in snaps:
            old_sid = s["id"]
            vals = [new_id, s["snapshot_at"], s["changed_by"],
                    s["change_summary"]] + [s[f] for f in _db.SNAPSHOT_FIELDS]
            cur = db.conn.execute(
                f"INSERT INTO snapshots({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})", vals)
            sid_map[old_sid] = cur.lastrowid
        # 当前指针修正到新快照 id
        db.conn.execute(
            "UPDATE projects SET current_id=? WHERE id=?",
            (sid_map.get(rp["current_id"]), new_id))
        # 收藏夹索引带回（收藏夹功能开启时）
        if items and db._table_exists("collection_items"):
            for cid, pos in items:
                db.conn.execute(
                    "INSERT OR IGNORE INTO collection_items"
                    "(collection_id, project_id, position) VALUES(?,?,?)",
                    (cid, new_id, pos))
        _drop_recycled_rows(db, project_id)
    return new_id, id_changed


def purge_project(db, project_id):
    """永久删除单个回收项目（物理销毁，不可恢复）。"""
    _drop_recycled_rows(db, project_id)


def empty_recycle(db):
    """清空回收站（物理销毁全部，不可恢复）。"""
    with db.conn:
        db.conn.execute("DELETE FROM recycled_snapshots")
        db.conn.execute("DELETE FROM recycled_collection_items")
        db.conn.execute("DELETE FROM recycled_projects")


def _drop_recycled_rows(db, project_id):
    with db.conn:
        db.conn.execute(
            "DELETE FROM recycled_snapshots WHERE project_id=?",
            (project_id,))
        db.conn.execute(
            "DELETE FROM recycled_collection_items WHERE project_id=?",
            (project_id,))
        db.conn.execute(
            "DELETE FROM recycled_projects WHERE id=?", (project_id,))


# ---------- 命令行 ----------

def _cmd_list(db):
    rows = list_recycled(db)
    if not rows:
        print("回收站是空的。")
        return
    print(f"{'id':>4}  {'项目名':<30} {'回收时间':<20} 快照数")
    for pid, title, at, cnt in rows:
        print(f"{pid:>4}  {title:<30} {at:<20} {cnt}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_recycled", description="回收站管理（查看/恢复/彻底删除）")
    ap.add_argument("db", help="数据库文件路径，如 xxx.db")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    ap.add_argument("--restore", metavar="ID|all", help="恢复项目")
    ap.add_argument("--purge", type=int, metavar="ID", help="永久删除单个")
    ap.add_argument("--empty", action="store_true", help="清空回收站")
    args = ap.parse_args(argv)

    db = Database(args.db)
    try:
        if args.gui:
            return _gui(db, args.db)
        if args.restore:
            if args.restore == "all":
                rows = list_recycled(db)
                for pid, _t, _a, _c in rows:
                    nid, changed = restore_project(db, pid)
                    print(f"已恢复 {pid}" +
                          (f"（新 id={nid}）" if changed else ""))
                print(f"共恢复 {len(rows)} 个项目。")
            else:
                nid, changed = restore_project(db, int(args.restore))
                print(f"已恢复 {nid}" +
                      (f"（原 id={args.restore} 被占用，换了新 id）"
                       if changed else ""))
            return 0
        if args.purge is not None:
            purge_project(db, args.purge)
            print(f"已永久删除回收项目 {args.purge}。")
            return 0
        if args.empty:
            empty_recycle(db)
            print("回收站已清空（全部永久删除）。")
            return 0
        _cmd_list(db)
        return 0
    finally:
        db.close()


# ---------- GUI ----------

def _gui(db, db_path=""):
    import tkinter as tk
    from tkinter import ttk, messagebox

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
        for pid, title, at, cnt in list_recycled(db):
            tree.insert("", "end", iid=str(pid),
                        values=(pid, title, at, cnt))

    def selected_id():
        sel = tree.selection()
        return int(sel[0]) if sel else None

    def do_view():
        pid = selected_id()
        if pid is None:
            return
        snaps = snapshots_of(db, pid)
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
        nid, changed = restore_project(db, pid)
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
        purge_project(db, pid)
        refresh()

    def do_empty():
        n = len(list_recycled(db))
        if n == 0:
            return
        ok = messagebox.askyesno(
            "清空回收站", f"确定要永久删除回收站里的全部 {n} 个项目吗？\n\n"
                         f"物理销毁，不可恢复。", icon="warning", parent=root)
        if not ok:
            return
        empty_recycle(db)
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
    sys.exit(main())
