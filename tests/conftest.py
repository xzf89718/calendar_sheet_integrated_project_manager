# -*- coding: utf-8 -*-
"""测试共享设施：最小 fields.json 配置 + 模块级全局量补丁。

背景（改测试前必读）：config.py 在 import 时即实例化 CFG 并读取
BASE_DIR/fields.json；db.py / importer.py / exporter.py 都用
"from config import CFG" 在 import 时绑定模块级引用，db.py 还用
CFG.names 冻结了 SNAPSHOT_FIELDS 与 _SCHEMA。因此每个测试在构造
Database 之前，必须把这些模块级全局量替换成本测试自己的最小配置
——这正是本文件两个 fixture 做的事。直接改源码目录里的 fields.json
来跑测试是绝对禁止的。
"""
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
import db  # noqa: E402
import exporter  # noqa: E402
import importer  # noqa: E402


def minimal_config_data(**over):
    """一份能通过 validate_config_data 的最小配置。

    覆盖全部字段类型：text / int / float / date / choice / status，
    name_fields 用默认的 厂家-客户-产品。
    任何测试要变体（如 favorites 开关）用关键字覆盖顶层段。
    """
    data = {
        "product_name": "测试工作台",
        "db_name": "test.db",
        "fields": [
            {"name": "manufacturer", "label": "厂家", "type": "text"},
            {"name": "customer", "label": "客户", "type": "text"},
            {"name": "product", "label": "产品", "type": "text"},
            {"name": "amount", "label": "金额", "type": "float"},
            {"name": "qty", "label": "数量", "type": "int"},
            {"name": "start_date", "label": "开始日期", "type": "date",
             "default": "2026-01-01"},
            {"name": "next_followup", "label": "下次跟进", "type": "date"},
            {"name": "close_date", "label": "关闭日期", "type": "date"},
            # followup_note：GUI 层（main.py 周报列 / reader.py 最新跟进）
            # 有硬编码引用，最小配置必须带上这个名字
            {"name": "followup_note", "label": "跟进记录", "type": "text"},
            {"name": "stage", "label": "阶段", "type": "choice",
             "choices": ["线索", "报价", "赢单", "输单"]},
            {"name": "status", "label": "状态", "type": "status",
             "choices": ["进行中", "赢单", "输单"]},
            {"name": "note", "label": "备注", "type": "text"},
        ],
        "status_closed": ["赢单", "输单"],
        "calendar_dates": [
            {"key": "start", "field": "start_date", "label": "开始",
             "color": "#2e7d32"},
            {"key": "followup", "field": "next_followup", "label": "跟进",
             "color": "#1565c0"},
            {"key": "close", "field": "close_date", "label": "关闭",
             "color": "#c62828"},
            {"key": "append", "label": "追加", "color": "#6a1b9a"},
        ],
    }
    data.update(over)
    return data


def _patch_cfg(monkeypatch, cfg_obj):
    """把 config/db/importer/exporter 四个模块里绑死的 CFG 引用
    及相关冻结量全部指向测试配置。"""
    for mod in (db, importer, exporter):
        monkeypatch.setattr(mod, "CFG", cfg_obj)
    # reader 也在模块级绑定了 CFG / SNAPSHOT_FIELDS / LABELS
    # （from db/config import 在 import 时冻结，不补会拿到真实配置的量）
    try:
        import reader
        monkeypatch.setattr(reader, "CFG", cfg_obj)
        monkeypatch.setattr(reader, "SNAPSHOT_FIELDS", cfg_obj.names)
        monkeypatch.setattr(reader, "LABELS", cfg_obj.labels)
    except ImportError:
        pass
    monkeypatch.setattr(config, "CFG", cfg_obj)
    monkeypatch.setattr(db, "SNAPSHOT_FIELDS", cfg_obj.names)
    monkeypatch.setattr(db, "STATUS_OPTIONS", cfg_obj.status_options)
    monkeypatch.setattr(db, "MILESTONES",
                        cfg_obj.choice_fields.get("milestone", []))
    monkeypatch.setattr(db, "_SCHEMA", db._schema_sql())
    # exporter 模块级列缓存（COLS/HEADS 在 import 时冻结，一并刷新）
    monkeypatch.setattr(exporter, "COLS", cfg_obj.names)
    monkeypatch.setattr(
        exporter, "HEADS", [cfg_obj.labels[c] for c in cfg_obj.names])
    # importer 模块级缓存（DATE/INT/FLOAT/ALIASES 同样在 import 时冻结）
    monkeypatch.setattr(importer, "DATE_FIELDS", set(cfg_obj.date_fields))
    monkeypatch.setattr(importer, "INT_FIELDS", set(cfg_obj.int_fields))
    monkeypatch.setattr(importer, "FLOAT_FIELDS", set(cfg_obj.float_fields))
    monkeypatch.setattr(importer, "ALIASES", cfg_obj.header_map)
    # main 模块同样绑死了 CFG（from config import CFG）
    try:
        import main
        monkeypatch.setattr(main, "CFG", cfg_obj)
    except ImportError:
        pass


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """最小配置（favorites 关闭）。返回 Config 对象。"""
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(minimal_config_data(), ensure_ascii=False),
                 encoding="utf-8")
    c = config.Config(path=str(p))
    _patch_cfg(monkeypatch, c)
    return c


@pytest.fixture()
def cfg_fav(tmp_path, monkeypatch):
    """收藏夹开启的变体配置。"""
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(
        minimal_config_data(favorites={"enabled": True, "label": "收藏夹"}),
        ensure_ascii=False), encoding="utf-8")
    c = config.Config(path=str(p))
    _patch_cfg(monkeypatch, c)
    return c


@pytest.fixture()
def cfg_rec(tmp_path, monkeypatch):
    """回收站开启的变体配置。"""
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(
        minimal_config_data(recycle_bin={"enabled": True}),
        ensure_ascii=False), encoding="utf-8")
    c = config.Config(path=str(p))
    _patch_cfg(monkeypatch, c)
    return c


@pytest.fixture()
def cfg_rec_fav(tmp_path, monkeypatch):
    """回收站 + 收藏夹双开变体。"""
    p = tmp_path / "fields.json"
    p.write_text(json.dumps(minimal_config_data(
        recycle_bin={"enabled": True},
        favorites={"enabled": True, "label": "收藏夹"}),
        ensure_ascii=False), encoding="utf-8")
    c = config.Config(path=str(p))
    _patch_cfg(monkeypatch, c)
    return c


@pytest.fixture()
def dbs(cfg, tmp_path):
    """已建 schema 的空库（最小配置）。"""
    database = db.Database(str(tmp_path / "test.db"))
    yield database
    database.close()


@pytest.fixture()
def db_fav(cfg_fav, tmp_path):
    """收藏夹开启的空库。"""
    database = db.Database(str(tmp_path / "fav.db"))
    yield database
    database.close()


@pytest.fixture()
def db_rec(cfg_rec, tmp_path):
    """回收站开启的空库。"""
    database = db.Database(str(tmp_path / "rec.db"))
    yield database
    database.close()


@pytest.fixture()
def db_rec_fav(cfg_rec_fav, tmp_path):
    """回收站 + 收藏夹双开的空库。"""
    database = db.Database(str(tmp_path / "recfav.db"))
    yield database
    database.close()


@pytest.fixture()
def seeded(dbs):
    """造好 5 个项目的库，覆盖筛选/排序/搜索的各种类型。

    项目1 厂家A 客户X 产品P1 金额10.5 数量2 进行中 开始2026-01-05
    项目2 厂家B 客户Y 产品P2 金额9    数量10 进行中 开始2026-02-01
    项目3 厂家C 客户Z 产品P3 金额100  数量1  赢单   开始2026-01-20（closed）
    项目4 厂家a 客户X 产品P4 金额9    数量3  进行中 开始2026-03-15 备注含"急"
    项目5 厂家E 客户W 产品P5 金额7    数量7  输单   开始2026-01-31（closed）
    """
    dbs.create_project(manufacturer="厂家A", customer="客户X",
                       product="产品P1", amount=10.5, qty=2, note="常规",
                       status="进行中", start_date="2026-01-05")
    dbs.create_project(manufacturer="厂家B", customer="客户Y",
                       product="产品P2", amount=9, qty=10,
                       status="进行中", start_date="2026-02-01")
    dbs.create_project(manufacturer="厂家C", customer="客户Z",
                       product="产品P3", amount=100, qty=1,
                       status="赢单", start_date="2026-01-20")
    dbs.create_project(manufacturer="厂家a", customer="客户X",
                       product="产品P4", amount=9, qty=3, note="加急项目",
                       status="进行中", start_date="2026-03-15")
    dbs.create_project(manufacturer="厂家E", customer="客户W",
                       product="产品P5", amount=7, qty=7,
                       status="输单", start_date="2026-01-31")
    return dbs
