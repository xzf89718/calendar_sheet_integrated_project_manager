# db_copy —— A/B 双库对照复制

把源库中选中的项目（**含全部历史快照**）追加到目标库。只新增、
不覆盖：目标库已有同 id 项目时自动分配新 id，两边数据永不互相
污染。作用域唯一——本模块只负责"挑项目"，整库汇总请用
[db_append](../db_append/README.md)。

与主程序共享 fields.json（库路径锚定其同目录），列清单按运行时
配置动态生成，不硬编码字段。

## 运行

| 方式 | 命令 |
|------|------|
| GUI | `python -m db_copy --gui` |
| 命令行 | `python -m db_copy A.db B.db 1 2` |
| 命令行（全部） | `python -m db_copy A.db B.db --all` |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `src` | 源库 A 路径（可选，缺省进 GUI） |
| `dst` | 目标库 B 路径 |
| `pids` | 要复制的项目 id，可多个 |
| `--all` | 复制全部项目 |
| `--gui` | 图形界面 |

## 示例

```bash
# 1. 图形界面：左右双库对照，勾选后箭头追加
python -m db_copy --gui

# 2. 把 A.db 里的项目 3、7、12 追加进 B.db
python -m db_copy A.db B.db 3 7 12

# 3. 整库并入（等价于 db_append 的双库场景）
python -m db_copy A.db B.db --all
```

GUI 里可以逐项目核对历史后再点箭头；命令行适合脚本化批量操作。
