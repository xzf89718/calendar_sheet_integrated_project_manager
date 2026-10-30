# -*- coding: utf-8 -*-
"""fields.json 配置校验器回归：validate_config_data 的错误逐条语义。

每个用例 = 一类坏配置 -> 期望的错误消息。校验器是纯函数，
不读文件不抛异常，这里直接喂 dict。
"""
import pytest

from config import validate_config_data
from conftest import minimal_config_data


def _base():
    return minimal_config_data()


def test_valid_minimal_passes():
    assert validate_config_data(_base()) == []


def test_root_not_dict():
    assert validate_config_data([1, 2]) != []


def test_fields_missing():
    d = _base()
    del d["fields"]
    errs = validate_config_data(d)
    assert any("fields" in e for e in errs)


def test_fields_empty():
    d = _base()
    d["fields"] = []
    assert any("fields" in e for e in validate_config_data(d))


def test_field_missing_name():
    d = _base()
    d["fields"][0] = {"label": "无名", "type": "text"}
    assert any("缺少 name" in e for e in validate_config_data(d))


def test_field_duplicate_name():
    d = _base()
    d["fields"][1] = dict(d["fields"][0])
    assert any("重复" in e for e in validate_config_data(d))


def test_field_bad_type():
    d = _base()
    d["fields"][0]["type"] = "richtext"
    assert any("type 无效" in e for e in validate_config_data(d))


def test_status_required():
    d = _base()
    d["fields"] = [f for f in d["fields"] if f["name"] != "status"]
    assert any("type=status" in e for e in validate_config_data(d))


def test_status_unique():
    d = _base()
    d["fields"].append({"name": "status2", "label": "状态2",
                        "type": "status", "choices": ["a"]})
    assert any("只能有一个" in e for e in validate_config_data(d))


def test_status_closed_section_required():
    d = _base()
    del d["status_closed"]
    assert any("status_closed" in e for e in validate_config_data(d))


def test_status_closed_must_be_list():
    d = _base()
    d["status_closed"] = "赢单"
    assert any("status_closed" in e for e in validate_config_data(d))


def test_status_closed_empty_list_ok():
    d = _base()
    d["status_closed"] = []
    assert validate_config_data(d) == []


def test_calendar_dates_missing():
    d = _base()
    del d["calendar_dates"]
    assert any("calendar_dates" in e for e in validate_config_data(d))


def test_calendar_dates_empty():
    d = _base()
    d["calendar_dates"] = []
    assert any("calendar_dates" in e for e in validate_config_data(d))


def test_calendar_core_key_required():
    d = _base()
    d["calendar_dates"] = [e for e in d["calendar_dates"]
                           if e["key"] != "followup"]
    assert any("followup" in e for e in validate_config_data(d))


def test_calendar_key_duplicate():
    d = _base()
    d["calendar_dates"].append(dict(d["calendar_dates"][0]))
    assert any("key 重复" in e for e in validate_config_data(d))


def test_calendar_core_missing_field():
    d = _base()
    d["calendar_dates"][0].pop("field")
    assert any("必须绑定日期字段" in e for e in validate_config_data(d))


def test_calendar_core_unknown_field():
    d = _base()
    d["calendar_dates"][0]["field"] = "ghost"
    assert any("不存在的字段" in e for e in validate_config_data(d))


def test_calendar_core_non_date_field():
    d = _base()
    d["calendar_dates"][0]["field"] = "note"       # text 类型
    assert any("必须是 date 类型" in e
               for e in validate_config_data(d))


def test_calendar_append_must_not_bind_field():
    d = _base()
    d["calendar_dates"][3]["field"] = "note"
    assert any("append" in e for e in validate_config_data(d))


def test_calendar_custom_without_field():
    d = _base()
    d["calendar_dates"].append({"key": "ship", "label": "发货"})
    assert any("必须绑定日期字段" in e for e in validate_config_data(d))


def test_calendar_custom_occupied_field():
    d = _base()
    d["calendar_dates"].append({"key": "ship", "label": "发货",
                                "field": "start_date"})
    assert any("已被法定类别占用" in e for e in validate_config_data(d))


def test_date_check_unknown_field():
    d = _base()
    d["date_check"] = {"enabled": True, "fields": ["ghost"]}
    assert any("不存在的字段" in e for e in validate_config_data(d))


def test_date_check_non_date_field():
    d = _base()
    d["date_check"] = {"enabled": True, "fields": ["note"]}
    assert any("必须是 date 类型" in e for e in validate_config_data(d))


def test_date_check_not_object():
    d = _base()
    d["date_check"] = ["start_date"]
    assert any("date_check 必须是对象" in e for e in validate_config_data(d))


def test_favorites_enabled_not_bool():
    d = _base()
    d["favorites"] = {"enabled": "yes", "label": "收藏夹"}
    assert any("true/false" in e for e in validate_config_data(d))


def test_favorites_label_empty():
    d = _base()
    d["favorites"] = {"enabled": True, "label": "  "}
    assert any("label" in e for e in validate_config_data(d))


def test_favorites_not_object():
    d = _base()
    d["favorites"] = ["enabled"]
    assert any("favorites 必须是对象" in e for e in validate_config_data(d))


def test_weekly_template_columns_nonempty():
    d = _base()
    d["templates"] = [{"name": "周报", "kind": "weekly", "columns": []}]
    assert any("columns 不能为空" in e for e in validate_config_data(d))


def test_legacy_calendar_marker_passes():
    # 旧式配置（fields 里标 calendar 标记、无 calendar_dates 段）不拦
    d = _base()
    del d["calendar_dates"]
    for f in d["fields"]:
        f.pop("calendar", None)
    d["fields"][5]["calendar"] = "start"           # start_date
    assert validate_config_data(d) == []


# ---------- Config 类装载行为 ----------

def test_config_display_unknown_field_raises(tmp_path):
    d = _base()
    d["display_mainsheet"] = [{"name": "ghost", "on": True}]
    p = tmp_path / "fields.json"
    import json
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    from config import Config
    with pytest.raises(ValueError, match="不存在的字段名"):
        Config(path=str(p))


def test_config_defaults_and_derived(cfg):
    assert cfg.field_defaults["start_date"] == "2026-01-01"
    assert cfg.name_fields == ["manufacturer", "customer", "product"]
    assert cfg.status_field == "status"
    assert cfg.calendar_mode == "all"
    assert cfg.render_limit == 600
    assert cfg.default_sort == {"column": "id", "desc": True}
