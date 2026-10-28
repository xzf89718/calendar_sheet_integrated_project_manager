# -*- coding: utf-8 -*-
"""入口：项目管理主窗口 = 项目列表 + 嵌入的通用日历。

三层各自独立：
  db.py           数据库层
  calendar_gui.py 通用日历（可被日程排布软件复用）
  editor/reader   编辑与阅读 UI
"""
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from db import Database, SNAPSHOT_FIELDS
from editor import LABELS
from config import CFG
from calendar_gui import CalendarWidget
from editor import SnapshotEditor
from reader import ProjectReader


class MainApp(tk.Tk):
    def __init__(self, db_path=None):
        super().__init__()
        if db_path is None:
            # 数据库锚定基础目录（开发=代码目录；打包=exe 目录）
            from config import BASE_DIR
            db_path = os.path.join(BASE_DIR, CFG.db_name)
        self.db_path = db_path
        # 已有 db 文件：必须能用，不能用就报错退出
        if os.path.exists(self.db_path):
            try:
                self.db = Database(self.db_path)
                self.db.conn.execute(
                    "SELECT 1 FROM projects LIMIT 1").fetchone()
            except Exception as e:                  # noqa: BLE001
                messagebox.showerror(
                    "数据库错误",
                    f"已有db文件，但无法使用：\n{e}")
                self.destroy()
                raise SystemExit(1)
        else:
            self.db = Database(self.db_path)
        self.title(CFG.product_name)
        self._base_title = CFG.product_name   # 收藏夹模式时标题栏追加夹名
        # 窗口按屏幕自适应：留边距，保证底部按钮一启动就可见（尺寸可配置）
        win = CFG.window
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(
            f"{min(win.get('width', 1480), sw - win.get('margin_x', 80))}"
            f"x{min(win.get('height', 860), sh - win.get('margin_y', 120))}")
        self.show_closed = False
        self._setup_fonts()

        self.mode = "followup"        # followup=跟进表(默认) / weekly=周报
        # 收藏夹模式（v2.7.0）：fav_ids=None 未开启；否则为当前收藏夹的
        # 项目 id 集合。纯视图筛选 —— 数据模型不知道它的存在，
        # 只是 _query_kwargs 给现有筛选接口多传一组 id。
        self.fav_ids = None
        self.fav_coll = None          # (collection_id, name)
        # ---- 上半：通用日历 ----
        self.cal = CalendarWidget(
            self,
            get_entries=self._cal_entries,
            on_entry_click=self._open_project,   # 点条目 -> 看项目
            on_day_click=self._open_day,         # 点日期/还有N条 -> 当天明细
            max_per_day=CFG.cal_ui.get("max_per_day", 1),
            colors=_kind_colors(),               # 类别颜色：calendar_dates 配置
        )
        self.cal.pack(fill="x", padx=8, pady=8)

        # ---- 按钮行：先于列表打包，保证任何情况下底部按钮都在 ----
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        self.new_btn = tk.Button(btns, text="新建项目",
                                 command=self._new_project)
        self.new_btn.pack(side="left", padx=4)
        self.import_btn = tk.Button(btns, text="导入Excel",
                                    command=self._import)
        self.import_btn.pack(side="left", padx=4)
        self.export_btn = tk.Button(btns, text="导出Excel",
                                    command=self._export)
        self.export_btn.pack(side="left", padx=4)
        tk.Button(btns, text="查看/跟进",
                  command=self._open_selected).pack(side="left", padx=4)
        self.closed_btn = tk.Button(btns, text="显示已关闭",
                                    command=self._toggle_closed)
        self.closed_btn.pack(side="left", padx=4)
        tk.Button(btns, text="清除筛选",
                  command=self._clear_filters).pack(side="left", padx=4)
        # 收藏夹（v2.7.0，仅 fields.json 的 favorites.enabled=true 显示）
        if CFG.favorites_enabled:
            self.fav_var = tk.StringVar()
            self.fav_btn = tk.Button(btns, text=CFG.favorites_label,
                                     command=self._open_favorites)
            self.fav_btn.pack(side="left", padx=4)
            # 模式横幅（状态 + 移出 + 退出）建在分页行里，与
            # "共 N 条"同一行（v2.7.2）：小窗口下不会像独立一行那样
            # 被挤出可视区。默认不打包，进入模式时显示
            self.bind("<Control-KeyPress>", self._fav_hotkey)
        tk.Button(btns, text="今日推送",
                  command=self._notify_now).pack(side="left", padx=4)
        tk.Button(btns, text="刷新",
                  command=self.reload).pack(side="left", padx=4)
        tk.Button(btns, text="备份",
                  command=self._backup).pack(side="left", padx=4)
        # 模式切换 + 周报导出（v1.4.0）
        self.mode_btn = tk.Button(btns, text="周报模式",
                                  command=self._toggle_mode)
        self.mode_btn.pack(side="left", padx=4)
        self.wk_export_btn = tk.Button(btns, text="导出周报",
                                       command=self._export_weekly)
        self.wk_export_btn.pack(side="left", padx=4)
        self.wk_export_btn.config(state="disabled")
        # 搜索按钮（最右）：点击弹出输入框，弹框开在按钮左侧
        self.search_btn = tk.Button(btns, text="搜索",
                                    command=self._open_search)
        self.search_btn.pack(side="right", padx=4)
        self.search_var = tk.StringVar()
        # 防抖：停手 300ms 后才过滤。输入法合成期间界面不动，
        # 避免 Tk+中文IME 的合成串被重绘打断（按"-"吐出旧文字的病根）
        self._search_after = None
        self._search_popup = None
        self.search_var.trace_add("write", self._search_changed)
        # 提示单独一行，放在按钮行下方（保留引用：收藏夹横幅要插在
        # 它前面，保证小窗口下横幅不被挤出可视区——v2.7.2 修复）
        self.hint_lbl = tk.Label(
            self, text="提示: 左键表头=排序  右键表头=筛选  "
                       "搜索=多关键词空格分隔(AND)",
            fg="#888888", anchor="w")
        self.hint_lbl.pack(fill="x", padx=12)
        self._build_list()      # 列表区（cols/tree/滚动条/启动加载/通知）

    def _search_changed(self, *_a):
        if self._search_after is not None:
            self.after_cancel(self._search_after)
        self._search_after = self.after(300, self._do_search)

    def _do_search(self):
        self._search_after = None
        self.reload()
        self._update_search_btn()

    def _open_search(self):
        """搜索弹框：开在搜索按钮左侧，输入即过滤，关掉后条件保留。"""
        if self._search_popup is not None and \
                self._search_popup.winfo_exists():
            self._search_popup.lift()
            return
        self._search_popup = SearchPopup(self, self.search_btn,
                                         self.search_var)
        self._update_search_btn()

    def _update_search_btn(self):
        term = self.search_var.get().strip()
        self.search_btn.config(text=f"搜索:{term}" if term else "搜索")

    def _build_list(self):
        # ---- 下半：项目列表（最后打包，吃掉剩余全部空间） ----
        bottom = tk.Frame(self)
        bottom.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # 显示列：由 fields.json 的 display_mainsheet 段决定（原名/别名/
        # 开关/顺序）。底层数据仍是全量字段，导出不受显示配置影响
        self.cols = tuple(n for n, _h in CFG.display_cols)
        self.heads = {n: h for n, h in CFG.display_cols}
        # Excel 式筛选状态：每列一个选中值集合，None = 该列不筛选
        self.col_filters = {c: None for c in self.cols}
        # 表格区：纵横向滚动条，列宽固定不压缩
        area = tk.Frame(bottom)
        self.tree = ttk.Treeview(area, columns=self.cols, show="headings",
                                 selectmode="browse", height=6)
        # 默认单选；收藏夹面板打开期间临时改为多选（Ctrl/Shift，
        # 批量加入收藏夹用），面板关闭即恢复。单项目操作取第一个
        # 选中项（_selected_id）
        for c in self.cols:
            self.tree.heading(c, text=self.heads[c],
                              command=lambda cc=c: self._sort(cc))
            self.tree.column(c, width=110, minwidth=60, stretch=False)
        ysb = ttk.Scrollbar(area, orient="vertical",
                            command=self.tree.yview)
        xsb = ttk.Scrollbar(bottom, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set,
                            xscrollcommand=xsb.set)
        # v2.1 翻页式：第 X~Y/共 N 提示 + 上/下一页（恒定每页渲染量）。
        # v2.7.3：翻页行（共N条/上下页/收藏夹横幅）第一个打包且锚定
        # 底部（side="bottom"）——高度先于表格被保证，窗口纵向紧张时
        # 表格少显示几行（可滚动），最底行永不被吞；位置仍在表格下方
        lrow = tk.Frame(bottom)
        lrow.pack(side="bottom", fill="x", pady=(2, 0))
        self.limit_lbl = tk.Label(lrow, text="", fg="#8d6e00", anchor="w")
        self.limit_lbl.pack(side="left")
        # 收藏夹模式横幅：分页行的子部件，排在"共 N 条"左边
        if CFG.favorites_enabled:
            self.fav_banner = tk.Frame(lrow)
            self.fav_state_lbl = tk.Label(self.fav_banner,
                                          textvariable=self.fav_var,
                                          fg="#8d6e00", anchor="w")
            self.fav_state_lbl.pack(side="left", padx=(0, 8))
            # 移出：把主表格选中项目从当前夹剔除（只删索引，v2.7.2）；
            # 周报模式下禁用（与面板"加入"一致）
            self.fav_remove_btn = tk.Button(
                self.fav_banner, text="移出",
                command=self._fav_remove_selected)
            self.fav_remove_btn.pack(side="left", padx=4)
            self.fav_exit_btn = tk.Button(
                self.fav_banner, text=f"退出{CFG.favorites_label}",
                command=self._exit_favorites)
            self.fav_exit_btn.pack(side="left", padx=4)
        # 滚动条先占位，否则被可伸展的表格挤成零宽/零高
        xsb.pack(fill="x")
        area.pack(fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._open_selected())
        self.tree.bind("<Button-3>", self._header_menu)  # 右键表头=筛选
        self.next_btn = tk.Button(lrow, text="下一页 ▼", state="disabled",
                                  command=self._load_more)
        self.next_btn.pack(side="right")
        self.prev_btn = tk.Button(lrow, text="▲ 上一页", state="disabled",
                                  command=self._load_prev)
        self.prev_btn.pack(side="right", padx=4)
        self.sort_col = None
        self.sort_reverse = False
        self.render_offset = 0
        # 默认排序：JSON 的 default_sort（读不到/有误时 config 已兜底为 id 倒序）
        self.sort_col = CFG.default_sort["column"]
        self.sort_reverse = CFG.default_sort["desc"]
        self._refresh_headings()
        self.reload()          # 启动即加载数据

        # Windows 通知：启动后推一次当天事项，之后每 30 分钟检查跨天
        self._last_notify_date = None
        # 日期哨兵（主程序自带，独立于通知）：每分钟检查今天是否变化，
        # 变了就翻新日历——开着过夜也能自动翻到新日期
        self._last_seen_date = None
        self.after(60 * 1000, self._date_watch_loop)
        self.after(1500, self._notify_today)
        self.after(30 * 60 * 1000, self._notify_loop)

    # ---------- 通知 ----------
    def _today_entries(self):
        from datetime import date
        t = date.today()
        return [e for e in self.db.calendar_entries(t.year, t.month)
                if e["date"] == t.isoformat()]

    def _push(self, entries):
        import notifier
        if not entries:
            return notifier.notify("今日项目事项", ["今天没有项目时间节点"])
        title, lines = notifier.build_today_message(entries)
        return notifier.notify(title, lines)

    def _notify_today(self):
        self._push(self._today_entries())
        from datetime import date
        self._last_notify_date = date.today()

    def _notify_loop(self):
        """每 30 分钟：跨天时重新推送当天事项。"""
        from datetime import date
        if date.today() != self._last_notify_date:
            self._notify_today()
        self.after(30 * 60 * 1000, self._notify_loop)

    def _date_watch_loop(self):
        """日期哨兵（主程序自带，与通知完全独立）：每分钟检查今天
        是否变化，变化即翻新日历——今天高亮移动，跨月时月视图一起
        翻过去。开着软件过夜，第二天日历自动是新日期。"""
        from datetime import date
        today = date.today()
        if today != self._last_seen_date:
            self._last_seen_date = today
            if (self.cal.year, self.cal.month) != (today.year, today.month):
                self.cal.year, self.cal.month = today.year, today.month
            self.cal.refresh()
        self.after(60 * 1000, self._date_watch_loop)

    def _notify_now(self):
        """按钮：立即推送（兼作测试）。"""
        import notifier
        if not self._push(self._today_entries()):
            messagebox.showinfo(
                "通知未送达",
                "推送需要 Windows 通知库，请安装一次：\n\n"
                "    pip install windows-toasts\n\n"
                "安装后重启软件即可。", parent=self)

    # ---------- 备份 ----------
    @staticmethod
    def _safe_ident(s):
        """识别符文件名安全化：替换各系统非法字符，去首尾空格和点。"""
        for ch in '<>:"/\\|?*':
            s = s.replace(ch, "_")
        return s.strip(" .") or "备份"

    def _backup(self):
        """数据库备份：SQLite 在线备份 API（一致性快照）。

        文件名：时间(精确到秒)-识别符-数据库文件名
        路径与识别符在 fields.json 的 backup 段配置。
        """
        import sqlite3
        from datetime import datetime
        from pathlib import Path
        cfg = CFG.backup
        dest = Path(cfg.get("path", "backups")).expanduser()
        if not dest.is_absolute():                # 相对路径 -> 基础目录下
            from config import BASE_DIR
            dest = Path(BASE_DIR) / dest
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("备份失败",
                                 f"无法创建备份目录：\n{e}", parent=self)
            return
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        ident = self._safe_ident(str(cfg.get("identifier", "备份")))
        target = dest / f"{ts}-{ident}-{Path(self.db_path).name}"
        try:
            tgt = sqlite3.connect(str(target))
            self.db.conn.backup(tgt)              # 官方在线备份，一致性快照
            tgt.close()
        except Exception as e:                    # noqa: BLE001
            messagebox.showerror("备份失败", str(e), parent=self)
            return
        messagebox.showinfo("备份完成", f"已备份到：\n{target}", parent=self)

    def _setup_fonts(self):
        """默认字体与控件尺寸（fields.json 的 ui.font 可配置）。"""
        from tkinter import font as tkfont
        size = CFG.font.get("default", 12)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                     "TkHeadingFont"):
            tkfont.nametofont(name).configure(size=size)
        style = ttk.Style(self)
        style.configure("Treeview",
                        rowheight=CFG.font.get("tree_rowheight", 38))
        style.configure("Treeview.Heading",
                        font=("", CFG.font.get("heading_size", 13),
                              "bold"))

    # ---------- 动作 ----------
    def _new_project(self):
        SnapshotEditor(self, self.db, on_saved=lambda pid: self.reload())

    def _pick_template(self, title):
        """弹出模板选择框，返回选中的模板或 None。
        周报模板是导出专用（只读视图），不出现在通用导入/导出选择里。"""
        tpls = [t for t in CFG.templates if t.get("kind") != "weekly"]
        if not tpls:
            return None
        picker = TemplatePicker(self, title, tpls)
        return picker.result

    def _import(self):
        tpl = self._pick_template("选择导入模板")
        if tpl is None:
            return
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Excel 或 CSV", "*.xlsx *.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            from importer import import_file
            created, skipped, unmapped = import_file(self.db, path,
                                                     template=tpl)
        except Exception as e:                      # noqa: BLE001
            messagebox.showerror("导入失败", str(e), parent=self)
            return
        msg = f"使用模板「{tpl['name']}」成功导入 {created} 个项目。"
        if skipped:
            msg += (f"\n跳过 {len(skipped)} 行（整行为空/重复表头）："
                    f"{skipped}")
        if unmapped:
            msg += f"\n未识别的列（已忽略）：{', '.join(unmapped)}"
        messagebox.showinfo("导入完成", msg, parent=self)
        self.reload()

    def _export(self):
        """导出当前筛选/排序后的行（列表里看到的 = 导出的）。
        先选模板，列序 = 模板定义。"""
        tpl = self._pick_template("选择导出模板")
        if tpl is None:
            return
        from exporter import export_with_template
        rows = self._all_rows()          # 全量匹配，不受渲染截断影响
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx",
            initialfile=f"{tpl['name']}表格.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            n = export_with_template(rows, path, tpl)
        except Exception as e:                      # noqa: BLE001
            messagebox.showerror("导出失败", str(e), parent=self)
            return
        messagebox.showinfo("导出完成",
                            f"已按模板「{tpl['name']}」导出 {n} 行到：\n{path}",
                            parent=self)

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        if self.mode == "weekly":
            return int(sel[0].split("-")[0])   # iid = "project_id-序号"
        return int(self.tree.item(sel[0])["values"][0])

    # ---------- 模式切换（v1.4.0 周报） ----------
    def _toggle_mode(self):
        self.mode = "weekly" if self.mode == "followup" else "followup"
        self._rebuild_cols()
        self.col_filters = {c: None for c in self.cols}
        self.render_offset = 0
        # 各模式默认排序：跟进表=JSON 的 default_sort；周报=追加时间倒序
        if self.mode == "weekly":
            self.sort_col, self.sort_reverse = "snapshot_at", True
        else:
            self.sort_col = CFG.default_sort["column"]
            self.sort_reverse = CFG.default_sort["desc"]
        self._refresh_headings()
        self._apply_mode()
        self.reload()

    def _rebuild_cols(self):
        """按模式重建列定义（表头、宽度），Treeview 原地换列。"""
        if self.mode == "weekly":
            # 列与顺序由 JSON 的 weekly_sheet.columns 决定
            builtin = {"snapshot_at": "追加时间", "project": "项目",
                       "change_summary": "改动说明"}
            self.cols = tuple(c for c in CFG.weekly_cols)
            self.heads = {c: builtin.get(c, LABELS.get(c, c))
                          for c in self.cols}
            self.widths = {}
        else:
            self.cols = tuple(n for n, _h in CFG.display_cols)
            self.heads = {n: h for n, h in CFG.display_cols}
        self.tree.configure(columns=self.cols)
        for c in self.cols:
            self.tree.heading(c, text=self.heads[c],
                              command=lambda cc=c: self._sort(cc))
            self.tree.column(c, width=self.widths.get(c, 140),
                             minwidth=60, stretch=False)

    def _apply_mode(self):
        weekly = self.mode == "weekly"
        for b in (self.new_btn, self.import_btn, self.export_btn):
            b.config(state="disabled" if weekly else "normal")
        # 收藏夹在两种模式下都可用（v2.7.0 周报兼容：表格/日历/导出联动）
        # v2.7.2：周报模式下"加入/移出"禁用（批量增删索引属于跟进表
        # 模式操作，周报行是快照视角）
        if CFG.favorites_enabled:
            st = "disabled" if weekly else "normal"
            self.fav_remove_btn.config(state=st)
            dlg = getattr(self, "_fav_dialog", None)
            if dlg is not None and dlg.winfo_exists():
                dlg.add_btn.config(state=st)
        self.wk_export_btn.config(
            state="normal" if weekly else "disabled")
        self.mode_btn.config(text="跟进表模式" if weekly else "周报模式")

    # ---------- 日历供给（按模式分流） ----------
    def _cal_entries(self, year, month):
        if self.mode == "weekly":
            # v1.5.5 修复：此前窗口锚定"今天"，翻到其他月份会白屏。
            # 日历组件一次只查询当前查看页的年月，窗口检查是恒真的
            # 赘余——直接供给所查月份即可：看 12 月时翻 11/12/1 月，
            # 各自显示当月追加记录（跨年天然正确），无白屏。
            append_label = _kind_labels().get("append", "追加")
            entries = [{"date": e["date"], "kind": "append",
                        "text": f"[{append_label}] " + e["text"],
                        "project_id": e["project_id"]}
                       for e in self.db.calendar_snapshots(year, month)]
            # 收藏夹模式：周报日历同样只看夹内项目
            if self.fav_ids is not None:
                entries = [e for e in entries
                           if e["project_id"] in self.fav_ids]
            return entries
        if CFG.calendar_mode == "filtered" or self.fav_ids is not None:
            # 跟随表格筛选：只渲染当前筛选/搜索后项目的时间节点。
            # 收藏夹模式强制走本分支（无论 calendar_mode 配置），
            # 保证"表格和日历同步只显示收藏夹内容"。
            # 启动初期 cols 尚未建好（日历先于列表创建），此时返回空，
            # 等列表就绪后的首次 reload 会重新填充。
            if not getattr(self, "cols", None):
                return []
            if self.mode == "weekly":
                ids = [r["project_id"] for r in self._filtered_rows()]
            else:
                ids = self.db.query_project_ids(
                    **self._query_kwargs(),
                    include_closed=self.show_closed)
            if not ids:
                return []
            return self.db.calendar_entries_for(ids, year, month)
        return self.db.calendar_entries(year, month)

    # ---------- 周报导出 ----------
    def _export_weekly(self):
        if self.mode != "weekly":
            return
        WeeklyReportDialog(self, on_ok=self._do_export_weekly)

    def _do_export_weekly(self, d1, d2, p1, p2):
        tpl = next((t for t in CFG.templates
                    if t.get("kind") == "weekly"), None)
        if tpl is None:
            # 内置默认周报列：JSON 不配 kind=weekly 也能导出
            tpl = {"kind": "weekly", "columns": [
                ("日期", "__date__", None),
                ("项目", "__name__", None),
                ("跟进记录", "followup_note", None),
                ("改动说明", "change_summary", None)]}
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx",
            initialfile=f"周报_{d1}~{d2}.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            rows_f = self.db.snapshots_between(d1, d2)
            rows_p = self.db.weekly_plan(p1, p2, self.show_closed)
            # 收藏夹模式：周报导出同样只导出夹内项目（与视图联动）
            if self.fav_ids is not None:
                rows_f = [r for r in rows_f
                          if r["project_id"] in self.fav_ids]
                rows_p = [r for r in rows_p if r["id"] in self.fav_ids]
            from exporter import export_weekly
            nf, np_ = export_weekly(rows_f, rows_p, tpl, path)
        except Exception as e:                      # noqa: BLE001
            messagebox.showerror("导出失败", str(e), parent=self)
            return
        messagebox.showinfo(
            "周报已导出",
            f"本周跟进 {nf} 条 / 下周计划 {np_} 条\n\n{path}", parent=self)

    def _open_selected(self):
        pid = self._selected_id()
        if pid:
            self._open_project({"project_id": pid})

    def _open_project(self, payload):
        """日历条目点击的入口：payload 来自 calendar_entries。"""
        return ProjectReader(self, self.db, payload["project_id"],
                             on_changed=self.reload)

    def _open_day(self, date_str):
        """点某天日期弹出当天明细。数据一律走 _cal_entries（与日历
        渲染同一入口，filtered 筛选不会被绕开）；弹窗持有 provider
        回调，返回时自动重新取数刷新。"""
        y, m = int(date_str[:4]), int(date_str[5:7])
        provider = lambda: [e for e in self._cal_entries(y, m)
                            if e["date"] == date_str]
        DayWindow(self, date_str, provider, self._open_project)

    def _toggle_closed(self):
        self.show_closed = not self.show_closed
        self.closed_btn.config(text="隐藏已关闭" if self.show_closed
                               else "显示已关闭")
        self.reload()

    def _sort(self, col):
        """点表头排序：再点一次反向。"""
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col, self.sort_reverse = col, False
        self._refresh_headings()
        self.reload()

    def _refresh_headings(self):
        """表头标注：排序方向 ▲▼ + 筛选标记 🔽。"""
        for c in self.cols:
            mark = ""
            if c == self.sort_col:
                mark += " ▼" if self.sort_reverse else " ▲"
            if self.col_filters.get(c) is not None:
                mark += " 🔽"
            self.tree.heading(c, text=self.heads[c] + mark,
                              command=lambda cc=c: self._sort(cc))

    def _filter_type(self, col):
        """列的筛选类型：range=日期区间；list=勾选清单（默认）。"""
        if col in CFG.col_filter_type:
            return CFG.col_filter_type[col]
        if col == "snapshot_at" or col in CFG.date_fields:
            return "range"
        return "list"

    def _header_menu(self, ev):
        """右键表头：日期列弹区间筛选，其余列弹取值勾选清单。"""
        if self.tree.identify_region(ev.x, ev.y) != "heading":
            return
        col_id = self.tree.identify_column(ev.x)      # "#3" 形式
        col = self.cols[int(col_id.lstrip("#")) - 1]
        # 收藏夹模式下给筛选弹窗标题加标注，避免"全局筛选"的错觉
        title = self.heads[col] + ("（收藏夹内）" if self.fav_ids is not None
                                   else "")
        if self._filter_type(col) == "range":
            def apply_range(rng):
                self.col_filters[col] = rng   # (d1, d2) 或 None
                self._refresh_headings()
                self.reload()
            RangeFilterPopup(self, title,
                             self.col_filters.get(col), apply_range)
            return
        # 取值范围跟随当前视野：收藏夹模式下只列夹内项目的取值，
        # 否则表头筛选项来自全量数据，会造成"筛选和看到的内容对不上"。
        # 只按收藏夹收缩，不叠加其他列筛选（保持"该列全量取值"的原语义）
        if self.fav_ids is not None:
            pool, _ = self.db.query_projects(
                filters={"id": set(self.fav_ids)},
                include_closed=self.show_closed)
        else:
            pool = self.db.list_projects(self.show_closed)
        values = sorted({str(p[col] if p[col] is not None else "")
                         for p in pool})

        def apply(selected):
            # 空集 = 该列全不显示，不能当成"无筛选"
            self.col_filters[col] = selected if selected else set()
            self._refresh_headings()
            self.reload()

        FilterPopup(self, title, values,
                    self.col_filters[col], apply)

    def _clear_filters(self):
        self.col_filters = {c: None for c in self.cols}
        self._refresh_headings()
        self.reload()

    def _selected_ids(self):
        """当前表格选中行的项目 id 列表（两种模式都支持）。

        周报模式 iid = "project_id-序号"，直接解析；跟进表模式走
        _row_ids 行号映射（iid 为 None，不能反查）。
        """
        sel = self.tree.selection()
        if not sel:
            return []
        if self.mode == "weekly":
            out = []
            for item in sel:
                try:
                    out.append(int(item.split("-")[0]))
                except (ValueError, IndexError):
                    pass
            return out
        if not getattr(self, "_row_ids", None):
            return []
        out = []
        for item in sel:
            i = self.tree.index(item)
            if 0 <= i < len(self._row_ids):
                out.append(self._row_ids[i])
        return out

    # ---------- 收藏夹模式（v2.7.0） ----------
    def _open_favorites(self):
        dlg = getattr(self, "_fav_dialog", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.lift()
            return
        self._fav_dialog = FavoritesDialog(
            self, self.db, on_enter=self._enter_favorites,
            on_changed=self._fav_changed)

    def _fav_chrome(self):
        """收藏夹模式的界面反馈：横幅文字 + 窗口标题栏夹名。"""
        if self.fav_coll is None:
            self.fav_var.set("")
            self.title(self._base_title)
            return
        cid, name = self.fav_coll
        n = len(self.fav_ids) if self.fav_ids is not None else 0
        self.fav_var.set(f"★ {CFG.favorites_label}模式：{name}"
                         f"（{n} 个项目）")
        self.title(f"{self._base_title} —— "
                   f"[{CFG.favorites_label}：{name}]")

    def _enter_favorites(self, coll_id, name):
        ids = self.db.collection_projects(coll_id)
        if not ids:
            messagebox.showinfo(
                CFG.favorites_label,
                f"收藏夹「{name}」是空的。\n请先在弹窗里加入项目。",
                parent=self)
            return
        # 进入模式时清掉已有列筛选：旧筛选可能把夹内项目全滤掉，
        # 造成"进了收藏夹却是空表"的困惑（与切换周报模式的行为一致）。
        # 周报/跟进表两种模式都允许进入，模式切换保持可用（联动）。
        self.col_filters = {c: None for c in self.cols}
        self._refresh_headings()
        self.fav_ids = set(ids)
        self.fav_coll = (coll_id, name)
        # 横幅与"共 N 条"同一行：钉在分页行"共 N 条"标签的左边，
        # 任何窗口高度下都随分页行可见（v2.7.2 修复）
        self.fav_banner.pack(side="left", padx=(8, 4),
                             before=self.limit_lbl)
        self._fav_chrome()
        self.reload()

    def _exit_favorites(self):
        self.fav_ids = None
        self.fav_coll = None
        self.fav_banner.pack_forget()
        self._fav_chrome()
        self.reload()

    def _fav_remove_selected(self):
        """把主表格选中的项目从当前收藏夹剔除（只删索引，项目数据
        不动；v2.7.2）。夹被清空时由 _fav_changed 自动退出模式。"""
        if self.fav_coll is None or self.mode == "weekly":
            return
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo(
                CFG.favorites_label,
                "先在主表格里选中要移出的项目（Ctrl/Shift 可多选）。",
                parent=self)
            return
        cid, _name = self.fav_coll
        for pid in ids:
            self.db.collection_remove(cid, pid)
        self._fav_changed()

    def _fav_changed(self):
        """收藏夹内容/清单被弹窗改动后的回调：模式内同步刷新，
        当前夹被删/清空则自动退出模式。"""
        if self.fav_coll is None:
            return
        cid, name = self.fav_coll
        cur = self.db.collection_name(cid)
        if cur is None:
            self._exit_favorites()
            return
        ids = self.db.collection_projects(cid)
        if not ids:
            messagebox.showinfo(
                CFG.favorites_label,
                f"收藏夹「{name}」已没有项目，退出收藏夹模式。",
                parent=self)
            self._exit_favorites()
            return
        self.fav_ids = set(ids)
        self.fav_coll = (cid, cur)      # 名字可能被重命名过
        self._fav_chrome()
        self.reload()

    def _fav_hotkey(self, ev):
        """Ctrl+1~9 直达前 9 个收藏夹；Ctrl+0 退出收藏夹模式。"""
        keysym = getattr(ev, "keysym", "")
        if not keysym.isdigit():
            return
        # 输入框里打字时不抢快捷键（搜索框/编辑器都是 Entry/Text）
        w = self.focus_get()
        if w is not None and w.winfo_class() in (
                "Entry", "TEntry", "Text", "Spinbox", "TSpinbox"):
            return
        n = int(keysym)
        if n == 0:
            if self.fav_ids is not None:
                self._exit_favorites()
            return
        rows = self.db.list_collections()
        if n <= len(rows):
            cid, name, _cnt = rows[n - 1]
            self._enter_favorites(cid, name)

    # ---------- 数据 ----------
    def _filtered_rows(self):
        """周报模式的行（SQL 窗口查询）。跟进表模式已全面走
        query_projects（_page_rows 显示 / _all_rows 导出），
        筛选/搜索/排序/分页均在 SQLite 内完成（v2.1）。"""
        if self.mode == "weekly":
            rows = self._weekly_base_rows()
        else:                                  # 兼容兜底，正常不会走到
            rows = self._all_rows()
        # 逐列筛选：勾选清单(list) 或 日期区间(range)
        for c in self.cols:
            sel = self.col_filters.get(c)
            if sel is None:
                continue
            if isinstance(sel, tuple):        # 区间 (d1, d2)，空串=不限
                d1, d2 = sel
                def in_range(r, c=c, d1=d1, d2=d2):
                    v = str(r[c])[:10]        # 只比日期部分
                    if not v:
                        return False
                    if d1 and v < d1:
                        return False
                    if d2 and v > d2:
                        return False
                    return True
                rows = [r for r in rows if in_range(r)]
            else:                             # 勾选集合
                rows = [r for r in rows if str(r[c]) in sel]
        # 搜索：每个关键词都必须命中（任一搜索字段包含该词；
        # 周报模式下 search_fields 与列无交集，退化为搜全部显示列）
        keywords = self.search_var.get().split()
        if keywords:
            fields = [f for f in CFG.search_fields if f in self.cols]
            # 项目名列参与搜索：周报视图里项目名是最常被搜的内容，
            # 漏掉它会让"带着搜索词切到周报"看到一张空表，像没切过去
            if "project" in self.cols and "project" not in fields:
                fields.append("project")
            if not fields:
                fields = list(self.cols)
            def hit(r, kw):
                return any(kw in str(r[f]).casefold() for f in fields)
            for kw in keywords:
                k = kw.casefold()
                rows = [r for r in rows if hit(r, k)]
        # 排序：数字列按数值，其余按文本
        #（周报模式的行可能没有排序列，如默认的 start_date，此时跳过）
        if self.sort_col and rows and self.sort_col in rows[0]:
            def key(r):
                v = r[self.sort_col]
                try:
                    return (0, float(v))
                except (TypeError, ValueError):
                    return (1, str(v).casefold())
            rows.sort(key=key, reverse=self.sort_reverse)
        return rows

    def _weekly_base_rows(self):
        """周报模式表格行：跟随日历当前查看月的 [查看月-1, 查看月+1]
        窗口（跨年正确）。列由 JSON 的 weekly_sheet.columns 决定。
        v1.5.5 修复：窗口此前锚定"今天"，翻月后表格内容不跟随。"""
        base = self.cal.year * 12 + (self.cal.month - 1)
        sy, sm0 = divmod(base - 1, 12)        # 窗口起点 = 查看月-1 的1号
        ey, em0 = divmod(base + 2, 12)        # 窗口终点(不含) = 查看月+2 的1号
        start_bound = f"{sy:04d}-{sm0 + 1:02d}-01 00:00:00"
        end_bound = f"{ey:04d}-{em0 + 1:02d}-01 00:00:00"
        rows = []
        for s in self.db.conn.execute(
                """SELECT s.*, p.title AS pt, p.status AS ps, p.id AS pid
                   FROM snapshots s JOIN projects p ON p.id = s.project_id
                   WHERE s.snapshot_at >= ? AND s.snapshot_at < ?
                   ORDER BY s.snapshot_at""",
                (start_bound, end_bound)):
            if not self.show_closed and s["ps"] != "open":
                continue
            r = {"project_id": s["pid"]}
            for c in self.cols:      # 只取配置列需要的数据
                if c == "snapshot_at":
                    r[c] = s["snapshot_at"]
                elif c == "project":
                    r[c] = s["pt"]
                elif c == "change_summary":
                    r[c] = s["change_summary"] or ""
                elif c in s.keys():
                    r[c] = s[c] if s[c] is not None else ""
                else:
                    r[c] = ""
            rows.append(r)
        # 收藏夹模式：周报表格也只显示夹内项目（与跟进表/日历联动）
        if self.fav_ids is not None:
            rows = [r for r in rows if r["project_id"] in self.fav_ids]
        return rows

    def _display(self, r, c):
        """显示值：搜索命中且在搜索字段范围内 -> 前加红点标记。

        仅影响界面显示，数据层（r）不变，导出不受影响。
        Tk 表格控件不支持单元格级颜色，红点标记是等价方案。
        """
        v = str(r[c])
        kws = [k.casefold() for k in self.search_var.get().split()]
        if kws and c in CFG.search_fields and \
                any(k in v.casefold() for k in kws):
            return "🔴 " + v
        return v

    def reload(self):
        self.render_offset = 0            # 任何数据变化回到第一页
        self._render_rows()
        self.cal.refresh()

    def _query_kwargs(self, favorites=True):
        """当前筛选/搜索状态 -> SQL 查询参数（followup 模式）。

        favorites=True 时并入收藏夹模式的项目 id 集合（key="id" 走
        _build_where 的 id 分支）；导出等场景传 favorites=False 绕过，
        保证收藏夹只是视图筛选、不影响产出内容。
        """
        filters = {c: s for c, s in self.col_filters.items()
                   if s is not None}
        if favorites and self.fav_ids is not None:
            filters["id"] = set(self.fav_ids)
        kws = self.search_var.get().split()
        sf = []
        if kws:
            sf = [f for f in CFG.search_fields if f in self.cols] \
                or list(self.cols)
        return {"filters": filters, "keywords": kws,
                "search_fields": sf}

    def _page_rows(self):
        """当前页（SQL 化：筛选/搜索/排序/分页全在 SQLite）。"""
        if self.mode == "weekly":
            rows = self._filtered_rows()          # 周报：原有 SQL 窗口
            total = len(rows)
            rows = rows[self.render_offset: self.render_offset
                        + CFG.render_limit]
            return rows, total
        return self.db.query_projects(
            **self._query_kwargs(),
            sort=self.sort_col, sort_desc=self.sort_reverse,
            include_closed=self.show_closed,
            offset=self.render_offset,      # 翻页式：恒定每页 render_limit 行
            limit=CFG.render_limit)

    def _all_rows(self):
        """全量匹配行（导出用）：同一 SQL 管线，不带 LIMIT。"""
        if self.mode == "weekly":
            return self._filtered_rows()
        rows, _ = self.db.query_projects(
            **self._query_kwargs(favorites=False),   # 导出不受收藏夹影响
            sort=self.sort_col, sort_desc=self.sort_reverse,
            include_closed=self.show_closed)
        return rows

    def _render_rows(self):
        """把当前页渲染进树。截断与排序全在 SQL 侧完成。"""
        rows, total = self._page_rows()
        self._fit_columns(rows)
        self.tree.delete(*self.tree.get_children())
        # 行号 -> 项目 id 映射（收藏夹"加入选中项目"用；iid 在跟进表
        # 模式下为 None，不能反查 id。跟进表行的键是 id，周报行是
        # project_id）
        self._row_ids = [r["id"] if "id" in r else r["project_id"]
                         for r in rows]
        for idx, r in enumerate(rows):
            if self.mode == "weekly":
                iid = f'{r["project_id"]}-{idx}'   # 一项目多条追加需唯一
            else:
                iid = None
            self.tree.insert("", "end", iid=iid,
                             values=[self._display(r, c) for c in self.cols])
        self._update_limit_bar(len(rows), total)

    def _update_limit_bar(self, shown, total):
        """翻页提示 + 上/下一页（v2.1 翻页式：恒定每页渲染量）。"""
        start = self.render_offset + (1 if shown else 0)
        end = self.render_offset + shown
        if total > shown or self.render_offset > 0:
            self.limit_lbl.config(
                text=f"第 {start} ~ {end} 条 / 共 {total} 条"
                     f"（筛选和导出仍基于全量）")
        else:
            self.limit_lbl.config(text=f"共 {total} 条")
        self.prev_btn.config(state="normal" if self.render_offset > 0
                             else "disabled")
        self.next_btn.config(
            state="normal" if end < total else "disabled")

    def _load_more(self):
        self.render_offset += CFG.render_limit
        self._render_rows()

    def _load_prev(self):
        self.render_offset = max(0, self.render_offset - CFG.render_limit)
        self._render_rows()

    @staticmethod
    def _est_px(text):
        """估算字符串像素宽：中文 17px，ASCII 9px。"""
        return sum(17 if ord(ch) > 127 else 9 for ch in str(text)) + 24

    def _fit_columns(self, rows):
        """列宽规则（v2.1.1）：
        1. 只增不减——内容变化绝不让列变窄
        2. 基线 = 表头宽 + 排序箭头(▲) + 筛选标记(🔽) 余量
        3. 内容比基线长时扩展到内容宽，上下限可配（ui.columns）
        4. 字段在 fields.json 配了 "width" 时以配置值为最终宽（同样只增不减）
        """
        lo = CFG.col_ui.get("min_width", 70)
        hi = CFG.col_ui.get("max_width", 360)
        for c in self.cols:
            if c in CFG.field_width:
                want = CFG.field_width[c]
            else:
                # 表头 + 箭头余量（排序▲+筛选🔽 按三倍预留，实测单倍不够）
                longest = self.heads[c] + " ▲🔽" * 3
                for r in rows:
                    cell = str(self._display(r, c))
                    if len(cell) > len(longest):
                        longest = cell
                want = self._est_px(longest)
            cur = self.tree.column(c)["width"]
            w = max(cur, lo, min(hi, want))          # 关键：与现宽取 max，只增不减
            self.tree.column(c, width=w, stretch=False)


class SearchPopup(tk.Toplevel):
    """搜索输入弹框：锚定在搜索按钮左侧展开，输入即过滤。

    关掉弹框搜索条件保留（按钮上会显示当前关键词）；
    点"清空"恢复全部并关闭。
    """

    def __init__(self, master, anchor_btn, var):
        super().__init__(master)
        self.var = var
        self.withdraw()                     # 先定位再显示，避免闪位置
        self.overrideredirect(False)
        self.title("搜索")
        frm = tk.Frame(self, padx=10, pady=10)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text="关键词（空格分隔=AND）:",
                 fg="#666666").pack(anchor="w")
        e = tk.Entry(frm, textvariable=var, width=30, font=("", 12))
        e.pack(fill="x", pady=4)
        e.icursor("end")
        self._entry = e
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="清空",
                  command=self._clear).pack(side="right", padx=4)
        tk.Button(btns, text="关闭",
                  command=self.destroy).pack(side="right")
        self.transient(master)
        self.update_idletasks()
        # 定位：右边缘对齐搜索按钮左边缘（向左展开），顶部对齐按钮下方
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = anchor_btn.winfo_rootx() - w - 4
        y = anchor_btn.winfo_rooty() + anchor_btn.winfo_height() + 2
        self.geometry(f"+{max(x, 0)}+{y}")
        self.deiconify()
        self.lift()
        e.focus_set()
        self.bind("<Escape>", lambda e_: self.destroy())

    def _clear(self):
        self.var.set("")
        self.destroy()


class WeeklyReportDialog(tk.Toplevel):
    """周报导出弹窗：两行日期区间（本周跟进 / 下周计划）。

    默认：本周 = 本周一~本周日；下周 = 下周一~下周日。
    on_ok(d1, d2, p1, p2) 由调用方执行导出。
    """

    def __init__(self, master, on_ok):
        super().__init__(master)
        self.on_ok = on_ok
        self.title("导出周报")
        self.transient(master)
        from datetime import date, timedelta
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        next_monday = monday + timedelta(days=7)
        d = lambda x: x.strftime("%Y-%m-%d")

        frm = tk.Frame(self, padx=16, pady=14)
        frm.pack(fill="both", expand=True)
        r1 = tk.Frame(frm)
        r1.pack(fill="x", pady=4)
        tk.Label(r1, text="本周跟进时间：").pack(side="left")
        self.d1 = tk.StringVar(value=d(monday))
        self.d2 = tk.StringVar(value=d(monday + timedelta(days=6)))
        tk.Entry(r1, textvariable=self.d1, width=12).pack(side="left", padx=4)
        tk.Label(r1, text="~").pack(side="left")
        tk.Entry(r1, textvariable=self.d2, width=12).pack(side="left", padx=4)
        r2 = tk.Frame(frm)
        r2.pack(fill="x", pady=4)
        tk.Label(r2, text="下周计划时间：").pack(side="left")
        self.p1 = tk.StringVar(value=d(next_monday))
        self.p2 = tk.StringVar(value=d(next_monday + timedelta(days=6)))
        tk.Entry(r2, textvariable=self.p1, width=12).pack(side="left", padx=4)
        tk.Label(r2, text="~").pack(side="left")
        tk.Entry(r2, textvariable=self.p2, width=12).pack(side="left", padx=4)
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(btns, text="确定", width=8,
                  command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="取消", width=8,
                  command=self.destroy).pack(side="right")
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}"
                      f"+{(self.winfo_screenheight() - h) // 2}")
        self.grab_set()
        self.lift()

    def _ok(self):
        for v in (self.d1, self.d2, self.p1, self.p2):
            s = v.get().strip()
            if len(s) != 10 or s[4] != "-" or s[7] != "-":
                messagebox.showwarning("提示", "日期格式应为 YYYY-MM-DD",
                                       parent=self)
                return
        self.on_ok(self.d1.get().strip(), self.d2.get().strip(),
                   self.p1.get().strip(), self.p2.get().strip())
        self.destroy()


class TemplatePicker(tk.Toplevel):
    """模板选择弹窗（导入/导出共用）：大按钮直选，点哪个用哪个。

    result 为选中的模板或 None。"""

    def __init__(self, master, title, templates):
        super().__init__(master)
        self.title(title)
        self.result = None
        self.transient(master)
        frm = tk.Frame(self, padx=18, pady=18)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text=title, font=("", 14, "bold")).pack(
            anchor="w", pady=(0, 12))
        for t in templates:
            # 大按钮：整行可点，点即选中并继续
            tk.Button(frm, text=t["name"], anchor="w",
                      font=("", 14), padx=20, pady=14,
                      command=lambda tt=t: self._pick(tt)).pack(
                fill="x", pady=5)
        tk.Button(frm, text="取消", font=("", 11),
                  command=self.destroy).pack(pady=(12, 0))
        self.grab_set()
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}"
                      f"+{(self.winfo_screenheight() - h) // 2}")
        self.lift()
        self.wait_window()

    def _pick(self, template):
        self.result = template
        self.destroy()


class RangeFilterPopup(tk.Toplevel):
    """日期区间筛选弹窗：从 ~ 到 两个日期框（留空=不限，可只填一端）。

    on_apply((d1, d2) 或 None)。d1/d2 为 YYYY-MM-DD；都空 = 清除筛选。
    """

    def __init__(self, master, col_name, current, on_apply):
        super().__init__(master)
        self.on_apply = on_apply
        self.title(f"筛选 - {col_name}")
        frm = tk.Frame(self, padx=14, pady=12)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text=f"{col_name}：日期区间（留空=不限）",
                 fg="#666666").pack(anchor="w")
        row = tk.Frame(frm)
        row.pack(fill="x", pady=6)
        cur = current or ("", "")
        self.v1 = tk.StringVar(value=cur[0] or "")
        self.v2 = tk.StringVar(value=cur[1] or "")
        tk.Entry(row, textvariable=self.v1, width=12).pack(side="left",
                                                           padx=2)
        tk.Label(row, text="~").pack(side="left")
        tk.Entry(row, textvariable=self.v2, width=12).pack(side="left",
                                                           padx=2)
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        tk.Button(btns, text="清除筛选",
                  command=self._clear).pack(side="left")
        tk.Button(btns, text="确定", width=8,
                  command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="取消", width=8,
                  command=self.destroy).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())   # 回车=确定
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(master)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}"
                      f"+{(self.winfo_screenheight() - h) // 2}")
        self.grab_set()
        self.lift()

    def _clear(self):
        self.on_apply(None)
        self.destroy()

    def _ok(self):
        from db import normalize_date
        a = self.v1.get().strip()
        b = self.v2.get().strip()
        na = normalize_date(a) if a else ""
        nb = normalize_date(b) if b else ""
        if (a and not na) or (b and not nb):
            # 无效日期：不给任何反馈错觉——弹窗停留 + 红字，不设置筛选
            for w in self.winfo_children():
                if getattr(w, "_err", False):
                    w.destroy()
            err = tk.Label(self, text="日期无法识别，应为 YYYY-MM-DD",
                           fg="#C62828")
            err._err = True
            err.pack()
            return
        self.on_apply((na, nb) if (na or nb) else None)
        self.destroy()


class FilterPopup(tk.Toplevel):
    """Excel 式筛选弹窗：勾选该列要显示的值。"""

    def __init__(self, master, col_name, values, selected, on_apply):
        super().__init__(master)
        self.title(f"筛选 - {col_name}")
        self.on_apply = on_apply
        self.vars = {}
        frm = tk.Frame(self, padx=10, pady=10)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text=f"{col_name}：勾选要显示的值",
                 fg="#666666").pack(anchor="w")
        # 值清单（可滚动）
        box = tk.Frame(frm)
        box.pack(fill="both", expand=True, pady=4)
        canvas = tk.Canvas(box, width=240, height=min(300, 40 * len(values) + 20),
                           highlightthickness=0)
        vsb = tk.Scrollbar(box, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        for v in values:
            var = tk.BooleanVar(value=(selected is None or v in selected))
            self.vars[v] = var
            tk.Checkbutton(inner, text=v or "(空)", variable=var,
                           anchor="w").pack(fill="x")
        # 全选/全不选 + 确定/取消
        ops = tk.Frame(frm)
        ops.pack(fill="x", pady=2)
        tk.Button(ops, text="全选",
                  command=lambda: self._set_all(True)).pack(side="left")
        tk.Button(ops, text="全不选",
                  command=lambda: self._set_all(False)).pack(side="left",
                                                             padx=4)
        btns = tk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        tk.Button(btns, text="确定",
                  command=self._ok).pack(side="right", padx=4)
        tk.Button(btns, text="取消",
                  command=self.destroy).pack(side="right")
        self.grab_set()

    def _set_all(self, b):
        for v in self.vars.values():
            v.set(b)

    def _ok(self):
        checked = {v for v, var in self.vars.items() if var.get()}
        self.on_apply(checked)
        self.destroy()


class FavoritesDialog(tk.Toplevel):
    """收藏夹面板（v2.7.0）。

    布局：左侧收藏夹列表，中间所选夹内的项目清单（可移除条目），
    右侧操作按钮。交互约定：
      - 从主窗口"收藏夹"按钮下方弹出（不挡日历）；
      - 非模态、不 grab、不设 transient——可最小化，开着不影响
        主程序任何操作，右上角叉即关闭；点主窗口任意处面板自动
        抬回主窗口之上（v2.7.2，不会沉到后面）；
      - 双击夹名进入筛选（由主窗口接管模式状态，见
        MainApp._enter_favorites），无"进入"按钮；
      - 无"关闭"按钮；
      - 面板打开期间，主表格临时改为多选（Ctrl/Shift），关闭即
        恢复单选——多选仅为加入收藏夹服务；
      - 任何增删操作后保持当前夹的选中态。
    """

    def __init__(self, app, db, on_enter, on_changed):
        super().__init__(app)
        self.app = app
        self.db = db
        self.on_enter = on_enter
        self.on_changed = on_changed
        self.title(CFG.favorites_label)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-KeyPress>", self._hotkey)

        # 定位：收藏夹按钮正下方（挡住表格没关系，表格此刻正是
        # 取数/多选的对象；不挡日历）
        self.update_idletasks()
        bx = app.fav_btn.winfo_rootx()
        by = app.fav_btn.winfo_rooty() + app.fav_btn.winfo_height()
        self.geometry(f"+{bx}+{by}")

        # 打开期间主表格允许多选，关闭时恢复
        self._prev_selectmode = str(app.tree.cget("selectmode"))
        app.tree.configure(selectmode="extended")

        # 点主窗口任意处把面板抬回主窗口之上（v2.7.2）：不设 transient
        # 也能保持"浮在主界面上"的观感，且仍非模态、可最小化
        self._lift_id = app.bind("<Button-1>", self._lift_me, add="+")

        tk.Label(self, text="收藏夹").grid(row=0, column=0, padx=8,
                                           pady=(4, 0), sticky="w")
        self.listbox = tk.Listbox(self, width=40, height=10,
                                  activestyle="dotbox", exportselection=False)
        self.listbox.grid(row=1, column=0, padx=(8, 4), pady=(0, 4))
        self.listbox.bind("<Double-1>", lambda e: self._enter())

        btns = tk.Frame(self)
        btns.grid(row=1, column=2, padx=8, pady=(0, 4), sticky="ns")
        for text, cmd in [
                ("新建", self._new),
                ("重命名", self._rename),
                ("删除", self._delete)]:
            tk.Button(btns, text=text, command=cmd).pack(fill="x", pady=3)
        # "加入"按钮保留引用：周报模式下由主窗口置灰（v2.7.2）
        self.add_btn = tk.Button(btns, text="加入",
                                 command=self._add_selected)
        self.add_btn.pack(fill="x", pady=3)
        # 周报模式下"加入"置灰（与横幅"移出"一致；v2.7.2）
        if app.mode == "weekly":
            self.add_btn.config(state="disabled")
        tk.Label(self, fg="#888888", justify="left",
                 text="双击夹名进入筛选；打开本面板时主表格可多选\n"
                      "（Ctrl/Shift），加入只写索引不动项目数据"
                 ).grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 8),
                        sticky="w")
        self._reload()

    # ---- 列表维护 ----
    def _reload(self, keep_cid=None):
        """刷新收藏夹列表；keep_cid 指定时保持该夹选中。"""
        if keep_cid is None:
            sel = self.listbox.curselection()
            if sel:
                keep_cid = self._rows[sel[0]][0]
        self._rows = self.db.list_collections()
        self.listbox.delete(0, "end")
        for _cid, name, n in self._rows:
            self.listbox.insert("end", f"{name}（{n} 个项目）")
        if keep_cid is not None:
            for i, r in enumerate(self._rows):
                if r[0] == keep_cid:
                    self.listbox.selection_set(i)
                    break

    def _pick(self, silent=False):
        sel = self.listbox.curselection()
        if not sel:
            if not silent:
                messagebox.showinfo(CFG.favorites_label, "请先选一个收藏夹",
                                    parent=self)
            return None
        return self._rows[sel[0]]

    def _selected_cid(self):
        row = self._pick(silent=True)
        return row[0] if row else None

    # ---- 操作 ----
    def _enter(self):
        row = self._pick()
        if row is None:
            return
        cid, name, _n = row
        # 不关闭本面板：进入后仍可切换/管理收藏夹。
        # 空夹会被弹框拒绝，模式状态不变。
        self.on_enter(cid, name)

    def _new(self):
        name = simpledialog.askstring(
            CFG.favorites_label, "新收藏夹名称：", parent=self)
        if name and name.strip():
            cid = self.db.create_collection(name.strip())
            self._reload(keep_cid=cid)
            self.on_changed()

    def _rename(self):
        row = self._pick()
        if row is None:
            return
        cid, name, _n = row
        new = simpledialog.askstring(
            CFG.favorites_label, "新名称：", initialvalue=name,
            parent=self)
        if new and new.strip() and new.strip() != name:
            self.db.collection_rename(cid, new.strip())
            self._reload(keep_cid=cid)
            self.on_changed()      # 若重命名的是当前模式夹，主窗口标题同步

    def _delete(self):
        row = self._pick()
        if row is None:
            return
        cid, name, _n = row
        if not messagebox.askyesno(
                CFG.favorites_label,
                f"删除收藏夹「{name}」？（只删索引，项目数据不动）",
                parent=self):
            return
        self.db.delete_collection(cid)
        self._reload()
        self.on_changed()      # 删的若是当前模式夹，主窗口会退出模式

    def _add_selected(self):
        cid = self._selected_cid()
        if cid is None:
            messagebox.showinfo(CFG.favorites_label, "请先选一个收藏夹",
                                parent=self)
            return
        ids = self.app._selected_ids()
        if not ids:
            messagebox.showinfo(
                CFG.favorites_label,
                "先在主表格里选中项目（Ctrl/Shift 可多选）再点这个按钮。",
                parent=self)
            return
        self.db.collection_add(cid, ids)
        self._reload(keep_cid=cid)
        self.on_changed()

    def _lift_me(self, event=None):
        """主窗口任意点击 → 面板抬到主窗口之上（不抢焦点）。"""
        if self.winfo_exists():
            self.lift()

    def _hotkey(self, ev):
        """面板内的快捷键：输入框不抢，其余转给主窗口同一处理。"""
        w = self.focus_get()
        if w is not None and w.winfo_class() in (
                "Entry", "TEntry", "Text", "Spinbox", "TSpinbox"):
            return
        self.app._fav_hotkey(ev)

    def _on_close(self):
        # 恢复主表格单选（多选只是本面板打开期间的服务）
        self.app.tree.configure(selectmode=self._prev_selectmode)
        self.app.unbind("<Button-1>", self._lift_id)
        self.destroy()


def _kind_labels():
    """日历类别显示名：calendar_dates 配置驱动（v2.5.0）。"""
    return {k: l for k, _f, l, _c in CFG.calendar_dates}


def _kind_colors():
    """日历类别颜色：calendar_dates 配置驱动。"""
    return {k: c for k, _f, _l, c in CFG.calendar_dates}


class DayWindow(tk.Toplevel):
    """某天的所有项目时间节点列表，点击打开项目详情。

    items_provider: 无参回调，返回该天条目（跟随当前筛选/模式）。
    从项目详情返回时重新调用 provider 刷新——刚完成的跟进会把项目
    移到别的日期，旧列表不能继续显示（v2.1.7 修复）。"""

    def __init__(self, master, date_str, items_provider, on_open):
        super().__init__(master)
        self.title(f"{date_str} 的时间节点")
        self.transient(master)      # 依附主窗口
        self.on_open = on_open
        self.provider = items_provider
        self.date_str = date_str
        tk.Label(self, text=f"{date_str}", font=("", 11, "bold")).pack(
            padx=12, pady=(10, 4))
        self.items_frame = tk.Frame(self)
        self.items_frame.pack(fill="both", expand=True)
        self._load()
        tk.Label(self).pack(pady=4)
        self.grab_set()             # 强制前置，点不到别处
        self.lift()

    def _load(self):
        """按 provider 最新数据重建条目列表。"""
        for w in self.items_frame.winfo_children():
            w.destroy()
        items = self.provider()
        if not items:
            tk.Label(self.items_frame, text="（当天没有项目时间节点）"
                     ).pack(padx=12, pady=8)
            return
        for e in items:
            tk.Button(self.items_frame, text=e["text"],
                      anchor="w", justify="left",
                      command=lambda p=e: self._open(p)
                      ).pack(fill="x", padx=12, pady=2)

    def _open(self, payload):
        """点开项目：当天列表先藏到后台，项目详情关闭后回来并刷新。"""
        self.withdraw()
        reader = self.on_open(payload)
        if reader is None:
            self._refresh_back()
            return
        reader.bind("<Destroy>",
                    lambda e: self._refresh_back()
                    if e.widget is reader else None, add="+")

    def _refresh_back(self):
        self._load()                # 数据可能已变（跟进完成/项目移动）
        self.deiconify()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
