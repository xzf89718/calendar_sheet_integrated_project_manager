# -*- coding: utf-8 -*-
"""Sphinx configuration for the pm_workbench API reference.

Native reST docstrings only (no napoleon). Build with:
    sphinx-build -b html docs docs/build/html
"""
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "pm_workbench"
author = "xu-zifeng"
release = "3.14.2"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["build"]

html_theme = "sphinx_rtd_theme"
html_static_path = []

language = "zh_CN"

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
