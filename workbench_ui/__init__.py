# -*- coding: utf-8 -*-
"""workbench_ui：主窗口全部 GUI 功能的命令行/图形双入口（v3.3.0）。

  python -m workbench_ui <子命令>   命令行（见 __main__.py 顶部文档）
  python -m workbench_ui gui        图形界面（等价于 main.py）

纯逻辑在 bench_core（不 import tkinter），__main__ 只做参数解析与打印。
"""
from workbench_ui import bench_core  # noqa: F401
