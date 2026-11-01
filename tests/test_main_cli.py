# -*- coding: utf-8 -*-
"""v3.2.0 主程序命令行接口测试：--view / --check-config。

--check-config 三条路都钉死：
  1. subprocess + 无 DISPLAY：证明"不建库、不启动 GUI、无显示可跑"
  2. 坏配置端到端：拷整个源码树到 tmp 换坏 fields.json → 退出码 1、
     错误清单在 stdout、无 traceback（生产事故路径）
  3. 内核 in-process：_run_check_config(path=...) 对任意路径文件校验，
     供 db_config（v3.2.1）复用同一入口
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_main(*args, env=None):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env=env, timeout=120)


def headless_env():
    """剥掉 DISPLAY 的环境：--check-config 必须在此可跑。"""
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    return env


# ---------- --check-config：真实配置（合法） ----------

def test_check_config_ok_exit_0():
    r = run_main("--check-config", env=headless_env())
    assert r.returncode == 0
    assert "配置校验通过" in r.stdout
    assert "生效配置摘要" in r.stdout
    assert "缺省视图" in r.stdout


def test_check_config_no_db_created():
    """只校验不建库：跑完源码目录不得长出 sales_pm.db。"""
    db = os.path.join(PROJECT_ROOT, "sales_pm.db")
    assert not os.path.exists(db), "测试前置：源码目录不应有 sales_pm.db"
    run_main("--check-config", env=headless_env())
    assert not os.path.exists(db), "--check-config 建了库！"


# ---------- --check-config：坏配置（生产事故路径） ----------

def test_check_config_broken_exit_1(tmp_path):
    """坏 fields.json → 退出码 1、错误逐条列出、无 traceback。"""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for name in os.listdir(PROJECT_ROOT):
        if name in (".fslckout", "_FOSSIL_", "__pycache__",
                    ".pytest_cache") or name.endswith(".db"):
            continue
        src = os.path.join(PROJECT_ROOT, name)
        dst = str(pkg / name)
        if os.path.isdir(src):
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)
    cfg_path = pkg / "fields.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data["fields"] = []          # 触发校验错误
    cfg_path.write_text(json.dumps(data, ensure_ascii=False),
                        encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "main.py", "--check-config"],
        cwd=str(pkg), capture_output=True, text=True,
        env=headless_env(), timeout=120)
    assert r.returncode == 1
    assert "配置校验未通过" in r.stdout
    assert "fields 段缺失或为空" in r.stdout
    assert "Traceback" not in r.stderr
    # GUI 路径同样干净退出（错误清单走 stderr，退出码 1，不弹窗不建库）
    g = subprocess.run(
        [sys.executable, "main.py"],
        cwd=str(pkg), capture_output=True, text=True,
        env=headless_env(), timeout=120)
    assert g.returncode == 1
    assert "fields.json 配置错误" in g.stderr
    assert "Traceback" not in g.stderr
    assert not (pkg / "sales_pm.db").exists()


# ---------- --check-config 内核：任意路径（db_config 复用入口） ----------

def test_check_config_core_bad_json(tmp_path, capsys):
    import main
    p = tmp_path / "fields.json"
    p.write_text("{ not json", encoding="utf-8")
    assert main._run_check_config(path=str(p)) == 1
    assert "不是合法 JSON" in capsys.readouterr().out


def test_check_config_core_semantic_errors(tmp_path, capsys):
    import main
    from conftest import minimal_config_data
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(
        minimal_config_data(ui={"default_view": "bogus"}),
        ensure_ascii=False), encoding="utf-8")
    assert main._run_check_config(path=str(p)) == 1
    out = capsys.readouterr().out
    assert "ui.default_view" in out


def test_check_config_core_ok(tmp_path, capsys):
    import main
    from conftest import minimal_config_data
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(minimal_config_data(),
                            ensure_ascii=False), encoding="utf-8")
    assert main._run_check_config(path=str(p)) == 0
    assert "配置校验通过" in capsys.readouterr().out


def test_check_config_missing_file(tmp_path, capsys):
    import main
    assert main._run_check_config(path=str(tmp_path / "nope.json")) == 1
    assert "读不到文件" in capsys.readouterr().out


# ---------- --view ----------

def test_view_invalid_choice_exit_2():
    r = run_main("--view", "bogus", env=headless_env())
    assert r.returncode == 2            # argparse 标准行为


def test_resolve_view_priority():
    import main
    assert main._resolve_view("calendar") == "calendar"
    assert main._resolve_view(None) == main.CFG.default_view
    assert main._resolve_view("table") == "table"
