#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单卡详情页 — 统计过程 + 明细表格"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from engine import CardReport


class CardTab(QWidget):
    """单卡 Tab：统计过程日志 + 明细表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 统计过程
        steps_label = QLabel("📋 统计过程:")
        steps_label.setObjectName("sectionTitle")
        layout.addWidget(steps_label)

        self._steps = QTextEdit()
        self._steps.setReadOnly(True)
        self._steps.setMaximumHeight(180)
        self._steps.setFont(QFont("Monaco", 10))
        layout.addWidget(self._steps)

        # 明细表格
        detail_label = QLabel("📊 统计明细:")
        detail_label.setObjectName("sectionTitle")
        layout.addWidget(detail_label)

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "分类", "日期", "关联日期/类型", "存入/买入", "取出/赎回", "统计金额", "备注"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

    def load(self, report: CardReport):
        """加载单卡报告数据"""
        self._steps.setText("\n".join(report.steps))
        self._build_table(report)

    def _build_table(self, r: CardReport):
        rows = []

        # 存取配对
        for p in r.cash_pairs:
            rows.append(["现金存取配对",
                p.deposit_tx.date.strftime("%Y-%m-%d"),
                p.withdraw_tx.date.strftime("%Y-%m-%d"),
                f"{abs(p.deposit_tx.amount):,.0f}",
                f"{abs(p.withdraw_tx.amount):,.0f}",
                f"{p.matched_amount:,.0f}", "配对成功"])

        # 未配对存取
        for d in r.unmatched_deposits:
            rows.append(["现金-未配对存款", d.date.strftime("%Y-%m-%d"), "",
                f"{abs(d.amount):,.0f}", "", f"{abs(d.amount):,.0f}", "净存入"])
        for w in r.unmatched_withdraws:
            rows.append(["现金-未配对取款", w.date.strftime("%Y-%m-%d"), "",
                "", f"{abs(w.amount):,.0f}", f"{abs(w.amount):,.0f}", "净取出"])

        # 理财配对
        for fp in r.finance_pairs:
            sell_date = fp.sell_tx.date.strftime("%Y-%m-%d") if fp.sell_tx else "未赎回"
            rows.append(["理财买卖配对",
                fp.buy_tx.date.strftime("%Y-%m-%d"), sell_date,
                f"{fp.principal:,.0f}",
                f"{abs(fp.sell_tx.amount):,.0f}" if fp.sell_tx else "",
                f"{fp.profit:,.0f}",
                "利息" if fp.profit > 0 else "无收益"])

        # 消费
        for tx in r.all_transactions:
            if tx.category == "consume":
                rows.append(["消费支出", tx.date.strftime("%Y-%m-%d"), tx.raw_type,
                    "", f"{abs(tx.amount):,.0f}", f"{abs(tx.amount):,.0f}",
                    tx.counterparty])

        # 转账
        for tx in r.all_transactions:
            if tx.category in ("transfer_in", "transfer_out"):
                direction = "转入" if tx.category == "transfer_in" else "转出"
                rows.append([f"转账-{direction}", tx.date.strftime("%Y-%m-%d"),
                    tx.raw_type,
                    f"{tx.amount:,.0f}" if tx.amount > 0 else "",
                    f"{-tx.amount:,.0f}" if tx.amount < 0 else "",
                    f"{abs(tx.amount):,.0f}", tx.counterparty])

        self._table.setRowCount(min(len(rows), 5000))
        for row_i, row in enumerate(rows[:5000]):
            for col_j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_i, col_j, item)
