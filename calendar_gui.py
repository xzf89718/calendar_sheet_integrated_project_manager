# -*- coding: utf-8 -*-
"""通用日历组件（Tkinter）。

不认识任何业务：只管显示"日期 + 文本条目"，通过回调与外界通信。
  get_entries(year, month) -> [dict(date,text,kind,payload...)]
  on_entry_click(payload)  点击条目
  on_day_click(date_str)   点击空白日期

项目管理、日程排布两个软件各自提供 get_entries 即可共用本组件。
"""
import calendar
import tkinter as tk
from datetime import date

KIND_COLORS = {          # kind -> 颜色，调用方可覆盖
    "default": "#333333",
    "start":   "#2e7d32",
    "followup": "#1565c0",
    "close":   "#c62828",
    "append":  "#6a1b9a",     # 周报模式的追加记录（紫）
}

WEEK = ["一", "二", "三", "四", "五", "六", "日"]


class CalendarWidget(tk.Frame):
    def __init__(self, master, get_entries,
                 on_entry_click=None, on_day_click=None,
                 colors=None, max_per_day=1):
        """通用日历组件构造：不认识任何业务，只管显示"日期 + 文本条目"。

        通过回调与外界通信：get_entries(year, month) 供给条目，
        on_entry_click/on_day_click 响应点击。kind 颜色可覆盖，每格最多
        "日期 + max_per_day 个条目 + 1 条更多链接"。

        :param master: 父容器
        :type master: tkinter.Misc
        :param get_entries: 条目供给回调，接收年月，返回条目 dict 列表
        :type get_entries: callable
        :param on_entry_click: 点条目回调（可空）
        :type on_entry_click: callable 或 None
        :param on_day_click: 点日期回调（可空）
        :type on_day_click: callable 或 None
        :param colors: kind -> 颜色 覆盖表
        :type colors: dict 或 None
        :param max_per_day: 每格最多显示的条目数
        :type max_per_day: int
        """
        super().__init__(master)
        self.get_entries = get_entries
        self.on_entry_click = on_entry_click
        self.on_day_click = on_day_click
        self.colors = dict(KIND_COLORS, **(colors or {}))
        self.max_per_day = max_per_day
        today = date.today()
        self.year, self.month = today.year, today.month
        self._build()

    # ---------- 界面 ----------
    def _build(self):
        """重建界面：头部（< 年月 > / 今天 / 跳转）+ 星期表头 + 6x7 格子，随后 refresh。"""
        for w in self.winfo_children():
            w.destroy()
        # 头部： < 2026年10月 >
        head = tk.Frame(self)
        head.pack(fill="x")
        tk.Button(head, text="<", width=3,
                  command=lambda: self._shift(-1)).pack(side="left")
        self.lbl = tk.Label(head, font=("Microsoft YaHei", 16, "bold"))
        self.lbl.pack(side="left", expand=True)
        tk.Button(head, text=">", width=3,
                  command=lambda: self._shift(1)).pack(side="right")
        tk.Button(head, text="今天", command=self._today).pack(side="right")
        tk.Button(head, text="跳转", command=self._jump).pack(side="right",
                                                              padx=2)
        # 星期表头
        grid = tk.Frame(self)
        grid.pack(fill="both", expand=True)
        for i, w in enumerate(WEEK):
            tk.Label(grid, text=w, bg="#eeeeee").grid(
                row=0, column=i, sticky="nsew", padx=1, pady=1)
        for i in range(7):
            grid.columnconfigure(i, weight=1, uniform="c")
        self._cells = []
        for r in range(6):
            grid.rowconfigure(r + 1, weight=1, uniform="r")
            for c in range(7):
                cell = tk.Frame(grid, bd=1, relief="solid", bg="white")
                cell.grid(row=r + 1, column=c, sticky="nsew", padx=1, pady=1)
                self._cells.append(cell)
        self.refresh()

    def _shift(self, delta):
        """翻月（delta=±1 或跨任意月数），跨年自动进位。

        :param delta: 月偏移量
        :type delta: int
        """
        m = self.month + delta
        y = self.year + (m - 1) // 12
        self.month = (m - 1) % 12 + 1
        self.year = y
        self.refresh()

    def _today(self):
        """回到本月（系统当前年月）并刷新。"""
        t = date.today()
        self.year, self.month = t.year, t.month
        self.refresh()

    def _entry(self, e):
        """条目点击分发：有回调则转给 on_entry_click。

        :param e: 被点条目 dict
        :type e: dict
        """
        if self.on_entry_click:
            self.on_entry_click(e)

    def _day(self, ds):
        """日期点击分发：有回调则转给 on_day_click。

        :param ds: 日期（YYYY-MM-DD）
        :type ds: str
        """
        if self.on_day_click:
            self.on_day_click(ds)

    def _jump(self):
        """弹出跳转对话框，确认后经 _jump_to 落位。"""
        JumpDialog(self, self.year, self.month, on_ok=self._jump_to)

    def _jump_to(self, year, month, day):
        """跳转到指定年月；填了日则直接弹出当天明细。

        :param year: 目标年
        :type year: int
        :param month: 目标月
        :type month: int
        :param day: 目标日；0 表示不弹当天明细
        :type day: int
        """
        self.year, self.month = year, month
        self.refresh()
        if day:                       # 填了日 -> 直接弹出当天明细
            self._day(f"{year:04d}-{month:02d}-{day:02d}")

    # ---------- 数据 ----------
    def refresh(self):
        """按当前年月重新取数并渲染：月标题、实际周数（多余的格子隐藏压缩总高）、
        今日高亮、逐格条目与"还有N条"链接。数据变化后调用本方法即可。"""
        self.lbl.config(text=f"{self.year}年{self.month}月")
        cal = calendar.Calendar(firstweekday=0)   # 周一开头
        days = [d for week in cal.monthdatescalendar(self.year, self.month)
                for d in week]
        entries = {}
        for e in self.get_entries(self.year, self.month):
            entries.setdefault(e["date"], []).append(e)
        today = date.today().isoformat()
        # 只显示本月实际周数（5或6行），多余的格子隐藏，压缩总高
        nweeks = len(cal.monthdatescalendar(self.year, self.month))
        for idx, cell in enumerate(self._cells):
            if idx < nweeks * 7:
                cell.grid()
            else:
                cell.grid_remove()
        for cell, d in zip(self._cells, days):
            for w in cell.winfo_children():
                w.destroy()
            in_month = (d.month == self.month)
            cell.config(bg="white" if in_month else "#f7f7f7")
            ds = d.isoformat()
            num = tk.Label(cell, text=str(d.day), anchor="w",
                           bg=cell["bg"], font=("", 11), pady=0,
                           fg="#333333" if in_month else "#bbbbbb")
            if ds == today:
                num.config(fg="#d32f2f", font=("", 12, "bold"))
            # 点日期数字 = 查看当天所有条目
            num.bind("<Button-1>", lambda ev, s=ds: self._day(s))
            num.pack(fill="x")
            # 每格最多"日期 + max_per_day 个条目 + 1 条更多链接"（v3.4.2：
            # max_per_day 分视图取值，聚合 1 条紧凑样式、纯日历可到 5 条），
            # 看当天全部：点"还有N条"链接或日期数字。
            day_items = entries.get(ds, [])
            if day_items:
                for e in day_items[:self.max_per_day]:
                    color = self.colors.get(e.get("kind", "default"),
                                            self.colors["default"])
                    tk.Button(cell, text=e["text"][:22], anchor="w",
                              bg=color, fg="white", relief="flat",
                              padx=2, pady=0, font=("", 10),
                              command=lambda p=e: self._entry(p)
                              ).pack(fill="x", padx=1)
                more = len(day_items) - min(len(day_items), self.max_per_day)
                if more > 0:
                    tk.Button(cell, text=f"还有{more}条 ▸",
                              anchor="w", relief="flat", pady=0,
                              font=("", 10, "bold"),
                              fg="#0d47a1", bg="#e3f2fd",
                              command=lambda s=ds: self._day(s)
                              ).pack(fill="x", padx=1)
            if self.on_day_click:
                cell.bind("<Button-1>",
                          lambda ev, s=ds: self.on_day_click(s))


class JumpDialog(tk.Toplevel):
    """跳转到指定年月日。"""

    def __init__(self, master, year, month, on_ok):
        """跳转到指定年月日的输入弹窗。

        :param master: 父窗口
        :type master: tkinter.Misc
        :param year: 初始年
        :type year: int
        :param month: 初始月
        :type month: int
        :param on_ok: 确认回调 (year, month, day)；day=0 表示未填
        :type on_ok: callable
        """
        super().__init__(master)
        self.title("跳转")
        self.on_ok = on_ok
        frm = tk.Frame(self, padx=12, pady=12)
        frm.pack(fill="both", expand=True)
        self.y = tk.StringVar(value=str(year))
        self.m = tk.StringVar(value=str(month))
        self.d = tk.StringVar()
        for i, (lab, var, width) in enumerate(
                (("年", self.y, 6), ("月", self.m, 4), ("日(可空)", self.d, 4))):
            tk.Label(frm, text=lab).grid(row=0, column=i * 2, sticky="e")
            tk.Entry(frm, textvariable=var, width=width).grid(
                row=0, column=i * 2 + 1, padx=2)
        btns = tk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=6, pady=(8, 0))
        tk.Button(btns, text="确定", command=self._ok).pack(side="left",
                                                            padx=4)
        tk.Button(btns, text="取消", command=self.destroy).pack(side="left")
        self.grab_set()

    def _ok(self):
        """校验年月日合法性（月 1~12、日 0~31）后回调 on_ok 并关闭；非法输入静默停留。"""
        try:
            y = int(self.y.get())
            m = int(self.m.get())
            assert 1 <= m <= 12
            d = int(self.d.get()) if self.d.get().strip() else 0
            assert 0 <= d <= 31
        except (ValueError, AssertionError):
            return
        self.on_ok(y, m, d)
        self.destroy()
