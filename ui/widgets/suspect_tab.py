#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嫌疑人画像 Tab (D1) — 同一人名下多张卡的聚合视图"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class SuspectTab(QWidget):
    """展示按身份证/姓名聚合后的嫌疑人画像"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("👤 嫌疑人画像 — 按身份证聚合多张卡")
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
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "姓名", "身份证", "卡数", "卡号", "合并交易数",
            "合并资金量", "卡间互转", "最高可疑度", "最高代持分"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table, stretch=1)

    def load(self, suspects: list):
        """suspects 来自 AnalysisResult.suspects"""
        if not suspects:
            self._info.setText("无嫌疑人聚合数据。")
            self._table.setRowCount(0)
            return

        multi = sum(1 for s in suspects if s.card_count > 1)
        self._info.setText(
            f"共 {len(suspects)} 名嫌疑人，其中 {multi} 人名下持有多张卡。"
            f"「合并资金量」已剔除本人卡间互转，避免重复计算。")

        self._table.setRowCount(len(suspects))
        for i, s in enumerate(suspects):
            vals = [
                s.name or "(无名)",
                s.id_card or "(无身份证)",
                str(s.card_count),
                ", ".join(c[-12:] for c in s.cards),
                str(s.total_records),
                f"{s.combined_fund_size:,.0f}",
                f"{s.inter_card_transfer:,.0f}",
                f"{s.max_suspicion:.0f} {s.max_suspicion_label}",
                f"{s.max_nominee:.0f} {s.max_nominee_label}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 多卡嫌疑人整行浅黄高亮
                if s.card_count > 1:
                    item.setBackground(QColor("#FFF3CD"))
                # 高可疑度 / 高代持分 标红
                if j == 7 and "高" in s.max_suspicion_label:
                    item.setBackground(QColor("#FFE0E0"))
                if j == 8 and ("高" in s.max_nominee_label
                               or "疑似" in s.max_nominee_label):
                    item.setBackground(QColor("#FFE0E0"))
                self._table.setItem(i, j, item)
