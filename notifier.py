# -*- coding: utf-8 -*-
"""Windows 通知推送（当天事项）。

可选依赖（Windows 上安装其一即可）：
    pip install windows-toasts      # 推荐，Win10/11 原生通知
    pip install win10toast          # 备选
未安装时 notify() 静默返回 False，不影响其他功能。
"""
import platform

from config import CFG

KIND_LABEL = CFG.cal_labels           # 日历类别显示名，fields.json 可配
_backends = None


def _load_backends():
    """探测可用的通知后端（windows_toasts / win10toast），只探一次。

    非 Windows 或都没装时后端列表为空，notify() 恒返回 False。"""
    global _backends
    if _backends is not None:
        return
    _backends = []
    if platform.system() != "Windows":
        return
    try:
        import windows_toasts          # noqa: F401
        _backends.append("windows_toasts")
    except ImportError:
        pass
    try:
        import win10toast               # noqa: F401
        _backends.append("win10toast")
    except ImportError:
        pass


def available():
    """当前可用的推送后端列表（空 = 不可用）。

    :return: 后端名字符串列表
    :rtype: list
    """
    _load_backends()
    return list(_backends)


def notify(title, lines):
    """推送一条通知；两个后端依次尝试，成功即返回。

    :param title: 通知标题
    :type title: str
    :param lines: 内容行列表
    :type lines: list
    :return: 推送是否成功（无后端或异常时 False）
    :rtype: bool
    """
    _load_backends()
    if "windows_toasts" in _backends:
        try:
            from windows_toasts import Toast, WindowsToaster
            toaster = WindowsToaster(CFG.product_name)
            toaster.show_toast(Toast([title] + list(lines)))
            return True
        except Exception:               # noqa: BLE001
            pass
    if "win10toast" in _backends:
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(
                title, "\n".join(lines), duration=10, threaded=True)
            return True
        except Exception:               # noqa: BLE001
            pass
    return False


def build_today_message(entries):
    """把当天条目聚合成 (标题, 内容行列表)：按类别计数，每类最多列 3 条。

    :param entries: 当日日历条目 dict 列表
    :type entries: list
    :return: 二元组（标题, 内容行列表，最多 6 行）
    :rtype: tuple
    """
    by = {}
    for e in entries:
        by.setdefault(e["kind"], []).append(e["text"])
    counts = "、".join(f"{len(v)}个{KIND_LABEL.get(k, k)}"
                      for k, v in by.items())
    lines = []
    for kind, items in by.items():
        for t in items[:3]:
            lines.append(t)             # text 本身已含 [开始]/[跟进] 标签
        rest = len(items) - 3
        if rest > 0:
            lines.append(f"  …另有 {rest} 条，打开软件查看")
    return f"今日项目事项：{counts}", lines[:6]
