# db_recycled —— 回收站

主程序删除的项目（项目 + 全部快照 + 收藏夹索引）移入回收站
（独立 `recycled_*` 表，主表格/日历/周报/导出/通知全部天然不可见）。
本模块负责查看、恢复、永久删除，命令行与 GUI 双入口。

回收站由 fields.json 的 `recycle_bin` 段开关（`enabled: true`
才启用；缺省 = 关闭，删除即物理删除，与本模块无关）。回收站随
.db 文件走——复制/备份库 = 连同回收站一起。

## 运行

| 方式 | 命令 |
|------|------|
| GUI | `python -m db_recycled 库.db --gui` |
| 命令行 | `python -m db_recycled 库.db`（列出回收站） |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `db` | 数据库文件路径，如 xxx.db |
| `--restore ID\|all` | 恢复项目；`all` = 全部恢复 |
| `--purge ID` | 永久删除单个（物理销毁，不可恢复） |
| `--empty` | 清空回收站 |
| `--gui` | 图形界面（恢复 / 红色永久删除按钮 + 二次确认） |

## 示例

```bash
# 1. 看回收站里有什么
python -m db_recycled sales.db

# 2. 恢复项目 12（原 id 空闲则原位放回；被占用则分配新 id，
#    收藏夹索引跟随指向新 id）
python -m db_recycled sales.db --restore 12

# 3. 后悔药吃完了：永久销毁
python -m db_recycled sales.db --purge 12
```

⚠️ `--purge` / `--empty` = 物理销毁、不可恢复；命令行不给确认，
执行即销毁。GUI 中对应红色按钮 + 二次确认弹窗。
