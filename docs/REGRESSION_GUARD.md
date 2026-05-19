# REGRESSION_GUARD.md — 历史回归 bug + 测试覆盖

> 这份文件是给所有 AI 编程助手的"前车之鉴"清单。
> 修改下面任一函数前，**先看本文件相关章节**，避免把已修复的 bug 改回来。

## 速查表（"我要改的代码 → 历史回归"）

| 你要改 | 必看 |
|--------|------|
| `_analyze_suspicion` 的整数偏好/阈值规避 | Bug 3, Bug 4, P1（v2.3 修复后被 v2.5 回归） |
| `SuspicionConfig` 字段 | Bug 4（不要把 AML 阈值改成可调） |
| `_analyze_suspicion` 的黑名单评分 | Bug 1（黑名单一度未接入打分） |
| `_analyze_nominee` | Bug 2（数据不足时不能评分） |
| `_analyze_nominee` 工资关键词 | Bug 6（"自定义"占位符） |
| `_analyze_tenure` 的 fund 字段 | Bug 5（不要用 sum(amount)） |
| `_analyze_funds` / `_calc_throughput` | v2.2 跨载体循环重复计算（已通过 FIFO 池修复） |
| `CounterpartyAnalyzer.analyze` | P2（HHI 顶格）、P3（品牌名漏识） |
| `ConsumptionClassifier.classify_consumption` | Bug 7（酒店品牌被误归高端购物） |
| `_analyze_timeseries` / `_fixed_holiday` | D3——不要把模式分并入 A5、不要硬编码农历节日 |
| `_analyze_key_dates` | D4 关键时间点关联 |
| `aggregate_suspects` | D1——合并资金量必须剔除卡间互转，否则重复计 |
| `AssetClueDetector.RULES` | D5——只用 2+ 字关键词，排除词只压制弱层 |
| `analyze_relationship_strength` | G3——核心关系要求资金+通讯双维度都 ≥15 |
| `audit.AuditLogger` | C3——只记元信息不含原始流水，append-only |
| `trace_fund_chains` | D2——四约束(起点门槛+时间窗+金额相似+跳数)缺一不可，只输出最大链 |
| `interop.py` 任何函数 / `SCHEMA_ID` | 跨仓库契约——见 `docs/INTEROP_SPEC.md`，不能单方面改 |
| `test_engine.py` 中任何 assert | "测试断言不能放宽"——v2.5 教训（详见 Bug 3） |

---

## v2.2.0 — fund_size 跨载体循环重复计算

### 现象
存 80 万 → 买理财 80 万 → 赎 80.1 万（同一笔钱）
- 旧算法：cash_fund(80) + finance_fund(80) = 160 万 ❌
- 新算法：throughput = 80.1 万 ✓

### 修复
引入 `_calc_throughput` FIFO 循环池，统一处理现金/理财/同对手转账三类循环。

### 测试
- `test_scenario_5_pure_cash_loop` — 1000×10 次循环 → 1000
- `test_scenario_6_cash_to_finance` — 现金→理财→赎回 → 80.1万
- `test_scenario_7_same_counterparty_loop` — 同对手转账循环 → 1万
- `test_scenario_8_deposit_then_transfer` — 跨对手 → 累计 10万
- `test_scenario_18_tenure_uses_throughput` — 任职期资金量

### 警告
**绝不**为了"代码更简洁"把 throughput 改回简单加总。FIFO 池看起来复杂，但是唯一正确的算法。

---

## v2.3.0 P1 — 阈值规避 elif 短路

### 现象
原代码：
```python
if amt in (49000, 99000, 199000, ...):
    int_pref += 1
elif 45000 <= amt <= 51000:    # 49000 永远走不到这里
    near_50k += 1
```
49000/199000 这种"踩线金额"是反洗钱最强信号，但被整数偏好的 elif 短路，从未计入 near_50k/near_200k。

### 修复
拆成两个独立 if 分支：阈值规避计数 + 整数偏好计数同时累加。

### 测试
- `test_scenario_11_threshold_avoidance` — 阈值规避得分 ≥ 16

---

## v2.3.0 P2 — HHI 顶格让正常用户起步 15 分

### 现象
正常工资+消费用户因工资集中 → HHI ≈ 7000+ → 集中度顶格 15 分。所有用户最低 15 分起步，🟢 低 的语义稀释。

### 修复
1. 新增 `hhi_excl_salary`（剔除工资类对手）用于评分
2. 阈值从 2500 提到 5000-10000 区间映射
3. 非工资对手 < 5 时不评分

### 测试
- `test_scenario_12_normal_user_low_suspicion` — 正常用户 0 分

---

## v2.3.0 P3 — 对公漏识主流消费品牌

### 现象
`_BIZ_KEYWORDS` 没含品牌名，美团/支付宝/淘宝/京东/拼多多等被算"个人"。

### 修复
`_is_business` 复用 `TransactionClassifier.CONSUME_CP_KEYWORDS`。

### 测试
- `test_scenario_10_brand_is_business`

---

## v3.0.1 Bug 1 — B3 黑名单未接入打分（致命）

### 现象
v2.5 引入 `blacklist_keywords` 配置和 `blacklist_hits` 计数器。**但 `blacklist_hits` 这个变量从来没被加进 `score`**——只在日志里打印了一行。用户配的"博彩、虚拟币"完全无效。

### 修复
新增 `blacklist_weight=15` 权重，`bl_score = min(15, blacklist_hits * 5)`。

### 测试
- `test_scenario_14_blacklist_scoring` — 配黑名单后总分应升

### 警告
任何新加的"检测变量"都必须有相应的"评分项"+测试验证。引入了变量但没接入打分 = 假象的功能。

---

## v3.0.1 Bug 2 — C1 死户卡误判为高度疑似代持

### 现象
仅工资入账、零流出的死户卡：
- S5 默认 `non_consume_ratio = 1.0`（满分 30）
- 收入模式 100% 工资（满分 20）
- 消费缺位（满分 20）
- 总分 70 → 🔴 高度疑似代持

但**死户卡 ≠ 代持卡**。可能是闲置卡、社保卡、第二张工资卡。

### 修复
`len(outflows) < 3 or total_out < 1.0` 时直接返回 score=0、label="—（数据不足）"。

### 测试
- `test_scenario_15_nominee_dead_card` — 死户卡 score=0
- `test_scenario_16_real_nominee_pattern` — 真实代持仍能识别

---

## v3.0.1 Bug 3 — A5 灵敏度回归（v2.5 把 v2.3 P1 修复改回了）⭐

### 这是最严重的回归案例

#### 时间线
1. **v2.3.0**：修复 P1（阈值规避 elif 短路）。`test_scenario_13` 高可疑场景得 60+ 分🔴。
2. **v2.5.0**：B3 重写整数偏好检测逻辑（从硬编码列表改成"踩线-1000/-100"模式）。新逻辑下 50000（恰好等于阈值）不再触发整数偏好。`test_scenario_13` 得分降到 56 🟡。
3. **v2.5 开发者发现测试失败** → **把断言从 `≥60` 改成 `≥55`** 让测试通过 ❌
4. v3.0.1 审查发现，恢复算法语义（整数偏好命中表覆盖 50000/200000 自身）+ 恢复测试断言到 ≥60。

#### 教训
- 重写"通过测试的代码"不等于等价实现。要么不重写，要么写完后**重读所有相关测试场景**，理解测试要求的语义。
- 测试失败时**先理解原因**再决定怎么处理，不能为了让 CI 通过就放宽断言。

### 修复
整数偏好命中表新增 50000/200000 自身和 100000/500000 等倍数：
```python
integer_pref_targets = {
    aml_lo, aml_lo - 100, aml_lo - 1000,
    aml_hi, aml_hi - 100, aml_hi - 1000,
    aml_lo * 2, aml_lo * 2 - 100, aml_lo * 2 - 1000,
    aml_lo * 10, aml_lo * 10 - 100, aml_lo * 10 - 1000,
}
```

### 测试
- `test_scenario_13` 断言恢复到 `≥60` 🔴 高
- `test_scenario_11` 整数偏好 ≥ 18

### 警告（重要）
未来如果再重写整数偏好/阈值规避检测，**必须先跑现有测试**。任何分数下降都要按 v3.0.1 的方式修复，**不要再次放宽断言**。

---

## v3.0.1 Bug 4 — 阈值规避被 large_threshold 绑定（设计悖论）

### 现象
`large_threshold` 同时作为"大额标识阈值"和"反洗钱规避检测中线"。用户改 large_threshold 到 1 万 → 49000 不再被识别为反洗钱规避。

### 修复
```python
class SuspicionConfig:
    large_threshold: float = 50000.0       # 用户可调（仅用于"大额标识"统计）
    AML_THRESHOLDS: tuple = (50000.0, 200000.0)  # 类常量，法定值，用户不能调
```

阈值规避检测永远基于 `AML_THRESHOLDS`。

### 测试
- `test_scenario_17_aml_threshold_decoupled`

### 警告
**绝不**把 `AML_THRESHOLDS` 改成 dataclass 字段（让用户可调）。

---

## v3.0.1 Bug 5 — A3 任职期"资金量"实际是净流向

### 现象
`_analyze_tenure: fund = sum(t.amount for t in txs)` —— 是净流向，不是真实资金量。任职期间大额过账（收 100 万→立即转出 100 万）会被冲销显示为 0。

### 修复
改用 `_calc_throughput(txs)` 返回 throughput。

### 测试
- `test_scenario_18_tenure_uses_throughput`

### 警告
所有需要"真实资金通量"的统计都必须用 `_calc_throughput`。**永远不要用** `sum(t.amount)` 当资金量。

---

## v3.0.1 Bug 6 — C1 工资关键词含占位符"自定义"

### 现象
工资关键词列表 `["工资", "薪金", "奖金", "劳务", "代付", "自定义"]` 里的"自定义"是开发时的占位符。会把 `raw_type="自定义"` 的任意交易误判为工资类。

### 修复
删除"自定义"，补全为 `["工资", "薪金", "奖金", "劳务", "代付", "代发", "津贴"]`。

### 警告
留意所有关键词列表中的"占位符"或"测试用"字符串。代码 review 时一定要扫一遍。

---

## v3.0.1 Bug 7 — 万豪/希尔顿被归"高端购物"

### 现象
`classify_consumption` 先匹配 `LUXURY_BRANDS` 就 return，导致万豪/希尔顿/丽思卡尔顿被归"高端购物"，"酒店住宿"分类下没数据。

### 修复
两步分类，正交：
1. 先按 `CATEGORY_KEYWORDS` 匹配类别（跳过"高端购物"）
2. 再独立判断 `is_luxury`，只有原类别为"其他"才归"高端购物"

同时把高端酒店品牌补到 `CATEGORY_KEYWORDS["酒店住宿"]`。

### 测试
- `test_scenario_19_hotel_classification`

---

## v3.0.1 Issue 8 — v2.5 commit 标题宣告"B1 已完成"但未实现

### 现象
`915ab1a feat(v2.5.0): B3 可调阈值规则引擎 + B1 多银行合并基础` —— diff 里没有任何 B1 多银行合并代码。

### 教训
- commit message **必须**反映实际改动
- ROADMAP 标记功能完成时，必须有对应代码 + 单元测试

### 修复
ROADMAP 中 B1 标 "⏳ 待实现"。

---

## 更新这份文件

每修复一个回归 bug，**必须**：
1. 在本文件加一段：现象 / 修复 / 测试覆盖 / 警告
2. 在 `test_engine.py` 加对应回归测试
3. 在 `CHANGELOG.md` 记录
4. 如果涉及关键设计，同步更新 `DESIGN_DECISIONS.md`

不更新这份文件 = 下一个 LLM/开发者会重蹈覆辙。
