# -*- coding: utf-8 -*-
"""v3.5.0/v3.5.1 db_analysis 测试：CLI 子进程 + 只读铁律 + 日期口径。

纪律同 test_workbench_ui：subprocess + cwd=tmp 源码副本（库锚定
fields.json 同目录）；日期口径用例直接 SQL 回写 snapshot_at 造历史。
v3.5.1：--field 可多次共享筛选；date 类型字段解禁为饼图变量；
输出文件名自动嵌筛选摘要。v3.5.2：--dump 改名 + 裸参数默认输出
目录 db_analysis/pie/（v3.8.2 收拢，不再分 plots/dump）。
"""
import hashlib
import importlib.util
import os
import sqlite3
import subprocess
import sys

import pytest

from conftest import PROJECT_ROOT
from test_workbench_ui import copy_pkg, run_ui

HAS_MPL = importlib.util.find_spec("matplotlib") is not None


def run_ana(pkg, *argv):
    return subprocess.run(
        [sys.executable, "-m", "db_analysis", *argv],
        cwd=str(pkg), capture_output=True, text=True, timeout=120)


@pytest.fixture()
def pkg(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    copy_pkg(d)
    return d


def _db(pkg):
    return sqlite3.connect(str(pkg / "sales_pm.db"))


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_pie_basic_counts(pkg):
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=乙", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=乙", "--note", "复购")
    r = run_ana(pkg, "pie", "--field", "customer")
    assert r.returncode == 0
    assert "共 3 个项目" in r.stdout
    assert "乙" in r.stdout and "甲" in r.stdout
    assert "2" in r.stdout and "66.7%" in r.stdout


def test_pie_closed_flag(pkg):
    run_ui(pkg, "new", "--set", "customer=在跟", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=已完", "--note", "立项")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' WHERE id=2")
    r = run_ana(pkg, "pie", "--field", "customer")
    assert "在跟" in r.stdout and "已完" not in r.stdout
    r = run_ana(pkg, "pie", "--field", "customer", "--closed")
    assert "在跟" in r.stdout and "已完" in r.stdout
    assert "含已归档" in r.stdout


def test_pie_where_filter(pkg):
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=乙", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer",
                "--where", "customer=甲")
    assert r.returncode == 0
    assert "共 1 个项目" in r.stdout
    assert "乙" not in r.stdout.split("（口径")[0]


def test_pie_window_last_and_range(pkg):
    """日期口径：窗口内取"当时最新"快照；窗口外项目被排除。"""
    run_ui(pkg, "new", "--set", "customer=新", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=旧", "--note", "立项")
    with _db(pkg) as c:
        c.execute("UPDATE snapshots SET snapshot_at='2026-08-01 10:00:00' "
                  "WHERE project_id=2")
    r = run_ana(pkg, "pie", "--field", "customer", "--last", "1m")
    assert "共 1 个项目" in r.stdout and "新" in r.stdout
    r = run_ana(pkg, "pie", "--field", "customer",
                "--from", "2026-07-01", "--to", "2026-08-31")
    assert "旧" in r.stdout and "新" not in r.stdout.split("（口径")[0]
    # 不给区间 = 当前行口径，两个都在
    r = run_ana(pkg, "pie", "--field", "customer")
    assert "共 2 个项目" in r.stdout


def test_pie_date_field_snapshot_column(pkg):
    """--date-field 指定快照里的 date 字段（作用于快照列而非 snapshot_at）。"""
    run_ui(pkg, "new", "--set", "customer=六月", "--set",
           "start_date=2026-06-01", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=九月", "--set",
           "start_date=2026-09-01", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer",
                "--date-field", "start_date",
                "--from", "2026-01-01", "--to", "2026-06-30")
    assert "六月" in r.stdout
    assert "九月" not in r.stdout.split("（口径")[0]


def test_pie_top_merges_tail(pkg):
    for i in range(10):
        run_ui(pkg, "new", "--set", f"customer=客{i}", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--top", "3")
    assert r.returncode == 0
    assert "其他" in r.stdout
    head = r.stdout.split("（口径")[0]
    assert "客0" in head and "客2" in head and "客3" not in head


def test_pie_dump_data_csv(pkg):
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    outdir = pkg / "outdir"
    outdir.mkdir()
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump", str(outdir))
    assert r.returncode == 0
    hits = list(outdir.glob("pie_customer_*.csv"))
    assert len(hits) == 1
    raw = hits[0].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")          # utf-8-sig BOM
    assert b"\r\n" not in raw                        # 纯 LF
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == "段,计数"
    assert "甲,1" in text


def test_pie_readonly_hash_unchanged(pkg):
    """只读铁律：跑完 pie 库文件字节不变。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    dbp = pkg / "sales_pm.db"
    before = _sha(dbp)
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump")
    assert r.returncode == 0
    assert _sha(dbp) == before


# ---------- v3.5.1：多变量饼图共享筛选条件 ----------

def test_pie_multi_field_shared_where(pkg):
    """一个命令多个 --field：共享同一组筛选条件，逐字段出表。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=乙", "--set", "city=沪",
           "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=丙", "--set", "city=京",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--where", "city=沪")
    assert r.returncode == 0
    assert "共 2 个项目" in r.stdout
    assert "丙" not in r.stdout and "京" not in r.stdout
    assert "甲" in r.stdout and "乙" in r.stdout and "沪" in r.stdout


def test_pie_date_field_as_pie_variable(pkg):
    """v3.5.1 解禁：date 类型字段可作饼图变量（原值归段，空值归（空））。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set",
           "start_date=2026-06-01", "--note", "立项")
    run_ui(pkg, "new", "--set", "customer=乙", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "start_date")
    assert r.returncode == 0
    assert "2026-06-01" in r.stdout and "（空）" in r.stdout


def test_pie_dump_auto_filename_embeds_where(pkg):
    """v3.5.1 用户定：输出文件名嵌筛选摘要；裸 --dump 自动命名。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--where", "city=沪", "--dump")
    assert r.returncode == 0
    hits = list(pkg.glob("db_analysis/pie/pie_customer-city_city=沪_*.csv"))
    assert len(hits) == 1
    text = hits[0].read_bytes().decode("utf-8-sig")
    assert text.splitlines()[0] == "字段,段,计数"
    assert "customer,甲,1" in text
    assert "city,沪,1" in text


def test_pie_dump_multi_has_field_column(pkg):
    """多字段导出 csv 带「字段」列；单字段保持 v3.5.0 两列格式。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    givendir = pkg / "givendir"
    givendir.mkdir()
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--dump", str(givendir))
    assert r.returncode == 0
    hits = list(givendir.glob("pie_customer-city_*.csv"))
    assert len(hits) == 1
    text = hits[0].read_bytes().decode("utf-8-sig")
    assert text.splitlines()[0] == "字段,段,计数"
    assert "customer,甲,1" in text and "city,沪,1" in text
    # 单字段仍是两列
    singledir = pkg / "singledir"
    singledir.mkdir()
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump", str(singledir))
    assert len(list(singledir.glob("*.csv"))) == 1
    hits = list(singledir.glob("*.csv"))
    assert hits[0].read_bytes().decode(
        "utf-8-sig").splitlines()[0] == "段,计数"


# ---------- v3.5.2：默认输出目录 + --dump 改名 ----------

def test_pie_dump_default_dir(pkg):
    """v3.5.2 用户定；v3.8.2 收拢：裸 --dump 默认存 db_analysis/pie/。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--dump")
    assert r.returncode == 0
    hits = list(pkg.glob("db_analysis/pie/pie_customer_*.csv"))
    assert len(hits) == 1
    assert "甲,1" in hits[0].read_bytes().decode("utf-8-sig")


def test_pie_dump_explicit_dir(pkg):
    """显式给目录仍按用户指定（不进默认目录）。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    outdir = pkg / "myout"
    outdir.mkdir()
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump", str(outdir))
    assert r.returncode == 0
    hits = list(outdir.glob("pie_customer_*.csv"))
    assert len(hits) == 1


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 未安装")
def test_pie_png_default_dir(pkg):
    """v3.5.2 用户定；v3.8.2 收拢：裸 --png 默认存 db_analysis/pie/。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--png")
    assert r.returncode == 0
    hits = list(pkg.glob("db_analysis/pie/pie_customer_*.png"))
    assert len(hits) == 1 and hits[0].stat().st_size > 1000


@pytest.mark.parametrize("argv,msg", [
    (("pie", "--field", "bogus"), "不存在的字段"),
    (("pie", "--field", "customer", "--dump", "x.txt"),
     "只支持目录"),
    (("pie", "--field", "customer", "--where", "bogus=1"), "不存在的字段"),
    (("pie", "--field", "customer", "--from", "bad-date"), "不是有效日期"),
    (("pie", "--field", "customer", "--where", "customer=不存在"),
     "所有字段都无匹配项目"),
])
def test_pie_errors_exit_1(pkg, argv, msg):
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    r = run_ana(pkg, *argv)
    assert r.returncode == 1
    assert msg in r.stderr
    assert "Traceback" not in r.stderr


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 未安装")
def test_pie_png_output(pkg):
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    outdir = pkg / "outdir"
    outdir.mkdir()
    r = run_ana(pkg, "pie", "--field", "customer", "--png", str(outdir))
    assert r.returncode == 0
    hits = list(outdir.glob("pie_customer_*.png"))
    assert len(hits) == 1 and hits[0].stat().st_size > 1000


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 未安装")
def test_pie_multi_png_one_file_per_field(pkg):
    """v3.5.1 用户定：PNG 每字段一个文件（拒绝多子图单文件）。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--where", "city=沪", "--png")
    assert r.returncode == 0
    pngs = list(pkg.glob("db_analysis/pie/pie_*_city=沪_*.png"))
    assert len(pngs) == 2



# ---------- timeline：项目分类时间点可视化（v3.8.3 贴图定版；
# v3.8.4 配置化：基准列/画法/色进 fields.json 的 timeline 段） ----------


def _mk(pkg, customer, start, nxt=None, close=None):
    args = ["new", "--set", f"customer={customer}",
            "--set", f"start_date={start}", "--note", "立项"]
    if nxt:
        args += ["--set", f"next_followup={nxt}"]
    if close:
        args += ["--set", f"close_date={close}"]
    assert run_ui(pkg, *args).returncode == 0


def _tbl_rows(text, name):
    """某项目的表内所有行（含表头/分隔）：定位表格外单独成行的
    项目名标题（v3.8.6），取其后的表头/分隔 + 4 行线段行。"""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if f"<b>{name}</b>" in l and not l.startswith("|"):
            return [x for x in lines[i + 1:i + 8] if x.startswith("|")]
    raise AssertionError(f"找不到项目行：{name}")


def _row_cells(line):
    return [c.strip() for c in line.split("|")[1:-1]]


def _n_hash(line):
    """去掉 font 标签与颜色码后数标记个数（# 与 $，月格内 4 字符；
    v3.8.9 起 spot 模式用 $）。"""
    import re
    s = re.sub(r"</?font[^>]*>|#\w{6}", "", line)
    return s.count("#") + s.count("$")


def test_timeline_nondump_prints_summary_and_writes_file(pkg):
    """非 dump：终端不打印 md 本体，只打印筛选/统计/路径；
    md 恒写出为文件（v3.8.1 用户定）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    assert "筛选：" in r.stdout
    assert "文件已写出：" in r.stdout
    assert "| 开始 |" not in r.stdout            # md 本体不上终端
    hits = list(pkg.glob("db_analysis/timeline/timeline_*.md"))
    assert len(hits) == 1
    text = hits[0].read_text(encoding="utf-8")
    assert "项目时间线图" in text
    # v3.8.4 版式：前导列名固定 开始/下一个跟进/关闭 + 日差 + 头/尾
    assert "| 开始 | 下一个跟进 | 关闭 | 日差 | 头 | 26-05 |" in text
    assert " | 尾 | 状态 | 备注 |" in text


def test_timeline_title_row_and_fixed_col_names(pkg):
    """v3.8.4（用户定）：项目名不是列，是每个表格的第一行；首行带
    3 日期值/日差/状态；线段行只有 # 线 + 备注。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    _mk(pkg, "乙", "2026-09-15", "2026-11-25")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    assert not any(l.startswith("### ") for l in text.splitlines())
    # v3.8.6（用户定）：项目名移出表格，单独一行加粗放大标题
    name_line = next(l for l in text.splitlines() if "<b>甲</b>" in l)
    assert not name_line.startswith("|") and "size=" in name_line
    rows = _tbl_rows(text, "甲")
    assert len(rows) == 6                # 表头 + 分隔 + 4 线段行
    lead = [c for c in _row_cells(rows[2]) if c and not c.startswith("<font")]
    assert lead[:2] == ["2026-11-01", "2026-11-20"]
    assert lead[2].isdigit() and lead[3] == "跟进中"
    for i, lab in enumerate(["今日", "最近跟进", "下一个跟进", "关闭"]):
        assert _row_cells(rows[2 + i])[-1] == f"开始-{lab}"


def test_timeline_line_partial_cell_dash_filled(pkg):
    """v3.8.9（用户定）：连线模式被触月格内，范围外用 - 填充（每格
    恒 4 字符）；点模式用 $ 标记。"""
    import re
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "甲")
    col = _row_cells(rows[0]).index("26-11")
    clean = lambda s: re.sub(r"</?font[^>]*>|#\w{6}", "", s)
    # 开始-下一个跟进（11-01 ~ 11-20，周 1→3）：26-11 格 = ###-
    assert clean(_row_cells(rows[4])[col]) == "###-"
    # 开始-今日（11-01 ~ 11-10，周 1→2）：26-11 格 = ##--
    assert clean(_row_cells(rows[2])[col]) == "##--"


def test_timeline_negative_diff_red(pkg):
    """日差 < 0 时数字标红（用户定 v3.8.4）。"""
    _mk(pkg, "逾期", "2026-09-01", "2026-11-01")     # diff < 0
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    import re
    assert re.search(r'<font color="#c62828">-\d+</font>', text)


def test_timeline_seg_line_fills_weeks_from_start(pkg):
    """line 模式：每行线段从开始日期逐周画 #：开始 11-01、下个跟进
    11-20 → 11 月格内 3 个 #（第 1~3 周）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "甲")
    assert _n_hash(rows[4]) == 3     # 开始-下一个跟进：周 1→3
    assert _n_hash(rows[2]) == 2     # 开始-今日（今天 11-10）：周 1→2
    assert _n_hash(rows[5]) == 0     # 无关闭 → 空行保留


def test_timeline_seg_missing_endpoint_keeps_blank_row(pkg):
    """两端任缺 → 该行不画线但保留位置（用户定）。"""
    _mk(pkg, "无排期", "2026-08-01")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "无排期")
    assert len(rows) == 6
    assert _n_hash(rows[4]) == 0 and _n_hash(rows[5]) == 0  # 下个跟进/关闭缺
    assert _n_hash(rows[2]) > 0      # 今日行照画


def test_timeline_head_tail_labels_earlier_later(pkg):
    """头/尾标注列文字 = <第一个月 / >第 12 个月（带年月，v3.8.8）。"""
    _mk(pkg, "老单", "2024-03-10", close="2027-06-15")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' WHERE id=1")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "老单")
    head_i = _row_cells(rows[0]).index("头")
    tail_i = _row_cells(rows[0]).index("尾")
    close_row = _row_cells(rows[5])
    assert close_row[head_i] == "<26-05"
    assert close_row[tail_i] == ">27-04"
    # v3.8.8：延伸出窗口的边缘月格一律填满 4 个 #（不画残格）
    first_col = _row_cells(rows[0]).index("26-05")
    today_cells = _row_cells(rows[2])          # 开始-今日（开始 2024 年）
    assert _n_hash(today_cells[first_col]) == 4
    assert _n_hash(rows[5]) == 48    # 夹边界铺满 12 个月格


def test_timeline_spot_plot_mode(pkg):
    """JSON timeline.plot=spot：每行只在终点日期画一个点。"""
    import json as _json
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    p = pkg / "fields.json"
    d = _json.loads(p.read_text(encoding="utf-8"))
    d["timeline"]["plot"] = "spot"
    p.write_text(_json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "甲")
    assert _n_hash(rows[4]) == 1     # 开始-下一个跟进：单点
    assert _n_hash(rows[2]) == 1     # 今日点
    assert _n_hash(rows[5]) == 0     # 无关闭 → 空行
    # v3.8.9：点模式用 $ 标记，且所在格其余位用 - 填充
    assert "$" in rows[4] and "###" not in rows[4]


def test_timeline_add_col_spot_and_colors(pkg):
    """--add-col 加列 + --add-plot spot 画点 + --add-colors 配色。"""
    import json as _json
    _mk(pkg, "甲", "2026-08-01", "2026-11-20")
    p = pkg / "fields.json"
    d = _json.loads(p.read_text(encoding="utf-8"))
    d["fields"].append({"name": "accept_date", "label": "验收日期",
                        "type": "date"})
    p.write_text(_json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = run_ana(pkg, "timeline", "--add-col", "accept_date",
                "--add-plot", "spot", "--add-colors", "#123456")
    assert r.returncode == 0, r.stderr
    hits = list(pkg.glob("db_analysis/timeline/timeline_*.md"))
    text = hits[0].read_text(encoding="utf-8")
    rows = _tbl_rows(text, "甲")
    assert "验收日期" in _row_cells(rows[0])
    title = _row_cells(rows[2])      # 第一行线段行带数据值
    assert title[3] == ""            # 未填验收日期 → 空
    # 额外列图行 = 项目名标题后第 7 行（表头/分隔 + 4 行基准之后）
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines)
             if "<b>甲</b>" in l and not l.startswith("|"))
    add_row = lines[i + 8]
    assert _row_cells(add_row)[-1] == "验收日期"
    assert _n_hash(add_row) == 0
    # 文件名嵌基准 + add-col 字段名
    assert any("accept_date" in h.name for h in hits)


def test_timeline_add_col_line_draws(pkg):
    """--add-col 默认 line 画法：从开始日期连线到该列日期。"""
    import json as _json
    _mk(pkg, "甲", "2026-08-01", "2026-11-20")
    r0 = run_ui(pkg, "follow", "1", "--set", "accept_date=2026-09-10")
    # 库表还没有该列，先补进配置再跟进
    p = pkg / "fields.json"
    d = _json.loads(p.read_text(encoding="utf-8"))
    d["fields"].append({"name": "accept_date", "label": "验收日期",
                        "type": "date"})
    p.write_text(_json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r0 = run_ui(pkg, "follow", "1", "--set", "accept_date=2026-09-10")
    assert r0.returncode == 0, r0.stderr
    r = run_ana(pkg, "timeline", "--add-col", "accept_date")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines)
             if "<b>甲</b>" in l and not l.startswith("|"))
    add_row = lines[i + 8]
    assert _row_cells(add_row)[-1] == "开始-验收日期"
    assert _n_hash(add_row) == 6     # 8 月初 ~ 9 月中，跨月
    assert "#c62828" in add_row      # 缺省 add 配色轮盘第 1 色


def test_timeline_add_colors_validated(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline", "--add-col", "close_date",
                "--add-colors", "red")
    assert r.returncode == 1
    assert "#RRGGBB" in r.stderr
    r = run_ana(pkg, "timeline", "--add-col", "close_date",
                "--add-col", "start_date", "--add-colors", "#111111")
    assert r.returncode == 1
    assert "一致" in r.stderr


def test_timeline_bad_config_reported(pkg):
    """timeline 配置错误（字段不是 date）要报可读错误。"""
    import json as _json
    _mk(pkg, "甲", "2026-11-01")
    p = pkg / "fields.json"
    d = _json.loads(p.read_text(encoding="utf-8"))
    d["timeline"]["start"] = "customer"
    p.write_text(_json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 1
    assert "timeline 配置" in r.stderr


def test_timeline_split_chapters_order_and_nav_links(pkg):
    """四章顺序 + 文首章导航超链接（用户定）。"""
    _mk(pkg, "逾期", "2026-09-01", "2026-11-01")
    _mk(pkg, "正常", "2026-11-01", "2026-11-25")
    _mk(pkg, "无排期", "2026-08-01")
    _mk(pkg, "已成单", "2026-05-01", close="2026-10-01")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' "
                  "WHERE id=(SELECT MAX(id) FROM projects)")
    r = run_ana(pkg, "timeline", "--split")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    nav = text.split("## ")[0]
    for chap in ("逾期未跟进", "待跟进", "未排跟进", "已关闭"):
        assert f"[{chap}（1 个项目）](#{chap}1-个项目)" in nav
    i1 = text.index("## 逾期未跟进")
    i2 = text.index("## 待跟进")
    i3 = text.index("## 未排跟进")
    i4 = text.index("## 已关闭")
    assert i1 < i2 < i3 < i4


def test_timeline_where_sort_and_desc(pkg):
    _mk(pkg, "甲", "2026-11-01", "2026-11-12")   # diff +2
    _mk(pkg, "乙", "2026-11-01", "2026-11-30")   # diff +20
    r = run_ana(pkg, "timeline", "--where", "customer=乙")
    assert r.returncode == 0, r.stderr
    assert "customer=乙" in r.stdout
    assert "共 1 个项目" in r.stdout
    r2 = run_ana(pkg, "timeline", "--sort", "diff", "--desc")
    hits = sorted(pkg.glob("db_analysis/timeline/timeline_*.md"),
                  key=lambda p: p.stat().st_mtime)
    text = hits[-1].read_text(encoding="utf-8")
    assert text.index("<b>乙</b>") < text.index("<b>甲</b>")


def test_timeline_path_explicit_dir_and_refuses_file(pkg):
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    outdir = pkg / "outdir"
    outdir.mkdir()
    r = run_ana(pkg, "timeline", "--path", str(outdir))
    assert r.returncode == 0, r.stderr
    assert str(outdir) in r.stdout
    assert len(list(outdir.glob("timeline_*.md"))) == 1
    r = run_ana(pkg, "timeline", "--path", str(outdir / "x.md"))
    assert r.returncode == 1
    assert "只支持目录" in r.stderr
    # v3.8.2：不存在的显式目录自动创建
    ndir = pkg / "newdir"
    r = run_ana(pkg, "timeline", "--path", str(ndir))
    assert r.returncode == 0, r.stderr
    assert ndir.is_dir() and list(ndir.glob("timeline_*.md"))
    # 文件名嵌基准字段名
    assert list(ndir.glob("timeline_start_date-*.md"))


def test_timeline_dump_prints_csv_only(pkg):
    """--dump：终端只出 csv 文本（无文件写出）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--dump")
    assert r.returncode == 0, r.stderr
    assert "开始,下一个跟进,关闭,日差,头,26-05,26-06" in r.stdout
    assert "<font" not in r.stdout
    assert not list(pkg.glob("db_analysis/timeline/*.md"))


def test_timeline_mode_year_columns(pkg):
    """year 模式：月列换成当年 1~12 月。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--mode", "year")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    tbl = [l for l in text.splitlines() if l.startswith("| 开始 |")][0]
    assert "| 头 | 26-01 |" in tbl and "| 26-12 | 尾 |" in tbl


# ---------- timeline 纯逻辑单元测试（不 subprocess） ----------

def test_timeline_window_rolling_six_back_five_fwd():
    from db_analysis.algo_timeline import window_months
    from datetime import date
    months = window_months("rolling", today=date(2026, 11, 10))
    assert len(months) == 12
    assert months[0][:2] == (2026, 5)
    assert months[-1][:2] == (2027, 4)
    year = window_months("year", today=date(2026, 3, 1))
    assert year[0][:2] == (2026, 1) and year[-1][:2] == (2026, 12)


def test_timeline_week_of_month_and_cell_index():
    from db_analysis.algo_timeline import _ym_week, _cell_index, \
        window_months
    from datetime import date
    assert _ym_week("2026-11-01")[1] == 0
    assert _ym_week("2026-11-07")[1] == 0
    assert _ym_week("2026-11-08")[1] == 1
    assert _ym_week("2026-11-29")[1] == 4   # 第 5 周，格内夹到 3
    months = window_months("rolling", today=date(2026, 11, 10))
    assert _cell_index("2026-11-01", months) == 6 * 4 + 0
    assert _cell_index("2026-11-20", months) == 6 * 4 + 2
    assert _cell_index("2026-11-29", months) == 6 * 4 + 3
    assert _cell_index("2025-01-01", months) == 0       # 窗外夹头
    assert _cell_index("2028-01-01", months) == 47      # 窗外夹尾
