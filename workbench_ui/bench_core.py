# -*- coding: utf-8 -*-
"""workbench_ui 纯逻辑：主窗口全部 GUI 功能的 CLI 内核（v3.3.0）。

纪律：
  * 不 import tkinter —— 本文件与 GUI 完全解耦；
  * 运行时取 config.CFG / db 模块量（冻结绑定坑：不 from 绑定）；
  * 库路径锚定 fields.json 同目录，与 main.py 同一规则（无 --db）；
  * 校验与 GUI 完全同源（db.validate_* / db.check_date_bounds，
    v3.3.0 从 editor.py 下沉，两处共用一份）。
业务错误一律 raise BenchError(message)，由 __main__.py 统一打印 + 退出码 1。
"""
import csv
import os
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import config as _config
import db as _db
import exporter as _exporter
import importer as _importer


class BenchError(Exception):
    """业务错误：消息面向用户，__main__ 打印到 stderr 并退出 1。"""


def _cfg():
    return _config.CFG


def _rg(row, key, default=""):
    """sqlite3.Row 安全取值（Row 没有 .get）。"""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


def open_db():
    """打开库（锚定 fields.json 同目录；不存在则建，与 main 一致）。"""
    return _db.Database(os.path.join(_config.BASE_DIR, _cfg().db_name))


# ---------- where / 筛选 ----------

def parse_where(items):
    """['字段=值', '日期字段=起~止', ...] -> filters dict（query_projects
    的规格：单值=勾选集合，区间=(d1,d2) 已规范化成 YYYY-MM-DD）。"""
    filters, errors = {}, []
    cfg = _cfg()
    names = set(cfg.names)
    for it in items or []:
        field, sep, val = it.partition("=")
        field, val = field.strip(), val.strip()
        if not sep or not field:
            errors.append(f"--where 格式应为 字段=值：{it!r}")
            continue
        if field not in names:
            errors.append(f"不存在的字段：{field}"
                          f"（可用：{' / '.join(cfg.names)}）")
            continue
        if "~" in val:
            if field not in cfg.date_fields:
                errors.append(f"字段 {field} 不是日期字段，不能用 ~ 区间")
                continue
            a, _, b = val.partition("~")
            d1 = _db.normalize_date(a.strip()) if a.strip() else ""
            d2 = _db.normalize_date(b.strip()) if b.strip() else ""
            if a.strip() and not d1:
                errors.append(f"区间起点不是有效日期：{a.strip()!r}")
                continue
            if b.strip() and not d2:
                errors.append(f"区间终点不是有效日期：{b.strip()!r}")
                continue
            filters[field] = (d1, d2)
        else:
            filters[field] = {val}
    if errors:
        raise BenchError("\n".join(errors))
    return filters


def _search_fields():
    return list(_cfg().search_fields)


# ---------- list ----------

def list_columns():
    """list 的列：id 恒打头（索引列），其余 = fields.json 显示列。"""
    cfg = _cfg()
    cols, heads = ["id"], {"id": "id"}
    for n, h in cfg.display_cols:
        if n != "id" and n not in heads:
            cols.append(n)
            heads[n] = h
    return cols, heads


def cmd_list(db, closed=False, search=None, where=None, sort=None,
             desc=False, limit=None, offset=0, fav=None):
    """项目列表。返回 (rows, total)。sort 缺省 = 配置 default_sort。

    fav = 收藏夹名（v3.3.4）：只看该夹内项目，且每行追加 "fav" 键 =
    该项目所属全部收藏夹名（顿号连接），供调用方加「收藏夹」列。
    收藏夹是纯索引，本过滤只是视图层，与导入导出的全库语义无关。
    """
    cfg = _cfg()
    filters = parse_where(where)
    if fav is not None:
        cid = _find_collection(db, fav)
        filters["id"] = set(db.collection_projects(cid))
    if sort is None:
        sort = cfg.default_sort["column"]
        desc = cfg.default_sort["desc"]
    elif sort != "id" and sort not in cfg.names:
        raise BenchError(f"排序列不存在：{sort}"
                         f"（可用：id / {' / '.join(cfg.names)}）")
    rows, total = db.query_projects(
        filters=filters, keywords=list(search or []),
        search_fields=_search_fields(),
        sort=sort, sort_desc=desc,
        include_closed=closed, offset=offset, limit=limit)
    if fav is not None:
        memb = {}
        for cid, name, _n in db.list_collections():
            for pid, _t in db.collection_items_detail(cid):
                memb.setdefault(pid, []).append(name)
        for r in rows:
            r["fav"] = "、".join(memb.get(r["id"], []))
    return rows, total


# ---------- show / new / follow ----------

def _require_project(db, pid):
    row = db.get_current(pid)
    if row is None:
        raise BenchError(f"项目 #{pid} 不存在")
    return row


def cmd_show(db, pid, hist=None):
    """项目详情：当前快照全字段 + 历史快照列表（新在上）。
    hist=N 时返回第 N 条历史（1 = 最新）的全字段。返回 dict。"""
    cur = _require_project(db, pid)
    title = _rg(db.get_project(pid), "title")
    snaps = db.get_snapshots(pid)          # 时间正序
    if hist is not None:
        if not 1 <= hist <= len(snaps):
            raise BenchError(
                f"项目 #{pid} 共有 {len(snaps)} 条历史，没有第 {hist} 条")
        return {"current": cur, "title": title, "hist_index": hist,
                "hist": snaps[len(snaps) - hist], "total": len(snaps)}
    return {"current": cur, "title": title, "snaps": list(reversed(snaps))}


def _parse_sets(sets):
    """['字段=值', ...] -> dict；字段名校验，值不做类型清洗（清洗在
    validate_snapshot_fields 里与 GUI 同源完成）。"""
    cfg = _cfg()
    out, errors = {}, []
    for it in sets or []:
        field, sep, val = it.partition("=")
        field = field.strip()
        if not sep or not field:
            errors.append(f"--set 格式应为 字段=值：{it!r}")
            continue
        if field not in cfg.names:
            errors.append(f"不存在的字段：{field}"
                          f"（可用：{' / '.join(cfg.names)}）")
            continue
        out[field] = val
    if errors:
        raise BenchError("\n".join(errors))
    return out


def _validate_or_raise(fields):
    cleaned, errors = _db.validate_snapshot_fields(fields)
    if errors:
        raise BenchError("输入校验未通过：\n- " + "\n- ".join(errors))
    errors = _db.check_date_bounds(cleaned)
    if errors:
        raise BenchError("日期范围检查未通过：\n- " + "\n- ".join(errors)
                         + "\n（检查器可在 fields.json 的 date_check 段关闭）")
    return cleaned


def cmd_new(db, sets, note=None):
    """新建项目 + 首快照。未传的字段：default > choice 首项 > 空
    （与 GUI 编辑器预填优先级一致）。返回 (pid, title)。"""
    cfg = _cfg()
    given = _parse_sets(sets)
    if note and "followup_note" in cfg.names:
        given.setdefault("followup_note", note)
    fields = {}
    for f in cfg.names:
        if f in given:
            fields[f] = given[f]
        elif f in cfg.field_defaults:
            fields[f] = str(cfg.field_defaults[f])
        elif f in cfg.choice_fields or f == cfg.status_field:
            opts = (cfg.choice_fields.get(f) or cfg.status_options)
            fields[f] = (opts or [""])[0]
        else:
            fields[f] = ""
    cleaned = _validate_or_raise(fields)
    pid = db.create_project(**cleaned)
    return pid, db.get_project(pid)["title"]


def cmd_follow(db, pid, sets, note=None):
    """追加跟进快照（= GUI 的"查看/跟进"保存）。未传的字段保持
    当前值；--note 写入跟进记录字段（存在时）。返回 (snap_id, summary)。"""
    cfg = _cfg()
    _require_project(db, pid)
    given = _parse_sets(sets)
    if note and "followup_note" in cfg.names:
        given.setdefault("followup_note", note)
    cur = db.get_current(pid)
    fields = {f: ("" if cur[f] is None else str(cur[f]))
              for f in cfg.names}
    fields.update(given)
    cleaned = _validate_or_raise(fields)
    sid = db.add_snapshot(pid, **cleaned)   # summary 由 diff_summary 自动生成
    snap = db.conn.execute(
        "SELECT change_summary FROM snapshots WHERE id=?",
        (sid,)).fetchone()
    return sid, snap["change_summary"]


# ---------- import / export / weekly ----------

def _find_template(name, for_weekly=False):
    cfg = _cfg()
    if name is None:
        tpls = [t for t in cfg.templates
                if for_weekly == (t.get("kind") == "weekly")]
        if len(tpls) == 1:
            return tpls[0]
        if not tpls:
            return None
        raise BenchError(
            "有多个模板，请用 --template 指定："
            + " / ".join(t["name"] for t in tpls))
    for t in cfg.templates:
        if t["name"] == name and for_weekly == (t.get("kind") == "weekly"):
            return t
    raise BenchError(f"模板不存在：{name}")


def cmd_import(db, path, template=None):
    tpl = _find_template(template)
    if not os.path.exists(path):
        raise BenchError(f"文件不存在：{path}")
    try:
        created, skipped, unmapped = _importer.import_file(db, path,
                                                           template=tpl)
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导入失败：{e}")
    return created, skipped, unmapped


def cmd_export(db, out_path, template=None, closed=False, search=None,
               where=None, sort=None, desc=False):
    """导出全量匹配行（与 GUI 导出同语义，不受 limit 影响）。"""
    lower = str(out_path).lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".csv")):
        raise BenchError("导出只支持 .xlsx / .csv（按扩展名）")
    rows, _ = cmd_list(db, closed=closed, search=search, where=where,
                       sort=sort, desc=desc, limit=None)
    tpl = _find_template(template)
    if tpl is None:
        raise BenchError("没有可用模板（fields.json 的 templates 段）")
    try:
        if lower.endswith(".csv"):
            n = _exporter.export_csv(rows, out_path, tpl)
        else:
            n = _exporter.export_with_template(rows, out_path, tpl)
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导出失败：{e}")
    return n


def _default_week_bounds():
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    d = lambda x: x.strftime("%Y-%m-%d")      # noqa: E731
    return d(mon), d(mon + timedelta(days=6)), \
        d(mon + timedelta(days=7)), d(mon + timedelta(days=13))


def cmd_weekly(db, out_path, d1=None, d2=None, p1=None, p2=None):
    """周报导出：本周跟进 + 下周计划。日期缺省 = 本周一~日/下周一~日。"""
    if not str(out_path).lower().endswith(".xlsx"):
        raise BenchError("周报导出只支持 .xlsx")
    dd1, dd2, pp1, pp2 = _default_week_bounds()
    d1, d2, p1, p2 = d1 or dd1, d2 or dd2, p1 or pp1, p2 or pp2
    for label, v in (("from", d1), ("to", d2),
                     ("plan-from", p1), ("plan-to", p2)):
        if not _db.normalize_date(v):
            raise BenchError(f"--{label} 不是有效日期：{v!r}")
    tpl = _find_template(None, for_weekly=True)
    if tpl is None:
        tpl = {"kind": "weekly", "columns": [
            ("日期", "__date__", None), ("项目", "__name__", None),
            ("跟进记录", "followup_note", None),
            ("改动说明", "change_summary", None)]}
    rows_f = db.snapshots_between(d1, d2)
    rows_p = db.weekly_plan(p1, p2, include_closed=False)
    try:
        nf, np_ = _exporter.export_weekly(rows_f, rows_p, tpl, out_path)
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导出失败：{e}")
    return nf, np_


# ---------- backup / notify ----------

def _safe_ident(s):
    """识别符文件名安全化（与 main.py 同一规则）。"""
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" .") or "备份"


def backup_database(db, db_path):
    """SQLite 在线备份。返回备份文件路径。异常原样抛（调用方处理）。"""
    cfg = _cfg()
    dest = Path(cfg.backup.get("path", "backups")).expanduser()
    if not dest.is_absolute():
        dest = Path(_config.BASE_DIR) / dest
    dest.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    ident = _safe_ident(str(cfg.backup.get("identifier", "备份")))
    target = dest / f"{ts}-{ident}-{Path(db_path).name}"
    tgt = sqlite3.connect(str(target))
    try:
        db.conn.backup(tgt)                   # 官方在线备份，一致性快照
    finally:
        tgt.close()
    return str(target)


def today_notify_text(db):
    """notify 子命令的数据：当天项目时间节点（终端打印版，不走 toast）。"""
    t = date.today()
    entries = [e for e in db.calendar_entries(t.year, t.month)
               if e["date"] == t.isoformat()]
    import notifier
    if not entries:
        return "今日项目事项\n- 今天没有项目时间节点"
    title, lines = notifier.build_today_message(entries)
    return title + "\n" + "\n".join("- " + ln for ln in lines)


# ---------- 收藏夹 ----------

def _find_collection(db, name):
    for cid, cname, _n in db.list_collections():
        if cname == name:
            return cid
    raise BenchError(f"收藏夹不存在：{name}")


def cmd_fav_list(db):
    return [(name, n, [r[0] for r in db.collection_items_detail(cid)])
            for cid, name, n in db.list_collections()]


def cmd_fav_new(db, name):
    for _cid, cname, _n in db.list_collections():
        if cname == name:
            raise BenchError(f"收藏夹已存在：{name}")
    return db.create_collection(name)


def cmd_fav_rename(db, old, new):
    db.collection_rename(_find_collection(db, old), new)


def cmd_fav_delete(db, name):
    db.delete_collection(_find_collection(db, name))


def cmd_fav_add(db, name, ids):
    cid = _find_collection(db, name)
    for pid in ids:
        _require_project(db, pid)
    db.collection_add(cid, ids)


def cmd_fav_remove(db, name, ids):
    cid = _find_collection(db, name)
    for pid in ids:
        db.collection_remove(cid, pid)


# ---------- cal（只读打印） ----------

def cmd_cal(db, year, month=None, day=None):
    """年/月/日的时间节点清单（只读）。返回 [(date, kind_label, text,
    project_id), ...] 按日期排序；project_id 供 show/follow 接续。"""
    cfg = _cfg()
    labels = {k: l for k, _f, l, _c in cfg.calendar_dates}
    months = [month] if month else range(1, 13)
    out = []
    for m in months:
        for e in db.calendar_entries(year, m):
            if day and int(e["date"][8:10]) != day:
                continue
            out.append((e["date"], labels.get(e["kind"], e["kind"]),
                        e["text"], e["project_id"]))
    out.sort()
    return out


# ---------- 输出格式 ----------

def _disp_w(s):
    """显示宽度：东亚宽字符/全角 = 2，其余 = 1。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in s)


def _pad(s, w):
    return s + " " * max(0, w - _disp_w(s))


def format_table(rows, cols, heads):
    """对齐表格：列间两空格，全角按 2 宽；无数据时只有表头。"""
    matrix = [["" if r.get(c) is None else str(r.get(c, ""))
               for c in cols] for r in rows]
    widths = [_disp_w(heads[c]) for c in cols]
    for row in matrix:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _disp_w(cell))
    lines = ["  ".join(_pad(heads[c], widths[i])
                        for i, c in enumerate(cols))]
    lines.append("  ".join("-" * w for w in widths))
    for row in matrix:
        lines.append("  ".join(_pad(cell, widths[i])
                               for i, cell in enumerate(row)))
    return "\n".join(lines)


def format_csv(rows, cols, heads):
    import io as _io
    buf = _io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([heads[c] for c in cols])
    for r in rows:
        writer.writerow(["" if r.get(c) is None else r.get(c, "")
                         for c in cols])
    return buf.getvalue().rstrip("\n")
