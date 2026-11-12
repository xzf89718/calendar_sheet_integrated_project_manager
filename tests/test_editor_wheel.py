# -*- coding: utf-8 -*-
"""v3.11.0 编辑器滚轮行为防回归：

1. 多行文本框上滚轮只滚框内，外层表单画布不跟着滚；
2. Combobox 滚轮不改条目（本体 + 弹出下拉都绑 break）。

历史背景：editor.py 曾用 canvas.bind_all("<MouseWheel>") 把滚轮
全局绑给外层画布，导致框内滚动时整个表单乱跑；Windows 下滚轮
划过下拉/下拉展开时滚轮会改条目。
"""
import os

import pytest

tk = pytest.importorskip("tkinter",
                         reason="tkinter 不可用，跳过 GUI 用例")
from tkinter import ttk  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="无 DISPLAY（用 xvfb-run 运行）")

import conftest  # noqa: E402


@pytest.fixture()
def cfg_multi(tmp_path, monkeypatch):
    """带一个多行文本字段（followup_note）的最小配置。"""
    import config
    data = conftest.minimal_config_data()
    for f in data["fields"]:
        if f["name"] == "followup_note":
            f["multiline"] = True
            f["height"] = 5
    p = tmp_path / "fields.json"
    p.write_text(__import__("json").dumps(data, ensure_ascii=False),
                 encoding="utf-8")
    c = config.Config(path=str(p))
    conftest._patch_cfg(monkeypatch, c)
    return c


@pytest.fixture()
def editor(cfg_multi, tmp_path):
    import editor as editor_mod
    from db import Database
    database = Database(str(tmp_path / "e.db"))
    root = tk.Tk()
    root.withdraw()
    ed = editor_mod.SnapshotEditor(root, database)
    ed.update()
    ed.update_idletasks()
    yield ed
    ed.destroy()
    root.destroy()
    database.close()


def _find_comboboxes(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, ttk.Combobox):
            out.append(c)
        out.extend(_find_comboboxes(c))
    return out


def test_text_wheel_scrolls_inside_not_canvas(editor):
    txt = editor.texts["followup_note"]
    txt.insert("1.0", "\n".join(f"line{i}" for i in range(60)))
    editor.update()
    canvas = editor.frm.master            # create_window 后 frm 的 master
    before_txt = txt.yview()
    before_canvas = canvas.yview()
    txt.event_generate("<MouseWheel>", delta=-120)
    editor.update()
    assert txt.yview() != before_txt, "框内应滚动"
    assert canvas.yview() == before_canvas, "外层画布不应滚动"


def test_text_wheel_over_own_scrollbar_also_inner(editor):
    txt = editor.texts["followup_note"]
    txt.insert("1.0", "\n".join(f"line{i}" for i in range(60)))
    editor.update()
    canvas = editor.frm.master
    sb = txt.master.winfo_children()[1]   # Frame(Text, Scrollbar) 的第二个
    before_canvas = canvas.yview()
    sb.event_generate("<MouseWheel>", delta=-120)
    editor.update()
    assert canvas.yview() == before_canvas, "滚专属滚动条也不应滚外层"


def test_combobox_wheel_does_not_change_value(editor):
    cbs = _find_comboboxes(editor.frm)
    assert cbs, "编辑器里应有下拉框"
    for cb in cbs:
        var = cb.cget("textvariable")
        val = editor.tk.globalgetvar(var)
        cb.event_generate("<MouseWheel>", delta=-120)
        cb.event_generate("<MouseWheel>", delta=120)
        editor.update()
        assert editor.tk.globalgetvar(var) == val, \
            "滚轮划过下拉不得改条目"


def test_combobox_popdown_guarded(editor):
    cb = _find_comboboxes(editor.frm)[0]
    # 模拟点按触发 post，idle 后弹出窗列表应已绑 break
    cb.event_generate("<ButtonPress-1>")
    editor.update()
    editor.update()
    pop = editor.tk.call("ttk::combobox::PopdownWindow", cb)
    assert editor.tk.call("bind", pop + ".f.l",
                          "<MouseWheel>") == "break", \
        "弹出下拉的滚轮应被吞掉"
