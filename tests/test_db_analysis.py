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



# ---------- v3.8.1 timeline：项目分类时间点可视化（每项目一表） ----------

COLS = ["start_date", "next_followup", "close_date"]


def _mk(pkg, customer, start, nxt=None, close=None):
    args = ["new", "--set", f"customer={customer}",
            "--set", f"start_date={start}", "--note", "立项"]
    if nxt:
        args += ["--set", f"next_followup={nxt}"]
    if close:
        args += ["--set", f"close_date={close}"]
    assert run_ui(pkg, *args).returncode == 0


def _tbl_rows(text, name):
    """某项目的表内所有行（含表头/分隔）：定位首列 = name 的数据行，
    连同其上两行表头/分隔（v3.8.3 起无 ### 小标题）。"""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("| " + name + " |"):
            return [x for x in lines[i - 2:i + 4] if x.startswith("|")]
    raise AssertionError(f"找不到项目行：{name}")


def _row_cells(line):
    return [c.strip() for c in line.split("|")[1:-1]]


def _n_hash(line):
    """去掉 font 标签后数 # 个数（月格内 4 字符，一格可有多个 #）。"""
    import re
    return len(re.sub(r"#\w{6}", "",
                      re.sub(r"</?font[^>]*>", "", line)).replace(" ", "")) \
        if False else re.sub(r"</?font[^>]*>|#\w{6}", "", line).count("#")


def test_timeline_nondump_prints_summary_and_writes_file(pkg):
    """非 dump：终端不打印 md 本体，只打印筛选/统计/路径；
    md 恒写出为文件（v3.8.1 用户定）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--cols", *COLS)
    assert r.returncode == 0, r.stderr
    assert "筛选：" in r.stdout
    assert "文件已写出：" in r.stdout
    assert "| 项目 |" not in r.stdout            # md 本体不上终端
    hits = list(pkg.glob("db_analysis/timeline/timeline_*.md"))
    assert len(hits) == 1
    text = hits[0].read_text(encoding="utf-8")
    assert "项目时间线图" in text
    # v3.8.3 版式：3 日期列 + 头/尾列 + 12 个月列（26-05 起）+ 状态/备注
    assert ("| 项目 | 日差 | 开始日期 | 下一个跟进日期 | 项目关闭日期"
            " | 头 | 26-05 |" in text)
    assert " | 尾 | 状态 | 备注 |" in text


def test_timeline_each_project_own_table_four_segment_rows(pkg):
    """v3.8.3 用户贴图定版：每项目一张表，4 行线段，顺序固定
    开始-今日/最近跟进/下个跟进/关闭；首行带项目名/日期/状态。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    _mk(pkg, "乙", "2026-09-15", "2026-11-25")
    r = run_ana(pkg, "timeline", "--cols", *COLS)
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    # 无单独小标题（用户定）；未分章只有「全部项目」一个章标题
    assert not any(l.startswith("### ") for l in text.splitlines())
    assert sum(1 for l in text.splitlines() if l.startswith("## ")) == 1
    rows = _tbl_rows(text, "甲")
    assert len(rows) == 6                    # 表头 + 分隔 + 4 行线段
    lead = [c for c in _row_cells(rows[2]) if c and not c.startswith("<font")]
    assert lead == ["甲", "10", "2026-11-01", "2026-11-20", "跟进中",
                    "开始-今日"]
    notes = [c for c in _row_cells(rows[5]) if c]
    assert notes == ["开始-关闭"]            # 无关闭 → 不画线但保留行
    # 4 行备注顺序固定
    for i, lab in enumerate(["今日", "最近跟进", "下个跟进", "关闭"]):
        assert _row_cells(rows[2 + i])[-1] == f"开始-{lab}"


def test_timeline_seg_line_fills_weeks_from_start(pkg):
    """每行线段从开始日期逐周画 #：开始 11-01、下个跟进 11-20 →
    11 月格内 3 个 #（第 1~3 周）；今日行 2 个 #。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--cols", *COLS)
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "甲")
    assert _n_hash(rows[4]) == 3               # 开始-下个跟进：周 1→3
    assert _n_hash(rows[2]) == 2               # 开始-今日（今天 11-10）：周 1→2
    assert _n_hash(rows[5]) == 0               # 无关闭 → 空行保留
    # 月格形态：4 字符一格，# 连续
    cell = [c for c in _row_cells(rows[4])
            if c.startswith("<font")][0]
    assert "###" in cell


def test_timeline_seg_missing_endpoint_keeps_blank_row(pkg):
    """两端任缺 → 该行不画线但保留位置（用户定）。"""
    _mk(pkg, "无排期", "2026-08-01")
    r = run_ana(pkg, "timeline", "--cols", *COLS)
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "无排期")
    assert len(rows) == 6
    assert _n_hash(rows[4]) == 0 and _n_hash(rows[5]) == 0   # 下个跟进/关闭缺
    assert _n_hash(rows[2]) > 0                # 今日行照画


def test_timeline_archived_seg_stops_at_close(pkg):
    """已关闭：开始-关闭线段到关闭日期为止。"""
    _mk(pkg, "已成单", "2026-09-01", close="2026-10-15")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' WHERE id=1")
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--split")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    arch = text.split("## 已关闭")[1]
    rows = [l for l in arch.splitlines() if l.startswith("|")]
    data = rows[2:6]                           # 该章唯一项目的 4 行
    assert 4 <= _n_hash(data[3]) <= 7          # 9 月初 ~ 10 月中，跨月停
    assert _n_hash(data[2]) == 0               # 无下个跟进 → 空行


def test_timeline_outside_months_in_head_tail(pkg):
    """窗口外的月份写进头/尾标注列（各一个，表示显示不完，用户定）。"""
    _mk(pkg, "老单", "2024-03-10", close="2027-06-15")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' WHERE id=1")
    r = run_ana(pkg, "timeline", "--cols", *COLS)
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    rows = _tbl_rows(text, "老单")
    head_i = _row_cells(rows[0]).index("头")
    tail_i = _row_cells(rows[0]).index("尾")
    close_row = _row_cells(rows[5])
    assert "24-03" in close_row[head_i]        # 开始在头列
    assert "27-06" in close_row[tail_i]        # 关闭在尾列
    assert _n_hash(rows[5]) == 48              # 夹边界铺满 12 个月格


def test_timeline_split_chapters_order_and_nav_links(pkg):
    """四章顺序 + 文首章导航超链接（用户定 v3.8.3 返修）。"""
    _mk(pkg, "逾期", "2026-09-01", "2026-11-01")
    _mk(pkg, "正常", "2026-11-01", "2026-11-25")
    _mk(pkg, "无排期", "2026-08-01")
    _mk(pkg, "已成单", "2026-05-01", close="2026-10-01")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' "
                  "WHERE id=(SELECT MAX(id) FROM projects)")
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--split")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    # 文首导航：在第一个 ## 章标题之前
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
    r = run_ana(pkg, "timeline", "--cols", *COLS,
                "--where", "customer=乙")
    assert r.returncode == 0, r.stderr
    assert "customer=乙" in r.stdout
    assert "共 1 个项目" in r.stdout
    r2 = run_ana(pkg, "timeline", "--cols", *COLS,
                 "--sort", "diff", "--desc")
    hits = sorted(pkg.glob("db_analysis/timeline/timeline_*.md"),
                  key=lambda p: p.stat().st_mtime)
    text = hits[-1].read_text(encoding="utf-8")
    assert text.index("| 乙 |") < text.index("| 甲 |")


def test_timeline_path_explicit_dir_and_refuses_file(pkg):
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    outdir = pkg / "outdir"
    outdir.mkdir()
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--path", str(outdir))
    assert r.returncode == 0, r.stderr
    assert str(outdir) in r.stdout
    assert len(list(outdir.glob("timeline_*.md"))) == 1
    r = run_ana(pkg, "timeline", "--cols", *COLS,
                "--path", str(outdir / "x.md"))
    assert r.returncode == 1
    assert "只支持目录" in r.stderr
    # v3.8.2：不存在的显式目录自动创建
    ndir = pkg / "newdir"
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--path", str(ndir))
    assert r.returncode == 0, r.stderr
    assert ndir.is_dir() and list(ndir.glob("timeline_*.md"))
    # 文件名嵌字段名（v3.8.2：stem 用字段名而非中文 label）
    assert list(ndir.glob("timeline_start_date-*.md"))


def test_timeline_dump_prints_csv_only(pkg):
    """--dump：终端只出 csv 文本（无文件写出）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--dump")
    assert r.returncode == 0, r.stderr
    assert "项目,日差,开始日期,下一个跟进日期,项目关闭日期,头,26-05" \
        in r.stdout
    assert "<font" not in r.stdout
    assert not list(pkg.glob("db_analysis/timeline/*.md"))


def test_timeline_cols_required_and_validated(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline")               # 缺 --cols → 参数错误
    assert r.returncode == 2
    r = run_ana(pkg, "timeline", "--cols", "customer", "x", "y")
    assert r.returncode == 1
    assert "--cols 必须是 date 类型字段" in r.stderr


def test_timeline_colors_validated(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--colors",
                "red", "#111111", "#222222", "#333333")
    assert r.returncode == 1
    assert "#RRGGBB" in r.stderr


def test_timeline_default_colors_distinct(pkg):
    """默认四色绿/蓝/橙/紫，互不相同（用户定：原橙红太近）。"""
    from db_analysis.algo_timeline import DEFAULT_COLORS
    assert len(set(DEFAULT_COLORS)) == 4
    assert "#7b1fa2" in DEFAULT_COLORS          # 紫（不是红）


def test_timeline_mode_year_columns(pkg):
    """year 模式：月列换成当年 1~12 月。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--cols", *COLS, "--mode", "year")
    assert r.returncode == 0, r.stderr
    text = list(pkg.glob("db_analysis/timeline/timeline_*.md"))[0] \
        .read_text(encoding="utf-8")
    tbl = [l for l in text.splitlines() if l.startswith("| 项目 |")][0]
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
