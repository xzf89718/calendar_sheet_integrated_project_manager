"""weekreport_clean：周报清洗（同一天匹配去重）。

GUI/CLI 双入口：`python -m weekreport_clean gui` 或
`preview` / `clean` 子命令。核心纯函数在 clean_core。
"""
from .clean_core import (                      # noqa: F401
    clean_rows, extract_dates, find_note_idx, load_rows,
    norm_date, parse_date, weekly_note_label)
