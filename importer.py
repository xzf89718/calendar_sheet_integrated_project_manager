# -*- coding: utf-8 -*-
"""Excel/CSV 导入：把旧项目批量导入为 项目 + 初始快照。

规则：
  表头与《调制器模板.xlsx》一致（中文字段名），也兼容常见别名；
  每一行 = 一个项目，项目名自动生成（厂家-客户-产品）；
  空单元格一律存数据库空值（界面显示空白）；
  日期统一转成 YYYY-MM-DD，空的或无法识别的留空（日历自动跳过）。
"""
import csv
from datetime import datetime

from db import normalize_date
from config import CFG

DATE_FIELDS = set(CFG.date_fields)
INT_FIELDS = set(CFG.int_fields)
FLOAT_FIELDS = set(CFG.float_fields)

# 表头匹配：只认 fields.json 里定义的 显示名 和 字段名（精确匹配）
ALIASES = CFG.header_map


def _cell_to_field(field, val):
    """单元格值 -> 字段值。空/None -> None；日期 -> YYYY-MM-DD 或 None。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d") if field in DATE_FIELDS else str(val)
    if isinstance(val, (int, float)) and not isinstance(val, bool) \
            and field in DATE_FIELDS:
        # Excel 序列号：单元格是数字格式时 openpyxl 不转日期，
        # 日期列里的数字按序列号解释（1899-12-30 起的天数）
        from datetime import timedelta
        try:
            d = datetime(1899, 12, 30) + timedelta(days=float(val))
            return d.strftime("%Y-%m-%d")
        except (OverflowError, ValueError, OSError):
            return None
    s = str(val).strip()
    if s == "" or s.lower() == "none":
        return None
    if field in DATE_FIELDS:
        return normalize_date(s)        # 无法识别的日期留空
    if field in INT_FIELDS:
        try:
            return int(float(s.rstrip("%")))
        except ValueError:
            return None
    if field in FLOAT_FIELDS:
        try:
            return float(s)
        except ValueError:
            return None
    return s


def import_file(db, path, template=None, changed_by="导入"):
    """导入入口。template 为 config.CFG.templates 中的一项（可选）：
    指定后按该模板的列清单匹配表头，不在库里的列自动忽略。
    返回 (成功数, 跳过的行号列表, 未识别的表头列表)。"""
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.reader(f) if any(x.strip() for x in r)]
    else:
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True).active
        rows = [list(r) for r in ws.iter_rows(values_only=True) if r]
    if not rows:
        return 0, [], []

    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    # 周报模板仅用于导出（周报是只读视图），不参与导入
    if template is not None:
        # 模板表头 + 该字段在"通用"里的标准名 都认：
        # 如"跟进历史"(模板名) 和 "跟进记录"(通用名) 是同一个字段，
        # 写哪个都能导入。不在库里的 const 列(如拥有者)自动忽略。
        table = {}
        for label, field, _c in template["columns"]:
            if field is None:
                continue
            table[label] = field
            standard = CFG.labels.get(field)
            if standard and standard != label:
                table[standard] = field
    else:
        table = ALIASES
    mapping, unmapped = {}, []
    for i, h in enumerate(header):
        field = table.get(h)
        if field:
            mapping[i] = field
        elif h:
            unmapped.append(h)

    created, skipped = 0, []
    header_set = {h for h in header if h}
    for lineno, row in enumerate(rows[1:], start=2):
        cells = [str(v).strip() for v in row
                 if v is not None and str(v).strip()]
        # 整行全空 -> 跳过；与表头同名的行（重复表头）-> 跳过
        if not cells or all(c in header_set for c in cells):
            skipped.append(lineno)
            continue
        fields = {}
        for i, field in mapping.items():
            val = row[i] if i < len(row) else None
            fields[field] = _cell_to_field(field, val)
        # 补空优先级：字段 default < 模板 defaults（更具体者覆盖），
        # 行里已有的值永不被覆盖
        for f_name, f_val in CFG.field_defaults.items():
            if f_val and not fields.get(f_name):
                fields[f_name] = f_val
        if template is not None:
            for f_name, f_val in template.get("defaults", {}).items():
                if f_val and not fields.get(f_name):
                    fields[f_name] = f_val
        # 状态兜底：导入时状态为空 -> 配置里的默认值
        if CFG.import_default_status and not fields.get(CFG.status_field):
            fields[CFG.status_field] = CFG.import_default_status
        db.create_project(changed_by=changed_by,
                          change_summary="Excel导入", **fields)
        created += 1
    return created, skipped, unmapped
