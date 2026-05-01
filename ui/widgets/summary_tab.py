#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总页 — 多卡横向对比表格 + 合计"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt

from engine import CardReport, AnalysisResult


class SummaryTab(QWidget):
    """汇总 Tab：概览卡片 + 多卡对比表"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reports: list[CardReport] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 汇总卡片行
        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setSpacing(10)
        layout.addWidget(self._cards_widget)

        # 对比表格
        self._table = QTableWidget()
        self._table.setObjectName("summaryTable")
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self._table, stretch=1)

        # 合计行
        self._total_label = QLabel()
        self._total_label.setStyleSheet("font-size:13px; font-weight:bold; padding:6px;")
        layout.addWidget(self._total_label)

    def load(self, result: AnalysisResult):
        self._reports = result.reports
        self._build_cards()
        self._build_table()
        self._build_total()

    def fund_info(self) -> dict:
        """返回汇总统计数据"""
        reports = self._reports
        return {
            "total_fund": sum(r.fund_size for r in reports),
            "total_balance": sum(r.balance for r in reports),
            "total_peak": sum(r.peak_funds for r in reports),
            "total_consume": sum(r.consume_total for r in reports),
            "total_income": sum(r.total_income for r in reports),
            "total_expense": sum(r.total_expense for r in reports),
            "card_count": len(reports),
            "total_txns": sum(r.total_records for r in reports),
        }

    # ── 内部 ──────────────────────────────────────────

    def _build_cards(self):
        while self._cards_layout.count():
            w = self._cards_layout.takeAt(0).widget()
            if w: w.deleteLater()

        info = self.fund_info()
        card_specs = [
            ("💎 总资金量", f"{info['total_fund']:,.0f} 元"),
            ("💰 总余额", f"{info['total_balance']:,.0f} 元"),
            ("📈 总历史峰值", f"{info['total_peak']:,.0f} 元"),
            ("🛒 总消费", f"{info['total_consume']:,.0f} 元"),
            ("📥 总入账", f"{info['total_income']:,.0f} 元"),
            ("📤 总出账", f"{info['total_expense']:,.0f} 元"),
            ("📋 卡数", f"{info['card_count']} 张"),
        ]
        for title, value in card_specs:
            frame = QFrame(); frame.setObjectName("cardFrame")
            fv = QVBoxLayout(frame); fv.setContentsMargins(10, 6, 10, 6)
            lt = QLabel(title); lt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lt.setStyleSheet("font-size:11px;")
            lv = QLabel(value); lv.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lv.setStyleSheet("font-size:15px; font-weight:bold;")
            fv.addWidget(lt); fv.addWidget(lv)
            self._cards_layout.addWidget(frame)

    def _build_table(self):
        headers = [
            "卡号", "姓名", "笔数", "入账", "出账", "入-出", "余额",
            "消费", "转出", "转入", "存现", "取现", "历史峰值", "资金量", "判定",
        ]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(self._reports))

        for i, r in enumerate(self._reports):
            vals = [
                r.card[-24:], r.name, str(r.total_records),
                f"{r.total_income:,.0f}", f"{r.total_expense:,.0f}",
                f"{r.total_income - r.total_expense:,.0f}",
                f"{r.balance:,.0f}", f"{r.consume_total:,.0f}",
                f"{r.transfer_out:,.0f}", f"{r.transfer_in:,.0f}",
                f"{r.income_detail.get('存现(cash_in)', 0):,.0f}",
                f"{r.expense_detail.get('取现(cash_out)', 0):,.0f}",
                f"{r.peak_funds:,.0f}", f"{r.fund_size:,.0f}",
                "取峰值" if r.peak_funds > r.fund_size else "取最小",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, j, item)

        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)

    def _build_total(self):
        info = self.fund_info()
        self._total_label.setText(
            f"▶ 合计: {info['card_count']}张卡 | {info['total_txns']}笔交易 | "
            f"总入账 {info['total_income']:,.0f} | 总出账 {info['total_expense']:,.0f} | "
            f"入-出 {info['total_income'] - info['total_expense']:,.0f} | "
            f"总资金量 {info['total_fund']:,.0f}"
        )
