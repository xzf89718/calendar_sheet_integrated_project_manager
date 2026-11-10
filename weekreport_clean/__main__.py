# -*- coding: utf-8 -*-
"""weekreport_clean：周报清洗入口（v3.6.1 起 CLI 化，GUI/CLI 双入口）。

    python -m weekreport_clean preview <file.xlsx>   # 预览：终端打印
        保留/丢弃行 + 汇总（只读，不写文件）
    python -m weekreport_clean clean <file.xlsx> [-o out.xlsx]
        # 生成清洗结果 xlsx；不带 -o 默认写 <原名>_cleaned.xlsx
        （同目录，已存在覆盖）
    python -m weekreport_clean gui                   # 图形界面

规则（与 GUI 完全同源）：第一列（写入时间）的日期出现在
「跟进记录」列文本中的行保留，其余丢弃——规避大规模导入 /
修改过去跟进记录带来的"写入时间≠跟进当天"污染行。
跟进记录列定位：周报模板 followup_note 标签优先，其次表头
含"跟进"。清洗结果为空拒绝写出（对齐 GUI）。
退出码：0 成功 / 1 业务错误（stderr，无 traceback）/ 2 参数错误。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import Workbook, load_workbook      # noqa: E402
from config import CFG                            # noqa: E402

from .clean_core import (                          # noqa: E402
    clean_rows, find_note_idx, load_rows, weekly_note_label)


class CliError(Exception):
    """业务错误：消息直接给用户看，不带 traceback。"""


def _load(path):
    """读取 xlsx -> (headers, rows, note_idx)。业务问题抛 CliError。"""
    if not path.lower().endswith(".xlsx"):
        raise CliError("只支持 .xlsx 文件")
    if not os.path.exists(path):
        raise CliError(f"文件不存在：{path}")
    try:
        wb = load_workbook(path, read_only=True)
        ws = wb[wb.sheetnames[0]]
        headers, rows = load_rows(ws)
        wb.close()
    except Exception as e:                          # noqa: BLE001
        raise CliError(f"读取失败：{e}")
    if not headers:
        raise CliError("文件没有数据行")
    prefer = weekly_note_label(CFG.templates)
    note_idx = find_note_idx(headers, prefer)
    return headers, rows, note_idx


def _note_idx_or_die(note_idx, headers):
    if note_idx is None:
        raise CliError("找不到「跟进记录」列（表头需含'跟进'或匹配"
                       "周报模板标签）")
    return headers[note_idx]


def _fmt_cell(v, width=28):
    s = "" if v is None else str(v)
    s = s.replace("\n", " ").replace("\r", " ")
    return s[:width]


def cmd_preview(args):
    from show_icon import tty_if_wanted
    tty_if_wanted(args.show_icon, args.no_show_icon)
    headers, rows, note_idx = _load(args.file)
    note_name = _note_idx_or_die(note_idx, headers)
    kept, dropped = clean_rows(headers, rows, note_idx)
    kept_ids = {id(r) for r in kept}
    print(f"跟进记录列：{note_name} ｜ 规则：第一列日期出现在"
          f"跟进记录中才保留")
    print("=" * 72)
    for r in rows:
        tag = "保留" if id(r) in kept_ids else "丢弃"
        cells = " | ".join(_fmt_cell(c) for c in r)
        print(f"[{tag}] {cells}")
    print("=" * 72)
    print(f"共 {len(rows)} 行：保留 {len(kept)} / 丢弃 {dropped}"
          f"（预览未写文件；用 clean 命令生成清洗结果）")
    return 0


def cmd_clean(args):
    from show_icon import tty_if_wanted
    tty_if_wanted(args.show_icon, args.no_show_icon)
    headers, rows, note_idx = _load(args.file)
    _note_idx_or_die(note_idx, headers)
    kept, dropped = clean_rows(headers, rows, note_idx)
    if not kept:
        raise CliError("清洗结果为空，拒绝写出（与 GUI 行为一致）")
    if args.output:
        out = args.output
    else:
        stem = os.path.splitext(os.path.basename(args.file))[0]
        out = os.path.join(os.path.dirname(os.path.abspath(args.file)),
                           f"{stem}_cleaned.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "清洗结果"
    ws.append(headers)
    for r in kept:
        ws.append(list(r))
    parent = os.path.dirname(os.path.abspath(out))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        wb.save(out)
    except Exception as e:                          # noqa: BLE001
        raise CliError(f"导出失败：{e}")
    print(f"已导出：{out}")
    print(f"共 {len(rows)} 行：保留 {len(kept)} / 丢弃 {dropped}")
    return 0


def cmd_gui(args):
    from show_icon import splash_if_wanted
    splash_if_wanted(args.show_icon, args.no_show_icon)
    from .clean_gui import CleanApp
    CleanApp().mainloop()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="weekreport_clean",
        description="周报清洗：同一天匹配，去掉非真实当日跟进的行")
    sub = ap.add_subparsers(dest="command")
    sub.required = True

    p = sub.add_parser("preview", help="预览清洗前/后（只读，不写文件）")
    p.add_argument("file", help="周报 xlsx 路径")
    p.set_defaults(func=cmd_preview)

    c = sub.add_parser("clean", help="生成清洗结果 xlsx")
    c.add_argument("file", help="周报 xlsx 路径")
    c.add_argument("-o", "--output", help="输出路径（默认 "
                   "<原名>_cleaned.xlsx，同目录，已存在覆盖）")
    c.set_defaults(func=cmd_clean)

    g = sub.add_parser("gui", help="图形界面")
    g.set_defaults(func=cmd_gui)

    from show_icon import add_icon_flags
    for sp in (p, c, g):                        # 每个子命令都接受双开关
        add_icon_flags(sp)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except CliError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
