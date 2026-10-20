# -*- coding: utf-8 -*-
"""周报清洗核心：日期匹配去重。

规则：对每一行，取第一列（修改日期），规范化后与"跟进记录"列的
文本做子串匹配——日期出现在跟进记录里的行保留，其余丢弃。
纯函数设计，不依赖 GUI。
"""
import re


def norm_date(s):
    """尽量把各种日期写法规范成 YYYY-MM-DD；失败返回原串。"""
    d = parse_date(s)
    if d:
        return f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}"
    return str(s or "").strip()


_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?")


def parse_date(s):
    """解析日期为 (年,月,日) 三元组；无法解析返回 None。"""
    m = _DATE_RE.search(str(s or ""))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def extract_dates(text):
    """从文本中捞出全部日期的 (年,月,日) 集合（不限写法）。"""
    return {(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for m in _DATE_RE.finditer(str(text or ""))}


def load_rows(ws):
    """openpyxl 工作表 -> (表头list, 数据行list[list])"""
    rows = [list(r) for r in ws.iter_rows(values_only=True) if r]
    if not rows:
        return [], []
    return ["" if h is None else str(h) for h in rows[0]], rows[1:]


def clean_rows(headers, rows, note_idx):
    """保留：第一列日期规范化后出现在跟进记录文本中的行。

    note_idx: "跟进记录"列的下标。返回 (保留行list, 丢弃数)。
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
    找不到返回 None。"""
    for i, h in enumerate(headers):
        if prefer and h == prefer:
            return i
    for i, h in enumerate(headers):
        if "跟进" in h:
            return i
    return None
