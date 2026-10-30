# -*- coding: utf-8 -*-
"""配置加载：fields.json 定义表格内容，启动时读取，运行期不变。

改配置的流程：关闭软件 -> 编辑 fields.json -> 启动软件。
程序启动时会自动核对数据库表结构，缺的列自动补上。
"""
import json
import os
import sys

# 基础目录：开发时 = 代码所在目录；PyInstaller 打包后 = exe 所在目录。
# fields.json / 数据库 / 备份等一切数据文件都锚到这里，
# 保证"exe 旁边放 JSON、旁边长数据库"的目标形态在两种模式下一致。
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 唯一的配置文件：基础目录的 fields.json
# 主程序与 db_copy / db_append 等子模块共用这一份。
# 冻结模式下若 exe 在子目录（如 dist/db_copy/），向上找一级共享根目录的配置。
_CFG_PATH = os.path.join(BASE_DIR, "fields.json")
if getattr(sys, "frozen", False) and not os.path.exists(_CFG_PATH):
    _up = os.path.join(os.path.dirname(BASE_DIR), "fields.json")
    if os.path.exists(_up):
        _CFG_PATH = _up


# 字段类型全集（fields.json 的 type 只允许这些）
KNOWN_TYPES = ("date", "int", "float", "text", "choice", "status")

# 日历法定四类：start/followup/close 绑定日期字段，append 是周报模式的
# 追加记录（无字段）。这四个不可增删、key 不可改，只能配置 label、
# color 与 show_calendar/show_table 显示开关；自定义日期类别往后追加。
CORE_DATE_KEYS = ("start", "followup", "close")
CORE_APPEND_KEY = "append"
CORE_CALENDAR_KEYS = CORE_DATE_KEYS + (CORE_APPEND_KEY,)


def validate_config_data(data):
    """fields.json 配置校验（v2.6.0 配置校验器）。

    纯函数：不读文件、不抛异常，返回错误消息列表（空 = 通过）。
    校验项：
      1. fields 段：非空、name 不重复、type 合法；
      2. 必须有一个 type=status 的字段（归档联动依赖它），且只能有一个；
      3. status_closed 段必须在（允许是空数组 []）；
      4. calendar_dates：start/followup/close/append 法定四类必须在
         （旧式 fields.calendar 标记的配置除外，会自动转换），key 不重复，
         三类日期字段必须绑定 date 类型字段，append 不应绑定字段，
         自定义类别必须绑定未被占用的 date 字段；
      5. date_check 段（可缺省）：fields 里必须是已配置的 date 字段；
      6. 周报模板（kind=weekly）的 columns 不能为空；
      7. favorites 段（可缺省）：enabled 必须是布尔，label 必须非空。
    """
    errs = []
    if not isinstance(data, dict):
        return ["fields.json 的根节点必须是 JSON 对象"]

    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        errs.append("fields 段缺失或为空（至少需要一个字段）")
        fields = []
    names, ftypes = set(), {}
    for i, f in enumerate(fields):
        if not isinstance(f, dict) or not f.get("name"):
            errs.append(f"fields 第 {i + 1} 项缺少 name")
            continue
        n = f["name"]
        if n in names:
            errs.append(f"fields 里字段名重复：{n}")
        names.add(n)
        ftypes[n] = f.get("type")
        if f.get("type") not in KNOWN_TYPES:
            errs.append(
                f"字段 {n} 的 type 无效：{f.get('type')!r}"
                f"（可选：{'/'.join(KNOWN_TYPES)}）")

    # status：必须有（归档联动依赖它），且全程序只能有一个
    st = [f["name"] for f in fields
          if isinstance(f, dict) and f.get("type") == "status"]
    if not st:
        errs.append("fields 里必须有一个 type=status 的字段"
                    "（「显示已关闭」归档联动依赖它）")
    elif len(st) > 1:
        errs.append(f"type=status 的字段只能有一个，现在有 {len(st)} 个：{st}")

    # status_closed：段必须在，允许为空数组
    if "status_closed" not in data:
        errs.append("缺少 status_closed 段（允许空数组 []，但段必须在）")
    elif not isinstance(data["status_closed"], list):
        errs.append("status_closed 必须是数组")

    # calendar_dates：新格式严格校验；旧格式（fields 的 calendar 标记）
    # 由 Config 自动转换，这里不拦
    cd = data.get("calendar_dates")
    legacy = cd is None and any(
        isinstance(f, dict) and f.get("calendar")
        for f in fields)
    if cd is None:
        if not legacy:
            errs.append("calendar_dates 段缺失（法定四类 "
                        "start/followup/close/append 必须配置）")
    else:
        if not isinstance(cd, list) or not cd:
            errs.append("calendar_dates 段为空")
            cd = []
        keys = []
        for e in cd:
            if not isinstance(e, dict) or not e.get("key"):
                errs.append("calendar_dates 里每项都必须有 key")
                continue
            keys.append(e["key"])
        for k in sorted({k for k in keys if keys.count(k) > 1}):
            errs.append(f"calendar_dates 的 key 重复：{k}")
        for req in CORE_CALENDAR_KEYS:
            if req not in keys:
                errs.append(
                    f"calendar_dates 缺少法定类别：{req}"
                    f"（start/followup/close/append 四类必须有，不可增删）")
        core_fields = {e.get("field")
                       for e in cd
                       if isinstance(e, dict)
                       and e.get("key") in CORE_DATE_KEYS}
        for e in cd:
            if not isinstance(e, dict):
                continue
            k, fld = e.get("key"), e.get("field")
            if k in CORE_DATE_KEYS:
                # 法定三类：必须绑定 date 字段（绑定本身属于结构，模板已给定）
                if not fld:
                    errs.append(f"calendar_dates 的 {k} 必须绑定日期字段")
                elif fld not in ftypes:
                    errs.append(f"calendar_dates 的 {k} 指向不存在的字段：{fld}")
                elif ftypes[fld] != "date":
                    errs.append(
                        f"calendar_dates 的 {k} 绑定的字段必须是 date 类型：{fld}")
            elif k == CORE_APPEND_KEY:
                if fld:
                    errs.append("calendar_dates 的 append 是周报追加记录"
                                "（无字段），不应写 field")
            else:  # 自定义日期类别
                if not fld:
                    errs.append(f"自定义日历类别 {k} 必须绑定日期字段（field）")
                elif fld not in ftypes or ftypes[fld] != "date":
                    errs.append(
                        f"自定义日历类别 {k} 必须绑定 date 类型字段：{fld}")
                elif fld in core_fields:
                    errs.append(
                        f"自定义日历类别 {k} 绑定的字段已被法定类别占用：{fld}")

    # date_check：保存跟进时的日期范围检查器（可缺省）
    dc = data.get("date_check")
    if dc is not None:
        if not isinstance(dc, dict):
            errs.append("date_check 必须是对象（{enabled, fields}）")
        else:
            for fn in dc.get("fields", []):
                if fn not in ftypes:
                    errs.append(f"date_check.fields 里有不存在的字段：{fn}")
                elif ftypes[fn] != "date":
                    errs.append(f"date_check.fields 里必须是 date 类型：{fn}")

    # favorites：收藏夹功能开关（可缺省，缺省 = 关闭）
    fav = data.get("favorites")
    if fav is not None:
        if not isinstance(fav, dict):
            errs.append("favorites 必须是对象（{enabled, label}）")
        else:
            if not isinstance(fav.get("enabled"), bool):
                errs.append("favorites.enabled 必须是 true/false")
            if not isinstance(fav.get("label"), str) \
                    or not fav.get("label", "").strip():
                errs.append("favorites.label 必须是非空字符串"
                            "（按钮/面板显示名）")

    # 周报模板：columns 不能为空（周报模式只读，列集合即模板本体）
    for t in data.get("templates", []) or []:
        if isinstance(t, dict) and t.get("kind") == "weekly":
            if not t.get("columns"):
                errs.append(f"周报模板「{t.get('name', '?')}」的 columns 不能为空"
                            f"（周报模式：列的 label 可改，列不可增删）")
    # recycle_bin：回收站开关（v3.1.0，可缺省 = 关闭）。
    # 关闭时删除为物理删除（与 v2.7.3 等价）；开启后删除 = 整行搬进
    # 独立回收表（主程序所有查询天然不命中），恢复/彻底删除由
    # db_recycled.py（命令行 + GUI）负责。
    rb = data.get("recycle_bin")
    if rb is not None:
        if not isinstance(rb, dict):
            errs.append("recycle_bin 必须是对象（{enabled}）")
        elif not isinstance(rb.get("enabled"), bool):
            errs.append("recycle_bin.enabled 必须是 true/false")
    return errs


class Config:
    def __init__(self, path=None):
        with open(path or _CFG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # 配置校验器（v2.6.0）：启动即全量核对 fields.json，错误逐条列出
        errors = validate_config_data(data)
        if errors:
            raise ValueError("fields.json 配置错误：\n- "
                             + "\n- ".join(errors))
        # 加载即剔除所有 "_" 开头的键（JSON 里的注释约定），保证它们
        # 只存在于文件里，程序内任何路径都接触不到
        self.fields = [{k: v for k, v in f.items() if not k.startswith("_")}
                       for f in data["fields"]]
        self.status_closed = data["status_closed"]
        # 产品名与数据库文件名（换产品只改 JSON）
        self.product_name = data.get("product_name", "销售项目跟进")
        self.db_name = data.get("db_name", "sales_pm.db")
        # 导入时状态为空的默认赋值（None = 不兜底，保持空）
        self.import_default_status = data.get("import_default_status")
        self.ui = data.get("ui", {})
        self.window = self.ui.get("window", {})
        self.font = self.ui.get("font", {})
        self.col_ui = self.ui.get("columns", {})
        self.cal_ui = self.ui.get("calendar", {})
        # 日历类别显示名，键 = 字段上的 "calendar" 标记值
        self.cal_labels = self.ui.get(
            "calendar_labels",
            {"start": "开始", "followup": "跟进", "close": "关闭"})
        self.editor_ui = self.ui.get("editor", {})
        # 字段级列宽提示（px）， fit_columns 会以此为基准再按内容伸缩
        self.field_width = {f["name"]: f.get("width")
                            for f in self.fields if f.get("width")}
        # 字段级默认值：编辑器新建预填、导入补空、导出补空，三处共用
        self.field_defaults = {f["name"]: f["default"]
                               for f in self.fields
                               if f.get("default") not in (None, "")}
        # 详情页限高行数：配置了 max_lines 的文本字段在详情页以
        # 固定行数 + 滚动条显示，不再无限撑高
        self.max_lines = {f["name"]: int(f["max_lines"])
                          for f in self.fields if f.get("max_lines")}
        # 常用派生视图
        self.names = [f["name"] for f in self.fields]
        self.labels = {f["name"]: f["label"] for f in self.fields}
        # 主界面显示配置：独立的 display_mainsheet 段，每项 {name原名,
        # alias别名, on开关}，数组顺序即列顺序；alias 空 = 用字段默认显示名。
        # 未配置 = ID 打头 + 全部字段按序全开。
        # 数据层永远全量——这里只管"看什么、叫什么、什么顺序"。
        disp = data.get("display_mainsheet")
        if disp is None:
            entries = [{"name": "id", "alias": "ID", "on": True}]
            entries += [{"name": f["name"], "alias": "", "on": True}
                        for f in self.fields]
        else:
            entries = [dict(e) for e in disp]
            listed = {e["name"] for e in entries}
            for f in self.fields:    # display 里没写的新字段自动补尾
                if f["name"] not in listed:
                    entries.append({"name": f["name"], "alias": "",
                                    "on": True})
        self.display = []            # [(name, 表头名, 是否显示)]
        for e in entries:
            name = e["name"]
            if name != "id" and name not in self.labels:
                raise ValueError(
                    f"display_mainsheet 段里有不存在的字段名：{name}"
                    f"（fields.json 的 fields 里没有这个名字）")
            default_head = "ID" if name == "id" else self.labels[name]
            on = bool(e.get("on", True))
            self.display.append((name, e.get("alias") or default_head, on))
        # 主界面列（含开关过滤）：[(name, 表头)]
        self.display_cols = [(n, h) for n, h, on in self.display if on]
        # 每列筛选类型："range"(区间)/"list"(勾选清单，默认)
        self.col_filter_type = {e["name"]: e.get("filter", "list")
                                for e in (data.get("display_mainsheet") or [])
                                if e.get("filter")}
        # 日历渲染模式："all"(当月全部，默认) / "filtered"(跟随表格筛选)
        self.calendar_mode = data.get("calendar_mode", "all")
        # 日历日期类别（v2.5.0 全配置化，本软件特色：一个项目多个日期）：
        # 法定四个：start/followup/close（各绑定一个日期字段）+ append
        # （追加记录，无字段，用快照时间）；此后可继续加任意日期字段。
        # 每项：key=类别标识，field=日期字段名（append 不写），
        #      label=显示名，color=#RRGGBB。
        cd = data.get("calendar_dates")
        if cd is None:
            # 旧式配置自动转换：fields 的 calendar 标记 + calendar_labels
            labels = self.ui.get("calendar_labels", {})
            base = {"start": "#2e7d32", "followup": "#1565c0",
                    "close": "#c62828", "append": "#6a1b9a"}
            cd = [{"key": f["calendar"], "field": f["name"],
                   "label": labels.get(f["calendar"], f["calendar"]),
                   "color": base[f["calendar"]]}
                  for f in self.fields
                  if f.get("calendar") in ("start", "followup", "close")]
            cd.append({"key": "append",
                       "label": labels.get("append", "追加"),
                       "color": base["append"]})
        keys = [e.get("key") for e in cd]
        for req in ("start", "followup", "close"):
            if req not in keys:
                raise ValueError(
                    f"calendar_dates 缺少法定类别：{req}"
                    f"（start/followup/close/append 必须有）")
        for e in cd:
            if e["key"] == "append":
                continue
            f = e.get("field")
            fd = next((x for x in self.fields if x["name"] == f), None)
            if fd is None or fd["type"] != "date":
                raise ValueError(
                    f"calendar_dates 的 {e['key']} 指向无效日期字段：{f}")
        # [(key, field 或 None, label, color)]
        self.calendar_dates = [
            (e["key"], e.get("field"), e.get("label", e["key"]),
             e.get("color", "#333333")) for e in cd]
        # 每个类别"在日历里显示与否"的开关（v2.6.0）：
        # show_calendar=false 则该日期不上日历；表格显隐与列顺序由
        # display_mainsheet 段负责，这里不重复管。缺省显示。
        self.calendar_show = {e["key"]: bool(e.get("show_calendar", True))
                              for e in cd}
        # 保存跟进时的日期范围检查器（v2.6.0，date_check 段，可缺省）：
        # 被检日期必须落在 [开始日期, 关闭日期] 内；边界字段取自
        # calendar_dates 的 start/close 绑定，某侧为空则该侧不检。
        dc = data.get("date_check") or {}
        self.date_check_enabled = bool(dc.get("enabled", False))
        self.date_check_fields = [f for f in dc.get("fields", [])
                                  if f in self.labels]

        # 收藏夹功能开关（v2.7.0，favorites 段，可缺省 = 关闭）。
        # 只控制 GUI 是否出现收藏夹按钮与是否建表；数据仍是 db 里的
        # 纯索引（collections/collection_items）。
        fav = data.get("favorites") or {}
        self.favorites_enabled = bool(fav.get("enabled", False))
        self.favorites_label = str(fav.get("label") or "收藏夹")
        # 回收站开关（v3.1.0）：默认关闭 = 删除仍是物理删除
        rb = data.get("recycle_bin") or {}
        self.recycle_bin_enabled = bool(rb.get("enabled", False))
        bound = {k: f for k, f, _l, _c in self.calendar_dates}
        self.date_check_bounds = (bound.get("start"), bound.get("close"))
        # 表格渲染上限（v2.0 懒渲染）：筛选+排序全量进行，仅显示前 N 条，
        # 数据层（导出/日历/周报/备份/写入）不受影响
        self.render_limit = int(self.ui.get("render_limit", 600))
        # 默认排序（跟进表模式）：JSON 配置；读取不到或列名有误时
        # 退路 = 按 id 倒序（最新的在最上面），保证不报错
        ds = data.get("default_sort")
        col, desc = "id", True
        if isinstance(ds, dict):
            c = str(ds.get("column", "")).strip()
            if c == "id" or c in self.labels:
                col, desc = c, bool(ds.get("desc", True))
        self.default_sort = {"column": col, "desc": desc}
        # db_split 输出文件名配方：组成部分及顺序可配 + 自定义前缀
        sp = data.get("split", {})
        self.split_components = sp.get(
            "components", ["field", "key", "time"])
        self.split_prefix = str(sp.get("prefix", ""))
        # 项目名组合字段：按此顺序用各字段值拼接（空值跳过），JSON 可配
        self.name_fields = [n for n in data.get(
            "name_fields", ["manufacturer", "customer", "product"])
            if n in self.names]
        # 搜索框匹配的字段范围（默认全字段）
        self.search_fields = data.get("search", {}).get(
            "fields", self.names)
        # 周报模式下方表格的列（内置列 + 字段名）
        self.weekly_cols = data.get("weekly_sheet", {}).get(
            "columns", ["snapshot_at", "project", "change_summary"])
        # 备份配置：目录 + 文件名识别符
        self.backup = data.get("backup", {})
        self.date_fields = [f["name"] for f in self.fields
                            if f["type"] == "date"]
        self.int_fields = [f["name"] for f in self.fields
                           if f["type"] == "int"]
        self.float_fields = [f["name"] for f in self.fields
                             if f["type"] == "float"]
        self.choice_fields = {f["name"]: f.get("choices", [])
                              for f in self.fields if f["type"] == "choice"}
        self.status_field = next(f["name"] for f in self.fields
                                 if f["type"] == "status")
        self.status_options = next(f["choices"] for f in self.fields
                                   if f["type"] == "status")
        self.multiline = {f["name"]: f.get("height", 5)
                          for f in self.fields if f.get("multiline")}
        # 日历用的时间节点字段：{"start": "start_date", "followup": ..., ...}
        self.calendar = {f["calendar"]: f["name"] for f in self.fields
                         if f.get("calendar")}
        # 导入表头匹配：显示名 或 字段名 -> 字段名（精确匹配，不做模糊别名）
        self.header_map = {}
        for f in self.fields:
            self.header_map[f["label"]] = f["name"]
            self.header_map[f["name"]] = f["name"]
        # 导入/导出模板：columns 展开成 [(表头, 字段名或None, 固定值或None)]
        # kind="weekly" 为周报模板：列为 date/name/field 三种特殊键
        self.templates = []
        for t in data.get("templates", []):
            if t.get("kind") == "weekly":
                cols = []
                for c in t["columns"]:
                    if "date" in c:                 # 追加时间列
                        cols.append((c.get("label", "日期"), "__date__", None))
                    elif c.get("name"):             # 项目名列（name_fields 组合）
                        cols.append((c.get("label", "项目"), "__name__", None))
                    elif "field" in c:
                        cols.append((c.get("label", c["field"]),
                                     c["field"], None))
                self.templates.append({
                    "name": t["name"], "kind": "weekly", "columns": cols,
                })
                continue
            cols = []
            if t["columns"] == "all":
                cols = [(f["label"], f["name"], None) for f in self.fields]
            else:
                for c in t["columns"]:
                    if "field" in c:
                        name = c["field"]
                        # 模板可自定义表头名（如"成功概率"），不写用字段默认名
                        label = c.get("label", self.labels.get(name, name))
                        cols.append((label, name, None))
                    else:      # 不在库里的列：导出填 const，导入忽略
                        cols.append((c["label"], None, c.get("const", "")))
            self.templates.append({
                "name": t["name"],
                "columns": cols,
                # 导入时的固定赋值：{"字段名": "值"}，模板里没有这些列
                "defaults": t.get("defaults", {}),
            })


CFG = Config()
