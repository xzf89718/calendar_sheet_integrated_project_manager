# db_analysis —— 只读数据分析

只读数据分析统一入口，**绝不写库**（专项测试：跑完库文件哈希
不变）。当前算法：多变量饼图共享筛选。

- 口径：默认统计 open 项目当前行；`--closed` 把已归档也纳入
- 给日期区间时，每个项目取窗口内"当时最新"的快照统计
- 空值归「（空）」段；取值超 `--top`（默认 9）长尾合并「其他」
- date 类型字段可作饼图变量（原值归段）

## 运行

```bash
python -m db_analysis pie --field 字段 [--field 字段2 ...] [--closed] [--top N]
        [--where 字段=值 ...] [--date-field 名]
        [--from YYYY-MM-DD --to YYYY-MM-DD | --last 1m|6m|1y]
        [--png [目录]] [--dump [目录]]
```

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

输出目录（v3.5.2 用户定）：`--png` / `--dump` **只接受目录**——
一次可能产出多个文件，指定单文件名直接报错；不带值用默认目录
（自动创建）PNG 存 `db_analysis/pie/plots/`、数据存
`db_analysis/pie/dump/`；带值 = 该目录内自动命名，文件名嵌筛选
摘要 `pie_<字段>_<筛选摘要>_<时间戳>.png/.csv`。

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
