# -*- coding: utf-8 -*-
"""export_all.py - 导出任务（workbench_ui export）。

按 runmyanalysis.py 里 EXPORTS 配置行逐行执行；每行 = 一张表，
文件名自动命名（嵌筛选摘要），同目录多行互不覆盖。
"""
from common import expand_where, mkdir, run, with_on


def run_exports(ctx):
    rows = with_on(ctx["exports"])
    if not rows:
        print("EXPORTS 没有开启的行，跳过导出。")
        return
    out = mkdir(ctx["out"], "exports")
    for r in rows:
        label = r.get("name") or "export"
        args = ["workbench_ui", "export", out]
        if r.get("template"):
            args += ["--template", r["template"]]
        for w in r.get("where", []):
            args += ["--where", expand_where(w)]
        if r.get("closed"):
            args.append("--closed")
        run(args, label=f"export:{label}")
