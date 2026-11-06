# -*- coding: utf-8 -*-
"""workbench_ui 命令行入口（v3.3.0）。

用法：
    python -m workbench_ui <子命令> [选项]
    python -m workbench_ui gui [--view aggregate|calendar|table]

子命令 = 主窗口全部 GUI 功能：
    list  项目列表（索引、筛选、排序、分页）
    show  查看项目（当前快照 / 第 N 条历史）
    new   新建项目
    follow  追加跟进快照
    import  表格导入
    export  批量导出
    weekly  周报导出
    backup  库备份
    notify  今日事项（直接打印到终端，不走系统通知）
    cal   日历时间节点（只读打印，只提供查看入口）
    fav   收藏夹（list/new/rename/delete/add/remove）

退出码：0 成功；1 业务错误；2 参数错误。
筛选：--where 字段=值（可多次，同字段取并集）；日期字段可用
      --where 字段=起~止（任一端可省略）。
"""
import argparse
import os
import sys

# 冻结绑定坑：bench_core 与 __main__ 都以包内绝对导入进入，
# conftest 对 config/db 等模块量的 patch 才能生效。
try:
    from workbench_ui import bench_core as bc
except ValueError as _cfg_err:                # 配置校验失败
    print(f"配置错误：{_cfg_err}", file=sys.stderr)
    sys.exit(1)

PROG = "python -m workbench_ui"


def _err(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def _add_filter_args(p):
    p.add_argument("--closed", action="store_true",
                   help="包含已完结项目（默认只看进行中）")
    p.add_argument("--search", action="append", default=None, metavar="词",
                   help="关键词搜索（可多次，取交集）")
    p.add_argument("--where", action="append", default=None,
                   metavar="字段=值",
                   help="字段精确筛选，可多次；日期字段支持 起~止 区间")
    p.add_argument("--sort", default=None, metavar="列",
                   help="排序列（缺省 = fields.json 的 default_sort）")
    p.add_argument("--desc", action="store_true", help="降序")


def _add_format_args(p):
    p.add_argument("--format", choices=("table", "csv"), default="table",
                   help="输出格式（默认 table）")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="最多输出 N 条")
    p.add_argument("--offset", type=int, default=0, metavar="N",
                   help="跳过前 N 条")


def _list_like(bc_fn):
    """list / export 共用的取数调用。"""

    def take(a):
        return bc_fn(a)

    return take


def cmd_list(a):
    db = bc.open_db()
    try:
        rows, total = bc.cmd_list(
            db, closed=a.closed, search=a.search, where=a.where,
            sort=a.sort, desc=a.desc, limit=a.limit, offset=a.offset,
            fav=a.fav)
        cols, heads = bc.list_columns()
        if a.fav:
            cols.append("fav")
            heads["fav"] = "收藏夹"
        data = bc.format_csv(rows, cols, heads) if a.format == "csv" \
            else bc.format_table(rows, cols, heads)
        print(data)
        shown = len(rows)
        if shown != total:
            print(f"本页 {shown} 条 / 共 {total} 条"
                  f"（--offset {a.offset} --limit"
                  f" {a.limit if a.limit is not None else '全部'}）")
        else:
            print(f"共 {total} 条")
    finally:
        db.close()


def cmd_show(a):
    db = bc.open_db()
    try:
        r = bc.cmd_show(db, a.id, hist=a.hist)
        cfg = bc._cfg()
        cur = r["current"]
        title = r.get("title") or ""
        if a.hist is not None:
            h = r["hist"]
            print(f"项目 #{a.id}  第 {a.hist} 条历史"
                  f"（共 {r['total']} 条，1 为最新）")
            print("-" * 40)
            for n, hlabel in cfg.display_cols:
                if n == "id":
                    continue
                print(f"{hlabel}: {bc._rg(h, n)}")
            print(f"跟进记录: {bc._rg(h, 'followup_note')}")
            return
        print(f"项目 #{a.id}  {title}")
        print("-" * 40)
        for n, hlabel in cfg.display_cols:
            if n == "id":
                continue
            print(f"{hlabel}: {bc._rg(cur, n)}")
        print(f"跟进记录: {bc._rg(cur, 'followup_note')}")
        snaps = r["snaps"]
        print(f"\n历史（{len(snaps)} 条，新在上）:")
        for i, s in enumerate(snaps, 1):
            ts = bc._rg(s, "snapshot_at") or bc._rg(s, "created_at")
            print(f"#{len(snaps) - i + 1}  {ts}  改动: "
                  f"{bc._rg(s, 'change_summary')}")
        if snaps:
            print("\n查看某条历史：show %d --hist N" % a.id)
    finally:
        db.close()


def cmd_new(a):
    db = bc.open_db()
    try:
        pid, title = bc.cmd_new(db, a.set, note=a.note)
        print(f"已创建项目 #{pid}  {title}")
        print(f"查看：show {pid}    跟进：follow {pid} --set 字段=值")
    finally:
        db.close()


def cmd_follow(a):
    db = bc.open_db()
    try:
        sid, summary = bc.cmd_follow(db, a.id, a.set, note=a.note)
        print(f"已追加快照 #{sid} 到项目 #{a.id}")
        if summary:
            print(f"改动: {summary}")
        print(f"查看：show {a.id}")
    finally:
        db.close()


def cmd_import(a):
    db = bc.open_db()
    try:
        created, skipped, unmapped = bc.cmd_import(db, a.file, a.template)
        print(f"导入完成：新建 {created} 条，跳过 {skipped} 条")
        if unmapped:
            print(f"未识别列：{'、'.join(unmapped)}")
    finally:
        db.close()


def cmd_export(a):
    db = bc.open_db()
    try:
        n = bc.cmd_export(db, a.out, template=a.template, closed=a.closed,
                          search=a.search, where=a.where,
                          sort=a.sort, desc=a.desc)
        print(f"已导出 {n} 条到 {os.path.abspath(a.out)}")
        print("注意：导出为全量匹配行，不受 --limit/--offset 影响")
    finally:
        db.close()


def cmd_weekly(a):
    db = bc.open_db()
    try:
        nf, np_ = bc.cmd_weekly(db, a.out, d1=a.date_from, d2=a.date_to,
                                p1=a.plan_from, p2=a.plan_to)
        print(f"已导出到 {os.path.abspath(a.out)}"
              f"：本周跟进 {nf} 条，下周计划 {np_} 条")
    finally:
        db.close()


def cmd_backup(a):
    db = bc.open_db()
    try:
        target = bc.backup_database(db, db.db_path)
        print(f"备份完成：{target}")
    finally:
        db.close()


def cmd_notify(a):
    db = bc.open_db()
    try:
        print(bc.today_notify_text(db))
    finally:
        db.close()


def cmd_cal(a):
    db = bc.open_db()
    try:
        entries = bc.cmd_cal(db, a.year, month=a.month, day=a.day)
        scope = f"{a.year} 年" + (f" {a.month} 月" if a.month else "") \
            + (f" {a.day} 日" if a.day else "")
        print(f"{scope} 项目时间节点（{len(entries)} 条）")
        print("-" * 40)
        for d, _kind, text, pid in entries:
            print(f"{d}  {text}  (#{pid})")
        print("\n查看项目：show <#id>    跟进：follow <#id> --set 字段=值")
    finally:
        db.close()


def cmd_fav(a):
    db = bc.open_db()
    try:
        sub = a.fav_cmd
        if sub == "list":
            favs = bc.cmd_fav_list(db)
            if not favs:
                print("还没有收藏夹")
                return
            for name, n, ids in favs:
                print(f"{name}（{n} 个项目）: "
                      + " ".join(f"#{i}" for i in ids))
        elif sub == "new":
            cid = bc.cmd_fav_new(db, a.name)
            print(f"已创建收藏夹 #{cid}  {a.name}")
        elif sub == "rename":
            bc.cmd_fav_rename(db, a.old, a.new)
            print(f"已重命名：{a.old} -> {a.new}")
        elif sub == "delete":
            bc.cmd_fav_delete(db, a.name)
            print(f"已删除收藏夹：{a.name}")
        elif sub == "add":
            bc.cmd_fav_add(db, a.name, a.ids)
            print(f"已把 {' '.join('#' + str(i) for i in a.ids)}"
                  f" 加入收藏夹 {a.name}")
        elif sub == "remove":
            bc.cmd_fav_remove(db, a.name, a.ids)
            print(f"已从收藏夹 {a.name} 移除 "
                  f"{' '.join('#' + str(i) for i in a.ids)}")
    finally:
        db.close()


def build_parser():
    p = argparse.ArgumentParser(
        prog=PROG,
        description="日历+表格聚合项目工作台 —— 命令行接口")
    sub = p.add_subparsers(dest="cmd", metavar="子命令")

    sp = sub.add_parser("list", help="项目列表")
    _add_filter_args(sp)
    _add_format_args(sp)
    sp.add_argument("--fav", default=None, metavar="收藏夹名",
                    help="只看该收藏夹内项目，输出追加「收藏夹」归属列"
                         "（纯索引视图过滤，不影响导入导出的全库语义）")

    sp = sub.add_parser("show", help="查看项目（含历史快照）")
    sp.add_argument("id", type=int, help="项目 id（list 第一列）")
    sp.add_argument("--hist", type=int, default=None, metavar="N",
                    help="查看第 N 条历史（1 = 最新）")

    sp = sub.add_parser("new", help="新建项目")
    sp.add_argument("--set", action="append", default=None,
                    metavar="字段=值", help="设置字段，可多次")
    sp.add_argument("--note", default=None, help="跟进记录")

    sp = sub.add_parser("follow", help="追加跟进快照")
    sp.add_argument("id", type=int, help="项目 id")
    sp.add_argument("--set", action="append", default=None,
                    metavar="字段=值", help="修改的字段，可多次；未传字段保持现值")
    sp.add_argument("--note", default=None, help="本次跟进记录")

    sp = sub.add_parser("import", help="表格导入")
    sp.add_argument("file", help="xlsx / csv 文件路径")
    sp.add_argument("--template", default=None, help="模板名")

    sp = sub.add_parser("export", help="批量导出（全量匹配行）")
    sp.add_argument("out", help="输出文件路径（xlsx / csv，按扩展名）")
    sp.add_argument("--template", default=None, help="模板名")
    _add_filter_args(sp)

    sp = sub.add_parser("weekly", help="周报导出（本周跟进 + 下周计划）")
    sp.add_argument("out", help="输出文件路径")
    sp.add_argument("--date-from", dest="date_from", default=None,
                    metavar="YYYY-MM-DD", help="跟进段起点（缺省本周一）")
    sp.add_argument("--date-to", dest="date_to", default=None,
                    metavar="YYYY-MM-DD", help="跟进段终点（缺省本周日）")
    sp.add_argument("--plan-from", dest="plan_from", default=None,
                    metavar="YYYY-MM-DD", help="计划段起点（缺省下周一）")
    sp.add_argument("--plan-to", dest="plan_to", default=None,
                    metavar="YYYY-MM-DD", help="计划段终点（缺省下周日）")

    sub.add_parser("backup", help="库备份")

    sub.add_parser("notify", help="今日项目事项（打印到终端）")

    sp = sub.add_parser("cal", help="日历时间节点（只读）")
    sp.add_argument("year", type=int, help="年，如 2026")
    sp.add_argument("month", type=int, nargs="?", default=None, help="月")
    sp.add_argument("day", type=int, nargs="?", default=None, help="日")

    sp = sub.add_parser("fav", help="收藏夹")
    fsub = sp.add_subparsers(dest="fav_cmd", metavar="动作")
    fsub.add_parser("list", help="列出全部收藏夹")
    fp = fsub.add_parser("new", help="新建收藏夹")
    fp.add_argument("name")
    fp = fsub.add_parser("rename", help="重命名收藏夹")
    fp.add_argument("old")
    fp.add_argument("new")
    fp = fsub.add_parser("delete", help="删除收藏夹")
    fp.add_argument("name")
    fp = fsub.add_parser("add", help="项目加入收藏夹")
    fp.add_argument("name")
    fp.add_argument("ids", type=int, nargs="+", help="项目 id，可多个")
    fp = fsub.add_parser("remove", help="从收藏夹移除项目")
    fp.add_argument("name")
    fp.add_argument("ids", type=int, nargs="+")

    return p


def main(argv=None):
    av = list(sys.argv[1:] if argv is None else argv)
    # gui 在 argparse 之前拦截透传：argparse 的 REMAINDER 吞不下
    # 选项形参（--view 之类），直接整体转交 main.py 最稳。
    if av and av[0] == "gui":
        import main as _main_mod
        _main_mod.main(av[1:])
        return
    parser = build_parser()
    args = parser.parse_args(av)              # 参数错误 -> 退出码 2
    if not args.cmd:
        parser.print_help()
        sys.exit(2)
    try:
        globals()["cmd_" + args.cmd](args)
    except bc.BenchError as e:
        _err(str(e))
    except SystemExit:
        raise


if __name__ == "__main__":
    main()
