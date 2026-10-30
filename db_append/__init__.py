# -*- coding: utf-8 -*-
"""db_append：多库追加器（团队报数汇总）。

核心逻辑在 append_core.py（纯逻辑，CLI/GUI 共用）；
append_gui.py 是图形界面；命令行走 python -m db_append。
"""
from db_append.append_core import (  # noqa: F401
    list_projects, check_compatible, copy_projects, append_sources,
)
