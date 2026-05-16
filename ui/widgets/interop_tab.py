#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通联交叉 Tab (G 组) — 大额转账前的通话关联展示"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class InteropTab(QWidget):
    """展示「大额转账 ← 前置密集通话」交叉分析结果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("🔗 通联交叉分析 — 大额转账前的通话")
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
            "转账时间", "金额(元)", "交易对手", "对手手机号",
            "前置通话次数", "通话总时长(分)", "判定"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

    def load(self, correlations: list, window_hours: float = 24.0):
        """correlations 来自 interop.analyze_transfer_call_correlation()"""
        if not correlations:
            self._info.setText(
                "未发现「大额转账前有通话」的关联。\n"
                "提示：需要先导入话单联动包，且交易要带「对手手机号」字段。")
            self._table.setRowCount(0)
            return

        self._info.setText(
            f"发现 {len(correlations)} 笔大额转账在转账前 {window_hours:.0f} 小时内"
            f"与交易对手有通话往来 —— 「先沟通→后转账」模式，建议重点核查。")

        self._table.setRowCount(len(correlations))
        for i, c in enumerate(correlations):
            tx = c["transaction"]
            minutes = c["total_duration_sec"] / 60.0
            # 通话越多越可疑：≥3 通标红，1-2 通标黄
            verdict = ("🔴 高度关联" if c["call_count"] >= 3
                       else "🟡 关联")
            vals = [
                str(tx.get("time", "")),
                f"{abs(float(tx.get('amount', 0))):,.0f}",
                str(tx.get("counterparty", "")),
                str(tx.get("counterparty_phone", "")),
                str(c["call_count"]),
                f"{minutes:.1f}",
                verdict,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c["call_count"] >= 3:
                    item.setBackground(QColor("#ffe0e0"))
                elif c["call_count"] > 0:
                    item.setBackground(QColor("#fff3cd"))
                self._table.setItem(i, j, item)
