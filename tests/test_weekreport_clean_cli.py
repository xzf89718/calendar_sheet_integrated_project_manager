# -*- coding: utf-8 -*-
"""weekreport_clean CLI（v3.6.1）测试。

subprocess 全链路：preview / clean 双命令 + 错误参数化。
不依赖 conftest 的最小配置补丁（CLI 是独立进程）。
"""
import os
import subprocess
import sys

import pytest
from openpyxl import Workbook

from conftest import PROJECT_ROOT


def _run(*argv):
    return subprocess.run(
        [sys.executable, "-m", "weekreport_clean", *argv],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))


def _make_xlsx(path, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return str(path)


GOOD = ["2026-11-03", "A", "2026年11月3日 电话沟通报价"]
BAD = ["2026-11-03", "B", "2026-10-20 的旧记录，今天补录"]
GOOD2 = ["2026-11-04", "C", "2026/11/4 拜访，谈交期"]
HDR = ["日期", "项目", "跟进记录"]


@pytest.fixture()
def mixed(tmp_path):
    return _make_xlsx(tmp_path / "周报.xlsx", HDR, [GOOD, BAD, GOOD2])


# ---------- preview ----------

def test_preview_shows_before_after(mixed):
    r = _run("preview", mixed)
    assert r.returncode == 0
    assert "[保留]" in r.stdout and "[丢弃]" in r.stdout
    assert "保留 2 / 丢弃 1" in r.stdout
    assert "跟进记录列：跟进记录" in r.stdout
    # 只读：不产出任何文件
    assert os.listdir(os.path.dirname(mixed)) == ["周报.xlsx"]


def test_preview_missing_file():
    r = _run("preview", "no_such.xlsx")
    assert r.returncode == 1
    assert "文件不存在" in r.stderr


def test_preview_rejects_non_xlsx(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("x", encoding="utf-8")
    r = _run("preview", str(p))
    assert r.returncode == 1
    assert ".xlsx" in r.stderr


def test_preview_no_note_column(tmp_path):
    f = _make_xlsx(tmp_path / "周报.xlsx", ["日期", "项目", "备注"],
                   [GOOD])
    r = _run("preview", f)
    assert r.returncode == 1
    assert "跟进记录" in r.stderr


# ---------- clean ----------

def test_clean_default_output(mixed, tmp_path):
    r = _run("clean", mixed)
    assert r.returncode == 0
    out = tmp_path / "周报_cleaned.xlsx"
    assert out.exists()
    ws = __import__("openpyxl").load_workbook(out).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == tuple(HDR)
    assert len(rows) == 3           # 表头 + 保留 2 行
    assert [r[1] for r in rows[1:]] == ["A", "C"]


def test_clean_explicit_output(mixed, tmp_path):
    out = tmp_path / "out" / "res.xlsx"
    r = _run("clean", mixed, "-o", str(out))
    assert r.returncode == 0
    assert out.exists()


def test_clean_empty_result_refused(tmp_path):
    f = _make_xlsx(tmp_path / "周报.xlsx", HDR, [BAD])
    r = _run("clean", f)
    assert r.returncode == 1
    assert "为空" in r.stderr
    assert not (tmp_path / "周报_cleaned.xlsx").exists()


def test_clean_missing_file():
    r = _run("clean", "no_such.xlsx")
    assert r.returncode == 1
    assert "文件不存在" in r.stderr
