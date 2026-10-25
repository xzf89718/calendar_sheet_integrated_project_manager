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


class Config:
    def __init__(self, path=None):
        with open(path or _CFG_PATH, encoding="utf-8") as f:
            data = json.load(f)
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
            self.display.append((name, e.get("alias") or default_head,
                                 bool(e.get("on", True))))
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
