#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金链追踪 Tab (D2) — A→B→C→D N 跳资金过桥识别"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class FundChainTab(QWidget):
    """展示 N 跳资金链追踪结果（每条链一行）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("🔗 资金链追踪 — A→B→C→D 多层过桥识别")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setStyleSheet("font-size:12px; padding:4px;")
        layout.addWidget(self._info)

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "跳数", "起点账户", "最终去向", "总流量",
            "时间跨度(小时)", "金额稳定度", "链路明细"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self._table, stretch=1)

    def load(self, chains: list):
        """chains 来自 engine.trace_fund_chains()"""
        if not chains:
            self._info.setText(
                "未检测到 N 跳资金链。\n"
                "D2 自动追踪 A→B→C 多层过桥（需启用 B1 多银行合并把链上各账户都导入，"
                "且交易要带「对手账号」字段）。")
            self._table.setRowCount(0)
            return

        deep = sum(1 for c in chains if c["hops"] >= 3)
        self._info.setText(
            f"共检出 {len(chains)} 条资金链，其中 {deep} 条 ≥3 跳（"
            f"多层过桥，受贿/洗钱「找最终受益人」重点核查对象）。")

        self._table.setRowCount(len(chains))
        for i, c in enumerate(chains):
            chain = c["chain"]
            # 链路明细：起点卡 → 对手 → 对手 → ...
            path_desc = chain[0].card
            for tx in chain:
                tail = (tx.counterparty_account
                        or tx.counterparty or "?")
                path_desc += f" →[{abs(tx.amount):,.0f}] {tail}"
            vals = [
                str(c["hops"]),
                c["start_card"][-12:],
                str(c["end_destination"])[-12:],
                f"{c['total_amount']:,.0f}",
                f"{c['time_span_hours']:.1f}",
                f"{c['amount_stability']:.0%}",
                path_desc,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j == 6:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft
                                          | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 跳数越多越可疑：≥4 跳红 / 3 跳黄
                if c["hops"] >= 4:
                    item.setBackground(QColor("#FFE0E0"))
                elif c["hops"] == 3:
                    item.setBackground(QColor("#FFF3CD"))
                self._table.setItem(i, j, item)
