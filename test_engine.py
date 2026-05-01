#!/usr/bin/env python3
"""测试核心引擎算法"""

import sys
from datetime import datetime
from engine import (
    Transaction, TransactionClassifier,
    CashChainMatcher, FinanceMatcher,
    CardAnalyzer, analyze_bank_flow
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

    assert r.suspicion_score >= 60, f"高可疑应≥60: {r.suspicion_score}"
    assert "高" in r.suspicion_label
    print("✅ 测试13通过")


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
    print("\n" + "=" * 60)
    print("🎉 所有测试完成")
