# -*- coding: utf-8 -*-
"""pie.py - 饼图任务（db_analysis pie，只读分析绝不写库）。

按 PIES 配置行逐行执行；db_analysis 的接口全部开放到行上：
  fields     字段名（英文 name，可多个，一字段一 PNG）
  where      筛选，形如 "city=某城市"；日期值可用令牌 @today/@today-1m
  closed     True = 含已归档项目
  date_field 日期区间作用列（缺省 snapshot_at，即按跟进日）
  last       快捷窗 "1m"/"6m"/"1y"（与 from/to 二选一）
  from / to  明确日期窗 YYYY-MM-DD
  top        段数上限，超出合并「其他」（缺省 9）
  png/dump   True = 出 PNG / 计数 CSV
matplotlib 缺失时自动降级为只出 CSV，不中断流水线。
"""
from common import expand_where, has_matplotlib, mkdir, run, with_on


def run_pies(ctx):
    rows = with_on(ctx["pies"])
    if not rows:
        print("PIES 没有开启的行，跳过饼图。")
        return
    out = mkdir(ctx["out"], "pie")
    no_mpl = not has_matplotlib()
    if no_mpl:
        print("（未安装 matplotlib，PNG 自动降级为只出计数 CSV；"
              "pip install matplotlib 后自动恢复）")
    for r in rows:
        label = r.get("name") or "pie"
        fields = [f for f in r.get("fields", []) if f]
        if not fields:
            print(f"[{label}] fields 为空，跳过本行。")
            continue
        args = ["db_analysis", "pie"]
        for f in fields:
            args += ["--field", f]
        for w in r.get("where", []):
            args += ["--where", expand_where(w)]
        if r.get("closed"):
            args.append("--closed")
        if r.get("date_field"):
            args += ["--date-field", r["date_field"]]
        if r.get("last"):
            args += ["--last", r["last"]]
        else:
            if r.get("from"):
                args += ["--from", r["from"]]
            if r.get("to"):
                args += ["--to", r["to"]]
        if r.get("top"):
            args += ["--top", str(r["top"])]
        if r.get("png", True) and not no_mpl:
            args += ["--png", out]
        if r.get("dump", True):
            args += ["--dump", out]
        run(args, label=f"pie:{label}")
