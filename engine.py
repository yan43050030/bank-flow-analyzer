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

    # ── 对手分析 ──
    cp_top_amount: list = field(default_factory=list)   # [(name, account, in, out, count, is_biz, is_bi), ...]
    cp_top_count: list = field(default_factory=list)
    cp_top_net: list = field(default_factory=list)
    cp_business_count: int = 0
    cp_personal_count: int = 0
    cp_bi_count: int = 0           # 双向对手数
    cp_hhi: float = 0.0            # 赫芬达尔集中度（全部对手）
    cp_hhi_excl_salary: float = 0.0  # 剔除工资类对手后的 HHI（用于可疑度评分）
    cp_salary_source_count: int = 0  # 工资类对手数量
    cp_total_players: int = 0      # 对手总数

    # ── 可疑度打分 (A5) ──
    suspicion_score: float = 0.0        # 0-100
    suspicion_label: str = ""           # 低/中/高
    suspicion_detail: Dict[str, float] = field(default_factory=dict)

    # ── 任职期对比 (A3) ──
    tenure_before: dict = field(default_factory=dict)
    tenure_during: dict = field(default_factory=dict)
    tenure_after: dict = field(default_factory=dict)
    has_tenure: bool = False

    # ── 代持卡识别 (C1) ──
    nominee_score: float = 0.0       # 代持嫌疑分 0-100
    nominee_label: str = ""          # 低/中/高
    nominee_signals: dict = field(default_factory=dict)  # 各信号详情
    nominee_beneficiary: str = ""    # 疑似受益人

    # ── 消费画像 (A4) ──
    consume_luxury_count: int = 0          # 高端消费笔数
    consume_luxury_total: float = 0.0      # 高端消费总额
    consume_by_category: dict = field(default_factory=dict)  # 分类汇总
    consume_luxury_brands: list = field(default_factory=list)  # 命中品牌列表

    # ── 资金量分析（最小值法）──
    total_income: float = 0.0          # 入账合计
    total_expense: float = 0.0         # 出账合计
    fund_size: float = 0.0             # 最小资金量
    income_detail: Dict[str, float] = field(default_factory=dict)
    expense_detail: Dict[str, float] = field(default_factory=dict)
    fund_detail: Dict[str, float] = field(default_factory=dict)
    balance_verified: bool = False
    balance_diff: float = 0.0
    transfer_recycled: float = 0.0     # 同账户转入转出中被抵销(取小)的部分

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
        return sum(r.peak_funds for r in self.unique_reports)

    @property
    def total_balance(self) -> float:
        return sum(r.balance for r in self.unique_reports)

    @property
    def unique_reports(self) -> list:
        """去重：多张卡对应同一流水时只保留一份"""
        seen = set()
        uniq = []
        for r in self.reports:
            # 指纹 = 笔数 + 入账合计 + 出账合计 + 资金量 + 首尾日期
            if not r.all_transactions:
                continue
            dates = sorted(t.date for t in r.all_transactions)
            fp = (r.total_records, round(r.total_income, 2), round(r.total_expense, 2),
                  round(r.fund_size, 2),
                  dates[0].strftime("%Y%m%d"), dates[-1].strftime("%Y%m%d"))
            if fp not in seen:
                seen.add(fp)
                uniq.append(r)
        return uniq


# ═══════════════════════════════════════════════════════════
# 交易分类器
# ═══════════════════════════════════════════════════════════

class TransactionClassifier:
    """根据交易类型/对手方/备注，自动分类交易"""

    # 现金存取关键词
    CASH_OUT_KEYWORDS = ["取款", "取现", "ATM取", "提款", "ATM取款", "支取"]
    CASH_IN_KEYWORDS = ["存款", "存现", "现金存入", "ATM存款", "ATM存"]

    # 理财关键词
    FINANCE_KEYWORDS = ["理财", "基金", "保险", "定期", "大额存单", "结构性存款",
                        "国债", "债券", "信托", "资管", "资产管理"]

    # 消费关键词
    CONSUME_KEYWORDS = ["消费", "支付", "购物", "刷卡", "POS", "银联消费",
                        "快捷支付", "网上支付", "扫码支付", "预授权",
                        "短信费", "扣款", "手续费", "服务费", "年费",
                        "充值", "管理费", "收费", "通讯费"]

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
                       "利息", "分红", "股息", "租金", "补贴",
                       "利息存入", "入账", "退货", "提现"]

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

        # 3. 收入/退款（必须在消费之前，避免 "消费退货" 被 "消费" 捕获）
        if any(kw in raw for kw in cls.INCOME_KEYWORDS):
            return "transfer_in"

        # 4. 消费
        if any(kw in raw for kw in cls.CONSUME_KEYWORDS):
            return "consume"
        if any(kw in combined for kw in cls.CONSUME_CP_KEYWORDS):
            return "consume"

        # 5. 转账
        is_transfer = any(kw in raw for kw in cls.TRANSFER_KEYWORDS)
        if is_transfer:
            return "transfer_out" if amount < 0 else "transfer_in"

        # 6. 按金额方向兜底判断
        if amount < 0:
            return "transfer_out"
        else:
            return "transfer_in"


# ═══════════════════════════════════════════════════════════
# 对手分析
# ═══════════════════════════════════════════════════════════

class CounterpartyAnalyzer:
    """从交易列表中提取对手统计：Top N / 对公对私 / 双向检测 / 集中度"""

    # 对公关键词（核心组织名特征）
    _BIZ_KEYWORDS = [
        "公司", "有限", "股份", "厂", "局", "委", "院", "校",
        "中心", "支行", "分理处", "储蓄所", "营业部", "联社",
        "银行", "保险", "政府", "办事", "管理", "办公室",
        "财务", "支付", "科技", "信息", "服务", "国际旅行",
        "信用", "合作", "运行", "核算", "专用户", "过渡户",
        "零余额", "工资", "代发", "代付", "代扣", "批量",
        "商务", "酒店", "餐饮", "百货", "商贸", "贸易",
        "实业", "集团", "投资", "建设", "工程", "地产",
    ]

    _BIZ_EXCLUDE = [
        "张三", "李四", "王五",  # 防误判（常见个人名）
    ]

    # 工资类关键词（用于剔除合法集中收入源后再算 HHI）
    _SALARY_KEYWORDS = [
        "工资", "薪", "代发", "代付", "奖金", "津贴", "补贴", "报销",
    ]

    @classmethod
    def analyze(cls, transactions: list) -> dict:
        """
        返回:
        {
            'entries': [(name, account, in_amt, out_amt, count, is_biz, is_bi), ...] 按金额降序
            'total_players': int,
            'business_count': int,
            'personal_count': int,
            'bidirectional_count': int,
            'hhi': float,                 # 原始集中度（含工资类）
            'hhi_excl_salary': float,     # 剔除工资类对手后的集中度（更适合可疑度评分）
            'salary_source_count': int,   # 工资类对手数量
        }
        """
        if not transactions:
            return {
                "entries": [], "total_players": 0,
                "business_count": 0, "personal_count": 0,
                "bidirectional_count": 0,
                "hhi": 0.0, "hhi_excl_salary": 0.0,
                "salary_source_count": 0,
            }

        cp_map = defaultdict(
            lambda: {"in": 0.0, "out": 0.0, "count": 0, "account": "",
                     "salary_hits": 0, "non_salary_hits": 0})
        for t in transactions:
            name = (t.counterparty or "").strip()
            if not name:
                name = "__无对手名称__"
            cp_map[name]["count"] += 1
            cp_map[name]["account"] = cp_map[name]["account"] or str(
                getattr(t, "counterparty_account", "")) if hasattr(t, "counterparty_account") else ""
            # 记录该笔交易是否带"工资类"特征（基于原始交易类型）
            raw = (t.raw_type or "")
            if any(kw in raw for kw in cls._SALARY_KEYWORDS):
                cp_map[name]["salary_hits"] += 1
            else:
                cp_map[name]["non_salary_hits"] += 1
            if t.amount > 0:
                cp_map[name]["in"] += t.amount
            else:
                cp_map[name]["out"] += abs(t.amount)

        entries = []
        salary_sources = set()
        for name, v in cp_map.items():
            is_biz = cls._is_business(name)
            is_bi = v["in"] > 0.01 and v["out"] > 0.01
            # 工资类对手：所有交易都是工资 + 仅入账（合法集中来源）
            if (v["salary_hits"] > 0
                    and v["non_salary_hits"] == 0
                    and v["out"] < 0.01):
                salary_sources.add(name)
            entries.append((
                name, v["account"],
                round(v["in"], 2), round(v["out"], 2),
                v["count"], is_biz, is_bi,
            ))

        entries.sort(key=lambda e: e[2] + e[3], reverse=True)

        # 总 HHI
        total_flow = sum(e[2] + e[3] for e in entries)
        hhi = sum((e[2] + e[3]) ** 2 for e in entries) / (total_flow ** 2) * 10000 \
            if total_flow > 0 else 0

        # 剔除工资类后的 HHI（用于可疑度评分，避免正常工资人群顶格）
        non_salary_entries = [e for e in entries if e[0] not in salary_sources]
        ns_total = sum(e[2] + e[3] for e in non_salary_entries)
        hhi_excl_salary = (
            sum((e[2] + e[3]) ** 2 for e in non_salary_entries) / (ns_total ** 2) * 10000
        ) if ns_total > 0 else 0

        biz_count = sum(1 for e in entries if e[5])
        bi_count = sum(1 for e in entries if e[6])

        return {
            "entries": entries,
            "total_players": len(entries),
            "business_count": biz_count,
            "personal_count": len(entries) - biz_count,
            "bidirectional_count": bi_count,
            "hhi": round(hhi, 1),
            "hhi_excl_salary": round(hhi_excl_salary, 1),
            "salary_source_count": len(salary_sources),
        }

    @classmethod
    def _is_business(cls, name: str) -> bool:
        for ex in cls._BIZ_EXCLUDE:
            if ex in name:
                return False
        for kw in cls._BIZ_KEYWORDS:
            if kw in name:
                return True
        # P3 修复：复用消费平台/商户关键词，避免美团/支付宝等被误判为"个人"
        for kw in TransactionClassifier.CONSUME_CP_KEYWORDS:
            if kw in name:
                return True
        return False


# ═══════════════════════════════════════════════════════════
# 现金存取链配对
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# 消费画像 (A4)
# ═══════════════════════════════════════════════════════════

class ConsumptionClassifier:
    """消费多级分类 + 高端品牌识别"""

    # 高端品牌关键词库
    LUXURY_BRANDS = [
        "爱马仕", "Hermes", "卡地亚", "Cartier", "LV", "Louis Vuitton",
        "Tiffany", "蒂芙尼", "迪奥", "Dior", "阿玛尼", "Armani",
        "古驰", "Gucci", "普拉达", "Prada", "宝格丽", "Bvlgari",
        "劳力士", "Rolex", "百达翡丽", "Patek", "江诗丹顿",
        "万国", "IWC", "欧米茄", "Omega", "浪琴", "Longines",
        "博柏利", "Burberry", "芬迪", "Fendi", "圣罗兰", "YSL",
        "范思哲", "Versace", "巴黎世家", "Balenciaga", "纪梵希", "Givenchy",
        "香奈儿", "Chanel", "赛琳", "Celine", "罗意威", "Loewe",
        "葆蝶家", "Bottega", "华伦天奴", "Valentino", "盟可睐", "Moncler",
        "加拿大鹅", "Canada Goose", "始祖鸟", "Arc'teryx",
        "宝珀", "Blancpain", "积家", "Jaeger", "理查德米勒", "Richard Mille",
        "奔驰", "Mercedes", "宝马", "BMW", "保时捷", "Porsche", "奥迪", "Audi",
        "特斯拉", "Tesla", "雷克萨斯", "Lexus", "宾利", "Bentley",
        "茅台", "五粮液", "拉菲", "Lafite", "马爹利", "轩尼诗", "Hennessy",
        "希尔顿", "Hilton", "万豪", "Marriott", "洲际", "丽思卡尔顿", "Ritz",
        "四季", "Four Seasons", "文华东方", "Mandarin Oriental", "安缦", "Aman",
        "头等舱", "商务舱", "公务舱",
        "高尔夫", "马术", "游艇", "赛马", "私人会所",
        "SKP", "连卡佛", "恒隆", "太古汇", "IFC",
    ]

    # 消费类别关键词
    CATEGORY_KEYWORDS = {
        "高端购物": LUXURY_BRANDS,
        "日用百货": ["超市", "百货", "商场", "便利店", "永辉", "物美", "华联", "大润发",
                    "沃尔玛", "Walmart", "Costco", "山姆", "Sam's", "屈臣氏", "711"],
        "餐饮": ["餐饮", "饭店", "餐厅", "火锅", "烧烤", "料理", "自助", "小吃", "快餐",
                 "面馆", "饺子", "咖啡", "奶茶", "茶饮", "肯德基", "KFC", "麦当劳",
                 "McDonald", "海底捞", "星巴克", "Starbucks", "必胜客", "Pizza Hut",
                 "砂锅", "串串", "烤鸭", "牛排", "日料", "韩料", "粤菜", "湘菜"],
        "酒店住宿": ["酒店", "宾馆", "旅馆", "民宿", "住宿", "客栈", "青旅",
                    # 高端酒店品牌（与 LUXURY_BRANDS 重叠，但需在此声明便于类别归类）
                    "希尔顿", "Hilton", "万豪", "Marriott", "洲际", "丽思卡尔顿", "Ritz",
                    "四季", "Four Seasons", "文华东方", "Mandarin Oriental", "安缦", "Aman"],
        "旅游出行": ["旅游", "旅行", "机票", "火车票", "高铁", "动车", "汽车票",
                    "打车", "滴滴", "出租车", "加油", "中石油", "中石化", "Shell",
                    "高速", "ETC", "停车", "机票", "携程", "去哪儿", "飞猪",
                    "航空", "机场", "旅行社", "景区", "门票"],
        "医疗健康": ["医院", "诊所", "药房", "药店", "医药", "门诊", "手术", "体检",
                    "牙科", "眼科", "中医", "同仁堂", "体检中心"],
        "教育培训": ["教育", "培训", "学校", "学费", "补习", "网课", "考试", "报名",
                    "留学", "雅思", "托福", "GRE", "MBA", "学而思", "新东方"],
        "生活服务": ["物业", "水电", "燃气", "暖气", "宽带", "话费", "充值", "快递",
                    "顺丰", "EMS", "邮政", "维修", "保洁", "洗衣", "理发", "美发"],
        "娱乐休闲": ["KTV", "酒吧", "夜店", "足疗", "按摩", "洗浴", "桑拿", "SPA",
                    "美容", "健身", "游泳", "滑雪", "温泉", "密室", "剧本杀",
                    "电影", "影院", "万达", "CGV", "IMAX", "桌游", "棋牌"],
        "数码家电": ["手机", "电脑", "笔记本", "iPad", "iPhone", "华为", "小米",
                    "苹果", "Samsung", "三星", "电器", "家电", "国美", "苏宁",
                    "数码", "相机", "镜头", "无人机", "DJI"],
    }

    @classmethod
    def classify_consumption(cls, counterparty: str, remark: str) -> dict:
        """对一笔消费交易进行多级分类。返回 {category, is_luxury, matched_brand}

        Bug 7 修复：先按消费类别分（如酒店、餐饮），再独立判断是否高端品牌。
        这样万豪/希尔顿/丽思卡尔顿能既归"酒店住宿"，又被标 is_luxury。
        """
        combined = (f"{counterparty} {remark}").lower()
        result = {"category": "其他消费", "is_luxury": False, "matched_brand": ""}

        # 1) 先按消费类别匹配（保留语义分类）
        for cat, keywords in cls.CATEGORY_KEYWORDS.items():
            if cat == "高端购物":
                continue   # 高端购物在第 2 步单独判
            for kw in keywords:
                if kw.lower() in combined:
                    result["category"] = cat
                    break
            if result["category"] != "其他消费":
                break

        # 2) 独立判断是否高端品牌（与类别正交）
        for brand in cls.LUXURY_BRANDS:
            if brand.lower() in combined:
                result["is_luxury"] = True
                result["matched_brand"] = brand
                # 若类别仍是"其他"，归到"高端购物"；否则保留原类别（如酒店住宿）
                if result["category"] == "其他消费":
                    result["category"] = "高端购物"
                break

        return result

    @classmethod
    def analyze(cls, transactions: list) -> dict:
        """对全部消费交易进行画像统计"""
        cats = defaultdict(lambda: {"count": 0, "total": 0.0})
        luxury_count = 0
        luxury_total = 0.0
        luxury_brands = defaultdict(float)

        for t in transactions:
            if t.category != "consume":
                continue
            cp = t.counterparty or ""
            rmk = t.remark or ""
            info = cls.classify_consumption(cp, rmk)
            cat = info["category"]
            amt = abs(t.amount)

            cats[cat]["count"] += 1
            cats[cat]["total"] += amt

            if info["is_luxury"]:
                luxury_count += 1
                luxury_total += amt
                luxury_brands[info["matched_brand"]] += amt

        return {
            "by_category": {k: dict(v) for k, v in sorted(cats.items())},
            "luxury_count": luxury_count,
            "luxury_total": luxury_total,
            "luxury_brands": sorted(luxury_brands.items(), key=lambda x: x[1], reverse=True),
        }


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

@dataclass
class SuspicionConfig:
    """可疑度评分可调阈值 (B3)"""
    large_threshold: float = 50000.0       # 大额交易阈值（用户可调，仅用于"大额标识"统计）
    night_start: int = 22                  # 深夜起始小时
    night_end: int = 6                     # 深夜结束小时
    hhi_warning: float = 2500.0            # HHI 警告阈值
    blacklist_keywords: list = field(default_factory=list)  # 对手黑名单关键词
    integer_pref_weight: float = 20.0      # 整数偏好权重
    threshold_weight: float = 20.0         # 阈值规避权重
    night_weight: float = 15.0             # 深夜交易权重
    bidirectional_weight: float = 15.0     # 双向对手权重
    hhi_weight: float = 15.0               # 集中度权重
    consume_ratio_weight: float = 15.0     # 消费收入比权重
    blacklist_weight: float = 15.0         # 黑名单命中权重（Bug 1 修复：原本未参与打分）

    # 反洗钱阈值（中国法定，固定不可调；与 large_threshold 解耦修复 Bug 4）
    # 检测"踩线规避"金额时使用：5万为人民银行《金融机构大额交易和可疑交易报告管理办法》阈值
    AML_THRESHOLDS: tuple = (50000.0, 200000.0)


class CardAnalyzer:
    """单张卡完整分析"""

    def __init__(self, cash_max_days: int = 30, finance_max_days: int = 365 * 3):
        self.cash_matcher = CashChainMatcher(max_days=cash_max_days)
        self.finance_matcher = FinanceMatcher(max_days=finance_max_days)

    def analyze(self, card: str, name: str, transactions: List[Transaction],
                tenure_start: Optional[datetime] = None,
                tenure_end: Optional[datetime] = None,
                suspicion_config: Optional[SuspicionConfig] = None) -> CardReport:
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
        # 余额 = 存现净额 + 净转入 + 理财净赎回 - 消费
        # 直接用分类合计计算，避免 cash_deposit_net 部分匹配时的误差

        cash_in_total = sum(abs(t.amount) for t in transactions if t.category == "cash_in")
        cash_out_total = sum(abs(t.amount) for t in transactions if t.category == "cash_out")
        finance_sell_total = sum(abs(t.amount) for t in transactions if t.category == "finance_sell")
        finance_buy_total = sum(abs(t.amount) for t in transactions if t.category == "finance_buy")

        report.balance = (cash_in_total - cash_out_total
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

        # === Step 6: 资金量分析 ===
        self._analyze_funds(report, transactions)

        # === Step 7: 对手分析 ===
        self._analyze_counterparties(report, transactions)

        # === Step 8: 可疑度打分 ===
        self._analyze_suspicion(report, transactions, suspicion_config)

        # === Step 9: 消费画像 ===
        self._analyze_consumption(report, transactions)

        # === Step 10: 任职期对比 ===
        if tenure_start and tenure_end:
            self._analyze_tenure(report, transactions, tenure_start, tenure_end)

        # === Step 11: 代持卡识别 (C1) ===
        self._analyze_nominee(report, transactions)

        return report

    def _analyze_tenure(self, report: CardReport, transactions: list,
                        t_start: datetime, t_end: datetime):
        """A3 任职期对比: 三段统计"""
        report.has_tenure = True

        def slice_stats(txs: list) -> dict:
            """计算单段统计。'资金量' 用 throughput（FIFO 循环池），不是 sum(amount)。"""
            if not txs:
                return {"笔数": 0, "资金量": 0, "月均": 0, "消费": 0,
                        "大额(≥5万)": 0, "深夜%": 0, "对手数": 0}
            total = len(txs)
            # Bug 5 修复：资金量用 throughput 而非 sum(amount)（净流向）
            # 净流向只反映余额变化，会被消费/转出冲销，掩盖任职期真实活跃度
            throughput, _, _ = self._calc_throughput(txs)
            consume = sum(abs(t.amount) for t in txs if t.category == "consume")
            days = (max(t.date for t in txs) - min(t.date for t in txs)).days
            months = max(1, days / 30)
            large = sum(1 for t in txs if abs(t.amount) >= 50000)
            night = sum(1 for t in txs if t.date.hour >= 22 or t.date.hour < 6)
            # 对手数：过滤空对手名（Bug 7 衍生修复）
            cps = len(set(c for c in (
                (t.counterparty or "").strip() for t in txs) if c))
            return {
                "笔数": total, "资金量": round(throughput, 2),
                "月均": round(throughput / months, 2),
                "消费": round(consume, 2), "大额(≥5万)": large,
                "深夜%": round(night / total * 100, 1) if total > 0 else 0,
                "对手数": cps,
            }

        before = [t for t in transactions if t.date < t_start]
        during = [t for t in transactions if t_start <= t.date <= t_end]
        after = [t for t in transactions if t.date > t_end]

        report.tenure_before = slice_stats(before)
        report.tenure_during = slice_stats(during)
        report.tenure_after = slice_stats(after)

        report.log(f"\n--- 任职期对比 ---")
        report.log(f"  任职期: {t_start.strftime('%Y-%m-%d')} ~ {t_end.strftime('%Y-%m-%d')}")
        for label, data in [("任职前", report.tenure_before),
                            ("任职中", report.tenure_during),
                            ("任职后", report.tenure_after)]:
            report.log(f"  {label}: {data['笔数']}笔 资金量{data['资金量']:,.0f} "
                       f"月均{data['月均']:,.0f} 消费{data['消费']:,.0f} "
                       f"大额{data['大额(≥5万)']}笔 深夜{data['深夜%']}%")

    def _analyze_nominee(self, report: CardReport, transactions: list):
        """C1 代持卡识别: S5 无消费模式 + S6 单一受益人"""
        if not transactions:
            return

        # ── 数据量门槛：交易量太少 / 没有任何流出，不足以判断代持 (Bug 2 修复) ──
        # 死户卡（仅工资入账，零流出）原本会被默认 S5=1.0 误判为高度疑似
        outflows = [t for t in transactions if t.amount < 0]
        total_out = sum(abs(t.amount) for t in outflows) if outflows else 0
        # 无流出 或 流出笔数 < 3 时不评分（数据不足以判断行为模式）
        if total_out < 1.0 or len(outflows) < 3:
            report.nominee_score = 0.0
            report.nominee_label = "—（数据不足）"
            report.nominee_signals = {"备注": f"流出笔数仅 {len(outflows)} 笔，不足以判断"}
            report.nominee_beneficiary = ""
            report.log(f"\n--- 代持卡识别 (C1) ---")
            report.log(f"  数据不足: 流出{len(outflows)}笔/{total_out:.0f}元，跳过评分")
            return

        # ── S5: 非消费占比（仅工资+取现+转出，无主动消费）──
        non_consume_out = sum(abs(t.amount) for t in outflows
                              if t.category != "consume")
        non_consume_ratio = non_consume_out / total_out

        # ── S6: 转出受益人集中度 ──
        transfer_outs = [t for t in transactions
                         if t.category == "transfer_out"]
        beneficiary_map = defaultdict(float)
        for t in transfer_outs:
            cp = (t.counterparty or "").strip()
            if cp: beneficiary_map[cp] += abs(t.amount)
        sorted_bens = sorted(beneficiary_map.items(), key=lambda x: x[1], reverse=True)
        top1_share = sorted_bens[0][1] / sum(v for _, v in sorted_bens) if sorted_bens else 0
        top_beneficiary = sorted_bens[0][0] if sorted_bens else ""

        # ── 代持打分 ──
        score = 0.0
        sig = {}
        # S5 (30分): 非消费流出占比 > 90% → 满分
        s5_score = min(30, non_consume_ratio * 30)
        score += s5_score; sig["S5-过账模式"] = round(s5_score, 1)
        # S6 (30分): 单一受益人 > 80% → 满分
        s6_score = min(30, top1_share * 30 / 0.8) if sorted_bens else 0
        score += s6_score; sig["S6-单一受益人"] = round(s6_score, 1)
        # 收入模式 (20分): 仅有"工资类"转入 → 代持特征
        # Bug 6 修复：删除占位符"自定义"
        income_txs = [t for t in transactions if t.amount > 0]
        salary_keywords = ["工资", "薪金", "奖金", "劳务", "代付", "代发", "津贴"]
        salary_income = sum(t.amount for t in income_txs
                           if any(kw in (t.raw_type + t.counterparty)
                                  for kw in salary_keywords))
        total_income_amt = sum(t.amount for t in income_txs) if income_txs else 0
        salary_ratio = salary_income / total_income_amt if total_income_amt > 0 else 0
        inc_score = min(20, salary_ratio * 20)
        score += inc_score; sig["收入模式"] = round(inc_score, 1)
        # 消费缺位 (20分): 没有日常消费对手（微信/支付宝/美团等）
        consume_cps = defaultdict(float)
        for t in transactions:
            if t.category == "consume" and t.counterparty:
                consume_cps[t.counterparty.strip()] += abs(t.amount)
        daily_cp_count = sum(1 for cp in consume_cps
                            if any(kw in cp for kw in ["微信", "支付宝", "财付通", "美团", "饿了么"]))
        no_daily = 20 if daily_cp_count == 0 else max(0, 20 - daily_cp_count * 5)
        score += no_daily; sig["消费缺位"] = round(no_daily, 1)

        score = min(100, round(score, 1))
        report.nominee_score = score
        report.nominee_signals = sig
        report.nominee_beneficiary = top_beneficiary

        if score <= 30:
            report.nominee_label = "🟢 正常"
        elif score <= 60:
            report.nominee_label = "🟡 疑似代持"
        else:
            report.nominee_label = "🔴 高度疑似"

        report.log(f"\n--- 代持卡识别 (C1) ---")
        report.log(f"  S5过账模式: {non_consume_ratio:.0%} 非消费流出 ({s5_score:.0f}/30)")
        report.log(f"  S6单一受益人: {top_beneficiary[:30]}({top1_share:.0%}) ({s6_score:.0f}/30)")
        report.log(f"  收入模式: {salary_ratio:.0%} 工资类 ({inc_score:.0f}/20)")
        report.log(f"  消费缺位: 日常消费对手{daily_cp_count}个 ({no_daily:.0f}/20)")
        report.log(f"  代持评分: {score:.0f}/100 → {report.nominee_label}")

    def _analyze_consumption(self, report: CardReport, transactions: list):
        """A4 消费画像: 高端品牌检测 + 多级分类"""
        cp = ConsumptionClassifier.analyze(transactions)
        report.consume_by_category = cp["by_category"]
        report.consume_luxury_count = cp["luxury_count"]
        report.consume_luxury_total = cp["luxury_total"]
        report.consume_luxury_brands = cp["luxury_brands"]

        if cp["luxury_count"] > 0:
            brands_str = ", ".join(
                f"{b}({a:,.0f})" for b, a in cp["luxury_brands"][:5])
            report.log(f"\n--- 消费画像 ---")
            report.log(f"  高端消费: {cp['luxury_count']}笔 {cp['luxury_total']:,.2f}")
            report.log(f"  命中品牌: {brands_str}")
        for cat, v in cp["by_category"].items():
            if v["total"] > 0:
                report.log(f"  {cat}: {v['count']}笔 {v['total']:,.2f}")

    def _analyze_suspicion(self, report: CardReport, transactions: list,
                           config: Optional[SuspicionConfig] = None):
        """A2-min 现金画像 + A5 可疑度打分 0-100（可调阈值 B3）"""
        if not transactions:
            return

        cfg = config or SuspicionConfig()
        lt = cfg.large_threshold / 10000  # 大额阈值（万），仅用于"大额标识"统计

        # ── A2-min: 现金画像 ──
        # Bug 4 修复：阈值规避检测使用法定反洗钱阈值（5万/20万固定），
        #            与用户可调的 large_threshold 解耦
        int_pref = 0
        near_aml_lo = 0   # 5万阈值附近交易（人民银行反洗钱阈值）
        near_aml_hi = 0   # 20万阈值附近交易
        night_txn = 0
        weekend_txn = 0
        blacklist_hits = 0
        total_txn = len(transactions)

        # AML 阈值（法定，固定值）
        aml_lo, aml_hi = SuspicionConfig.AML_THRESHOLDS  # (50000, 200000)
        # ±10% 区间（包含 50000 自身、49000 等踩线值）
        aml_margin_lo = aml_lo * 0.10
        aml_margin_hi = aml_hi * 0.10

        # 整数偏好：经典踩线特征数字
        # Bug 3 修复：覆盖恰好等于阈值的"贴线"金额（50000/200000 也算偏好）
        # 以及 阈值-100/-1000 的踩线值（49900/49000/199000/199900 等）
        integer_pref_targets = {
            aml_lo, aml_lo - 100, aml_lo - 1000,           # 50000, 49900, 49000
            aml_hi, aml_hi - 100, aml_hi - 1000,           # 200000, 199900, 199000
            aml_lo * 2, aml_lo * 2 - 100, aml_lo * 2 - 1000,  # 100000, 99900, 99000
            aml_lo * 10, aml_lo * 10 - 100, aml_lo * 10 - 1000,  # 500000 等
        }

        for t in transactions:
            amt = abs(t.amount)
            # 阈值规避检测（万元以上的整千/整万金额才参与）
            if amt >= 10000 and (amt % 10000 == 0 or amt % 1000 == 0):
                if aml_lo - aml_margin_lo <= amt <= aml_lo + aml_margin_lo:
                    near_aml_lo += 1
                elif aml_hi - aml_margin_hi <= amt <= aml_hi + aml_margin_hi:
                    near_aml_hi += 1
                # 整数偏好命中
                for target in integer_pref_targets:
                    if abs(amt - target) <= 10:
                        int_pref += 1
                        break
            # 深夜交易
            hour = t.date.hour
            if hour >= cfg.night_start or hour < cfg.night_end:
                night_txn += 1
            # 周末
            if t.date.weekday() >= 5:
                weekend_txn += 1
            # 黑名单（对手名 + 备注 + raw_type 都查）
            haystack = (
                (t.counterparty or "") + " " +
                (t.remark or "") + " " +
                (t.raw_type or "")
            ).lower()
            for kw in cfg.blacklist_keywords:
                if kw and kw.lower() in haystack:
                    blacklist_hits += 1
                    break

        night_ratio = night_txn / total_txn if total_txn > 0 else 0
        weekend_ratio = weekend_txn / total_txn if total_txn > 0 else 0
        zero_hour = sum(1 for t in transactions if t.date.hour == 0)
        has_reliable_time = total_txn > 0 and (zero_hour / total_txn) < 0.5

        # ── A5: 可疑度打分（使用可调权重）──
        score = 0.0
        detail = {}

        ip_score = min(cfg.integer_pref_weight, int_pref * 3)
        score += ip_score; detail["整数偏好"] = round(ip_score, 1)

        th_score = min(cfg.threshold_weight, (near_aml_lo + near_aml_hi * 2) * 4)
        score += th_score; detail["阈值规避"] = round(th_score, 1)

        if has_reliable_time:
            nt_score = min(cfg.night_weight, night_ratio * 100)
        else:
            nt_score = 0
        score += nt_score; detail["深夜交易"] = round(nt_score, 1)

        bi_score = min(cfg.bidirectional_weight, report.cp_bi_count * 3)
        score += bi_score; detail["双向对手"] = round(bi_score, 1)

        non_salary = report.cp_total_players - report.cp_salary_source_count
        hhi_val = report.cp_hhi_excl_salary
        if non_salary >= 5 and hhi_val > 0:
            hhi_score = min(cfg.hhi_weight,
                            max(0, (hhi_val - cfg.hhi_warning) / cfg.hhi_warning * cfg.hhi_weight))
        else:
            hhi_score = 0
        score += hhi_score; detail["对手集中度"] = round(hhi_score, 1)

        income = report.total_income
        consume = report.consume_total
        if income > 0:
            cr = consume / income
            ci_score = min(cfg.consume_ratio_weight,
                           max(0, (cr - 0.5) * cfg.consume_ratio_weight))
        else:
            ci_score = cfg.consume_ratio_weight * 0.67  # 无收入数据 → 中等保守分
        score += ci_score; detail["消费收入比"] = round(ci_score, 1)

        # Bug 1 修复：黑名单命中接入打分（每命中 1 次 +5 分，封顶 blacklist_weight）
        if cfg.blacklist_keywords and blacklist_hits > 0:
            bl_score = min(cfg.blacklist_weight, blacklist_hits * 5)
        else:
            bl_score = 0
        score += bl_score; detail["黑名单命中"] = round(bl_score, 1)

        score = min(100, round(score, 1))
        report.suspicion_score = score
        report.suspicion_detail = detail

        if score <= 30:
            report.suspicion_label = "🟢 低"
        elif score <= 60:
            report.suspicion_label = "🟡 中"
        else:
            report.suspicion_label = "🔴 高"

        report.log(f"\n--- 可疑度打分 (大额标识阈值={lt:.0f}万, AML阈值=5万/20万) ---")
        report.log(f"  整数偏好: {int_pref:.0f}次 深夜: {night_txn}次({night_ratio:.1%})")
        report.log(f"  阈值规避(AML 5万附近): {near_aml_lo:.0f}次, 20万附近: {near_aml_hi:.0f}次")
        report.log(f"  黑名单命中: {blacklist_hits}次 周末: {weekend_txn}次({weekend_ratio:.1%})")
        report.log(f"  评分: {score:.0f}/100 → {report.suspicion_label}")
        for k, v in detail.items():
            report.log(f"    {k}: {v:.0f}分")

    def _analyze_counterparties(self, report: CardReport, transactions: list):
        """对手分析：Top N / 对公对私 / 双向检测 / 集中度"""
        cp = CounterpartyAnalyzer.analyze(transactions)
        entries = cp["entries"]
        report.cp_top_amount = entries[:10]
        report.cp_top_count = sorted(entries, key=lambda e: e[4], reverse=True)[:10]
        report.cp_top_net = sorted(entries, key=lambda e: abs(e[2] - e[3]), reverse=True)[:10]
        report.cp_business_count = cp["business_count"]
        report.cp_personal_count = cp["personal_count"]
        report.cp_bi_count = cp["bidirectional_count"]
        report.cp_hhi = cp["hhi"]
        report.cp_hhi_excl_salary = cp["hhi_excl_salary"]
        report.cp_salary_source_count = cp["salary_source_count"]
        report.cp_total_players = cp["total_players"]

        report.log(f"\n--- 对手分析 ---")
        report.log(f"  对手总数: {cp['total_players']} (对公{cp['business_count']} / 个人{cp['personal_count']})")
        report.log(f"  双向对手: {cp['bidirectional_count']}个")
        report.log(f"  工资类对手: {cp['salary_source_count']}个")
        report.log(f"  集中度HHI: {cp['hhi']:.0f} (剔工资后{cp['hhi_excl_salary']:.0f})")
        for e in entries[:10]:
            tag = ""
            if e[5]: tag += "对公"
            if e[6]: tag += "⇄"
            report.log(f"  {e[0][:30]:30s} 入{e[2]:>12,.0f} 出{e[3]:>12,.0f}  #{e[4]:>4d}  {tag}")

    def _analyze_funds(self, report: CardReport, transactions: List[Transaction]):
        """资金量分析：入/出校验 + 资金通量估算（统一 FIFO 循环池）"""
        # ── 入账 / 出账合计 ──
        cash_in_total = sum(abs(t.amount) for t in transactions if t.category == "cash_in")
        cash_out_total = sum(abs(t.amount) for t in transactions if t.category == "cash_out")
        transfer_in_total = sum(abs(t.amount) for t in transactions if t.category == "transfer_in")
        transfer_out_total = sum(abs(t.amount) for t in transactions if t.category == "transfer_out")
        finance_buy_total = sum(abs(t.amount) for t in transactions if t.category == "finance_buy")
        finance_sell_total = sum(abs(t.amount) for t in transactions if t.category == "finance_sell")
        consume_total = sum(abs(t.amount) for t in transactions if t.category == "consume")

        report.total_income = cash_in_total + transfer_in_total + finance_sell_total
        report.total_expense = cash_out_total + transfer_out_total + finance_buy_total + consume_total

        report.income_detail = {
            "存现(cash_in)": cash_in_total,
            "转入(transfer_in)": transfer_in_total,
            "理财返还(finance_sell)": finance_sell_total,
        }
        report.expense_detail = {
            "取现(cash_out)": cash_out_total,
            "转出(transfer_out)": transfer_out_total,
            "理财上划(finance_buy)": finance_buy_total,
            "消费(consume)": consume_total,
        }

        # ── 余额校验: 入 - 出 应等于 余额 + 未到期理财 ──
        expected_balance = report.total_income - report.total_expense
        actual_balance_plus_finance = report.balance + report.finance_unredeemed
        report.balance_diff = expected_balance - actual_balance_plus_finance
        report.balance_verified = abs(report.balance_diff) < 0.02

        # ── 资金通量（throughput）：累计真实流入卡的资金，去除循环 ──
        # 三类循环统一处理（按时间顺序 FIFO 池）：
        #   1. 现金循环：取款→进口袋池；存款→优先从口袋池消费（视为同笔钱回流）
        #   2. 理财循环：买入→进理财池；赎回→优先从理财池消费（本金回流）
        #   3. 同对手转账循环：转出→进对手池；同对手转入→优先从对手池消费
        # 消费、纯工资/退款、跨对手转账 不会形成循环，直接计入新流入。
        throughput, throughput_inflow, throughput_recycled = self._calc_throughput(transactions)

        report.transfer_recycled = throughput_recycled.get("transfer_recycled", 0.0)
        report.fund_size = max(report.peak_funds, throughput)

        cash_recycled = throughput_recycled.get("cash_recycled", 0.0)
        finance_recycled = throughput_recycled.get("finance_recycled", 0.0)
        transfer_recycled = throughput_recycled.get("transfer_recycled", 0.0)

        report.fund_detail = {
            "存现新增(cash_in_new)": throughput_inflow.get("cash_in_new", 0.0),
            "转入新增(transfer_in_new)": throughput_inflow.get("transfer_in_new", 0.0),
            "理财收益(finance_profit)": throughput_inflow.get("finance_profit", 0.0),
            "消费(consume)": consume_total,
            "现金循环抵销": cash_recycled,
            "理财循环抵销": finance_recycled,
            "同户转账循环抵销": transfer_recycled,
            "=资金通量(throughput)": throughput,
            "历史最高峰值(peak)": report.peak_funds,
            "=最终资金量(max)": report.fund_size,
            # 兼容 main_window.py 的取值
            "=最小资金量(min_fund)": throughput,
        }

        if report.peak_funds > throughput:
            peak_reason = (
                f"历史峰值 {report.peak_funds:,.0f} > 资金通量 {throughput:,.0f}，"
                f"说明卡曾持有大额资金（可能为初始余额或同日多笔流入）"
            )
        elif abs(report.peak_funds - throughput) < 1:
            peak_reason = f"历史峰值与资金通量基本一致 ({report.peak_funds:,.0f})"
        else:
            peak_reason = (
                f"资金通量 {throughput:,.0f} >= 历史峰值 {report.peak_funds:,.0f}，"
                f"资金多次流入流出（去重后真实经过此卡）"
            )

        report.log(f"\n--- 资金量分析 ---")
        report.log(f"  入账合计: {report.total_income:,.2f}")
        report.log(f"  出账合计: {report.total_expense:,.2f}")
        report.log(f"  入-出 = {expected_balance:,.2f}")
        report.log(f"  余额+未到期理财 = {actual_balance_plus_finance:,.2f}")
        report.log(f"  余额校验{'✓' if report.balance_verified else '✗ 差异=' + str(round(report.balance_diff, 2))}")
        report.log(f"  现金循环抵销: {cash_recycled:,.2f} (取款{cash_out_total:,.0f}↔存款{cash_in_total:,.0f})")
        report.log(f"  理财循环抵销: {finance_recycled:,.2f} (买入{finance_buy_total:,.0f}↔赎回{finance_sell_total:,.0f})")
        report.log(f"  同户转账循环抵销: {transfer_recycled:,.2f}")
        report.log(f"  历史峰值(A): {report.peak_funds:,.2f}")
        report.log(f"  资金通量(B): {throughput:,.2f}")
        report.log(f"    = 存现新增{throughput_inflow.get('cash_in_new', 0):,.0f}"
                   f" + 转入新增{throughput_inflow.get('transfer_in_new', 0):,.0f}"
                   f" + 理财收益{throughput_inflow.get('finance_profit', 0):,.0f}")
        report.log(f"  最终资金量 max(A,B): {report.fund_size:,.2f}")
        report.log(f"  结论: {peak_reason}")

    def _calc_throughput(
        self, transactions: List[Transaction]
    ) -> Tuple[float, Dict[str, float], Dict[str, float]]:
        """
        资金通量算法：累计真实流入卡的资金（去除循环）

        按时间顺序遍历交易，维护三个 FIFO 池来识别"同一笔钱反复流通"：
          - pocket_pool   : 已取出未存回的现金（取款进池→存款消费池）
          - finance_pool  : 已买入未赎回的理财（买入进池→赎回消费池）
          - transfer_pool : 同对手已转出未回款的金额（转出进池→同对手转入消费池）

        每笔流入交易先抵销对应池中的额度（视为循环回流），剩余部分才算"新流入"。
        消费、跨对手转账、不同载体之间的资金链 不形成循环。

        返回: (throughput, inflow_detail, recycled_detail)
        """
        if not transactions:
            return 0.0, {}, {}

        sorted_txs = sorted(
            transactions, key=lambda t: (t.date, getattr(t, "row_index", 0))
        )

        pocket_pool = 0.0          # 用户口袋的现金（取款流出后未回流）
        finance_pool = 0.0         # 已买未赎的理财本金
        transfer_pool: Dict[str, float] = defaultdict(float)  # 同对手未回款转出

        throughput = 0.0
        inflow = defaultdict(float)
        recycled = defaultdict(float)

        for tx in sorted_txs:
            amt = abs(tx.amount)
            cat = tx.category

            if cat == "cash_in":
                from_pool = min(amt, pocket_pool)
                pocket_pool -= from_pool
                new_money = amt - from_pool
                throughput += new_money
                inflow["cash_in_new"] += new_money
                recycled["cash_recycled"] += from_pool

            elif cat == "cash_out":
                pocket_pool += amt

            elif cat == "transfer_in":
                cp = (tx.counterparty or "").strip() or "__无对手__"
                from_pool = min(amt, transfer_pool[cp])
                transfer_pool[cp] -= from_pool
                new_money = amt - from_pool
                throughput += new_money
                inflow["transfer_in_new"] += new_money
                recycled["transfer_recycled"] += from_pool

            elif cat == "transfer_out":
                cp = (tx.counterparty or "").strip() or "__无对手__"
                transfer_pool[cp] += amt

            elif cat == "finance_sell":
                from_pool = min(amt, finance_pool)
                finance_pool -= from_pool
                new_money = amt - from_pool   # 超出本金的部分 = 收益
                throughput += new_money
                inflow["finance_profit"] += new_money
                recycled["finance_recycled"] += from_pool

            elif cat == "finance_buy":
                finance_pool += amt

            # consume: 钱花出去不会回，无需进池

        return throughput, dict(inflow), dict(recycled)

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
                      finance_max_days: int = 365 * 3,
                      tenure_start: Optional[datetime] = None,
                      tenure_end: Optional[datetime] = None,
                      suspicion_config: Optional[SuspicionConfig] = None) -> AnalysisResult:
    """批量分析所有卡"""
    result = AnalysisResult()

    card_groups = defaultdict(list)
    for tx in transactions:
        card_groups[tx.card].append(tx)

    for card, txs in card_groups.items():
        name = txs[0].name if txs else ""
        analyzer = CardAnalyzer(cash_max_days=cash_max_days, finance_max_days=finance_max_days)
        report = analyzer.analyze(card, name, txs,
                                  tenure_start=tenure_start,
                                  tenure_end=tenure_end,
                                  suspicion_config=suspicion_config)
        result.reports.append(report)
        result.summary_steps.extend(report.steps)

    return result


# ═══════════════════════════════════════════════════════════
# 证据包导出 (C2)
# ═══════════════════════════════════════════════════════════

def generate_report(report: CardReport, title: str = "银行流水分析报告") -> str:
    """生成单卡 HTML 证据报告"""
    r = report
    lines = []
    w = lines.append

    w("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    w(f"<title>{title} — {r.card[-16:]}</title>")
    w("<style>")
    w("body{font-family:'Microsoft YaHei',sans-serif;max-width:960px;margin:0 auto;padding:20px;color:#333}")
    w("h1{color:#1a73e8;border-bottom:2px solid #1a73e8;padding-bottom:8px}")
    w("h2{color:#333;margin-top:24px;border-left:4px solid #1a73e8;padding-left:12px}")
    w(".card{background:#f8f9fa;border-radius:8px;padding:12px 16px;margin:8px 0}")
    w(".warn{background:#fff3cd;border-left:4px solid #ffc107}")
    w(".danger{background:#ffe0e0;border-left:4px solid #dc3545}")
    w("table{width:100%;border-collapse:collapse;margin:12px 0}")
    w("th{background:#1a73e8;color:#fff;padding:8px 10px;text-align:left}")
    w("td{padding:8px 10px;border-bottom:1px solid #e0e0e0}")
    w("tr:nth-child(even){background:#f8f9fa}")
    w(".score{font-size:24px;font-weight:bold}")
    w(".red{color:#dc3545}.yellow{color:#ffc107}.green{color:#28a745}")
    w(".tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;margin:2px}")
    w(".tag-biz{background:#e3f2fd;color:#1565c0}.tag-bi{background:#fff3cd;color:#e65100}")
    w("</style></head><body>")

    w(f"<h1>{title}</h1>")
    w(f"<p>卡号: {r.card} | 姓名: {r.name} | 交易笔数: {r.total_records}</p>")

    w("<h2>📊 资金概览</h2><div class='card'>")
    w(f"<p><b>资金量:</b> <span class='score'>{r.fund_size:,.0f} 元</span></p>")
    w(f"<p>峰值: {r.peak_funds:,.0f} | 余额: {r.balance:,.0f} | "
      f"入: {r.total_income:,.0f} | 出: {r.total_expense:,.0f}</p>")
    w(f"<p>消费: {r.consume_total:,.0f} | 转出: {r.transfer_out:,.0f}</p>")
    w("</div>")

    cls = "red" if "高" in r.suspicion_label else ("yellow" if "中" in r.suspicion_label else "green")
    w(f"<h2>⚠ 可疑度</h2><div class='card warn'>")
    w(f"<p><span class='score {cls}'>{r.suspicion_score:.0f}/100 — {r.suspicion_label}</span></p>")
    w("<table><tr><th>指标</th><th>得分</th></tr>")
    for k, v in r.suspicion_detail.items():
        w(f"<tr><td>{k}</td><td>{v:.0f}</td></tr>")
    w("</table></div>")

    if r.nominee_score > 0:
        cls2 = "red" if "高" in r.nominee_label else ("yellow" if "疑似" in r.nominee_label else "green")
        w(f"<h2>🔍 代持分析</h2><div class='card danger'>")
        w(f"<p><span class='score {cls2}'>{r.nominee_score:.0f}/100 — {r.nominee_label}</span></p>")
        if r.nominee_beneficiary:
            w(f"<p>疑似受益人: <b>{r.nominee_beneficiary}</b></p>")
        w("<table><tr><th>信号</th><th>得分</th></tr>")
        for k, v in r.nominee_signals.items():
            w(f"<tr><td>{k}</td><td>{v:.0f}</td></tr>")
        w("</table></div>")

    w("<h2>👥 主要对手 Top 10</h2>")
    w("<table><tr><th>#</th><th>对手</th><th>流入</th><th>流出</th><th>净额</th><th>笔数</th><th>标签</th></tr>")
    for i, e in enumerate(r.cp_top_amount[:10]):
        name, _, ins, outs, cnt, is_biz, is_bi = e
        tags = " ".join([f"<span class='tag tag-biz'>对公</span>" if is_biz else "",
                         f"<span class='tag tag-bi'>⇄双向</span>" if is_bi else ""])
        w(f"<tr><td>{i+1}</td><td>{name[:40]}</td><td>{ins:,.0f}</td>"
          f"<td>{outs:,.0f}</td><td>{ins-outs:+,.0f}</td><td>{cnt}</td><td>{tags}</td></tr>")
    w("</table>")

    if r.consume_by_category:
        w("<h2>🛍 消费画像</h2><table><tr><th>类别</th><th>笔数</th><th>金额</th></tr>")
        for cat, v in sorted(r.consume_by_category.items(), key=lambda x: x[1]["total"], reverse=True):
            w(f"<tr><td>{cat}</td><td>{v['count']}</td><td>{v['total']:,.0f}</td></tr>")
        w("</table>")
    if r.consume_luxury_count > 0:
        brands = ", ".join(f"{b}({a:,.0f})" for b, a in r.consume_luxury_brands[:10])
        w(f"<div class='card danger'><b>⚠ 高端消费:</b> {r.consume_luxury_count}笔 "
          f"合计{r.consume_luxury_total:,.0f}元 | {brands}</div>")

    if r.has_tenure:
        w("<h2>📅 任职期对比</h2><table><tr><th>阶段</th><th>笔数</th><th>资金量</th>"
          "<th>月均</th><th>消费</th><th>大额</th></tr>")
        for label, data in [("任职前", r.tenure_before), ("任职中", r.tenure_during), ("任职后", r.tenure_after)]:
            w(f"<tr><td>{label}</td><td>{data.get('笔数',0)}</td>"
              f"<td>{data.get('资金量',0):,.0f}</td><td>{data.get('月均',0):,.0f}</td>"
              f"<td>{data.get('消费',0):,.0f}</td><td>{data.get('大额(≥5万)',0)}</td></tr>")
        w("</table>")

    w("<h2>📝 方法说明</h2><div class='card'><ul>")
    w("<li>资金量 = max(历史峰值, FIFO 循环池通量)</li>")
    w("<li>可疑度 = 6 维加权：整数偏好+阈值规避+深夜+双向对手+HHI+消费比</li>")
    w("<li>代持识别 = S5过账模式+S6单一受益人+收入模式+消费缺位</li>")
    w("<li>对手分析 = 对公/个人自动分类 + 双向检测 + HHI 集中度</li>")
    w("</ul></div></body></html>")
    return "\n".join(lines)
