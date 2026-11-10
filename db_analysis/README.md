# db_analysis —— 只读数据分析

只读数据分析统一入口，**绝不写库**（专项测试：跑完库文件哈希
不变）。当前算法：多变量饼图共享筛选；项目分类时间点可视化
（timeline，v3.8.0；v3.8.1 布局重排）。

- 口径：默认统计 open 项目当前行；`--closed` 把已归档也纳入
  （timeline 例外：全量取数，`--split` 时归「已关闭」章）
- 给日期区间时，每个项目取窗口内"当时最新"的快照统计
- 空值归「（空）」段；取值超 `--top`（默认 9）长尾合并「其他」
- date 类型字段可作饼图变量（原值归段）

## 运行

```bash
python -m db_analysis pie --field 字段 [--field 字段2 ...] [--closed] [--top N]
        [--where 字段=值 ...] [--date-field 名]
        [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
        [--png [目录]] [--dump [目录]]

python -m db_analysis timeline [--mode year|rolling] [--cols 4个字段]
        [--colors 4个#RRGGBB] [--sort 字段|diff] [--desc] [--split]
        [--where 字段=值 ...] [--path [目录]] [--dump]
```

### timeline：项目分类时间点可视化（v3.8.0；v3.8.1 重排）

**不叫甘特图**（用户定）：甘特图 = 持续时间条 + 完成百分比 +
依赖关系；本软件只有离散时间点 + 类别，不做进度评估——给证据
不给结论。

**输出形式（v3.8.1 用户定）**：非 dump 模式终端只打印筛选条件 +
统计 + 写出路径，md 恒写出为文件（`--path` 缺省
`db_analysis/timeline/`，只接受目录，自动命名
`timeline_<模式>_<筛选>_<排序>_<时间戳>.md`）；`--dump` 不写出
文件，把表格数据以 csv 文本打印到终端（纯 `#` 不着色）。

**表格布局（每项目一张独立表）**：前导列 = 项目 / 日差 / 4 个日期
（同一行）/ 状态（最后，快照 status 字段原值）；月网格 = 12 个月
× 4 周列，从**开始日期**起逐周画 `#` 连成线——终点：已关闭 → 关
闭日期，进行中 → 下个跟进，无下个跟进 → 拖到窗口尾。窗口外的
日期标注在头/尾列，窗外区域与月块两侧各断开 4 个空列。`--cols`
**强制指定** 4 个 date 字段（开始 最后跟进 下个跟进 关闭的位置
语义），不自动推导。

| 参数 | 说明 |
|------|------|
| `--mode year\|rolling` | 12 个月窗口：当年 1–12 月 / 当月-6 至 当月+5（默认） |
| `--cols f1 f2 f3 f4` | **必填**，4 个 date 字段名（fields.json 的 name），依次 = 开始/最后跟进/下个跟进/关闭位置 |
| `--colors #RRGGBB ×4` | 4 行配色（默认绿/蓝/橙/红，连线用第 1 色） |
| `--sort 字段\|diff` | 章内排序：任意库字段名或 `diff`（日差 = cols 第三列 − 今天）；缺省 diff 升序，无日差排最后 |
| `--desc` | 降序 |
| `--split` | 分章：逾期未跟进 → 待跟进 → 未排跟进 → 已关闭（归档只画开始/关闭区间） |
| `--where 字段=值` | 同 pie |
| `--path [目录]` | md 写出目录（与 --dump 互斥） |
| `--dump` | csv 文本打印到终端，不写出文件 |

「日差」= `--cols` 第三列（缺省即下个跟进）− 今天的天数。

## 参数

**字段口径（重要）**：`--field` / `--where` / `--date-field` 一律填
fields.json 里的**英文字段名（`name`）**，不是 GUI/界面显示的
中文 label——如 `customer` 而不是「客户」。填错报错时会列出全部
可用字段名。

| 参数 | 说明 |
|------|------|
| `--field` | 饼图变量（fields.json 英文 name），可多次；一次画多个字段，共享同一组筛选 |
| `--closed` | 纳入已归档项目 |
| `--top N` | 长尾合并阈值，默认 9 |
| `--where 字段=值` | 筛选，可多次，同字段取并集、异字段交集；日期支持 `起~止` |
| `--date-field` | 快照里的 date 列作时间基准（缺省 snapshot_at） |
| `--from/--to`、`--last 1m\|6m\|1y` | 日期区间（二选一） |
| `--png [目录]` | 画饼图（matplotlib 可选依赖）；只接受目录，不带值 = 默认目录 |
| `--dump [目录]` | 导出画饼数据 csv（utf-8-sig + 纯 LF）；同上只接受目录 |

输出目录（v3.5.2 用户定；v3.8.2 收拢）：`--png` / `--dump` /
`--path` **只接受目录**——一次可能产出多个文件，指定单文件名
（带扩展名的路径）直接报错；不带值用默认目录（自动创建）：
pie 的 PNG 和 csv 都直接存 `db_analysis/pie/`（不再分
plots/dump 子目录），timeline 存 `db_analysis/timeline/`；
带值 = 该目录内自动命名（**目录不存在则自动创建**，v3.8.2），
文件名嵌筛选摘要 `pie_<字段>_<筛选摘要>_<时间戳>.png/.csv`、
`timeline_<字段名>_<模式>_<筛选>_<排序>_<时间戳>.md`（timeline
的 stem 用英文字段名，短且路径安全，v3.8.2）。

## 示例

```bash
# 1. 客户分布饼图（终端计数表必出）
python -m db_analysis pie --field 客户

# 2. 多变量共享筛选：近 6 个月、只看武汉的项目
python -m db_analysis pie --field 客户 --field 里程碑     --last 6m --where 城市=武汉

# 3. 出图 + 导出数据到指定目录
python -m db_analysis pie --field 厂家 --png out/plots --dump out/dump

# 4. 含归档、按日期区间、指定时间基准
python -m db_analysis pie --field 状态 --closed     --from 2026-01-01 --to 2026-06-30 --date-field 跟进日期
```

退出码：0 成功；1 业务错误（stderr 无 traceback）；2 参数错误。
个别字段无匹配打印提示跳过，全部无匹配才报错。
