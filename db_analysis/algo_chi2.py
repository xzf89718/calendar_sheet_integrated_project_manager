# -*- coding: utf-8 -*-
"""卡方列联表算法（v3.17.0）：两个分类变量的独立性检验。

给证据不给结论：输出列联表 + Pearson 卡方统计量 + 自由度 + p 值 +
Cramér's V 效应量 + 期望频数体检，不判定"相关/无关"。2×2 表且最小
期望频数 <5 时另给 Fisher 精确检验（双侧），输出注明本次用了什么检验。

- 默认不合并长尾（v3.17.0 用户定）；--top N 才把行/列取值数压到 N，
  超出合并「其他」（合并改变检验口径，故默认关闭）
- 可用字段由 fields.json 的 chi2.fields 配置；缺省 = 全部
  choice/status 字段；date 与 multiline（跟进简介类长文本）永不纳入
- 输出 HTML 整页（仿 timeline）；--dump 导出用到的观测数据 csv
  （utf-8-sig + 纯 LF，与导出端编码纪律一致）
"""
import csv

from config import CFG

from .analysis_core import AnalysisError, collect_pairs

EMPTY = "（空）"
OTHER = "其他"


def _bucket(v):
    """原始取值 -> 归段名：None/空串归「（空）」，其余转字符串。

    :param v: 数据库原始取值。
    :type v: object
    :return: 归段名。
    :rtype: str
    """
    return str(v) if v not in (None, "") else EMPTY


def _axis_order(names_totals, top):
    """一个轴的取值排序：合计降序（同值按名升序），top>0 时尾部并入「其他」。

    :param names_totals: {取值: 边缘合计}。
    :type names_totals: dict
    :param top: 取值数上限；0 = 不合并。
    :type top: int
    :return: (保留取值有序列表, 被合并取值列表)。
    :rtype: tuple
    """
    ordered = sorted(names_totals.items(), key=lambda kv: (-kv[1], kv[0]))
    if top and len(ordered) > top:
        return [k for k, _n in ordered[:top]], \
               [k for k, _n in ordered[top:]]
    return [k for k, _n in ordered], []


def _build_table(pairs, top):
    """原始配对 -> 列联表：归段、双轴 top 合并、边际合计。

    :param pairs: [(行原始值, 列原始值), ...]。
    :type pairs: list
    :param top: 每轴取值数上限；0 = 不合并。
    :type top: int
    :return: (rows, cols, obs, rtot, ctot, n)。
    :rtype: tuple
    """
    cells = {}
    rtot, ctot = {}, {}
    for rv, cv in pairs:
        r, c = _bucket(rv), _bucket(cv)
        cells[(r, c)] = cells.get((r, c), 0) + 1
        rtot[r] = rtot.get(r, 0) + 1
        ctot[c] = ctot.get(c, 0) + 1
    rows, r_drop = _axis_order(rtot, top)
    cols, c_drop = _axis_order(ctot, top)
    if r_drop:
        rows = rows + [OTHER]
        for r in r_drop:
            for c in list(ctot):
                n = cells.pop((r, c), 0)
                if n:
                    cells[(OTHER, c)] = cells.get((OTHER, c), 0) + n
    if c_drop:
        cols = cols + [OTHER]
        for c in c_drop:
            for r in list(rtot):
                n = cells.pop((r, c), 0)
                if n:
                    cells[(r, OTHER)] = cells.get((r, OTHER), 0) + n
    obs = [[cells.get((r, c), 0) for c in cols] for r in rows]
    rtot_v = [sum(row) for row in obs]
    ctot_v = [sum(obs[i][j] for i in range(len(rows)))
              for j in range(len(cols))]
    return rows, cols, obs, rtot_v, ctot_v, sum(rtot_v)


def _stats(rows, cols, obs, rtot, ctot, n):
    """列联表统计量：Pearson 卡方 + 自由度 + p 值 + Cramér's V。

    2×2 且最小期望频数 <5 时附 Fisher 精确检验（双侧）。p 值需要
    scipy；缺失时抛 AnalysisError（v3.17.0 起 scipy 为必需依赖，
    此处保留防御）。

    :param rows: 行取值列表。
    :type rows: list
    :param cols: 列取值列表。
    :type cols: list
    :param obs: 观测频数二维表。
    :type obs: list
    :param rtot: 行边缘合计。
    :type rtot: list
    :param ctot: 列边缘合计。
    :type ctot: list
    :param n: 总样本量。
    :type n: int
    :return: {chi2, dof, p, cramers_v, fisher_p, method, warnings}。
    :rtype: dict
    """
    try:
        from scipy import stats
    except ImportError:
        raise AnalysisError("未安装 scipy，无法计算 p 值"
                            "（pip install scipy）")
    expected = [[rtot[i] * ctot[j] / n for j in range(len(cols))]
                for i in range(len(rows))]
    chi2 = sum((obs[i][j] - expected[i][j]) ** 2 / expected[i][j]
               for i in range(len(rows)) for j in range(len(cols)))
    dof = (len(rows) - 1) * (len(cols) - 1)
    p = float(stats.chi2.sf(chi2, dof))
    cramers_v = (chi2 / (n * (min(len(rows), len(cols)) - 1))) ** 0.5
    min_e = min(min(row) for row in expected)
    n_small = sum(1 for row in expected for e in row if e < 5)
    warnings = []
    if n_small:
        warnings.append(
            f"期望频数 <5 的格子 {n_small}/{len(rows) * len(cols)}"
            f"（{n_small / (len(rows) * len(cols)) * 100:.0f}%）"
            f"——卡方近似可能失效，结果仅供参考")
    method = "Pearson 卡方独立性检验"
    fisher_p = None
    if len(rows) == 2 and len(cols) == 2 and min_e < 5:
        fisher_p = float(stats.fisher_exact(obs)[1])
        method += "；2×2 小样本（最小期望频数 <5），以 Fisher 精确" \
                  "检验（双侧）为准"
    return {"chi2": chi2, "dof": dof, "p": p, "cramers_v": cramers_v,
            "fisher_p": fisher_p, "method": method,
            "expected": expected, "warnings": warnings}


def _validate_axis(name, field):
    """校验 chi2 的行/列字段：存在、且在 chi2 允许清单内。

    :param name: 选项名（"--row"/"--col"，报错文案用）。
    :type name: str
    :param field: 字段英文 name。
    :type field: str
    :raises AnalysisError: 字段不存在或不允许时。
    """
    if field not in CFG.names:
        raise AnalysisError(f"{name} 不存在的字段：{field}"
                            f"（可用：{'、'.join(CFG.names)}）")
    if field not in CFG.chi2_fields:
        raise AnalysisError(f"{name} 字段 {field} 不支持列联表"
                            f"（date 类型与跟进简介类长文本不参与；"
                            f"可用：{'、'.join(CFG.chi2_fields) or '无'}；"
                            f"可在 fields.json 的 chi2.fields 配置）")


def cmd_chi2(db, row, col, closed=False, top=0, where=None,
             date_field=None, d1=None, d2=None):
    """卡方列联表内核：取配对、建表、算统计量，结果字典交渲染层。

    :param db: 已打开的库。
    :type db: db.Database
    :param row: 行字段英文 name。
    :type row: str
    :param col: 列字段英文 name。
    :type col: str
    :param closed: 是否含已归档项目。
    :type closed: bool
    :param top: 每轴取值数上限；0 = 不合并（默认）。
    :type top: int
    :param where: --where 筛选列表。
    :type where: list 或 None
    :param date_field: 日期区间作用的列。
    :type date_field: str 或 None
    :param d1: 区间起点。
    :type d1: str 或 None
    :param d2: 区间终点。
    :type d2: str 或 None
    :return: 结果字典（表、边际、统计量、method、warnings、字段名与 label）。
    :rtype: dict
    :raises AnalysisError: 字段不允许、无匹配项目或表退化为 1 格时。
    """
    _validate_axis("--row", row)
    _validate_axis("--col", col)
    pairs = collect_pairs(db, row, col, closed=closed, where=where,
                          date_field=date_field, d1=d1, d2=d2)
    if not pairs:
        raise AnalysisError("没有匹配的项目（检查 --where / 日期区间 /"
                            " 是否缺 --closed）")
    rows, cols, obs, rtot, ctot, n = _build_table(pairs, top)
    if len(rows) < 2 or len(cols) < 2:
        raise AnalysisError("行/列变量合并后只剩 1 个取值，无法做"
                            "独立性检验（换字段或放宽筛选）")
    st = _stats(rows, cols, obs, rtot, ctot, n)
    label_of = dict(zip(CFG.names, CFG.labels))
    return {"row_field": row, "col_field": col,
            "row_label": label_of.get(row, row),
            "col_label": label_of.get(col, col),
            "rows": rows, "cols": cols, "obs": obs,
            "rtot": rtot, "ctot": ctot, "n": n, **st}


def _fmt_p(p):
    """p 值格式化：常规 %.4g，极小值显 <0.0001。

    :param p: p 值。
    :type p: float
    :return: 格式化字符串。
    :rtype: str
    """
    return "<0.0001" if p < 0.0001 else f"{p:.4g}"


def format_text(res, conds, scope):
    """终端文本：观测表（含边际）+ 统计量 + 检验方法 + 告警。

    :param res: cmd_chi2 的结果字典。
    :type res: dict
    :param conds: 筛选摘要（文件名同款，终端回显）。
    :type conds: str
    :param scope: 口径说明文字。
    :type scope: str
    :return: 完整终端输出文本。
    :rtype: str
    """
    out = [f"行：{res['row_label']}（{res['row_field']}）  "
           f"列：{res['col_label']}（{res['col_field']}）  "
           f"共 {res['n']} 个项目"]
    width = max(12, max(len(c) for c in res["cols"]) + 2)
    head = f"{'':<16}" + "".join(f"{c:>{width}}" for c in res["cols"]) \
        + f"{'合计':>{width}}"
    out.append(head)
    out.append("-" * len(head))
    for i, r in enumerate(res["rows"]):
        line = f"{r:<16}" \
            + "".join(f"{v:>{width}}" for v in res["obs"][i]) \
            + f"{res['rtot'][i]:>{width}}"
        out.append(line)
    out.append("-" * len(head))
    out.append(f"{'合计':<16}"
               + "".join(f"{v:>{width}}" for v in res["ctot"])
               + f"{res['n']:>{width}}")
    out.append(f"检验：{res['method']}")
    out.append(f"卡方 = {res['chi2']:.3f}  自由度 = {res['dof']}  "
               f"p = {_fmt_p(res['p'])}  Cramér's V = "
               f"{res['cramers_v']:.3f}")
    if res["fisher_p"] is not None:
        out.append(f"Fisher 精确检验（双侧）p = {_fmt_p(res['fisher_p'])}")
    for w in res["warnings"]:
        out.append(f"注意：{w}")
    out.append(f"（筛选：{conds}；口径：{scope}；只读分析，绝不写库）")
    return "\n".join(out)


_HTML_HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>卡方列联表</title>
<style>
body{font-family:Microsoft YaHei,sans-serif;margin:10px}
table{border-collapse:collapse;margin-bottom:14px}
td,th{border:1px solid #999;padding:3px 10px;white-space:pre;
      font-family:Consolas,Menlo,monospace;text-align:center}
th{background:#f0f0f0}
h2{margin:18px 0 6px}
.warn{background:#fff3e0;border:1px solid #ffa726;padding:6px 12px;
      margin:10px 0}
.hi-pos{background:#fdecea}.hi-neg{background:#e8f0fe}
#bar{position:fixed;top:6px;right:10px;z-index:9;background:#fff;
     border:1px solid #aaa;padding:4px 10px;font-size:14px}
#bar button{font-size:16px;margin:0 2px}
</style></head><body>
<div id="bar"><button onclick="zoom(1.25)">+</button>
<button onclick="zoom(0.8)">-</button>
<button onclick="fit()">fit</button></div>
<div id="page">
"""

_HTML_TAIL = """</div>
<script>
var z=1;
function apply(){document.getElementById('page').style.zoom=z;}
function zoom(f){z*=f;apply();}
function fit(){var w=document.documentElement.clientWidth-30;var tw=0;
document.querySelectorAll('#page table').forEach(function(t){
tw=Math.max(tw,t.offsetWidth);});
if(tw>0){z=Math.min(Math.max(w/tw,0.2),4);}apply();}
window.addEventListener('load',fit);
</script></body></html>
"""


def render_html(res, conds, scope):
    """HTML 整页渲染：观测表 + 期望表 + 统计量 + 告警 + 口径页脚。

    观测表中 |标准化残差| >= 2 的格子染色（正残差浅红 = 超预期，
    负残差浅蓝 = 低于预期）——给证据，不给"相关"结论。

    :param res: cmd_chi2 的结果字典。
    :type res: dict
    :param conds: 筛选摘要。
    :type conds: str
    :param scope: 口径说明文字。
    :type scope: str
    :return: 完整 HTML 文本。
    :rtype: str
    """
    width = max(12, max(len(c) for c in res["cols"]) + 2)

    def _table(title, matrix, margins_r, margins_c, hi=False):
        """渲染一张矩阵表（观测或期望），可按要求染标准化残差格子。

        :param title: 表标题（h2）。
        :type title: str
        :param matrix: 二维数据（与 res 维度一致）。
        :type matrix: list
        :param margins_r: 行边缘合计。
        :type margins_r: list
        :param margins_c: 列边缘合计。
        :type margins_c: list
        :param hi: True = 按标准化残差染 |残差| >= 2 的格子。
        :type hi: bool
        :return: 表的 HTML 片段。
        :rtype: str
        """
        out = [f"<h2>{title}</h2>", "<table>",
               "<tr><th></th>" + "".join(f"<th>{c}</th>"
                                         for c in res["cols"])
               + "<th>合计</th></tr>"]
        for i, r in enumerate(res["rows"]):
            cells = []
            for j in range(len(res["cols"])):
                cls = ""
                if hi:
                    e = res["expected"][i][j]
                    sr = (matrix[i][j] - e) / e ** 0.5 if e else 0.0
                    if sr >= 2:
                        cls = ' class="hi-pos"'
                    elif sr <= -2:
                        cls = ' class="hi-neg"'
                cells.append(f"<td{cls}>{matrix[i][j]}</td>")
            out.append(f"<tr><th>{r}</th>" + "".join(cells)
                       + f"<td>{margins_r[i]}</td></tr>")
        out.append("<tr><th>合计</th>"
                   + "".join(f"<td>{v}</td>" for v in margins_c)
                   + f"<td>{res['n']}</td></tr>")
        out.append("</table>")
        return "".join(out)

    out = [_HTML_HEAD,
           f"<h1>卡方列联表：{res['row_label']} × {res['col_label']}"
           f"（{res['n']} 个项目）</h1>",
           f"<p>筛选：{conds}；口径：{scope}</p>"]
    for w in res["warnings"]:
        out.append(f'<div class="warn">注意：{w}</div>')
    out.append(_table("观测频数", res["obs"], res["rtot"], res["ctot"],
                      hi=True))
    exp_show = [[round(e, 1) for e in rowrow] for rowrow
                in res["expected"]]
    out.append(_table("期望频数", exp_show, res["rtot"], res["ctot"]))
    stats_rows = [
        ("检验方法", res["method"]),
        ("卡方统计量", f"{res['chi2']:.3f}"),
        ("自由度", str(res["dof"])),
        ("p 值", _fmt_p(res["p"])),
        ("Cramér's V（效应量）", f"{res['cramers_v']:.3f}"),
    ]
    if res["fisher_p"] is not None:
        stats_rows.append(("Fisher 精确检验（双侧）p 值",
                           _fmt_p(res["fisher_p"])))
    out.append("<h2>统计量</h2><table>"
               + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>"
                         for k, v in stats_rows)
               + "</table>")
    out.append("<p>给证据不给结论：本表只呈现计数与统计量，是否相关"
               "由使用者结合业务判断。|标准化残差| ≥ 2 的格子已染色"
               "（红 = 超预期，蓝 = 低于预期）。只读分析，绝不写库。</p>")
    out.append(_HTML_TAIL)
    return "".join(out)


def dump_csv(res, path):
    """列联表观测数据 -> csv 文件（utf-8-sig + 纯 LF）。

    宽表 + 边际合计：首列行取值，其后每列一个列取值，末列合计，
    末行合计——即检验实际用到的全部数据。

    :param res: cmd_chi2 的结果字典。
    :type res: dict
    :param path: 输出路径，必须 .csv 结尾。
    :type path: str
    :raises AnalysisError: 路径不是 .csv 时。
    """
    if not str(path).lower().endswith(".csv"):
        raise AnalysisError("--dump 只支持 .csv 路径："
                            f"{path}")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([f"{res['row_label']}\\{res['col_label']}"]
                   + list(res["cols"]) + ["合计"])
        for i, r in enumerate(res["rows"]):
            w.writerow([r] + list(res["obs"][i]) + [res["rtot"][i]])
        w.writerow(["合计"] + list(res["ctot"]) + [res["n"]])
