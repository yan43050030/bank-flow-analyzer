#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
银行流水资金统计 — 核心分析引擎
纯算法模块，无UI依赖，可独立测试
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════

@dataclass
class Transaction:
    """单笔交易"""
    date: datetime
    card: str
    name: str
    raw_type: str            # 原始交易类型文本
    amount: float            # 正=收入/流入，负=支出/流出
    counterparty: str = ""
    remark: str = ""
    row_index: int = 0       # 原始行号

    # 分类后会赋值
    category: str = ""       # cash_in, cash_out, finance_buy, finance_sell, consume, transfer_in, transfer_out, other


@dataclass
class CashPair:
    """存取配对结果"""
    withdraw_tx: Transaction
    deposit_tx: Transaction
    matched_amount: float    # min(取款额, 存款额)
    is_partial: bool = False # 部分匹配


@dataclass
class FinancePair:
    """理财买卖配对结果"""
    buy_tx: Transaction      # 买入交易
    sell_tx: Optional[Transaction]  # 赎回交易（未赎回时为 None）
    principal: float         # 本金
    profit: float            # 利息/收益（赎回-买入，非负）


@dataclass
class CardReport:
    """单张卡的统计报告"""
    card: str
    name: str

    # 原始统计
    total_records: int = 0

    # 历史最高资金（序列累计峰值）
    peak_funds: float = 0.0

    # 卡内余额（净存入 - 净转出 - 消费 + 已赎回理财净流入 - 未赎回理财支出）
    balance: float = 0.0

    # 理财产品
    finance_unredeemed: float = 0.0   # 未赎回理财（买入后未配对）
    finance_principal: float = 0.0    # 理财本金（已配对买入本金，不重复）
    finance_profit: float = 0.0       # 理财获利（赎回-买入的利息）

    # 消费
    consume_total: float = 0.0

    # 转账
    transfer_out: float = 0.0
    transfer_in: float = 0.0

    # 存取
    cash_paired: float = 0.0          # 配对成功的存取金额
    cash_deposit_net: float = 0.0     # 净存入（未配对存款 - 未配对取款）

    # 明细过程
    cash_pairs: List[CashPair] = field(default_factory=list)
    finance_pairs: List[FinancePair] = field(default_factory=list)
    unmatched_deposits: List[Transaction] = field(default_factory=list)
    unmatched_withdraws: List[Transaction] = field(default_factory=list)

    # 原始分类交易
    all_transactions: List[Transaction] = field(default_factory=list)

    # 步骤日志
    steps: List[str] = field(default_factory=list)

    def log(self, msg: str):
        self.steps.append(msg)

    @property
    def net_transfer(self) -> float:
        """净转出"""
        return self.transfer_out - self.transfer_in


@dataclass
class AnalysisResult:
    """完整分析结果"""
    reports: List[CardReport] = field(default_factory=list)
    summary_steps: List[str] = field(default_factory=list)

    @property
    def total_peak(self) -> float:
        return sum(r.peak_funds for r in self.reports)

    @property
    def total_balance(self) -> float:
        return sum(r.balance for r in self.reports)


# ═══════════════════════════════════════════════════════════
# 交易分类器
# ═══════════════════════════════════════════════════════════

class TransactionClassifier:
    """根据交易类型/对手方/备注，自动分类交易"""

    # 现金存取关键词
    CASH_OUT_KEYWORDS = ["取款", "取现", "ATM取", "提款", "ATM取款"]
    CASH_IN_KEYWORDS = ["存款", "存现", "现金存入", "ATM存款", "ATM存"]

    # 理财关键词
    FINANCE_KEYWORDS = ["理财", "基金", "保险", "定期", "大额存单", "结构性存款",
                        "国债", "债券", "信托", "资管", "资产管理"]

    # 消费关键词
    CONSUME_KEYWORDS = ["消费", "支付", "购物", "刷卡", "POS", "银联消费",
                        "快捷支付", "网上支付", "扫码支付", "预授权"]

    # 消费对手方关键词
    CONSUME_CP_KEYWORDS = ["支付宝", "微信", "京东", "淘宝", "美团", "饿了么",
                           "拼多多", "抖音", "滴滴", "携程", "去哪儿", "超市",
                           "商场", "百货", "餐饮", "酒店", "加油", "医院",
                           "药房", "物业", "水电", "燃气"]

    # 转账关键词
    TRANSFER_KEYWORDS = ["转账", "汇款", "汇入", "汇出", "网银转账", "手机银行转账",
                         "跨行转账", "行内转账", "代发", "代扣", "汇兑"]

    # 收入关键词（工资等）
    INCOME_KEYWORDS = ["工资", "薪金", "奖金", "劳务", "报销", "退款", "退税",
                       "利息", "分红", "股息", "租金", "补贴"]

    @classmethod
    def classify(cls, tx: Transaction) -> str:
        """返回分类: cash_in, cash_out, finance_buy, finance_sell, consume, transfer_in, transfer_out, other"""
        raw = tx.raw_type.strip()
        cp = tx.counterparty.strip()
        remark = tx.remark.strip()
        combined = f"{raw} {cp} {remark}".lower()
        amount = tx.amount

        # 1. 现金存取
        if any(kw in raw for kw in cls.CASH_OUT_KEYWORDS):
            return "cash_out"
        if any(kw in raw for kw in cls.CASH_IN_KEYWORDS):
            return "cash_in"

        # 2. 理财
        is_finance = any(kw in raw for kw in cls.FINANCE_KEYWORDS)
        if is_finance:
            # 正金额=赎回/卖出, 负金额=买入
            return "finance_sell" if amount > 0 else "finance_buy"

        # 3. 消费
        if any(kw in raw for kw in cls.CONSUME_KEYWORDS):
            return "consume"
        if any(kw in combined for kw in cls.CONSUME_CP_KEYWORDS):
            return "consume"

        # 4. 转账
        is_transfer = any(kw in raw for kw in cls.TRANSFER_KEYWORDS)
        if is_transfer:
            return "transfer_out" if amount < 0 else "transfer_in"

        # 5. 收入
        if any(kw in raw for kw in cls.INCOME_KEYWORDS):
            return "transfer_in"

        # 6. 按金额方向兜底判断
        if amount < 0:
            return "transfer_out"
        else:
            return "transfer_in"


# ═══════════════════════════════════════════════════════════
# 现金存取链配对
# ═══════════════════════════════════════════════════════════

class CashChainMatcher:
    """
    存取链配对算法（贪婪匹配）

    原则：
    1. 所有存取按时间排序
    2. 取款往后找最近的存款配对（取出的钱来自之前的存款）
    3. 存款配不完的视为净存入
    4. 历史最高资金 = 序列累计峰值
    """

    def __init__(self, max_days: int = 30, max_ratio: float = 0.3):
        self.max_days = max_days
        self.max_ratio = max_ratio

    def match(self, cash_txs: List[Transaction]) -> Tuple[
        List[CashPair], List[Transaction], List[Transaction], float]:
        """
        返回: (配对列表, 未配对取款, 未配对存款, 存取经过金额)
        """
        # 分离取款和存款
        withdraws = sorted([t for t in cash_txs if t.category == "cash_out"],
                          key=lambda t: t.date)
        deposits = sorted([t for t in cash_txs if t.category == "cash_in"],
                         key=lambda t: t.date)

        pairs = []
        wd_used = [False] * len(withdraws)
        dp_remaining = [abs(d.amount) for d in deposits]  # 存款可用余额
        dp_used = [False] * len(deposits)

        # 对每笔取款，找到最近的可配对存款
        for i, wd in enumerate(withdraws):
            if wd_used[i]:
                continue

            wd_amt = abs(wd.amount)
            best_j = -1
            best_score = float("inf")

            for j, dp in enumerate(deposits):
                if dp_used[j] or dp_remaining[j] <= 0:
                    continue

                # 时间检查：取款应该在存款之后（或同一天）
                days = (wd.date - dp.date).days
                if days < -self.max_days or days > self.max_days:
                    continue

                # 金额占比检查
                avl = dp_remaining[j]
                ratio = abs(wd_amt - avl) / max(wd_amt, avl) if max(wd_amt, avl) > 0 else 0
                if ratio > self.max_ratio and wd_amt > avl:
                    continue

                # 时间优先，越近越好
                score = abs(days) + ratio * 50
                if score < best_score:
                    best_score = score
                    best_j = j

            if best_j >= 0:
                matched = min(wd_amt, dp_remaining[best_j])
                pairs.append(CashPair(
                    withdraw_tx=wd,
                    deposit_tx=deposits[best_j],
                    matched_amount=matched,
                    is_partial=wd_amt > dp_remaining[best_j]
                ))
                dp_remaining[best_j] -= matched
                wd_used[i] = True
                if dp_remaining[best_j] <= 0.01:
                    dp_used[best_j] = True

        # 未配对的
        unmatched_wd = [wd for i, wd in enumerate(withdraws) if not wd_used[i]]
        unmatched_dp = [dp for j, dp in enumerate(deposits) if not dp_used[j]]

        # 存取经过金额 = 配对成功的金额
        cash_flow_amount = sum(p.matched_amount for p in pairs)

        return pairs, unmatched_wd, unmatched_dp, cash_flow_amount


# ═══════════════════════════════════════════════════════════
# 理财买卖配对
# ═══════════════════════════════════════════════════════════

class FinanceMatcher:
    """
    理财买卖配对算法

    原则：
    1. 买入（资金流出）和赎回（资金流入）
    2. 按时间顺序，每笔赎回匹配最近的未匹配买入
    3. 利息 = 赎回金额 - 买入金额
    4. 未匹配买入 = 未赎回理财
    5. 本金 = 已配对买入金额（不重复计算）
    """

    def __init__(self, max_days: int = 365 * 3, amount_tolerance: float = 0.5):
        self.max_days = max_days
        self.amount_tolerance = amount_tolerance  # 赎回额相对买入额的最大倍数

    def match(self, finance_txs: List[Transaction]) -> Tuple[
        List[FinancePair], float, float]:
        """
        返回: (配对列表, 总本金, 总获利)
        """
        buys = sorted([t for t in finance_txs if t.category == "finance_buy"],
                     key=lambda t: t.date)
        sells = sorted([t for t in finance_txs if t.category == "finance_sell"],
                      key=lambda t: t.date)

        pairs = []
        buy_used = [False] * len(buys)
        total_principal = 0.0
        total_profit = 0.0

        # 每笔赎回找最近未匹配买入
        for sell in sells:
            sell_amt = abs(sell.amount)
            best_i = -1
            best_score = float("inf")

            for i, buy in enumerate(buys):
                if buy_used[i]:
                    continue

                buy_amt = abs(buy.amount)

                # 赎回应在买入之后
                days = (sell.date - buy.date).days
                if days < 0 or days > self.max_days:
                    continue

                # 赎回金额合理范围（本金+利息，通常在0.5~2倍本金）
                ratio = sell_amt / buy_amt if buy_amt > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    continue

                # 赎回金额应 >= 买入金额（含利息）或略低于（亏损赎回）
                # 优先匹配金额接近的
                score = abs(sell_amt - buy_amt) / max(sell_amt, buy_amt)
                if score < best_score:
                    best_score = score
                    best_i = i

            if best_i >= 0:
                buy = buys[best_i]
                buy_amt = abs(buy.amount)
                profit = max(0, sell_amt - buy_amt)

                pairs.append(FinancePair(
                    buy_tx=buy,
                    sell_tx=sell,
                    principal=buy_amt,
                    profit=profit
                ))
                total_profit += profit
                buy_used[best_i] = True
            else:
                pass

        # 未配对买入 = 未赎回理财
        unredeemed = sum(abs(buys[i].amount) for i in range(len(buys)) if not buy_used[i])

        # 本金去重：同一笔钱循环买理财，只算一次
        total_principal = self._deduplicate_principal(pairs)

        return pairs, total_principal, total_profit, unredeemed

    def _deduplicate_principal(self, pairs: List[FinancePair]) -> float:
        """去重本金：循环买入的同一笔钱只算一次"""
        if not pairs:
            return 0.0
        sorted_pairs = sorted(pairs, key=lambda p: p.buy_tx.date)
        used = []
        for fp in sorted_pairs:
            amt = fp.principal
            sell_date = fp.sell_tx.date if fp.sell_tx else None
            is_recycled = False
            for prev_amt, prev_sell_date in used:
                ratio = abs(amt - prev_amt) / max(amt, prev_amt) if max(amt, prev_amt) > 0 else 0
                if ratio <= 0.10:
                    if sell_date and prev_sell_date:
                        days = (fp.buy_tx.date - prev_sell_date).days
                        if 0 <= days <= 60:
                            is_recycled = True
                            break
            if not is_recycled:
                used.append((amt, sell_date))
        return sum(p[0] for p in used)


# ═══════════════════════════════════════════════════════════
# 卡片分析器
# ═══════════════════════════════════════════════════════════

class CardAnalyzer:
    """单张卡完整分析"""

    def __init__(self, cash_max_days: int = 30, finance_max_days: int = 365 * 3):
        self.cash_matcher = CashChainMatcher(max_days=cash_max_days)
        self.finance_matcher = FinanceMatcher(max_days=finance_max_days)

    def analyze(self, card: str, name: str, transactions: List[Transaction]) -> CardReport:
        report = CardReport(card=card, name=name)
        report.total_records = len(transactions)
        report.all_transactions = transactions

        # === Step 0: 分类所有交易 ===
        report.log(f"共 {len(transactions)} 笔交易，开始分类...")
        for tx in transactions:
            tx.category = TransactionClassifier.classify(tx)

        categories = defaultdict(int)
        for tx in transactions:
            categories[tx.category] += 1
        report.log(f"分类结果: {dict(categories)}")

        # === Step 1: 现金存取链配对 ===
        cash_txs = [t for t in transactions if t.category in ("cash_in", "cash_out")]
        if cash_txs:
            report.log(f"\n--- 现金存取配对 ({len(cash_txs)}笔) ---")
            pairs, unmatched_wd, unmatched_dp, cash_flow = self.cash_matcher.match(cash_txs)
            report.cash_pairs = pairs
            report.unmatched_deposits = unmatched_dp
            report.unmatched_withdraws = unmatched_wd
            report.cash_paired = cash_flow

            dp_net = sum(abs(d.amount) for d in unmatched_dp)
            wd_net = sum(abs(w.amount) for w in unmatched_wd)
            report.cash_deposit_net = dp_net - wd_net

            report.log(f"  配对成功: {len(pairs)} 对，金额: {cash_flow:,.2f}")
            report.log(f"  未配对存款: {len(unmatched_dp)} 笔 ({dp_net:,.2f})")
            report.log(f"  未配对取款: {len(unmatched_wd)} 笔 ({wd_net:,.2f})")
            for p in pairs:
                report.log(f"    {p.withdraw_tx.date.strftime('%m-%d')} 取{abs(p.withdraw_tx.amount):,.0f} ↔ "
                          f"{p.deposit_tx.date.strftime('%m-%d')} 存{abs(p.deposit_tx.amount):,.0f} → {p.matched_amount:,.0f}")

        # === Step 2: 理财买卖配对 ===
        finance_txs = [t for t in transactions if t.category in ("finance_buy", "finance_sell")]
        if finance_txs:
            report.log(f"\n--- 理财买卖配对 ({len(finance_txs)}笔) ---")
            fpairs, principal, profit, unredeemed = self.finance_matcher.match(finance_txs)
            report.finance_pairs = fpairs
            report.finance_principal = principal
            report.finance_profit = profit
            report.finance_unredeemed = unredeemed

            report.log(f"  配对成功: {len(fpairs)} 对")
            report.log(f"  理财本金: {principal:,.2f}")
            report.log(f"  理财获利: {profit:,.2f}")
            report.log(f"  未赎回理财: {unredeemed:,.2f}")
            for fp in fpairs:
                sell_date = fp.sell_tx.date.strftime('%m-%d') if fp.sell_tx else "未赎回"
                report.log(f"    {fp.buy_tx.date.strftime('%m-%d')} 买{abs(fp.buy_tx.amount):,.0f} → "
                          f"{sell_date} 赎{abs(fp.sell_tx.amount):,.0f} 利息{fp.profit:,.0f}")

        # === Step 3: 消费汇总 ===
        consume_txs = [t for t in transactions if t.category == "consume"]
        report.consume_total = sum(abs(t.amount) for t in consume_txs)
        report.log(f"\n--- 消费支出 ---")
        report.log(f"  共 {len(consume_txs)} 笔，合计: {report.consume_total:,.2f}")

        # === Step 4: 转账统计 ===
        t_out = [t for t in transactions if t.category == "transfer_out"]
        t_in = [t for t in transactions if t.category == "transfer_in"]
        report.transfer_out = sum(abs(t.amount) for t in t_out)
        report.transfer_in = sum(abs(t.amount) for t in t_in)
        report.log(f"\n--- 转账 ---")
        report.log(f"  转出: {len(t_out)} 笔 ({report.transfer_out:,.2f})")
        report.log(f"  转入: {len(t_in)} 笔 ({report.transfer_in:,.2f})")

        # === Step 5: 计算余额 & 历史峰值 ===
        # 余额 = 净存入(未配对) + 净转入 + 已赎回理财净额 - 消费 - 未赎回理财支出
        #       = cash_deposit_net + transfer_in - transfer_out + (理财赎回总额 - 理财买入已配对总额) - consume - finance_unredeemed

        finance_sell_total = sum(abs(t.amount) for t in transactions if t.category == "finance_sell")
        finance_buy_total = sum(abs(t.amount) for t in transactions if t.category == "finance_buy")

        # 余额估算
        report.balance = (report.cash_deposit_net
                         + report.transfer_in
                         - report.transfer_out
                         + finance_sell_total
                         - finance_buy_total
                         - report.consume_total)

        # 历史最高资金：按时间序列累计
        report.peak_funds = self._calc_peak(transactions)

        report.log(f"\n=== 计算结果 ===")
        report.log(f"  历史最高资金: {report.peak_funds:,.2f}")
        report.log(f"  卡内余额: {report.balance:,.2f}")
        report.log(f"  理财未赎回: {report.finance_unredeemed:,.2f}")
        report.log(f"  消费支出: {report.consume_total:,.2f}")
        report.log(f"  净转出: {report.net_transfer:,.2f}")
        report.log(f"  存取经过: {report.cash_paired:,.2f}")
        report.log(f"  理财获利: {report.finance_profit:,.2f}")

        return report

    def _calc_peak(self, transactions: List[Transaction]) -> float:
        """计算历史最高资金（序列累计峰值）"""
        if not transactions:
            return 0.0

        sorted_txs = sorted(transactions, key=lambda t: t.date)
        cumulative = 0.0
        peak = 0.0

        for tx in sorted_txs:
            if tx.category in ("cash_in", "transfer_in", "finance_sell"):
                cumulative += abs(tx.amount)
            elif tx.category in ("cash_out", "transfer_out", "finance_buy", "consume"):
                cumulative -= abs(tx.amount)
            peak = max(peak, cumulative)

        return peak


# ═══════════════════════════════════════════════════════════
# 批量分析入口
# ═══════════════════════════════════════════════════════════

def analyze_bank_flow(transactions: List[Transaction],
                      card_col: str = "card",
                      cash_max_days: int = 30,
                      finance_max_days: int = 365 * 3) -> AnalysisResult:
    """批量分析所有卡"""
    result = AnalysisResult()

    # 按卡号分组
    card_groups = defaultdict(list)
    for tx in transactions:
        card_groups[tx.card].append(tx)

    for card, txs in card_groups.items():
        name = txs[0].name if txs else ""
        analyzer = CardAnalyzer(cash_max_days=cash_max_days, finance_max_days=finance_max_days)
        report = analyzer.analyze(card, name, txs)
        result.reports.append(report)
        result.summary_steps.extend(report.steps)

    return result
