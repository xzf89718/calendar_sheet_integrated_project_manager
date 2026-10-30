# -*- coding: utf-8 -*-
"""db.py 纯逻辑单测：查询引擎 / 快照写入 / 项目名 / 状态联动 / 收藏夹。

不启动 GUI。所有用例走 conftest 的最小配置与临时库。
"""
import pytest

from db import diff_summary, normalize_date


# ---------- normalize_date：全角/中文/混合分隔符 ----------

@pytest.mark.parametrize("raw,expect", [
    ("2026年3月19日", "2026-03-19"),
    ("２０２６／３／１９", "2026-03-19"),
    ("2026/3/5", "2026-03-05"),
    ("2026-03-05", "2026-03-05"),
    ("  2026 . 3 . 5  ", "2026-03-05"),
    ("", None),
    (None, None),
    ("下周四", None),
])
def test_normalize_date(raw, expect):
    assert normalize_date(raw) == expect


# ---------- diff_summary ----------

def test_diff_summary_create():
    assert diff_summary(None, {"note": "x"}) == "创建项目"


def test_diff_summary_changes(cfg):
    old = {"manufacturer": "甲", "amount": 10, "note": ""}
    new = {"manufacturer": "乙", "amount": 10}
    s = diff_summary(old, new)
    assert "manufacturer: 甲 → 乙" in s


def test_diff_summary_no_change(cfg):
    old = {"manufacturer": "甲"}
    new = {"manufacturer": "甲"}
    assert diff_summary(old, new) == "无字段变化（仅跟进记录）"


# ---------- 创建项目：默认值 / 命名 / 状态联动 ----------

def test_create_applies_defaults(dbs, cfg):
    pid = dbs.create_project(manufacturer="甲", customer="乙",
                             product="丙", status="进行中")
    cur = dbs.get_current(pid)
    assert cur["start_date"] == "2026-01-01"   # fields.json 的 default


def test_create_name_from_fields(dbs):
    pid = dbs.create_project(manufacturer="甲", customer="乙",
                             product="丙", status="进行中")
    assert dbs.get_project(pid)["title"] == "甲-乙-丙"


def test_create_name_fallback(dbs):
    pid = dbs.create_project(status="进行中")
    assert dbs.get_project(pid)["title"] == f"项目{pid}"


def test_create_partial_name_skips_empty(dbs):
    pid = dbs.create_project(manufacturer="甲", product="丙",
                             status="进行中")
    assert dbs.get_project(pid)["title"] == "甲-丙"


def test_status_closed_linkage(dbs):
    pid = dbs.create_project(manufacturer="甲", status="赢单")
    assert dbs.get_project(pid)["status"] == "closed"
    dbs.add_snapshot(pid, status="进行中")
    assert dbs.get_project(pid)["status"] == "open"
    dbs.add_snapshot(pid, status="输单")
    assert dbs.get_project(pid)["status"] == "closed"


def test_empty_string_becomes_null(dbs):
    pid = dbs.create_project(manufacturer="甲", note="", status="进行中")
    row = dbs.conn.execute(
        "SELECT note FROM snapshots WHERE project_id=?", (pid,)).fetchone()
    assert row["note"] is None


def test_create_summary_defaults_to_create(dbs):
    pid = dbs.create_project(manufacturer="甲", status="进行中",
                             changed_by="测试员")
    snap = dbs.get_snapshots(pid)[0]
    assert snap["change_summary"] == "创建项目"
    assert snap["changed_by"] == "测试员"


# ---------- add_snapshot ----------

def test_add_snapshot_moves_current_and_summarizes(dbs):
    # 注意：add_snapshot 要求全量字段（缺省字段会退化为 NULL，
    # 这是交接文档明示的行为，测试按合同来而不是按愿望来）
    pid = dbs.create_project(manufacturer="甲", amount=1, status="进行中")
    sid = dbs.add_snapshot(pid, manufacturer="甲", amount=2,
                           status="进行中", changed_by="李四")
    assert dbs.get_project(pid)["current_id"] == sid
    assert "amount: 1.0 → 2" in dbs.get_current(pid)["change_summary"]
    assert len(dbs.get_snapshots(pid)) == 2


def test_add_snapshot_custom_summary_wins(dbs):
    pid = dbs.create_project(manufacturer="甲", status="进行中")
    dbs.add_snapshot(pid, amount=9, change_summary="电话沟通")
    assert dbs.get_current(pid)["change_summary"] == "电话沟通"


# ---------- 列表查询引擎 ----------

def test_query_all_open_only(seeded):
    rows, total = seeded.query_projects()
    assert total == 3                     # 2 个 closed 被排除
    assert {r["title"] for r in rows} == {"厂家A-客户X-产品P1",
                                          "厂家B-客户Y-产品P2",
                                          "厂家a-客户X-产品P4"}


def test_query_include_closed(seeded):
    _rows, total = seeded.query_projects(include_closed=True)
    assert total == 5


def test_query_choice_filter(seeded):
    rows, total = seeded.query_projects(filters={"stage": {"报价"}})
    assert total == 0                     # seeded 里没人设 stage
    rows, total = seeded.query_projects(filters={"status": {"进行中"}})
    assert total == 3


def test_query_empty_choice_set_shows_nothing(seeded):
    _rows, total = seeded.query_projects(filters={"status": set()})
    assert total == 0                     # 空集 = 全不显示


def test_query_none_filter_ignored(seeded):
    _rows, total = seeded.query_projects(filters={"status": None})
    assert total == 3


def test_query_date_range(seeded):
    _rows, total = seeded.query_projects(
        filters={"start_date": ("2026-01-01", "2026-01-31")})
    assert total == 1                     # 只有项目1（1-05）在 1 月内
    _rows, total = seeded.query_projects(
        filters={"start_date": ("2026-02-01", "2026-12-31")})
    assert total == 2                     # 项目2、项目4


def test_query_keywords_and_semantics(seeded):
    # "客户X" 命中项目1和项目4；"急" 只在项目4备注里 -> AND = 项目4
    rows, total = seeded.query_projects(
        keywords=["客户x", "急"], search_fields=["customer", "note"])
    assert total == 1
    assert rows[0]["title"] == "厂家a-客户X-产品P4"


def test_query_keyword_only_snapshot_fields(seeded):
    # title 不是快照字段，混入 search_fields 必须被忽略而不是报错
    _rows, total = seeded.query_projects(
        keywords=["甲"], search_fields=["title", "note"])
    assert total == 0


def test_query_sort_numeric(seeded):
    rows, _ = seeded.query_projects(
        include_closed=True, sort="amount", sort_desc=True)
    amounts = [r["amount"] for r in rows]
    assert amounts == sorted(amounts, reverse=True)
    assert rows[0]["amount"] == 100


def test_query_sort_text_nocase(seeded):
    rows, _ = seeded.query_projects(
        include_closed=True, sort="manufacturer")
    names = [r["manufacturer"] for r in rows]
    assert names == sorted(names, key=str.lower)


def test_query_pagination(seeded):
    rows, total = seeded.query_projects(include_closed=True,
                                        sort="id", limit=2, offset=0)
    assert total == 5 and len(rows) == 2
    rows2, _ = seeded.query_projects(include_closed=True,
                                     sort="id", limit=2, offset=2)
    assert [r["id"] for r in rows2] == [r["id"] + 2 for r in rows]


def test_query_id_filter_like_favorites(seeded):
    ids = [r["id"] for r in seeded.query_projects()[0]]
    rows, total = seeded.query_projects(filters={"id": set(ids[:2])})
    assert total == 2
    _rows, total = seeded.query_projects(filters={"id": set()})
    assert total == 0                     # 收藏夹空集 = 全不显示


def test_query_project_ids(seeded):
    ids = seeded.query_project_ids(filters={"status": {"进行中"}})
    assert len(ids) == 3


def test_query_missing_current_joined_out(seeded):
    # 没有 current_id 的项目不出现在列表（防御性：孤儿项目不炸列表）
    seeded.conn.execute("UPDATE projects SET current_id=NULL WHERE id=1")
    rows, total = seeded.query_projects()
    assert total == 2


# ---------- 收藏夹（纯索引） ----------

def test_fav_disabled_no_tables(cfg, dbs):
    tables = {r[0] for r in dbs.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "collections" not in tables


def test_fav_crud(db_fav):
    # collection_items 对 projects 有外键：必须先有真实项目
    p1 = db_fav.create_collection("重点")
    c2 = db_fav.create_collection("备选")
    assert [c[1] for c in db_fav.list_collections()] == ["重点", "备选"]
    db_fav.collection_rename(c2, "二期")
    assert db_fav.collection_name(c2) == "二期"
    pid1 = db_fav.create_project(manufacturer="甲", status="进行中")
    pid2 = db_fav.create_project(manufacturer="乙", status="进行中")
    c1 = p1
    db_fav.collection_add(c1, [pid1, pid2, pid2])          # 重复加入幂等
    assert db_fav.collection_projects(c1) == [pid1, pid2]
    db_fav.collection_remove(c1, pid1)
    assert db_fav.collection_projects(c1) == [pid2]
    detail = dict(db_fav.collection_items_detail(c1))
    assert pid2 in detail
    db_fav.delete_collection(c2)
    assert [c[0] for c in db_fav.list_collections()] == [c1]


def test_fav_prunes_deleted_projects(db_fav):
    c1 = db_fav.create_collection("重点")
    pid1 = db_fav.create_project(manufacturer="甲", status="进行中")
    db_fav.collection_add(c1, [pid1])
    db_fav.delete_project(pid1)
    assert db_fav.collection_projects(c1) == []


# ---------- 周报供给 ----------

def test_snapshots_between(seeded):
    snaps = seeded.snapshots_between("2000-01-01", "2100-01-01")
    assert len(snaps) == 5
    assert all("ptitle" in s.keys() for s in snaps)


def test_weekly_plan(seeded):
    seeded.add_snapshot(1, next_followup="2026-04-01")
    rows = seeded.weekly_plan("2026-03-30", "2026-04-05")
    assert len(rows) == 1 and rows[0]["id"] == 1


# ---------- 日历供给 ----------

def test_calendar_entries_current_month(seeded):
    entries = seeded.calendar_entries(2026, 3)
    kinds = {e["kind"] for e in entries}
    assert entries and all(e["date"].startswith("2026-03") for e in entries)
    assert "start" in kinds
    # closed 项目不上日历
    assert all("厂家C" not in e["text"] and "厂家E" not in e["text"]
               for e in entries)


def test_calendar_entries_for_subset(seeded):
    entries = seeded.calendar_entries_for([1, 3], 2026, 3)
    assert entries == []                  # 1 和 3 三月都没有日期
    entries = seeded.calendar_entries_for([1], 2026, 1)
    assert len(entries) == 1


# ---------- 删除 ----------

def test_delete_project_removes_all(seeded):
    seeded.delete_project(1)
    assert seeded.get_project(1) is None
    assert seeded.get_snapshots(1) == []
