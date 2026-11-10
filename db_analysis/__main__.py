# -*- coding: utf-8 -*-
"""db_analysis：只读数据分析统一入口（v3.5.0；v3.5.1 多变量饼图；
v3.5.2 默认输出目录 + --dump 改名；v3.8.0 timeline 时间线图）。

    python -m db_analysis pie --field 客户 [--field 城市 ...] [--closed]
            [--top N] [--where 字段=值 ...] [--date-field 名]
            [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
            [--png [路径或目录]] [--dump [路径或目录]]

    python -m db_analysis timeline [--mode year|rolling] [--cols 4个字段]
            [--colors 4个#RRGGBB] [--sort 字段|diff] [--desc] [--split]
            [--where 字段=值 ...] [--path [目录]] [--dump]

字段参数（--field/--where/--date-field）一律填 fields.json
的英文 name，不用 GUI 显示 label。
铁律：绝不写库。库锚定 fields.json 同目录（软件设计准则，
不提供 --db 路径参数）。--field 可多次：多变量共享同一组筛选
条件；输出文件名自动嵌入筛选摘要（v3.5.1，用户定）。
v3.5.2（用户定）：--dump-data 改名 --dump；输出只接受目录（一次
可能产出多个文件，指定单文件名无法理解）——裸 --png 默认存
db_analysis/pie/plots/、裸 --dump 默认存 db_analysis/pie/dump/
（均相对 fields.json 同目录，自动创建）；显式目录按用户指定。
退出码：0 成功 / 1 业务错误（stderr，无 traceback）/
2 参数错误。
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
    "timeline": (None, "项目分类时间点可视化（markdown 表格，非甘特图）"),
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
                                 "date 类型自 v3.5.1 起允许）。"
                                 "填 fields.json 的英文 name，不是界面"
                                 "显示 label；报错会列出可用字段名")
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
                            default=None, metavar="目录",
                            help="另存 PNG 饼图，每字段一个文件（需 matplotlib）"
                                 "；只接受目录：不带值 = db_analysis/pie/"
                                 "plots/，带值 = 该目录内自动命名"
                                 "（文件名嵌筛选摘要）")
            sp.add_argument("--dump", nargs="?", const="__AUTO__",
                            default=None, metavar="目录",
                            help="导出画饼数据 csv（utf-8-sig）；只接受目录："
                                 "不带值 = db_analysis/pie/dump/，带值 = "
                                 "该目录内自动命名（文件名嵌筛选摘要）")
        if name == "timeline":
            sp.add_argument("--mode", choices=("year", "rolling"),
                            default="rolling",
                            help="12 个月窗口：year=当年 1–12 月；"
                                 "rolling=当月-6 至 当月+5（默认）")
            sp.add_argument("--cols", nargs=4, default=None, metavar="字段",
                            help="4 个日期列（开始 最后跟进 下个跟进 关闭），"
                                 "缺省从 calendar_dates 推导；最后跟进用"
                                 "特殊值 last，字段填 fields.json 的 name")
            sp.add_argument("--colors", nargs=4, default=None,
                            metavar="#RRGGBB",
                            help="4 行配色（默认绿/蓝/橙/红）")
            sp.add_argument("--sort", default=None, metavar="字段",
                            help="章内排序字段：任意库字段名或 diff（日差）；"
                                 "缺省按 diff 升序，无日差排最后")
            sp.add_argument("--desc", action="store_true",
                            help="降序（缺省升序）")
            sp.add_argument("--split", action="store_true",
                            help="按 逾期未跟进/待跟进/未排跟进/已关闭 "
                                 "分章（已关闭章只画开始/关闭两格）")
            sp.add_argument("--where", action="append", default=None,
                            metavar="字段=值",
                            help="筛选，可多次；同字段并集、异字段交集")
            sp.add_argument("--path", nargs="?", const="__AUTO__",
                            default=None, metavar="目录",
                            help="另存 markdown 到目录（终端始终打印）；"
                                 "只接受目录：不带值 = "
                                 "db_analysis/timeline/，带值 = 该目录内"
                                 "自动命名 timeline_<模式>_<筛选>_<时间戳>.md")
            sp.add_argument("--dump", action="store_true",
                            help="把表格数据以 csv 文本形式打印到终端"
                                 "（纯 # 不着色，便于复制再分析）")
        from show_icon import add_icon_flags
        add_icon_flags(sp)                      # 各算法子命令接受双开关
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


def _resolve_out(base, stem, ext, conds, default_dir, prefix="pie"):
    """输出路径裁定（v3.5.2 用户定：只接受目录，产出可能是多个
    文件，指定单文件名无法理解——显式文件一律报错）。裸参数
    (__AUTO__) → 默认目录（png = db_analysis/pie/plots/，csv =
    db_analysis/pie/dump/，md = db_analysis/timeline/）内自动命名
    <prefix>_<字段>_<筛选摘要>_<时间戳>.<ext>；显式目录 → 该目录内
    自动命名。prefix（v3.8.0）：timeline 复用本规则时区分模块名。"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    auto = f"{prefix}_{_safe(stem)}_{conds}_{ts}{ext}"
    if base == "__AUTO__":
        return os.path.join(default_dir, auto)
    if os.path.isdir(base):
        return os.path.join(base, auto)
    raise AnalysisError(
        f"输出只支持目录（一次可能产出多个文件）：{base}")


def _ensure_parent(path):
    """自动命名的输出目录可能不存在，显式创建（v3.5.2）。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main(argv=None):
    a = _build_parser().parse_args(argv)
    from show_icon import tty_if_wanted
    tty_if_wanted(a.show_icon, a.no_show_icon)
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
            if a.png:
                plot_dir = os.path.join(BASE_DIR, "db_analysis",
                                        "pie", "plots")
                for f, label, segments in results:
                    path = _resolve_out(a.png, label, ".png", conds,
                                        plot_dir)
                    _ensure_parent(path)
                    algo_pie.render_png(segments, path, title=label)
                    print(f"PNG 已写出：{path}")
            if a.dump:
                dump_dir = os.path.join(BASE_DIR, "db_analysis",
                                        "pie", "dump")
                stem = "-".join(label for _f, label, _s in results)
                path = _resolve_out(a.dump, stem, ".csv", conds,
                                    dump_dir)
                _ensure_parent(path)
                algo_pie.dump_csv([(label, segments)
                                   for _f, label, segments in results],
                                  path)
                print(f"数据已导出：{path}")
        if a.algo == "timeline":
            from . import algo_timeline as tl
            cols = a.cols or tl.default_cols()
            col_labels = tl.validate_cols(cols)
            if not any(cols):
                raise AnalysisError(
                    "推导不出任何日期列（检查 fields.json 的 "
                    "calendar_dates 配置）")
            if a.sort and a.sort != "diff" and a.sort not in CFG.names:
                raise AnalysisError(f"--sort 不存在的字段：{a.sort}"
                                    f"（可用：{'、'.join(CFG.names)}"
                                    f" 或 diff）")
            colors = a.colors or tl.DEFAULT_COLORS
            for c in colors:
                if not isinstance(c, str) or not c.startswith("#") \
                        or len(c) != 7:
                    raise AnalysisError(
                        f"--colors 每项应为 #RRGGBB：{c!r}")
            rows = tl.collect(db, cols, where=a.where)
            if not rows:
                raise AnalysisError(
                    "没有匹配的项目（检查 --where 条件）")
            tl.enrich(rows, cols)
            groups = tl.split_groups(rows) if a.split \
                else [("全部项目", rows)]
            for _name, g in groups:
                tl.sort_rows(g, key=a.sort, desc=a.desc)
            months = tl.window_months(a.mode)
            mode_label = ("当年 12 个月" if a.mode == "year"
                          else "滚动 12 个月（当月-6 至 当月+5）")
            md = tl.render_md(groups, cols, col_labels, months,
                              colors, mode_label)
            print(md)
            if a.path:
                conds = list(a.where or [])
                conds.append(f"模式{a.mode}")
                if a.split:
                    conds.append("分章")
                if a.sort:
                    conds.append(f"排序{a.sort}{'降' if a.desc else '升'}")
                conds = _safe("_".join(conds)) if conds else "全量"
                out_dir = os.path.join(BASE_DIR, "db_analysis",
                                       "timeline")
                path = _resolve_out(a.path, "-".join(col_labels),
                                    ".md", conds, out_dir,
                                    prefix="timeline")
                _ensure_parent(path)
                with open(path, "w", encoding="utf-8",
                          newline="\n") as f:
                    f.write(md)
                print(f"文件已写出：{path}")
            if a.dump:
                print(tl.dump_csv_text(groups, cols, col_labels,
                                       months))
        return 0
    except AnalysisError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
