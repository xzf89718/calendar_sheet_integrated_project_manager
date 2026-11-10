# -*- coding: utf-8 -*-
"""品牌图标展示（v3.7.1）：GUI 闪屏 + 终端 ASCII 字符画，双通道。

  show_icon.gui_splash(ms)    GUI 闪屏：屏幕中央 512px 无边框，
                              透明底（Windows 透明色键控），ms 毫秒自毁
  show_icon.tty_icon()        终端图标：加载 scripts/ 下薄脚本
                              （ps1 走 [Console] 颜色 / sh 走 ANSI）；
                              失败静默放弃，无 ANSI 兜底（用户定，
                              经典控制台兜不住且多占代码）

终端字符画定稿（2026-11-09 用户定）：只用 #$& 三个符号 + 空格，
Ubuntu/Debian version 横幅的 ASCII logo 风格——绿区 #、蓝区 &、
红区 $、白色细节以白色 # 呈现。纯 ASCII 字符 + 16 色，不挑终端
编码与字体（半块字符 U+2580/U+2584 在 GBK 控制台退化成 ?，已
弃用；truecolor/256 探测降级链随之整体移除）。

PNG 解码只支持本项目图标实际用到的子集：8-bit、color type 6
(RGBA) 或 2 (RGB)、非隔行——文件不符时报错，不猜测。
"""
import os
import struct
import sys
import zlib

# 终端字符画的横向字符格数（1024px 原图每格约 21px，按字符 2:1
# 纵横比纵向取格，整图约 24 行）
TTY_COLS = 48


def icon_path():
    """图标锚定 fields.json 同目录的 icon/pm_workbench_icon.png
    （与项目 fields.json 锚定准则一致）。"""
    from config import BASE_DIR
    return os.path.join(BASE_DIR, "icon", "pm_workbench_icon.png")


# ---------------------------------------------------------------- PNG 解码

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def decode_png_rgba(path):
    """最小 PNG 解码器：8-bit RGBA/RGB 非隔行 → (width, height, bytes
    RGBA 每像素 4 字节)。仅服务品牌图标，不做通用解码器。"""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG 文件")
    pos, width, height, color_type, idat = 8, None, None, None, b""
    while pos < len(raw):
        (length, ctype) = struct.unpack(">I4s", raw[pos:pos + 8])
        chunk = raw[pos + 8: pos + 8 + length]
        if ctype == b"IHDR":
            (width, height, bitdepth, color_type, _comp, _filt,
             interlace) = struct.unpack(">IIBBBBB", chunk)
            if bitdepth != 8 or interlace != 0 \
                    or color_type not in (2, 6):
                raise ValueError(
                    "PNG 子集不支持：需 8-bit RGBA/RGB 非隔行")
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if width is None or not idat:
        raise ValueError("PNG 缺 IHDR/IDAT")
    bpp = 4 if color_type == 6 else 3
    stride = width * bpp
    data = zlib.decompress(idat)
    px = bytearray(width * height * 4)
    prev = bytearray(stride)
    off = 0
    for y in range(height):
        filt = data[off]
        line = bytearray(data[off + 1: off + 1 + stride])
        off += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if filt == 1:
                line[x] = (line[x] + a) & 0xFF
            elif filt == 2:
                line[x] = (line[x] + b) & 0xFF
            elif filt == 3:
                line[x] = (line[x] + (a + b) // 2) & 0xFF
            elif filt == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
        for x in range(width):
            si, di = x * bpp, (y * width + x) * 4
            px[di:di + 3] = line[si:si + 3]
            px[di + 3] = line[si + 3] if bpp == 4 else 255
        prev = line
    return width, height, bytes(px)


# ------------------------------------------------------- 终端字符画（#$&）

# 颜色类别表：绿区 #、蓝区 &、红区 $、白色细节 #（白字符呈现）、
# 透明空格。ANSI 列 = bright SGR 前景码（16 色基础，处处可渲染）；
# ps1 列 = [ConsoleColor] 名（经典控制台无需 ANSI/VT）。
_CLASSES = [
    #   (名,      符号, 类基准 RGB,        ANSI SGR, [ConsoleColor])
    ("green", "#", (32, 140, 40), 92, "Green"),
    ("blue",  "&", (0, 100, 200), 94, "Blue"),
    ("red",   "$", (210, 40, 40), 91, "Red"),
    ("white", "#", (235, 235, 235), 97, "White"),
]
_CLS_TRANSPARENT = -1
_ALPHA_MIN = 64                   # 格内平均 alpha 低于此值视为透明


def render_ascii(path=None, cols=TTY_COLS):
    """图标采样为 ASCII 字符画：每行 [(ch, cls)]，cls 取
    _CLS_TRANSPARENT 或 _CLASSES 下标。按终端字符 2:1 纵横比取格，
    格内多像素平均后归入最近的基准色（抗锯齿边过渡自然）。
    行尾透明空格已剥除。"""
    path = path or icon_path()
    w, h, px = decode_png_rgba(path)
    sx = max(1, round(w / cols))
    rows_target = max(8, round(cols * h / w / 2))
    sy = max(1, round(h / rows_target))
    nx = max(1, sx // 2)             # 格内稀疏采样 2x4 点做平均
    ny = max(1, sy // 4)
    rows = []
    for cy in range(0, h, sy):
        line = []
        for cx in range(0, w, sx):
            rs = gs = bs = al = n = 0
            for dy in range(0, sy, ny):
                for dx in range(0, sx, nx):
                    yy = cy + dy if cy + dy < h else h - 1
                    xx = cx + dx if cx + dx < w else w - 1
                    i = (yy * w + xx) * 4
                    rs += px[i]
                    gs += px[i + 1]
                    bs += px[i + 2]
                    al += px[i + 3]
                    n += 1
            if al // n < _ALPHA_MIN:
                line.append((" ", _CLS_TRANSPARENT))
                continue
            rgb = (rs // n, gs // n, bs // n)
            cls = min(range(len(_CLASSES)),
                      key=lambda k: sum((c - p) ** 2
                                        for c, p in zip(rgb,
                                                        _CLASSES[k][2])))
            line.append((_CLASSES[cls][1], cls))
        while line and line[-1][1] == _CLS_TRANSPARENT:
            line.pop()               # 剥行尾透明空格
        rows.append(line)
    return rows


def _rle(line):
    """一行 [(ch, cls)] → RLE 段 [(cls, count)]（cls=-1 为透明）。"""
    segs = []
    for _ch, cls in line:
        if segs and segs[-1][0] == cls:
            segs[-1] = (cls, segs[-1][1] + 1)
        else:
            segs.append((cls, 1))
    return segs


# ------------------------------------------- scripts/ 脚本渲染（用户定）

# 设计（2026-11-09 用户定）：终端图标不深入系统 API，由 Python 生成
# 薄脚本（RLE 数据 + 通用渲染循环）放根目录 scripts/，再加载执行——
# 兼顾可读性、维护性、速率。PS 脚本走 [Console] 颜色（PowerShell
# 原生机制，经典控制台无需 ANSI/VT）；sh 脚本走 ANSI（mintty 等真
# 终端）。脚本头带图标 mtime/size 标记，图标未变则跳过生成。
# Windows（含 Git Bash/mintty，powershell 子进程经 winpty 翻译
# 控制台颜色）一律 ps1；sh 只留给真正的 POSIX 系统。

def _backend_kind():
    """'ps1'（Windows）或 'sh'（Linux/macOS 等 POSIX）。"""
    return "ps1" if os.name == "nt" else "sh"


def _icon_marker(path):
    """图标溯源标记（写进脚本头，用于变更再生成）。"""
    st = os.stat(path)
    return f"mtime={st.st_mtime:.1f} size={st.st_size}"


def _gen_ps1(rows, marker):
    """生成 show_icon.ps1：纯 ASCII（项目规矩：PS 脚本不含中文，
    产品名由 -Name 参数传入）；[Console] 颜色渲染字符画，不依赖
    ANSI/VT，字符全 ASCII 故控制台代码页无关。段编码 "k,n"：
    k=0 透明 / 1 绿(#) / 2 蓝(&) / 3 红($) / 4 白(#)。"""
    data = ",\n    ".join('"' + " ".join(f"{k + 1},{n}"
                                         for k, n in _rle(line))
                           + '"' for line in rows)
    return f"""# Auto-generated by show_icon.py -- do not edit.
# Renders the brand icon as ASCII art with [Console] colors (no ANSI/VT).
# Segment code "k,n": k=0 transparent, 1 green(#), 2 blue(&), 3 red($), 4 white(#).
# source: icon/pm_workbench_icon.png {marker}
param([string]$Name = "")
$rows = @(
    {data}
)
$sym = @(' ', '#', '&', '$', '#')
$col = @('', 'Green', 'Blue', 'Red', 'White')
$ofg = [Console]::ForegroundColor
$obg = [Console]::BackgroundColor
if ($Name) {{
    [Console]::ForegroundColor = 'White'
    [Console]::WriteLine($Name)
}}
foreach ($row in $rows) {{
    foreach ($seg in $row.Split(' ')) {{
        if ($seg -eq '') {{ continue }}
        $p = $seg.Split(',')
        $k = [int]$p[0]
        if ($k -eq 0) {{
            [Console]::ForegroundColor = $ofg
            [Console]::Write(' ' * [int]$p[1])
        }} else {{
            [Console]::ForegroundColor = $col[$k]
            [Console]::Write($sym[$k] * [int]$p[1])
        }}
    }}
    [Console]::ForegroundColor = $ofg
    [Console]::BackgroundColor = $obg
    [Console]::WriteLine('')
}}
[Console]::ForegroundColor = $ofg
[Console]::BackgroundColor = $obg
"""


def _gen_sh(rows, marker):
    """生成 show_icon.sh：ANSI bright 前景色（mintty/xterm 系真终
    端），一行 printf 输出一行字符画。"""
    out = ["#!/usr/bin/env bash",
           "# Auto-generated by show_icon.py -- do not edit.",
           "# Renders the brand icon as ASCII art with ANSI colors.",
           f"# source: icon/pm_workbench_icon.png {marker}",
           "printf '\\033[1m%s\\033[0m\\n' \"$1\"",
           ]
    for line in rows:
        parts = []
        for cls, n in _rle(line):
            if cls == _CLS_TRANSPARENT:
                parts.append(" " * n)
            else:
                parts.append(f"\\033[{_CLASSES[cls][3]}m"
                             + _CLASSES[cls][1] * n)
        out.append("printf '\\033[0m" + "".join(parts) + "\\033[0m\\n'")
    return "\n".join(out) + "\n"


def _scripts_dir():
    from config import BASE_DIR
    return os.path.join(BASE_DIR, "scripts")


_SCRIPT_FILES = {"ps1": "show_icon.ps1", "sh": "show_icon.sh"}


def _existing_script(kind):
    """scripts/ 下脚本已存在 → 直接返回路径（默认路径：运行时
    只执行脚本，**不解码 PNG、不校验内容**）；缺失返回 None。
    图标变更后的重新采样是手动动作（python show_icon.py），见
    README「图标脚本手动重采样」。"""
    fp = os.path.join(_scripts_dir(), _SCRIPT_FILES[kind])
    return fp if os.path.exists(fp) else None


def _write_script(kind, rows):
    """采样结果落盘为脚本（含溯源标记），返回路径；无图标 None。"""
    path = icon_path()
    if not os.path.exists(path):
        return None
    os.makedirs(_scripts_dir(), exist_ok=True)
    fp = os.path.join(_scripts_dir(), _SCRIPT_FILES[kind])
    gen = _gen_ps1 if kind == "ps1" else _gen_sh
    with open(fp, "w", encoding="utf-8", newline="\n") as f:
        f.write(gen(rows, _icon_marker(path)))
    return fp


def _try_script_render(name="", path=None):
    """加载 scripts/ 下对应脚本执行（默认路径：脚本已存在就直接
    跑，零 PNG 解码）；仅当脚本缺失时才兜底采样生成一次。任何一
    步失败返回 False，调用方静默放弃（无 ANSI 兜底，用户定）。"""
    import subprocess
    import shutil
    try:
        kind = _backend_kind()
        fp = _existing_script(kind)
        if fp is None:
            fp = _write_script(kind, render_ascii(path))
            if not fp:
                return False
        if kind == "ps1":
            exe = shutil.which("powershell") or shutil.which("pwsh")
            if not exe:
                return False
            cmd = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", fp, "-Name", name]
        else:
            exe = shutil.which("bash") or shutil.which("sh")
            if not exe:
                return False
            cmd = [exe, fp, name]
        return subprocess.run(cmd, timeout=30).returncode == 0
    except Exception:                           # noqa: BLE001
        return False


def _product_name():
    from config import CFG
    return CFG.product_name if CFG is not None else ""


def tty_icon(path=None):
    """终端打印品牌图标（含产品名一行，行流输出，不碰光标坐标）：
    加载 scripts/ 下的 ps1/sh 薄脚本执行（用户定；脚本已存在时
    零 PNG 解码，缺失则兜底生成一次）。图标文件缺失抛
    FileNotFoundError；脚本加载失败静默放弃——**无 ANSI 兜底**
    （用户定 2026-11-10：经典控制台兜不住，且多占代码）。"""
    p = path or icon_path()
    if not os.path.exists(p):
        raise FileNotFoundError(f"品牌图标不存在：{p}")
    _try_script_render(_product_name(), path)


# ---------------------------------------------------------------- GUI 闪屏

def gui_splash(ms=3000):
    """GUI 闪屏：屏幕中央 512px 无边框图标，3 秒自毁（v3.7.1：
    透明底——窗口底色品红 + Windows 透明色键控，图标不含品红，
    安全）。图标缺失/读取失败静默跳过，不影响启动。"""
    import tkinter as tk
    path = icon_path()
    if not os.path.exists(path):
        return
    win = tk.Tk()                       # 先建 root：PhotoImage 依赖默认 root
    win.overrideredirect(True)
    try:
        img = tk.PhotoImage(file=path)
    except tk.TclError:
        win.destroy()
        return
    # 1024 原图整数倍缩小到 512（≈500px），不依赖 PIL
    if img.width() > 500:
        img = img.subsample(2, 2)
    w, h = img.width(), img.height()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{sw // 2 - w // 2}+{sh // 2 - h // 2}")
    # 透明底：底色用品红（图标不含），Windows 透明色键控穿透
    KEY = "#ff00ff"
    win.configure(bg=KEY)
    if os.name == "nt":
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
    lbl = tk.Label(win, image=img, bd=0, bg=KEY)
    lbl.image = img                     # 防 PhotoImage 被 GC 回收
    lbl.pack()
    win.after(ms, win.destroy)
    win.mainloop()


# ---------------------------------------------------------------- 开关裁决

def resolve_show_icon(cli_on, cli_off, cfg_value):
    """show_icon 生效值：命令行 > fields.json > 缺省 false。
    cli_on=True 强制开；cli_off=True 强制关（--no-show-icon）。"""
    if cli_on:
        return True
    if cli_off:
        return False
    return bool(cfg_value)


# ---------------------------------------------------------------- 子模块植入
# v3.7.1：全部子模块 GUI/CLI 统一接入品牌图标，开关同源于
# fields.json 的 ui.show_icon（缺省 false），--show-icon /
# --no-show-icon 强覆盖。

def add_icon_flags(ap):
    """给 argparse 解析器注入 --show-icon / --no-show-icon 双开关。"""
    ap.add_argument("--show-icon", dest="show_icon", action="store_true",
                    help="强制显示品牌图标（覆盖 ui.show_icon）")
    ap.add_argument("--no-show-icon", dest="no_show_icon",
                    action="store_true",
                    help="强制关闭品牌图标（覆盖 ui.show_icon）")
    return ap


def want_icon(cli_on=False, cli_off=False):
    """JSON 开关 + 命令行覆盖裁决（缺省 false）。"""
    from config import CFG
    return resolve_show_icon(cli_on, cli_off,
                             CFG.show_icon if CFG is not None else False)


def splash_if_wanted(cli_on=False, cli_off=False):
    """GUI 入口：开关生效则品牌闪屏（屏幕中央 3 秒）。"""
    if want_icon(cli_on, cli_off):
        gui_splash()


def tty_if_wanted(cli_on=False, cli_off=False):
    """CLI 入口：开关生效且 stdout 是交互终端才打印终端图标。
    管道/重定向静默跳过，不污染机器可读输出（pie 计数表、csv）。"""
    if want_icon(cli_on, cli_off) and sys.stdout.isatty():
        tty_icon()


def gui_icon_flags(argv):
    """gui 拦截（argparse 之前）路径的开关解析：两个 flag 可混在
    gui 子命令的参数里。"""
    return "--show-icon" in argv, "--no-show-icon" in argv


# ---------------------------------------------------------------- 手动重采样

def regen_scripts(path=None, cols=TTY_COLS):
    """手动重采样入口：重新解码 PNG 并把结果写回 scripts/ 的
    ps1 + sh 两个薄脚本（覆盖旧脚本）。运行时的默认行为是只
    执行已有脚本、永不解码 PNG；更换图标后须手动调用本函数
    （命令行等价物：python show_icon.py [--icon 路径] [--cols N]）。
    返回写出的脚本路径列表。"""
    rows = render_ascii(path, cols=cols)
    return [_write_script(kind, rows)
            for kind in ("ps1", "sh")]


def _main():
    """`python show_icon.py` 手动重采样命令行入口。"""
    import argparse
    ap = argparse.ArgumentParser(
        description="Resample the brand icon PNG into scripts/"
                    "show_icon.ps1 and scripts/show_icon.sh.")
    ap.add_argument("--icon", default=None,
                    help="icon PNG path (default: icon/pm_workbench_icon.png"
                         " next to fields.json)")
    ap.add_argument("--cols", type=int, default=TTY_COLS,
                    help=f"character columns (default: {TTY_COLS})")
    args = ap.parse_args()
    written = [fp for fp in regen_scripts(args.icon, cols=args.cols) if fp]
    if not written:
        print("icon PNG not found, nothing written", file=sys.stderr)
        raise SystemExit(1)
    for fp in written:
        print(f"resampled -> {fp}")


if __name__ == "__main__":
    _main()
