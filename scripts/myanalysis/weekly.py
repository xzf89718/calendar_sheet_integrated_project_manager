# -*- coding: utf-8 -*-
"""weekly.py - 周报导出 + 周报清洗任务（workbench_ui weekly /
weekreport_clean clean）。

按 WEEKLIES 配置行逐行执行；clean=True 时对该行刚导出的最新周报
xlsx 顺手跑清洗，结果在 <OUT_DIR>/clean/<原名>_cleaned.xlsx。
清洗对"无历史变动"的库会以退出码 1 拒绝写出——那是数据状态不是
脚本错误，本步永不中止流水线。
"""
from pathlib import Path

from common import mkdir, run, with_on


def run_weeklies(ctx):
    rows = with_on(ctx["weeklies"])
    if not rows:
        print("WEEKLIES 没有开启的行，跳过周报。")
        return
    for r in rows:
        label = r.get("name") or "weekly"
        out = mkdir(ctx["out"], "weekly")
        args = ["workbench_ui", "weekly", out]
        for flag, key in (("--date-from", "date_from"),
                          ("--date-to", "date_to"),
                          ("--plan-from", "plan_from"),
                          ("--plan-to", "plan_to")):
            if r.get(key):
                args += [flag, r[key]]
        run(args, label=f"weekly:{label}")

        if not r.get("clean"):
            continue
        srcs = sorted(out.glob("*.xlsx"), key=lambda p: p.stat().st_mtime)
        if not srcs:
            print("weekly/ 里没有 xlsx，跳过清洗。")
            continue
        src = srcs[-1]
        dst_dir = mkdir(ctx["out"], "clean")
        run(["weekreport_clean", "clean", src, "-o",
             dst_dir / f"{Path(src).stem}_cleaned.xlsx"],
            label=f"clean:{label}", check=False)
