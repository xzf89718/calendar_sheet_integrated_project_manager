# -*- coding: utf-8 -*-
"""GUI 字体方案应用器（v3.15.0）：按 fields.json 的 ui.font 段配置字体。

设计原则：UI 参数一律由 JSON 配置（ui.font 段），本模块只做"读取
配置 -> 应用命名字体"，不含任何硬编码字号。主窗口 main.py 有自己的
_setup_fonts 消费同一配置；本模块供各工具包 GUI（db_* /
weekreport_clean）复用，保证全套窗口字号口径一致。

ui.font 段键（均可缺省，缺省值如下）：
  default      正文字号 pt（12）
  heading_size 表格表头字号 pt（13）
  tree_rowheight 表格行高 px（38）

用法：在 tk.Tk()（或 Tk 子类 super().__init__()）之后、创建业务
控件之前调用 apply(root)。幂等，重复调用安全。
"""
from tkinter import font as _tkfont
from tkinter import ttk as _ttk

from config import CFG

_FONT_NAMES = ("TkDefaultFont", "TkTextFont", "TkHeadingFont",
               "TkMenuFont", "TkFixedFont")


def apply(root):
    """把 fields.json ui.font 段应用到根窗口的全局命名字体与表格样式。

    只改字号/行高，不改字体族与字重；命名字体一旦配置，后创建的
    全部控件自动继承，无需逐个 widget 传 font 参数。

    :param root: 已创建的 Tk 根窗口。
    :type root: tkinter.Tk
    """
    size = CFG.font.get("default", 12)
    for name in _FONT_NAMES:
        try:
            _tkfont.nametofont(name).configure(size=size)
        except (KeyError, RuntimeError):
            pass                          # 字体未实例化：跳过
    style = _ttk.Style(root)
    style.configure("Treeview",
                    rowheight=CFG.font.get("tree_rowheight", 38))
    style.configure("Treeview.Heading",
                    font=("", CFG.font.get("heading_size", 13), "bold"))
