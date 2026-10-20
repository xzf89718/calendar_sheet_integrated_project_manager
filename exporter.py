# -*- coding: utf-8 -*-
"""导出 Excel（单一格式）。

列序与《调制器模板.xlsx》完全一致（fields.json 的 fields 顺序），
无标题列。只导出传入的行（即界面上筛选/排序后的结果）。
空值输出空白单元格。
"""
from openpyxl import Workbook

from config import CFG

COLS = CFG.names
HEADS = [CFG.labels[c] for c in COLS]


def _fill(v, field):
    """导出值：有值出值，空值补字段的 default（未配置则空）。"""
    if v not in (None, ""):
        return v
    return CFG.field_defaults.get(field) or None


def export_excel(rows, path):
    """按模板列序导出（默认 = fields.json 字段顺序）。返回导出行数。"""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADS)
    for r in rows:
        ws.append([_fill(r.get(c), c) for c in COLS])
    wb.save(path)
    return len(rows)


def export_with_template(rows, path, template):
    """按命名模板导出。不在库里的列填配置的固定值。返回导出行数。"""
    wb = Workbook()
    ws = wb.active
    ws.append([label for label, _f, _c in template["columns"]])
    for r in rows:
        row = []
        for _label, field, const in template["columns"]:
            if field is None:
                row.append(const)          # 固定值原样导出（空=空单元格）
            else:
                row.append(_fill(r.get(field), field))
        ws.append(row)
    wb.save(path)
    return len(rows)


# ---------- 周报 ----------
def _weekly_cell(snap, field):
    """本周跟进行取值：快照记录 + 项目名。"""
    if field == "__date__":
        return snap["snapshot_at"][:10]
    if field == "__name__":
        return snap["ptitle"]
    return snap[field] if snap[field] not in (None, "") else None


def _weekly_plan_cell(proj, field):
    """下周计划行取值：项目当前状态，日期列 = next_followup。"""
    if field == "__date__":
        return proj["next_followup"]
    if field == "__name__":
        return proj["title"]
    return proj[field] if proj[field] not in (None, "") else None


def export_weekly(rows_follow, rows_plan, template, path):
    """周报导出：两个时间段的内容合并到一个文件的两个工作表。
    表1=本周跟进（区间内的全部快照），表2=下周计划（next_followup
    落在计划区间内的项目）。列结构由周报模板（kind=weekly）定义。"""
    wb = Workbook()
    heads = [label for label, _f, _c in template["columns"]]
    ws1 = wb.active
    ws1.title = "本周跟进"
    ws1.append(heads)
    for s in rows_follow:
        ws1.append([_weekly_cell(s, f) for _l, f, _c in template["columns"]])
    ws2 = wb.create_sheet("下周计划")
    ws2.append(heads)
    for p in rows_plan:
        ws2.append([_weekly_plan_cell(p, f) for _l, f, _c in
                    template["columns"]])
    wb.save(path)
    return len(rows_follow), len(rows_plan)
