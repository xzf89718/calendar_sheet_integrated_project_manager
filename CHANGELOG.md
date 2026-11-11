# 更新日志

版本规则：修复动第三位，功能动第二位，结构动第一位。

- **v3.8.14** db_analysis --where 区间校验对齐 workbench_ui（修复，
  2026-11-12 实测发现）：此前 pie/timeline 侧非日期字段误用 `~`
  被静默当单值过滤、非法日期（abc~def）与反向区间（起晚于止）均
  不校验，全部落到误导性的「没有匹配的项目」空结果；现三者均
  明确报错（不是日期字段 / 不是有效日期 / 起点晚于终点）。
  合法区间行为不变。261 passed。

- **v3.8.13** timeline 删除 markdown 模式，HTML 成为唯一输出
  （用户定，2026-11-12）。删除原因：markdown 表格宽度不可控，
  无法整体缩放适配窗口宽度，月格多列必然横向滚动，浏览体验不可
  接受；HTML 整页打开即按窗口宽度自动适配（fit），右上角
  +/-/fit 按钮按需再放大，同一份数据阅读体验远好于 md。
  `--html` 参数随之移除（不再需要开关）。260 passed。

- **v3.8.12** timeline HTML 输出（用户定，2026-11-11）：markdown
  表格宽度不可控、浏览体验差；新增 `--html` 写出 .html 整页，
  打开后按窗口宽度自动适配（fit），右上角 +/-/fit 按钮可再
  缩放，表结构与 md 版一致。260 passed。

- **v3.8.11** timeline 列名与行序（用户定，2026-11-11）：
  1. 头/尾两列更名 **更早 / 更晚**；
  2. 基准线段行顺序改为：开始-最近跟进 / 开始-今日 /
     开始-下一个跟进 / 开始-关闭（add-on 列仍在最后）。
  259 passed。

- **v3.8.10** timeline 头/尾列改标记（用户贴图定，2026-11-11）：头/尾
  列不再填「<26-05」「>27-04」文字标注，延伸出窗口时直接画满 4 个
  标记字符（line 填 #，spot 填 $），与月格同色。259 passed。

- **v3.8.9** timeline 月格填充（用户定，2026-11-11）：连线模式被
  线段触到的月格内，范围外一律用 `-` 填充（如 `###-`），保证各
  月格长度一致、线看起来连续；点（spot）模式用 `$` 标记替代 #。
  csv 导出同步。259 passed。

- **v3.8.8** timeline 窗外画法（用户贴图定，2026-11-11）：
  1. 线段延伸出标准 12 个月窗口时，边缘月格一律填满 4 个 #，
     不再按夹边界后的周数画残格（用户：原来画得像中间断开）；
  2. 头/尾标注列文字改为「<26-05」「>27-04」（带具体年月）。
  258 passed。

- **v3.8.7** timeline 渲染修复（用户贴图反馈，2026-11-11）：
  1. 线段行多出一个空单元格（尾与状态之间），导致状态/备注列
     错位、备注被挤掉——删除该空列，备注恢复为每行日期注释；
  2. 表外项目名标题与表格之间补空行，避免部分渲染器无法识别
     表格。csv 导出同步对齐列数。258 passed。

- **v3.8.6** timeline 项目名移出表格（用户定，2026-11-11）：项目名
  不再作为表内第一行，改为每个表格上方单独一行标题（加粗放大
  字体、不带数据）；表内仍是 4 行线段行，3 日期值/日差/状态在
  第一行线段行。258 passed。

- **v3.8.5** --where 同字段多次取并集（修复，用户提出需求，同日）：
  此前 `--where milestone=Lead --where milestone=Qualified Lead` 后者
  覆盖前者，多值过滤无法表达。改为同字段重复取值自动并入集合，
  区间条件仍覆盖。导出四分报表（pipeline_report 模板 + 多值
  milestone 过滤）依赖此修复。新增测试
  test_parse_where_same_field_union，258 passed。

- **v3.8.4** timeline 配置化 + CLI 改版（用户定 6 点，同日）：
  1. 项目名单独一行（加粗放大字体、不带数据），不再有项目列；
  2. 前导列名固定：开始 / 下一个跟进 / 关闭；
  3. 日差 < 0 数字标红；
  4. 头/尾标注列文字 = 「早于26-05」「晚于27-04」（早于第一个月 /
     晚于第 12 个月）；
  5. 基准四列（开始/下一个跟进/关闭/最近跟进）的字段、画法
     （line 连线 / spot 画点）、配色全部进 fields.json 的 timeline
     段（派生最近跟进列命名 last_snapshot）；--cols / --colors 删除；
  6. CLI 增量：--add-col（额外列 + 图行）、--add-plot line|spot、
     --add-colors（只给额外列）。
  测试重写，257 passed。

- **v3.8.3** timeline 重排为用户贴图定版（用户定，同日），含 5 点
  返修：
  1. `--cols` 收为 3 个必填 date 字段（开始/下个跟进/关闭）；
     「最近跟进」是快照派生量（MAX(snapshot_at)），不再要求指定；
  2. 每项目一张表、表内 4 行线段（开始-今日/最近跟进/下个跟进/
     关闭），行线 4 色；两端任缺 → 不画线但保留行位置；
  3. 首行带项目名/日差/3 日期值/状态，其余行仅 # 线 + 备注；
  4. 月格 = 12 个月列 × 每格 4 字符（不再 48 个编号列）；窗外月份
     写进头/尾两个标注列，窗外日期夹边界画线；
  5. 无单独小标题；默认四色改绿/蓝/橙/紫（原橙红太近）；文件名
     用 `split`；--split 时文首给章导航超链接。
  测试同步重写，255 passed。

- **v3.8.2** 输出路径收拢（用户定，同日）：
  ① pie 默认落点从 `pie/plots/`、`pie/dump/` 子目录收拢到
  `db_analysis/pie/`（PNG 与 csv 同目录，靠扩展名区分）；
  timeline 默认维持 `db_analysis/timeline/`；
  ② `_resolve_out`（v3.5.2 规矩的温和化）：显式目录**不存在则
  自动创建**（makedirs）；带扩展名的路径仍按"想指定文件名"拒绝；
  ③ timeline 文件名 stem 从中文 label 改为**英文字段名**
  （`timeline_start_date-next_followup-..._<模式>_<筛选>_<时间戳>.md`，
  短且路径安全）；④ 模块 docstring / help / README / 测试同步
  （默认目录 globs 收拢 + 自动建目录用例 + 文件名嵌字段名断言），
  全量 254 passed
- **v3.8.1** db_analysis timeline 布局重排（用户返修 6 点，同日）：
  ① **非 dump 模式终端不再打印 md 本体**，只打印筛选条件 + 口径
  统计 + 写出路径（md 恒写出为文件，--path 缺省
  db_analysis/timeline/）；--dump 不写出文件、csv 打终端；两者
  互斥；
  ② **每项目一张独立表**（表头分开，不再拼大表）；4 个日期值 +
  **状态列**（快照 status 字段原值，修掉了 p.status/s.status 列名
  撞车导致只显示 open 的 bug）在同一行，状态列在最后；
  ③ 月网格 12 个月 × **4 周列**；从**开始日期**逐周画 `#` 连成线
  （终点：已关闭 → 关闭日期；进行中 → 下个跟进；无下个跟进 →
  拖到窗口尾；29–31 日夹入第 4 周）；
  ④ 窗外日期标注在**头/尾列**，窗外区域与月块**两侧各断开 4 个
  空列**；
  ⑤ `--cols` 改为 **required 强制指定**，删除自动推导；--dump
  与 --path 互斥组。测试重写 16 用例（单行布局/连线条数/窗外
  头尾列/断列/状态列/摘要式终端输出/--cols 缺省报退出码 2），
  全量 254 passed
- **v3.8.0** db_analysis timeline：项目分类时间点可视化（用户定，
  需求文档「项目时间点可视化-日历表格聚合」）：
  ① **命名定案：不叫甘特图**——甘特图 = 持续时间条 + 完成百分比 +
  依赖关系；本软件只有离散时间点 + 类别，不做进度评估（给证据
  不给结论）；
  ② **markdown 表格输出**：每项目 4 行（对应 4 个日期，默认从
  calendar_dates 推导：开始/最后跟进（最新快照，特殊值 `last`）/
  下个跟进/关闭，--cols 可指定），12 个月窗口每月一列，在日期
  所属月份格画着色 `<font color>` `#`；窗口 = year（当年）或
  rolling（当月-6 至 当月+5，默认）；窗口外时间点不丢弃，「窗外」
  列标注实际月份；4 行默认绿/蓝/橙/红，--colors 可指定；
  ③ **输出形式（用户定）**：终端始终打印 md，`--path` 只接受
  目录、另存 `timeline_<模式>_<筛选>_<排序>_<时间戳>.md`
  （_resolve_out 泛化出 prefix 参数）；`--dump` 把表格数据以 csv
  文本打印到终端（纯 # 不着色）；
  ④ **--sort** 任意库字段或 diff（日差 = --cols 第三列 − 今天）
  升降序，缺省 diff 升序、无日差垫底；**--split** 四章（用户定）：
  逾期未跟进 → 待跟进 → 未排跟进 → 已关闭（归档从 status_closed
  读，projects.status 布尔化口径，归档章只画开始/关闭两格）；
  **--where** 复用 analysis_core 解析；取数当前行口径、open +
  closed 全取；
  ⑤ 新增 `db_analysis/algo_timeline.py`（取数/分章/排序/渲染/
  dump 分层，`today` 可注入保测试确定性）；db_analysis README
  增 timeline 章节。测试 +12（md 网格/窗口两模式/四章顺序/窗外
  标注/where+sort/path 只接受目录/dump/--cols/--colors 校验/
  rolling 窗口单元/空章剔除），全量 251 passed
- **v3.7.2** CLI 全命令图标开关（用户定）：
  ① **workbench_ui 全部子命令接入**（list/show/new/follow/import/
  export/weekly/backup/notify/cal/fav 及其二级动作），--show-icon /
  --no-show-icon 注入每个子解析器，统一裁决于 fields.json 的
  ui.show_icon；补齐 v3.7.1 植入时遗漏的最后一个 CLI 入口；
  ② **main.py CLI 路径**（--check-config）接入 tty_if_wanted；
  ③ 语义统一：CLI 下图标行流先播、**不停顿**，播完立即执行原命令
  （GUI 闪屏 3 秒保持不变）；文档串/README 同步更新（顺带修正
  "半块字符堆叠"过时描述为 #$& ASCII 字符画）。测试 +2（子命令
  help 暴露开关含 fav 二级、check-config 在 pty 下图标先于校验
  输出），全量 236 passed。
  **卡顿修复（同日用户实测：--show-icon 明显卡顿）**：脚本写盘
  虽有缓存，但 v3.7.2 初版每次运行仍先 `render_ascii()` 纯 Python
  解码 1MB PNG（实测 760ms）。改为**惰性采样**：`_existing_script`
  只查脚本存在与否，存在则跳过 PNG 解码与写盘直接加载执行；重复
  运行开销只剩子进程启动（Linux 实测 3ms，Windows 另加
  powershell 启动，为脚本方案的固有成本）。测试 +1（缓存命中
  打桩 render_ascii 抛错仍渲染成功），全量 237 passed。
  **定稿（同日用户定）：默认只跑 scripts/ 里的脚本，重采样手动**：
  运行时不再校验脚本内容是否过期（存在即执行，零 stat 头读、
  零 PNG 解码）；仅脚本缺失时兜底生成一次。更换图标后的重新采样
  为手动动作——新增命令行入口 `python show_icon.py [--icon 路径]
  [--cols N]`（regen_scripts 函数），幂等重写 ps1 + sh 两脚本，
  README 增「图标脚本手动重采样」一节。测试 +2（regen 双脚本
  写出且 ps1 纯 ASCII、`python show_icon.py` 入口冒烟），
  全量 239 passed。
  **ANSI 兜底移除（同日用户定：兜不住且多占代码）**：tty_icon 脚
  本加载失败静默放弃，不再退回 ANSI 渲染（render_tty 约 20 行
  整体删除，os.system("") 开 VT 一并移除）；图标缺失仍抛
  FileNotFoundError，workbench_ui 独立 --show-icon 入口的
  stderr + 退出码 1 语义不变。测试 ±0（删 ANSI 兜底用例、加无
  兜底行为锁），全量 239 passed
- **v3.7.1** 品牌闪屏三项收尾（用户定，5 条要求）：
  ① **`ui.show_icon` 入 JSON**（可缺省 = false），命令行
  `--show-icon` / `--no-show-icon` 覆盖之（裁决优先级
  CLI > JSON > false；config 校验必须是 bool）；
  ② **GUI 闪屏 512px**（≈500px，Tk subsample 无 PIL），**透明底**
  ——窗口底色品红 + Windows `-transparentcolor` 键控穿透（图标
  不含品红，安全）；
  ③ **CLI `--show-icon` 终端图标**：自写最小 PNG 解码器（标准库
  zlib，8-bit RGBA/RGB 非隔行子集）+ ANSI 24-bit 颜色 + "▀/▄"
  半块字符按 alpha 上下堆叠，44 格宽，Windows 自动开 VT；
  闪屏实现抽为独立模块 `show_icon.py`（gui_splash / render_tty /
  decode_png_rgba / resolve_show_icon）。顺手修复 2 处 README
  断行（跨行行内代码、weekly 用法 Synopsis 断行）。样例
  fields.json 加 `ui.show_icon`。测试 +5（裁决优先级、PNG 解码、
  ANSI 输出、缺图标报错、开关缺省），全量 223 passed。
  **返修（同日用户实测）**：经典 Windows 控制台忽略 24-bit 颜色
  序列 → 图标全白。终端渲染加**颜色降级链**：truecolor → 256 色
  → 16 色（`PMWB_ICON_COLORS` 环境变量可强制；按 COLORTERM /
  WT_SESSION / TERM_PROGRAM 自动检测；Windows 经典控制台按
  256 色，其余保守 16 色）。16 色档 RGB 最近邻映射标准调色板，
  品牌三色 + 白依然可辨。调研 term-image（Windows 有限支持、
  依赖 Pillow）与 chafa（外部 exe）后**不引入依赖**，自写渲染器
  保底（用户造轮子哲学）。测试 +3（检测/覆盖、三档量化、三档
  渲染冒烟），全量 226 passed。
  **子模块全植入（同日追加，用户定）**：品牌图标接入全部 7 个
  子模块（db_copy/db_append/db_split/db_assign/db_recycled/
  weekreport_clean/db_analysis）的 GUI 与 CLI——GUI 入口闪屏
  （gui 拦截路径在 argparse 前解析双开关），CLI 入口打印终端
  图标（仅 stdout 为交互终端时，管道/重定向静默跳过，不污染
  pie 计数表等机器可读输出）；db_recycled gui 顺带支持开关与库
  路径任意顺序。共享助手集中在 show_icon.py（add_icon_flags /
  want_icon / splash_if_wanted / tty_if_wanted / gui_icon_flags），
  各模块零逻辑复制。测试 +4（7 模块 help 暴露开关、管道防污染、
  拦截解析、覆盖裁决），全量 230 passed。
  **返修2（同日用户实测 Git Bash / PowerShell 5.1）**：上述静态
  环境变量启发式在经典 conhost 上不可靠——转义序列被消费（VT
  已开）但 24-bit 与 256 色 SGR 均被静默忽略，图标仍全白。改为
  **运行时探测**：向终端发 OSC 4 调色板查询（`\x1b]4;1;?`），
  xterm/mintty/kitty 系应答 `rgb:` 即判 256 色安全，0.3s 超时
  无应答（经典 conhost 不认 OSC）→ 落到 **16 色基础 SGR**（最老
  终端也认），扁平色图标 16 色下视觉近乎无损。检测顺序：环境
  变量强制 → truecolor 环境提示 → OSC 4 探测 → 16 地板。测试
  +1（探测注入 256/16 两分支），全量 231 passed。
  **返修3（同日用户实测 PowerShell 5.1 经典控制台仍全灰）**：根
  因是该类控制台对 24-bit/256 色 SGR 静默忽略（用户强制的
  truecolor 恰是最差档）。不再纯 ANSI 死磕：Windows 真控制台改走
  **Win32 控制台 API 直写**（`WriteConsoleOutputAttribute` /
  `WriteConsoleOutputCharacterW`），逐格设 16 色属性（最近邻映射
  Windows 默认调色板）——这是 PowerShell 自身上色的原生机制，
  不经 VT/转义序列，Win7 以来所有 Windows 控制台均支持；mintty/
  Git Bash 等非控制台句柄自动退回 ANSI 路径。采样逻辑抽为
  render_cells，与 ANSI 渲染共用。测试 +3（采样矩阵、Win16 量化、
  ANSI 与矩阵结构一致），全量 234 passed。
  **返修4（同日用户裁定）**：不深入系统 API（坐标直写受窗口大小/
  位置影响，且名字压进图标、越画越少）；改为 **scripts/ 薄脚本方案**
  （用户定，兼顾可读性、维护性、速率）：Python 完成 PNG 采样与量化，
  生成 RLE 数据 + 通用渲染循环的薄脚本存根目录 `scripts/`，再加载
  执行——`show_icon.ps1` 用 `[Console]` 颜色（PowerShell 原生机制，
  经典控制台无需 ANSI/VT；纯 ASCII，产品名经 -Name 参数传入，遵守
  PS 脚本不含中文的规矩）；`show_icon.sh` 走 ANSI（mintty 等真终
  端，printf 逐行）。脚本头带图标 mtime/size 标记，图标未变跳过重
  生成；两份脚本随包预生成；找不到 powershell/bash 或执行失败退回
  ANSI 降级链兜底。Win32 ctypes 直写代码整段移除。测试 +5（RLE 段
  化、ps1 纯 ASCII 与数据合法性、sh 端到端 bash 执行、ANSI 兜底、
  脚本路径），全量 239 passed。
  **返修5（同日用户实测 + 用户定稿，符号方案重做）**：PowerShell
  实测暴露两 bug——①半块字符 ▀/▄ 经 [Console]::Write 按 GBK
  控制台输出编码写出，U+2580/2584 不可编码全部退化成 `?`；②
  WriteLine 换行时控制台以当前背景色填充行尾，拖出彩色长条。
  用户裁定**弃用花哨符号**：终端图标改用 `#$&` 三符号 + 空格，
  绿区 #、蓝区 &、红区 $、白细节白色 #（Ubuntu/Debian version 横幅
  ASCII logo 风格），按字符 2:1 纵横比采样、格内平均色归类 4 基准
  色。纯 ASCII + 16 色 bright SGR，根上免疫编码/字体/VT 问题；
  truecolor/256 探测降级链（OSC4 查询、调色板量化）随精细渲染
  一并移除，代码显著瘦身。Git Bash 归并 ps1 路径（powershell
  子进程经 winpty 翻译控制台颜色），sh 仅留 POSIX。换行填色 bug
  修复（换行前重置为终端原色）。测试重写 -7 +8（字符画合法性、
  类别符号映射、RLE、ps1/sh 生成与 bash 端到端、后端判别、双路径
  渲染），全量 234 passed
- **v3.7.0** exe 图标支持 + 品牌图标入库（用户定，插队）：
  根目录新建 `icon/` 文件夹，存用户处理好的品牌图标两文件——
  `pm_workbench_icon.png`（1024 透明底，README 顶部相对路径
  引用）与 `pm_workbench_icon.ico`（16~256 多尺寸，
  `build_exe.ps1` 探测 `icon\pm_workbench_icon.ico`，存在则全部
  6 个 exe 套 --icon，**绝对路径**传入规避 PyInstaller 按 spec
  目录解析相对路径的坑；不存在则跳过不阻断构建）。README 图标
  引用 width=300。新增 **`--show-icon` 品牌闪屏**（同日追加）：
  `main.py --show-icon` 或 `python -m workbench_ui gui
  --show-icon`，启动主界面前屏幕中央显示
  icon/pm_workbench_icon.png 3 秒（256px 无边框，Tk subsample
  缩放、无 PIL 依赖）；图标锚定 fields.json 同目录，缺失/读取
  失败静默跳过。顺手修复 build_exe.ps1 `$Root` 未定义空值 bug
  （顶部 `$PSScriptRoot` 赋值 + Get-Location 兜底）。217 passed
  （+4 新用例：参数解析×3、闪屏生命周期×1——后者抓到
  PhotoImage 先于 Tk() 创建的平台差异，已修）。顺手勘误：
  CHANGELOG 历史条目重复粘贴一整段，本版清除
- **v3.6.3** db_analysis 字段口径文档澄清（用户定，补丁）：pie 的
`--field` / `--where` / `--date-field` 一律匹配 fields.json 的
**英文 name**，不用 GUI 显示 label——纯文档与 help 修正，行为
不变（本就只认 name，报错列可用字段名）；后续 db_analysis 新
配置遵循同一口径。模块 README 参数节加「字段口径（重要）」提示，
--field help 同步注明
- **v3.6.2** 子模块 GUI 入口统一为 gui 子命令（用户定）：db_copy /
db_append / db_split / db_assign / db_recycled 五模块废弃
`--gui` 参数，统一 `python -m db_xxx gui`，与 workbench_ui /
weekreport_clean 启动风格一致（`--gui` 现报参数错误 exit 2）；
db_recycled 的 gui 子命令带库路径（`gui <xxx.db>`，必给）。
5 份模块 README / FIELDS-CONFIG 回收站命令示例 / 各 *_gui.py 运行
提示同步更新。新增 6 条回归用例（5 模块 --gui 拒收参数化 +
db_recycled gui 缺库路径），全套 213 passed
- **v3.6.1** weekreport_clean CLI 化（用户定）：GUI / CLI 双入口，
启动接口与 workbench_ui 统一——`python -m weekreport_clean gui`
进图形界面，新增 `preview`（终端逐行打印 [保留]/[丢弃] + 汇总，
只读不写文件）与 `clean [-o 输出]`（生成清洗结果 xlsx，不带 -o
默认 `<原名>_cleaned.xlsx` 同目录，已存在覆盖，显式 -o 父目录
自动创建）两子命令，功能与 GUI 一一对应（结果为空拒绝写出等
行为两入口一致）。补齐四件套包结构：`__main__.py` 命令行入口、
`__init__.py` 导出核心、clean_core 新增 `weekly_note_label()`
（跟进记录列定位逻辑 GUI/CLI 同源，GUI 同步改用）；退出码沿用
0/1/2 约定。`setup.ps1` / `setup.sh` shim 清单补入本模块。新增 8
条 subprocess 全链路用例，全套 207 passed
- **v3.6.0** README 文档重构（用户定，裁定 7+1 条）：根 README 收敛为
定位 / 设计哲学 / 安装与启动 / 宽版基本使用（GUI 起步，面向零基础
= 核心设计，CLI 标「进阶」指向 workbench_ui/README.md）/ 文档导航，
目标 200~250 行；更新日志整体搬出至 CHANGELOG.md（历史条目原文
保留，今后发版在顶部追加）；fields.json 逐条详解 + SQL 速查（附录）
至 FIELDS-CONFIG.md；三个产品形态至 example/README.md；8 个子模块
各获参考式 README（定位 + 命令表 + 示例，40~80 行），全部根目录
及各模块目录平铺，不建 docs/。README 标题保留版本号（用户定）。
fossil 表述改 git（用户定，W1-A）：开头"基于自托管 Fossil 仓库开发"
→"基于 git 做版本控制开发"；设计思想末"开发历史由自托管 Fossil
仓库管理，Gitee/GitHub 为只读镜像"→"开发历史由 git 管理，Gitee/
GitHub 双远程仓库同步"；「更新和维护计划」删两句（"本地Fossil仓库
做版本控制和开发""新功能和代码贡献请联系我讨论。"）。勘误：工具
清单"分析（占位）"自 v3.5.0 起已转正、回收站漏列，本版改正为七
件套。新增 9 份文档。纯文档版，无代码改动，196 passed 原样回归
- **v3.5.2** 输出路径裁定（用户定）：`--dump-data` 改名 **`--dump`**；
  **`--png` / `--dump` 只接受目录**（一次可能产出多个文件，指定单
  文件名无法理解，显式文件名直接报错）；裸参数默认输出目录定为
  `db_analysis/pie/plots/` 与 `db_analysis/pie/dump/`（相对
  fields.json 同目录，自动创建，建议加入 .gitignore）。测试显式
  文件名用例全部改目录形态，错误参数化对齐「只支持目录」，新增
  3 用例（dump 默认目录 / dump 显式目录 / png 默认目录），全套
  196 passed（PNG 3 条在无 matplotlib 环境跳过）
- **v3.5.1** 多变量饼图共享筛选（用户定）：`--field` 可多次，一次
  命令画多个字段，共享同一组 `--where` / 日期区间 / `--closed`。
  逐字段出计数表 + PNG 每字段一个文件（拒绝多子图单文件，用户定）；
  个别字段无匹配打印提示跳过，全部无匹配才报业务错误。输出文件名
  自动嵌筛选摘要（用户定）：`pie_<字段>_<筛选摘要>_<时间戳>`，
  `--png` / `--dump-data` 不带值或给目录即自动命名。date 类型字段
  解禁为饼图变量（原值归段，空值归「（空）」）。多字段 csv 加
  「字段」列，单字段保持 v3.5.0 两列。新增 5 用例（多字段共享
  where / date 变量解禁 / 自动文件名嵌筛选 / 多列 csv / 多 PNG
  每字段一文件，其中 2 条 PNG 用例在无 matplotlib 环境跳过），
  错误参数化对齐新行为（date 拒绝用例退役、csv 扩展名断言对齐新
  裁定文案、补全空报错 1 条），全套 194 passed（PNG 2 条跳过）。
  顺手勘误：模块表 db_analysis 行自 v3.5.0 起残留"预留占位"描述，
  本版改正
- **v3.5.0** db_analysis 只读分析统一入口（占位模块转正，首个算法
  饼图）：`python -m db_analysis pie --field 字段`，铁律绝不写库
  （专项测试：跑完库文件哈希不变）。口径：默认 open 项目当前行，
  `--closed` 把已归档也纳入（客户自由选择）；给 `--from/--to` 或
  `--last 1m|6m|1y` 日期区间时，每个项目取窗口内"当时最新"的快照
  统计（用户定口径），`--date-field` 可指定快照里的 date 列（缺省
  跟进日 snapshot_at）。`--where 字段=值` 可选可多次（与 workbench_ui
  语法对齐：同字段并集、异字段交集）。空值归「（空）」段，取值超
  `--top`（默认 9）长尾合并「其他」。输出终端计数表（必有）；
  `--png` 显式才画饼图（matplotlib 可选依赖，中文按
  Microsoft YaHei→SimHei→Noto 探测防豆腐块）；`--dump-data` 导出
  画饼数据 csv（utf-8-sig + 纯 LF，与导出端编码纪律一致）。库锚定
  fields.json 同目录，无 --db 参数（软件设计准则）。算法表注册结构
  = GUI 预留数据源。新增 14 用例（计数/closed/where/日期三口径/
  top 合并/csv 导出/只读哈希/错误参数化 5/PNG），占位断言退役 1 条，
  全套 190 passed（PNG 1 条在无 matplotlib 环境跳过）
- **v3.4.2** 补丁合并版（用户裁定 v3.4.1 并入，编号取消）：
  ① 按钮文案修正：「导入Excel / 导出Excel」改名「导入 / 导出」——
  v3.4.0 落地 csv 导出后按钮已不限于 Excel，旧文案作废。GUI 现行文档
  （§六导入导出、§10.14 收藏夹语义）同步更新；v3.3.5 changelog 历史
  条目保持原文（描述当时事实）；
  ② 日历每日条数分视图可配置：`ui.calendar.max_per_day_view`（纯日历
  视图缺省 5，可配 1~5）与既有 `max_per_day`（聚合/周报，维持 1）分开。
  勘误修复：`max_per_day` 自引入起存而未用（渲染硬编码每格 1 条），
  本版接通渲染——每格循环画前 N 条，溢出折叠"还有N条"。视图在
  MainApp 构造时按 `--view` 一次性选定，无需运行时切换；check-config
  摘要改为同时显示两值并校验 1~5。周报模式沿用聚合的 1 条。
  新增用例 13 条（按钮文案 1、校验 8：合法 1/缺键兼容 1/越界与类型
  参数化 6、GUI 渲染 4：聚合回归 1/纯日历 5 条 1/封顶 1/可配置 1），
  删除 1 条过时用例（旧版"export 拒绝 csv"断言，v3.4.0 已反转），
  全套 177 passed
- **v3.4.0** CSV 导出（导入导出对称补齐）：
  ① CLI `export` 按扩展名分派：`.xlsx` 走原模板引擎；`.csv` 新增
  `exporter.export_csv`（列结构/取值规则与 xlsx 完全一致：模板列清单、
  const 列原样、空值补 default），`utf-8-sig` 编码 + 纯 LF——Excel
  双击打开中文不乱码，与导入端 `utf-8-sig` 读取天然对称；其余扩展名
  报"导出只支持 .xlsx / .csv"。原 help 文案"xlsx / csv，按扩展名"
  自本版起成为事实；
  ② GUI 跟进表导出文件对话框改为"Excel 或 CSV"（与导入对话框同一
  风格），按最终文件名后缀分派生成路径；收藏夹/周报模式置灰不受影响；
  ③ `weekly` 保持 xlsx-only 不动（双 sheet 带格式，csv 无意义）；
  ④ 按钮文案跟进：「导入Excel / 导出Excel」改名「导入 / 导出」——
  csv 落地后按钮已不限于 Excel，旧文案是 v3.4.0 之前的事实陈述，故
  记于本版而非历史条目；README 现行文档同步更新。
  新增 4 条用例（CLI csv 编码 1、csv 往返对称 1、非法扩展名 1、GUI
  后缀分派 1），删除 1 条过时用例（旧版"export 拒绝 csv"断言，行为已
  反转），另加按钮文案回归 1 条，全套 165 passed
- **v3.3.5** 接口补丁三连（收藏夹语义定稿）：
  ① 收藏夹面板新增"打开"按钮：与双击夹名同一入口（选中夹 → 进入
  筛选），照顾无法双击的场景（手指受伤等无障碍需求），双击保留；
  ② `workbench_ui list` 新增 `--fav 收藏夹名`：只看该夹内项目，输出
  追加「收藏夹」归属列（该项目所属全部收藏夹，顿号连接）；夹名不
  存在按业务错误退出码 1；纯索引的视图层过滤，与导入导出的全库
  语义无关；
  ③ 收藏夹模式下「导入Excel / 导出Excel」置灰：收藏夹是纯索引
  （软链接）视图，在视图里导入导出语义错误；置灰与周报模式同一
  手法，退出后按当前模式恢复（周报叠加时保持置灰）。CLI 无模式
  状态，import/export 恒为全库操作、不接受收藏夹参数——两种入口
  语义一致声明。
  新增 4 条回归用例（GUI 面板按钮 1、CLI 子进程 1、模式置灰 2），
  全套 161 passed
- **v3.3.2** 修复 `add_snapshot` 部分字段跟进的联动误判：项目名被
  "项目N"兜底覆盖、已完结项目被误标回 open。联动判定改为"未传字段从
  项目当前行继承"（GUI/CLI 全字段跟进本就不受影响，走数据库 API 的
  部分字段调用才会踩到；从上一快照继承会断链——上一快照也可能是
  部分的）；新增 2 条回归用例
- **v3.3.1** 测试适配：`test_setup_shims` 在 Windows
  跳过——它验证的是 setup.sh 的 bash shim + `~/.local/bin` 软链，
  属 Linux/macOS 机制（Windows 无软链权限必失败，且触发 GBK 解码
  警告）；Windows 的 shim 由 setup.ps1 生成，不在 pytest 覆盖范围。
  Windows 上全套测试现为 131 passed + 1 skipped（Python 3.14 实测）
- **v3.3.0** 命令行工作台 `workbench_ui`：主窗口全部 GUI 功能
  命令行化（list / show / new / follow / import / export / weekly /
  backup / notify / cal / fav，`gui` 子命令进入图形界面 = main.py）。
  纯逻辑内核 `bench_core` 与 GUI 共用：备份一份实现、`new`/`follow`
  的值校验同源（validate_* / check_date_bounds 自 editor.py 下沉
  db.py，GUI/CLI 两处一份）；库路径锚定 fields.json 同目录，无
  `--db`。`--where 字段=值` 可多次、日期支持区间；`notify` 只打印
  终端不走系统通知；`cal` 只读打印不接编辑。退出码 0/1/2
- **v3.2.0** 三视图模式 + 主程序命令行接口。启动视图三选一：
  **聚合**（日历+表格，现状不变）/ **仅日历**（表格与按钮行整体移除，
  日历吃满窗口；底部保留一行"新建项目"，点条目查看跟进、点日期看
  当天明细；日历恒显示全部时间节点）/ **仅表格**（隐藏日历，
  其余原样）。视图启动时定、运行中不切换、不回写配置。命令行：
  `--view calendar|table|aggregate`（优先级：命令行 > fields.json
  的 `ui.default_view` > 聚合）；`--check-config` 只校验
  fields.json（复用启动同款校验器），逐项列出错误、退出码
  0=通过 1=有错误，不建库不启动 GUI，无显示环境可跑，校验通过
  打印生效配置摘要。双击即用与库路径锚定规则完全不变
- **v3.1.1** 子模块命令行化 + 快捷命令：db_split / db_copy / db_append /
  db_assign / db_recycled / db_analysis 统一为四件套包结构
  （`__init__.py` 导出 + `*_core.py` 纯逻辑 + `*_gui.py` 的 `run_gui()`
  + `__main__.py` 命令行），全部支持 `python -m db_xxx` 与
  `python -m db_xxx --gui` 双入口；新增 `setup.ps`（Windows，纯英文）
  / `setup.sh`（Linux）一键生成 `db_split` 等单字命令。修复
  db_copy/db_append 列清单硬编码 milestone 导致真实配置下打不开的问题
  （列改按 fields.json 动态生成）。
- **v3.1.0** 回收站（`recycle_bin` 段开关，可缺省 = 关闭，默认与
  v2.7.3 等价）：开启后删除 = 项目/快照/收藏夹索引整体移入独立回收
  表，主程序全部视图天然排除；查看/恢复/彻底删除由独立模块
  `db_recycled/` 子模块负责（命令行 + GUI 双入口，永久删除 = 红色按钮 +
  二次确认）。恢复时原 id 空闲则原位放回（快照 id 重新分配、当前
  指针修正、收藏夹索引带回）。为将来的跨库合并打底：删除永不静默
  传播，永远有人工裁决口
- **v3.0.0** 测试基建（开发者侧能力，用户无感知）：新增 `tests/`
  自动化测试套件——L1 纯逻辑单测（查询引擎全组合、导入导出往返
  一致性、配置校验器全部错误分支）、L2 布局防回归（两次 pack
  顺序 BUG 变成永久用例）、L3 发布前冒烟脚本；`python -m pytest
  tests/ -q` 全绿成为每次发布的强制检查项。软件功能与 v2.7.3
  完全一致。
- **v2.7.3** 布局修复：① 收藏夹模式横幅与"共 N 条/翻页"合并为同一行，
  并保证该行锚定底部（表格下方）、窗口纵向紧张时不被吞掉——小窗口下
  "移出/退出收藏夹"始终可见（此前非最大化窗口底部被裁掉）；
  ② 项目详情里查看历史版本时，"正在查看历史版本"横幅停靠内容区
  最上方、只占一行（此前从滚动面板里弹出，被画布挤得占掉半页）
- **v2.7.2** 收藏夹交互修正：点主窗口任意处收藏夹面板自动抬回
  主窗口之上（不再沉到后面）；面板按钮更名为 新建/重命名/删除/
  加入；模式横幅在退出按钮左侧新增"移出"（把主表格选中项目从
  当前夹剔除索引，只删索引不动项目数据，夹空自动退出模式）；
  周报模式下"加入/移出"禁用置灰（收藏夹其余功能周报下照常可用；
  修复周报下打开收藏夹面板空窗口的问题）
- **v2.7.1** 收藏夹交互定稿：模式指示加强（窗口标题栏追加夹名 +
  按钮行下方模式横幅）；收藏夹面板新增"重命名此夹"；快捷键
  Ctrl+1~9 直达前 9 个收藏夹、Ctrl+0 退出模式；面板内不再显示
  夹内项目清单（选择的结果直接体现在日历与表格）；修复周报模式下
  搜索词不匹配项目名列导致切换视图空表的问题；README 全面修订
  （配置总览补齐 calendar_dates / date_check / favorites 等键、
  章节编号去重、过期内容更新）
- **v2.7.0** 收藏夹（favorites 段开关）：db 里新增
  collections/collection_items 两张纯索引表（存项目 id 引用，
  项目数据只有一份）；按钮行"收藏夹"按钮 → 建夹/删夹/重命名/把
  表格选中项目加入夹；进入收藏夹模式后主表格与日历同步只显示夹内
  项目（沿用现有筛选接口传 id 集合）；表头筛选的取值列表跟随视野；
  进入模式自动清除已有列筛选；收藏夹面板为非模态——不锁主窗口、
  可最小化、双击夹名即进入筛选、右上角叉关闭，面板打开期间主表格
  临时支持 Ctrl/Shift 多选用于批量加入收藏夹；周报模式全面联动
  （周报表格、周报日历、周报导出只含夹内项目）；跟进表导出不受
  模式影响；重启自动退出模式；enabled=false 时按钮不出现、db 不建表
- **v2.6.0** 配置校验器（启动即全量核对 fields.json，错误逐条列出：
  法定三日期字段、status、status_closed 必须在；周报法定四类
  start/followup/close/append 锁定，仅 label/颜色/日历显隐可配）；
  calendar_dates 每项新增 show_calendar（该类日期在日历显示与否；表格
  显隐与顺序仍由 display_mainsheet 管）；
  编辑器字段类型校验（日期/整数/实数逐字段弹错）；
  保存跟进时日期范围检查器（date_check 段：被检日期须在
  开始~关闭之间，开关与检查字段 JSON 可配）
- **v2.5.1** 更新README，作者联系方式，维护承诺等
- **v2.5.0** 更名"日历表格聚合项目跟进工作台"；日历日期类别全
  配置化（calendar_dates：开始/跟进/关闭/追加的显示名与颜色可配，
  可无限追加自定义日期字段——一个项目多个日历日期的特色由硬编码
  变为配置能力）；README 按设计评估重写定位与设计哲学
- **v2.4.1** 开源版精简：根目录仅提供全选模板 xlsx（周报模板保留在
  JSON、不发 xlsx 文件）；内置周报默认列兜底
- **v2.4.0** 开源版：新增 example/ 形态模板（求职、实验记录本）；
  根目录 fields.json 精简为必要模板；README 重写开头与联系方式
  （zifeng.xu@foxmail.com，欢迎捐赠/模板定制/咨询）
- **v2.3.0** db_split 输出文件名配方 JSON 化（split.components 四成分
  可排序 + prefix 前缀）；build_exe.ps1 全面重制（六件套全收录）
- **v2.2.0** 更名"日期表格聚合项目管理框架"（日历与表格聚合界面）；
  还有N条弹窗返回自动刷新；新增 db_split 按键分拆器（团队轮转分发
  环节）；db_analysis 占位；客户模板中性化命名；README 全面重构 +
  JSON 逐条详解
- v2.1.x 数据层 SQL 化（翻页式，30万启动约5秒）；列宽只增不减；
  默认排序 JSON 化（有误兜底 id 倒序）；日历弹窗统一数据入口
- v1.6.x 日期区间筛选；日历跟随筛选；批量赋值器 db_assign
- v1.5.x 周报模式；周报清洗器；PyInstaller；发布检查制度
- v1.4.x 周报只读视图化；标准/全选模板
- v1.3.x 单包发布；子模块化；LICENSE（MIT, Ken）
- v1.2.x 显示列可配（display_mainsheet）
- v1.1.x 历史穿越；db_copy/db_append
- v1.0.x 快照追溯、日历、搜索红点、筛选排序、模板、默认值、
  备份、通知
