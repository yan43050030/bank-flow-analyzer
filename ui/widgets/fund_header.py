#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金量突出显示 + 概览卡片"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PySide6.QtCore import Qt


class FundHeader(QWidget):
    """顶部：资金量大字 + 概览卡片行"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards_container = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_container)
        self._cards_layout.setSpacing(10)

        self._fund_label = QLabel("—")
        self._fund_label.setObjectName("fundBig")
        self._fund_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fund_label.setMinimumHeight(50)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._fund_label)
        layout.addWidget(self._cards_container)

    def set_fund_text(self, text: str):
        self._fund_label.setText(text)

    def set_cards(self, cards: list[tuple[str, str]]):
        """cards = [(title, value), ...]"""
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for title, value in cards:
            frame = QFrame()
            frame.setObjectName("cardFrame")
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(10, 6, 10, 6)

            lt = QLabel(title)
            lt.setStyleSheet("font-size:11px;")
            lt.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lv = QLabel(value)
            lv.setStyleSheet("font-size:15px; font-weight:bold;")
            lv.setAlignment(Qt.AlignmentFlag.AlignCenter)

            fv.addWidget(lt)
            fv.addWidget(lv)
            self._cards_layout.addWidget(frame)
