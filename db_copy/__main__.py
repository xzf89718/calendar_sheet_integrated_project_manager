# -*- coding: utf-8 -*-
"""库复制器命令行入口。

用法：
  python -m db_copy <A.db> <B.db> <pid...>   把 A 库选中的项目复制到 B 库
  python -m db_copy <A.db> <B.db> --all      复制 A 库全部项目
  python -m db_copy --gui                     图形界面（A/B 对照视图）

只新增：B 库已有数据不会被修改或删除；项目与快照在 B 库获得全新 id，
快照时间与内容原样保留（含完整历史）。
"""
import argparse
import sys

from db import Database
import db_copy.copy_core as core


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_copy", description="把源库项目（含全部历史）追加到目标库")
    ap.add_argument("src", nargs="?", help="源库 A 路径")
    ap.add_argument("dst", nargs="?", help="目标库 B 路径")
    ap.add_argument("pids", nargs="*", type=int, help="要复制的项目 id")
    ap.add_argument("--all", action="store_true", help="复制全部项目")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    args = ap.parse_args(argv)

    if args.gui:
        import db_copy.copy_gui as gui
        return gui.run_gui()
    if not args.src or not args.dst:
        ap.error("需要提供源库和目标库（或用 --gui）")
    if not args.all and not args.pids:
        ap.error("需要指定项目 id，或 --all 复制全部")

    db_a = Database(args.src)
    db_b = Database(args.dst)
    try:
        ok, msg = core.check_compatible(db_a, db_b)
        if not ok:
            print(f"配置不一致：{msg}", file=sys.stderr)
            return 1
        pids = [r["id"] for r in core.list_projects(db_a)] \
            if args.all else args.pids
        n_p, n_s = core.copy_projects(db_a, db_b, pids)
    except Exception as e:                                # noqa: BLE001
        print(f"复制失败（已整体回滚）：{e}", file=sys.stderr)
        return 1
    finally:
        db_a.close()
        db_b.close()
    print(f"已复制 {n_p} 个项目、{n_s} 条快照到 {args.dst}"
          f"（B 库原有数据未动）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
