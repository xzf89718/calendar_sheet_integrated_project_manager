# -*- coding: utf-8 -*-
"""GUI 入口：python -m workbench_ui gui [--view ...] 等价于 main.py。

放在单独文件，使 `python -m workbench_ui`（CLI）完全不触碰 tkinter。
"""
import sys


def run_gui(argv=None):
    import main as _main_mod           # 延迟到调用时（tkinter 重）
    _main_mod.main(argv)


if __name__ == "__main__":
    run_gui(sys.argv[1:])
