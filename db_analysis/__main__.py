# -*- coding: utf-8 -*-
"""db_analysis：只读数据分析统一入口（v3.5.0；v3.5.1 多变量饼图；
v3.5.2 默认输出目录 + --dump 改名；v3.8.0 timeline 时间线图；
v3.17.0 chi2 卡方列联表）。

    python -m db_analysis pie --field 客户 [--field 城市 ...] [--closed]
            [--top N] [--where 字段=值 ...] [--date-field 名]
            [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
            [--png [路径或目录]] [--dump [路径或目录]]

    python -m db_analysis timeline [--mode year|rolling]
            [--add-col 字段 ...] [--add-plot line|spot]
            [--add-colors #RRGGBB ...] [--sort 字段|diff] [--desc]
            [--split] [--where 字段=值 ...] [--path [目录]] [--dump]

    python -m db_analysis chi2 --row 字段 --col 字段 [--closed]
            [--top N] [--where 字段=值 ...] [--date-field 名]
            [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
            [--dump [目录]] [--path [目录]]

    基准四列（开始/下一个跟进/关闭/最近跟进）的字段、画法与配色在
    fields.json 的 timeline 段配置，不走 CLI（v3.8.4）。

字段参数（--field/--where/--date-field）一律填 fields.json
的英文 name，不用 GUI 显示 label。
铁律：绝不写库。库锚定 fields.json 同目录（软件设计准则，
不提供 --db 路径参数）。--field 可多次：多变量共享同一组筛选
条件；输出文件名自动嵌入筛选摘要（v3.5.1，用户定）。
v3.5.2（用户定）：--dump-data 改名 --dump；输出只接受目录（一次
可能产出多个文件，指定单文件名无法理解）——裸 --png 默认存
db_analysis/pie/（均相对 fields.json 同目录，
自动创建；v3.8.2 起 plots/dump 子目录收拢，默认直接放 pie/ 下）；显式目录按用户指定。
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
from . import algo_chi2                     # noqa: E402

# 算法表：子命令名 → (内核函数, 一句话说明)。GUI 预留数据源。
ALGOS = {
    "pie": (algo_pie.cmd_pies, "选定字段取值分布饼图 + 计数（可多字段）"),
    "timeline": (None, "项目分类时间点可视化（HTML 整页，非甘特图；"
                 "v3.8.13 起只出 HTML）"),
    "chi2": (algo_chi2.cmd_chi2, "两分类变量卡方列联表独立性检验"
             "（HTML 整页；v3.17.0）"),
}

_LASTS = {"1m": 30, "6m": 183, "1y": 365}


def _norm_date(s, opt):
    """normalize_date 的严格版：无效日期抛 AnalysisError。

    :param s: 原始日期字符串。
    :type s: str
    :param opt: 出错消息里标注的选项名（如 "--from/--last"）。
    :type opt: str
    :return: 规范化后的 YYYY-MM-DD。
    :rtype: str
    :raises AnalysisError: 日期无效时。
    """
    v = normalize_date(s)
    if not v:
        raise AnalysisError(f"{opt} 不是有效日期：{s!r}")
    return v


def _build_parser():
    """构建 db_analysis 的 argparse 解析器：pie / timeline / chi2 子命令。

    pie：--field（必填，可多次）/ --closed / --top / --where / --date-field
    / 日期区间（--from|--last 互斥 + --to）/ --png / --dump；timeline：
    --mode / --add-col / --add-plot / --add-colors / --sort / --desc /
    --split / --where / --path|--dump。每个子命令注入图标双开关。

    :return: 组装完成的 ArgumentParser。
    :rtype: argparse.ArgumentParser
    """
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
                                 "；只接受目录：不带值 = db_analysis/pie/，"
                                 "带值 = 该目录内自动命名（不存在则自动创建；"
                                 "文件名嵌筛选摘要）")
            sp.add_argument("--dump", nargs="?", const="__AUTO__",
                            default=None, metavar="目录",
                            help="导出画饼数据 csv（utf-8-sig）；只接受目录："
                                 "不带值 = db_analysis/pie/，带值 = 该目录"
                                 "内自动命名（不存在则自动创建；文件名嵌筛选"
                                 "摘要）")
        if name == "timeline":
            sp.add_argument("--mode", choices=("year", "rolling"),
                            default="rolling",
                            help="12 个月窗口：year=当年 1–12 月；"
                                 "rolling=当月-6 至 当月+5（默认）")
            sp.add_argument("--add-col", action="append", default=None,
                            metavar="字段",
                            help="额外加一个 date 字段列并画对应图行，可"
                                 "多次；画法由 --add-plot 定，配色由 "
                                 "--add-colors 定（基准四列在 fields.json "
                                 "的 timeline 段配置，不走 CLI）")
            sp.add_argument("--add-plot", choices=("line", "spot"),
                            default="line",
                            help="额外列的画法：line=从开始日期连线到该"
                                 "日期（默认）；spot=只在该日期画一个点")
            sp.add_argument("--add-colors", action="append", default=None,
                            metavar="#RRGGBB",
                            help="额外列配色，可多次，个数须与 --add-col "
                                 "一致；缺省用内置轮盘")
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
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--path", nargs="?", const="__AUTO__",
                           default="__AUTO__", metavar="目录",
                           help="HTML 写出目录（默认 db_analysis/"
                                "timeline/）；只接受目录，自动命名 "
                                "timeline_<模式>_<筛选>_<排序>_<时间戳>"
                                ".html（v3.8.13 起只出 HTML 整页，md 模式"
                                "已删）")
            g.add_argument("--dump", action="store_true",
                           help="不写出文件：把表格数据以 csv 文本打印到"
                                "终端（纯 # 不着色，便于复制再分析）")
        from show_icon import add_icon_flags
        add_icon_flags(sp)                      # 各算法子命令接受双开关
        if name == "chi2":
            sp.add_argument("--row", required=True, metavar="字段",
                            help="行字段英文 name（分类变量；可用字段由 "
                                 "fields.json 的 chi2.fields 配置，缺省 "
                                 "choice/status 字段）")
            sp.add_argument("--col", required=True, metavar="字段",
                            help="列字段英文 name（同 --row）")
            sp.add_argument("--closed", action="store_true",
                            help="把已归档（closed）项目也纳入分析")
            sp.add_argument("--top", type=int, default=0,
                            help="每轴取值数上限，超出合并「其他」；"
                                 "0 = 不合并（默认；合并会改变检验口径）")
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
            sp.add_argument("--dump", nargs="?", const="__AUTO__",
                            default=None, metavar="目录",
                            help="导出检验用到的观测数据 csv（宽表 + 边际"
                                 "合计，utf-8-sig）；只接受目录：不带值 = "
                                 "db_analysis/chi2/，带值 = 该目录内自动"
                                 "命名（不存在则自动创建；文件名嵌筛选摘要）")
            sp.add_argument("--path", nargs="?", const="__AUTO__",
                            default="__AUTO__", metavar="目录",
                            help="HTML 写出目录（默认 db_analysis/chi2/）；"
                                 "只接受目录，自动命名 chi2_<行>-<列>_<筛选>"
                                 "_<时间戳>.html")
    return p


def _window(a):
    """把 --from/--to/--last 归一成 (d1, d2) 日期区间。

    都缺省返回 None（= 当前行口径）。d2 缺省 = 今天；--last 快捷档按
    _LASTS 天数回推。

    :param a: 已解析的 argparse 命名空间（含 date_from / date_to / last）。
    :type a: argparse.Namespace
    :return: (起点, 终点) 或 None。
    :rtype: tuple 或 None
    """
    d2 = a.date_to or date.today().isoformat()
    if a.last:
        d1 = (date.today() - timedelta(days=_LASTS[a.last])).isoformat()
    elif a.date_from:
        d1 = a.date_from
    else:
        return None
    return d1, d2


def _print_table(field, segments, closed):
    """终端打印一个字段的饼图计数表（段/计数/占比 + 口径说明）。

    :param field: 字段英文 name。
    :type field: str
    :param segments: [(段名, 计数), ...]。
    :type segments: list
    :param closed: 是否含已归档项目（口径文案用）。
    :type closed: bool
    """
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
    """文件名安全化（与 main.py / bench_core 同一规则）。

    :param s: 原始名字段。
    :type s: str
    :return: 安全化后的名字段，空结果回退 "x"。
    :rtype: str
    """
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" .") or "x"


def _cond_summary(a, d1, d2):
    """筛选条件 -> 文件名摘要段（v3.5.1 用户定：文件名嵌筛选条件）。

    where 原样拼接，日期区间拼 ``date_field=起~止``（缺省字段名"跟进"），
    含归档加"含归档"；无条件时返回 "全量"。整段过 _safe 安全化。

    :param a: 已解析的 argparse 命名空间（含 where / date_field / closed）。
    :type a: argparse.Namespace
    :param d1: 区间起点，None = 无日期条件。
    :type d1: str 或 None
    :param d2: 区间终点。
    :type d2: str 或 None
    :return: 文件名条件摘要段。
    :rtype: str
    """
    parts = list(a.where or [])
    if d1:
        parts.append(f"{a.date_field or '跟进'}={d1}~{d2}")
    if a.closed:
        parts.append("含归档")
    return _safe("_".join(parts)) if parts else "全量"


def _resolve_out(base, stem, ext, conds, default_dir, prefix="pie"):
    """输出路径裁定（v3.5.2 用户定：只接受目录，文件名自动命名）。

    裸参数(__AUTO__) -> default_dir 内自动命名
    ``<prefix>_<字段>_<筛选摘要>_<时间戳>.<ext>``；显式目录不存在则自动
    创建，带扩展名的路径按"想指定文件名"拒绝。prefix 供 timeline 复用
    本规则时区分模块名。

    :param base: 用户给的输出位置，"__AUTO__" = 缺省目录。
    :type base: str
    :param stem: 文件名字段段。
    :type stem: str
    :param ext: 扩展名（含点）。
    :type ext: str
    :param conds: 条件摘要段。
    :type conds: str
    :param default_dir: 裸参数时的缺省目录。
    :type default_dir: str
    :param prefix: 文件名前缀（pie / timeline）。
    :type prefix: str
    :return: 完整输出路径。
    :rtype: str
    :raises AnalysisError: base 是文件语义的路径时。
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    auto = f"{prefix}_{_safe(stem)}_{conds}_{ts}{ext}"
    if base == "__AUTO__":
        return os.path.join(default_dir, auto)
    if os.path.isfile(base) or (not os.path.isdir(base)
                                and os.path.splitext(base)[1]):
        raise AnalysisError(
            f"输出只支持目录（一次可能产出多个文件）：{base}")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, auto)


def _ensure_parent(path):
    """自动命名的输出目录可能不存在，显式创建（v3.5.2）。

    :param path: 输出文件完整路径。
    :type path: str
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main(argv=None):
    """db_analysis CLI 总入口（python -m db_analysis）。

    parse_args（参数错误退出码 2）后播图标，按 algo 分发：pie 逐字段
    取数打印计数表，可选 PNG / csv 导出（个别字段无匹配跳过，全部无匹
    配才报业务错误）；timeline 取数、分章、排序、渲染 HTML 整页或
    --dump 终端打印 csv。AnalysisError 打印 stderr 返回 1；库在 finally
    中关闭。

    :param argv: 参数列表，None = sys.argv[1:]。
    :type argv: list 或 None
    :return: 进程退出码（0 成功 / 1 业务错误）。
    :rtype: int
    """
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
                                        "pie")
                for f, label, segments in results:
                    path = _resolve_out(a.png, label, ".png", conds,
                                        plot_dir)
                    _ensure_parent(path)
                    algo_pie.render_png(segments, path, title=label)
                    print(f"PNG 已写出：{path}")
            if a.dump:
                dump_dir = os.path.join(BASE_DIR, "db_analysis",
                                        "pie")
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
            tlcfg = tl.load_tl()
            adds = a.add_col or []
            if a.sort and a.sort != "diff" and a.sort not in CFG.names:
                raise AnalysisError(f"--sort 不存在的字段：{a.sort}"
                                    f"（可用：{'、'.join(CFG.names)}"
                                    f" 或 diff）")
            add_colors = a.add_colors or tl.DEFAULT_ADD_COLORS
            for c in add_colors:
                if not isinstance(c, str) or not c.startswith("#") \
                        or len(c) != 7:
                    raise AnalysisError(
                        f"--add-colors 每项应为 #RRGGBB：{c!r}")
            if a.add_colors and len(a.add_colors) != len(adds):
                raise AnalysisError(
                    f"--add-colors 个数（{len(a.add_colors)}）须与 "
                    f"--add-col 个数（{len(adds)}）一致")
            add_labels = [CFG.labels.get(x, x) for x in adds]
            rows = tl.collect(db, adds=adds, where=a.where)
            if not rows:
                raise AnalysisError(
                    "没有匹配的项目（检查 --where 条件）")
            tl.enrich(rows)
            groups = tl.split_groups(rows) if a.split \
                else [("全部项目", rows)]
            for _name, g in groups:
                tl.sort_rows(g, key=a.sort, desc=a.desc)
            months = tl.window_months(a.mode)
            mode_label = ("当年 12 个月" if a.mode == "year"
                          else "滚动 12 个月（当月-6 至 当月+5）")
            n_proj = sum(len(g) for _n, g in groups)
            chap = "；".join(f"{n} {len(g)}" for n, g in groups)
            conds = list(a.where or [])
            conds.append(f"模式{a.mode}")
            if a.split:
                conds.append("split")
            if adds:
                conds.append(f"加列{'-'.join(adds)}")
            if a.sort:
                conds.append(f"排序{a.sort}{'降' if a.desc else '升'}")
            conds = _safe("_".join(conds)) if conds else "全量"
            stem = "-".join([tlcfg["start"], tlcfg["next"],
                             tlcfg["close"]] + adds)
            if a.dump:                  # 终端打印 csv，不写文件
                print(tl.dump_csv_text(groups, tlcfg, adds, add_labels,
                                       a.add_plot, add_colors, months))
                print(f"\n（口径：{mode_label}；筛选：{conds}；"
                      f"共 {n_proj} 个项目：{chap}）")
                return 0
            # 非 dump：HTML 整页写文件，终端只打印摘要（用户定 v3.8.1；
            # v3.8.13 起只出 HTML，md 模式删除——markdown 表格宽度不可
            # 控，无法整体缩放适配窗口，浏览体验不可接受）
            text = tl.render_html(groups, tlcfg, adds, add_labels,
                                  a.add_plot, add_colors, months,
                                  mode_label, split=a.split)
            suffix = ".html"
            out_dir = os.path.join(BASE_DIR, "db_analysis", "timeline")
            path = _resolve_out(a.path, stem, suffix,
                                conds, out_dir, prefix="timeline")
            _ensure_parent(path)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"筛选：{conds}")
            print(f"口径：{mode_label}；共 {n_proj} 个项目：{chap}")
            print(f"文件已写出：{path}")
        if a.algo == "chi2":
            if a.top < 0:
                raise AnalysisError("--top 必须是 >=0 的整数"
                                "（0 = 不合并长尾）")
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
            res = fn(db, a.row, a.col, closed=a.closed, top=a.top,
                     where=a.where, date_field=date_field,
                     d1=d1, d2=d2)
            conds = _cond_summary(a, d1, d2)
            scope = ("open 项目" + ("，含已归档" if a.closed else "")
                     + (f"，日期窗 {a.date_field or '跟进'}"
                        f"={d1}~{d2}" if d1 else ""))
            stem = f"{res['row_label']}-{res['col_label']}"
            print(algo_chi2.format_text(res, conds, scope))
            out_dir = os.path.join(BASE_DIR, "db_analysis", "chi2")
            if a.dump:
                path = _resolve_out(a.dump, stem, ".csv", conds,
                                    out_dir, prefix="chi2")
                _ensure_parent(path)
                algo_chi2.dump_csv(res, path)
                print(f"数据已导出：{path}")
            path = _resolve_out(a.path, stem, ".html", conds,
                                out_dir, prefix="chi2")
            _ensure_parent(path)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(algo_chi2.render_html(res, conds, scope))
            print(f"文件已写出：{path}")
        return 0
    except AnalysisError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
