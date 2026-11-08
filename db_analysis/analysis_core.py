# -*- coding: utf-8 -*-
"""db_analysis 内核：只读分析共享层（v3.5.0）。

铁律：绝不写库——本模块只发 SELECT。算法插件（algo_*.py）在此层
之上组合出各子命令的 cmd_* 函数（仿 workbench_ui 的 cmd_ 内核风格：
参数已解析好，业务错误抛 AnalysisError，由 CLI 端转退出码 1）。

日期区间语义（2026-11-07 用户定）：给定区间时，每个项目取窗口内
"当时最新"的一条快照来统计（按 snapshot_at 取最大）；不给区间时
用当前行（projects.current_id），与列表默认口径一致。
"""

from config import CFG


class AnalysisError(Exception):
    """业务错误：CLI 端捕获后打印 stderr、退出码 1（无 traceback）。"""


# ---------- 数据口径 ----------

def _pick_snapshot_sql(date_field, d1, d2):
    """按日期口径拼"每项目取哪条快照"的条件片段。

    返回 (where_sql, args)。date_field=None 表示当前行口径。
    """
    if date_field is None:
        return "s.id = p.current_id", []
    col = "snapshot_at" if date_field == "__snap__" else date_field
    sql = (f"s.id = (SELECT s2.id FROM snapshots s2 "
           f"WHERE s2.project_id = s.project_id "
           f"AND date(s2.{col}) BETWEEN ? AND ? "
           f"ORDER BY s2.snapshot_at DESC, s2.id DESC LIMIT 1)")
    return sql, [d1, d2]


def _parse_where(items):
    """--where 语法与 workbench_ui 对齐：字段=值（可多次，同字段
    取并集、异字段取交集）、日期字段=起~止（任一端可省略）。
    返回 {字段: set(值)} 与 [(字段, d1, d2)]。"""
    filters, ranges = {}, []
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    for item in items or []:
        if "=" not in item:
            raise AnalysisError(f"--where 需要 字段=值 形式：{item!r}")
        name, _, raw = item.partition("=")
        name = name.strip()
        if name not in ftypes:
            raise AnalysisError(f"不存在的字段：{name}"
                                f"（可用：{'、'.join(CFG.names)}）")
        if ftypes[name] == "date" and "~" in raw:
            d1, _, d2 = raw.partition("~")
            ranges.append((name, d1.strip() or None, d2.strip() or None))
        else:
            filters.setdefault(name, set()).add(raw.strip())
    return filters, ranges


def _validate_field(field):
    """饼图字段必须存在且不是 date 类型（date 分段无意义）。"""
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    if field not in ftypes:
        raise AnalysisError(f"--field 不存在的字段：{field}"
                            f"（可用：{'、'.join(CFG.names)}）")
    if ftypes[field] == "date":
        raise AnalysisError(f"--field 不支持 date 类型字段：{field}"
                            "（日期请用 --date-field/--from/--to 做区间筛选）")
    return ftypes[field]


def collect_rows(db, field, closed=False, where=None,
                 date_field=None, d1=None, d2=None):
    """按口径取数：返回该字段的原始取值列表（含 None/空串，未归段）。"""
    _validate_field(field)
    filters, ranges = _parse_where(where)
    pick_sql, pick_args = _pick_snapshot_sql(date_field, d1, d2)
    wheres = [pick_sql]
    args = list(pick_args)
    if not closed:
        wheres.append("p.status = 'open'")
    for name, vals in filters.items():
        marks = ",".join("?" * len(vals))
        wheres.append(f"(s.{name} IN ({marks})"
                      f" OR (s.{name} IS NULL AND '' IN ({marks})))")
        args.extend(list(vals) + list(vals))
    for name, r1, r2 in ranges:
        if r1:
            wheres.append(f"date(s.{name}) >= date(?)")
            args.append(r1)
        if r2:
            wheres.append(f"date(s.{name}) <= date(?)")
            args.append(r2)
    sql = (f"SELECT s.{field} FROM snapshots s "
           f"JOIN projects p ON p.id = s.project_id "
           f"WHERE {' AND '.join(wheres)}")
    return [r[0] for r in db.conn.execute(sql, args).fetchall()]


def aggregate(values, top=9):
    """原始取值 → 饼图段：空值归「（空）」，计数降序，
    超过 top 个段时长尾合并「其他」。返回 [(段名, 计数), ...]。"""
    counts = {}
    for v in values:
        key = str(v) if v not in (None, "") else "（空）"
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) > top:
        head, tail = ordered[:top], ordered[top:]
        merged = sum(n for _k, n in tail)
        ordered = head + [("其他", merged)]
    return ordered
