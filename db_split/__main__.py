# -*- coding: utf-8 -*-
"""按键分拆器命令行入口。

用法：
  python -m db_split <src.db> --key <键列> [--dest DIR]   执行分拆
  python -m db_split <src.db> --key <键列> --preview      只预览
  python -m db_split --gui                                 图形界面

键列可以是字段名（city）或显示名（城市）。全量分拆（含归档）、
空值进"未分配.db"、目标文件已存在则拒绝执行。
"""
import argparse
import sys

from db import Database
import db_split.split_core as core


def _resolve_field(name_or_label):
    """字段名或显示名 -> 字段名，找不到返回 None。"""
    from config import CFG
    cols = [c for c, _h in CFG.display_cols if c != "id"]
    if name_or_label in cols:
        return name_or_label
    for c in cols:
        if CFG.labels.get(c, c) == name_or_label:
            return c
    return None


def _cmd_preview(db, field, label):
    counts = core.preview(db, field)
    if not counts:
        print("源库里没有项目。")
        return 0
    print(f"按「{label}」将拆成 {len(counts)} 个文件：")
    for k, n in counts.items():
        print(f"  {(k or '未分配')}：{n} 个项目")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_split", description="按某列取值把源库拆成多个库文件")
    ap.add_argument("db", nargs="?", help="源库路径，如 xxx.db")
    ap.add_argument("--key", help="键列（字段名或显示名，如 city / 城市）")
    ap.add_argument("--dest", help="输出目录")
    ap.add_argument("--preview", action="store_true", help="只预览不执行")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    args = ap.parse_args(argv)

    if args.gui:
        import db_split.split_gui as gui
        return gui.run_gui()
    if not args.db or not args.key:
        ap.error("需要提供源库和 --key（或用 --gui）")
    field = _resolve_field(args.key)
    if field is None:
        print(f"错误：库里没有「{args.key}」这一列", file=sys.stderr)
        return 1
    if args.preview:
        db = Database(args.db)
        try:
            return _cmd_preview(db, field, args.key)
        finally:
            db.close()
    if not args.dest:
        ap.error("需要 --dest 输出目录（或 --preview 只预览）")

    db = Database(args.db)
    try:
        try:
            result = core.split_by_key(db, args.dest, field)
        except FileExistsError as e:
            print(f"已存在，拒绝执行：{e}", file=sys.stderr)
            return 1
    finally:
        db.close()
    for fname, (n_p, n_s) in result.items():
        print(f"{fname}：{n_p} 项目 / {n_s} 快照")
    print(f"完成：{len(result)} 个文件 → {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
