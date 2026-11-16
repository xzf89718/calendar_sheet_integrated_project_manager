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
    """导出值：有值出值，空值补字段的 default（未配置则空）。

    :param v: 单元格原值
    :type v: object
    :param field: 字段名
    :type field: str
    :return: 导出值；无值且无 default 时 None（空单元格）
    :rtype: object 或 None
    """
    if v not in (None, ""):
        return v
    return CFG.field_defaults.get(field) or None


def export_excel(rows, path):
    """按默认列序导出（fields.json 字段顺序 + 显示名表头）。返回导出行数。

    :param rows: 行 dict 列表（即界面上筛选/排序后的结果）
    :type rows: list
    :param path: 输出 .xlsx 路径
    :type path: str
    :return: 导出行数
    :rtype: int
    """
    wb = Workbook()
    ws = wb.active
    ws.append(HEADS)
    for r in rows:
        ws.append([_fill(r.get(c), c) for c in COLS])
    wb.save(path)
    return len(rows)


def export_with_template(rows, path, template):
    """按命名模板导出 xlsx：不在库里的列填配置的固定值（const）。返回导出行数。

    :param rows: 行 dict 列表
    :type rows: list
    :param path: 输出 .xlsx 路径
    :type path: str
    :param template: 模板（config.CFG.templates 的一项，columns 三元组列表）
    :type template: dict
    :return: 导出行数
    :rtype: int
    """
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


def export_csv(rows, path, template):
    """按命名模板导出 CSV（utf-8-sig，Excel 双击打开中文不乱码）。

    列与取值规则和 export_with_template 完全一致（const 列原样、空值补
    default），仅无固定列样式。返回导出行数。

    :param rows: 行 dict 列表
    :type rows: list
    :param path: 输出 .csv 路径
    :type path: str
    :param template: 模板（config.CFG.templates 的一项）
    :type template: dict
    :return: 导出行数
    :rtype: int
    """
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([label for label, _f, _c in template["columns"]])
        for r in rows:
            w.writerow([const if field is None
                        else _fill(r.get(field), field)
                        for _label, field, const in template["columns"]])
    return len(rows)


# ---------- 周报 ----------
def _weekly_cell(snap, field):
    """本周跟进表取值：__date__=快照日期、__name__=项目名、其余取快照字段。

    :param snap: 快照行（sqlite3.Row，带 ptitle）
    :type snap: sqlite3.Row
    :param field: 模板列的字段名或特殊键
    :type field: str
    :return: 单元格值；空为 None
    :rtype: object 或 None
    """
    if field == "__date__":
        return snap["snapshot_at"][:10]
    if field == "__name__":
        return snap["ptitle"]
    return snap[field] if snap[field] not in (None, "") else None


def _weekly_plan_cell(proj, field):
    """下周计划表取值：__date__=next_followup、__name__=项目名、其余取当前状态字段。

    :param proj: 项目当前状态行（sqlite3.Row）
    :type proj: sqlite3.Row
    :param field: 模板列的字段名或特殊键
    :type field: str
    :return: 单元格值；空为 None
    :rtype: object 或 None
    """
    if field == "__date__":
        return proj["next_followup"]
    if field == "__name__":
        return proj["title"]
    return proj[field] if proj[field] not in (None, "") else None


def export_weekly(rows_follow, rows_plan, template, path):
    """周报导出 xlsx：两个工作表——表1=本周跟进（区间内全部快照），
    表2=下周计划（next_followup 落在计划区间内的项目）。列结构由周报
    模板（kind=weekly）定义。

    :param rows_follow: 本周跟进行列表
    :type rows_follow: list
    :param rows_plan: 下周计划行列表
    :type rows_plan: list
    :param template: 周报模板（kind=weekly）
    :type template: dict
    :param path: 输出 .xlsx 路径
    :type path: str
    :return: 二元组（跟进行数, 计划行数）
    :rtype: tuple
    """
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


def export_weekly_csv(rows_follow, rows_plan, template, path):
    """周报 CSV（v3.9.0）：单文件两段形态——段标题「本周跟进」、表头、数据，
    空行，段标题「下周计划」、表头、数据。utf-8-sig + 纯 LF。

    :param rows_follow: 本周跟进行列表
    :type rows_follow: list
    :param rows_plan: 下周计划行列表
    :type rows_plan: list
    :param template: 周报模板（kind=weekly）
    :type template: dict
    :param path: 输出 .csv 路径
    :type path: str
    :return: 二元组（跟进行数, 计划行数）
    :rtype: tuple
    """
    import csv
    heads = [label for label, _f, _c in template["columns"]]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["本周跟进"])
        w.writerow(heads)
        for s in rows_follow:
            w.writerow(["" if (v := _weekly_cell(s, fld)) is None else v
                        for _l, fld, _c in template["columns"]])
        w.writerow([])
        w.writerow(["下周计划"])
        w.writerow(heads)
        for p in rows_plan:
            w.writerow(["" if (v := _weekly_plan_cell(p, fld)) is None else v
                        for _l, fld, _c in template["columns"]])
    return len(rows_follow), len(rows_plan)
