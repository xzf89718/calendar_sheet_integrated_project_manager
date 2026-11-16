# scripts/ —— 开发者脚本

面向开发者/高级用户的辅助脚本，普通使用者不需要碰这里。
全部脚本锚定仓库根目录的 `fields.json` 与数据库，无额外配置。

| 文件 | 作用 | 用法 |
|------|------|------|
| `check_docs.py` | 全仓库 docstring 体检：缺 docstring、`:return:` 标注与函数体不符两类问题，退出码 0=全绿 1=有问题（可接 CI） | `python scripts/check_docs.py [文件...]`；不带参数扫全仓库（跳过 tests/docs/build 等） |
| `build_docs.ps1` | 先跑 check_docs，再 sphinx-build 生成 HTML 文档到 `docs/_build` | `powershell -File scripts/build_docs.ps1`（首次自动建 `.docs-venv` 并装依赖） |
| `runmyanalysis.py` | 本地一键分析：四张任务清单（导出/周报/饼图/时间线），每行一个任务，参数全在行上，支持 `@today` / `@today-1m` 日期令牌；改文件头参数区即可 | `python scripts/runmyanalysis.py`（先跑 `setup.ps1` / `setup.sh` 生成 shim 后有短命令） |
| `myanalysis/` | runmyanalysis 的任务执行内核（common 工具 + export_all / pie / timeline / weekly 四个执行器），被 runmyanalysis.py 调用，一般不直接运行 | — |
| `show_icon.py` | 品牌图标字符画重采样：把 `icon/pm_workbench_icon.png` 转成终端字符画，写回 show_icon.ps1 / show_icon.sh 薄脚本 | `python show_icon.py [--cols 48]` |
| `show_icon.ps1` / `show_icon.sh` | 重采样产物：纯薄脚本（ps1 走 [Console] 颜色 / sh 走 ANSI），CLI 启动时 `--show-icon` 只执行它们、零 PNG 解码 | 由 CLI 自动调用，也可手动运行看效果 |

注意：

- `show_icon.ps1` / `show_icon.sh` 是生成产物，换图标后必须重跑
  `show_icon.py` 再生（脚本头部有 mtime/size 溯源标记可核对）；
- 跑过 pytest 后这两个文件可能出现换行符污染（`git status` 显示
  modified），属良性，`git checkout --` 还原即可；
- 全部 PowerShell 脚本保持纯英文，避免 Windows PowerShell 5.1
  非 ASCII 编码问题。
