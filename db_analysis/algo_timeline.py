# -*- coding: utf-8 -*-
"""时间线算法（v3.8.0 首版；v3.8.1 返修；v3.8.3 用户贴图定版；
v3.8.4 配置化 + CLI 改版，用户定）：
项目分类时间点可视化——markdown 每项目一张表。

命名定案（2026-11-10 用户定）：**不叫甘特图**。甘特图 = 持续时间条 +
完成百分比 + 依赖关系；本软件只有离散时间点 + 类别，不做进度
评估——给证据不给结论。

v3.8.4 版式与口径（用户定，6 点）：
- 项目名不是列，是**每个表格的第一行**（首格 = 项目名，同行带
  3 个日期值 / 日差 / 状态）；
- 前导列名固定：开始 / 下一个跟进 / 关闭（不用 JSON label）；
- 日差 < 0 时数字标红；
- 头/尾标注列文字 = 「早于26-05」「晚于27-04」（早于第一个月 /
  晚于第 12 个月，带具体年月）；
- 基准四列（开始→今日 / 最近跟进 / 下个跟进 / 关闭）的字段、派生
  「最近跟进」列名、绘图模式（line 两日期连线 / spot 单日期画点）、
  配色全部进 fields.json 的 timeline 段（派生列命名 last_snapshot，
  不属于 fields 的 name）；--cols / --colors 删除；
- CLI 增量：--add-col 字段（额外列 + 对应图行）、--add-plot
  line|spot（额外列的画法）、--add-colors（只给额外列配色）。

铁律：绝不写库（db_analysis 全模块同）。取数当前行口径。
"""

import re
from datetime import date

from .analysis_core import AnalysisError, _parse_where

# 4 行基准线段兜底配色（绿/蓝/橙/紫；JSON timeline.colors 优先）
DEFAULT_COLORS = ["#2e7d32", "#1565c0", "#e65100", "#7b1fa2"]
# 额外列（--add-col）兜底配色轮盘
DEFAULT_ADD_COLORS = ["#c62828", "#00695c", "#5d4037", "#455a64"]
# 每个月的周格数（用户定：4 个 # 分四周）
WEEKS_PER_MONTH = 4
# 日差为负的标红色（用户定）
DIFF_RED = "#c62828"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def load_tl():
    """读并校验 CFG.timeline（config.py 已合并 JSON 配置与
    calendar 法定三类兜底）。返回 dict(start, next, close, last,
    plot, colors)。配置错误抛 AnalysisError。"""
    from config import CFG
    tl = dict(CFG.timeline)
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    for k in ("start", "next", "close"):
        f = tl.get(k)
        if not f or ftypes.get(f) != "date":
            raise AnalysisError(
                f"timeline 配置缺少有效的 {k} 日期字段：{f!r}"
                f"（在 fields.json 的 timeline 段配置）")
    if tl["plot"] not in ("line", "spot"):
        raise AnalysisError(
            f"timeline.plot 只支持 line / spot：{tl['plot']!r}")
    colors = tl["colors"]
    if len(colors) < 4 or any(not _HEX.match(c) for c in colors):
        raise AnalysisError("timeline.colors 需要 4 个 #RRGGBB 颜色")
    return tl


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


def collect(db, adds=(), where=None):
    """当前行口径取数：open + closed 全取（--split 时归「已关闭」章）。
    基准字段取自 CFG.timeline；vals = [开始, 最近跟进(最新快照,
    派生), 下一个跟进, 关闭]；「最近跟进」列名 = timeline.last
    （默认 last_snapshot，不属于 fields 的 name）。
    adds = --add-col 的额外字段名列表（必须是 date 字段）。
    返回 [dict(id,title,status_val,archived,vals,adds,sortmap)]。"""
    from config import CFG
    tl = load_tl()
    for a in adds:
        ft = next((f["type"] for f in CFG.fields if f["name"] == a), None)
        if ft != "date":
            raise AnalysisError(f"--add-col 必须是 date 类型字段：{a}")
    status_field = next((f["name"] for f in CFG.fields
                         if f["type"] == "status"), None)
    base = [tl["start"], tl["next"], tl["close"]]
    sel_cols = base + [a for a in adds if a not in base]
    if status_field and status_field not in sel_cols:
        sel_cols.append(status_field)
    extra = sorted({f["name"] for f in CFG.fields} - set(sel_cols))
    sel = ", ".join(f"s.{c}" for c in sel_cols + extra)
    wheres, args = _where_sql(where)
    wh = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    sql = (f"SELECT p.id, p.title, p.status AS pstatus, "
           f"l.last_at AS last_at, {sel} "
           f"FROM snapshots s "
           f"JOIN projects p ON p.id = s.project_id "
           f"AND s.id = p.current_id "
           f"LEFT JOIN (SELECT project_id, MAX(snapshot_at) AS last_at "
           f"FROM snapshots GROUP BY project_id) l "
           f"ON l.project_id = p.id {wh}")
    rows = []
    for r in db.conn.execute(sql, args).fetchall():
        rows.append({"id": r["id"], "title": r["title"],
                     "status_val": r[status_field] if status_field else "",
                     "archived": r["pstatus"] == "closed",
                     "vals": [r[tl["start"]],
                              r["last_at"][:10] if r["last_at"] else None,
                              r[tl["next"]], r[tl["close"]]],
                     "adds": {a: r[a] for a in adds},
                     "sortmap": {c: r[c] for c in sel_cols + extra},
                     "diff": None})
    return rows


def enrich(rows, today=None):
    """计算日差（timeline.next − 今天，天）并补项目显示名。
    归档项目的 diff 恒为 None。today 可注入（测试确定性）。"""
    from config import CFG
    t = today or date.today()
    name_cols = [c for c in CFG.name_fields if c in CFG.names]
    for row in rows:
        if not row["archived"] and row["vals"][2]:
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


def _seg_cells(start, end, months):
    """line 模式：start→end 的绝对周列集合；任一端缺失 → 空（行保留
    不画线，用户定）；窗外夹边界；start 在 end 之后 → 空。"""
    if not start or not end:
        return set()
    si = _cell_index(start, months)
    ei = _cell_index(end, months)
    if si > ei:
        return set()
    return set(range(si, ei + 1))


def _spot_cells(end, months):
    """spot 模式：只在 end 日期所在周格画一个点（单 #）；
    日期缺失 → 空。"""
    if not end:
        return set()
    return {_cell_index(end, months)}


def _plot_cells(mode, start, end, months):
    if mode == "spot":
        return _spot_cells(end, months)
    return _seg_cells(start, end, months)


def _month_cells(cells):
    """绝对周列集合 → 12 个月格文本，每格 4 字符（# 或空格，对应
    每月 4 周；用户定：月格而不是 48 个编号列）。"""
    return ["".join("#" if mi * WEEKS_PER_MONTH + wk in cells else " "
                    for wk in range(WEEKS_PER_MONTH))
            for mi in range(12)]


def _outside_labels(dates, months):
    """日期列表 → (头标注, 尾标注)：窗外月份存在时头 = 早于第一个月
    （带具体年月）、尾 = 晚于第 12 个月（用户定 v3.8.4）。"""
    lo = (months[0][0], months[0][1])
    hi = (months[-1][0], months[-1][1])
    head = tail = False
    for d in dates:
        if not d:
            continue
        ym = (int(d[:4]), int(d[5:7]))
        if ym < lo:
            head = True
        elif ym > hi:
            tail = True
    first_lab = months[0][2]
    last_lab = months[-1][2]
    return (f"早于{first_lab}" if head else "",
            f"晚于{last_lab}" if tail else "")


def _base_segments(row, today):
    """基准 4 行线段（顺序固定）：(标签, 终点日期)。
    起点恒 = vals[0]（开始）；终点依次为 今日 / 最近跟进(派生) /
    下一个跟进 / 关闭。"""
    return [("今日", today.isoformat()),
            ("最近跟进", row["vals"][1]),
            ("下一个跟进", row["vals"][2]),
            ("关闭", row["vals"][3])]


def _lead(adds, add_labels, months):
    """表头：前导列名固定（用户定：开始/下一个跟进/关闭），额外列用
    JSON label；然后 日差 / 头 + 12 个月列 + 尾 / 状态 / 备注。"""
    return (["开始", "下一个跟进", "关闭"] + add_labels
            + ["日差", "头"] + [lab for _y, _m, lab in months]
            + ["尾", "状态", "备注"])


def _anchor(gname, n):
    """章标题 → GitHub 风格 md 锚点（小写、空格转 -、去掉括号）。"""
    h = f"{gname}（{n} 个项目）"
    h = re.sub(r"[（）()]", "", h)
    return "#" + re.sub(r"\s+", "-", h.strip().lower())


def _diff_text(r):
    """日差文本；< 0 标红（用户定 v3.8.4）。"""
    if r["diff"] is None:
        return ""
    txt = str(r["diff"])
    if r["diff"] < 0:
        return f'<font color="{DIFF_RED}">{txt}</font>'
    return txt


def _render_rows(r, tl, adds, add_labels, add_plot, add_colors,
                 months, t):
    """一个项目的全部表体行（首行 = 项目名行：单独一行、加粗放大、
    不带数据；3 日期值/额外列值/日差/状态在第一行线段行上），已按列
    展开。返回 [[str...]]（不含表头/分隔）。"""
    from config import CFG
    n_lead = 3 + len(adds)
    n_cols = n_lead + 1 + 12 + 3            # 前导 + 日差 + 月格 + 头尾状态备注
    name_row = [f'<font size="5"><b>{r["name"]}</b></font>'] \
        + [""] * (n_cols - 1)
    title = ([""] * n_lead
             + [_diff_text(r), ""] + [""] * 12 + ["",
                                                  r["status_val"] or "", ""])
    # 数据值放第一行线段行的前导列：开始/下一个跟进/关闭 + 额外列
    out = [name_row]
    first_vals = ([r["vals"][0] or "", r["vals"][2] or "",
                   r["vals"][3] or ""]
                  + [r["adds"].get(a) or "" for a in adds])
    segs = [(f"开始-{lab}", end, tl["plot"], tl["colors"][i])
            for i, (lab, end) in enumerate(_base_segments(r, t))]
    for ai, a in enumerate(adds):
        lab = add_labels[ai]
        note = f"开始-{lab}" if add_plot == "line" else lab
        segs.append((note, r["adds"].get(a), add_plot,
                     add_colors[ai % len(add_colors)]))
    for si, (note, end, mode, color) in enumerate(segs):
        start = r["vals"][0] if mode == "line" else None
        cells = _plot_cells(mode, start, end, months)
        head, tail = _outside_labels(
            [start, end] if mode == "line" else [end], months)
        lead_vals = first_vals if si == 0 else [""] * n_lead
        row = lead_vals + [_diff_text(r) if si == 0 else "", head]
        row += [f'<font color="{color}">{c}</font>' if "#" in c else c
                for c in _month_cells(cells)]
        row += [tail, "",
                r["status_val"] if si == 0 and r["status_val"] else "",
                note]
        out.append(row)
    return out


def render_md(rows_groups, tl, adds, add_labels, add_plot, add_colors,
              months, mode_label, today=None, split=False):
    """markdown 文本（用户定，v3.8.4）：每项目一张表；第一行 = 项目名
    （单独一行、加粗放大字体、不带数据）；第一行线段行带 3 日期值/
    额外列值/日差(负标红)/状态；其余线段行只有 # 线 + 头尾标注
    （早于/晚于）+ 备注；基准段字段/画法/色在 JSON timeline 段；
    --split 时文首给章导航超链接。"""
    t = today or date.today()
    lead = _lead(adds, add_labels, months)
    sep = ["---"] * len(lead)
    out = [f"# 项目时间线图（{mode_label}）\n"]
    if split:
        out.append("  ".join(f"[{n}（{len(g)} 个项目）]({_anchor(n, len(g))})"
                             for n, g in rows_groups) + "\n")
    legend = [f'<font color="{tl["colors"][i]}">■</font>开始-{lab}'
              for i, (lab, _e) in enumerate(_base_segments(
                  {"vals": [None] * 4}, t))]
    legend += [f'<font color="{add_colors[i % len(add_colors)]}">■</font>'
               + (f"开始-{lab}" if add_plot == "line" else lab)
               for i, lab in enumerate(add_labels)]
    out.append("  ".join(legend) + "\n")
    for gname, grows in rows_groups:
        out.append(f"## {gname}（{len(grows)} 个项目）\n")
        for r in grows:
            out.append("| " + " | ".join(lead) + " |")
            out.append("|" + "|".join(sep) + "|")
            for row in _render_rows(r, tl, adds, add_labels, add_plot,
                                    add_colors, months, t):
                out.append("| " + " | ".join(row) + " |")
            out.append("")
    return "\n".join(out)


def dump_csv_text(rows_groups, tl, adds, add_labels, add_plot, add_colors,
                  months, today=None):
    """csv 文本（--dump 终端打印用）：与 md 同网格，纯 # 不着色。"""
    t = today or date.today()
    lead = _lead(adds, add_labels, months)
    out = [",".join(lead)]
    for gname, grows in rows_groups:
        out.append(f"# {gname}（{len(grows)} 个项目）")
        for r in grows:
            for row in _csv_rows(r, tl, adds, add_labels, add_plot,
                                 add_colors, months, t):
                out.append(",".join(row))
    return "\n".join(out)


def _csv_rows(r, tl, adds, add_labels, add_plot, add_colors, months, t):
    """一个项目的 csv 表体行（与 _render_rows 同结构，纯 # 无颜色）。"""
    n_lead = 3 + len(adds)
    out = [[r["name"]] + [""] * (n_lead + 1 + 12 + 3 - 1)]   # 项目名行
    first_vals = ([r["vals"][0] or "", r["vals"][2] or "",
                   r["vals"][3] or ""]
                  + [r["adds"].get(a) or "" for a in adds])
    segs = [(lab, end, tl["plot"])
            for lab, end in _base_segments(r, t)]
    for ai, a in enumerate(adds):
        lab = add_labels[ai]
        note = f"开始-{lab}" if add_plot == "line" else lab
        segs.append((note, r["adds"].get(a), add_plot))
    for si, (note, end, mode) in enumerate(segs):
        start = r["vals"][0] if mode == "line" else None
        cells = _plot_cells(mode, start, end, months)
        head, tail = _outside_labels(
            [start, end] if mode == "line" else [end], months)
        lead_vals = first_vals if si == 0 else [""] * n_lead
        out.append(lead_vals
                   + [str(r["diff"]) if si == 0 and r["diff"] is not None
                      else "", head]
                   + _month_cells(cells)
                   + [tail, "",
                      r["status_val"] if si == 0 and r["status_val"] else "",
                      note])
    return out
