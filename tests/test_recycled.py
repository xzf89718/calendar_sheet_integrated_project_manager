# -*- coding: utf-8 -*-
"""回收站（v3.1.0，B 方案）核心逻辑 + CLI 测试。

合同要点（设计定稿）：
- 开关关闭：删除 = 物理删除（与 v2.7.3 等价，回归锁在 test_db）
- 开关开启：删除 = 整行搬进 recycled_* 三张独立表，主表查询天然不命中
- 恢复：原 id 空闲则原样放回 + 收藏夹索引带回；id 被占才发新 id
- 彻底删除/清空：物理销毁，只在 db_recycled
"""
import os
import subprocess
import sys

import pytest

tk = pytest.importorskip("tkinter",
                         reason="tkinter 不可用，跳过 GUI 用例")

import db_recycled
from db import Database
from conftest import PROJECT_ROOT


@pytest.fixture()
def seeded_rec(db_rec):
    """回收站开启 + 3 项目（项目3 有两条快照）。"""
    db_rec.create_project(manufacturer="甲", status="进行中")
    db_rec.create_project(manufacturer="乙", status="进行中")
    p3 = db_rec.create_project(manufacturer="丙", status="进行中")
    db_rec.add_snapshot(p3, manufacturer="丙", note="第二跟",
                        status="进行中")
    return db_rec


# ---------- 开关行为 ----------

def test_disabled_default_physical_delete(dbs):
    # 开关关闭（默认）= 物理删除，回收表不存在
    pid = dbs.create_project(manufacturer="甲", status="进行中")
    dbs.delete_project(pid)
    assert dbs.get_project(pid) is None
    assert not dbs._table_exists("recycled_projects")


def test_enabled_delete_moves_to_recycle(seeded_rec):
    seeded_rec.delete_project(2)
    assert seeded_rec.get_project(2) is None
    rows = db_recycled.list_recycled(seeded_rec)
    assert [r[0] for r in rows] == [2]
    snaps = db_recycled.snapshots_of(seeded_rec, 2)
    assert len(snaps) == 1
    assert seeded_rec.conn.execute(
        "SELECT COUNT(*) FROM snapshots WHERE project_id=2").fetchone()[0] == 0


# ---------- 主表全部供给天然排除（B 方案的回归锁） ----------

def test_all_queries_exclude_recycled(seeded_rec):
    seeded_rec.delete_project(2)
    _rows, total = seeded_rec.query_projects(include_closed=True)
    assert total == 2
    assert len(seeded_rec.list_projects(include_closed=True)) == 2
    assert len(seeded_rec.query_project_ids(include_closed=True)) == 2
    assert len(seeded_rec.snapshots_between("2000-01-01", "2100-01-01")) == 3
    assert {e["project_id"] for e in seeded_rec.calendar_entries(
        2026, 1)} <= {1, 3}
    # 工具级 SQL 也天然排除（db_assign 式的全表枚举）
    assert 2 not in [r[0] for r in seeded_rec.conn.execute(
        "SELECT id FROM projects")]


def test_weekly_plan_excludes_recycled(seeded_rec):
    seeded_rec.add_snapshot(1, manufacturer="甲", next_followup="2026-04-01",
                            status="进行中")
    seeded_rec.delete_project(1)
    assert seeded_rec.weekly_plan("2026-03-30", "2026-04-05") == []


# ---------- 恢复 ----------

def test_restore_keeps_id_and_history(seeded_rec):
    seeded_rec.delete_project(3)
    new_id, changed = db_recycled.restore_project(seeded_rec, 3)
    assert (new_id, changed) == (3, False)
    assert seeded_rec.get_project(3)["title"] == "丙"
    snaps = seeded_rec.get_snapshots(3)
    assert len(snaps) == 2
    # current 指针仍然指向"第二跟"那条
    assert seeded_rec.get_current(3)["note"] == "第二跟"
    assert db_recycled.list_recycled(seeded_rec) == []


def test_restore_with_id_taken_gets_new_id(seeded_rec):
    seeded_rec.delete_project(1)              # 回收 1
    # AUTOINCREMENT 不会复用 1，所以手工插一行显式占住原 id
    # （不能用 UPDATE 换 id：snapshots 的外键会拦）
    with seeded_rec.conn:
        seeded_rec.conn.execute(
            "INSERT INTO projects(id, title, status) VALUES (1, '占位', 'open')")
    nid, changed = db_recycled.restore_project(seeded_rec, 1)
    assert changed is True and nid != 1
    assert seeded_rec.get_project(nid)["title"].startswith("甲")
    assert len(seeded_rec.get_snapshots(nid)) == 1


def test_restore_unknown_id_raises(seeded_rec):
    with pytest.raises(ValueError):
        db_recycled.restore_project(seeded_rec, 999)


# ---------- 收藏夹索引备份/带回 ----------

def test_fav_items_backed_up_and_restored(db_rec_fav):
    db = db_rec_fav
    pid = db.create_project(manufacturer="甲", status="进行中")
    cid = db.create_collection("重点")
    db.collection_add(cid, [pid])
    db.delete_project(pid)
    assert db.collection_projects(cid) == []           # 索引随项目进回收站
    nid, _c = db_recycled.restore_project(db, pid)
    assert db.collection_projects(cid) == [nid]        # 索引跟着回来


def test_fav_disabled_no_index_backup(db_rec):
    pid = db_rec.create_project(manufacturer="甲", status="进行中")
    db_rec.delete_project(pid)                          # 不炸即可
    assert db_recycled.list_recycled(db_rec)[0][0] == pid


# ---------- 彻底删除 / 清空 ----------

def test_purge_physically_removes(seeded_rec):
    seeded_rec.delete_project(3)
    db_recycled.purge_project(seeded_rec, 3)
    assert db_recycled.list_recycled(seeded_rec) == []
    assert seeded_rec.conn.execute(
        "SELECT COUNT(*) FROM recycled_snapshots").fetchone()[0] == 0
    assert seeded_rec.get_project(3) is None


def test_empty_recycle(seeded_rec):
    for pid in (1, 2, 3):
        seeded_rec.delete_project(pid)
    db_recycled.empty_recycle(seeded_rec)
    assert db_recycled.list_recycled(seeded_rec) == []
    assert seeded_rec.query_projects(include_closed=True)[1] == 0


def test_recycle_restore_cycle_idempotent(seeded_rec):
    seeded_rec.delete_project(2)
    db_recycled.restore_project(seeded_rec, 2)
    # 恢复后再删除再恢复，历史完整、不重复
    seeded_rec.add_snapshot(2, manufacturer="乙", note="三", status="进行中")
    seeded_rec.delete_project(2)
    nid, changed = db_recycled.restore_project(seeded_rec, 2)
    assert (nid, changed) == (2, False)
    assert len(seeded_rec.get_snapshots(2)) == 2


# ---------- CLI ----------

def _run_cli(db_path, *argv):
    return subprocess.run(
        [sys.executable, "-m", "db_recycled",
         str(db_path), *argv],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT))


def test_cli_list_and_restore_and_purge(seeded_rec, tmp_path):
    path = str(tmp_path / "rec.db")
    seeded_rec.delete_project(1)
    seeded_rec.conn.commit()
    r = _run_cli(path)                              # 无参数 = 列出回收站
    assert "甲" in r.stdout
    r = _run_cli(path, "--restore", "1")
    assert "已恢复" in r.stdout
    assert seeded_rec.get_project(1) is not None
    seeded_rec.delete_project(1)
    seeded_rec.conn.commit()
    r = _run_cli(path, "--purge", "1")
    assert "已永久删除" in r.stdout
    assert db_recycled.list_recycled(seeded_rec) == []
    for pid in (2, 3):
        seeded_rec.delete_project(pid)
    seeded_rec.conn.commit()
    r = _run_cli(path, "--empty")
    assert "已清空" in r.stdout


def test_cli_restore_all(seeded_rec, tmp_path):
    path = str(tmp_path / "rec.db")
    for pid in (1, 2, 3):
        seeded_rec.delete_project(pid)
    seeded_rec.conn.commit()
    r = _run_cli(path, "--restore", "all")
    assert "共恢复 3 个项目" in r.stdout
    assert seeded_rec.query_projects(include_closed=True)[1] == 3


# ---------- GUI 删除入口（reader._delete 的回收站分支） ----------
# 无 DISPLAY 时跳过（与 test_gui_layout 同一约定；Windows 不查 DISPLAY）
pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="无 DISPLAY（用 xvfb-run 运行）")


def test_reader_delete_confirm_mentions_recycle_bin(seeded_rec, monkeypatch):
    """回归：回收站开启时，reader 的删除确认文案必须提示"回收站"，
    且 reader 模块级能拿到 CFG（曾因局部导入导致 NameError）。"""
    import reader

    assert hasattr(reader, "CFG")          # 模块级 CFG 必须存在
    root = tk.Tk()
    try:
        captured = {}

        class _FakeDialog:
            def __init__(self, master, title, msg):
                captured["msg"] = msg
                self.result = False        # 不真删

        monkeypatch.setattr(reader, "ConfirmDialog", _FakeDialog)
        win = reader.ProjectReader(root, seeded_rec, 1)
        win._delete()
        assert "回收站" in captured["msg"]
    finally:
        root.destroy()


def test_reader_delete_confirm_physical_when_disabled(seeded, monkeypatch):
    """回收站关闭时，确认文案必须是物理删除提示。"""
    import reader

    root = tk.Tk()
    try:
        captured = {}

        class _FakeDialog:
            def __init__(self, master, title, msg):
                captured["msg"] = msg
                self.result = False

        monkeypatch.setattr(reader, "ConfirmDialog", _FakeDialog)
        win = reader.ProjectReader(root, seeded, 1)
        win._delete()
        assert "回收站" not in captured["msg"]
        assert "不可恢复" in captured["msg"]
    finally:
        root.destroy()
