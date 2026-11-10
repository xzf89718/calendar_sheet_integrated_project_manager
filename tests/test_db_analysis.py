# -*- coding: utf-8 -*-
"""v3.5.0/v3.5.1 db_analysis 测试：CLI 子进程 + 只读铁律 + 日期口径。

纪律同 test_workbench_ui：subprocess + cwd=tmp 源码副本（库锚定
fields.json 同目录）；日期口径用例直接 SQL 回写 snapshot_at 造历史。
v3.5.1：--field 可多次共享筛选；date 类型字段解禁为饼图变量；
输出文件名自动嵌筛选摘要。v3.5.2：--dump 改名 + 裸参数默认输出
目录 db_analysis/pie/{plots,dump}/。
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
    hits = list(pkg.glob("db_analysis/pie/dump/pie_customer-city_city=沪_*.csv"))
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
    """v3.5.2 用户定：裸 --dump 默认存 db_analysis/pie/dump/。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--dump")
    assert r.returncode == 0
    hits = list(pkg.glob("db_analysis/pie/dump/pie_customer_*.csv"))
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
    """v3.5.2 用户定：裸 --png 默认存 db_analysis/pie/plots/。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--png")
    assert r.returncode == 0
    hits = list(pkg.glob("db_analysis/pie/plots/pie_customer_*.png"))
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
    pngs = list(pkg.glob("db_analysis/pie/plots/pie_*_city=沪_*.png"))
    assert len(pngs) == 2


# ---------- v3.8.0 timeline：项目分类时间点可视化（markdown 表格） ----------

def _mk(pkg, customer, start, nxt=None, close=None, extra=()):
    args = ["new", "--set", f"customer={customer}",
            "--set", f"start_date={start}", "--note", "立项"]
    if nxt:
        args += ["--set", f"next_followup={nxt}"]
    if close:
        args += ["--set", f"close_date={close}"]
    args += list(extra)
    assert run_ui(pkg, *args).returncode == 0


def test_timeline_basic_md_table(pkg):
    """默认 rolling 窗口：md 表格头、12 个月列、着色 #、全部项目章。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    assert "## 全部项目（1 个项目）" in r.stdout
    assert "| 项目 | 日差 | 开始日期 | 最后跟进 | 下一个跟进日期 | 项目关闭日期 | 窗外 |" in r.stdout
    for m in ("26-05", "26-11", "27-04"):      # 当月-6 ~ 当月+5
        assert m in r.stdout
    assert '<font color="#2e7d32">#</font>' in r.stdout   # 开始行绿
    assert '<font color="#1565c0">#</font>' in r.stdout   # 最后跟进蓝
    assert '<font color="#e65100">#</font>' in r.stdout   # 跟进橙
    assert "甲" in r.stdout


def test_timeline_year_mode_january_first(pkg):
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--mode", "year")
    assert r.returncode == 0, r.stderr
    head = r.stdout.splitlines()
    tbl = next(l for l in head if l.startswith("| 项目 |"))
    assert "26-01" in tbl and "26-12" in tbl and "27-04" not in tbl


def test_timeline_split_four_chapters_in_order(pkg):
    """四章顺序：逾期未跟进 → 待跟进 → 未排跟进 → 已关闭；
    已关闭章只画开始/关闭两格（每项目 2 行数据）。"""
    _mk(pkg, "逾期", "2026-09-01", "2026-11-01")     # diff = -9
    _mk(pkg, "正常", "2026-11-01", "2026-11-25")     # diff = +15
    _mk(pkg, "无排期", "2026-08-01")
    _mk(pkg, "已成单", "2026-05-01", close="2026-10-01")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' "
                  "WHERE id=(SELECT MAX(id) FROM projects)")
    r = run_ana(pkg, "timeline", "--split")
    assert r.returncode == 0, r.stderr
    i1 = r.stdout.index("## 逾期未跟进")
    i2 = r.stdout.index("## 待跟进")
    i3 = r.stdout.index("## 未排跟进")
    i4 = r.stdout.index("## 已关闭")
    assert i1 < i2 < i3 < i4
    assert "## 全部项目" not in r.stdout
    # 已关闭章内：已成单 只有 2 行（开始/关闭），无跟进格
    arch = r.stdout[i4:]
    assert arch.count("| 已成单") == 1


def test_timeline_archived_outside_month_annotated(pkg):
    """窗口外的时间点进「窗外」列标注月份，不画 #。"""
    _mk(pkg, "老单", "2024-03-01", close="2024-06-01")
    with _db(pkg) as c:
        c.execute("UPDATE projects SET status='closed' WHERE id=1")
    r = run_ana(pkg, "timeline")
    assert r.returncode == 0, r.stderr
    assert "24-03" in r.stdout and "24-06" in r.stdout   # 窗外月份


def test_timeline_where_filter_and_sort_desc(pkg):
    _mk(pkg, "甲", "2026-11-01", "2026-11-12")     # diff +2
    _mk(pkg, "乙", "2026-11-01", "2026-11-30")     # diff +20
    r = run_ana(pkg, "timeline", "--where", "customer=乙")
    assert r.returncode == 0, r.stderr
    assert "乙" in r.stdout and "甲" not in r.stdout
    r2 = run_ana(pkg, "timeline", "--sort", "diff", "--desc")
    assert r2.returncode == 0, r2.stderr
    assert r2.stdout.index("| 乙 | 20 |") < r2.stdout.index("| 甲 | 2 |")
    r3 = run_ana(pkg, "timeline", "--sort", "customer", "--desc")
    assert r3.returncode == 0


def test_timeline_sort_bad_field_errors(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline", "--sort", "bogus")
    assert r.returncode == 1
    assert "--sort 不存在的字段" in r.stderr


def test_timeline_path_writes_md_and_refuses_file(pkg):
    """--path 只接受目录：裸参数写 db_analysis/timeline/ 自动命名；
    显式文件路径报错（v3.5.2 规矩）。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--path")
    assert r.returncode == 0, r.stderr
    hits = list(pkg.glob("db_analysis/timeline/timeline_*.md"))
    assert len(hits) == 1
    text = hits[0].read_text(encoding="utf-8")
    assert "项目时间线图" in text and "<font color=" in text
    outdir = pkg / "outdir"
    outdir.mkdir()
    r = run_ana(pkg, "timeline", "--path", str(outdir))
    assert r.returncode == 0
    assert len(list(outdir.glob("timeline_*.md"))) == 1
    r = run_ana(pkg, "timeline", "--path", str(outdir / "x.md"))
    assert r.returncode == 1
    assert "只支持目录" in r.stderr


def test_timeline_dump_csv_to_stdout(pkg):
    """--dump：csv 文本打印到终端，纯 # 不着色。"""
    _mk(pkg, "甲", "2026-11-01", "2026-11-20")
    r = run_ana(pkg, "timeline", "--dump")
    assert r.returncode == 0, r.stderr
    assert "项目,日差,开始日期,最后跟进,下一个跟进日期,项目关闭日期,窗外" in r.stdout
    assert ",26-05," in r.stdout
    assert "<font" not in r.stdout.split("项目,日差", 1)[1]


def test_timeline_cols_validation(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline", "--cols", "customer", "x", "y", "z")
    assert r.returncode == 1
    assert "--cols 必须是 date 类型字段" in r.stderr
    r = run_ana(pkg, "timeline", "--cols", "start_date", "last",
                "next_followup", "close_date")
    assert r.returncode == 0, r.stderr
    assert "| 开始日期 | 最后跟进 | 下一个跟进日期 | 项目关闭日期 |" in r.stdout


def test_timeline_colors_validation(pkg):
    _mk(pkg, "甲", "2026-11-01")
    r = run_ana(pkg, "timeline", "--colors", "red", "#111111",
                "#222222", "#333333")
    assert r.returncode == 1
    assert "#RRGGBB" in r.stderr


# ---------- timeline 纯逻辑单元测试（不 subprocess） ----------

def test_timeline_window_rolling_six_back_five_fwd():
    from db_analysis.algo_timeline import window_months
    from datetime import date
    months = window_months("rolling", today=date(2026, 11, 10))
    assert len(months) == 12
    assert months[0][:2] == (2026, 5)          # 当月-6
    assert months[-1][:2] == (2027, 4)         # 当月+5
    labels = [l for _y, _m, l in months]
    assert labels[0] == "26-05" and labels[-1] == "27-04"
    year = window_months("year", today=date(2026, 3, 1))
    assert year[0][:2] == (2026, 1) and year[-1][:2] == (2026, 12)


def test_timeline_split_groups_excludes_empty_chapters():
    from db_analysis.algo_timeline import split_groups
    rows = [{"archived": False, "diff": -1},
            {"archived": False, "diff": 3},
            {"archived": True, "diff": None}]
    groups = split_groups(rows)
    assert [n for n, _g in groups] == ["逾期未跟进", "待跟进", "已关闭"]
