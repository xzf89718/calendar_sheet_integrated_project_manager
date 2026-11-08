# -*- coding: utf-8 -*-
"""gui 子命令统一（v3.6.2）回归：5 个子模块废弃 --gui，统一 gui 子命令。"""
import subprocess
import sys

import pytest

from conftest import PROJECT_ROOT


@pytest.mark.parametrize("mod", [
    "db_copy", "db_append", "db_split", "db_assign", "db_recycled"])
def test_gui_flag_removed(mod):
    """--gui 不再被接受：argparse 参数错误 exit 2。"""
    r = subprocess.run(
        [sys.executable, "-m", mod, "--gui"],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))
    assert r.returncode == 2


def test_recycled_gui_needs_db():
    """db_recycled gui 需要库路径：缺路径 exit 2 + 提示。"""
    r = subprocess.run(
        [sys.executable, "-m", "db_recycled", "gui"],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))
    assert r.returncode == 2
    assert "数据库路径" in r.stderr
