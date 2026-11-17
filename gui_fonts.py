# -*- coding: utf-8 -*-
"""GUI 字体方案应用器（v3.15.1）：每个程序独立的 ui.<程序名> 配置。

设计原则：各程序 UI 完全独立配置——主窗口用 ui 段下原有的
window/font/columns 等键（main.py 的 _setup_fonts 消费，不动）；
本模块供各工具包 GUI 读各自独立的 ui.<程序名> 段，互不影响：

  ui.db_append.font    多库追加器
  ui.db_assign.font    批量赋值器
  ui.db_copy.font      项目库复制器
  ui.db_recycled.font  回收站
  ui.db_split.font     按键分拆器
  ui.weekreport_clean.font  周报清洗器

每个程序段下两个子段，全部可缺省：

  font 子段（缺省 12 / 13 / 38 / normal）：
    default        正文字号 pt
    heading_size   表格表头字号 pt
    tree_rowheight 表格行高 px
    weight         正文字粗 normal / bold（bold 更适合大屏远观）

  window 子段（缺省 = 代码传入的默认值，各工具不同）：
    width / height        初始窗口尺寸 px
    min_width / min_height 最小窗口尺寸 px（仅需要的程序）

用法：tk.Tk()（或 Tk 子类 super().__init__()）之后、创建业务控件
之前调用 apply(root, "db_copy")（第二个参数 = ui 段键名）配字体，
apply_window(root, "db_copy", 1520, 780) 配窗口。均幂等。

配置整体缺省 = 用缺省值，JSON 无需预先加段；段不存在或键缺失都不报错。
值非法（非正整数）自动回落缺省值，不抛异常。

用法：tk.Tk()（或 Tk 子类 super().__init__()）之后、创建业务控件
之前调用 apply(root, "db_copy")（第二个参数 = ui 段键名）。幂等。
"""
from tkinter import font as _tkfont
from tkinter import ttk as _ttk

from config import CFG

_FONT_NAMES = ("TkDefaultFont", "TkTextFont", "TkHeadingFont",
               "TkMenuFont", "TkFixedFont")


def _pos_int(v, fallback):
    """配置值 -> 正整数，非法时回落缺省值。

    :param v: 配置值（任意类型）。
    :param fallback: 缺省正整数。
    :return: v 的正整数形式或 fallback。
    :rtype: int
    """
    try:
        n = int(v)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def apply(root, name):
    """把 fields.json 的 ui.<name>.font 段应用到根窗口字体与表格样式。

    只改字号/行高，不改字体族与字重；命名字体一旦配置，后创建的全部
    控件自动继承，无需逐个 widget 传 font 参数。段或键缺失时取缺省值，
    各工具包之间完全独立（没有共享回退）。

    :param root: 已创建的 Tk 根窗口。
    :type root: tkinter.Tk
    :param name: ui 段下的程序配置键名（如 "db_copy"）。
    :type name: str
    """
    ui = CFG.ui if isinstance(CFG.ui, dict) else {}
    sec = ui.get(name, {})
    f = sec.get("font", {}) if isinstance(sec, dict) else {}
    size = _pos_int(f.get("default"), 12)
    weight = f.get("weight", "normal")
    if weight not in ("normal", "bold"):
        weight = "normal"
    for fname in _FONT_NAMES:
        try:
            _tkfont.nametofont(fname).configure(size=size, weight=weight)
        except (KeyError, RuntimeError):
            pass                          # 字体未实例化：跳过
    style = _ttk.Style(root)
    style.configure("Treeview",
                    rowheight=_pos_int(f.get("tree_rowheight"), 38))
    style.configure("Treeview.Heading",
                    font=("", _pos_int(f.get("heading_size"), 13), "bold"))


def apply_window(root, name, default_w, default_h,
                 default_min_w=None, default_min_h=None):
    """按 ui.<name>.window 段设置初始/最小窗口尺寸。

    配置缺失时回落到传入的默认值（各程序自己的出厂尺寸）；只设置
    width/height 与 min_width/min_height 四个键，不写死任何尺寸。

    :param root: 已创建的 Tk 根窗口。
    :type root: tkinter.Tk
    :param name: ui 段下的程序配置键名（如 "db_copy"）。
    :type name: str
    :param default_w: 配置缺失时的初始宽度 px。
    :type default_w: int
    :param default_h: 配置缺失时的初始高度 px。
    :type default_h: int
    :param default_min_w: 配置缺失时的最小宽度 px；None = 不设最小宽。
    :type default_min_w: int 或 None
    :param default_min_h: 配置缺失时的最小高度 px；None = 不设最小高。
    :type default_min_h: int 或 None
    """
    ui = CFG.ui if isinstance(CFG.ui, dict) else {}
    sec = ui.get(name, {})
    w = sec.get("window", {}) if isinstance(sec, dict) else {}
    width = _pos_int(w.get("width"), default_w)
    height = _pos_int(w.get("height"), default_h)
    root.geometry(f"{width}x{height}")
    min_w = w.get("min_width", default_min_w)
    min_h = w.get("min_height", default_min_h)
    if min_w is not None and min_h is not None:
        root.minsize(_pos_int(min_w, 1), _pos_int(min_h, 1))
