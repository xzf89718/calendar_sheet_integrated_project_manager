# -*- coding: utf-8 -*-
"""db_analysis：只读数据分析统一入口（v3.5.0）。

    python -m db_analysis pie --field 客户 [--closed] [--top N]
            [--where 字段=值 ...] [--date-field 名]
            [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
            [--png 路径.png] [--dump-data 路径.csv]

铁律：绝不写库。库锚定 fields.json 同目录（软件设计准则，
不提供 --db 路径参数）。退出码：0 成功 / 1 业务错误（stderr，
无 traceback）/ 2 参数错误。
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CFG, BASE_DIR            # noqa: E402
from db import Database, normalize_date     # noqa: E402

from .analysis_core import AnalysisError    # noqa: E402
from . import algo_pie                      # noqa: E402

# 算法表：子命令名 → (内核函数, 一句话说明)。GUI 预留数据源。
ALGOS = {
    "pie": (algo_pie.cmd_pie, "选定字段取值分布饼图 + 计数"),
}

_LASTS = {"1m": 30, "6m": 183, "1y": 365}


def _norm_date(s, opt):
    v = normalize_date(s)
    if not v:
        raise AnalysisError(f"{opt} 不是有效日期：{s!r}")
    return v


def _build_parser():
    p = argparse.ArgumentParser(
        prog="db_analysis",
        description="只读数据分析（绝不写库；库锚定 fields.json 同目录）")
    sub = p.add_subparsers(dest="algo", required=True)
    for name, (_fn, desc) in ALGOS.items():
        sp = sub.add_parser(name, help=desc)
        if name == "pie":
            sp.add_argument("--field", required=True,
                            help="统计字段（fields.json 的 name，date 类型除外）")
            sp.add_argument("--closed", action="store_true",
                            help="把已归档（closed）项目也纳入分析")
            sp.add_argument("--top", type=int, default=9,
                            help="段数上限，超出合并为「其他」（默认 9）")
            sp.add_argument("--where", action="append", default=None,
                            metavar="字段=值",
                            help="筛选，可多次；同字段并集、异字段交集")
            sp.add_argument("--date-field", default=None,
                            metavar="字段名",
                            help="日期区间作用的列：缺省 = 跟进日"
                                 "（snapshot_at）；也可填快照里的 date 字段名")
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--from", dest="date_from", default=None,
                           metavar="YYYY-MM-DD")
            g.add_argument("--last", default=None, choices=sorted(_LASTS),
                           help="快捷档：近一个月/半年/一年")
            sp.add_argument("--to", dest="date_to", default=None,
                            metavar="YYYY-MM-DD")
            sp.add_argument("--png", default=None,
                            help="另存 PNG 饼图（需 matplotlib，可选依赖）")
            sp.add_argument("--dump-data", default=None, metavar="路径.csv",
                            help="导出画饼数据 csv（utf-8-sig）")
    return p


def _window(a):
    """把 --from/--to/--last 归一成 (d1, d2)；都缺省 = None（当前行口径）。"""
    d2 = a.date_to or date.today().isoformat()
    if a.last:
        d1 = (date.today() - timedelta(days=_LASTS[a.last])).isoformat()
    elif a.date_from:
        d1 = a.date_from
    else:
        return None
    return d1, d2


def _print_table(field, segments, closed):
    label = dict(zip(CFG.names, CFG.labels)).get(field, field)
    total = sum(n for _k, n in segments)
    print(f"字段：{label}（{field}）  共 {total} 个项目")
    print(f"{'段':<24}{'计数':>6}{'占比':>8}")
    print("-" * 40)
    for k, n in segments:
        print(f"{k:<24}{n:>6}{n / total * 100:>7.1f}%")
    print("-" * 40)
    print("（口径：open 项目" + ("，含已归档" if closed else "") +
          "；只读分析，绝不写库）")


def main(argv=None):
    a = _build_parser().parse_args(argv)
    fn = ALGOS[a.algo][0]
    db = Database(os.path.join(BASE_DIR, CFG.db_name))
    try:
        if a.algo == "pie":
            if a.top < 1:
                raise AnalysisError("--top 必须是 >=1 的整数")
            win = _window(a)
            date_field = "__snap__" if (win and not a.date_field) \
                else a.date_field
            if a.date_field:
                ftypes = {f["name"]: f["type"] for f in CFG.fields}
                if a.date_field not in ftypes:
                    raise AnalysisError(
                        f"--date-field 不存在的字段：{a.date_field}")
                if ftypes[a.date_field] != "date":
                    raise AnalysisError(
                        f"--date-field 必须是 date 类型字段：{a.date_field}")
            d1 = d2 = None
            if win:
                d1 = _norm_date(win[0], "--from/--last")
                d2 = _norm_date(win[1], "--to")
            segments = fn(db, a.field, closed=a.closed, top=a.top,
                          where=a.where, date_field=date_field,
                          d1=d1, d2=d2, dump=a.dump_data, png=a.png)
            _print_table(a.field, segments, a.closed)
        return 0
    except AnalysisError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
