# -*- coding: utf-8 -*-
"""回收站子模块（v3.1.0）。

核心逻辑在 recycled_core.py（纯逻辑，CLI/GUI 共用）；
recycled_gui.py 是图形界面；命令行走 python -m db_recycled。
"""
from db_recycled.recycled_core import (  # noqa: F401
    list_recycled, snapshots_of, restore_project,
    purge_project, empty_recycle,
)
