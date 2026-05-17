#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单卡详情页 — 统计明细 + 对手分析（子 Tab）"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from engine import CardReport


class CardTab(QWidget):
    """单卡 Tab：统计过程 + 明细表 + 对手分析（子 Tab）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 统计过程日志
        steps_label = QLabel("📋 统计过程:")
        steps_label.setObjectName("sectionTitle")
        layout.addWidget(steps_label)

        self._steps = QTextEdit()
        self._steps.setReadOnly(True)
        self._steps.setMaximumHeight(150)
        self._steps.setFont(QFont("Monaco", 10))
        layout.addWidget(self._steps)

        # 子 Tab: 统计明细 / 对手分析
        self._sub_tabs = QTabWidget()
        layout.addWidget(self._sub_tabs, stretch=1)

        # ── 子 Tab 1: 统计明细 ──
        detail_page = QWidget()
        dv = QVBoxLayout(detail_page)
        dv.setContentsMargins(0, 0, 0, 0)
        self._detail_table = QTableWidget()
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._detail_table.setColumnCount(7)
        self._detail_table.setHorizontalHeaderLabels([
            "分类", "日期", "关联日期/类型", "存入/买入", "取出/赎回", "统计金额", "备注"])
        self._detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        dv.addWidget(self._detail_table)
        self._sub_tabs.addTab(detail_page, "📊 统计明细")

        # ── 子 Tab 2: 对手分析 ──
        cp_page = QWidget()
        cv = QVBoxLayout(cp_page)
        cv.setContentsMargins(0, 0, 0, 0)

        self._cp_info = QLabel()
        self._cp_info.setStyleSheet("font-size:12px; padding:4px;")
        cv.addWidget(self._cp_info)

        self._cp_table = QTableWidget()
        self._cp_table.setAlternatingRowColors(True)
        self._cp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._cp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._cp_table.setColumnCount(8)
        self._cp_table.setHorizontalHeaderLabels([
            "排名", "对手名称", "对方账号", "流入", "流出", "净额", "笔数", "标签"])
        self._cp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._cp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        cv.addWidget(self._cp_table)
        self._sub_tabs.addTab(cp_page, "🔍 对手分析")

        # ── 子 Tab 3: 消费画像 ──
        consume_page = QWidget()
        cv2 = QVBoxLayout(consume_page)
        cv2.setContentsMargins(0, 0, 0, 0)
        self._consume_info = QLabel()
        self._consume_info.setStyleSheet("font-size:12px; padding:4px;")
        cv2.addWidget(self._consume_info)
        self._consume_table = QTableWidget()
        self._consume_table.setAlternatingRowColors(True)
        self._consume_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._consume_table.setColumnCount(3)
        self._consume_table.setHorizontalHeaderLabels(["消费类别", "笔数", "金额"])
        self._consume_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cv2.addWidget(self._consume_table)
        self._sub_tabs.addTab(consume_page, "🛍 消费画像")

        # ── 子 Tab 4: 任职对比 ──
        tenure_page = QWidget()
        tv = QVBoxLayout(tenure_page)
        tv.setContentsMargins(0, 0, 0, 0)
        self._tenure_info = QLabel("未设置任职期")
        self._tenure_info.setStyleSheet("font-size:12px; padding:4px;")
        tv.addWidget(self._tenure_info)
        self._tenure_table = QTableWidget()
        self._tenure_table.setAlternatingRowColors(True)
        self._tenure_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tenure_table.setColumnCount(8)
        self._tenure_table.setHorizontalHeaderLabels(
            ["阶段", "笔数", "资金量", "月均", "消费", "大额(≥5万)", "深夜%", "对手数"])
        self._tenure_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tv.addWidget(self._tenure_table)
        self._sub_tabs.addTab(tenure_page, "📅 任职对比")

        # ── 子 Tab 5: 代持分析 ──
        nominee_page = QWidget()
        nv = QVBoxLayout(nominee_page)
        nv.setContentsMargins(0, 0, 0, 0)
        self._nominee_info = QLabel()
        self._nominee_info.setStyleSheet("font-size:12px; padding:4px;")
        nv.addWidget(self._nominee_info)
        self._nominee_table = QTableWidget()
        self._nominee_table.setAlternatingRowColors(True)
        self._nominee_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._nominee_table.setColumnCount(3)
        self._nominee_table.setHorizontalHeaderLabels(["代持信号", "得分", "说明"])
        self._nominee_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        nv.addWidget(self._nominee_table)
        self._sub_tabs.addTab(nominee_page, "🔍 代持分析")

        # ── 子 Tab 6: 异常时序 (D3/D4) ──
        anomaly_page = QWidget()
        av = QVBoxLayout(anomaly_page)
        av.setContentsMargins(0, 0, 0, 0)
        self._anomaly_info = QLabel()
        self._anomaly_info.setStyleSheet("font-size:12px; padding:4px;")
        self._anomaly_info.setWordWrap(True)
        av.addWidget(self._anomaly_info)
        self._anomaly_table = QTableWidget()
        self._anomaly_table.setAlternatingRowColors(True)
        self._anomaly_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._anomaly_table.setColumnCount(4)
        self._anomaly_table.setHorizontalHeaderLabels(
            ["类型", "描述", "关注度", "涉及笔数"])
        self._anomaly_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        av.addWidget(self._anomaly_table)
        self._sub_tabs.addTab(anomaly_page, "⚠ 异常时序")

    def load(self, report: CardReport):
        """加载单卡报告"""
        self._steps.setText("\n".join(report.steps))
        self._build_detail_table(report)
        self._build_cp_table(report)
        self._build_consume_table(report)
        self._build_tenure_table(report)
        self._build_nominee_table(report)
        self._build_anomaly_table(report)

    # ── 统计明细 ──────────────────────────────────────

    def _build_detail_table(self, r: CardReport):
        rows = []

        for p in r.cash_pairs:
            rows.append(["现金存取配对",
                p.deposit_tx.date.strftime("%Y-%m-%d"),
                p.withdraw_tx.date.strftime("%Y-%m-%d"),
                f"{abs(p.deposit_tx.amount):,.0f}",
                f"{abs(p.withdraw_tx.amount):,.0f}",
                f"{p.matched_amount:,.0f}", "配对成功"])
        for d in r.unmatched_deposits:
            rows.append(["现金-未配对存款", d.date.strftime("%Y-%m-%d"), "",
                f"{abs(d.amount):,.0f}", "", f"{abs(d.amount):,.0f}", "净存入"])
        for w in r.unmatched_withdraws:
            rows.append(["现金-未配对取款", w.date.strftime("%Y-%m-%d"), "",
                "", f"{abs(w.amount):,.0f}", f"{abs(w.amount):,.0f}", "净取出"])
        for fp in r.finance_pairs:
            sd = fp.sell_tx.date.strftime("%Y-%m-%d") if fp.sell_tx else "未赎回"
            rows.append(["理财买卖配对",
                fp.buy_tx.date.strftime("%Y-%m-%d"), sd,
                f"{fp.principal:,.0f}",
                f"{abs(fp.sell_tx.amount):,.0f}" if fp.sell_tx else "",
                f"{fp.profit:,.0f}",
                "利息" if fp.profit > 0 else "无收益"])
        for tx in r.all_transactions:
            if tx.category == "consume":
                rows.append(["消费支出", tx.date.strftime("%Y-%m-%d"), tx.raw_type,
                    "", f"{abs(tx.amount):,.0f}", f"{abs(tx.amount):,.0f}",
                    tx.counterparty])
        for tx in r.all_transactions:
            if tx.category in ("transfer_in", "transfer_out"):
                d = "转入" if tx.category == "transfer_in" else "转出"
                rows.append([f"转账-{d}", tx.date.strftime("%Y-%m-%d"), tx.raw_type,
                    f"{tx.amount:,.0f}" if tx.amount > 0 else "",
                    f"{-tx.amount:,.0f}" if tx.amount < 0 else "",
                    f"{abs(tx.amount):,.0f}", tx.counterparty])

        self._detail_table.setRowCount(min(len(rows), 5000))
        for ri, row in enumerate(rows[:5000]):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._detail_table.setItem(ri, ci, item)

    # ── 对手分析 ──────────────────────────────────────

    def _build_cp_table(self, r: CardReport):
        entries = r.cp_top_amount
        if not entries:
            self._cp_info.setText("暂无对手数据")
            self._cp_table.setRowCount(0)
            return

        bi = r.cp_bi_count
        hhi = r.cp_hhi
        hhi_level = "高度集中" if hhi > 2500 else ("中度集中" if hhi > 1000 else "分散")
        self._cp_info.setText(
            f"对手总数: {r.cp_total_players} | 对公: {r.cp_business_count} | "
            f"个人: {r.cp_personal_count} | 双向对手(⇄): {bi}个 | "
            f"HHI集中度: {hhi:.0f} ({hhi_level})"
        )

        self._cp_table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            name, acct, in_a, out_a, cnt, is_biz, is_bi = e
            net = in_a - out_a
            tag_parts = []
            if is_biz: tag_parts.append("对公")
            else: tag_parts.append("个人")
            if is_bi: tag_parts.append("⇄双向")

            vals = [
                str(i + 1), name,
                str(acct)[:24] if acct else "",
                f"{in_a:,.0f}", f"{out_a:,.0f}",
                f"{net:+,.0f}", str(cnt), " ".join(tag_parts),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 双向对手标黄
                if is_bi:
                    from PySide6.QtGui import QColor
                    item.setBackground(QColor("#FFF3CD"))
                self._cp_table.setItem(i, j, item)

        self._cp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._cp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    # ── 消费画像 (A4) ──────────────────────────────────

    def _build_consume_table(self, r: CardReport):
        cats = r.consume_by_category
        if not cats:
            self._consume_info.setText("无消费数据")
            self._consume_table.setRowCount(0)
            return

        luxury_note = ""
        if r.consume_luxury_count > 0:
            brands = ", ".join(f"{b}({a:,.0f})" for b, a in r.consume_luxury_brands[:8])
            luxury_note = (f"⚠ 高端消费: {r.consume_luxury_count}笔 "
                           f"合计{r.consume_luxury_total:,.0f}元 | 品牌: {brands}")

        self._consume_info.setText(
            f"消费总笔数: {sum(v['count'] for v in cats.values())} | "
            f"分类数: {len(cats)} | {luxury_note}"
        )

        sorted_cats = sorted(cats.items(), key=lambda x: x[1]["total"], reverse=True)
        self._consume_table.setRowCount(len(sorted_cats))
        for i, (cat, v) in enumerate(sorted_cats):
            for j, val in enumerate([cat, str(v["count"]), f"{v['total']:,.0f}"]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if cat == "高端购物":
                    from PySide6.QtGui import QColor
                    item.setBackground(QColor("#FFE0E0"))
                self._consume_table.setItem(i, j, item)

    # ── 任职对比 (A3) ──────────────────────────────────

    def _build_tenure_table(self, r: CardReport):
        if not r.has_tenure:
            self._tenure_info.setText("未设置任职期（可在左侧面板设置后重新统计）")
            self._tenure_table.setRowCount(0)
            return

        self._tenure_info.setText("任职期已设置 — 对比三段: 任职前 / 任职中 / 任职后")
        rows = [("任职前", r.tenure_before), ("任职中", r.tenure_during), ("任职后", r.tenure_after)]
        self._tenure_table.setRowCount(3)
        for i, (label, data) in enumerate(rows):
            vals = [
                label, str(data.get("笔数", 0)),
                f"{data.get('资金量', 0):,.0f}", f"{data.get('月均', 0):,.0f}",
                f"{data.get('消费', 0):,.0f}", str(data.get("大额(≥5万)", 0)),
                f"{data.get('深夜%', 0)}%", str(data.get("对手数", 0)),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if label == "任职中":
                    from PySide6.QtGui import QColor
                    item.setBackground(QColor("#FFF3CD"))
                self._tenure_table.setItem(i, j, item)

    # ── 代持分析 (C1) ──────────────────────────────────

    def _build_nominee_table(self, r: CardReport):
        signals = r.nominee_signals
        if not signals:
            self._nominee_info.setText("代持分析数据不可用")
            self._nominee_table.setRowCount(0)
            return

        cls = ("高度疑似代持卡" if "高" in r.nominee_label
               else "疑似代持卡" if "疑似" in r.nominee_label
               else "正常使用")
        ben = f" | 疑似受益人: {r.nominee_beneficiary}" if r.nominee_beneficiary else ""
        self._nominee_info.setText(
            f"代持评分: {r.nominee_score:.0f}/100 — {r.nominee_label} ({cls}){ben}"
        )

        descriptions = {
            "S5-过账模式": "非消费流出占比越高，越像纯过账卡（只收工资→取现/转出，无个人消费）",
            "S6-单一受益人": "转出资金越集中于一个对手，越像为特定人代持",
            "收入模式": "收入中工资类占比越高，越像代发工资后取现的过账模式",
            "消费缺位": "缺少微信/支付宝/美团等日常消费对手，无个人生活痕迹",
        }
        sigs = sorted(signals.items())
        self._nominee_table.setRowCount(len(sigs))
        for i, (k, v) in enumerate(sigs):
            desc = descriptions.get(k, "")
            for j, val in enumerate([k, f"{v:.0f}/0", desc]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._nominee_table.setItem(i, j, item)

    # ── 异常时序 (D3/D4) ──────────────────────────────

    def _build_anomaly_table(self, r: CardReport):
        anomalies = r.timeseries_anomalies
        key_hits = r.key_date_hits
        type_label = {
            "split_laundering": "🔴 拆分洗钱",
            "batch_round": "🟡 批量整数",
            "holiday_burst": "🟡 节假日突击",
        }

        if not anomalies and not key_hits:
            self._anomaly_info.setText(
                "未检出异常时序模式。\n"
                "D3 自动检测：拆分洗钱 / 批量整数 / 节假日突击；"
                "D4 关键时间点需在左侧面板填写。")
            self._anomaly_table.setRowCount(0)
            return

        parts = []
        if anomalies:
            parts.append(f"D3 检出 {len(anomalies)} 类异常时序模式")
        if key_hits:
            parts.append(f"D4 关键时间点 {len(key_hits)} 个")
        self._anomaly_info.setText(" | ".join(parts))

        rows = []
        for a in anomalies:
            rows.append((
                type_label.get(a["type"], a["type"]),
                a["desc"], f"+{a['score']:.0f}", str(len(a.get("txns", []))),
                a["type"] == "split_laundering"))
        for label, h in key_hits.items():
            rows.append((
                f"📅 关键点·{label}",
                f"{h['date']} ±{h['window_days']}天: 前{h['before_count']}笔"
                f"/后{h['after_count']}笔，大额{h['large_count']}笔",
                "—", str(h["txn_count"]), False))

        self._anomaly_table.setRowCount(len(rows))
        for i, (typ, desc, score, cnt, is_red) in enumerate(rows):
            for j, val in enumerate([typ, desc, score, cnt]):
                item = QTableWidgetItem(val)
                if j == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft
                                          | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_red:
                    from PySide6.QtGui import QColor
                    item.setBackground(QColor("#FFE0E0"))
                self._anomaly_table.setItem(i, j, item)
