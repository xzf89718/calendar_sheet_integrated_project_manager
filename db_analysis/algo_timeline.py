# -*- coding: utf-8 -*-
"""时间线算法（v3.8.0 首版；v3.8.1 用户返修重排）：
项目分类时间点可视化——markdown 每项目一张表。

命名定案（2026-11-10 用户定）：**不叫甘特图**。甘特图 = 持续时间条 +
完成百分比 + 依赖关系；本软件只有离散时间点 + 类别，不做进度
评估——给证据不给结论。

v3.8.1 布局（用户定）：
- 非 dump 模式终端不打印 md 本体，只打印筛选条件 + 统计 +
  写出路径（md 恒写出为文件）；--dump 才把 csv 文本打到终端；
- 每项目一张独立表（表头分开，不再拼成大表）；
- 4 个日期值 + 状态列在同一行（不再 4 行错开），状态列在最后；
- 月网格 = 12 个月 × 4 周列；从**开始日期**起逐周画 `#` 连成线——
  终点：已关闭 → 关闭日期（无关闭 = 单点）；进行中 → 下个跟进，
  无下个跟进 → 拖到窗口尾；开始日期在窗外则夹到边界起线，窗外
  日期标注在头/尾列；
- 头、尾各一个窗外标注列，与 12 个月块之间断开 4 个空列；
- 4 个日期列由 CLI 强制指定（--cols required），不自动推导。

铁律：绝不写库（db_analysis 全模块同）。取数当前行口径。
"""

from datetime import date

from .analysis_core import AnalysisError, _parse_where

# 连线与图例默认配色（绿/蓝/橙/红，CLI 可覆盖；连线用 colors[0]）
DEFAULT_COLORS = ["#2e7d32", "#1565c0", "#e65100", "#c62828"]
# 每个月的周列数（用户定：4 个 # 分四周）
WEEKS_PER_MONTH = 4
# 窗外列与 12 个月块之间断开的空列数（用户定）
GAP_COLS = 4


def validate_cols(cols):
    """4 列逐一校验：必须是存在的字段名且为 date 类型。
    返回 4 个展示名列表（fields.json 的 label）。"""
    from config import CFG
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    labels = CFG.labels
    for c in cols:
        if c not in ftypes:
            raise AnalysisError(f"--cols 不存在的字段：{c}"
                                f"（可用：{'、'.join(CFG.names)}）")
        if ftypes[c] != "date":
            raise AnalysisError(f"--cols 必须是 date 类型字段：{c}")
    return [labels.get(c, c) for c in cols]


def window_months(mode, today=None):
    """12 个月窗口 → [(year, month, 'YY-MM'), ...]。

    year    = 当年 1–12 月；
    rolling = [当月-6, 当月+5]（含当月共 12 列，用户定）。"""
    t = today or date.today()
    if mode == "year":
        y, m0 = t.year, 1
    elif mode == "rolling":
        y, m0 = t.year, t.month - 6
        while m0 < 1:
            m0 += 12
            y -= 1
    else:
        raise AnalysisError(f"--mode 只支持 year / rolling：{mode!r}")
    out = []
    y, m = y, m0
    for _ in range(12):
        out.append((y, m, f"{y - 2000:02d}-{m:02d}"))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _where_sql(where):
    """--where → (wheres, args)（与 analysis_core.collect_rows 同语义：
    单值集合 IN + 空值兜底；日期区间 date() 比较）。"""
    filters, ranges = _parse_where(where)
    wheres, args = [], []
    for name, vals in filters.items():
        marks = ",".join("?" * len(vals))
        wheres.append(f"(s.{name} IN ({marks})"
                      f" OR (s.{name} IS NULL AND '' IN ({marks})))")
        args.extend(list(vals) + list(vals))
    for name, r1, r2 in ranges:
        if r1:
            wheres.append("date(s.%s) >= date(?)" % name)
            args.append(r1)
        if r2:
            wheres.append("date(s.%s) <= date(?)" % name)
            args.append(r2)
    return wheres, args


def collect(db, cols, where=None):
    """当前行口径取数：open + closed 全取（--split 时归「已关闭」章）。
    返回 [dict(id,title,status_val,archived,vals=[4 个日期或 None],
    sortmap)]；status_val = 快照里 type=status 字段的显示值（md 状态列）。"""
    from config import CFG
    status_field = next((f["name"] for f in CFG.fields
                         if f["type"] == "status"), None)
    sel_cols = list(cols)
    if status_field and status_field not in sel_cols:
        sel_cols.append(status_field)
    extra = sorted({f["name"] for f in CFG.fields} - set(sel_cols))
    sel = ", ".join(f"s.{c}" for c in sel_cols + extra)
    wheres, args = _where_sql(where)
    wh = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    sql = (f"SELECT p.id, p.title, p.status AS pstatus, {sel} "
           f"FROM snapshots s JOIN projects p ON p.id = s.project_id "
           f"AND s.id = p.current_id {wh}")
    rows = []
    for r in db.conn.execute(sql, args).fetchall():
        rows.append({"id": r["id"], "title": r["title"],
                     "status_val": r[status_field] if status_field else "",
                     "archived": r["pstatus"] == "closed",
                     "vals": [r[c] for c in cols],
                     "sortmap": {c: r[c] for c in sel_cols + extra},
                     "diff": None})
    return rows


def enrich(rows, cols, today=None):
    """计算日差（cols 第三列 − 今天，天）并补项目显示名。
    归档项目的 diff 恒为 None。today 可注入（测试确定性）。"""
    from config import CFG
    t = today or date.today()
    name_cols = [c for c in CFG.name_fields if c in CFG.names]
    for row in rows:
        if not row["archived"] and len(cols) >= 3 and row["vals"][2]:
            d0 = date.fromisoformat(row["vals"][2])
            row["diff"] = (d0 - t).days
        name = "-".join(str(row["sortmap"].get(c) or "")
                        for c in name_cols).strip("-")
        row["name"] = name or row["title"]
    return rows


def split_groups(rows):
    """四章划分（用户定，顺序固定）：逾期未跟进（diff<0）→
    待跟进（diff>=0）→ 未排跟进（无下个跟进）→ 已关闭（归档）。
    返回 [(章名, [row...])]，空章不出现。"""
    overdue, due, unscheduled, archived = [], [], [], []
    for r in rows:
        if r["archived"]:
            archived.append(r)
        elif r["diff"] is None:
            unscheduled.append(r)
        elif r["diff"] < 0:
            overdue.append(r)
        else:
            due.append(r)
    out = []
    for name, g in (("逾期未跟进", overdue), ("待跟进", due),
                    ("未排跟进", unscheduled), ("已关闭", archived)):
        if g:
            out.append((name, g))
    return out


def sort_rows(rows, key=None, desc=False):
    """章内排序：key=None/diff 按日差；库字段按原始值。None/空值
    恒排最后（与升降序无关）。"""
    if key is None or key == "diff":
        def bad(r):
            return r["diff"] is None

        def keyv(r):
            return r["diff"]
    else:
        def bad(r):
            return r["sortmap"].get(key) in (None, "")

        def keyv(r):
            return str(r["sortmap"].get(key) or "")
    head = [r for r in rows if not bad(r)]
    head.sort(key=keyv, reverse=desc)
    rows[:] = head + [r for r in rows if bad(r)]
    return rows


def _ym_week(dstr):
    """'YYYY-MM-DD' → ((year, month), week0-3)；week = (day-1)//7。"""
    return (int(dstr[:4]), int(dstr[5:7])), (int(dstr[8:10]) - 1) // 7


def _cell_index(dstr, months):
    """日期 → 月网格绝对周列 idx；窗外日期夹到 0 / 最后一列。"""
    ym, wk = _ym_week(dstr)
    hit = [i for i, (y, m, _l) in enumerate(months) if (y, m) == ym]
    if not hit:
        return 0 if ym < (months[0][0], months[0][1]) \
            else len(months) * WEEKS_PER_MONTH - 1
    return hit[0] * WEEKS_PER_MONTH + min(wk, WEEKS_PER_MONTH - 1)


def _outside(row, months):
    """(头月份列表, 尾月份列表)：4 个日期里落在窗口外的，去重排序。"""
    head, tail = [], []
    lo = (months[0][0], months[0][1])
    hi = (months[-1][0], months[-1][1])
    for d in row["vals"]:
        if not d:
            continue
        ym = (int(d[:4]), int(d[5:7]))
        tag = f"{ym[0]}-{ym[1]:02d}"
        if ym < lo:
            head.append(tag)
        elif ym > hi:
            tail.append(tag)
    return sorted(set(head)), sorted(set(tail))


def _line_cols(row, months):
    """连线占的 (月idx, 周idx) 集合 + (头月份, 尾月份)。
    起点 = cols[0]（开始）；终点：已关闭 → cols[3]（无则单点）；
    进行中 → cols[2]，无则拖到窗口尾。起点缺失 → 空线。"""
    start = row["vals"][0]
    if not start:
        return set(), _outside(row, months)
    if row["archived"]:
        end = row["vals"][3] or start
    else:
        end = row["vals"][2]
    si = _cell_index(start, months)
    ei = _cell_index(end, months) if end \
        else len(months) * WEEKS_PER_MONTH - 1
    cells = set()
    for c in range(min(si, ei), max(si, ei) + 1):
        cells.add((c // WEEKS_PER_MONTH, c % WEEKS_PER_MONTH))
    return cells, _outside(row, months)


def _month_grid_header(months):
    """12 个月 × 4 周列表头：每月首列挂月份标签，其余空。"""
    head, sep = [], []
    for _y, _m, label in months:
        head += [label, "", "", ""]
        sep += ["---"] * WEEKS_PER_MONTH
    return head, sep


def _grid_cells(line_cells):
    """(月,周) 集合 → 12×4 的格子文本列表（# 或空）。"""
    return ["#" if (mi, wk) in line_cells else ""
            for mi in range(12) for wk in range(WEEKS_PER_MONTH)]


def _lead_header(col_labels, months):
    """前导列（项目/日差/4 日期/状态）+ 头列 + 4 空列 + 48 周列 +
    4 空列 + 尾列（窗外区域与月块两侧各断开 4 列，用户定）。"""
    head_m, sep_m = _month_grid_header(months)
    lead = ["项目", "日差"] + col_labels + ["状态", "头"] \
        + [""] * GAP_COLS + head_m + [""] * GAP_COLS + ["尾"]
    lead_sep = ["---"] * (6 + 2 + 2 * GAP_COLS) + sep_m
    return lead, lead_sep


def _lead_row(r, head_out):
    return [r["name"],
            str(r["diff"]) if r["diff"] is not None else "",
            ] + [v or "" for v in r["vals"]] \
        + [r["status_val"] or "", head_out]


def render_md(rows_groups, col_labels, months, colors, mode_label):
    """markdown 文本：每项目一张表；# 连线用 colors[0] 着色。"""
    lead, lead_sep = _lead_header(col_labels, months)
    out = [f"# 项目时间线图（{mode_label}）\n"]
    out.append("  ".join(f'<font color="{colors[i]}">■</font>'
                         f'{col_labels[i]}' for i in range(4)) + "\n")
    for gname, grows in rows_groups:
        out.append(f"## {gname}（{len(grows)} 个项目）\n")
        for r in grows:
            line_cells, (head_out, tail_out) = _line_cols(r, months)
            grid = [f'<font color="{colors[0]}">{c}</font>' if c else ""
                    for c in _grid_cells(line_cells)]
            row = _lead_row(r, "、".join(head_out)) \
                + [""] * GAP_COLS + grid + [""] * GAP_COLS \
                + ["、".join(tail_out)]
            out.append("### " + r["name"] + "\n")
            out.append("| " + " | ".join(lead) + " |")
            out.append("|" + "|".join(lead_sep) + "|")
            out.append("| " + " | ".join(row) + " |")
            out.append("")
    return "\n".join(out)


def dump_csv_text(rows_groups, col_labels, months):
    """csv 文本（--dump 终端打印用）：与 md 同网格，纯 # 不着色。"""
    lead, _sep = _lead_header(col_labels, months)
    out = [",".join(lead)]
    for gname, grows in rows_groups:
        out.append(f"# {gname}（{len(grows)} 个项目）")
        for r in grows:
            line_cells, (head_out, tail_out) = _line_cols(r, months)
            row = _lead_row(r, "、".join(head_out)) \
                + [""] * GAP_COLS + _grid_cells(line_cells) \
                + [""] * GAP_COLS + ["、".join(tail_out)]
            out.append(",".join(row))
    return "\n".join(out)
