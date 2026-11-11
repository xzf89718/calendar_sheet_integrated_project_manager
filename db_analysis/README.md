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

python -m db_analysis timeline [--mode year|rolling] [--cols 3个字段]
        [--colors 4个#RRGGBB] [--sort 字段|diff] [--desc] [--split]
        [--where 字段=值 ...] [--path [目录]] [--dump]
```

### timeline：项目分类时间点可视化（v3.8.0 首版；v3.8.3 贴图定版；v3.8.4 配置化改版）

**不叫甘特图**（用户定）：甘特图 = 持续时间条 + 完成百分比 +
依赖关系；本软件只有离散时间点 + 类别，不做进度评估——给证据
不给结论。

**配置（fields.json 的 timeline 段，v3.8.4 用户定）**：

```json
"timeline": {
    "start": "start_date",      // 开始列（fields 的 name）
    "next": "next_followup",    // 下一个跟进列
    "close": "close_date",      // 关闭列
    "last": "last_snapshot",    // 派生「最近跟进」列名（取最新快照日期，
                                // 不属于 fields 的 name）
    "plot": "line",             // 基准画法：line=两日期连线 / spot=单日期画点
    "colors": ["#2e7d32", "#1565c0", "#e65100", "#7b1fa2"]
                                // 基准四行配色（今日/最近跟进/下一个跟进/关闭）
}
```

缺省从 calendar_dates 法定三类推导 start/next/close，其余取默认值。

**CLI**：

```bash
python -m db_analysis timeline [--mode year|rolling]
        [--add-col 字段 ...] [--add-plot line|spot]
        [--add-colors #RRGGBB ...] [--sort 字段|diff] [--desc]
        [--split] [--where 字段=值 ...] [--path [目录]] [--dump]
```

**输出形式**：非 dump 模式终端只打印筛选条件 + 统计 + 写出路径，
md 恒写出为文件（`--path` 缺省 `db_analysis/timeline/`，只接受目录，
自动命名 `timeline_<基准字段名>_<模式>_<筛选>_<时间戳>.md`）；
`--dump` 不写出文件，把表格数据以 csv 文本打印到终端（纯 `#` 不着色）。

**表格布局（v3.8.4 用户定）**：

- **项目名单独一行**：每个表格第一行 = 项目名（加粗、放大字体、
  不带数据）；3 日期值/额外列值/日差/状态在第一行线段行上；
- 前导列名固定：**开始 / 下一个跟进 / 关闭**（不用 JSON label）；
  额外列（--add-col）用自己的 label；
- **日差 < 0 时数字标红**；
- 每项目一张表（无单独小标题），表内基准 **4 行线段**，顺序固定：
  开始-今日 / 开始-最近跟进 / 开始-下一个跟进 / 开始-关闭；
  画图模式由 JSON `timeline.plot` 定：line = 从开始日期连线到终点，
  spot = 只在终点日期画一个点；**任一行日期缺失则不画线、保留行位置**；
- `--add-col 字段` 额外加一列 + 对应图行（画法和配色由
  `--add-plot` / `--add-colors` 定，spot 模式备注只写列名）；
- 月格 = **12 个月列，每格 4 字符**（对应每月 4 周）；连线模式被触
  月格内范围外用 `-` 填充（v3.8.9，格长恒 4），点模式用 `$` 标记；
  窗口外的月份
  延伸出窗口时**头/尾列直接画满 4 个标记字符**（v3.8.10 起，填 #
  / spot 填 $，不再填文字标注），窗外日期夹到边界画线，且**延伸
  出窗口的边缘月格一律填满 4 个 #**（不画残格）；
- `--split` 时文首给章导航超链接。

| 参数 | 说明 |
|------|------|
| `--mode year\|rolling` | 12 个月窗口：当年 1–12 月 / 当月-6 至 当月+5（默认） |
| `--add-col 字段` | 额外 date 字段列 + 图行，可多次 |
| `--add-plot line\|spot` | 额外列画法：line=从开始连线（默认）/ spot=单日期画点 |
| `--add-colors #RRGGBB` | 额外列配色，可多次，个数须与 --add-col 一致 |
| `--sort 字段\|diff` | 章内排序：任意库字段名或 `diff`（日差 = 下一个跟进 − 今天）；缺省 diff 升序，无日差排最后 |
| `--desc` | 降序 |
| `--split` | 分章：逾期未跟进 → 待跟进 → 未排跟进 → 已关闭；文首给章导航超链接；文件名记 `split` |
| `--where 字段=值` | 同 pie |
| `--path [目录]` | md 写出目录（与 --dump 互斥） |
| `--dump` | csv 文本打印到终端，不写出文件 |

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
