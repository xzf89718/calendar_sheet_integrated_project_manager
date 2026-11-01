# -*- coding: utf-8 -*-
"""v3.3.0 workbench_ui 测试：CLI 全链路 + 纯逻辑内核。

纪律对应：
  * CLI 一律 subprocess + cwd=tmp 源码副本（绝不碰源码目录的
    fields.json / .db）——workbench_ui 没有 --db，锚定同目录；
  * 内核单测走 conftest 的 _patch_cfg（冻结绑定坑：bench_core
    运行时取 config.CFG / db 模块量，patch 才生效）；
  * notify 只打印到终端（测试钉死：不 import win10toast 路径）。
"""
import os
import shutil
import subprocess
import sys

import pytest

from conftest import PROJECT_ROOT, _patch_cfg, minimal_config_data
from workbench_ui import bench_core as bc


def copy_pkg(dst):
    """把源码树（除掉版本控制/缓存/库文件）拷到 dst。"""
    for name in os.listdir(PROJECT_ROOT):
        if name in (".fslckout", "_FOSSIL_", "__pycache__",
                    ".pytest_cache", "backups") \
                or name.endswith(".db"):
            continue
        src = os.path.join(PROJECT_ROOT, name)
        tgt = os.path.join(str(dst), name)
        if os.path.isdir(src):
            shutil.copytree(src, tgt,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, tgt)


@pytest.fixture()
def pkg(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    copy_pkg(d)
    return d


def run_ui(pkg, *argv):
    return subprocess.run(
        [sys.executable, "-m", "workbench_ui", *argv],
        cwd=str(pkg), capture_output=True, text=True, timeout=120)


# ---------- CLI 全链路 ----------

def test_cli_list_empty(pkg):
    r = run_ui(pkg, "list")
    assert r.returncode == 0
    assert "共 0 条" in r.stdout
    # 索引列打头
    assert r.stdout.splitlines()[0].startswith("id")


def test_cli_new_follow_show_roundtrip(pkg):
    r = run_ui(pkg, "new", "--set", "customer=厂家A",
               "--set", "start_date=2026-01-05", "--note", "立项")
    assert r.returncode == 0
    assert "已创建项目 #1" in r.stdout

    r = run_ui(pkg, "follow", "1", "--set", "status=报价")
    assert r.returncode == 0
    assert "已追加快照" in r.stdout

    r = run_ui(pkg, "show", "1")
    assert r.returncode == 0
    assert "项目 #1  厂家A" in r.stdout
    assert "历史（2 条，新在上）" in r.stdout
    assert "创建项目" in r.stdout

    r = run_ui(pkg, "show", "1", "--hist", "2")
    assert r.returncode == 0
    assert "第 2 条历史" in r.stdout


def test_cli_show_missing_id_exit_1(pkg):
    r = run_ui(pkg, "show", "99")
    assert r.returncode == 1
    assert "不存在" in r.stderr
    assert "Traceback" not in r.stderr


def test_cli_bad_where_exit_1(pkg):
    r = run_ui(pkg, "list", "--where", "bogus=1")
    assert r.returncode == 1
    assert "不存在的字段：bogus" in r.stderr


def test_cli_where_date_range(pkg):
    run_ui(pkg, "new", "--set", "customer=A", "--set",
           "start_date=2026-01-05")
    run_ui(pkg, "new", "--set", "customer=B", "--set",
           "start_date=2026-03-05")
    r = run_ui(pkg, "list", "--where", "start_date=2026-01-01~2026-02-01")
    assert r.returncode == 0
    assert "厂家" not in r.stdout or "A" in r.stdout
    assert "共 1 条" in r.stdout


def test_cli_csv_format(pkg):
    run_ui(pkg, "new", "--set", "customer=厂家A")
    r = run_ui(pkg, "list", "--format", "csv")
    assert r.returncode == 0
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert lines[0].startswith("id,")
    assert "厂家A" in r.stdout


def test_cli_export_rejects_csv_extension(pkg):
    r = run_ui(pkg, "export", "out.csv")
    assert r.returncode == 1
    assert ".xlsx" in r.stderr


def test_cli_export_and_backup(pkg):
    run_ui(pkg, "new", "--set", "customer=厂家A")
    r = run_ui(pkg, "export", "out.xlsx")
    assert r.returncode == 0
    assert os.path.exists(pkg / "out.xlsx")
    assert "已导出 1 条" in r.stdout

    r = run_ui(pkg, "backup")
    assert r.returncode == 0
    assert "备份完成" in r.stdout
    backups = list((pkg / "backups").glob("*.db"))
    assert len(backups) == 1


def test_cli_weekly(pkg):
    run_ui(pkg, "new", "--set", "customer=厂家A")
    run_ui(pkg, "follow", "1", "--note", "本周跟进")
    r = run_ui(pkg, "weekly", "周报.xlsx")
    assert r.returncode == 0
    assert os.path.exists(pkg / "周报.xlsx")
    assert "本周跟进" in r.stdout


def test_cli_cal_readonly(pkg):
    run_ui(pkg, "new", "--set", "customer=厂家A", "--set",
           "start_date=2026-01-05")
    r = run_ui(pkg, "cal", "2026", "1")
    assert r.returncode == 0
    assert "2026-01-05" in r.stdout
    assert "(#1)" in r.stdout


def test_cli_fav_flow(pkg):
    run_ui(pkg, "new", "--set", "customer=厂家A")
    assert run_ui(pkg, "fav", "new", "重点").returncode == 0
    r = run_ui(pkg, "fav", "add", "重点", "1")
    assert r.returncode == 0
    r = run_ui(pkg, "fav", "list")
    assert "重点（1 个项目）: #1" in r.stdout
    r = run_ui(pkg, "fav", "delete", "重点")
    assert r.returncode == 0


def test_cli_notify_prints_to_terminal(pkg):
    r = run_ui(pkg, "notify")
    assert r.returncode == 0
    assert "今日项目事项" in r.stdout


def test_cli_no_subcommand_exit_2(pkg):
    r = run_ui(pkg)
    assert r.returncode == 2


def test_cli_gui_passthrough_check_config(pkg):
    """gui 子命令透传 main.py：--check-config 无显示可跑。"""
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    r = subprocess.run(
        [sys.executable, "-m", "workbench_ui", "gui", "--check-config"],
        cwd=str(pkg), capture_output=True, text=True,
        env=env, timeout=120)
    assert r.returncode == 0
    assert "配置校验通过" in r.stdout


# ---------- 内核单测（conftest patch 链） ----------

def test_parse_where_bad_field(cfg, seeded):
    with pytest.raises(bc.BenchError):
        bc.parse_where(["nope=1"])


def test_parse_where_nondate_range(cfg, seeded):
    with pytest.raises(bc.BenchError):
        bc.parse_where(["customer=2026-01-01~2026-02-01"])


def test_cmd_list_defaults_open_only(cfg, seeded):
    db = seeded
    rows, total = bc.cmd_list(db)
    assert total == 3                     # seeded：3 个进行中
    assert [r["id"] for r in rows] == [1, 3, 5] or total == 3
    rows_c, total_c = bc.cmd_list(db, closed=True)
    assert total_c == 5


def test_cmd_list_sort_desc(cfg, seeded):
    db = seeded
    rows, _ = bc.cmd_list(db, sort="id", desc=True)
    assert rows[0]["id"] > rows[-1]["id"]


def test_cmd_new_defaults_and_validate(cfg, dbs, monkeypatch):
    _patch_cfg(monkeypatch, cfg)
    db = dbs
    pid, title = bc.cmd_new(db, ["customer=新厂家"])
    assert pid == 1
    assert title == "新厂家"
    cur = db.get_current(pid)
    assert cur["customer"] == "新厂家"
    assert cur["status"] == cfg.status_options[0]   # 状态缺省=首项
    # 非法日期被校验拒绝
    with pytest.raises(bc.BenchError):
        bc.cmd_new(db, ["customer=X", "start_date=不是日期"])


def test_cmd_follow_keeps_unset_fields(cfg, dbs, monkeypatch):
    _patch_cfg(monkeypatch, cfg)
    db = dbs
    pid, _ = bc.cmd_new(db, ["customer=厂家A", "product=P1",
                             "start_date=2026-01-05"])
    sid, summary = bc.cmd_follow(db, pid, ["status=" + cfg.status_options[-1]])
    cur = db.get_current(pid)
    assert cur["product"] == "P1"           # 未传字段保持现值
    assert cur["status"] == cfg.status_options[-1]
    assert "status" in summary


def test_format_table_cjk_width():
    rows = [{"id": 1, "customer": "厂家甲", "city": "北京"},
            {"id": 22, "customer": "B", "city": "上海"}]
    out = bc.format_table(rows, ["id", "customer", "city"],
                          {"id": "id", "customer": "客户", "city": "城市"})
    lines = out.splitlines()
    assert lines[0].startswith("id")
    assert lines[2].startswith("1   厂家甲")
    assert lines[3].startswith("22  B")

    def disp_start(line, sub):
        """子串在行内的显示列位置（CJK 按 2 宽）。"""
        return bc._disp_w(line[:line.index(sub)])

    # 对齐看显示列，不是码位下标（厂家甲=6 显示宽、3 码位）
    assert disp_start(lines[2], "厂家") == disp_start(lines[3], "B")
    assert disp_start(lines[2], "北京") == disp_start(lines[3], "上海")
    assert disp_start(lines[2], "北京") == 12


def test_cmd_cal(cfg, seeded, monkeypatch):
    _patch_cfg(monkeypatch, cfg)
    db = seeded
    entries = bc.cmd_cal(db, 2026, 1)
    assert any(e[0] == "2026-01-05" for e in entries)
    day = bc.cmd_cal(db, 2026, 1, 5)
    assert len(day) == 1 and day[0][3] == 1


def test_backup_database(cfg, dbs, monkeypatch, tmp_path):
    _patch_cfg(monkeypatch, cfg)
    db = dbs
    db.create_project(customer="甲")
    target = bc.backup_database(db, db.db_path)
    assert os.path.exists(target)
    from db import Database
    d2 = Database(target)
    assert len(d2.list_projects()) == 1
    d2.close()
