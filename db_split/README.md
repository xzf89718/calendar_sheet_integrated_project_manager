# db_split —— 按键列拆库

按某列的取值把源库拆成多个库文件：每个键值一个 .db（如按
负责人拆成每人一份）。全量拆分（含归档项目）；键值为空的行归
入 `未分配.db`；输出文件名配方由 fields.json 的 `split` 段配置
（成分 prefix / field / key / time 可排序 + 前缀文本）。

与主程序共享 fields.json，`--key` 可填字段名或显示名
（如 `city` 或 `城市`）。

## 运行

| 方式 | 命令 |
|------|------|
| GUI | `python -m db_split --gui` |
| 命令行 | `python -m db_split 源.db --key 负责人 --dest 输出目录` |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `db` | 源库路径，如 xxx.db |
| `--key` | 键列（字段名或显示名，如 city / 城市） |
| `--dest` | 输出目录 |
| `--preview` | 只预览拆分结果，不写出文件 |
| `--gui` | 图形界面 |

## 示例

```bash
# 1. 先预览：按负责人拆，看会产出哪些文件
python -m db_split team.db --key 负责人 --dest out/ --preview

# 2. 确认无误后正式拆分
python -m db_split team.db --key 负责人 --dest out/

# 3. 图形界面（等价操作）
python -m db_split --gui
```

输出文件名示例：`负责人_张三_20261108-103000.db`
（配方缺省 components=["field","key","time"]；改配方见
FIELDS-CONFIG.md 的 `split` 一节）。
