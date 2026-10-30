# -*- coding: utf-8 -*-
"""db_split：按键分拆器（团队轮转的分发环节）。

核心逻辑在 split_core.py（纯逻辑，CLI/GUI 共用）；
split_gui.py 是图形界面；命令行走 python -m db_split。
"""
from db_split.split_core import (  # noqa: F401
    list_keys, preview, build_filename, split_by_key,
)
