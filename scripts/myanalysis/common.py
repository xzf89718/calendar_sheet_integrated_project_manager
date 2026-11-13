# -*- coding: utf-8 -*-
"""common.py - runmyanalysis 公共件。

run()         以项目根为 cwd 调项目 CLI（python -m ...），统一 UTF-8 管道编码；
              check=True（默认）非零退出即 SystemExit 中止流水线，
              check=False 只警告继续（用于周报清洗这类"数据状态"型失败）。
expand_where  把 where 里的日期令牌展开成具体日期：
              @today = 今天；@today-30d = 30 天前；@today-1m = 一个月前
              （日历月，同日；月底自动钳制，如 3-31 一个月前 = 2-28）。
              例："start_date=@today-1m~@today" = 过去一个月。
with_on()     过滤清单里 on 不为 False 的行（行开关；删行也行）。
mkdir()       建输出子目录（幂等）。
"""
import calendar
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]   # 项目根（fields.json 同目录）

_TOKEN = re.compile(r"^@today(-(\d+)([dm]))?$")


def _expand_token(tok):
    """@today / @today-30d / @today-1m → YYYY-MM-DD；其余原样。"""
    t = tok.strip()
    m = _TOKEN.match(t)
    if not m:
        return tok
    today = date.today()
    if not m.group(2):
        return today.isoformat()
    n = int(m.group(2))
    if m.group(3) == "d":
        return (today - timedelta(days=n)).isoformat()
    year, month = today.year, today.month - n
    while month <= 0:
        month += 12
        year -= 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def expand_where(w):
    """展开 where 值里的日期令牌（支持 起~止 区间，两侧各自展开）。"""
    key, _, val = w.partition("=")
    if "~" in val:
        a, _, b = val.partition("~")
        val = f"{_expand_token(a)}~{_expand_token(b)}"
    else:
        val = _expand_token(val)
    return f"{key}={val}"


def with_on(rows):
    """只留 on 不为 False 的配置行（on 缺省 = True）。"""
    return [r for r in rows if r.get("on", True)]


def mkdir(out_dir, name):
    """在 out_dir 下建子目录 name（连带父目录），返回 Path。"""
    p = Path(out_dir) / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _env():
    # Windows 管道默认编码随控制台代码页（GBK 常见），中文输出乱码/解码炸；
    # 强制子进程 stdout/stderr 走 UTF-8。
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(args, label=None, check=True):
    """调一次项目 CLI。args = ['workbench_ui', 'export', ...]。

    check=True（默认）：退出码非 0 → 打印 stderr，SystemExit 中止流水线。
    check=False：只打警告，返回 CompletedProcess 由调用方决定。
    """
    label = label or " ".join(str(a) for a in args[:2])
    cmd = [sys.executable, "-m"] + [str(a) for a in args]
    print(f"\n--- [{label}] {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, env=_env())
    out = p.stdout.decode("utf-8", errors="replace").strip()
    err = p.stderr.decode("utf-8", errors="replace").strip()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    if p.returncode != 0:
        if check:
            raise SystemExit(f"[{label}] 失败（退出码 {p.returncode}），流水线中止。")
        print(f"[{label}] 退出码 {p.returncode}（警告，流水线继续）")
    return p


def has_matplotlib():
    """饼图 PNG 的可选依赖探测（缺失时调用方降级只出 CSV 计数）。"""
    return find_spec("matplotlib") is not None
