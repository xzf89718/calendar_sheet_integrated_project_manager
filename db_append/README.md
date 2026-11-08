# db_append —— 多源库整库追加

把多个源库**依次全部追加**进目标库（团队报数汇总场景：每人一份
库、同一格式，定期把各人的库追加进汇总库）。每次追加都走快照
机制，来源留痕，可回溯。作用域唯一——只挑部分项目请用
[db_copy](../db_copy/README.md)。

与主程序共享 fields.json，列清单按运行时配置动态生成。

## 运行

| 方式 | 命令 |
|------|------|
| GUI | `python -m db_append --gui` |
| 命令行 | `python -m db_append 目标.db 源1.db [源2.db ...]` |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `target` | 目标库路径（合并进这里） |
| `sources` | 源库路径，可多个，按顺序依次追加 |
| `--gui` | 图形界面 |

## 示例

```bash
# 1. 图形界面：选目标库 + 多个源库
python -m db_append --gui

# 2. 张三、李四的周报库汇总进团队库
python -m db_append team.db zhangsan.db lisi.db
```

注意：源库字段配置（fields.json）应与目标库一致；不一致时按
目标库配置解释，追加前列清单差异请先用 GUI 预览。
