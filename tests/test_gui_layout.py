# -*- coding: utf-8 -*-
"""L2 GUI 布局防回归：把两次历史 pack 顺序 BUG 变成永久测试。

运行前提：需要 DISPLAY（xvfb-run）；断言一律用 winfo/pack 几何，
不做像素对比。历史 BUG 备忘：
  v2.7.2  收藏夹横幅必须钉在分页行"共 N 条"左边（before= 钉位）
  v2.7.3  分页行 lrow 必须第一个 pack + side="bottom"，否则小窗口被吞
  v2.7.3  reader 历史横幅是 root 直接子部件，before=left_wrap 钉顶
"""
import os

import pytest

tk = pytest.importorskip("tkinter",
                         reason="tkinter 不可用，跳过 GUI 用例")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="无 DISPLAY（用 xvfb-run 运行）")


@pytest.fixture()
def app(seeded, tmp_path):
    import main
    a = main.MainApp(db_path=str(tmp_path / "test.db"))
    a.geometry("1100x640")            # 交接文档实测尺寸，900x520 布局退化
    # update() 才处理窗口映射（Windows 必需；X11 自动 map 的隐式
    # 依赖曾导致 L2 在 Windows 上报"底部分页行不可见"）
    a.update()
    a.update_idletasks()
    yield a
    a.destroy()


@pytest.fixture()
def app_fav(cfg_fav, tmp_path):
    """收藏夹开启的主窗口 + 两个项目。"""
    import main
    from db import Database
    db = Database(str(tmp_path / "fav.db"))
    db.create_project(manufacturer="甲", status="进行中")
    db.create_project(manufacturer="乙", status="进行中")
    db.close()
    a = main.MainApp(db_path=str(tmp_path / "fav.db"))
    a.geometry("1100x640")
    a.update()
    a.update_idletasks()
    yield a
    a.destroy()


# ---------- v2.7.3：底部分页行（lrow）第一个 pack + side=bottom ----------

def test_lrow_packed_first_and_bottom(app):
    lrow = app.limit_lbl.master
    assert lrow.pack_info()["side"] == "bottom"
    # pack_slaves() 顺序 = 打包顺序：lrow 必须排第一（先于 area/tree），
    # 否则 expand 的表格会把它挤没 —— v2.7.3 修复的回归锁
    assert lrow.master.pack_slaves()[0] is lrow


def test_bottom_row_visible_at_1100x640(app):
    # 非最大化、交接文档实测尺寸下，"共 N 条"必须真实可见
    assert app.limit_lbl.winfo_ismapped()
    assert app.limit_lbl.winfo_height() > 0


# ---------- v2.7.2：收藏夹横幅钉在"共 N 条"左边 ----------

def test_fav_mode_banner_pinned(app_fav):
    a = app_fav
    cid = a.db.create_collection("重点")
    ids = a.db.query_project_ids()
    # 先查项目 id 再加进夹（顺序反了会加空集，空夹会弹 messagebox 阻塞）
    a.db.collection_add(cid, ids)
    assert a.db.collection_projects(cid) == ids
    a._enter_favorites(cid, "重点")
    a.update()                           # pack + 映射都刷新后再断言
    a.update_idletasks()
    try:
        assert a.fav_ids == set(ids)
        assert a.fav_coll == (cid, "重点")
        assert a.fav_banner.winfo_manager() == "pack"
        # 钉位：横幅排在 limit_lbl 之前（before=limit_lbl 的回归锁）
        order = a.fav_banner.master.pack_slaves()
        assert order.index(a.fav_banner) < order.index(a.limit_lbl)
        # 模式横幅随分页行可见（v2.7.3 小窗口不被吞的组合验证）
        assert a.fav_banner.winfo_ismapped()
        assert a.fav_remove_btn.cget("state") == "normal"
    finally:
        a._exit_favorites()
    assert a.fav_banner.winfo_manager() == ""
    assert a.fav_ids is None


def test_fav_empty_collection_does_not_enter(app_fav, monkeypatch):
    a = app_fav
    calls = []
    # 无 WM 环境下 messagebox 会永久阻塞，必须打桩（只记录不弹窗）
    monkeypatch.setattr(
        __import__("main").messagebox, "showinfo",
        lambda *ar, **kw: calls.append(ar))
    cid = a.db.create_collection("空夹")
    a._enter_favorites(cid, "空夹")
    assert a.fav_ids is None and len(calls) == 1


# ---------- v3.3.3：收藏夹面板"打开"按钮（无障碍，照顾无法双击的用户） ----------

def test_fav_dialog_has_open_button(app_fav):
    """打开按钮 = 双击夹名的等价路径：存在、可点、回调进入筛选。"""
    from main import FavoritesDialog
    a = app_fav
    entered = []
    dlg = FavoritesDialog(a, a.db,
                          on_enter=lambda cid, name: entered.append((cid, name)),
                          on_changed=lambda: None)
    try:
        a.update()
        # 按钮嵌在 btns Frame 里，递归收集全部后代 Button
        stack, btns = list(dlg.winfo_children()), []
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if w.winfo_class() == "Button":
                btns.append(w)
        texts = [str(b.cget("text")) for b in btns]
        assert "打开" in texts
        cid = a.db.create_collection("重点")
        a.db.collection_add(cid, a.db.query_project_ids())
        dlg._reload(keep_cid=cid)
        dlg._enter()          # 与"打开"按钮 command 同一入口
        assert entered == [(cid, "重点")]
    finally:
        dlg._on_close()


# ---------- v3.3.5：收藏夹模式下 导入/导出 置灰（纯索引视图语义） ----------

def test_fav_mode_greys_import_export(app_fav):
    a = app_fav
    cid = a.db.create_collection("重点")
    a.db.collection_add(cid, a.db.query_project_ids())
    a._enter_favorites(cid, "重点")
    a.update()
    try:
        assert a.import_btn.cget("state") == "disabled"
        assert a.export_btn.cget("state") == "disabled"
    finally:
        a._exit_favorites()
    a.update()
    assert a.import_btn.cget("state") == "normal"
    assert a.export_btn.cget("state") == "normal"


def test_fav_exit_keeps_weekly_grey(app_fav):
    """周报+收藏夹叠加：退出收藏夹后仍在周报模式，导入导出保持置灰。"""
    a = app_fav
    a._toggle_mode()                       # 进入周报模式
    cid = a.db.create_collection("重点")
    a.db.collection_add(cid, a.db.query_project_ids())
    a._enter_favorites(cid, "重点")
    a._exit_favorites()
    a.update()
    assert a.import_btn.cget("state") == "disabled"
    assert a.export_btn.cget("state") == "disabled"


# ---------- reader：历史横幅钉在内容区最上方 ----------

def test_reader_banner_pinned_to_top(app):
    from reader import ProjectReader
    pid = app.db.create_project(manufacturer="甲", status="进行中")
    app.db.add_snapshot(pid, manufacturer="甲", status="进行中",
                        note="第二次")
    r = ProjectReader(app, app.db, pid)
    try:
        assert r.banner.winfo_manager() == ""     # 初始隐藏
        r.listbox.selection_set(0)                # 选最早一条历史
        r._view_selected()
        assert r.viewing_hist is True
        assert r.banner.winfo_manager() == "pack"
        # 横幅是 root 的直接子部件，且钉在 left_wrap 之前（v2.7.3）
        assert r.banner.master is r.left_wrap.master
        order = r.banner.master.pack_slaves()
        assert order.index(r.banner) < order.index(r.left_wrap)
        r._show_latest()
        assert r.banner.winfo_manager() == ""
    finally:
        r.grab_release()
        r.destroy()


def _export_with_dir(app, monkeypatch, tmp_path):
    """v3.9.1：GUI 导出 = 选输出文件夹（askdirectory），格式只按
    ui.io.export_format 配置来，不回写。"""
    import main
    monkeypatch.setattr(main.filedialog, "askdirectory",
                        lambda **kw: str(tmp_path))
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(app, "_pick_template",
                        lambda *_a, **_k: {"name": "全选", "columns": [
                            ("客户", "customer", None)]})
    app._export()


def test_gui_export_csv_per_config(app, tmp_path, monkeypatch):
    """ui.io.export_format=csv → GUI 导出 csv（utf-8-sig），自动命名。"""
    import main
    main.CFG.io_ui["export_format"] = "csv"
    try:
        _export_with_dir(app, monkeypatch, tmp_path)
    finally:
        main.CFG.io_ui.pop("export_format", None)
    outs = list(tmp_path.glob("*.csv"))
    assert len(outs) == 1
    assert outs[0].name.startswith("export_全选_")   # 自动命名含模板名
    data = outs[0].read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert "客户X".encode("utf-8") in data   # seeded 项目1 的客户


def test_gui_export_default_excel(app, tmp_path, monkeypatch):
    """ui.io 缺省 → GUI 导出 xlsx。"""
    _export_with_dir(app, monkeypatch, tmp_path)
    outs = list(tmp_path.glob("*.xlsx"))
    assert len(outs) == 1


def test_gui_export_no_writeback(app, tmp_path, monkeypatch):
    """v3.9.1（用户定）：GUI 导出不回写 fields.json——配置内存态不变，
    且 main 模块里不存在 save_ui_io（回写机制已整体移除）。"""
    import config
    import main
    before = main.CFG.io_ui.copy()
    _export_with_dir(app, monkeypatch, tmp_path)
    assert main.CFG.io_ui == before
    assert not hasattr(config, "save_ui_io")


def test_gui_export_rejects_file_path(app, tmp_path, monkeypatch):
    """GUI 导出目录传带扩展名的路径 → 拒绝并弹错误框。"""
    import main
    bad = str(tmp_path / "out.xlsx")
    monkeypatch.setattr(main.filedialog, "askdirectory",
                        lambda **kw: bad)
    errors = []
    monkeypatch.setattr(main.messagebox, "showerror",
                        lambda *a, **k: errors.append(a))
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(app, "_pick_template",
                        lambda *_a, **_k: {"name": "全选", "columns": [
                            ("客户", "customer", None)]})
    app._export()
    assert errors, "应弹导出失败错误框"
    assert "只支持目录" in errors[0][1]


def test_import_export_button_labels(app):
    """v3.4.0：按钮文案「导入 / 导出」——csv 落地后不再带 Excel 后缀。"""
    assert app.import_btn.cget("text") == "导入"
    assert app.export_btn.cget("text") == "导出"


# ---- v3.4.2：日历每日条数分视图（max_per_day 接通渲染）----

def _cell_for(app, day):
    """日历组件里渲染了 day 号的格子（首个匹配）。"""
    for cell in app.cal._cells:
        for w in cell.winfo_children():
            if w.winfo_class() == "Label" and w.cget("text") == str(day):
                return cell
    raise AssertionError(f"no calendar cell for day {day}")


def _cell_buttons(cell):
    return [w for w in cell.winfo_children() if w.winfo_class() == "Button"]


def _seed_same_day(db, n, day="2026-06-15"):
    """n 个项目同一天开始，造同日多条目。"""
    for i in range(n):
        pid = db.create_project(manufacturer=f"厂{i}", status="进行中")
        db.add_snapshot(pid, start_date=day)


def test_calendar_limit_aggregate_stays_one(app):
    """聚合视图回归：每日仍只渲染 1 条 + 还有N条链接（v3.4.2 行为不变）。"""
    _seed_same_day(app.db, 3)
    app.cal.year, app.cal.month = 2026, 6
    app.cal.refresh()
    btns = _cell_buttons(_cell_for(app, 15))
    assert len(btns) == 2                 # 1 条目 + 1 "还有2条"
    assert any("还有2条" in b.cget("text") for b in btns)


def test_calendar_view_shows_all_five(tmp_path):
    """纯日历视图：每日最多渲染 5 条（max_per_day_view 缺省 = 5）。"""
    import main
    from db import Database
    db = Database(str(tmp_path / "cal5.db"))
    _seed_same_day(db, 5)
    db.close()
    a = main.MainApp(db_path=str(tmp_path / "cal5.db"), view="calendar")
    try:
        a.update()
        a.cal.year, a.cal.month = 2026, 6
        a.cal.refresh()
        btns = _cell_buttons(_cell_for(a, 15))
        assert len(btns) == 5               # 5 条全渲染，无"还有N条"
        assert not any("还有" in b.cget("text") for b in btns)
    finally:
        a.destroy()


def test_calendar_view_caps_at_five(tmp_path):
    """纯日历视图：同日 7 条只渲染 5 条 + 还有2条（封顶生效）。"""
    import main
    from db import Database
    db = Database(str(tmp_path / "cap.db"))
    _seed_same_day(db, 7)
    db.close()
    a = main.MainApp(db_path=str(tmp_path / "cap.db"), view="calendar")
    try:
        a.update()
        a.cal.year, a.cal.month = 2026, 6
        a.cal.refresh()
        btns = _cell_buttons(_cell_for(a, 15))
        assert len(btns) == 6               # 5 条目 + 1 "还有2条"
        assert any("还有2条" in b.cget("text") for b in btns)
    finally:
        a.destroy()


def test_calendar_view_limit_configurable(tmp_path, monkeypatch):
    """fields.json 配 max_per_day_view=3：纯日历只渲染 3 条（可配置验证）。"""
    import json
    import config as config_mod
    import main
    from conftest import minimal_config_data, _patch_cfg
    p = tmp_path / "fields.json"
    data = minimal_config_data()
    data.setdefault("ui", {})["calendar"] = {"max_per_day": 1,
                                             "max_per_day_view": 3}
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    _patch_cfg(monkeypatch, config_mod.Config(path=str(p)))
    from db import Database
    db = Database(str(tmp_path / "cfg.db"))
    _seed_same_day(db, 5)
    db.close()
    a = main.MainApp(db_path=str(tmp_path / "cfg.db"), view="calendar")
    try:
        a.update()
        a.cal.year, a.cal.month = 2026, 6
        a.cal.refresh()
        btns = _cell_buttons(_cell_for(a, 15))
        assert len(btns) == 4               # 3 条目 + 1 "还有2条"
        assert any("还有2条" in b.cget("text") for b in btns)
    finally:
        a.destroy()
