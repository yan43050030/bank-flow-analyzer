#!/usr/bin/env python3
"""测试核心引擎算法"""

import sys
import os
import json
import tempfile
from datetime import datetime
from engine import (
    Transaction, TransactionClassifier,
    CashChainMatcher, FinanceMatcher,
    CardAnalyzer, analyze_bank_flow
)
from interop import (
    SCHEMA_ID, InteropPackage, InteropError,
    load_interop_package, save_interop_package,
    reports_to_transaction_events, build_export_package,
    analyze_transfer_call_correlation,
)


def make_tx(date_str, card, raw_type, amount, name="测试", cp="", rmk=""):
    """快捷创建交易"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return Transaction(date=d, card=card, name=name, raw_type=raw_type,
                       amount=amount, counterparty=cp, remark=rmk)


def test_scenario_1():
    """理财循环: 存100万→买100万→赎100.1万→买100万→赎100.1万"""
    print("\n" + "=" * 60)
    print("测试1: 理财循环（两次买入赎回）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "存款", 1000000),
        make_tx("2024-01-02", "6222", "理财购买", -1000000),
        make_tx("2024-01-03", "6222", "理财赎回", 1001000),
        make_tx("2024-01-04", "6222", "理财购买", -1000000),
        make_tx("2024-01-05", "6222", "理财赎回", 1001000),
    ]

    result = analyze_bank_flow(txs)
    r = result.reports[0]
    print(f"历史最高资金: {r.peak_funds:,.0f} (预期 1,000,000)")
    print(f"卡内余额: {r.balance:,.0f} (预期 1,002,000)")
    print(f"理财本金: {r.finance_principal:,.0f} (预期 1,000,000)")
    print(f"理财获利: {r.finance_profit:,.0f} (预期 2,000)")
    print(f"理财未赎回: {r.finance_unredeemed:,.0f} (预期 0)")

    assert r.finance_principal == 1000000, f"本金应为1000000, got {r.finance_principal}"
    assert r.finance_profit == 2000, f"获利应为2000, got {r.finance_profit}"
    assert r.finance_unredeemed == 0, f"未赎回应为0, got {r.finance_unredeemed}"
    print("✅ 测试1通过")


def test_scenario_2():
    """存取反复: 存100→取100→存200→取150→存100"""
    print("\n" + "=" * 60)
    print("测试2: 存取反复（多次存取链条）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "存款", 1000000),
        make_tx("2024-01-02", "6222", "取款", -1000000),
        make_tx("2024-01-03", "6222", "存款", 2000000),
        make_tx("2024-01-04", "6222", "取款", -1500000),
        make_tx("2024-01-05", "6222", "存款", 1000000),
    ]

    result = analyze_bank_flow(txs)
    r = result.reports[0]
    print(f"历史最高资金: {r.peak_funds:,.0f} (预期 2,000,000)")
    print(f"卡内余额: {r.balance:,.0f} (预期 1,500,000)")
    # 解释：存100后取100→余额0，再存200→峰值200万，再取150→剩余50，再存100→余额150万
    print(f"配对对数: {len(r.cash_pairs)} (预期 2)")
    print(f"存取经过: {r.cash_paired:,.0f} (预期配对部分金额)")

    print("✅ 测试2完成")


def test_scenario_3():
    """未赎回理财: 存100万→买理财80万"""
    print("\n" + "=" * 60)
    print("测试3: 未赎回理财")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "存款", 1000000),
        make_tx("2024-01-02", "6222", "理财购买", -800000),
    ]

    result = analyze_bank_flow(txs)
    r = result.reports[0]
    print(f"历史最高资金: {r.peak_funds:,.0f} (预期 1,000,000)")
    print(f"卡内余额: {r.balance:,.0f} (预期 200,000)")
    print(f"理财未赎回: {r.finance_unredeemed:,.0f} (预期 800,000)")

    assert r.finance_unredeemed == 800000, f"未赎回应为800000, got {r.finance_unredeemed}"
    print("✅ 测试3通过")


def test_scenario_4():
    """复杂场景：存取+理财+消费混合"""
    print("\n" + "=" * 60)
    print("测试4: 综合场景")
    print("=" * 60)

    txs = [
        # 工资存入
        make_tx("2024-01-01", "6222", "工资", 500000),
        # 存取反复
        make_tx("2024-01-02", "6222", "取款", -200000),
        make_tx("2024-01-05", "6222", "存款", 300000),
        make_tx("2024-01-06", "6222", "取款", -100000),
        # 买理财
        make_tx("2024-01-10", "6222", "理财购买", -300000),
        make_tx("2024-03-10", "6222", "理财赎回", 305000),
        # 再买（部分赎回）
        make_tx("2024-03-15", "6222", "理财购买", -400000),
        # 消费
        make_tx("2024-02-01", "6222", "消费", -5000, cp="支付宝"),
        make_tx("2024-04-01", "6222", "消费", -3000, cp="美团"),
        # 转账
        make_tx("2024-02-15", "6222", "转账", -50000, cp="张三"),
        make_tx("2024-05-01", "6222", "转账", 20000, cp="李四"),
    ]

    result = analyze_bank_flow(txs)
    r = result.reports[0]
    print(f"历史最高资金: {r.peak_funds:,.0f}")
    print(f"卡内余额: {r.balance:,.0f}")
    print(f"理财未赎回: {r.finance_unredeemed:,.0f}")
    print(f"理财本金: {r.finance_principal:,.0f}")
    print(f"理财获利: {r.finance_profit:,.0f}")
    print(f"消费支出: {r.consume_total:,.0f} (预期 8,000)")
    print(f"转出: {r.transfer_out:,.0f} (预期 50,000)")
    print(f"转入: {r.transfer_in:,.0f} (预期 20,000)")
    print(f"存取配对对数: {len(r.cash_pairs)}")

    assert r.consume_total == 8000, f"消费应为8000, got {r.consume_total}"
    print("✅ 测试4通过")


def test_scenario_5_pure_cash_loop():
    """资金量去重：1000元存入又取出，反复10次 → 应=1000，而不是10000"""
    print("\n" + "=" * 60)
    print("测试5: 纯现金存取循环（1000×10次）")
    print("=" * 60)

    txs = []
    for i in range(10):
        txs.append(make_tx(f"2024-01-{i*2+1:02d}", "6222", "存款", 1000))
        txs.append(make_tx(f"2024-01-{i*2+2:02d}", "6222", "取款", -1000))

    r = analyze_bank_flow(txs).reports[0]
    print(f"入账合计: {r.total_income:,.0f}")
    print(f"出账合计: {r.total_expense:,.0f}")
    print(f"历史峰值: {r.peak_funds:,.0f}")
    print(f"资金量(fund_size): {r.fund_size:,.0f} (预期 1,000)")

    assert r.fund_size == 1000, f"资金量应为1000(同笔钱循环), got {r.fund_size}"
    print("✅ 测试5通过")


def test_scenario_6_cash_to_finance():
    """跨载体循环：存80万→买理财80万→赎80.1万 → 应≈80万，而不是160万"""
    print("\n" + "=" * 60)
    print("测试6: 现金→理财→赎回（同一笔钱跨载体循环）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "存款", 800000),
        make_tx("2024-01-02", "6222", "理财购买", -800000),
        make_tx("2024-03-02", "6222", "理财赎回", 801000),
    ]
    r = analyze_bank_flow(txs).reports[0]
    print(f"资金量(fund_size): {r.fund_size:,.0f} (预期 801,000 = 本金80万+利息0.1万)")

    assert r.fund_size == 801000, f"资金量应为801000, got {r.fund_size}"
    print("✅ 测试6通过")


def test_scenario_7_same_counterparty_loop():
    """同对手转账循环：转入1万→转出1万×10次 → 应=1万，而不是10万"""
    print("\n" + "=" * 60)
    print("测试7: 同对手转账循环（1万×10次）")
    print("=" * 60)

    txs = []
    for i in range(10):
        txs.append(make_tx(f"2024-01-{i*2+1:02d}", "6222", "转账", 10000, cp="张三"))
        txs.append(make_tx(f"2024-01-{i*2+2:02d}", "6222", "转账", -10000, cp="张三"))

    r = analyze_bank_flow(txs).reports[0]
    print(f"资金量(fund_size): {r.fund_size:,.0f} (预期 10,000)")

    assert r.fund_size == 10000, f"资金量应为10000, got {r.fund_size}"
    print("✅ 测试7通过")


def test_scenario_8_deposit_then_transfer():
    """无循环连续新增：存1万→转出9000×10次 → 应=10万（10次新存款）"""
    print("\n" + "=" * 60)
    print("测试8: 连续新增资金（存1万→转出9千×10次）")
    print("=" * 60)

    txs = []
    for i in range(10):
        txs.append(make_tx(f"2024-01-{i*2+1:02d}", "6222", "存款", 10000))
        txs.append(make_tx(f"2024-01-{i*2+2:02d}", "6222", "转账", -9000, cp="李四"))

    r = analyze_bank_flow(txs).reports[0]
    print(f"资金量(fund_size): {r.fund_size:,.0f} (预期 100,000)")

    assert r.fund_size == 100000, f"资金量应为100000, got {r.fund_size}"
    print("✅ 测试8通过")


def test_scenario_9_counterparty_basic():
    """A1 对手分析：双向检测 + 对公识别 + HHI"""
    print("\n" + "=" * 60)
    print("测试9: 对手分析（双向/对公/HHI）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "工资", 10000, cp="某某科技有限公司"),
        make_tx("2024-01-03", "6222", "转账", 5000, cp="李四"),
        make_tx("2024-01-04", "6222", "转账", -3000, cp="李四"),  # 双向
        make_tx("2024-01-05", "6222", "转账", -2000, cp="王五"),
    ]
    r = analyze_bank_flow(txs).reports[0]

    print(f"对手总数: {r.cp_total_players} (期望 3)")
    print(f"双向对手: {r.cp_bi_count} (期望 1)")
    print(f"对公: {r.cp_business_count} (期望 1)")
    print(f"HHI: {r.cp_hhi:.0f} | 剔工资 HHI: {r.cp_hhi_excl_salary:.0f}")
    print(f"工资类对手: {r.cp_salary_source_count} (期望 1: 公司)")

    assert r.cp_total_players == 3
    assert r.cp_bi_count == 1, f"双向应为1: {r.cp_bi_count}"
    assert r.cp_business_count == 1
    assert r.cp_salary_source_count == 1, f"工资类应为1: {r.cp_salary_source_count}"
    print("✅ 测试9通过")


def test_scenario_10_brand_is_business():
    """P3: 美团/支付宝/淘宝等品牌名应识别为对公"""
    print("\n" + "=" * 60)
    print("测试10: 消费品牌名识别为对公（P3 修复）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-01", "6222", "消费", -100, cp="美团"),
        make_tx("2024-01-02", "6222", "消费", -200, cp="支付宝"),
        make_tx("2024-01-03", "6222", "消费", -300, cp="淘宝"),
        make_tx("2024-01-04", "6222", "转账", -500, cp="李四"),
    ]
    r = analyze_bank_flow(txs).reports[0]

    print(f"对公: {r.cp_business_count} (期望 3: 美团/支付宝/淘宝)")
    print(f"个人: {r.cp_personal_count} (期望 1: 李四)")

    assert r.cp_business_count == 3, f"对公应为3: {r.cp_business_count}"
    assert r.cp_personal_count == 1
    print("✅ 测试10通过")


def test_scenario_11_threshold_avoidance():
    """P1: 49000/199000 应同时计入 整数偏好 + 阈值规避"""
    print("\n" + "=" * 60)
    print("测试11: 阈值规避评分（P1 修复 elif 短路）")
    print("=" * 60)

    # 6 笔阈值规避典型金额
    txs = [
        make_tx("2024-01-01", "6222", "存款", 49000),
        make_tx("2024-01-02", "6222", "存款", 49000),
        make_tx("2024-01-03", "6222", "存款", 49000),
        make_tx("2024-01-04", "6222", "存款", 199000),
        make_tx("2024-01-05", "6222", "存款", 199000),
        make_tx("2024-01-06", "6222", "取款", -199000),
    ]
    r = analyze_bank_flow(txs).reports[0]

    print(f"可疑度: {r.suspicion_score:.0f} {r.suspicion_label}")
    print(f"明细: {r.suspicion_detail}")
    print(f"  - 整数偏好: {r.suspicion_detail.get('整数偏好', 0):.0f}/20")
    print(f"  - 阈值规避: {r.suspicion_detail.get('阈值规避', 0):.0f}/20")

    # 修复前阈值规避会是 0；修复后应有显著得分（near_50k=3, near_200k=3）
    assert r.suspicion_detail.get("阈值规避", 0) >= 16, \
        f"阈值规避得分太低: {r.suspicion_detail.get('阈值规避', 0)}"
    # 整数偏好也应满分（6 笔×3 = 18 → 顶格 20）
    assert r.suspicion_detail.get("整数偏好", 0) >= 18, \
        f"整数偏好得分: {r.suspicion_detail.get('整数偏好', 0)}"
    print("✅ 测试11通过")


def test_scenario_12_normal_user_low_suspicion():
    """P2: 正常工资+消费用户不应因 HHI 顶格而误判"""
    print("\n" + "=" * 60)
    print("测试12: 正常用户可疑度（P2 修复 HHI 评分）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-15", "6222", "工资", 8000, cp="某某公司"),
        make_tx("2024-01-16", "6222", "消费", -300, cp="美团"),
        make_tx("2024-01-18", "6222", "消费", -150, cp="超市"),
        make_tx("2024-01-20", "6222", "消费", -2000, cp="百货"),
        make_tx("2024-02-15", "6222", "工资", 8000, cp="某某公司"),
        make_tx("2024-02-16", "6222", "消费", -350, cp="美团"),
    ]
    r = analyze_bank_flow(txs).reports[0]

    print(f"可疑度: {r.suspicion_score:.0f} {r.suspicion_label}")
    print(f"明细: {r.suspicion_detail}")
    print(f"剔除工资 HHI: {r.cp_hhi_excl_salary:.0f}")
    print(f"非工资对手数: {r.cp_total_players - r.cp_salary_source_count}")

    # 正常用户：HHI 项应为 0（非工资对手 < 5）
    assert r.suspicion_detail.get("对手集中度", 0) == 0, \
        f"正常用户 HHI 不应得分: {r.suspicion_detail.get('对手集中度', 0)}"
    # 总分应为低
    assert r.suspicion_score <= 15, f"正常用户可疑度过高: {r.suspicion_score}"
    print("✅ 测试12通过")


def test_scenario_13_high_suspicion_full():
    """高可疑场景综合：阈值规避 + 深夜 + 双向过账 + 集中度 → 应为🔴高"""
    print("\n" + "=" * 60)
    print("测试13: 高可疑场景综合识别")
    print("=" * 60)

    from datetime import datetime
    def mk(date_h, raw, amt, cp=""):
        return Transaction(
            date=datetime.strptime(date_h, "%Y-%m-%d %H:%M"),
            card="6222", name="嫌疑人", raw_type=raw, amount=amt, counterparty=cp)

    txs = [
        mk("2024-01-01 23:30", "存款", 49000),
        mk("2024-01-02 23:45", "存款", 49000),
        mk("2024-01-03 02:15", "存款", 49000),
        mk("2024-01-05 23:00", "存款", 199000),
        mk("2024-01-06 22:30", "取款", -199000),
        mk("2024-01-07 14:00", "转账", -50000, cp="某某代持"),
        mk("2024-01-08 14:00", "转账", 50000, cp="某某代持"),
        mk("2024-01-09 14:00", "转账", -50000, cp="某某代持"),
    ]
    r = analyze_bank_flow(txs).reports[0]

    print(f"可疑度: {r.suspicion_score:.0f} {r.suspicion_label}")
    print(f"明细: {r.suspicion_detail}")

    # Bug 3 修复后恢复原断言：高可疑场景应能上 🔴 高（≥60）
    assert r.suspicion_score >= 60, f"高可疑应≥60: {r.suspicion_score}"
    assert "高" in r.suspicion_label, f"label 应为高: {r.suspicion_label}"
    print("✅ 测试13通过")


def test_scenario_14_blacklist_scoring():
    """Bug 1: 黑名单关键词应实际接入打分"""
    print("\n" + "=" * 60)
    print("测试14: 黑名单关键词接入打分（Bug 1）")
    print("=" * 60)
    from engine import SuspicionConfig

    # 不配黑名单 — 基线分
    txs_base = [
        make_tx("2024-01-01", "6222", "转账", -50000, cp="某某博彩公司"),
        make_tx("2024-01-02", "6222", "转账", -50000, cp="正常公司"),
    ]
    r0 = analyze_bank_flow(txs_base).reports[0]
    base_score = r0.suspicion_score

    # 配博彩黑名单 — 应升分
    cfg = SuspicionConfig(blacklist_keywords=["博彩", "虚拟币"])
    r1 = analyze_bank_flow(txs_base, suspicion_config=cfg).reports[0]
    print(f"基线分: {base_score:.0f}, 配黑名单后: {r1.suspicion_score:.0f}")
    print(f"明细: {r1.suspicion_detail}")

    bl_score = r1.suspicion_detail.get("黑名单命中", 0)
    assert bl_score > 0, f"黑名单评分应>0: {bl_score}"
    assert r1.suspicion_score > base_score, \
        f"配置黑名单后总分应升: {base_score} → {r1.suspicion_score}"
    print("✅ 测试14通过")


def test_scenario_15_nominee_dead_card():
    """Bug 2: 死户卡（仅工资入账，无任何流出）不应被评高代持嫌疑"""
    print("\n" + "=" * 60)
    print("测试15: 死户卡代持评分豁免（Bug 2）")
    print("=" * 60)

    txs = [
        make_tx("2024-01-15", "6222", "工资", 8000, cp="某某公司"),
        make_tx("2024-02-15", "6222", "工资", 8000, cp="某某公司"),
        make_tx("2024-03-15", "6222", "工资", 8000, cp="某某公司"),
    ]
    r = analyze_bank_flow(txs).reports[0]
    print(f"代持评分: {r.nominee_score:.0f} {r.nominee_label}")
    print(f"信号: {r.nominee_signals}")

    assert r.nominee_score == 0, f"死户卡不应评分: {r.nominee_score}"
    assert "数据不足" in r.nominee_label, f"应标数据不足: {r.nominee_label}"
    print("✅ 测试15通过")


def test_scenario_16_real_nominee_pattern():
    """Bug 2 反向：真实代持模式仍应识别为高度疑似"""
    print("\n" + "=" * 60)
    print("测试16: 真实代持模式（工资入→全部转给同一受益人）")
    print("=" * 60)

    txs = []
    for m in range(1, 7):
        txs.append(make_tx(f"2024-{m:02d}-15", "6222", "工资", 10000, cp="某某公司"))
        txs.append(make_tx(f"2024-{m:02d}-16", "6222", "转账", -10000, cp="王大老板"))
    r = analyze_bank_flow(txs).reports[0]
    print(f"代持评分: {r.nominee_score:.0f} {r.nominee_label}")
    print(f"受益人: {r.nominee_beneficiary}")

    assert r.nominee_score >= 80, f"真实代持应≥80: {r.nominee_score}"
    assert "高" in r.nominee_label or "疑似" in r.nominee_label
    assert "王大老板" in r.nominee_beneficiary
    print("✅ 测试16通过")


def test_scenario_17_aml_threshold_decoupled():
    """Bug 4: 用户改 large_threshold 不应影响法定反洗钱阈值检测"""
    print("\n" + "=" * 60)
    print("测试17: AML 阈值与 large_threshold 解耦（Bug 4）")
    print("=" * 60)
    from engine import SuspicionConfig

    txs = [
        make_tx("2024-01-01", "6222", "存款", 49000),
        make_tx("2024-01-02", "6222", "存款", 49000),
        make_tx("2024-01-03", "6222", "存款", 49000),
    ]
    # 默认配置 — 应捕获 49000 阈值规避
    r1 = analyze_bank_flow(txs).reports[0]
    th1 = r1.suspicion_detail.get("阈值规避", 0)
    print(f"默认阈值: 阈值规避={th1:.0f}")

    # 用户把 large_threshold 改到 1万 — AML 检测仍基于法定 5万
    cfg = SuspicionConfig(large_threshold=10000)
    r2 = analyze_bank_flow(txs, suspicion_config=cfg).reports[0]
    th2 = r2.suspicion_detail.get("阈值规避", 0)
    print(f"large=1万: 阈值规避={th2:.0f} (应仍捕获 49000)")

    assert th1 > 0 and th2 > 0, \
        f"AML 检测不应被 large_threshold 影响: th1={th1} th2={th2}"
    assert th1 == th2, f"阈值规避得分应相同: {th1} vs {th2}"
    print("✅ 测试17通过")


def test_scenario_18_tenure_uses_throughput():
    """Bug 5: A3 任职期"资金量"应是 throughput 而非 sum(amount)"""
    print("\n" + "=" * 60)
    print("测试18: 任职期资金量用 throughput（Bug 5）")
    print("=" * 60)

    # 任职期 6 个月：每月入 11万 + 出 11万（净流向≈0，但实际经过 66万）
    txs = []
    for m in range(1, 7):
        txs.append(make_tx(f"2024-{m:02d}-10", "6222", "转账", 110000, cp="A"))
        txs.append(make_tx(f"2024-{m:02d}-20", "6222", "转账", -110000, cp="B"))
    # 任职前后零交易，为了创建三段须有任职前后数据
    txs = [make_tx("2023-12-01", "6222", "工资", 10000, cp="公司")] + txs + \
          [make_tx("2024-08-01", "6222", "工资", 10000, cp="公司")]

    result = analyze_bank_flow(
        txs,
        tenure_start=datetime(2024, 1, 1),
        tenure_end=datetime(2024, 6, 30),
    )
    r = result.reports[0]
    during_fund = r.tenure_during.get("资金量", 0)
    print(f"任职中资金量: {during_fund:,.0f}")
    print(f"  (sum(amount) ≈ 0；throughput 应反映 6 笔进+6 笔出 ≈ 66万 或 110万跨对手新流入)")

    # throughput 算法：跨对手转账不形成循环，所以 6 笔流入 = 66万
    assert during_fund >= 600000, \
        f"任职期资金量应反映真实通量(≥66万)，不是净流向: {during_fund}"
    print("✅ 测试18通过")


def test_scenario_19_hotel_classification():
    """Bug 7: 万豪/希尔顿应归"酒店住宿"，并保留 luxury 标签"""
    print("\n" + "=" * 60)
    print("测试19: 酒店品牌分类（Bug 7）")
    print("=" * 60)
    from engine import ConsumptionClassifier

    cases = [
        ("万豪酒店", "酒店住宿", True),
        ("希尔顿", "酒店住宿", True),
        ("丽思卡尔顿", "酒店住宿", True),
        ("爱马仕", "高端购物", True),    # 无类别标签，仍归高端购物
        ("Costco超市", "日用百货", False),
        ("星巴克", "餐饮", False),
    ]
    for name, expect_cat, expect_luxury in cases:
        info = ConsumptionClassifier.classify_consumption(name, "")
        print(f"  {name:12s} → 类别={info['category']:8s}, luxury={info['is_luxury']}")
        assert info["category"] == expect_cat, \
            f"{name}: 类别错误 期望{expect_cat}, 实际{info['category']}"
        assert info["is_luxury"] == expect_luxury, \
            f"{name}: luxury错误 期望{expect_luxury}, 实际{info['is_luxury']}"
    print("✅ 测试19通过")


def test_scenario_20_interop_roundtrip():
    """G1: case-interop-v1 交换包 写出→读回 数据保真"""
    print("\n" + "=" * 60)
    print("测试20: 交换包读写往返（G1）")
    print("=" * 60)

    pkg = InteropPackage(
        case_name="测试案件",
        entities=[{"id": "E1", "name": "张三", "phones": ["13800001111"],
                   "accounts": ["6222"], "role": "目标人"}],
        call_events=[{"time": "2024-01-01T10:00:00", "self": "13800001111",
                      "other": "13900002222", "duration_sec": 60, "type": "呼出"}],
        transaction_events=[{"time": "2024-01-01T12:00:00", "amount": 50000,
                             "counterparty_phone": "13900002222"}],
    )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = f.name
    try:
        save_interop_package(pkg, tmp)
        # 校验文件确实写了 schema 标识
        with open(tmp, encoding="utf-8") as fh:
            raw = json.load(fh)
        assert raw["schema"] == SCHEMA_ID, f"schema 标识错误: {raw.get('schema')}"
        assert raw["exported_by"] == "银行流水分析系统"

        loaded = load_interop_package(tmp)
        print(f"案件名: {loaded.case_name}")
        print(f"实体数: {len(loaded.entities)}  通话数: {len(loaded.call_events)}")
        print(f"交易数: {len(loaded.transaction_events)}")
        assert loaded.case_name == "测试案件"
        assert len(loaded.entities) == 1
        assert len(loaded.call_events) == 1
        assert loaded.call_events[0]["other"] == "13900002222"
    finally:
        os.unlink(tmp)
    print("✅ 测试20通过")


def test_scenario_21_interop_schema_validation():
    """G1: schema 不匹配必须明确报错，不能静默"""
    print("\n" + "=" * 60)
    print("测试21: 交换包 schema 校验（G1）")
    print("=" * 60)

    bad_cases = [
        ('{"schema": "wrong-version", "entities": []}', "错误 schema"),
        ('{"entities": []}', "缺失 schema"),
        ('{not valid json', "非法 JSON"),
    ]
    for content, desc in bad_cases:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w",
                                         encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            raised = False
            try:
                load_interop_package(tmp)
            except InteropError as e:
                raised = True
                print(f"  {desc}: 正确抛出 InteropError — {str(e)[:50]}")
            assert raised, f"{desc} 应抛 InteropError 但没有"
        finally:
            os.unlink(tmp)
    print("✅ 测试21通过")


def test_scenario_22_reports_to_transaction_events():
    """G1: CardReport → transaction_events 字段映射正确"""
    print("\n" + "=" * 60)
    print("测试22: 交易事件导出（G1）")
    print("=" * 60)

    txs = [
        Transaction(date=datetime(2024, 1, 1, 10, 0), card="6222000011112222",
                    name="张三", raw_type="转账", amount=-50000,
                    counterparty="李四", counterparty_phone="13900002222",
                    counterparty_account="6228111122223333", channel="手机银行"),
        Transaction(date=datetime(2024, 1, 2, 14, 0), card="6222000011112222",
                    name="张三", raw_type="工资", amount=8000,
                    counterparty="某某公司", counterparty_phone=""),
    ]
    r = analyze_bank_flow(txs).reports[0]
    events = reports_to_transaction_events([r])
    print(f"导出交易数: {len(events)}")
    out = events[0]
    print(f"  转出: time={out['time']} amount={out['amount']} "
          f"from={out['from_account']} to={out['to_account']} "
          f"phone={out['counterparty_phone']}")
    assert len(events) == 2
    assert out["amount"] == -50000, f"金额带符号: {out['amount']}"
    assert out["from_account"] == "6222000011112222", "转出 from 应为本卡"
    assert out["to_account"] == "6228111122223333", "转出 to 应为对手账号"
    assert out["counterparty_phone"] == "13900002222", "手机号桥梁键应保留"
    assert out["channel"] == "手机银行"
    # 流入方向
    inc = events[1]
    assert inc["amount"] == 8000
    assert inc["to_account"] == "6222000011112222", "流入 to 应为本卡"
    print("✅ 测试22通过")


def test_scenario_23_transfer_call_correlation():
    """G2: 大额转账前的密集通话交叉分析（受贿"先沟通后送钱"模式）"""
    print("\n" + "=" * 60)
    print("测试23: 转账-通话时序交叉分析（G2）")
    print("=" * 60)

    # 大额转账：2024-01-05 15:00 给 13900002222 转 50万
    transaction_events = [
        {"time": "2024-01-05T15:00:00", "amount": -500000,
         "counterparty": "李四", "counterparty_phone": "13900002222"},
        # 小额转账（低于阈值，不应触发）
        {"time": "2024-01-06T10:00:00", "amount": -3000,
         "counterparty": "王五", "counterparty_phone": "13911112222"},
    ]
    call_events = [
        # 转账前 1 天内的 3 通电话 → 应被关联
        {"time": "2024-01-05T09:00:00", "self": "13800001111",
         "other": "13900002222", "duration_sec": 300, "type": "呼出"},
        {"time": "2024-01-05T11:00:00", "self": "13800001111",
         "other": "13900002222", "duration_sec": 120, "type": "呼入"},
        {"time": "2024-01-04T20:00:00", "self": "13800001111",
         "other": "13900002222", "duration_sec": 600, "type": "呼出"},
        # 转账后的电话 → 不在窗口内
        {"time": "2024-01-05T18:00:00", "self": "13800001111",
         "other": "13900002222", "duration_sec": 60, "type": "呼出"},
        # 与本案无关号码
        {"time": "2024-01-05T10:00:00", "self": "13800001111",
         "other": "13988889999", "duration_sec": 60, "type": "呼出"},
    ]
    results = analyze_transfer_call_correlation(
        transaction_events, call_events,
        window_hours=24, large_threshold=50000)

    print(f"关联到 {len(results)} 笔大额转账有先行通话")
    assert len(results) == 1, f"应只有 1 笔大额转账命中: {len(results)}"
    hit = results[0]
    print(f"  转账 {hit['transaction']['amount']} → 前 24h 内 "
          f"{hit['call_count']} 通电话, 累计 {hit['total_duration_sec']} 秒")
    assert hit["call_count"] == 3, f"应关联 3 通转账前的电话: {hit['call_count']}"
    assert hit["total_duration_sec"] == 1020, \
        f"累计时长应 300+120+600=1020: {hit['total_duration_sec']}"
    print("✅ 测试23通过")


def test_scenario_24_interop_preserves_call_events():
    """G1: 银行侧导出时必须保留话单工具填的 call_events（只补自己那部分）"""
    print("\n" + "=" * 60)
    print("测试24: 导出保留对方数组（G1）")
    print("=" * 60)

    # 模拟从话单工具导入的包
    base = InteropPackage(
        case_name="某受贿案",
        entities=[{"id": "E1", "name": "张三", "accounts": ["6222"]}],
        call_events=[{"time": "2024-01-01T10:00:00", "self": "138",
                      "other": "139", "duration_sec": 60}],
        sms_events=[{"time": "2024-01-01T10:05:00", "self": "138",
                     "other": "139", "direction": "发送"}],
    )
    txs = [make_tx("2024-01-01", "6222", "转账", -50000, cp="李四")]
    r = analyze_bank_flow(txs).reports[0]

    pkg = build_export_package([r], case_name="某受贿案", base_package=base)
    print(f"call_events 保留: {len(pkg.call_events)} 条")
    print(f"sms_events 保留: {len(pkg.sms_events)} 条")
    print(f"transaction_events 补充: {len(pkg.transaction_events)} 条")
    print(f"analysis_summary 键: {list(pkg.analysis_summary.keys())}")

    assert len(pkg.call_events) == 1, "必须保留话单工具的 call_events"
    assert len(pkg.sms_events) == 1, "必须保留话单工具的 sms_events"
    assert len(pkg.transaction_events) == 1, "应补充银行交易"
    assert "银行流水分析" in pkg.analysis_summary, "应写入银行侧摘要"
    print("✅ 测试24通过")


if __name__ == "__main__":
    test_scenario_1()
    test_scenario_2()
    test_scenario_3()
    test_scenario_4()
    test_scenario_5_pure_cash_loop()
    test_scenario_6_cash_to_finance()
    test_scenario_7_same_counterparty_loop()
    test_scenario_8_deposit_then_transfer()
    test_scenario_9_counterparty_basic()
    test_scenario_10_brand_is_business()
    test_scenario_11_threshold_avoidance()
    test_scenario_12_normal_user_low_suspicion()
    test_scenario_13_high_suspicion_full()
    test_scenario_14_blacklist_scoring()
    test_scenario_15_nominee_dead_card()
    test_scenario_16_real_nominee_pattern()
    test_scenario_17_aml_threshold_decoupled()
    test_scenario_18_tenure_uses_throughput()
    test_scenario_19_hotel_classification()
    test_scenario_20_interop_roundtrip()
    test_scenario_21_interop_schema_validation()
    test_scenario_22_reports_to_transaction_events()
    test_scenario_23_transfer_call_correlation()
    test_scenario_24_interop_preserves_call_events()
    print("\n" + "=" * 60)
    print("🎉 所有测试完成")
