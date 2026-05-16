# Changelog

## [3.0.2] - 2026-05-16

### 修复
- **P4 部分匹配存款剩余金额未扣除**：`CashChainMatcher.match()` 中存款被部分匹配后（如存20万取10万），`unmatched_dp` 仍返回原始金额20万而非剩余10万，导致 `cash_deposit_net` 和 `balance` 虚高
- **P5 `is_partial` 语义错误**：`is_partial = wd_amt > dp_remaining` 只在"取款>存款"时标记，改为 `wd_amt != dp_remaining`，存款与取款金额不等即为部分匹配

### 新增
- `parse_amount()` 支持银行常见负数格式：`(1,000.00)` → `-1000.0`，`1000.00-` → `-1000.0`

## [3.0.1] - 2026-05-01

### 修复（v2.4-3.0 审查发现的 7 个缺陷）

- **Bug 1（致命）**：B3 黑名单关键词未接入打分。`blacklist_hits` 计数器在 v2.5 引入但从未加入 `score`，导致用户配置的"博彩/虚拟币"等关键词完全无效。新增 `blacklist_weight=15` 权重，命中按 5 分/次累加封顶
- **Bug 2**：C1 代持识别误判死户卡。`total_out=0` 时默认 `non_consume_ratio=1.0` 让仅工资入账的死户卡评 70 分🔴。新增数据量门槛：流出 < 3 笔或合计 < 1 元时不评分，标记"—（数据不足）"
- **Bug 3**：A5 灵敏度回归。v2.5 重写整数偏好检测后 50000（恰好等于阈值）不再触发，让经典反洗钱场景从 60🔴 降到 56🟡。整数偏好命中表新增 `aml_lo / aml_hi`（即 50000/200000 自身）和 100000/500000 等倍数
- **Bug 4**：阈值规避检测被 large_threshold 绑定（设计悖论）。`SuspicionConfig` 新增 `AML_THRESHOLDS=(50000, 200000)` 法定固定值，与用户可调的 `large_threshold` 解耦。`large_threshold` 仅用于"大额标识"统计，反洗钱阈值规避检测永远基于法定值
- **Bug 5**：A3 任职期"资金量"语义错误。`sum(t.amount)` 是净流向（受消费/转出冲销），改为调用 `_calc_throughput()` 得到真实资金通量
- **Bug 6**：C1 工资关键词列表含占位符"自定义"。会把 `raw_type` 含此词的任意交易误判为工资。删除并补全为标准列表
- **Bug 7**：A4 万豪/希尔顿/丽思卡尔顿等酒店品牌被归"高端购物"。重写 `classify_consumption`：先按类别分类（酒店住宿/餐饮等），再独立标记 `is_luxury`，两个维度正交

### 新增
- `SuspicionConfig.AML_THRESHOLDS`、`SuspicionConfig.blacklist_weight`
- 6 个新单元测试场景（test_scenario_14~19）覆盖每个 bug 的回归路径

### 文档
- ROADMAP.md：B1 标 "⏳ 待实现"，纠正 v2.5.0 commit 标题中"B1 基础"的错误宣告
- CHANGELOG.md：补全 [2.4.0] / [2.5.0] / [3.0.0] 段（v2.4-3.0 之前未记录）

## [3.0.0] - 2026-05-01

### 新增（ROADMAP C 组）
- **C1 代持卡识别**：S5 过账模式 + S6 单一受益人 + 收入模式 + 消费缺位 → 0-100 分代持嫌疑评分
- **C2 证据包导出**：`generate_report()` 生成单卡 HTML 调查报告（含资金概览/可疑度/代持/Top10 对手/消费画像/任职期对比）；UI 新增「📄 导出证据报告 (HTML)」按钮

### 数据模型
- `CardReport.nominee_score / nominee_label / nominee_signals / nominee_beneficiary`
- `CardReport.has_tenure / tenure_before / tenure_during / tenure_after`
- `CardReport.consume_by_category / consume_luxury_count / consume_luxury_total / consume_luxury_brands`

## [2.5.0] - 2026-05-01

### 新增
- **B3 可调阈值规则引擎**：`SuspicionConfig` dataclass 支持调阈值（大额/深夜/HHI/黑名单/各项权重）
- UI 左侧面板新增「可疑度阈值 (B3)」配置区：大额阈值滑块、深夜时段设置、对手黑名单输入

### 已知问题（在 [3.0.1] 修复）
- 黑名单关键词命中数被检测但未接入打分（Bug 1）
- 阈值规避检测被 large_threshold 绑定（Bug 4）
- commit message 提及"B1 多银行合并基础"但代码未实现（Issue 8）

## [2.4.0] - 2026-05-01

### 新增（ROADMAP A 组扩展）
- **A3 任职期对比**：用户输入任职起止日期，自动对比"任职前/任职中/任职后"三段
- **A4 消费画像**：`ConsumptionClassifier` 多级消费分类（餐饮/酒店/旅游/医疗/教育/数码等 10+ 类） + 高端品牌识别（爱马仕/卡地亚/劳力士/茅台/万豪 等 100+ 品牌库）
- `analyze_bank_flow()` 接受 `tenure_start / tenure_end / suspicion_config` 参数

### 已知问题（在 [3.0.1] 修复）
- 任职期"资金量"实际是 sum(amount) 净流向（Bug 5）
- 万豪等酒店品牌被分类为"高端购物"而非"酒店住宿"（Bug 7）

## [2.3.0] - 2026-05-01

### 新增（ROADMAP A 组完成）
- **A1 对手分析**：Top N（金额/笔数/净流向）、对公对私分类、双向对手检测、HHI 集中度
- **A2-min 现金画像**：整数偏好、5万/20万阈值规避、深夜/周末交易统计
- **A5 可疑度打分**：0-100 分综合评分 → 🟢 低 / 🟡 中 / 🔴 高 三级分类

### 修复
- **P1 阈值规避评分 elif 短路 bug**：49000/199000 等踩线金额原本被"整数偏好"硬编码列短路，不再计入 near_50k/near_200k 计数。改成两个计数器独立累加，使最关键的反洗钱阈值规避信号能正确捕获
- **P2 HHI 顶格问题**：
  - 新增 `hhi_excl_salary`（剔除工资类对手后的集中度），用于可疑度评分避免正常工资人群顶格
  - 阈值从 2500 上调到 5000-10000 区间映射，更符合"集中度异常"的实际门槛
  - 新增"非工资对手 ≥5"门槛，数据太少时不评 HHI 分
- **P3 对公识别漏品牌名**：`CounterpartyAnalyzer._is_business` 复用 `TransactionClassifier.CONSUME_CP_KEYWORDS`，美团/支付宝/淘宝/京东/拼多多等品牌名不再被误判为"个人"
- **深夜交易评分对低质量数据的鲁棒性**：当 ≥50% 交易的 hour=0（数据只有日期没有具体时间）时，跳过深夜评分项，避免误判

### 测试
- 新增 5 个测试场景（test_scenario_9 ~ 13）：对手分析、品牌识别、阈值规避、正常用户、高可疑场景
- 测试覆盖：正常用户 0 分 🟢 / 高可疑 60+ 分 🔴 区分清晰

### 数据模型
- `CardReport` 新增字段：`cp_top_amount`, `cp_top_count`, `cp_top_net`, `cp_business_count`, `cp_personal_count`, `cp_bi_count`, `cp_hhi`, `cp_hhi_excl_salary`, `cp_salary_source_count`, `cp_total_players`, `suspicion_score`, `suspicion_label`, `suspicion_detail`

### UI 变化
- 单卡 Tab 新增「对手分析」子页（Top 10 对手 / 对公对私标签 / 双向对手标黄）
- 单卡顶部卡片新增「对手」「可疑度」概览
- 汇总表新增「对手数 / ⇄双向 / HHI / 可疑度」列

## [2.2.0] - 2026-05-01

### 重大变更
- **资金量算法重构**: 旧的"分项相加"（消费+转出去重+现金新增+min理财）改为统一的 FIFO 循环池 throughput 算法
- 修复了同一笔钱在多个渠道（现金↔理财↔同户转账）之间循环时被重复计算的 bug

### 修复
- **跨载体循环重复计算**: 存80万→买理财80万→赎80.1万 旧版误算成 160万，新版正确为 80.1万
- **同对手转账循环未去重**: 同对手转入1万→转出1万 ×10次 旧版误算成 10万，新版正确为 1万
- **现金+转账重复**: 存1万→转出9千 ×10次 旧版误算成 19万，新版正确为 10万

### 新增
- `_calc_throughput()` 统一处理三类循环（现金/理财/同户转账）的 FIFO 池算法
- 新 `fund_detail` 字段：现金循环抵销、理财循环抵销、同户转账循环抵销
- 4 个新测试场景覆盖核心 bug 路径
- README 多设备协作章节（git 工作流 + 数据隔离纪律）
- `.gitignore` 强化：默认拒绝所有 Excel/CSV，仅放行 `test_*` / `sample_*` / `demo_*` 前缀
- `.gitignore` 拦截案件目录（`真实数据/`、`证据/`、`case-data/`）和导出结果（`资金统计结果*.xlsx`）

### UI 变化
- 单卡顶部卡片新增"循环抵销(现/理/转)"显示
- 资金量来源说明改为 "取通量" / "取峰值"

## [2.1.0] - 2026-05-01

### 重大变更
- **框架迁移**: PyQt6 → PySide6
- **模块化重构**: UI 拆分为独立模块 (`parsers`, `widgets/left_panel`, `fund_header`, `summary_tab`, `card_tab`)
- **多卡分页**: 每卡独立 Tab + 汇总 Tab（多卡横向对比表）
- **资金量分析**: 入/出校验 + 最小值法 + max(峰值,最小资金量) 取最终资金量

### 新增
- 资金量突出显示：顶部大字蓝色高亮
- 余额校验：`入-出 == 余额+未到期理财`，精确到分
- 借贷标志自动识别（进/出/借/贷/收入/支出等）
- 多 Sheet 自动选择（优先「交易明细」sheet）
- 同户转入出循环检测
- 建设银行模板适配（多 Sheet、交易类型+交易摘要组合分类）
- 黑龙江省农村信用社模板适配
- 分类顺序优化（收入/退款关键词优先于消费）
- 新增交易关键词：`支取`、`充值`、`管理费`、`收费`、`利息存入`、`退货`、`提现`、`入账`

### 修复
- 余额公式修正：由 `cash_deposit_net` 改为分类合计直接计算，消除部分匹配误差
- 消费退货/支付机构提现不再被误判为消费
- `%Y%m%d%H%M%S` 日期格式支持

### 打包
- 排除 PyQt6/PyQt5 避免 Qt 绑定冲突
- CI 构建使用 PySide6 + `--exclude-module PyQt6`

## [2.0.0] - 2026-04-27

### 新增
- 完全重写核心分析引擎 `engine.py`
- 交易自动四分类：现金存取、理财交易、消费支出、转账
- 现金存取链配对算法（贪婪匹配，支持多笔存取链）
- 理财买卖配对算法（买入↔赎回匹配，计算利息和未赎回金额）
- 4套UI主题：Light / Dark / Classic / High Contrast
- 统计过程可视化（展示每步配对操作）
- GitHub Actions 自动构建（Windows .exe + macOS .app/.dmg）
- 自动发布（推送 tag 触发）
- 版本号管理 `version.py`

### 修复
- 存取配对从简单两两配对改为链条配对
- 理财合并从金额去重改为买卖配对
- 统计口径调整为保守估计（宁可少算不重复算）

## [1.0.0] - 2026-04-27

### 初始版本
- 基础银行流水导入（Excel/CSV）
- 简单理财产品金额去重
- 简单取现存现两两配对
- 按账户汇总
- Excel 导出
