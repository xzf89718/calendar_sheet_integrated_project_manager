# tests/ · 自动化测试套件（v3.0.0 起）

分层结构（详见 development_project.md「测试约定」）：

| 文件 | 层 | 内容 |
|------|-----|------|
| `test_db.py` | L1 纯逻辑 | 查询引擎 `_build_where`、分页、命名兜底、状态联动、收藏夹 CRUD、周报/日历供给、日期归一化 |
| `test_config.py` | L1 纯逻辑 | fields.json 校验器全部错误分支 + Config 装载行为 |
| `test_roundtrip.py` | L1 纯逻辑 | 导入导出往返一致性、单元格转换规则 |
| `test_gui_layout.py` | L2 GUI | 布局防回归（lrow 第一个 pack/bottom、收藏夹横幅钉位、reader 历史横幅钉位），需 DISPLAY |
| `smoke.py` | L3 冒烟 | 发布前手动跑：启动→翻页→搜索→收藏夹→导出→截图存档，不入 pytest |

## 运行

```bash
# L1（毫秒级，无 GUI 依赖）
python -m pytest tests/ -q --ignore=tests/test_gui_layout.py

# L2 + 全量（Linux/沙箱需虚拟显示）
xvfb-run -a python -m pytest tests/ -q

# L3 冒烟（发布前）
xvfb-run -a python tests/smoke.py        # Windows 去掉 xvfb-run
```

## 给改代码的人

- 所有测试用 **conftest.py 的最小 fields.json 配置** + 临时库，
  **绝不**读写源码目录的 fields.json / 真实 .db；
- conftest 的 `_patch_cfg` 负责替换四个模块里 `from config import CFG`
  绑死的模块级引用（含 db._SCHEMA、importer 的 DATE/INT/FLOAT/ALIASES、
  exporter 的 COLS/HEADS）——**新增同类模块级冻结量时必须同步补进那里**；
- GUI 用例禁用 `sleep`，断言一律 `winfo`/`pack_slaves` 几何，不做像素对比；
- 弹 `messagebox` 的路径在无窗口管理器下会永久阻塞，测试里必须打桩。
