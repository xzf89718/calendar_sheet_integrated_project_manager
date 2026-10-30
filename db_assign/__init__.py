# -*- coding: utf-8 -*-
"""db_assign：批量赋值器（全库统一给一列赋值，走快照可回溯）。

核心逻辑在 assign_core.py（纯逻辑，CLI/GUI 共用）；
assign_gui.py 是图形界面；命令行走 python -m db_assign。
"""
from db_assign.assign_core import (  # noqa: F401
    all_project_ids, assign_value,
)
