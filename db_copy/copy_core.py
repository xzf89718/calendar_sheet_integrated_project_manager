# -*- coding: utf-8 -*-
"""复制器核心：把源库中选中的项目（含全部历史快照）追加为目标库的新项目。

纯函数式设计，不依赖 GUI，方便测试。
规则：
  - 只新增，绝不修改/删除目标库任何已有数据
  - 项目与快照在目标库获得全新 id；快照的 snapshot_at/内容原样保留
  - 复制携带完整历史；"当前状态"指向时间最新的那条快照
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Database, SNAPSHOT_FIELDS          # noqa: E402


def list_projects(db):
    """项目清单：[(pid, 名称, 里程碑, 状态, 快照数, 最近更新)]"""
    sql = """
    SELECT p.id, p.title,
           cur.milestone AS milestone, cur.status AS status,
           agg.cnt AS snap_count, agg.mx AS last_at
    FROM projects p
    LEFT JOIN snapshots cur ON cur.id = p.current_id
    LEFT JOIN (SELECT project_id, COUNT(*) AS cnt,
                      MAX(snapshot_at) AS mx
               FROM snapshots GROUP BY project_id) agg
           ON agg.project_id = p.id
    ORDER BY p.id
    """
    return db.conn.execute(sql).fetchall()


def check_compatible(db_a, db_b):
    """两库字段兼容性检查：目标库必须包含当前配置的全部字段列。"""
    need = set(SNAPSHOT_FIELDS)
    cols_b = {r[1] for r in db_b.conn.execute(
        "PRAGMA table_info(snapshots)")}
    missing = need - cols_b
    if missing:
        return False, f"目标库缺少字段列：{sorted(missing)}（两库配置不一致）"
    return True, ""


def copy_projects(db_a, db_b, pids):
    """把 pids 项目从 A 追加到 B。返回 (项目数, 快照数)。

    全部插入在一个事务里，失败整体回滚。
    """
    n_proj = n_snap = 0
    cols = SNAPSHOT_FIELDS
    with db_b.conn:
        for pid in pids:
            p = db_a.get_project(pid)
            snaps = db_a.get_snapshots(pid)
            if not snaps:
                continue
            cur = db_b.conn.execute(
                "INSERT INTO projects(title, status, created_at) "
                "VALUES (?, ?, ?)",
                (p["title"], p["status"], p["created_at"]))
            new_pid = cur.lastrowid
            last_sid = None
            for s in snaps:
                vals = [s[c] for c in cols]
                cur = db_b.conn.execute(
                    f"INSERT INTO snapshots(project_id, snapshot_at, "
                    f"{','.join(cols)}, changed_by, change_summary) "
                    f"VALUES (?, ?, {','.join('?' * len(cols))}, ?, ?)",
                    [new_pid, s["snapshot_at"]] + vals
                    + [s["changed_by"], s["change_summary"]])
                last_sid = cur.lastrowid
                n_snap += 1
            # 当前状态 = 时间最新的快照（最后插入的那条）
            db_b.conn.execute(
                "UPDATE projects SET current_id=? WHERE id=?",
                (last_sid, new_pid))
            n_proj += 1
    return n_proj, n_snap
