# -*- coding: utf-8 -*-
"""v3.5.0/v3.5.1 db_analysis 测试：CLI 子进程 + 只读铁律 + 日期口径。

纪律同 test_workbench_ui：subprocess + cwd=tmp 源码副本（库锚定
fields.json 同目录）；日期口径用例直接 SQL 回写 snapshot_at 造历史。
v3.5.1：--field 可多次共享筛选；date 类型字段解禁为饼图变量；
输出文件名自动嵌筛选摘要。
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
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump-data", "out.csv")
    assert r.returncode == 0
    raw = (pkg / "out.csv").read_bytes()
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
                "--dump-data", "out.csv")
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
    """v3.5.1 用户定：输出文件名嵌筛选摘要；裸 --dump-data 自动命名。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--where", "city=沪", "--dump-data")
    assert r.returncode == 0
    hits = list(pkg.glob("pie_customer-city_city=沪_*.csv"))
    assert len(hits) == 1
    text = hits[0].read_bytes().decode("utf-8-sig")
    assert text.splitlines()[0] == "字段,段,计数"
    assert "customer,甲,1" in text
    assert "city,沪,1" in text


def test_pie_dump_multi_has_field_column(pkg):
    """多字段导出 csv 带「字段」列；单字段保持 v3.5.0 两列格式。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--dump-data", "given.csv")
    assert r.returncode == 0
    text = (pkg / "given.csv").read_bytes().decode("utf-8-sig")
    assert text.splitlines()[0] == "字段,段,计数"
    assert "customer,甲,1" in text and "city,沪,1" in text
    # 单字段仍是两列
    r = run_ana(pkg, "pie", "--field", "customer",
                "--dump-data", "single.csv")
    assert (pkg / "single.csv").read_bytes().decode(
        "utf-8-sig").splitlines()[0] == "段,计数"


@pytest.mark.parametrize("argv,msg", [
    (("pie", "--field", "bogus"), "不存在的字段"),
    (("pie", "--field", "customer", "--dump-data", "x.txt"),
     "需要 .csv 扩展名"),
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
    r = run_ana(pkg, "pie", "--field", "customer", "--png", "pie.png")
    assert r.returncode == 0
    out = pkg / "pie.png"
    assert out.exists() and out.stat().st_size > 1000


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 未安装")
def test_pie_multi_png_one_file_per_field(pkg):
    """v3.5.1 用户定：PNG 每字段一个文件（拒绝多子图单文件）。"""
    run_ui(pkg, "new", "--set", "customer=甲", "--set", "city=沪",
           "--note", "立项")
    r = run_ana(pkg, "pie", "--field", "customer", "--field", "city",
                "--where", "city=沪", "--png")
    assert r.returncode == 0
    pngs = list(pkg.glob("pie_*_city=沪_*.png"))
    assert len(pngs) == 2
