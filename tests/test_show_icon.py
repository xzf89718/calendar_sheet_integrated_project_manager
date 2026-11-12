# -*- coding: utf-8 -*-
"""v3.7.1 品牌图标：JSON 开关 / 命令行覆盖 / 终端 ANSI 图标 / GUI 闪屏。

终端图标与 PNG 解码用例无 DISPLAY 也跑；GUI 闪屏生命周期用例需
xvfb-run。
"""
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args, cwd=PROJECT_ROOT):
    return subprocess.run(
        [sys.executable] + args, cwd=cwd,
        capture_output=True, text=True, timeout=120)


# ---------- 参数解析与开关裁决 ----------

def test_main_show_icon_flag_accepted():
    """--show-icon 与 --check-config 同用：只校验配置，不弹闪屏。"""
    r = _run(["main.py", "--show-icon", "--check-config"])
    assert r.returncode == 0, r.stderr


def test_main_no_show_icon_flag_accepted():
    r = _run(["main.py", "--no-show-icon", "--check-config"])
    assert r.returncode == 0, r.stderr


def test_workbench_ui_gui_show_icon_passthrough():
    r = _run(["-m", "workbench_ui", "gui", "--show-icon",
              "--check-config"])
    assert r.returncode == 0, r.stderr


def test_show_icon_unknown_flag_still_rejected():
    r = _run(["main.py", "--show-icn"])
    assert r.returncode == 2


def test_resolve_show_icon_precedence():
    """裁决：--show-icon > --no-show-icon > JSON > 缺省 false。"""
    from show_icon import resolve_show_icon
    assert resolve_show_icon(True, False, False) is True
    assert resolve_show_icon(True, True, False) is True    # on 优先
    assert resolve_show_icon(False, True, True) is False
    assert resolve_show_icon(False, False, True) is True
    assert resolve_show_icon(False, False, False) is False  # 缺省
    assert resolve_show_icon(False, False, None) is False   # 缺键


def test_cfg_show_icon_default_false():
    """样例 fields.json 缺省 false；config 加载正确。"""
    from config import CFG
    assert CFG.show_icon is False


# ---------- 终端图标（scripts/ 脚本渲染） ----------

def test_tty_icon_no_ansi_fallback():
    """脚本渲染失败时静默放弃：无 ANSI 兜底输出（用户定 2026-11-10，
    经典控制台兜不住且多占代码），且不再 import 已删除的 render_tty。"""
    import show_icon as s
    orig = s._try_script_render
    s._try_script_render = lambda *a, **k: False
    try:
        s.tty_icon()                     # 不抛错、不打印
    finally:
        s._try_script_render = orig
    assert not hasattr(s, "render_tty")   # ANSI 渲染函数已整体删除


def test_tty_icon_script_path():
    """脚本渲染路径：bash 执行 scripts/show_icon.sh，输出经子进程
    管道捕获（产品名 + bright SGR + #$& 字符画）。"""
    r = subprocess.run(
        [sys.executable, "-m", "workbench_ui", "--show-icon"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        timeout=120)
    assert r.returncode == 0, r.stderr
    assert "日历表格聚合项目跟进工作台" in r.stdout
    for ch in ("#", "&", "$"):
        assert ch in r.stdout
    if os.name != "nt":
        assert "\x1b[92m" in r.stdout     # sh 脚本 ANSI（绿 bright）
    # Windows 走 show_icon.ps1（[Console] 颜色，不经 ANSI）


def test_tty_icon_missing_file_errors():
    """图标缺失：tty_icon 抛 FileNotFoundError（不静默吞）。"""
    from show_icon import tty_icon
    with pytest.raises(FileNotFoundError):
        tty_icon(path=os.path.join(PROJECT_ROOT, "icon", "nope.png"))


# ---------- PNG 解码器 ----------

def test_decode_png_rgba_real_icon():
    from show_icon import decode_png_rgba
    w, h, px = decode_png_rgba(
        os.path.join(PROJECT_ROOT, "icon", "pm_workbench_icon.png"))
    assert (w, h) == (1024, 1024)
    assert len(px) == w * h * 4
    assert px[3] == 0                        # 左上角 = 全透明
    mid = ((h // 2) * w + w // 2) * 4      # 中心 = Y 白缝附近
    assert any(px[mid:mid + 4])


# ---------- GUI 闪屏生命周期（需 DISPLAY） ----------

tk = pytest.importorskip("tkinter",
                         reason="tkinter 不可用，跳过 GUI 用例")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="无 DISPLAY（用 xvfb-run 运行）")


def test_splash_window_shows_and_closes():
    import main
    main._show_icon_splash(ms=50)   # 到时自毁；能返回即生命周期正确


# ---------- 终端字符画 #$&（2026-11-09 用户定稿） ----------

def test_render_ascii_real_icon():
    """真实图标采样：三符号齐备、行数与符号集合法、行尾无透明空格。"""
    from show_icon import render_ascii, _CLASSES, _CLS_TRANSPARENT
    rows = render_ascii()
    assert len(rows) >= 16
    text = ["".join(ch for ch, _ in line) for line in rows]
    joined = "\n".join(text)
    for ch in ("#", "&", "$"):
        assert ch in joined
    for line in rows:
        for ch, cls in line:
            assert ch in (" ", "#", "&", "$")
            assert cls == _CLS_TRANSPARENT or 0 <= cls < len(_CLASSES)
        assert not line or line[-1][1] != _CLS_TRANSPARENT   # 行尾已剥


def test_render_ascii_class_symbols():
    """类别→符号映射：绿 #、蓝 &、红 $、白 #。"""
    from show_icon import render_ascii, _CLASSES
    assert [c[1] for c in _CLASSES] == ["#", "&", "$", "#"]


def test_gen_ps1_ascii_and_data():
    """ps1 纯 ASCII、含标记、段编码 k 合法（0~4）。"""
    from show_icon import _gen_ps1, render_ascii
    rows = render_ascii()
    text = _gen_ps1(rows, "mtime=1.0 size=2")
    assert all(ord(c) < 128 for c in text)
    assert "mtime=1.0 size=2" in text
    assert "param([string]$Name" in text
    assert "$col = @('', 'Green', 'Blue', 'Red', 'White')" in text
    for line in rows:
        for k, n in (seg.split(",") for seg in
                     " ".join(f"{c_ + 1},{n_}" for c_, n_ in
                              __import__("show_icon")._rle(line)).split()):
            assert 0 <= int(k) <= 4 and int(n) >= 1


def test_gen_sh_runs_in_bash():
    """sh 脚本端到端：bash 执行输出产品名 + 字符画 + bright SGR。"""
    import shutil
    import tempfile
    from show_icon import _gen_sh, render_ascii
    if not shutil.which("bash"):
        return
    rows = render_ascii()
    text = _gen_sh(rows, "mtime=1.0 size=2")
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     newline="\n") as f:
        f.write(text)
        fp = f.name
    r = subprocess.run(["bash", fp, "TESTNAME"], capture_output=True,
                       text=True, timeout=30)
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and "TESTNAME" in lines[0]
    assert len(lines) == 1 + len(rows)
    for code in ("92", "94", "91", "97"):
        assert f"\x1b[{code}m" in r.stdout


def test_backend_kind():
    """后端判别：POSIX → sh；Windows → ps1。"""
    from show_icon import _backend_kind
    assert _backend_kind() == ("ps1" if os.name == "nt" else "sh")


def test_rle_merges_and_counts():
    """RLE：同类相邻合并、计数正确。"""
    from show_icon import _rle, _CLS_TRANSPARENT as T
    line = [("#", 0), ("#", 0), (" ", T), (" ", T), ("$", 2), ("#", 3)]
    assert _rle(line) == [(0, 2), (T, 2), (2, 1), (3, 1)]


# ---------- v3.7.2：CLI 全命令图标开关 ----------

def test_workbench_ui_all_subcommands_expose_icon_flags():
    """workbench_ui 每个子命令（含 fav 二级动作）help 都暴露双开关。"""
    cmds = ["list", "show", "new", "follow", "import", "export",
            "weekly", "backup", "notify", "cal", "fav",
            "fav list", "fav new", "fav rename", "fav delete",
            "fav add", "fav remove"]
    for c in cmds:
        r = subprocess.run(
            [sys.executable, "-m", "workbench_ui"] + c.split() + ["--help"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, f"{c}: {r.stderr}"
        assert "--show-icon" in r.stdout, c
        assert "--no-show-icon" in r.stdout, c


def test_check_config_tty_icon_under_pty():
    """main.py --check-config --show-icon：pty 下图标先播（行流、
    不停顿），随后立即输出校验结果。"""
    pty = pytest.importorskip("pty")   # Windows 无 pty/termios，跳过
    import select
    master, slave = pty.openpty()
    try:
        r = subprocess.run(
            [sys.executable, "main.py", "--check-config", "--show-icon"],
            cwd=PROJECT_ROOT, stdin=slave, stdout=slave, stderr=slave,
            timeout=120, close_fds=True)
    finally:
        os.close(slave)
    out = b""
    while True:
        rl, _, _ = select.select([master], [], [], 2)
        if not rl:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    os.close(master)
    text = out.decode("utf-8", "replace")
    assert r.returncode == 0, text
    assert "日历表格聚合项目跟进工作台" in text      # 图标先播
    assert "配置校验通过" in text                    # 随后执行原命令
    assert text.index("日历表格聚合项目跟进工作台") < text.index("配置校验通过")


def test_cached_script_skips_png_decode():
    """缓存命中时连 PNG 都不解码：render_ascii 打桩抛错，脚本渲染
    仍须成功（v3.7.2 卡顿修复的行为锁；脚本存在即执行，不校验
    内容，重新采样是手动动作）。"""
    from show_icon import _backend_kind, _write_script, render_ascii, \
        _try_script_render
    kind = _backend_kind()
    _write_script(kind, render_ascii())      # 确保脚本与标记就位
    import show_icon as s
    orig = s.render_ascii
    s.render_ascii = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("PNG decoded on cached run!"))
    try:
        assert _try_script_render("缓存测试") is True
    finally:
        s.render_ascii = orig


def test_regen_scripts_writes_both(tmp_path, monkeypatch):
    """手动重采样入口 regen_scripts：ps1 + sh 两个脚本都写出，
    ps1 内容纯 ASCII（Windows GBK 控制台安全），含溯源标记。"""
    import show_icon as s
    monkeypatch.setattr(s, "_scripts_dir", lambda: str(tmp_path))
    written = [fp for fp in s.regen_scripts() if fp]
    assert len(written) == 2
    ps1 = (tmp_path / "show_icon.ps1").read_text(encoding="utf-8")
    sh = (tmp_path / "show_icon.sh").read_text(encoding="utf-8")
    assert ps1.isascii()
    assert "pm_workbench_icon.png" in ps1        # 溯源标记
    assert sh.startswith("#!/usr/bin/env bash")


def test_show_icon_main_resamples_in_place():
    """`python show_icon.py` 命令行入口：幂等重采样（图标未变则
    内容不变），stdout 报出两个脚本路径。"""
    import subprocess
    import sys
    from config import BASE_DIR
    r = subprocess.run([sys.executable, "show_icon.py"],
                       cwd=BASE_DIR, capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stderr
    assert "show_icon.ps1" in r.stdout
    assert "show_icon.sh" in r.stdout
