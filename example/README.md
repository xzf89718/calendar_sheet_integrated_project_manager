# 三个产品形态（example/）


同一套代码 + 一份 fields.json = 一个产品。**换形态 = 把 example 里
对应的文件复制为根目录 `fields.json`，重启即切换**：

| 形态 | 文件 | 场景 |
|------|------|------|
| **销售项目管理**（默认） | 根目录 fields.json | 销售/代理商跟进客户项目（客户/金额/概率/跟进） |
| 求职投递 | example/qiuzhi_fields.json | 投简历：公司/岗位/笔试面试阶段/被拒复盘 |
| 实验记录本 | example/shiyan_fields.json | 按日期记录实验：条件参数留痕、现象、成功/失败归档 |

example/ 内同时附带各形态的 Excel 模板（`qiuzhi_模板_*.xlsx`、
`shiyan_模板_*.xlsx`）。想为自己的业务定义第四个形态，照抄一份
改字段即可——详见 [FIELDS-CONFIG.md](../FIELDS-CONFIG.md)。

### 怎么替换形态（三步）

**核心一句话：无论复制哪个文件，根目录最终的文件名必须叫
`fields.json`——程序只认这一个名字。**

1. **关闭软件**（配置只在启动时读取）
2. 备份当前配置（随意命名，如 `fields_sales.json.bak`）：
   ```powershell
   copy fields.json fields_sales.json.bak
   ```
3. 把 example 里的形态文件**复制并改名**为根目录的 `fields.json`：
   ```powershell
   copy example\qiuzhi_fields.json fields.json     # 切到求职版
   copy example\shiyan_fields.json fields.json     # 切到实验记录本
   copy fields_sales.json.bak fields.json          # 切回销售版
   ```

   注意 `copy 源文件 目标文件` 的第二个参数就是新文件名，复制
   动作本身就完成了改名——复制完看一眼根目录，存在且只存在一份
   `fields.json` 即成功。

重启即生效。数据库不用动——新形态的字段自动补列，旧数据原样
保留；切回时原列重新出现。建议不同形态用不同数据文件（改各形态
JSON 里的 `db_name`，如 qiuzhi.db / shiyan.db），避免字段语义串味。
