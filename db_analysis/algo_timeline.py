# -*- coding: utf-8 -*-
"""时间线算法（v3.8.0）：项目分类时间点可视化——markdown 表格输出。

命名定案（2026-11-10 用户定）：**不叫甘特图**。甘特图 = 持续时间条 +
完成百分比 + 依赖关系；本软件只有离散时间点 + 类别，不做进度评估
——给证据不给结论。每个项目 4 行（对应 4 个日期），每月一列，在
日期所属月份格画一个着色 `#`；窗口外的时间点不丢弃，「窗外」列
标注实际月份。已关闭/已成单归档章（status_closed 来自 fields.json）
只画开始、关闭两格。

- 取数：当前行口径（projects.current_id），open + closed 全取，
  分章时归「已关闭」章；
- --where 复用 analysis_core._parse_where；
- --dump 输出 csv 文本到终端（不着色，纯 #）；
- --path 另存 md 到目录（自动命名，与 pie 同一 _resolve_out 规矩）。
"""

from datetime import date

from .analysis_core import AnalysisError, _parse_where

# 4 行默认配色（绿/蓝/橙/红，CLI 可覆盖）
DEFAULT_COLORS = ["#2e7d32", "#1565c0", "#e65100", "#c62828"]
# “最后跟进”列的特殊字段名：取该项目最新快照时间
LAST = "last"


def default_cols():
    """默认 4 列：开始 / 最后跟进 / 下个跟进 / 关闭，从
    fields.json 的 calendar_dates 推导（找不到的位 = last/None）。"""
    from config import CFG
    fmap = {}
    for k, f, _l, _c in CFG.calendar_dates:
        if k in ("start", "followup", "close") and f:
            fmap[k] = f
    return [fmap.get("start"), LAST, fmap.get("followup"),
            fmap.get("close")]


def validate_cols(cols):
    """4 列逐一校验：必须是存在的字段名且为 date 类型，或 last。
    返回 [(原始名, label, color槽位用原名)] 之外的展示名列表。"""
    from config import CFG
    ftypes = {f["name"]: f["type"] for f in CFG.fields}
    labels = CFG.labels
    for c in cols:
        if c == LAST:
            continue
        if c not in ftypes:
            raise AnalysisError(f"--cols 不存在的字段：{c}"
                                f"（可用：{'、'.join(CFG.names)}；"
                                f"最后跟进用特殊值 {LAST}）")
        if ftypes[c] != "date":
            raise AnalysisError(f"--cols 必须是 date 类型字段：{c}")
    return [("最后跟进" if c == LAST else labels.get(c, c)) for c in cols]


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
    """当前行口径取数：open + closed 全取（分章归「已关闭」章）。
    返回 [dict(id,title,archived,vals=[4 个 'YYYY-MM-DD' 或 None],
    sortmap={字段: 原始值})]；sortmap 预置全部字段值供 --sort 使用。"""
    from config import CFG
    fields = [c for c in cols if c and c != LAST]
    extra = sorted({f["name"] for f in CFG.fields}
                   - set(fields) - {"status"})
    sel = ", ".join(f"s.{c}" for c in fields + extra)
    wheres, args = _where_sql(where)
    wh = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    sql = (f"SELECT p.id, p.title, p.status, {sel} "
           f"FROM snapshots s JOIN projects p ON p.id = s.project_id "
           f"AND s.id = p.current_id {wh}")
    rows = []
    for r in db.conn.execute(sql, args).fetchall():
        vals = []
        for c in cols:
            if c == LAST:
                v = db.conn.execute(
                    "SELECT MAX(snapshot_at) FROM snapshots "
                    "WHERE project_id=?", (r["id"],)).fetchone()[0]
                vals.append(v[:10] if v else None)
            else:
                vals.append(r[c] if c else None)
        sortmap = {c: r[c] for c in extra}
        for c in fields:
            sortmap[c] = r[c]
        rows.append({"id": r["id"], "title": r["title"],
                     "archived": r["status"] == "closed",
                     "vals": vals, "sortmap": sortmap,
                     "diff": None})
    return rows


def enrich(rows, cols, today=None):
    """计算日差（cols 第三列 − 今天，天）并补项目显示名。
    归档项目的 diff 恒为 None。today 可注入（测试确定性）。"""
    from config import CFG
    t = today or date.today()
    name_cols = [c for c in CFG.name_fields if c in CFG.names]
    for row in rows:
        if not row["archived"] and len(cols) >= 3 and cols[2] \
                and row["vals"][2]:
            d0 = date.fromisoformat(row["vals"][2])
            row["diff"] = (d0 - t).days
        name = "-".join(str(row["sortmap"].get(c) or "")
                        for c in name_cols).strip("-")
        row["name"] = name or row["title"]
    return rows


def split_groups(rows):
    """四章划分（用户定 2026-11-10，顺序固定）：
    逾期未跟进（diff<0）→ 待跟进（diff>=0）→ 未排跟进（无下个跟进）
    → 已关闭（status_closed 归档）。归档只看第一/第四列。返回
    [(章名, [row...])]，空章不出现。"""
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
    """章内排序：key=None/--sort diff 按日差（None 恒排最后，与
    升降序无关）；库字段按原始值（None 视作空串排最后）。"""
    if key is None or key == "diff":
        rows.sort(key=lambda r: (r["diff"] is None,
                                 r["diff"] if r["diff"] is not None else 0),
                  reverse=desc)
        if desc:                       # None 仍要垫底
            tail = [r for r in rows if r["diff"] is None]
            rows[:] = [r for r in rows if r["diff"] is not None] + tail
        return rows
    rows.sort(key=lambda r: (r["sortmap"].get(key) in (None, ""),
                             str(r["sortmap"].get(key) or "")),
              reverse=desc)
    if desc:
        tail = [r for r in rows if r["sortmap"].get(key) in (None, "")]
        rows[:] = [r for r in rows if r["sortmap"].get(key) not in (None, "")
                   ] + tail
    return rows


def _month_of(dstr):
    """'YYYY-MM-DD' → (year, month)。"""
    return int(dstr[:4]), int(dstr[5:7])


def render_md(rows_groups, cols, col_labels, months, colors,
              mode_label):
    """markdown 文本。每个项目 4 行（对应 4 个日期）：本行日期列写
    日期值，其余日期列空；在日期所属月份格画着色 <font>#</font>；
    窗外月份去重列进「窗外」列（首行）。归档项目只画第 1/4 行。"""
    win = {(y, m) for y, m, _l in months}
    lines = []
    lines.append(f"# 项目时间线图（{mode_label}）\n")
    legend = "  ".join(f'<font color="{colors[i]}">■</font>'
                       f'{col_labels[i]}' for i in range(4))
    lines.append(legend + "\n")
    head = ("| 项目 | 日差 | " + " | ".join(col_labels)
            + " | 窗外 | " + " | ".join(l for _y, _m, l in months) + " |")
    sep = "|" + "---|" * (7 + 12)      # 7 前导列 + 12 个月格
    for gname, grows in rows_groups:
        lines.append(f"\n## {gname}（{len(grows)} 个项目）\n")
        lines.append(head)
        lines.append(sep)
        for r in grows:
            outside = []
            row_cells = []
            for i in range(4):
                if r["archived"] and i not in (0, 3):
                    continue            # 归档只画开始/关闭两格
                dstr = r["vals"][i]
                cells = [""] * 4
                grid = [""] * 12
                if dstr:
                    cells[i] = dstr
                    ym = _month_of(dstr)
                    if ym in win:
                        grid[months.index((*ym, f"{ym[0]-2000:02d}-"
                                           f"{ym[1]:02d}"))] = \
                            f'<font color="{colors[i]}">#</font>'
                    else:
                        outside.append(f"{ym[0]}-{ym[1]:02d}")
                row_cells.append((i, cells, grid))
            for j, (i, cells, grid) in enumerate(row_cells):
                first = j == 0
                lead = [r["name"] if first else "",
                        str(r["diff"]) if (first and r["diff"] is not None)
                        else "",
                        ] + cells + ["、".join(sorted(set(outside)))
                                     if (first and outside) else ""]
                lines.append("| " + " | ".join(lead) + " | "
                             + " | ".join(grid) + " |")
    lines.append("")
    return "\n".join(lines)


def dump_csv_text(rows_groups, cols, col_labels, months):
    """csv 文本（终端打印用）：与 md 同网格，纯 # 不着色。"""
    win = {(y, m) for y, m, _l in months}
    out = ["项目,日差," + ",".join(col_labels) + ",窗外,"
           + ",".join(l for _y, _m, l in months)]
    for gname, grows in rows_groups:
        out.append(f"# {gname}（{len(grows)} 个项目）")
        for r in grows:
            outside = []
            for i in range(4):
                if r["archived"] and i not in (0, 3):
                    continue
                dstr = r["vals"][i]
                cells = [""] * 4
                grid = [""] * 12
                if dstr:
                    cells[i] = dstr
                    ym = _month_of(dstr)
                    if ym in win:
                        grid[months.index((*ym, f"{ym[0]-2000:02d}-"
                                           f"{ym[1]:02d}"))] = "#"
                    else:
                        outside.append(f"{ym[0]}-{ym[1]:02d}")
                lead = [r["name"],
                        str(r["diff"]) if r["diff"] is not None else "",
                        ] + cells + ["、".join(sorted(set(outside)))]
                out.append(",".join(lead) + "," + ",".join(grid))
    return "\n".join(out)
