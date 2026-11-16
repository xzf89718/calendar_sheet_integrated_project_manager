# -*- coding: utf-8 -*-
"""split_by_key 核心：把源库按某列的取值拆成多个库文件。

规则（设计定稿）：
  - 全量分拆：进行中与已归档全部分走（归档项目只留源库会丢在退休基线）
  - 键值为空 -> "未分配.db"
  - 目标文件已存在 -> 报错拒绝（防手滑覆盖）
  - 复制语义与 db_append 完全一致（复用其 copy_projects：只新增、
    历史全带、ID 重编），纯函数设计。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import Database                     # noqa: E402
from db_append.append_core import copy_projects  # noqa: E402


def list_keys(db, key_field):
    """该列的全部取值（None 也算一个键，排最前）。

    :param db: 已打开的源库。
    :type db: db.Database
    :param key_field: 键列字段名。
    :type key_field: str
    :return: 键值列表（None 排最前）。
    :rtype: list
    """
    rows = db.conn.execute(
        f"""SELECT DISTINCT cur.{key_field} FROM projects p
            JOIN snapshots cur ON cur.id = p.current_id
            ORDER BY cur.{key_field} IS NOT NULL, cur.{key_field}"""
    ).fetchall()
    return [r[0] for r in rows]


def preview(db, key_field):
    """预览：{键值: 项目数}（None 显示为 未分配）。

    :param db: 已打开的源库。
    :type db: db.Database
    :param key_field: 键列字段名。
    :type key_field: str
    :return: {键值字符串: 项目数}。
    :rtype: dict
    """
    rows = db.conn.execute(
        f"""SELECT cur.{key_field}, COUNT(*) FROM projects p
            JOIN snapshots cur ON cur.id = p.current_id
            GROUP BY cur.{key_field}
            ORDER BY cur.{key_field} IS NOT NULL, cur.{key_field}"""
    ).fetchall()
    return {("" if k is None else str(k)): n for k, n in rows}


def build_filename(key, field_label, when=None, cfg=None):
    """按 JSON 配方拼输出文件名：components 顺序 + prefix。

    组成部分：prefix(前缀文本)/field(键列名)/key(键值,空→未分配)/
    time(时间戳 YYYYMMDD-HHMMSS)。空段自动跳过，非法文件名字符清洗。

    :param key: 键值，空/None → "未分配"。
    :type key: str
    :param field_label: 键列显示名。
    :type field_label: str
    :param when: 时间戳基准时间，None = 现在。
    :type when: datetime.datetime 或 None
    :param cfg: 配置对象（取 split_components/split_prefix），None = CFG。
    :type cfg: config.Config 或 None
    :return: 输出文件名（含 .db 后缀）。
    :rtype: str
    """
    from datetime import datetime
    from config import CFG
    cfg = cfg or CFG
    parts = []
    for comp in getattr(cfg, "split_components", ["field", "key", "time"]):
        if comp == "prefix":
            v = str(getattr(cfg, "split_prefix", "") or "").strip()
        elif comp == "field":
            v = str(field_label or "")
        elif comp == "key":
            v = str(key if key else "未分配")
        elif comp == "time":
            v = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
        else:
            v = ""
        if v:
            parts.append(v)
    name = "_".join(parts) or "split"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name + ".db"


def split_by_key(db_src, dest_dir, key_field, safe=True):
    """按 key_field 拆分源库到 dest_dir。

    文件名由 fields.json 的 split 段配方生成（build_filename）。
    safe=True 时目标文件已存在则报错拒绝。

    :param db_src: 已打开的源库。
    :type db_src: db.Database
    :param dest_dir: 输出目录。
    :type dest_dir: str
    :param key_field: 键列字段名。
    :type key_field: str
    :param safe: 目标文件已存在时是否拒绝（True = 拒绝）。
    :type safe: bool
    :return: {文件名: (项目数, 快照数)}。
    :rtype: dict
    :raises FileExistsError: safe=True 且目标文件已存在时。
    """
    from config import CFG
    os.makedirs(dest_dir, exist_ok=True)
    field_label = CFG.labels.get(key_field, key_field)
    groups = {}
    for pid, key in db_src.conn.execute(
            f"""SELECT p.id, cur.{key_field} FROM projects p
                JOIN snapshots cur ON cur.id = p.current_id"""):
        groups.setdefault("" if key is None else str(key), []).append(pid)
    result = {}
    for key, pids in groups.items():
        fname = build_filename(key, field_label)
        fpath = os.path.join(dest_dir, fname)
        if safe and os.path.exists(fpath):
            raise FileExistsError(f"目标已存在，拒绝覆盖：{fpath}")
        target = Database(fpath)
        n_p, n_s = copy_projects(db_src, target, pids)
        target.close()
        result[fname] = (n_p, n_s)
    return result
