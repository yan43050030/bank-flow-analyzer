#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通联交叉 Tab (G 组) — 转账-通话交叉 (G2) + 综合关联评分 (G3)"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class InteropTab(QWidget):
    """通联交叉：子 Tab1 转账-通话交叉(G2) + 子 Tab2 综合关联评分(G3)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._sub_tabs = QTabWidget()
        layout.addWidget(self._sub_tabs, stretch=1)

        # ── 子 Tab 1: 转账-通话交叉 (G2) ──
        g2_page = QWidget()
        g2v = QVBoxLayout(g2_page)
        g2v.setContentsMargins(0, 0, 0, 0)
        self._corr_info = QLabel()
        self._corr_info.setWordWrap(True)
        self._corr_info.setStyleSheet("font-size:12px; padding:4px;")
        g2v.addWidget(self._corr_info)
        self._corr_table = QTableWidget()
        self._corr_table.setAlternatingRowColors(True)
        self._corr_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._corr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._corr_table.setColumnCount(7)
        self._corr_table.setHorizontalHeaderLabels([
            "转账时间", "金额(元)", "交易对手", "对手手机号",
            "前置通话次数", "通话总时长(分)", "判定"])
        self._corr_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        g2v.addWidget(self._corr_table)
        self._sub_tabs.addTab(g2_page, "🔗 转账-通话交叉")

        # ── 子 Tab 2: 综合关联评分 (G3) ──
        g3_page = QWidget()
        g3v = QVBoxLayout(g3_page)
        g3v.setContentsMargins(0, 0, 0, 0)
        self._rel_info = QLabel()
        self._rel_info.setWordWrap(True)
        self._rel_info.setStyleSheet("font-size:12px; padding:4px;")
        g3v.addWidget(self._rel_info)
        self._rel_table = QTableWidget()
        self._rel_table.setAlternatingRowColors(True)
        self._rel_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rel_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._rel_table.setColumnCount(9)
        self._rel_table.setHorizontalHeaderLabels([
            "对手手机号", "交易对手", "交易笔数", "交易总额",
            "通话次数", "通话时长(分)", "资金分", "通讯分", "综合判定"])
        self._rel_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        g3v.addWidget(self._rel_table)
        self._sub_tabs.addTab(g3_page, "⭐ 综合关联评分")

    def load(self, correlations: list, relationships: list = None,
             window_hours: float = 24.0):
        """correlations 来自 analyze_transfer_call_correlation()
        relationships 来自 analyze_relationship_strength()"""
        self._build_corr(correlations, window_hours)
        self._build_rel(relationships or [])

    # ── G2 转账-通话交叉 ──────────────────────────────
    def _build_corr(self, correlations: list, window_hours: float):
        if not correlations:
            self._corr_info.setText(
                "未发现「大额转账前有通话」的关联。\n"
                "提示：需先导入话单联动包，且交易要带「对手手机号」字段。")
            self._corr_table.setRowCount(0)
            return

        self._corr_info.setText(
            f"发现 {len(correlations)} 笔大额转账在转账前 {window_hours:.0f} 小时内"
            f"与交易对手有通话往来 —— 「先沟通→后转账」模式，建议重点核查。")
        self._corr_table.setRowCount(len(correlations))
        for i, c in enumerate(correlations):
            tx = c["transaction"]
            minutes = c["total_duration_sec"] / 60.0
            verdict = ("🔴 高度关联" if c["call_count"] >= 3 else "🟡 关联")
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
                self._corr_table.setItem(i, j, item)

    # ── G3 综合关联评分 ──────────────────────────────
    def _build_rel(self, relationships: list):
        if not relationships:
            self._rel_info.setText(
                "无综合关联评分数据。\n"
                "G3 = 资金往来 + 通讯往来 → 识别「资金+通讯双密切」核心关系。")
            self._rel_table.setRowCount(0)
            return

        core = sum(1 for r in relationships if r["is_core"])
        self._rel_info.setText(
            f"共 {len(relationships)} 个关联对手，其中 🔴 核心关系 {core} 个"
            f"（资金往来与通话往来双密切 —— 受贿/共谋核心圈的最强信号，优先核查）。")
        self._rel_table.setRowCount(len(relationships))
        for i, r in enumerate(relationships):
            names = ", ".join(r["counterparty_names"]) or "—"
            vals = [
                r["phone"], names, str(r["tx_count"]),
                f"{r['tx_amount']:,.0f}", str(r["call_count"]),
                f"{r['call_duration_sec'] / 60.0:.1f}",
                f"{r['fund_score']:.0f}", f"{r['comm_score']:.0f}",
                f"{r['total_score']:.0f} {r['label']}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if r["is_core"]:
                    item.setBackground(QColor("#ffe0e0"))
                elif r["total_score"] >= 50:
                    item.setBackground(QColor("#fff3cd"))
                self._rel_table.setItem(i, j, item)
