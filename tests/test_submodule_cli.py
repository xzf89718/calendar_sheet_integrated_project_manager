# -*- coding: utf-8 -*-
"""子模块命令行（python -m db_xxx）测试。

真实 fields.json 配置 + 临时库文件，走 subprocess 全链路验证：
db_split / db_copy / db_append / db_assign / db_analysis / setup.sh。
这些测试不依赖 conftest 的最小配置补丁（CLI 是独立进程）。
"""
import os
import subprocess
import sys

import pytest

from db import Database
from conftest import PROJECT_ROOT


def _run(mod, *argv):
    return subprocess.run(
        [sys.executable, "-m", mod, *argv],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))


@pytest.fixture()
def lib(tmp_path):
    """造一个 3 项目的小库（真实配置字段），返回路径。"""
    path = str(tmp_path / "lib.db")
    db = Database(path)
    for city, cust in [("北京", "甲"), ("上海", "乙"), ("北京", "丙")]:
        db.create_project(city=city, customer=cust, product="P1",
                          status="open", start_date="2026-01-01")
    db.conn.commit()
    db.close()
    return path


# ---------- db_split ----------

def test_split_preview_and_run(lib, tmp_path):
    out = str(tmp_path / "out")
    r = _run("db_split", lib, "--key", "城市", "--preview")
    assert r.returncode == 0
    assert "北京" in r.stdout and "上海" in r.stdout

    r = _run("db_split", lib, "--key", "city", "--dest", out)
    assert r.returncode == 0
    assert "完成：2 个文件" in r.stdout
    files = os.listdir(out)
    assert len(files) == 2
    # 每个输出库都是合法库，项目数对得上
    for f in files:
        d = Database(os.path.join(out, f))
        try:
            n = len(d.list_projects())
            assert n in (1, 2)
        finally:
            d.close()


def test_split_refuses_existing(lib, tmp_path):
    out = str(tmp_path / "out")
    assert _run("db_split", lib, "--key", "city", "--dest", out).returncode == 0
    r = _run("db_split", lib, "--key", "city", "--dest", out)
    assert r.returncode == 1
    assert "已存在" in r.stderr


def test_split_bad_key(lib):
    r = _run("db_split", lib, "--key", "不存在的列", "--dest", "/tmp/x")
    assert r.returncode == 1
    assert "没有" in r.stderr


# ---------- db_copy ----------

def test_copy_selected_and_all(lib, tmp_path):
    dst = str(tmp_path / "dst.db")
    r = _run("db_copy", lib, dst, "1", "2")
    assert r.returncode == 0
    assert "已复制 2 个项目" in r.stdout
    d = Database(dst)
    try:
        assert len(d.list_projects()) == 2
    finally:
        d.close()

    r = _run("db_copy", lib, dst, "--all")
    assert "已复制 3 个项目" in r.stdout
    d = Database(dst)
    try:
        # 追加语义：叠加不覆盖，2 + 3 = 5
        assert len(d.list_projects()) == 5
    finally:
        d.close()


def test_copy_requires_selection(lib, tmp_path):
    r = _run("db_copy", lib, str(tmp_path / "x.db"))
    assert r.returncode != 0


# ---------- db_append ----------

def test_append(lib, tmp_path):
    target = str(tmp_path / "t.db")
    Database(target).close()          # 空库
    r = _run("db_append", target, lib)
    assert r.returncode == 0
    assert "合计追加 3 个项目" in r.stdout
    d = Database(target)
    try:
        assert len(d.list_projects()) == 3
    finally:
        d.close()


def test_append_rejects_same_file(lib):
    r = _run("db_append", lib, lib)
    assert r.returncode == 1
    assert "同一个文件" in r.stderr


# ---------- db_assign ----------

def test_assign_dry_run_then_execute(lib):
    r = _run("db_assign", lib, "--field", "城市", "--value", "广州")
    assert r.returncode == 0
    assert "预览" in r.stdout and "--yes" in r.stdout
    # 干跑不写库
    d = Database(lib)
    try:
        n0 = sum(len(d.get_snapshots(p["id"]))
                 for p in d.list_projects())
    finally:
        d.close()
    assert n0 == 3                      # 每项目仍只有建库时那一条

    r = _run("db_assign", lib, "--field", "city", "--value", "广州", "--yes")
    assert r.returncode == 0
    assert "已赋值 3 / 3" in r.stdout
    d = Database(lib)
    try:
        rows = d.list_projects()
        assert all(r["city"] == "广州" for r in rows)
        # 每项目最新一条是"批量赋值"快照（走跟进方法，可回溯）；
        # 更早的"创建项目"快照原样保留
        for p in rows:
            snaps = d.get_snapshots(p["id"])
            assert "批量赋值" in snaps[-1]["change_summary"]
            assert len(snaps) == 2
    finally:
        d.close()


# ---------- db_analysis 占位 ----------

def test_analysis_placeholder():
    r = _run("db_analysis")
    assert r.returncode == 0
    assert "占位" in r.stdout


# ---------- setup.sh 快捷命令 ----------

def test_setup_shims(tmp_path):
    """setup.sh 生成的 shim 必须：不依赖 cwd、参数原样透传。"""
    r = subprocess.run(
        ["bash", "setup.sh"], capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))
    assert r.returncode == 0
    shim = os.path.expanduser("~/.local/bin/db_split")
    assert os.path.islink(shim)
    # 从与项目无关的目录调用，仍能解析包路径
    r = subprocess.run([shim, "--help"], capture_output=True, text=True,
                       timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0
    assert "db_split" in r.stdout
