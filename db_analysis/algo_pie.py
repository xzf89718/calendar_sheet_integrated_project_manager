# -*- coding: utf-8 -*-
"""饼图算法（v3.5.0 首个分析插件）：计数表 + 可选 PNG + 可选 csv 数据导出。

- 计数表输出在 __main__.py（终端必有）；
- PNG 需要 matplotlib（可选依赖，缺失由 CLI 端提示跳过）；
- --dump 导出画饼用的段数据：csv，utf-8-sig + 纯 LF，
  与 v3.4.0 导出端编码纪律一致（Excel 双击中文不乱码）。
"""

import csv

from .analysis_core import AnalysisError


def cmd_pies(db, fields, closed=False, top=9, where=None,
             date_field=None, d1=None, d2=None):
    """多变量饼图内核（v3.5.1）：逐字段取数 + 归段，共享全部筛选条件。

    空字段不抛错，返回空 segments 由调用方决定跳过策略（CLI：个别跳过 +
    提示，全部为空才报业务错误）。

    :param db: 已打开的库。
    :type db: db.Database
    :param fields: 统计字段英文 name 列表。
    :type fields: list
    :param closed: 是否含已归档项目。
    :type closed: bool
    :param top: 段数上限。
    :type top: int
    :param where: --where 筛选列表。
    :type where: list 或 None
    :param date_field: 日期区间作用的列。
    :type date_field: str 或 None
    :param d1: 区间起点。
    :type d1: str 或 None
    :param d2: 区间终点。
    :type d2: str 或 None
    :return: [(field_name, [(段名, 计数), ...]), ...]。
    :rtype: list
    """
    from . import analysis_core as ac
    out = []
    for f in fields:
        values = ac.collect_rows(db, f, closed=closed, where=where,
                                 date_field=date_field, d1=d1, d2=d2)
        out.append((f, ac.aggregate(values, top=top)))
    return out


def cmd_pie(db, field, **kw):
    """单字段兼容包装（GUI / 算法表用）。

    :param db: 已打开的库。
    :type db: db.Database
    :param field: 统计字段英文 name。
    :type field: str
    :param kw: 透传给 cmd_pies 的筛选参数（closed/top/where/...）。
    :type kw: dict
    :return: [(段名, 计数), ...]。
    :rtype: list
    :raises AnalysisError: 无匹配项目时。
    """
    results = cmd_pies(db, [field], **kw)
    segments = results[0][1]
    if not segments:
        raise AnalysisError("没有匹配的项目（检查 --where / 日期区间 / "
                            "是否缺 --closed）")
    return segments


def dump_csv(results, path):
    """画饼数据 -> csv 文件（utf-8-sig + 纯 LF，与导出端编码纪律一致）。

    单字段保持 v3.5.0 两列格式（段,计数），多字段加「字段」列。

    :param results: [(字段中文 label, [(段名, 计数), ...]), ...]。
    :type results: list
    :param path: 输出路径，必须 .csv 结尾。
    :type path: str
    :raises AnalysisError: 路径不是 .csv 时。
    """
    if not str(path).lower().endswith(".csv"):
        raise AnalysisError("--dump 只支持 .csv 路径："
                            f"{path}")
    multi = len(results) > 1
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow((["字段"] if multi else []) + ["段", "计数"])
        for label, segs in results:
            for k, n in segs:
                w.writerow(([label] if multi else []) + [k, n])


def render_png(segments, path, title=""):
    """matplotlib 饼图渲染（可选依赖）。

    中文字体按 Microsoft YaHei -> SimHei -> Noto Sans CJK 顺序探测，
    全失败仍出图但中文可能显示为方框（附警告）。

    :param segments: [(段名, 计数), ...]。
    :type segments: list
    :param path: PNG 输出路径。
    :type path: str
    :param title: 图标题（段名），空 = 只写"分布"。
    :type title: str
    :raises AnalysisError: matplotlib 缺失或路径不可写时。
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        raise AnalysisError("未安装 matplotlib，无法出 PNG"
                            "（pip install matplotlib；计数表不受影响）")
    for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                 "Noto Sans CJK", "WenQuanYi Zen Hei"):
        if any(f.name == cand for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [cand]
            break
    else:
        print("警告：找不到中文字体，饼图中文可能显示为方框")
    plt.rcParams["axes.unicode_minus"] = False
    labels = [k for k, _n in segments]
    sizes = [n for _k, n in segments]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90,
           textprops={"fontsize": 10})
    ax.set_title(f"{title} 分布" if title else "分布")
    fig.tight_layout()
    try:
        fig.savefig(path)
    except OSError as e:
        raise AnalysisError(f"PNG 写出失败：{e}")
    finally:
        plt.close(fig)
