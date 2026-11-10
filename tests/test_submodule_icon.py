# -*- coding: utf-8 -*-
"""v3.7.1：品牌图标植入全部子模块 GUI/CLI。

- 每个子模块 --help 都能列出 --show-icon / --no-show-icon；
- 非交互（管道）下即使强制开也不输出图标（不污染机器可读输出）；
- gui 拦截路径的开关解析单元验证。
"""
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODULES = ["db_copy", "db_append", "db_split", "db_assign",
           "db_recycled", "weekreport_clean", "db_analysis"]


def _run(args, cwd=PROJECT_ROOT):
    return subprocess.run(
        [sys.executable] + args, cwd=cwd,
        capture_output=True, text=True, timeout=120)


def test_all_modules_expose_icon_flags():
    """7 个子模块 help 均列出双开关。单解析器模块看根 --help；
    子命令式模块（weekreport_clean / db_analysis）开关挂在子命令上，
    看子命令 help。"""
    for m in ("db_copy", "db_append", "db_split", "db_assign",
              "db_recycled"):              # 单解析器：根 help 即全量
        r = _run(["-m", m, "--help"])
        assert r.returncode == 0, (m, r.stderr)
        assert "--show-icon" in r.stdout, m
        assert "--no-show-icon" in r.stdout, m
    for m, sub in (("weekreport_clean", "gui"),
                   ("weekreport_clean", "preview"),
                   ("weekreport_clean", "clean"),
                   ("db_analysis", "pie")):
        r = _run(["-m", m, sub, "--help"])
        assert r.returncode == 0, (m, sub, r.stderr)
        assert "--show-icon" in r.stdout, (m, sub)
        assert "--no-show-icon" in r.stdout, (m, sub)


def test_pipe_mode_never_prints_icon():
    """stdout 非 tty（subprocess 捕获）：--show-icon 也不出图标。"""
    r = _run(["-m", "weekreport_clean", "preview", "missing.xlsx",
              "--show-icon"])
    assert r.returncode == 1            # 业务错误照旧
    assert "\x1b[" not in r.stdout      # 图标未泄漏进输出
    assert "不存在" in r.stderr


def test_gui_icon_flags_parser():
    from show_icon import gui_icon_flags
    assert gui_icon_flags(["--show-icon"]) == (True, False)
    assert gui_icon_flags(["--no-show-icon"]) == (False, True)
    assert gui_icon_flags(["--show-icon", "--no-show-icon"]) == (True, True)
    assert gui_icon_flags(["a.db", "--show-icon"]) == (True, False)
    assert gui_icon_flags([]) == (False, False)


def test_gui_flags_resolution_overrides_json():
    """--show-icon 覆盖 JSON false；--no-show-icon 覆盖 JSON true。"""
    from show_icon import resolve_show_icon
    assert resolve_show_icon(True, False, False) is True
    assert resolve_show_icon(False, True, True) is False
