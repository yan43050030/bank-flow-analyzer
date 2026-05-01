# CLAUDE.md — AI 辅助开发须知

> 本文件给所有 AI 编程助手（Claude / GPT / Gemini / Cursor 等）阅读。
> 在修改本仓库代码前，务必先读完。

## 项目背景

**用途**：职务犯罪调查辅助工具，分析银行流水、识别可疑账户、定位代持卡。

**用户**：纪检/检察/公安系统办案人员。**误判会产生司法后果**——宁可漏报，不可误报。

**部署**：纯本地运行，**真实案件数据绝不入 Git**。仅 `test_*` / `sample_*` / `demo_*` 前缀的合成数据可入库。

## 修改前必读

修改 `engine.py` 中以下任一函数 / 类前，**必须**先读对应章节：

| 修改位置 | 必读文档 |
|---------|---------|
| `_calc_throughput` / `_analyze_funds` | `docs/DESIGN_DECISIONS.md#资金量算法` |
| `_analyze_suspicion` | `docs/DESIGN_DECISIONS.md#可疑度打分` + `docs/REGRESSION_GUARD.md#bug-3-bug-4` |
| `SuspicionConfig` | `docs/DESIGN_DECISIONS.md#aml-阈值不可调` |
| `_analyze_nominee` | `docs/DESIGN_DECISIONS.md#代持卡数据门槛` |
| `_analyze_tenure` | `docs/DESIGN_DECISIONS.md#任职期资金量` |
| `ConsumptionClassifier` | `docs/DESIGN_DECISIONS.md#消费分类` |
| `CounterpartyAnalyzer` | `docs/DESIGN_DECISIONS.md#hhi-排除工资` |

## 七条铁律（违反等于回归）

1. **绝不**把 `AML_THRESHOLDS`（5万/20万）合并进 `large_threshold`——它们是两个不同概念。理由见 [DESIGN_DECISIONS.md AML 阈值不可调](docs/DESIGN_DECISIONS.md#aml-阈值不可调)。
2. **绝不**用 `sum(t.amount)` 当资金量——那是净流向。资金量必须用 `_calc_throughput` 的 FIFO 循环池算法。理由见 [DESIGN_DECISIONS.md 资金量算法](docs/DESIGN_DECISIONS.md#资金量算法)。
3. **绝不**让数据量不足的账户（流出 < 3 笔）参与代持评分——会把死户卡误判为高度疑似。
4. **绝不**让 HHI 集中度评分包含工资类对手——正常工资人群天然集中，会顶格 15 分。
5. **绝不**在低质量数据（≥50% 交易 hour=0）上评深夜分——会让所有交易看起来都在深夜。
6. **绝不**通过放宽测试断言来让测试通过——测试是规格，断言失败说明代码错了。
7. **绝不**用 `git add .` 或 `git add -A`——可能误传案件数据。只 add 具体文件名。

## 工作流

### 改代码前
1. 读相关 [DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) 章节
2. 在 [REGRESSION_GUARD.md](docs/REGRESSION_GUARD.md) 检查这块代码是否曾有回归历史
3. 看 `test_engine.py` 中相关测试场景，理解断言含义

### 改代码后
1. **必须**跑 `python3 test_engine.py`——19 个测试全过才能提交
2. 如果改了算法逻辑，**必须**新增对应回归测试
3. 修复 bug 后，把 bug 加入 [REGRESSION_GUARD.md](docs/REGRESSION_GUARD.md)，让下一个 LLM 知道

### 提交前
1. 改 `engine.py` → 升 patch 版本（如 3.0.1 → 3.0.2）
2. 改算法语义 / 数据模型 → 升 minor 版本（3.0.x → 3.1.0）
3. 不兼容改动 → 升 major（3.x → 4.0）
4. **必须**更新 `CHANGELOG.md`——历史断层等于失忆
5. 不要在没人要求的情况下创建文档文件（README/MD），但 CHANGELOG / DESIGN_DECISIONS / REGRESSION_GUARD 必须维护

## 不要做

- ❌ "顺手"重构通过测试的代码——你能跑通测试不代表你的实现等价（v2.5 重写整数偏好就是这种翻车）
- ❌ 把 `# CRITICAL:` 注释删除——那是给下一个 LLM 的安全锁
- ❌ 在 commit message 宣告未实现的功能（如 v2.5.0 错误宣告"B1 已完成"）
- ❌ 在没读 DESIGN_DECISIONS.md 的情况下"优化"打分权重
- ❌ 创建 `*.md` 路线图文档（除非用户明确要求）

## 关键命令

```bash
# 测试（必须 19/19 通过）
python3 test_engine.py

# 启动 UI（需要 PySide6）
python3 fund_analyzer.py

# 检查无敏感数据被加进来
git status                  # 看到 .xlsx/.csv 警惕，除非是 test_ 前缀
git check-ignore <文件>     # 验证文件是否被 .gitignore 拦截
```

## 我若不知道某个功能为什么这么设计

去 `docs/DESIGN_DECISIONS.md` 查；如果没有，说明 **没有人类决策依据，请询问用户而不是自行决定**。
