#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""runmyanalysis.py - pm_workbench 本地一键分析

用法（项目根目录下）：
    python scripts/runmyanalysis.py

组织方式（v2，2026-11-12 用户重定）：不是"一个开关跑全部"，而是
四张任务清单——导出 / 周报 / 饼图 / 时间线，每行一个任务，
行首 "on": True/False 选用，删行也行。每行的参数就是对应 CLI
接口的开放，改行即调参。

实现拆在 scripts/myanalysis/ 包内（common / export_all / weekly /
pie / timeline），全部通过项目 CLI（python -m ...）调用，
不 import 项目内部实现。

日期小令牌（where / from / to 的值里可用）：
    @today        = 今天
    @today-30d    = 30 天前
    @today-1m     = 一个月前（日历月，同日；月底自动钳制）
例："start_date=@today-1m~@today" = 过去一个月内开始的项目。
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent          # scripts/
PKG = HERE / "myanalysis"                        # scripts/myanalysis/
sys.path.insert(0, str(PKG))

import common           # noqa: E402
import export_all       # noqa: E402
import pie              # noqa: E402
import timeline         # noqa: E402
import weekly           # noqa: E402

# ============================ 参数区（只改这里） ============================

# 输出文件夹（自动创建；内部分 exports/ weekly/ clean/ pie/ timeline/）
OUT_DIR = Path(r"D:\pm_analysis")

# ---- 任务清单 1：导出（每行 = 一张 xlsx，文件名自动命名互不覆盖）--------
# 模板名 = fields.json templates 里的 name；留空 = 缺省模板（全选）。
# where = 筛选，形如 "manufacturer=厂家A" / "status=跟进中"；
#       日期字段支持 起~止 区间，可用 @today 令牌。
# closed = True 含已归档项目（默认只看进行中）。
EXPORTS = [
    {"name": "厂家A全量", "template": "全选",
     "where": ["manufacturer=厂家A"], "closed": True},
    # 过去一个月新增（@today-1m 令牌，永久有效不用每月改）
    {"name": "厂家A近一月新增", "template": "全选",
     "where": ["manufacturer=厂家A", "start_date=@today-1m~@today"],
     "closed": True},
    {"name": "厂家A跟进中", "template": "全选",
     "where": ["manufacturer=厂家A", "status=跟进中"], "closed": False},
    {"name": "厂家AUnder Negotiation", "template": "全选",
     "where": ["manufacturer=厂家A", "milestone=Under negotiation"],
     "closed": False},
    {"name": "厂家A成单", "template": "全选",
     "where": ["manufacturer=厂家A", "status=成单"], "closed": True},
    {"name": "厂家A关闭", "template": "全选",
     "where": ["manufacturer=厂家A", "status=关闭"], "closed": True},
]

# ---- 任务清单 2：周报（date/plan 留 None = 本周一~日 / 下周一~日）------
# clean = True 导出后顺手出清洗版到 clean/。
WEEKLIES = [
    {"name": "本周周报", "date_from": None, "date_to": None,
     "plan_from": None, "plan_to": None, "clean": True},
]

# ---- 任务清单 3：饼图（db_analysis pie 接口全开放）----------------------
# fields = 字段英文 name 列表，可多个（一字段一 PNG）
# closed / date_field / last / from / to / top 与 CLI 一一对应；
# last("1m"/"6m"/"1y") 与 from/to 二选一；png/dump 控制产出。
PIES = [
    {"name": "状态分布", "fields": ["status"],
     "where": ["manufacturer=厂家A"], "closed": True,
     "date_field": None, "last": None, "from": None, "to": None,
     "top": 9, "png": True, "dump": True},
    {"name": "城市分布近一年", "fields": ["city"],
     "where": [], "closed": True,
     "date_field": None, "last": "1y", "from": None, "to": None,
     "top": 9, "png": True, "dump": True},
]

# ---- 任务清单 4：时间线（db_analysis timeline 接口全开放）---------------
# split = 分章（逾期未跟进/待跟进/未排跟进/已关闭）；
# sort = 章内排序（字段名或 diff=日差），desc = 降序；
# add = 追加日期列 [{"col": 字段, "plot": "line"/"spot", "color": "#RRGGBB"}]
TIMELINES = [
    {"name": "厂家A分章", "where": ["manufacturer=厂家A"],
     "split": True, "sort": None, "desc": False, "add": []},
    {"name": "全量按日差", "where": [],
     "split": False, "sort": "diff", "desc": True, "add": []},
]

# ===========================================================================


def _ctx():
    return {
        "out": Path(OUT_DIR).expanduser(),
        "exports": EXPORTS,
        "weeklies": WEEKLIES,
        "pies": PIES,
        "timelines": TIMELINES,
    }


def main():
    ctx = _ctx()
    ctx["out"].mkdir(parents=True, exist_ok=True)
    print(f"输出文件夹：{ctx['out']}")
    print(f"项目根：{common.BASE_DIR}")

    export_all.run_exports(ctx)
    weekly.run_weeklies(ctx)
    pie.run_pies(ctx)
    timeline.run_timelines(ctx)

    print("\n=== 完成，产出文件：")
    for p in sorted(ctx["out"].rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(ctx['out'])}")


if __name__ == "__main__":
    main()
