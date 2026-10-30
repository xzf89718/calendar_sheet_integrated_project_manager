# -*- coding: utf-8 -*-
"""L3 端到端冒烟（发布前人工跑一遍，不入 pytest）。

用法（沙箱/CI）：
    xvfb-run -a -s "-screen 0 1280x800x24" python tests/smoke.py
Windows 直接：
    python tests/smoke.py

做一遍"用户一天的动线"：启动 -> 翻页 -> 搜索 -> 收藏夹模式 ->
导出 Excel -> 截图存档。任何一步抛异常即失败退出（exit=1）。
截图存到系统临时目录，供人工目检（不做自动像素断言）。
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from conftest import minimal_config_data, _patch_cfg  # noqa: E402


class _NoMonkeyPatch:
    """smoke 不在 pytest 里，给 _patch_cfg 一个可用的最小 setattr。"""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="smoke_"))
    (tmp / "fields.json").write_text(
        __import__("json").dumps(
            minimal_config_data(favorites={"enabled": True,
                                           "label": "收藏夹"}),
            ensure_ascii=False),
        encoding="utf-8")
    cfg = config.Config(path=str(tmp / "fields.json"))
    import db
    import main
    _patch_cfg(_NoMonkeyPatch(), cfg)

    db_path = str(tmp / "smoke.db")
    d = db.Database(db_path)
    for i in range(100):
        d.create_project(manufacturer=f"厂家{i % 10}",
                         customer=f"客户{i}", product="产品",
                         amount=float(i), status="进行中",
                         start_date="2026-03-01")
    d.close()
    print(f"[1/6] 造数完成：100 个项目 -> {db_path}")

    app = main.MainApp(db_path=db_path)
    app.geometry("1280x720")
    # update()（不是 update_idletasks）才会处理窗口映射事件：
    # Linux/X11 下 toplevel 自动 map，Windows 下必须跑过事件循环，
    # 之后 winfo_ismapped() 的断言才成立
    app.update()
    app.update_idletasks()
    assert app.limit_lbl.winfo_ismapped(), "底部分页行不可见"
    print("[2/6] 启动完成：底部分页行可见")

    for _ in range(3):                    # 翻两页再翻回
        app._load_more()
        app.update_idletasks()
    for _ in range(3):
        app._load_prev()
        app.update_idletasks()
    print(f"[3/6] 翻页完成：{app.limit_lbl.cget('text')}")

    app.search_var.set("客户7")
    app._do_search()                      # 无 mainloop，直接同步触发防抖回调
    app.update_idletasks()
    n_search = app.limit_lbl.cget("text")
    assert "11" in n_search, f"搜索未生效:{n_search}"   # 客户7/17/…/97
    print(f"[4/6] 搜索完成：{n_search}")
    app.search_var.set("")
    app.update()

    cid = app.db.create_collection("冒烟夹")
    ids = app.db.query_project_ids()[:5]
    app.db.collection_add(cid, ids)
    app._enter_favorites(cid, "冒烟夹")
    app.update()
    app.update_idletasks()
    assert app.fav_banner.winfo_ismapped(), "收藏夹横幅不可见"
    rows, total = app.db.query_projects(filters={"id": set(ids)})
    assert total == 5
    app._exit_favorites()
    print("[5/6] 收藏夹模式完成")

    out = tmp / "export.xlsx"
    rows, _t = app.db.query_projects(include_closed=True)
    from exporter import export_excel
    assert export_excel(rows, str(out)) == 100
    print(f"[6/6] 导出完成：{out}")

    shot = tmp / "smoke.png"
    if os.environ.get("DISPLAY") and \
            subprocess.run(["which", "import"],
                           capture_output=True).returncode == 0:
        subprocess.run(["import", "-window", "root", str(shot)],
                       capture_output=True, timeout=30)
        print(f"      截图存档：{shot}")
    app.destroy()
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
