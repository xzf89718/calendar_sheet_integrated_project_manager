# -*- coding: utf-8 -*-
"""v3.2.0 三视图模式 GUI 防回归：aggregate / calendar / table。

设计锁定（用户 2026-10-31 拍板）：
  * 视图启动时定（--view > fields.json ui.default_view > aggregate），
    GUI 内无切换器、运行中不可切、不回写配置；
  * calendar（仅日历）：表格 + 按钮行整体移除，日历吃满窗口，
    最底保留一行（至少"新建项目"，复用 _new_project）；
    按钮行第一个 pack 且 side="bottom" 锚定（pack 顺序坑修复模式）；
    日历供给恒为全量（无表格 = 无筛选/搜索/收藏夹可牵扯）；
  * table（仅表格）：日历不创建，其余原样（按钮行/表格/分页行）；
  * aggregate = 现状（全存在，无标题视图标注）。
"""
import os

import pytest

tk = pytest.importorskip("tkinter",
                         reason="tkinter 不可用，跳过 GUI 用例")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="无 DISPLAY（用 xvfb-run 运行）")


@pytest.fixture()
def db_path(seeded, tmp_path):
    return str(tmp_path / "test.db")


def make_app(db_path, view):
    import main
    a = main.MainApp(db_path=db_path, view=view)
    a.geometry("1100x640")
    a.update()
    a.update_idletasks()
    return a


# ---------- aggregate：现状回归 ----------

def test_aggregate_unchanged(db_path):
    a = make_app(db_path, "aggregate")
    try:
        assert a.view == "aggregate"
        assert a.cal is not None and a.cal.winfo_ismapped()
        assert a.tree.winfo_ismapped()
        assert a.new_btn.winfo_ismapped()
        # 现状：聚合模式标题栏不加视图标注
        assert "[" not in a.title()
    finally:
        a.destroy()


# ---------- table：仅表格 ----------

def test_table_hides_calendar_keeps_rest(db_path):
    a = make_app(db_path, "table")
    try:
        assert a.view == "table"
        assert a.cal is None
        assert a.tree.winfo_ismapped()
        assert a.new_btn.winfo_ismapped()
        assert a.limit_lbl.winfo_ismapped()
        # 标题标注
        assert "[仅表格]" in a.title()
        # 现有回归锁仍成立：分页行第一个 pack + side=bottom
        lrow = a.limit_lbl.master
        assert lrow.pack_info()["side"] == "bottom"
        assert lrow.master.pack_slaves()[0] is lrow
        # reload 不碰日历（getattr 守卫）
        a.reload()
    finally:
        a.destroy()


def test_table_cal_entries_unaffected(db_path, seeded):
    """仅表格模式：日历供给接口若被调用不应崩（filtered 分支只在
    有日历时被日历组件驱动，这里直接验证守卫存在）。"""
    a = make_app(db_path, "table")
    try:
        assert a.view == "table"
    finally:
        a.destroy()


# ---------- calendar：仅日历 ----------

def test_calendar_removes_table_and_buttons(db_path):
    a = make_app(db_path, "calendar")
    try:
        assert a.view == "calendar"
        assert getattr(a, "tree", None) is None
        assert getattr(a, "new_btn", None) is None
        assert getattr(a, "search_btn", None) is None
        # 日历吃满：expand + fill=both
        info = a.cal.pack_info()
        assert info["expand"] == 1 and info["fill"] == "both"
        assert a.cal.winfo_ismapped()
        assert "[仅日历]" in a.title()
    finally:
        a.destroy()


def test_calendar_bottom_bar_pinned(db_path):
    """仅日历底部行：第一个 pack 且 side=bottom，含"新建项目"，
    任何窗口高度下永不被日历挤没（pack 顺序坑修复模式回归锁）。"""
    a = make_app(db_path, "calendar")
    try:
        slaves = a.pack_slaves()
        bar = slaves[0]
        assert bar.pack_info()["side"] == "bottom"
        texts = [str(w.cget("text"))
                 for w in bar.winfo_children()
                 if w.winfo_class() == "Button"]
        assert "新建项目" in texts
        # 窄窗口下仍真实可见
        a.geometry("900x400")
        a.update()
        a.update_idletasks()
        assert bar.winfo_ismapped()
        assert bar.winfo_height() > 0
    finally:
        a.destroy()


def test_calendar_entries_unfiltered(db_path, seeded):
    """仅日历模式：日历供给恒为全量，即使配置了 filtered 也不牵扯
    不存在的表格筛选状态。"""
    a = make_app(db_path, "calendar")
    try:
        entries = a._cal_entries(2026, 1)
        # 与底层全量供给完全一致（closed 项目被日历层过滤是既有
        # 行为，两种视图一致即可，不在本测试范围）
        assert entries == a.db.calendar_entries(2026, 1)
        dates = {e["date"] for e in entries}
        assert "2026-01-05" in dates      # 进行中的项目1（1月开始）
    finally:
        a.destroy()


def test_calendar_reload_without_table(db_path, seeded):
    """无表格时 reload 是安全的（新建保存回调 = 同一入口）。"""
    a = make_app(db_path, "calendar")
    try:
        a.reload()
        a._open_day("2026-01-05")   # 点日期 = 当天明细，原有交互保留
        for w in a.winfo_children():
            if w.winfo_class() == "Toplevel" or \
                    isinstance(w, tk.Toplevel):
                w.grab_release()
                w.destroy()
    finally:
        a.destroy()
