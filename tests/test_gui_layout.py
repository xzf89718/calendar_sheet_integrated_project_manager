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
