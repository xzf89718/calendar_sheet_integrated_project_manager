# -*- coding: utf-8 -*-
"""多库追加核心：把若干个源库的项目（含全部历史快照）依次追加进目标库。

纯函数式设计，不依赖 GUI。与 db_copy 同一套复制语义：
  - 只新增，绝不修改/删除目标库已有数据
  - 快照时间/内容原样保留；当前状态指向最新一条
  - 每个源库一个事务，失败回滚该源、已完成的源保留
前提：所有库使用同一份 fields.json（团队统一格式）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Database, SNAPSHOT_FIELDS          # noqa: E402


def list_projects(db):
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


def check_compatible(db_src, db_target):
    need = set(SNAPSHOT_FIELDS)
    cols = {r[1] for r in db_target.conn.execute(
        "PRAGMA table_info(snapshots)")}
    missing = need - cols
    if missing:
        return False, f"目标库缺少字段列：{sorted(missing)}（配置不一致）"
    return True, ""


def copy_projects(db_src, db_target, pids):
    """单库内把 pids 项目追加到目标库。返回 (项目数, 快照数)。"""
    n_proj = n_snap = 0
    cols = SNAPSHOT_FIELDS
    with db_target.conn:
        for pid in pids:
            p = db_src.get_project(pid)
            snaps = db_src.get_snapshots(pid)
            if not snaps:
                continue
            cur = db_target.conn.execute(
                "INSERT INTO projects(title, status, created_at) "
                "VALUES (?, ?, ?)",
                (p["title"], p["status"], p["created_at"]))
            new_pid = cur.lastrowid
            last_sid = None
            for s in snaps:
                vals = [s[c] for c in cols]
                cur = db_target.conn.execute(
                    f"INSERT INTO snapshots(project_id, snapshot_at, "
                    f"{','.join(cols)}, changed_by, change_summary) "
                    f"VALUES (?, ?, {','.join('?' * len(cols))}, ?, ?)",
                    [new_pid, s["snapshot_at"]] + vals
                    + [s["changed_by"], s["change_summary"]])
                last_sid = cur.lastrowid
                n_snap += 1
            db_target.conn.execute(
                "UPDATE projects SET current_id=? WHERE id=?",
                (last_sid, new_pid))
            n_proj += 1
    return n_proj, n_snap


def append_sources(db_target, db_sources):
    """把多个源库依次全部追加进目标库。

    返回 (总项目数, 总快照数, [每个源的明细...])。
    """
    total_p = total_s = 0
    details = []
    for src in db_sources:
        fname = src.conn.execute("PRAGMA database_list").fetchone()[2]
        fname = os.path.basename(fname) if fname else "?"
        pids = [r["id"] for r in list_projects(src)]
        np_, ns = copy_projects(src, db_target, pids)
        total_p += np_
        total_s += ns
        details.append((fname, np_, ns))
    return total_p, total_s, details
