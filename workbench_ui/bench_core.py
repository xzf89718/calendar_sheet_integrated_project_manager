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
    """业务错误异常。

    workbench_ui 纯逻辑层抛出的所有可预期错误（字段不存在、日期非法、
    模板缺失等）一律是 BenchError；消息面向用户，由 ``__main__.py`` 统一
    打印到 stderr 并以退出码 1 结束进程。
    """


def _cfg():
    """取当前配置对象（``config.CFG``）。

    运行时取模块量而非 from 绑定：conftest 在测试里 patch ``config.CFG``
    时这里能看到新值（冻结绑定坑）。

    :return: 当前生效的 Config 对象。
    :rtype: config.Config
    """
    return _config.CFG


def _rg(row, key, default=""):
    """sqlite3.Row 安全取值。

    Row 没有 ``.get``，缺列时抛 KeyError/IndexError；这里捕获后回退
    到默认值，并把 SQL NULL 也视为缺值。

    :param row: 一行查询结果。
    :type row: sqlite3.Row
    :param key: 列名。
    :type key: str
    :param default: 缺列或值为 NULL 时的回退值。
    :return: 列值，缺列/NULL 时返回 default。
    """
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


def open_db():
    """打开库并返回 Database 实例。

    库路径锚定 fields.json 同目录（与 main.py 同一规则，无 --db 参数）；
    不存在则建库。

    :return: 已打开的 Database。
    :rtype: db.Database
    """
    return _db.Database(os.path.join(_config.BASE_DIR, _cfg().db_name))


# ---------- where / 筛选 ----------

def parse_where(items):
    """解析 --where 筛选参数。

    ``['字段=值', '日期字段=起~止', ...]`` -> query_projects 规格的
    filters dict：单值字段 = 勾选集合（同字段多次出现取并集），日期字段 =
    ``(d1, d2)`` 元组（已用 normalize_date 规范化成 YYYY-MM-DD，任一端
    可省略）。全部格式/字段/日期错误收集后一次性 raise。

    :param items: 原始 --where 字符串列表，可为 None。
    :type items: list 或 None
    :return: 字段名 -> set 或 (d1, d2) 的筛选 dict。
    :rtype: dict
    :raises BenchError: 任一条目格式错、字段不存在或日期非法时。
    """
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
            # 同字段多次 --where 取并集（v3.8.5，与 db_analysis 一致）；
            # 与区间混用时后写覆盖
            cur = filters.get(field)
            if isinstance(cur, set):
                cur.add(val)
            else:
                filters[field] = {val}
    if errors:
        raise BenchError("\n".join(errors))
    return filters


def _search_fields():
    """取配置的搜索字段列表（副本）。

    :return: search_fields 字段名列表。
    :rtype: list
    """
    return list(_cfg().search_fields)


# ---------- list ----------

def list_columns():
    """list 输出的列定义。

    id 恒打头（索引列），其余 = fields.json 的 display_cols，去重。

    :return: (列名列表, {列名: 中文表头})。
    :rtype: tuple
    """
    cfg = _cfg()
    cols, heads = ["id"], {"id": "id"}
    for n, h in cfg.display_cols:
        if n != "id" and n not in heads:
            cols.append(n)
            heads[n] = h
    return cols, heads


def cmd_list(db, closed=False, search=None, where=None, sort=None,
             desc=False, limit=None, offset=0, fav=None):
    """项目列表查询内核。

    返回 (rows, total)。sort 缺省 = fields.json 的 default_sort。fav =
    收藏夹名（v3.3.4）时只看该夹内项目，且每行追加 "fav" 键 = 该项目所属
    全部收藏夹名（顿号连接），供调用方加「收藏夹」列；收藏夹是纯索引，
    本过滤只是视图层，与导入导出的全库语义无关。

    :param db: 已打开的库。
    :type db: db.Database
    :param closed: 是否包含已完结项目。
    :type closed: bool
    :param search: 关键词列表（取交集），None = 不搜索。
    :type search: list 或 None
    :param where: --where 原始参数列表，None = 不过滤。
    :type where: list 或 None
    :param sort: 排序列名，None = 用配置 default_sort。
    :type sort: str 或 None
    :param desc: 是否降序（仅 sort 显式给出时生效）。
    :type desc: bool
    :param limit: 每页条数上限，None = 不限。
    :type limit: int 或 None
    :param offset: 跳过的条数。
    :type offset: int
    :param fav: 收藏夹名过滤，None = 不过滤。
    :type fav: str 或 None
    :return: (当前页行列表, 命中总数)。
    :rtype: tuple
    :raises BenchError: 排序列不存在时。
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
    """断言项目存在并返回当前快照行。

    :param db: 已打开的库。
    :type db: db.Database
    :param pid: 项目 id。
    :type pid: int
    :return: 该项目的当前快照行。
    :rtype: sqlite3.Row
    :raises BenchError: 项目不存在时。
    """
    row = db.get_current(pid)
    if row is None:
        raise BenchError(f"项目 #{pid} 不存在")
    return row


def cmd_show(db, pid, hist=None):
    """项目详情查询内核。

    返回当前快照全字段 + 历史快照列表（新在上）的 dict；hist=N 时改返
    回第 N 条历史（1 = 最新）的全字段。

    :param db: 已打开的库。
    :type db: db.Database
    :param pid: 项目 id。
    :type pid: int
    :param hist: 历史序号（1 = 最新），None = 看当前快照 + 历史清单。
    :type hist: int 或 None
    :return: 含 current/title 及 snaps（hist=None）或 hist_index/hist/total
        （hist 非 None）的 dict。
    :rtype: dict
    :raises BenchError: 项目不存在或历史序号越界时。
    """
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
    """解析 --set 赋值参数。

    ``['字段=值', ...]`` -> dict；字段名按 fields.json 校验（不存在则
    收集错误），值不做类型清洗——清洗在 validate_snapshot_fields 里与
    GUI 同源完成。全部错误收集后一次性 raise。

    :param sets: 原始 --set 字符串列表，可为 None。
    :type sets: list 或 None
    :return: 字段名 -> 原始字符串值的 dict。
    :rtype: dict
    :raises BenchError: 任一条目格式错或字段不存在时。
    """
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
    """走与 GUI 完全同源的校验链，不过则一次性 raise。

    依次：validate_snapshot_fields（类型清洗 + 逐字段校验）与
    check_date_bounds（日期范围检查，可在 fields.json 的 date_check 段
    关闭），错误收集后拼成 BenchError 消息。

    :param fields: 待校验的字段 dict。
    :type fields: dict
    :return: 清洗后的字段 dict。
    :rtype: dict
    :raises BenchError: 任一校验未通过时。
    """
    cleaned, errors = _db.validate_snapshot_fields(fields)
    if errors:
        raise BenchError("输入校验未通过：\n- " + "\n- ".join(errors))
    errors = _db.check_date_bounds(cleaned)
    if errors:
        raise BenchError("日期范围检查未通过：\n- " + "\n- ".join(errors)
                         + "\n（检查器可在 fields.json 的 date_check 段关闭）")
    return cleaned


def cmd_new(db, sets, note=None):
    """新建项目 + 首快照。

    未传的字段按 GUI 编辑器同一预填优先级取值：default > choice 首项
    （状态字段用 status_options 首项）> 空串；全部字段过同源校验链。

    :param db: 已打开的库。
    :type db: db.Database
    :param sets: --set 赋值列表。
    :type sets: list 或 None
    :param note: 跟进记录（仅当 followup_note 字段存在时写入）。
    :type note: str 或 None
    :return: (新项目 id, 项目标题)。
    :rtype: tuple
    :raises BenchError: 字段不存在或校验未通过时。
    """
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
    """追加跟进快照（= GUI 的"查看/跟进"保存）。

    未传的字段保持当前值；--note 写入跟进记录字段（存在时）。字段合并
    后过同源校验链，summary 由 add_snapshot 内部 diff_summary 自动生
    成。

    :param db: 已打开的库。
    :type db: db.Database
    :param pid: 项目 id。
    :type pid: int
    :param sets: --set 赋值列表（只列改动的字段）。
    :type sets: list 或 None
    :param note: 本次跟进记录。
    :type note: str 或 None
    :return: (新快照 id, 改动摘要)。
    :rtype: tuple
    :raises BenchError: 项目不存在、字段不存在或校验未通过时。
    """
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
    """按名称与 kind 找导出/导入模板。

    name 为 None 时：唯一匹配直接返回，无匹配返回 None，多个匹配要求
    显式指定并 raise。否则按名称 + kind（weekly 与否）精确匹配。

    :param name: 模板名，None = 自动裁定。
    :type name: str 或 None
    :param for_weekly: 找周报模板还是普通模板。
    :type for_weekly: bool
    :return: 模板 dict；无匹配且可自动裁定时为 None。
    :rtype: dict 或 None
    :raises BenchError: 多模板未指定名或名称不存在时。
    """
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


def cmd_import(db, path, template=None, csv=False):
    """表格导入内核。

    默认按 Excel(xlsx) 解析；csv=True 按 CSV(utf-8-sig) 解析。模板用
    _find_template 自动裁定。导入底层异常统一包成 BenchError。

    :param db: 已打开的库。
    :type db: db.Database
    :param path: 表格文件路径。
    :type path: str
    :param template: 模板名，None = 自动裁定。
    :type template: str 或 None
    :param csv: 是否按 CSV 解析。
    :type csv: bool
    :return: (新建条数, 跳过条数, 未识别列名列表)。
    :rtype: tuple
    :raises BenchError: 文件不存在、模板缺失或导入失败时。
    """
    tpl = _find_template(template)
    if not os.path.exists(path):
        raise BenchError(f"文件不存在：{path}")
    fmt = "csv" if csv else "excel"
    try:
        created, skipped, unmapped = _importer.import_file(
            db, path, template=tpl, fmt=fmt)
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导入失败：{e}")
    return created, skipped, unmapped


# ---------- 导出路径自动命名（v3.9.0：接口仿照 db_analysis） ----------

def _safe(s):
    """文件名安全化（与 main.py / db_analysis 同一规则）。

    ``<>:"/\\|?*`` 替换为下划线，去掉首尾空格和点，空结果回退 "x"。

    :param s: 原始名字段。
    :type s: str
    :return: 安全化后的名字段。
    :rtype: str
    """
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" .") or "x"


def _resolve_out_dir(base, cmd="export"):
    """输出目录裁定（仿 db_analysis v3.5.2 规则）。

    裸参数(None) -> fields.json 同目录 exports/；显式目录不存在则自动
    创建；带扩展名的路径视为"想指定文件名"而拒绝（文件名一律自动命名）。

    :param base: 用户给的输出位置，None = 缺省 exports/。
    :type base: str 或 None
    :param cmd: 子命令名，用于报错提示用法。
    :type cmd: str
    :return: 已确保存在的输出目录。
    :rtype: pathlib.Path
    :raises BenchError: base 不是目录语义的路径时。
    """
    if base is None:
        dest = Path(_config.BASE_DIR) / "exports"
    else:
        base = str(base)
        if os.path.isfile(base) or (not os.path.isdir(base)
                                    and os.path.splitext(base)[1]):
            raise BenchError(
                f"输出只支持目录（文件名自动命名）：{base}\n"
                f"用法：{cmd} [目录] [--csv]；缺省目录 = exports/")
        dest = Path(base)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _cond_summary(closed=False, search=None, where=None):
    """筛选条件 -> 文件名摘要段（仿 db_analysis _cond_summary）。

    where 原样拼接，search 拼成 ``搜索=词1,词2``，含归档加"含归档"；
    无条件时返回 "全量"。整段过 _safe 安全化。

    :param closed: 是否含归档条件。
    :type closed: bool
    :param search: 关键词列表或字符串，None/空 = 无搜索条件。
    :type search: list 或 str 或 None
    :param where: 原始 where 字符串列表。
    :type where: list 或 None
    :return: 文件名条件摘要段。
    :rtype: str
    """
    parts = list(where or [])
    if search:
        kw = ",".join(search) if isinstance(search, (list, tuple)) \
            else str(search)
        parts.append(f"搜索={kw}")
    if closed:
        parts.append("含归档")
    return _safe("_".join(parts)) if parts else "全量"


def _sort_seg(sort, desc=False):
    """排序条件 -> 文件名段。

    :param sort: 排序列名，空/None = 无排序段。
    :type sort: str 或 None
    :param desc: 是否降序。
    :type desc: bool
    :return: 排序文件名段，无排序时为空串。
    :rtype: str
    """
    if not sort:
        return ""
    return _safe("sort-" + sort + ("_desc" if desc else ""))


def _export_path(dest, stem, conds, sort, desc, ext):
    """拼导出文件完整路径。

    ``stem_conds_sort段_时间戳.ext``，空段自动略去；时间戳精确到秒。

    :param dest: 输出目录。
    :type dest: pathlib.Path
    :param stem: 文件名主干（如 export_<模板> / weekly_<日期区间>）。
    :type stem: str
    :param conds: 条件摘要段。
    :type conds: str
    :param sort: 排序列名（可空）。
    :type sort: str 或 None
    :param desc: 是否降序。
    :type desc: bool
    :param ext: 扩展名（含点）。
    :type ext: str
    :return: 完整输出路径。
    :rtype: pathlib.Path
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    segs = [s for s in (stem, conds, _sort_seg(sort, desc), ts) if s]
    return dest / ("_".join(segs) + ext)


def cmd_export(db, out_dir, template=None, closed=False, search=None,
               where=None, sort=None, desc=False, csv=False):
    """批量导出内核（与 GUI 导出同语义，不受 limit 影响）。

    out_dir 只接受目录，文件名自动命名：
    ``export_<模板>_<筛选摘要>_<排序段>_<时间戳>.xlsx|csv``；默认 Excel，
    csv=True 出 CSV(utf-8-sig)。行集用 cmd_list（limit=None）取全量。

    :param db: 已打开的库。
    :type db: db.Database
    :param out_dir: 输出目录，None = 缺省 exports/。
    :type out_dir: str 或 None
    :param template: 导出模板名，None = 自动裁定。
    :type template: str 或 None
    :param closed: 是否含已完结项目。
    :type closed: bool
    :param search: 关键词列表。
    :type search: list 或 None
    :param where: --where 筛选列表。
    :type where: list 或 None
    :param sort: 排序列名，None = 配置默认。
    :type sort: str 或 None
    :param desc: 是否降序。
    :type desc: bool
    :param csv: 是否出 CSV。
    :type csv: bool
    :return: (导出行数, 输出文件路径)。
    :rtype: tuple
    :raises BenchError: 无可用模板或导出失败时。
    """
    dest = _resolve_out_dir(out_dir)
    rows, _ = cmd_list(db, closed=closed, search=search, where=where,
                       sort=sort, desc=desc, limit=None)
    tpl = _find_template(template)
    if tpl is None:
        raise BenchError("没有可用模板（fields.json 的 templates 段）")
    path = _export_path(dest, f"export_{_safe(tpl['name'])}", _cond_summary(
        closed, search, where), sort, desc, ".csv" if csv else ".xlsx")
    try:
        if csv:
            n = _exporter.export_csv(rows, str(path), tpl)
        else:
            n = _exporter.export_with_template(rows, str(path), tpl)
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导出失败：{e}")
    return n, str(path)


def _default_week_bounds():
    """本周/下周四个缺省日期边界（周一起算）。

    :return: (本周一起, 本周日止, 下周一起, 下周日止)，YYYY-MM-DD 格式。
    :rtype: tuple
    """
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    d = lambda x: x.strftime("%Y-%m-%d")      # noqa: E731
    return d(mon), d(mon + timedelta(days=6)), \
        d(mon + timedelta(days=7)), d(mon + timedelta(days=13))


def cmd_weekly(db, out_dir, d1=None, d2=None, p1=None, p2=None, csv=False):
    """周报导出内核（本周跟进 + 下周计划）。

    日期缺省 = 本周一~日 / 下周一~日；v3.9.0 起 out_dir 只接受目录，
    文件名自动命名 ``weekly_<跟进段>_<计划段>_<时间戳>.xlsx|csv``；CSV
    为单文件两段（本周跟进 / 下周计划，与 xlsx 两工作表对应）。无 weekly
    模板时内置一份四列默认模板。

    :param db: 已打开的库。
    :type db: db.Database
    :param out_dir: 输出目录，None = 缺省 exports/。
    :type out_dir: str 或 None
    :param d1: 跟进段起点，None = 本周一。
    :type d1: str 或 None
    :param d2: 跟进段终点，None = 本周日。
    :type d2: str 或 None
    :param p1: 计划段起点，None = 下周一。
    :type p1: str 或 None
    :param p2: 计划段终点，None = 下周日。
    :type p2: str 或 None
    :param csv: 是否出 CSV。
    :type csv: bool
    :return: (本周跟进条数, 下周计划条数, 输出文件路径)。
    :rtype: tuple
    :raises BenchError: 任一日期非法或导出失败时。
    """
    dest = _resolve_out_dir(out_dir, cmd="weekly")
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
    path = _export_path(dest, f"weekly_{d1}~{d2}_{p1}~{p2}",
                        "", None, False, ".csv" if csv else ".xlsx")
    try:
        if csv:
            nf, np_ = _exporter.export_weekly_csv(rows_f, rows_p, tpl,
                                                  str(path))
        else:
            nf, np_ = _exporter.export_weekly(rows_f, rows_p, tpl,
                                              str(path))
    except Exception as e:                    # noqa: BLE001
        raise BenchError(f"导出失败：{e}")
    return nf, np_, str(path)


# ---------- backup / notify ----------

def _safe_ident(s):
    """识别符文件名安全化（与 main.py 同一规则）。

    与 _safe 相同字符集替换，但空结果回退 "备份"（备份文件名语义）。

    :param s: 原始识别符。
    :type s: str
    :return: 安全化后的识别符。
    :rtype: str
    """
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" .") or "备份"


def backup_database(db, db_path):
    """库备份：SQLite 在线备份 + fields.json 同事件备份（v3.10.0 定）。

    备份目标 = fields.json 同目录下配置 backup.path（相对则拼
    BASE_DIR），文件名 ``时间戳-识别符-原库名``；fields.json 用
    config._CFG_PATH 源（含冻结模式向上找一级规则）同前缀同时戳复制，
    缺失时不报错——库备份照常完成，stderr 提示并返回 None。

    :param db: 已打开的库。
    :type db: db.Database
    :param db_path: 库文件路径（只取文件名入备份名）。
    :type db_path: str
    :return: (库备份路径, fields.json 备份路径或 None)。
    :rtype: tuple
    """
    import shutil
    import sys
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
    # v3.10.0：同一备份事件内追加复制 fields.json，与库备份同前缀
    # 同时戳，肉眼可配对。源路径取 config 的 _CFG_PATH（含冻结模式
    # 向上找一级的规则），不自己重算。
    json_target = None
    src = Path(getattr(_config, "_CFG_PATH",
                       Path(_config.BASE_DIR) / "fields.json"))
    if src.is_file():
        json_target = dest / f"{ts}-{ident}-fields.json"
        shutil.copy2(str(src), str(json_target))
    else:
        print(f"提示：未找到 fields.json（{src}），本次仅备份数据库",
              file=sys.stderr)
    return str(target), (str(json_target) if json_target else None)


def today_notify_text(db):
    """notify 子命令的数据：当天项目时间节点（终端打印版）。

    取当天全部 calendar_entries 中 date 恰为今天的项；为空返回固定提
    示文案，否则用 notifier.build_today_message 组标题 + 列表。不走
    toast，纯文本终端输出。

    :param db: 已打开的库。
    :type db: db.Database
    :return: 可直接打印的多行文本。
    :rtype: str
    """
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
    """按名称找收藏夹并返回其 id。

    :param db: 已打开的库。
    :type db: db.Database
    :param name: 收藏夹名。
    :type name: str
    :return: 收藏夹 id。
    :rtype: int
    :raises BenchError: 收藏夹不存在时。
    """
    for cid, cname, _n in db.list_collections():
        if cname == name:
            return cid
    raise BenchError(f"收藏夹不存在：{name}")


def cmd_fav_list(db):
    """列出全部收藏夹。

    :return: [(收藏夹名, 项目数, [项目 id, ...]), ...]。
    :rtype: list
    """
    return [(name, n, [r[0] for r in db.collection_items_detail(cid)])
            for cid, name, n in db.list_collections()]


def cmd_fav_new(db, name):
    """新建收藏夹。

    :param db: 已打开的库。
    :type db: db.Database
    :param name: 新收藏夹名（不允许重名）。
    :type name: str
    :return: 新收藏夹 id。
    :rtype: int
    :raises BenchError: 同名收藏夹已存在时。
    """
    for _cid, cname, _n in db.list_collections():
        if cname == name:
            raise BenchError(f"收藏夹已存在：{name}")
    return db.create_collection(name)


def cmd_fav_rename(db, old, new):
    """收藏夹重命名。

    :param db: 已打开的库。
    :type db: db.Database
    :param old: 现名。
    :type old: str
    :param new: 新名。
    :type new: str
    :raises BenchError: 现名不存在时。
    """
    db.collection_rename(_find_collection(db, old), new)


def cmd_fav_delete(db, name):
    """删除收藏夹。

    :param db: 已打开的库。
    :type db: db.Database
    :param name: 收藏夹名。
    :type name: str
    :raises BenchError: 收藏夹不存在时。
    """
    db.delete_collection(_find_collection(db, name))


def cmd_fav_add(db, name, ids):
    """把项目批量加入收藏夹。

    :param db: 已打开的库。
    :type db: db.Database
    :param name: 收藏夹名。
    :type name: str
    :param ids: 项目 id 列表。
    :type ids: list
    :raises BenchError: 收藏夹不存在或任一项目不存在时。
    """
    cid = _find_collection(db, name)
    for pid in ids:
        _require_project(db, pid)
    db.collection_add(cid, ids)


def cmd_fav_remove(db, name, ids):
    """把项目批量移出收藏夹。

    :param db: 已打开的库。
    :type db: db.Database
    :param name: 收藏夹名。
    :type name: str
    :param ids: 项目 id 列表。
    :type ids: list
    :raises BenchError: 收藏夹不存在时。
    """
    cid = _find_collection(db, name)
    for pid in ids:
        db.collection_remove(cid, pid)


# ---------- cal（只读打印） ----------

def cmd_cal(db, year, month=None, day=None):
    """年/月/日的时间节点清单（只读）。

    返回按日期排序的元组列表；project_id 供 show/follow 接续使用。

    :param db: 已打开的库。
    :type db: db.Database
    :param year: 年，如 2026。
    :type year: int
    :param month: 月，None = 全年逐月汇总。
    :type month: int 或 None
    :param day: 日，None = 不限；给出时按月过滤后再按日过滤。
    :type day: int 或 None
    :return: [(日期, 节点类型中文标签, 文本, project_id), ...]。
    :rtype: list
    """
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
    """字符串显示宽度：东亚宽字符/全角 = 2，其余 = 1。

    :param s: 待测字符串。
    :type s: str
    :return: 显示宽度。
    :rtype: int
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in s)


def _pad(s, w):
    """按显示宽度右补空格到指定宽度（不足才补）。

    :param s: 原字符串。
    :type s: str
    :param w: 目标显示宽度。
    :type w: int
    :return: 补齐后的字符串（显示宽度 >= w）。
    :rtype: str
    """
    return s + " " * max(0, w - _disp_w(s))


def format_table(rows, cols, heads):
    """把行列表渲染成对齐文本表格。

    列间两空格，全角按 2 宽对齐；无数据时输出只有表头和分隔线。NULL
    显示为空串。

    :param rows: 行 dict 列表（sqlite3.Row 亦可，按列名取值）。
    :type rows: list
    :param cols: 列名顺序。
    :type cols: list
    :param heads: {列名: 中文表头}。
    :type heads: dict
    :return: 多行文本表格（换行连接，无尾随换行）。
    :rtype: str
    """
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
    """把行列表渲染成 CSV 文本。

    列序与表头同 format_table；lineterminator 固定 ``\\n``，NULL 输出
    空字段；返回文本不带尾随换行。

    :param rows: 行 dict 列表。
    :type rows: list
    :param cols: 列名顺序。
    :type cols: list
    :param heads: {列名: 中文表头}。
    :type heads: dict
    :return: CSV 文本。
    :rtype: str
    """
    import io as _io
    buf = _io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([heads[c] for c in cols])
    for r in rows:
        writer.writerow(["" if r.get(c) is None else r.get(c, "")
                         for c in cols])
    return buf.getvalue().rstrip("\n")
