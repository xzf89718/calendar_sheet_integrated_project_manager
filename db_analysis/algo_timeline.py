# -*- coding: utf-8 -*-
"""时间线算法（v3.8.0 首版；v3.8.1 返修；v3.8.3 用户贴图重排定版）：
项目分类时间点可视化——markdown 每项目一张表。

命名定案（2026-11-10 用户定）：**不叫甘特图**。甘特图 = 持续时间条 +
完成百分比 + 依赖关系；本软件只有离散时间点 + 类别，不做进度
评估——给证据不给结论。

v3.8.3 版式（用户贴图定，替代 v3.8.1 单行长线版；同日 5 点返修）：
- 每项目一张表（无单独小标题，用户定），表内 4 行线段，顺序固定：
  开始-今日 / 开始-最近跟进 / 开始-下个跟进 / 开始-关闭；
  行 # 线各用一种颜色（默认绿/蓝/橙/紫，用户定：橙红太近）；
- 任一线段两端有缺失 → 该行不画线，但保留行位置（用户定）；
- 首行带项目名（JSON name 字段拼合）/日差/3 日期值/状态，其余行
  只有 # 线 + 备注；备注列 = 线段标签（开始-今日 等）；
- 月格 = 12 个月列，每格 4 字符（# 或空格，每月 4 周）；窗口外的
  月份写进头/尾两个标注列（各一个，表示显示不完，用户定）；窗外
  日期夹到边界画线；--split 时文首给章导航超链接（用户定）。
- 3 个日期列由 CLI 强制指定（--cols required：开始 / 下个跟进 /
  关闭）；「最近跟进」是派生量——程序自动取该项目最新快照时间，
  不需要也不允许用户指定（v3.8.3 用户定）。

铁律：绝不写库（db_analysis 全模块同）。取数当前行口径。
"""

from datetime import date

from .analysis_core import AnalysisError, _parse_where

# 4 行线段默认配色（绿/蓝/橙/红，CLI 可覆盖；第 i 行用 colors[i]）
DEFAULT_COLORS = ["#2e7d32", "#1565c0", "#e65100", "#7b1fa2"]
# 每个月的周列数（用户定：4 个 # 分四周）
WEEKS_PER_MONTH = 4


def validate_cols(cols):
    """3 列逐一校验：必须是存在的字段名且为 date 类型。返回 4 个
    展示名（开始 / 最后跟进 / 下个跟进 / 关闭）——最后跟进是派生
    列，固定字面量，不参与 --cols（v3.8.3 用户定）。"""
    from config import CFG
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    labels = CFG.labels
    for c in cols:
        if c not in ftypes:
            raise AnalysisError(f"--cols 不存在的字段：{c}"
                                f"（可用：{'、'.join(CFG.names)}）")
        if ftypes[c] != "date":
            raise AnalysisError(f"--cols 必须是 date 类型字段：{c}")
    return [labels.get(cols[0], cols[0]), "最后跟进",
            labels.get(cols[1], cols[1]), labels.get(cols[2], cols[2])]


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
    cols = 3 个 date 字段（开始 / 下个跟进 / 关闭）；vals 展开成 4 个
    日期：[开始, 最后跟进(最新快照,派生), 下个跟进, 关闭]。
    返回 [dict(id,title,status_val,archived,vals,sortmap)]；status_val =
    快照里 type=status 字段的显示值（md 状态列）。"""
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
                     "vals": [r[cols[0]],
                              r["last_at"][:10] if r["last_at"] else None,
                              r[cols[1]], r[cols[2]]],
                     "sortmap": {c: r[c] for c in sel_cols + extra},
                     "diff": None})
    return rows


def enrich(rows, cols, today=None):
    """计算日差（cols 第二列(下个跟进) − 今天，天）并补项目显示名。
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


def _seg_cells(start, end, months):
    """一段连线的绝对周列集合：start/end 任一端缺失 → 空（行保留，
    不画线，用户定）；窗外日期夹到边界；start 在 end 之后 → 空。"""
    if not start or not end:
        return set()
    si = _cell_index(start, months)
    ei = _cell_index(end, months)
    if si > ei:
        return set()
    return set(range(si, ei + 1))


def _month_cells(cells):
    """绝对周列集合 → 12 个月格文本，每格 4 字符（# 或空格，对应
    每月 4 周；用户定：月格而不是 48 个编号列）。"""
    return ["".join("#" if mi * WEEKS_PER_MONTH + wk in cells else " "
                    for wk in range(WEEKS_PER_MONTH))
            for mi in range(12)]


def _segments(row, today):
    """4 行线段（用户定，顺序固定）：(标签, 终点日期)。
    起点恒 = vals[0]（开始）；终点依次为 今日 / 最近跟进(派生) /
    下个跟进 / 关闭。标签填备注列（开始-今日 等）。"""
    return [("今日", today.isoformat()),
            ("最近跟进", row["vals"][1]),
            ("下个跟进", row["vals"][2]),
            ("关闭", row["vals"][3])]


def _outside_tags(dates, months):
    """日期列表 → (头标签, 尾标签)：落在窗口外的月份 'YY-MM'，
    去重排序、顿号连接（头/尾各一个大标注列，表示显示不完）。"""
    lo = (months[0][0], months[0][1])
    hi = (months[-1][0], months[-1][1])
    head, tail = [], []
    for d in dates:
        if not d:
            continue
        ym = (int(d[:4]), int(d[5:7]))
        tag = f"{ym[0] - 2000:02d}-{ym[1]:02d}"
        if ym < lo:
            head.append(tag)
        elif ym > hi:
            tail.append(tag)
    return "、".join(sorted(set(head))), "、".join(sorted(set(tail)))


def _lead(col_labels, months):
    """表头：项目/日差/3 日期列/头 + 12 个月列 + 尾 + 状态 + 备注。"""
    return (["项目", "日差", col_labels[0], col_labels[2], col_labels[3],
             "头"] + [lab for _y, _m, lab in months]
            + ["尾", "状态", "备注"])


def _anchor(gname, n):
    """章标题 → GitHub 风格 md 锚点（小写、空格转 -、去掉括号）。"""
    h = f"{gname}（{n} 个项目）"
    import re
    h = re.sub(r"[（）()]", "", h)
    return "#" + re.sub(r"\s+", "-", h.strip().lower())


def render_md(rows_groups, col_labels, months, colors, mode_label,
              today=None, split=False):
    """markdown 文本（用户贴图定，v3.8.3）：每项目一张表、4 行线段；
    无单独小标题；月格 4 字符；窗外月份写头/尾列；--split 时文首给
    章导航超链接。"""
    t = today or date.today()
    lead = _lead(col_labels, months)
    sep = ["---"] * len(lead)
    out = [f"# 项目时间线图（{mode_label}）\n"]
    if split:
        out.append("  ".join(f"[{n}（{len(g)} 个项目）]({_anchor(n, len(g))})"
                             for n, g in rows_groups) + "\n")
    legend_labels = ["今日", "最近跟进", col_labels[2], col_labels[3]]
    out.append("  ".join(f'<font color="{colors[i]}">■</font>'
                         f'开始-{lab}'
                         for i, lab in enumerate(legend_labels)) + "\n")
    for gname, grows in rows_groups:
        out.append(f"## {gname}（{len(grows)} 个项目）\n")
        for r in grows:
            rows = []
            for i, (label, end) in enumerate(_segments(r, t)):
                cells = _seg_cells(r["vals"][0], end, months)
                head, tail = _outside_tags([r["vals"][0], end], months)
                mcells = _month_cells(cells)
                if i == 0:
                    row = [r["name"],
                           str(r["diff"]) if r["diff"] is not None else "",
                           r["vals"][0] or "", r["vals"][2] or "",
                           r["vals"][3] or "", head]
                else:
                    row = ["", "", "", "", "", head]
                row += [f'<font color="{colors[i]}">{c}</font>' if "#" in c
                        else c for c in mcells]
                row += [tail,
                        (r["status_val"] or "") if i == 0 else "",
                        f"开始-{label}"]
                rows.append(row)
            out.append("| " + " | ".join(lead) + " |")
            out.append("|" + "|".join(sep) + "|")
            for row in rows:
                out.append("| " + " | ".join(row) + " |")
            out.append("")
    return "\n".join(out)


def dump_csv_text(rows_groups, col_labels, months, today=None):
    """csv 文本（--dump 终端打印用）：与 md 同网格，纯 # 不着色。"""
    t = today or date.today()
    lead = _lead(col_labels, months)
    out = [",".join(lead)]
    for gname, grows in rows_groups:
        out.append(f"# {gname}（{len(grows)} 个项目）")
        for r in grows:
            for i, (label, end) in enumerate(_segments(r, t)):
                cells = _seg_cells(r["vals"][0], end, months)
                head, tail = _outside_tags([r["vals"][0], end], months)
                if i == 0:
                    row = [r["name"],
                           str(r["diff"]) if r["diff"] is not None else "",
                           r["vals"][0] or "", r["vals"][2] or "",
                           r["vals"][3] or "", head]
                    row += _month_cells(cells) + [tail,
                                                  r["status_val"] or "",
                                                  f"开始-{label}"]
                else:
                    row = (["", "", "", "", "", head] + _month_cells(cells)
                           + [tail, "", f"开始-{label}"])
                out.append(",".join(row))
    return "\n".join(out)
