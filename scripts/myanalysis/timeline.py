# -*- coding: utf-8 -*-
"""timeline.py - 时间线任务（db_analysis timeline，HTML 整页，只读）。

按 TIMELINES 配置行逐行执行；接口全部开放到行上：
  where   筛选；日期值可用令牌 @today/@today-1m
  split   True = 按 逾期未跟进/待跟进/未排跟进/已关闭 分章
  sort    章内排序字段（库字段名或 diff=日差；缺省按 diff 升序）
  desc    True = 降序
  add     额外日期列，逐项 {"col": 字段, "plot": "line"/"spot",
          "color": "#RRGGBB"（可空走内置轮盘）}
"""
from common import expand_where, mkdir, run, with_on


def run_timelines(ctx):
    rows = with_on(ctx["timelines"])
    if not rows:
        print("TIMELINES 没有开启的行，跳过时间线。")
        return
    out = mkdir(ctx["out"], "timeline")
    for r in rows:
        label = r.get("name") or "timeline"
        args = ["db_analysis", "timeline"]
        for w in r.get("where", []):
            args += ["--where", expand_where(w)]
        if r.get("split"):
            args.append("--split")
        if r.get("sort"):
            args += ["--sort", r["sort"]]
        if r.get("desc"):
            args.append("--desc")
        for a in r.get("add", []):
            args += ["--add-col", a["col"]]
            if a.get("plot"):
                args += ["--add-plot", a["plot"]]
            if a.get("color"):
                args += ["--add-colors", a["color"]]
        args += ["--path", out]
        run(args, label=f"timeline:{label}")
