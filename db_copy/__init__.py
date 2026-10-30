# -*- coding: utf-8 -*-
"""db_copy：A/B 双库对照复制器。

核心逻辑在 copy_core.py（纯逻辑，CLI/GUI 共用）；
copy_gui.py 是图形界面；命令行走 python -m db_copy。
"""
from db_copy.copy_core import (  # noqa: F401
    list_projects, check_compatible, copy_projects,
)
