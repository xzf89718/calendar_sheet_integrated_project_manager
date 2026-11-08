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
    返回 [(field_name, segments), ...]——空字段由调用方决定跳过策略。"""
    from . import analysis_core as ac
    out = []
    for f in fields:
        values = ac.collect_rows(db, f, closed=closed, where=where,
                                 date_field=date_field, d1=d1, d2=d2)
        out.append((f, ac.aggregate(values, top=top)))
    return out


def cmd_pie(db, field, **kw):
    """单字段兼容包装（GUI/算法表用）。无匹配抛 AnalysisError。"""
    results = cmd_pies(db, [field], **kw)
    segments = results[0][1]
    if not segments:
        raise AnalysisError("没有匹配的项目（检查 --where / 日期区间 / "
                            "是否缺 --closed）")
    return segments


def dump_csv(results, path):
    """画饼数据 → csv（utf-8-sig + 纯 LF）。results =
    [(field_label, segments), ...]；单字段保持 v3.5.0 两列格式
    （段,计数），多字段加「字段」列。"""
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
    """matplotlib 饼图。中文字体按 Microsoft YaHei → SimHei →
    Noto Sans CJK 顺序探测，全失败仍出图但中文可能显示为方框
    （附警告）。抛 AnalysisError 仅当 matplotlib 缺失/路径不可写。"""
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
