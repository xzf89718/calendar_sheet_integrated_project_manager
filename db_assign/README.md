# db_assign —— 全库统一赋值

对整个库统一给某一列赋同一个值（如把全库 `城市` 改成 `武汉`）。
**默认只预览不执行**，加 `--yes` 才真正写入；写入走快照机制，
每次赋值留痕、可回溯。双只读预览（执行前/执行后对照）。

与主程序共享 fields.json，`--field` 可填字段名或显示名。

## 运行

| 方式 | 命令 |
|------|------|
| GUI | `python -m db_assign --gui` |
| 命令行（预览） | `python -m db_assign 库.db --field 城市 --value 武汉` |
| 命令行（执行） | 同上再加 `--yes` |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `db` | 数据库路径 |
| `--field` | 赋值列（字段名或显示名，如 city / 城市） |
| `--value` | 新值；缺省空 = 清空该列 |
| `--yes` | 确认执行（不加只预览） |
| `--gui` | 图形界面 |

## 示例

```bash
# 1. 预览把全库城市改成武汉（不写库）
python -m db_assign sales.db --field 城市 --value 武汉

# 2. 确认后执行
python -m db_assign sales.db --field 城市 --value 武汉 --yes

# 3. 清空某列（value 缺省 = 空）
python -m db_assign sales.db --field 备注 --yes
```

适用场景：库迁移后统一改归属、批量修正录错的列。逐项目修改请
回到主程序走「编辑/添加跟进」，保留上下文。
