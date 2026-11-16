# -*- coding: utf-8 -*-
"""周报清洗核心：日期匹配去重。

规则：对每一行，取第一列（修改日期），规范化后与"跟进记录"列的
文本做子串匹配——日期出现在跟进记录里的行保留，其余丢弃。
纯函数设计，不依赖 GUI/CLI。
"""
import re


def norm_date(s):
    """尽量把各种日期写法规范成 YYYY-MM-DD；失败返回原串（strip 后）。

    :param s: 原始日期值（任意写法）。
    :type s: object
    :return: 规范化日期字符串；无法解析时返回原串的字符串形式。
    :rtype: str
    """
    d = parse_date(s)
    if d:
        return f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}"
    return str(s or "").strip()


_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?")


def parse_date(s):
    """解析日期为 (年,月,日) 三元组；无法解析返回 None。

    支持 YYYY年MM月DD日 及 / - . 分隔的各种混写（正则搜索首个匹配）。

    :param s: 原始日期值。
    :type s: object
    :return: (年, 月, 日)；无法解析时为 None。
    :rtype: tuple 或 None
    """
    m = _DATE_RE.search(str(s or ""))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def extract_dates(text):
    """从文本中捞出全部日期的 (年,月,日) 集合（不限写法）。

    :param text: 任意文本。
    :type text: object
    :return: 日期三元组集合。
    :rtype: set
    """
    return {(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for m in _DATE_RE.finditer(str(text or ""))}


def load_rows(ws):
    """openpyxl 工作表 -> (表头list, 数据行list[list])。

    :param ws: 工作表对象。
    :type ws: openpyxl.worksheet.worksheet.Worksheet
    :return: (表头列表, 数据行列表)；空表时为 ([], [])。
    :rtype: tuple
    """
    rows = [list(r) for r in ws.iter_rows(values_only=True) if r]
    if not rows:
        return [], []
    return ["" if h is None else str(h) for h in rows[0]], rows[1:]


def clean_rows(headers, rows, note_idx):
    """保留：第一列日期规范化后出现在跟进记录文本中的行。

    按日期三元组匹配：跟进记录里任何写法的同一天都算命中。

    :param headers: 表头列表。
    :type headers: list
    :param rows: 数据行列表。
    :type rows: list
    :param note_idx: "跟进记录"列的下标。
    :type note_idx: int
    :return: (保留行列表, 丢弃数)。
    :rtype: tuple
    """
    kept = []
    dropped = 0
    for r in rows:
        d = parse_date(r[0] if len(r) > 0 else None)   # 第一列 -> (y,m,d)
        note = str(r[note_idx]) if len(r) > note_idx and r[note_idx] else ""
        # 按日期三元组匹配：跟进记录里任何写法的同一天都算命中
        if d and d in extract_dates(note):
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


def find_note_idx(headers, prefer):
    """找"跟进记录"列下标：优先匹配模板配置的标签，其次包含"跟进"。

    :param headers: 表头列表。
    :type headers: list
    :param prefer: 优先匹配的表头名（周报模板 followup_note 标签），无则 None。
    :type prefer: str 或 None
    :return: 列下标；找不到返回 None。
    :rtype: int 或 None
    """
    for i, h in enumerate(headers):
        if prefer and h == prefer:
            return i
    for i, h in enumerate(headers):
        if "跟进" in h:
            return i
    return None


def weekly_note_label(templates):
    """从 fields.json 周报模板取「跟进记录」列的优先标签；无则 None。

    :param templates: config.CFG.templates（columns 已展开为
        (表头, 字段名或None, 固定值或None) 三元组）。
    :type templates: list
    :return: 跟进记录列的表头名；无 weekly 模板或该列时 None。
    :rtype: str 或 None
    """
    tpl = next((t for t in templates if t.get("kind") == "weekly"), None)
    if tpl:
        for label, field, _c in tpl["columns"]:
            if field == "followup_note":
                return label
    return None
