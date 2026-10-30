# -*- coding: utf-8 -*-
"""批量赋值器命令行入口。

用法：
  python -m db_assign <xxx.db> --field <列> --value <值> [--yes]
  python -m db_assign --gui

作用域 = 库内全部项目（与 GUI 一致，刻意不做子集选择）。
默认只预览不写库；加 --yes 才真正执行。

铁律：不直接改数据。每个项目生成一条新快照（走跟进方法），
赋值动作全程可追溯、可对比、可回溯。
"""
import argparse
import sys

from db import Database
import db_assign.assign_core as core


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


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_assign", description="对整个库统一给一列赋值（走快照可回溯）")
    ap.add_argument("db", nargs="?", help="数据库路径")
    ap.add_argument("--field", help="赋值列（字段名或显示名，如 city / 城市）")
    ap.add_argument("--value", default="", help="新值（默认空=清空该列）")
    ap.add_argument("--yes", action="store_true", help="确认执行（默认只预览）")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    args = ap.parse_args(argv)

    if args.gui:
        import db_assign.assign_gui as gui
        return gui.run_gui()
    if not args.db or not args.field:
        ap.error("需要提供数据库和 --field（或用 --gui）")
    field = _resolve_field(args.field)
    if field is None:
        print(f"错误：库里没有「{args.field}」这一列", file=sys.stderr)
        return 1

    db = Database(args.db)
    try:
        pids = core.all_project_ids(db)
        shown = args.value or "(清空)"
        if not args.yes:
            print(f"预览：将对全部 {len(pids)} 个项目赋值："
                  f"{args.field} = {shown}")
            print("不写库。确认无误后加 --yes 执行。")
            return 0
        ok, fails = core.assign_value(db, pids, field, args.value)
    finally:
        db.close()
    msg = f"已赋值 {ok} / {len(pids)} 个项目"
    if fails:
        msg += f"，失败 {len(fails)}：{fails[:3]}"
    print(msg)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
