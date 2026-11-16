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
from db import normalize_date


class AnalysisError(Exception):
    """业务错误异常。

    db_analysis 各层抛出的可预期错误一律是 AnalysisError；CLI 端捕获
    后打印 stderr、退出码 1（无 traceback）。
    """


# ---------- 数据口径 ----------

def _pick_snapshot_sql(date_field, d1, d2):
    """按日期口径拼"每项目取哪条快照"的 SQL 条件片段。

    date_field=None 表示当前行口径（s.id = p.current_id，与列表默认口径
    一致）；否则取窗口内 snapshot_at 最大的一条（相关子查询）。

    :param date_field: 日期字段名，"__snap__" = 快照时间本身，None = 当前行。
    :type date_field: str 或 None
    :param d1: 区间起点（date_field 非 None 时必填）。
    :type d1: str
    :param d2: 区间终点。
    :type d2: str
    :return: (where 条件 SQL, 参数列表)。
    :rtype: tuple
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
    """--where 语法解析（与 workbench_ui 对齐）。

    字段=值（可多次，同字段取并集、异字段取交集）；日期字段=起~止（任
    一端可省略；v3.8.14 起非日期字段用 ~ 明确报错，非法日期/反向区间
    不再静默落到误导性的空结果）。错误立即 raise。

    :param items: 原始 --where 字符串列表，可为 None。
    :type items: list 或 None
    :return: ({字段: set(值)}, [(字段, d1 或 None, d2 或 None)])。
    :rtype: tuple
    :raises AnalysisError: 格式错、字段不存在或区间非法时。
    """
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
        if "~" in raw:
            # v3.8.14：与 workbench_ui 对齐——非日期字段用 ~ 明确报错，
            # 非法日期/反向区间不再静默落到误导性的空结果
            if ftypes[name] != "date":
                raise AnalysisError(f"字段 {name} 不是日期字段，"
                                    f"不能用 ~ 区间：{item!r}")
            d1, _, d2 = raw.partition("~")
            d1 = normalize_date(d1.strip()) if d1.strip() else None
            d2 = normalize_date(d2.strip()) if d2.strip() else None
            if d1 is None and d2 is None:
                raise AnalysisError(f"区间不是有效日期：{raw!r}（应为 "
                                    f"起~止，任一端可省略）")
            if d1 and d2 and d1 > d2:
                raise AnalysisError(f"区间起点晚于终点：{d1}~{d2}")
            ranges.append((name, d1, d2))
        else:
            filters.setdefault(name, set()).add(raw.strip())
    return filters, ranges


def _validate_field(field):
    """校验统计字段存在并返回其类型。

    date 类型自 v3.5.1 起允许作为饼图变量——按原始日期值分段（配合
    --top/「其他」兜长尾）。

    :param field: 字段英文 name。
    :type field: str
    :return: 字段类型（ftypes 值）。
    :rtype: str
    :raises AnalysisError: 字段不存在时。
    """
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    if field not in ftypes:
        raise AnalysisError(f"--field 不存在的字段：{field}"
                            f"（可用：{'、'.join(CFG.names)}）")
    return ftypes[field]


def collect_rows(db, field, closed=False, where=None,
                 date_field=None, d1=None, d2=None):
    """按口径取数：返回该字段的原始取值列表（含 None/空串，未归段）。

    口径链：_validate_field -> _parse_where -> _pick_snapshot_sql；默认
    只取 open 项目（closed=True 含归档）。单值筛选带空值兜底
    （NULL 视为 '' 参与 IN），日期区间用 date() 比较。

    :param db: 已打开的库。
    :type db: db.Database
    :param field: 统计字段英文 name。
    :type field: str
    :param closed: 是否含已归档项目。
    :type closed: bool
    :param where: --where 原始参数列表。
    :type where: list 或 None
    :param date_field: 日期区间作用的列（"__snap__" = 快照时间）。
    :type date_field: str 或 None
    :param d1: 区间起点。
    :type d1: str 或 None
    :param d2: 区间终点。
    :type d2: str 或 None
    :return: 原始取值列表。
    :rtype: list
    """
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
    """原始取值 -> 饼图段：空值归「（空）」，计数降序，长尾合并「其他」。

    :param values: 原始取值列表。
    :type values: list
    :param top: 段数上限，超出合并为「其他」。
    :type top: int
    :return: [(段名, 计数), ...]，按计数降序（同计数按段名字典序）。
    :rtype: list
    """
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
