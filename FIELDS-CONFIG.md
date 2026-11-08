# fields.json 配置详解


**改配置不改代码。关闭软件 → 编辑 → 重启生效。** 五个铁律：

1. 程序只在启动时读配置，运行中不变
2. 新增字段自动补列（`ALTER TABLE`），旧数据原样保留
3. 删字段 = 列留在库里不再使用（SQLite 不支持删列）
4. 改坏 JSON → 启动报错退出，恢复原文件即可
5. `_` 开头的键是注释，程序自动忽略——放心写给人看的话

### 10.0 顶层键总览（按文件顺序）

| 键 | 类型 | 管什么 |
|----|------|--------|
| `product_name` | 字符串 | 窗口标题、通知署名 |
| `db_name` | 字符串 | 数据库文件名（首启创建） |
| `name_fields` | 数组 | 项目名由哪几列拼接 |
| `fields` | 数组 | **数据定义**：字段清单（核心） |
| `status_closed` | 数组 | 哪些状态值算"归档/结案" |
| `calendar_mode` | 字符串 | 日历渲染模式 |
| `split` | 对象 | db_split 输出文件名配方 |
| `default_sort` | 对象 | 跟进表打开时的默认排序 |
| `backup` | 对象 | 备份目录与文件名识别符 |
| `search` | 对象 | 搜索框匹配哪些字段 |
| `import_default_status` | 字符串 | 导入时状态为空的兜底值 |
| `templates` | 数组 | 导入导出模板 |
| `display_mainsheet` | 数组 | 主表：列的原名/别名/开关/筛选/顺序 |
| `weekly_sheet` | 对象 | 周报表格列 |
| `ui` | 对象 | 窗口/字体/列宽/渲染上限/编辑器 |
| `calendar_dates` | 数组 | 日历日期类别（法定四类 + 自定义） |
| `date_check` | 对象 | 保存跟进时的日期范围检查器（可缺省） |
| `favorites` | 对象 | 收藏夹开关与显示名（可缺省 = 关闭） |

### 10.1 `product_name` / `db_name`

```json
"product_name": "日历表格聚合项目跟进工作台",
"db_name": "sales_pm.db"
```

- `product_name`：窗口标题栏、Windows 通知的署名。**改产品名只动
  这一行**——求职版填"求职项目跟进"，实验版填"实验记录本"，
  同一个 exe 行为完全不同。
- `db_name`：数据库文件名。改它等于换新库（旧库文件还在，用
  Database 工具或改回名字继续用）。**不要随意改**——改了之后软件
  会以为自己是空的。

### 10.2 `name_fields`

```json
"name_fields": ["manufacturer", "customer", "product"]
```

项目名的组合配方：按数组顺序取各字段的当前值、用 `-` 连接、空值
跳过。效果：厂家=AdvR、客户=XX水厂、产品=P-100 → 项目名
`AdvR-XX水厂-P-100`。列表、日历、模板"项目"列全部用它。
换产品形态时改这里即可（求职版 = `["customer", "product"]` =
公司-岗位）。

### 10.3 `fields` —— 数据定义（最核心的一段）

数组，每项一个字段，**数组顺序 = 编辑器/详情页/导出的字段顺序**。

```json
{"name": "start_date", "label": "开始日期", "type": "date",
 "calendar": "start", "default": ""}
```

| 键 | 取值 | 配置效果 |
|----|------|---------|
| `name` | 英文字段名 | **数据库列名，创建后不要再改**（改了 = 新列，旧列闲置）。习惯用 snake_case |
| `label` | 中文显示名 | 编辑器标签、列表表头（未配 alias 时）、模板表头默认、筛选弹窗标题 |
| `type` | date / text / choice / status / int / float | **决定行为**：date→日期归一化+区间筛选+日历类别；choice→下拉建议值；status→归档逻辑（见 10.4）；int/float→数值排序+数字校验 |
| `choices` | 字符串数组 | choice/status 的下拉建议值。**仍可自由输入**，只是给建议 |
| `default` | 与 type 匹配的值 | 三处生效：编辑器新建预填、导入补空、导出补空 |
| `multiline` | true | 编辑器给多行大文本框（带滚动条） |
| `height` | 行数 | 编辑器大文本框高度；详情页限高见 `max_lines` |
| `max_lines` | 行数 | 详情页该字段以固定行数+滚动条显示，防长文撑爆窗口 |
| `calendar` | "start" / "followup" / "close" | **旧式**日历类别标记（v2.5.0 起由 `calendar_dates` 段接管，见 10.15）：写了会自动转换成 calendar_dates 配置，新配置的字段不必再写 |

**一个框架里恰好一个** `type: "status"` 的字段——它是唯一影响程序
行为的变量（见下节）。

### 10.4 状态语义：`status_closed` + 状态字段

```json
{"name": "status", "label": "状态", "type": "status",
 "choices": ["跟进中", "成单", "关闭"], "default": "跟进中"},
"status_closed": ["成单", "关闭"]
```

- 状态字段的**建议值列表**随意；`status_closed` 里列出的值是
  "归档"判定：项目从默认列表和日历消失（「显示已关闭」可找回，
  历史全保留）
- 销售版语义：成单/关闭 = 归档；求职版：已Offer/已拒/已放弃 = 归档；
  **逻辑固定，取值可改**——想换成"赢单/丢单"，改两个数组即可
- 存档判断在每次保存快照时执行（`add_snapshot`），改配置后对
  新保存生效

### 10.5 `split` —— db_split 输出文件名配方

```json
"split": {"components": ["field", "key", "time"], "prefix": ""}
```

| 键 | 效果 |
|----|------|
| `components` | 文件名组成部分及顺序：`prefix`(前缀文本) / `field`(键列名) / `key`(键值，空→未分配) / `time`(执行时间 YYYYMMDD-HHMMSS)；空段自动跳过 |
| `prefix` | 前缀文本（如"团队A"），需在 components 里含 "prefix" 才生效 |

默认产出 `厂家_张三_20261020-113000.db`；改
`["prefix", "key"]` + `"prefix": "团队A"` 产出 `团队A_张三.db`。

### 10.6 `default_sort`

```json
"default_sort": {"column": "start_date", "desc": true}
```

跟进表打开时的默认排序。`column` 填字段名或 `"id"`；`desc` true=倒序。
**兜底**：键缺失、column 不是字段也不是 id、类型不对——一律落回
`id 倒序`（最新置顶），永不报错。

### 10.7 `backup`

```json
"backup": {"path": "backups", "identifier": "备份"}
```

- `path`：备份目录。相对路径基于程序目录；支持绝对路径、`~`、中文
- `identifier`：备份文件名中间的识别符，产物为
  `20261020-221530-备份-sales_pm.db`
- 备份用 SQLite 官方在线备份接口，软件运行中也能安全执行

### 10.8 `search`

```json
"search": {"fields": ["customer", "city", "product", ...]}
```

搜索框匹配的字段范围（子串、不区分大小写、多关键词空格 AND）。
增删字段名即可调整；这些字段命中时列表标红点。

### 10.9 `import_default_status`

导入时某行状态为空 → 自动填这个值。销售版"跟进中"，求职版"投递中"。

### 10.10 `templates` —— 导入导出模板

数组，每项一个模板，模板选择器按顺序显示。三种形态：

**① 全量模板**

```json
{"name": "通用", "columns": "all"}
```

= 全部字段按 fields 顺序。导入导出完全可逆，适合备份迁移。

**② 字段模板**（客户/外部格式）

```json
{"name": "十四列模板", "defaults": {"manufacturer": ""},
 "columns": [
   {"field": "start_date", "label": "开始时间"},
   {"field": "customer",   "label": "终端客户"},
   {"label": "拥有者", "const": ""}
 ]}
```

| 键 | 效果 |
|----|------|
| 列 `field` | 该列对应的数据库字段（表头可用 label 改成对方习惯的措辞） |
| 列 `label` | 导出表头/导入匹配名；不写 = 字段默认 label |
| 列 `label+const`（无 field） | **不在库里的列**：导出填 const 值，导入忽略（如"拥有者"） |
| `defaults` | 导入时给字段的固定赋值：文件里没有这列也能统一填（如全表厂家） |

导入匹配规则：表头与"模板 label 或字段默认 label"一致即对上
（两种写法都认）。

**③ 周报模板**（导出专用）

```json
{"name": "周报", "kind": "weekly", "columns": [
  {"date": "snapshot_at", "label": "日期"},
  {"name": true, "label": "项目"},
  {"field": "followup_note", "label": "跟进记录"},
  {"field": "change_summary", "label": "改动说明"}
]}
```

`kind: "weekly"` 表示周报导出专用（不出现在通用导入导出选择器，
**不可导入**）。列的三种键：`date`=追加时间列（snapshot_at）；
`name`=项目名列（按 name_fields 组合）；`field`=普通快照字段。

### 10.11 `display_mainsheet` —— 主表显示配置

数组，每项一列，**数组顺序 = 列顺序**。

```json
{"name": "customer", "alias": "客户方", "on": true, "filter": "range"}
```

| 键 | 取值 | 效果 |
|----|------|------|
| `name` | 字段名或 `"id"` | 该列数据源；id 也是普通条目，可关可改名可挪位 |
| `alias` | 字符串，可空 | 列表表头别名；空 = 字段默认 label |
| `on` | true / false | false = 主表隐藏该列。**数据仍在，导出全量不受影响** |
| `filter` | "list"（默认）/ "range" | 右键筛选形态：勾选清单 / "从~到"日期区间（留空不限、可只填一端） |

规则：没写进这里的新字段自动补到末尾（on=true）；字段级固定列宽
也可在此加 `"width": 200（px，只增不减）`。

### 10.12 `calendar_mode`

```json
"calendar_mode": "all"    // 或 "filtered"
```

- `all`（默认）：日历显示当月所有进行中项目的时间节点
- `filtered`：**跟随表格筛选**——日历只渲染当前筛选/搜索后的项目
  （点"还有N条"/日期弹窗同样跟随，同一数据入口）

### 10.13 `weekly_sheet`

```json
"weekly_sheet": {"columns": ["snapshot_at", "project", "milestone",
                             "status", "probability", "change_summary"]}
```

周报表格的列。内置列：`snapshot_at`（追加时间）、`project`（项目名）、
`change_summary`（改动说明）；其余写字段名。数组顺序 = 列顺序。

### 10.14 `favorites` —— 收藏夹（v2.7.0，可缺省 = 关闭）

```json
"favorites": {"enabled": true, "label": "收藏夹"}
```

- `enabled`：false 时按钮行不出现收藏夹按钮，db 也不建相关表
- `label`：按钮/面板显示名

收藏夹 = **项目 id 的命名集合（纯索引）**，存在 db 文件里
（`collections` / `collection_items` 两张表，旧库打开自动补建），
按库独立。点按钮在按钮下方弹出**非模态**收藏夹面板（可最小化、
不锁主窗口、右上角叉关闭）：左侧夹列表（名称 + 项目数），**双击
夹名进入筛选**；右侧新建/重命名/删除/加入（把主表格选中项目加入
此夹，只写索引不动项目数据）。面板打开期间主表格临时变为多选
（Ctrl/Shift，关闭即恢复单选）；点主窗口任意处面板自动抬回主窗口
之上，不会沉到后面。
进入收藏夹模式后主表格和日历**同步**只显示夹内项目（与列筛选、
搜索叠加），列表上方出现模式横幅（与"共 N 条"同一行）和
"退出收藏夹模式"按钮，**窗口
标题栏追加夹名**；快捷键 **Ctrl+1~9 直达前 9 个收藏夹、Ctrl+0
退出模式**（输入框内不抢键）；进入模式后「导入 / 导出」
置灰（v3.3.5：收藏夹是纯索引视图，导入导出永远是全库操作）。
周报模式同样联动：周报表格、周报
日历（追加记录）、周报导出都只含夹内项目，模式内可自由切换两种
视图；周报下搜索词会匹配项目名列；**周报模式下"加入/移出"按钮
禁用（置灰）**；收藏夹模式下「导入 / 导出」同样置灰
（v3.3.5，替代旧表述"跟进表导出不受模式影响"）；重启软件自动退出模式。

### 10.15 `calendar_dates` —— 日历日期类别（本软件特色）

```json
"calendar_dates": [
  {"key": "start",    "field": "start_date",    "label": "开始", "color": "#2e7d32",  "show_calendar": true},
  {"key": "followup", "field": "next_followup", "label": "跟进", "color": "#1565c0", "show_calendar": true},
  {"key": "close",    "field": "close_date",    "label": "关闭", "color": "#c62828", "show_calendar": true},
  {"key": "append",   "label": "追加", "color": "#6a1b9a", "show_calendar": true},
  {"key": "tapeout",  "field": "tapeout", "label": "流片", "color": "#e65100", "show_calendar": true}
]
```

**一个项目挂多个日期，每个日期都能在日历上点击找到项目**——这是
本工作台区别于 Excel 的核心体验，全部由此段配置驱动：

- 法定四类必须有：`start` / `followup` / `close`（各绑定一个
  date 类型字段）+ `append`（追加记录，无字段，用快照时间，
  周报模式用）；缺任何一类启动报错并指明缺谁
- 四类之后的条目 = **自由增加的日期类别**：任意 date 字段 +
  自定义 key / 显示名 / 颜色（如示例的"流片"）
- 每项五键：`key` 类别标识、`field` 日期字段名（append 省略）、
  `label` 日历与弹窗显示名、`color` 条目颜色 `#RRGGBB`、
  `show_calendar` 该类日期是否上日历（false = 数据保留但日历不显示；
  表格显隐与列顺序由 display_mainsheet 管）
- 说明文字（法定四类要求、追加格式等）写在数组外的 `_` 开头注释键里，
  数组条目内只保留上述配置键
- 不写此段时自动从旧式配置（字段上的 calendar 标记）转换

### 10.16 `ui` —— 界面参数

| 键 | 默认 | 效果 |
|----|------|------|
| `window.width / height / margin_x / margin_y` | 1480/860/80/120 | 窗口尺寸上限与屏幕边距（按屏幕自适应取小） |
| `font.default` | 12 | 全局字体（磅） |
| `font.tree_rowheight` | 38 | 列表行高（px） |
| `font.heading_size` | 13 | 表头字号 |
| `columns.min_width / max_width` | 70 / 360 | 列宽上下限（配合只增不减规则） |
| `calendar.max_per_day` | 1 | 聚合视图（含周报模式）日历每格最多显示几条；更多折叠为"还有N条"（v3.4.2 起真正生效，此前存而未用） |
| `calendar.max_per_day_view` | 5 | 纯日历视图（`--view calendar`）每格最多显示几条；可配 1~5，缺本键按 5 处理（v3.4.2） |
| `calendar_labels.start / followup / close` | 开始/跟进/关闭 | **兼容项**：Windows 通知文案仍读它；日历上的显示名与颜色以 calendar_dates 段为准（求职版可改"投递/检查点/结项"） |
| `editor.width / height / entry_width / text_width` | 840/940/52/50 | 编辑器窗口与输入框尺寸 |
| `render_limit` | 600 | **每页渲染行数**（翻页式；30万条与600条翻页同速） |
| `default_view` | 无（=aggregate） | 启动视图缺省：`aggregate`（聚合）/ `calendar`（仅日历）/ `table`（仅表格）；被 `--view` 覆盖（v3.2.0） |

### 10.17 `recycle_bin` —— 回收站（v3.1.0，可缺省 = 关闭）

```json
"recycle_bin": {"enabled": true}
```

- `enabled`：true（本发布包内置配置已开启）时删除 = **项目 + 全部快照
  + 收藏夹索引整体移入回收站**；false 时删除 = 物理删除，与 v2.7.3 完全
  等价；整段缺省时按 false 处理（老配置文件不加这段，行为零变化）
  （独立表 `recycled_*`，主表格/日历/周报/导出/通知全部天然不再
  显示），删除确认框会说明"可在回收站中恢复"
- 主程序**只管删进去**；查看/恢复/彻底删除由独立模块负责，
  命令行与 GUI 双入口：

```bash
python -m db_recycled xxx.db            # 列出回收站
python -m db_recycled xxx.db --restore 12    # 恢复（id 空闲则原位放回）
python -m db_recycled xxx.db --restore all   # 全部恢复
python -m db_recycled xxx.db --purge 12      # 永久删除单个
python -m db_recycled xxx.db --empty         # 清空回收站
python -m db_recycled xxx.db --gui           # 图形界面（恢复/红色永久删除）
```

- 恢复时原 id 已被新项目占用才分配新 id（收藏夹索引跟着指向新 id）；
- **彻底删除（purge/empty）= 物理销毁、不可恢复**，GUI 中是红色
  按钮 + 二次确认弹窗；命令行不给确认，执行即销毁；
- 回收站随 .db 文件走（复制/备份库 = 连同回收站一起）。

### 10.18 建议：用 AI 来改配置

fields.json 是"人意图"和"程序"之间的协议层。推荐工作流：把
fields.json 和需求发给 AI（如"加一列'竞争对手'，字符串，放简述
后面"）→ 贴回 → 重启生效；启动报错就把报错发回给 AI。本文档
就是写给 AI 看的说明书。

## 附录：SQL 速查（贴合本框架）

数据模型：`projects` + `snapshots`（一条跟进一行），平铺、ISO 日期。
DB Browser for SQLite 打开 `.db` 即可练习：

```sql
-- ① 项目列表（界面骨架）
SELECT p.id, p.title, s.milestone, s.status, s.next_followup
FROM projects p JOIN snapshots s ON s.id = p.current_id
WHERE p.status = 'open' ORDER BY p.id;
-- ② 单项目历史（详情页时间线）
SELECT * FROM snapshots WHERE project_id = 5 ORDER BY snapshot_at;
-- ③ 周报区间取数
SELECT s.*, p.title FROM snapshots s JOIN projects p ON p.id = s.project_id
WHERE date(s.snapshot_at) BETWEEN '2026-10-12' AND '2026-10-18';
-- ④ 更新 = 追加新快照（本框架从不用 UPDATE 改历史）
BEGIN;
INSERT INTO snapshots(project_id, snapshot_at, followup_note, status)
VALUES (5, datetime('now','localtime'), '本次跟进内容', '跟进中');
UPDATE projects SET current_id = last_insert_rowid() WHERE id = 5;
COMMIT;
-- ⑤ 项目聚合
SELECT p.title, COUNT(*) AS n, MAX(s.snapshot_at) AS last
FROM projects p JOIN snapshots s ON s.project_id = p.id
GROUP BY p.id ORDER BY last DESC;
-- ⑥ 索引排查
EXPLAIN QUERY PLAN SELECT * FROM snapshots WHERE project_id = 5;
-- ⑦ 收藏夹（favorites 开启时建表；纯索引，删夹/删项目级联清索引）
SELECT c.name AS 收藏夹, COUNT(i.project_id) AS 项目数
FROM collections c LEFT JOIN collection_items i ON i.collection_id = c.id
GROUP BY c.id;
```
