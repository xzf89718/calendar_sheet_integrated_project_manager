# -*- coding: utf-8 -*-
"""批量赋值核心：对一批项目统一给某列赋值。

铁律：**不直接改数据**。每个项目生成一条新快照（走跟进方法），
赋值动作全程可追溯、可对比、可回溯。纯函数设计，不依赖 GUI。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import Database, SNAPSHOT_FIELDS, diff_summary  # noqa: E402
from config import CFG                              # noqa: E402


def all_project_ids(db):
    """库内全部项目 id（赋值作用域 = 整个库，刻意不做子集选择）。"""
    return [r[0] for r in db.conn.execute("SELECT id FROM projects")]


def assign_value(db, pids, field, value, changed_by="批量赋值"):
    """对 pids 逐项目追加一条快照：field 列 = value，其余保持当前值。

    返回 (成功项目数, 失败列表[(pid, 错误)])。
    一个事务，全部成功或全部回滚。
    """
    ok, fails = 0, []
    with db.conn:
        for pid in pids:
            try:
                cur = db.get_current(pid)
                if cur is None:
                    fails.append((pid, "无快照"))
                    continue
                fields = {f: cur[f] for f in SNAPSHOT_FIELDS}
                fields[field] = value if value != "" else None
                summary = f"批量赋值: {CFG.labels.get(field, field)} → " \
                          f"{value or '(清空)'}"
                db._insert_snapshot(pid, changed_by, summary, fields)
                ok += 1
            except Exception as e:                    # noqa: BLE001
                fails.append((pid, str(e)))
    return ok, fails
