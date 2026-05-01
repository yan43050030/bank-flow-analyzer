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

    def load(self, report: CardReport):
        """加载单卡报告"""
        self._steps.setText("\n".join(report.steps))
        self._build_detail_table(report)
        self._build_cp_table(report)

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
