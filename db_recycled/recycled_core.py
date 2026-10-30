# -*- coding: utf-8 -*-
"""回收站核心（v3.1.0）：查看 / 恢复 / 彻底删除。

纯函数式设计，不依赖 GUI，CLI 与 GUI 共用。
主程序只管"删除 = 搬进回收站"（db.py delete_project 分支）；
本模块负责回收站里的一切。

恢复语义：项目原 id 空闲则原样放回（收藏夹索引一并带回）；id 已被
新项目占用才发新 id，收藏夹索引指向新 id。快照 id 一律重新分配
（回收期间主表可能已增长），projects.current_id 同步修正。
彻底删除 = 物理销毁。

注意：SNAPSHOT_FIELDS 通过 _db 动态取 —— db.py 在 import 时
按 fields.json 冻结它，测试/多形态下会被替换，绑定死会拿到错配置。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db as _db                             # noqa: E402


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
