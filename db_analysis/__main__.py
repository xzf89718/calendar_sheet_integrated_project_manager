# -*- coding: utf-8 -*-
"""db_analysis：只读数据分析统一入口（v3.5.0；v3.5.1 多变量饼图）。

    python -m db_analysis pie --field 客户 [--field 城市 ...] [--closed]
            [--top N] [--where 字段=值 ...] [--date-field 名]
            [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
            [--png [路径或目录]] [--dump-data [路径或目录]]

铁律：绝不写库。库锚定 fields.json 同目录（软件设计准则，
不提供 --db 路径参数）。--field 可多次：多变量共享同一组筛选
条件；输出文件名自动嵌入筛选摘要（v3.5.1，用户定）。
退出码：0 成功 / 1 业务错误（stderr，无 traceback）/ 2 参数错误。
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CFG, BASE_DIR            # noqa: E402
from db import Database, normalize_date     # noqa: E402

from .analysis_core import AnalysisError    # noqa: E402
from . import algo_pie                      # noqa: E402

# 算法表：子命令名 → (内核函数, 一句话说明)。GUI 预留数据源。
ALGOS = {
    "pie": (algo_pie.cmd_pies, "选定字段取值分布饼图 + 计数（可多字段）"),
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
            sp.add_argument("--field", action="append", required=True,
                            metavar="字段",
                            help="统计字段，可多次（多变量共享筛选条件；"
                                 "date 类型自 v3.5.1 起允许）")
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
            sp.add_argument("--png", nargs="?", const="__AUTO__",
                            default=None, metavar="路径或目录",
                            help="另存 PNG 饼图，每字段一个文件（需 matplotlib）；"
                                 "不带值或给目录 = 自动命名（文件名嵌筛选摘要）")
            sp.add_argument("--dump-data", nargs="?", const="__AUTO__",
                            default=None, metavar="路径或目录",
                            help="导出画饼数据 csv（utf-8-sig）；不带值或给"
                                 "目录 = 自动命名（文件名嵌筛选摘要）")
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


def _safe(s):
    """文件名安全化（与 main.py / bench_core 同一规则）。"""
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" .") or "x"


def _cond_summary(a, d1, d2):
    """筛选条件 → 文件名摘要段（v3.5.1 用户定：输出文件名嵌筛选条件）。"""
    parts = list(a.where or [])
    if d1:
        parts.append(f"{a.date_field or '跟进'}={d1}~{d2}")
    if a.closed:
        parts.append("含归档")
    return _safe("_".join(parts)) if parts else "全量"


def _resolve_out(base, stem, ext, conds, multi):
    """输出路径裁定：__AUTO__（裸参数）或目录 → 自动命名
    pie_<字段>_<筛选摘要>_<时间戳>.<ext>；显式文件名 → 单字段原样，
    多字段把字段名插到扩展名前。"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    auto = f"pie_{_safe(stem)}_{conds}_{ts}{ext}"
    if base == "__AUTO__":
        return auto
    if os.path.isdir(base):
        return os.path.join(base, auto)
    if multi:
        root, e = os.path.splitext(base)
        if e.lower() != ext:
            raise AnalysisError(f"输出路径需要 {ext} 扩展名：{base}")
        return f"{root}_{_safe(stem)}{e}"
    if not base.lower().endswith(ext):
        raise AnalysisError(f"输出路径需要 {ext} 扩展名：{base}")
    return base


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
            # 多变量共享同一组筛选条件；个别字段无匹配 = 跳过+提示，
            # 全部无匹配才报业务错误（v3.5.1）
            label_of = dict(zip(CFG.names, CFG.labels))
            results = []                        # [(field, label, segments)]
            for f in a.field:
                label = label_of.get(f, f)
                got = fn(db, [f], closed=a.closed, top=a.top,
                         where=a.where, date_field=date_field,
                         d1=d1, d2=d2)
                segments = got[0][1] if got else []
                if segments:
                    results.append((f, label, segments))
                else:
                    print(f"提示：字段「{label}」无匹配项目，跳过")
            if not results:
                raise AnalysisError(
                    "所有字段都无匹配项目（检查 --where / 日期区间 /"
                    " 是否缺 --closed）")
            for f, label, segments in results:
                _print_table(f, segments, a.closed)
            conds = _cond_summary(a, d1, d2)
            multi = len(results) > 1
            if a.png:
                for f, label, segments in results:
                    path = _resolve_out(a.png, label, ".png", conds, multi)
                    algo_pie.render_png(segments, path, title=label)
                    print(f"PNG 已写出：{path}")
            if a.dump_data:
                stem = "-".join(label for _f, label, _s in results)
                path = _resolve_out(a.dump_data, stem, ".csv", conds,
                                    False)
                algo_pie.dump_csv([(label, segments)
                                   for _f, label, segments in results],
                                  path)
                print(f"数据已导出：{path}")
        return 0
    except AnalysisError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
