# -*- coding: utf-8 -*-
"""数据库层：SQLite，只负责存取，不认识任何 GUI。

对外暴露 Database 类。数据结构（与已确认的设计一致）：
  projects   项目主表，只管"当前指针"和开关状态
  snapshots  快照表，一次跟进 = 一条完整快照，只增不改
"""
import re
import sqlite3

from config import CFG

# 快照中的业务字段（平铺，便于外部工具阅读和 diff）——由 fields.json 配置驱动
SNAPSHOT_FIELDS = CFG.names
# 兼容旧引用
MILESTONES = CFG.choice_fields.get("milestone", [])
STATUS_OPTIONS = CFG.status_options

_SQL_TYPES = {"date": "TEXT", "int": "INTEGER", "float": "REAL",
              "text": "TEXT", "choice": "TEXT", "status": "TEXT"}


def _schema_sql():
    cols = ",\n    ".join(
        f"{f['name']} {_SQL_TYPES[f['type']]}" for f in CFG.fields)
    return f"""
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',      -- open / closed
    current_id  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    snapshot_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
{cols},
    changed_by      TEXT,
    change_summary  TEXT
);

CREATE INDEX IF NOT EXISTS idx_snap_project
    ON snapshots(project_id, snapshot_at);
"""

_SCHEMA = _schema_sql()


_DATE_RE = re.compile(
    r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})")
_FW_MAP = {0xFF01 + i: 0x21 + i for i in range(94)}  # 全角->半角（键必须是整数码点）


def normalize_date(s):
    """各种日期写法统一成 YYYY-MM-DD；无法识别返回 None。

    兼容全角字符（２０２６／３／１９）和中文（2026年3月19日）。
    """
    if not s:
        return None
    s = str(s).strip().translate(_FW_MAP)
    m = _DATE_RE.match(s)
    if m:
        return (f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
                f"-{int(m.group(3)):02d}")
    return None


def diff_summary(old, new):
    """对比两份快照（dict/Sqlite Row），生成一句话改动说明。

    例: "里程碑: Lead → Quotation; 金额: 10 → 20"
    old 为 None 时返回 "创建项目"。
    """
    if old is None:
        return "创建项目"
    changes = []
    for f in SNAPSHOT_FIELDS:
        if isinstance(old, dict):
            ov = old.get(f)
        else:                      # sqlite3.Row
            ov = old[f] if f in old.keys() else None
        nv = new.get(f)
        if str(ov or "") != str(nv or ""):
            changes.append(f"{f}: {ov} → {nv}")
    return "; ".join(changes) if changes else "无字段变化（仅跟进记录）"


class Database:
    def __init__(self, path="sales_pm.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self._reconcile_columns()
        # _migrate 已于 v1.5.5 停用（见下方注释），保留调用点仅作记录。
        # self._migrate()

    def _reconcile_columns(self):
        """核对配置与表结构：fields.json 里新增的字段时间自动补列。
        SQLite 不支持删列，配置里去掉的字段列会留在表中不再使用。"""
        existing = {r[1] for r in self.conn.execute(
            "PRAGMA table_info(snapshots)")}
        with self.conn:
            for f in CFG.fields:
                if f["name"] not in existing:
                    self.conn.execute(
                        f"ALTER TABLE snapshots ADD COLUMN "
                        f"{f['name']} {_SQL_TYPES[f['type']]}")

    # ==================== v1.5.5 起停用（保留代码仅供考古） ====================
    # 停用原因：这套迁移面向 v1.0 时代的旧库债——
    #   ① 补 status/fail_reason 列：新库建表语句已含，永远走不到
    #   ② 重建表去 CHECK：新库建表已不含 CHECK，永远走不到
    #   ③ 自定义标题回填：标题自动命名自 v1.2 起已稳定
    #   ④ 脏日期清洗：所有用户都经 GUI 录入、库随最新版一直在线，
    #      数据天然是干净的
    # 若将来遇到需要从旧格式迁移的真实需求，做成独立的 db_migrate
    # 命令行工具（见 development_project.md 1.5），而不是常驻启动路径。
    # def _migrate(self):
    def _migrate_DEPRECATED(self):
        """旧数据库迁移（全部幂等）：
        1. 补充新增字段  2. 重建表去掉里程碑 CHECK  3. 标题改为自动命名
        """
        for col, decl in (("status", "TEXT"), ("fail_reason", "TEXT")):
            try:
                self.conn.execute(
                    f"ALTER TABLE snapshots ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass   # 列已存在
        # 2. 旧表带 CHECK(milestone ...)：重建去掉
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='snapshots'").fetchone()
        if row and "CHECK" in row[0]:
            with self.conn:
                self.conn.executescript("""
                    ALTER TABLE snapshots RENAME TO snapshots_old;
                """)
                self.conn.executescript(_SCHEMA)
                want = ["id", "project_id", "snapshot_at"] \
                    + SNAPSHOT_FIELDS + ["changed_by", "change_summary"]
                old_cols = {r[1] for r in self.conn.execute(
                    "PRAGMA table_info(snapshots_old)")}
                common = [c for c in want if c in old_cols]
                # 按名称显式映射，不依赖列顺序；配置新增列自动为 NULL
                self.conn.execute(
                    f"INSERT INTO snapshots({','.join(common)}) "
                    f"SELECT {','.join(common)} FROM snapshots_old")
                self.conn.execute("DROP TABLE snapshots_old")
        # 3. 标题自动命名：厂家-客户-产品，取不到的保留原标题
        #    （仅当这三个字段都存在时执行，自定义字段集的产品跳过）
        cols3 = {r[1] for r in self.conn.execute(
            "PRAGMA table_info(snapshots)")}
        if set(CFG.name_fields) <= cols3 and CFG.name_fields:
            sel = ", ".join(f"s.{n}" for n in CFG.name_fields)
            for p in self.conn.execute("SELECT id, title FROM projects"):
                cur = self.conn.execute(
                    f"""SELECT {sel} FROM snapshots s
                        JOIN projects j ON j.current_id = s.id
                        WHERE j.id=?""", (p["id"],)).fetchone()
                if cur:
                    name = "-".join(x for x in cur if x)
                    if name:
                        self.conn.execute(
                            "UPDATE projects SET title=? WHERE id=?",
                            (name, p["id"]))
        # 4. 历史脏数据修复：快照里的日期统一为 YYYY-MM-DD
        for f in CFG.date_fields:
            for row in self.conn.execute(
                    f"SELECT id, {f} FROM snapshots WHERE {f} IS NOT NULL"):
                v = row[f]
                if isinstance(v, str) and not re.match(
                        r"^\d{4}-\d{2}-\d{2}$", v):
                    nv = normalize_date(v)
                    if nv:
                        self.conn.execute(
                            f"UPDATE snapshots SET {f}=? WHERE id=?",
                            (nv, row["id"]))
        self.conn.commit()

    # ---------- 项目 ----------
    def create_project(self, changed_by="", change_summary="", **fields):
        """新建项目 = 项目行 + 第一条快照，一个事务。
        项目名自动生成：厂家-客户-产品（取不到的字段跳过）。
        字段默认值（fields.json 的 default）在新建时兜底，显式传值优先；
        后续的添加跟进不套默认值，允许有意清空。"""
        fields = {**CFG.field_defaults, **fields}
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO projects(title) VALUES ('')")
            pid = cur.lastrowid
            self._insert_snapshot(
                pid, changed_by,
                change_summary or diff_summary(None, fields), fields)
            return pid

    def list_projects(self, include_closed=False):
        fields = ", ".join(f"s.{f}" for f in SNAPSHOT_FIELDS)
        sql = f"""
        SELECT p.id, p.title, p.created_at, {fields}
        FROM projects p
        LEFT JOIN snapshots s ON s.id = p.current_id
        """
        if not include_closed:
            sql += " WHERE p.status = 'open'"
        sql += " ORDER BY p.id DESC"
        return self.conn.execute(sql).fetchall()

    def get_project(self, project_id):
        return self.conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()

    def get_current(self, project_id):
        """当前快照（完整状态）。"""
        return self.conn.execute(
            """SELECT s.* FROM snapshots s
               JOIN projects p ON p.current_id = s.id
               WHERE p.id=?""", (project_id,)).fetchone()

    def set_status(self, project_id, status):
        with self.conn:
            self.conn.execute("UPDATE projects SET status=? WHERE id=?",
                              (status, project_id))

    def delete_project(self, project_id):
        """彻底删除项目及其全部快照历史（需调用方二次确认）。"""
        with self.conn:
            self.conn.execute("DELETE FROM snapshots WHERE project_id=?",
                              (project_id,))
            self.conn.execute("DELETE FROM projects WHERE id=?",
                              (project_id,))

    # ---------- SQL 化列表查询（v2.1：筛选/搜索/排序/分页下沉 SQLite） ----------
    def _build_where(self, filters=None, keywords=None,
                     search_fields=None):
        """把筛选/搜索状态翻译成 WHERE 片段。返回 (where_sql, args)。"""
        where, args = [], []
        for c, spec in (filters or {}).items():
            if spec is None or c == "id":
                continue
            if isinstance(spec, tuple):            # 日期区间 (d1, d2)
                d1, d2 = spec
                cond = [f"cur.{c} <> ''"]
                if d1:
                    cond.append(f"date(cur.{c}) >= ?")
                    args.append(d1)
                if d2:
                    cond.append(f"date(cur.{c}) <= ?")
                    args.append(d2)
                where.append("(" + " AND ".join(cond) + ")")
            else:                                  # 勾选集合
                vals = [str(v) for v in spec]
                if not vals:
                    where.append("1=0")            # 空集 = 全不显示
                    continue
                where.append(f"cur.{c} IN ({','.join('?' * len(vals))})")
                args += vals
        for kw in (keywords or []):
            like = "%" + kw.casefold() + "%"
            ors = []
            for f in (search_fields or []):
                if f in SNAPSHOT_FIELDS:
                    ors.append(f"LOWER(CAST(cur.{f} AS TEXT)) LIKE ?")
                    args.append(like)
            if ors:
                where.append("(" + " OR ".join(ors) + ")")
        return where, args

    def query_projects(self, filters=None, keywords=None,
                       search_fields=None, sort=None, sort_desc=False,
                       include_closed=False, offset=0, limit=None,
                       cols=None):
        """列表查询：筛选/搜索/排序/分页全部在 SQLite 完成（v2.1）。

        filters   {列名: set(勾选) 或 (d1,d2)(日期区间)}
        keywords  搜索词列表（AND 语义，字段间 OR）
        sort      列名；"id" 或字段名；数字按值、文本按不区分大小写，
                  与旧 Python 排序语义一致（typeof 分组）
        返回 (当前页 [dict], 全量匹配数 int)
        """
        cols = cols or SNAPSHOT_FIELDS
        sel = ", ".join(f"cur.{c}" for c in cols)
        where, args = self._build_where(filters, keywords, search_fields)
        if not include_closed:
            where.append("p.status='open'")
        wh = ("WHERE " + " AND ".join(where)) if where else ""
        base = (f"FROM projects p "
                f"JOIN snapshots cur ON cur.id = p.current_id {wh}")
        total = self.conn.execute(
            f"SELECT COUNT(*) {base}", args).fetchone()[0]
        order = ""
        if sort:
            col = "p.id" if sort == "id" else f"cur.{sort}"
            flag = f"(typeof({col}) NOT IN ('integer','real'))"
            num = (f"CASE WHEN typeof({col}) IN ('integer','real') "
                   f"THEN CAST({col} AS REAL) END")
            txt = (f"CASE WHEN typeof({col}) NOT IN ('integer','real') "
                   f"THEN {col} END COLLATE NOCASE")
            d = "DESC" if sort_desc else "ASC"
            order = f"ORDER BY {flag} {d}, {num} {d}, {txt} {d}"
        lim = ""
        if limit is not None:
            lim = f"LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = self.conn.execute(
            f"SELECT p.id, p.title, {sel} {base} {order} {lim}",
            args).fetchall()
        out = []
        for r in rows:
            d_ = {"id": r["id"], "title": r["title"]}
            for c in cols:
                d_[c] = r[c] if r[c] is not None else ""
            out.append(d_)
        return out, total

    def query_project_ids(self, filters=None, keywords=None,
                          search_fields=None, include_closed=False):
        """只取匹配的项目 id 列表（日历 filtered 模式用，轻量）。"""
        where, args = self._build_where(filters, keywords, search_fields)
        if not include_closed:
            where.append("p.status='open'")
        wh = ("WHERE " + " AND ".join(where)) if where else ""
        return [r[0] for r in self.conn.execute(
            f"SELECT p.id FROM projects p "
            f"JOIN snapshots cur ON cur.id = p.current_id {wh}",
            args)]

    # ---------- 周报模式（只读视图：数据唯一入口是跟进表） ----------
    def snapshots_between(self, d1, d2):
        """时间区间内的全部快照（周报取数，按天含端点，时间正序）。"""
        return self.conn.execute(
            """SELECT s.*, p.title AS ptitle, p.status AS pstatus
               FROM snapshots s JOIN projects p ON p.id = s.project_id
               WHERE date(s.snapshot_at) BETWEEN ? AND ?
               ORDER BY s.snapshot_at, s.id""", (d1, d2)).fetchall()

    def calendar_entries_for(self, project_ids, year, month):
        """只给指定项目集合供给日历条目（filtered 模式用）。"""
        if not project_ids:
            return []
        # show_calendar=false 的类别不上日历（v2.6.0 显示开关）
        date_items = [(k, f) for k, f, _l, _c in CFG.calendar_dates
                      if f and CFG.calendar_show.get(k, True)]
        cal_names = [f for _k, f in date_items]
        name_cols = [c for c in CFG.name_fields if c in SNAPSHOT_FIELDS]
        select_cols = ", ".join(f"s.{c}" for c in cal_names + name_cols)
        ph = ",".join("?" * len(project_ids))
        prefix = f"{year:04d}-{month:02d}"
        kind_tag = {k: l for k, _f, l, _c in CFG.calendar_dates}
        rows = self.conn.execute(
            f"""SELECT p.id AS pid, p.title, {select_cols}
                FROM projects p
                JOIN snapshots s ON s.id = p.current_id
                WHERE p.status='open' AND p.id IN ({ph})""",
            list(project_ids)).fetchall()
        entries = []
        for r in rows:
            name = "-".join(x for x in (r[c] for c in name_cols) if x) \
                or r["title"]
            for kind, col in date_items:
                d = r[col]
                if d and d.startswith(prefix):
                    entries.append({
                        "date": d, "kind": kind,
                        "text": f"[{kind_tag.get(kind, kind)}] {name}",
                        "project_id": r["pid"],
                    })
        return entries

    def calendar_snapshots(self, year, month):
        """周报模式的日历供给：该月每天的追加记录。
        条目格式与跟进表日历一致，kind 恒为 "append"。"""
        prefix = f"{year:04d}-{month:02d}"
        rows = self.conn.execute(
            """SELECT s.id AS sid, s.snapshot_at, s.project_id, p.title
               FROM snapshots s JOIN projects p ON p.id = s.project_id
               WHERE s.snapshot_at LIKE ? || '%'
               ORDER BY s.snapshot_at""", (prefix,)).fetchall()
        return [{"date": r["snapshot_at"][:10], "kind": "append",
                 "text": r["title"], "project_id": r["project_id"],
                 "snapshot_id": r["sid"]} for r in rows]

    def weekly_plan(self, d1, d2, include_closed=False):
        """下周计划：next_followup 落在 [d1,d2] 的项目当前状态。"""
        wh = "" if include_closed else "AND p.status='open'"
        fields = ", ".join(f"cur.{f}" for f in SNAPSHOT_FIELDS)
        return self.conn.execute(
            f"""SELECT p.id, p.title, {fields},
                       cur.change_summary AS change_summary
                FROM projects p
                LEFT JOIN snapshots cur ON cur.id = p.current_id
                WHERE date(cur.next_followup) BETWEEN ? AND ? {wh}
                ORDER BY cur.next_followup""", (d1, d2)).fetchall()

    def find_project_by_title(self, title):  # noqa: D102 保留公共查询
        return self.conn.execute(
            "SELECT id FROM projects WHERE title=?",
            (title.strip(),)).fetchone()

    # ---------- 快照 ----------
    def _insert_snapshot(self, project_id, changed_by, summary, fields):
        cols = ["project_id", "changed_by", "change_summary"] + SNAPSHOT_FIELDS
        vals = [project_id, changed_by, summary] + \
               [fields.get(f) or None for f in SNAPSHOT_FIELDS]
        cur = self.conn.execute(
            f"INSERT INTO snapshots({','.join(cols)}) "
            f"VALUES ({','.join('?'*len(cols))})", vals)
        sid = cur.lastrowid
        # 业务状态联动项目开关：status_closed 里配置的值 = 归档
        pstatus = ("closed"
                   if fields.get(CFG.status_field) in CFG.status_closed
                   else "open")
        # 项目名自动更新：厂家-客户-产品，全空则保留原名
        # 项目名 = 配置字段按序拼接（默认 厂家-客户-产品，JSON 的 name_fields 可改）
        name = "-".join(str(fields.get(f) or "")
                        for f in CFG.name_fields
                        if fields.get(f))
        if not name:                      # 组合字段全空时兜底编号
            name = f"项目{project_id}"
        self.conn.execute(
            "UPDATE projects SET current_id=?, status=?, title=? "
            "WHERE id=?", (sid, pstatus, name, project_id))
        return sid

    def add_snapshot(self, project_id, changed_by="", change_summary="",
                     **fields):
        """保存一次跟进 = 插入完整快照 + 更新当前指针。"""
        old = self.get_current(project_id)
        summary = change_summary or diff_summary(old, fields)
        with self.conn:
            return self._insert_snapshot(project_id, changed_by, summary,
                                         fields)

    def get_snapshots(self, project_id):
        return self.conn.execute(
            "SELECT * FROM snapshots WHERE project_id=? ORDER BY snapshot_at",
            (project_id,)).fetchall()

    # ---------- 日历供给 ----------
    def calendar_entries(self, year, month):
        """给日历组件的数据：当月内所有 open 项目的关键日期。

        返回 list[dict]: date('YYYY-MM-DD'), text, kind, project_id
        日历组件不认识项目，只认这三个字段 + payload。
        """
        prefix = f"{year:04d}-{month:02d}"
        # 日历类别全配置化（v2.5.0 calendar_dates）：字段/显示名/颜色
        # show_calendar=false 的类别不上日历（v2.6.0 显示开关）
        date_items = [(k, f) for k, f, _l, _c in CFG.calendar_dates
                      if f and CFG.calendar_show.get(k, True)]
        cal_names = [f for _k, f in date_items]
        # 项目名组合字段由 JSON 的 name_fields 配置（空值跳过）
        name_cols = [c for c in CFG.name_fields if c in SNAPSHOT_FIELDS]
        select_cols = ", ".join(f"s.{c}" for c in cal_names + name_cols)
        rows = self.conn.execute(
            f"""SELECT p.id AS pid, p.title, {select_cols}
                FROM projects p
                JOIN snapshots s ON s.id = p.current_id
                WHERE p.status='open'""").fetchall()
        label_of = {k: l for k, _f, l, _c in CFG.calendar_dates}
        entries = []
        for r in rows:
            name = "-".join(x for x in (r[c] for c in name_cols) if x) \
                or r["title"]
            for kind, col in date_items:
                d = r[col]
                if d and d.startswith(prefix):
                    entries.append({
                        "date": d, "kind": kind,
                        "text": f"[{label_of.get(kind, kind)}] {name}",
                        "project_id": r["pid"],
                    })
        return entries

    def close(self):
        self.conn.close()
