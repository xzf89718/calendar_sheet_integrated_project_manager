# -*- coding: utf-8 -*-
"""回收站命令行入口。

用法：
  python -m db_recycled <xxx.db>                列出回收站
  python -m db_recycled <xxx.db> --restore 12   恢复项目
  python -m db_recycled <xxx.db> --restore all  全部恢复
  python -m db_recycled <xxx.db> --purge 12     永久删除单个
  python -m db_recycled <xxx.db> --empty        清空回收站
  python -m db_recycled <xxx.db> --gui          图形界面
"""
import argparse
import sys

from db import Database
import db_recycled.recycled_core as core


def _cmd_list(db):
    rows = core.list_recycled(db)
    if not rows:
        print("回收站是空的。")
        return
    print(f"{'id':>4}  {'项目名':<30} {'回收时间':<20} 快照数")
    for pid, title, at, cnt in rows:
        print(f"{pid:>4}  {title:<30} {at:<20} {cnt}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_recycled", description="回收站管理（查看/恢复/彻底删除）")
    ap.add_argument("db", help="数据库文件路径，如 xxx.db")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    ap.add_argument("--restore", metavar="ID|all", help="恢复项目")
    ap.add_argument("--purge", type=int, metavar="ID", help="永久删除单个")
    ap.add_argument("--empty", action="store_true", help="清空回收站")
    args = ap.parse_args(argv)

    db = Database(args.db)
    try:
        if args.gui:
            import db_recycled.recycled_gui as gui
            return gui.run_gui(db, args.db)
        if args.restore:
            if args.restore == "all":
                rows = core.list_recycled(db)
                for pid, _t, _a, _c in rows:
                    nid, changed = core.restore_project(db, pid)
                    print(f"已恢复 {pid}" +
                          (f"（新 id={nid}）" if changed else ""))
                print(f"共恢复 {len(rows)} 个项目。")
            else:
                nid, changed = core.restore_project(db, int(args.restore))
                print(f"已恢复 {nid}" +
                      (f"（原 id={args.restore} 被占用，换了新 id）"
                       if changed else ""))
            return 0
        if args.purge is not None:
            core.purge_project(db, args.purge)
            print(f"已永久删除回收项目 {args.purge}。")
            return 0
        if args.empty:
            core.empty_recycle(db)
            print("回收站已清空（全部永久删除）。")
            return 0
        _cmd_list(db)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
