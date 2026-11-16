# -*- coding: utf-8 -*-
"""GUI 入口：python -m workbench_ui gui [--view ...] 等价于 main.py。

放在单独文件，使 `python -m workbench_ui`（CLI）完全不触碰 tkinter。
"""
import sys


def run_gui(argv=None):
    """GUI 入口：等价于直接运行 main.py。

    import main 延迟到调用时，保证 `python -m workbench_ui`（CLI）不
    触碰 tkinter。

    :param argv: 透传给 main.main 的参数列表（去掉了 "gui" 本身）。
    :type argv: list 或 None
    """
    import main as _main_mod           # 延迟到调用时（tkinter 重）
    _main_mod.main(argv)


if __name__ == "__main__":
    run_gui(sys.argv[1:])
