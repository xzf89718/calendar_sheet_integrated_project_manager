# -*- coding: utf-8 -*-
"""多库追加器命令行入口。

用法：
  python -m db_append <target.db> <src.db> [src2.db...]   依次全部追加
  python -m db_append --gui                                图形界面

只新增：目标库已有数据不会被修改或删除；快照时间/内容原样保留，
当前状态指向时间最新的一条。重复执行会产生重复项目（追加语义）。
前提：所有库使用同一份 fields.json（团队统一格式）。
"""
import argparse
import os
import sys

from db import Database
import db_append.append_core as core


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="db_append", description="多个源库依次全部追加进目标库")
    ap.add_argument("target", nargs="?", help="目标库路径（合并进这里）")
    ap.add_argument("sources", nargs="*", help="源库路径（可多个）")
    ap.add_argument("--gui", action="store_true", help="图形界面")
    args = ap.parse_args(argv)

    if args.gui:
        import db_append.append_gui as gui
        return gui.run_gui()
    if not args.target or not args.sources:
        ap.error("需要提供目标库和至少一个源库（或用 --gui）")

    abs_target = os.path.abspath(args.target)
    t = Database(args.target)
    dbs = []
    try:
        for p in args.sources:
            if os.path.abspath(p) == abs_target:
                print(f"错误：源库与目标库是同一个文件：{p}", file=sys.stderr)
                return 1
            d = Database(p)
            ok, msg = core.check_compatible(d, t)
            if not ok:
                print(f"配置不一致：{p}\n{msg}", file=sys.stderr)
                return 1
            dbs.append(d)
        n_p, n_s, details = core.append_sources(t, dbs)
    except Exception as e:                                # noqa: BLE001
        print(f"追加失败：{e}", file=sys.stderr)
        return 1
    finally:
        for d in dbs:
            d.close()
        t.close()
    for name, p, s in details:
        print(f"  {name}：+{p} 项目 / +{s} 快照")
    print(f"合计追加 {n_p} 个项目、{n_s} 条快照。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
