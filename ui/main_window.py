#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主窗口 — 组装各模块 (thin orchestrator)"""

import os
from typing import List, Optional

import pandas as pd
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QComboBox, QLabel, QTabWidget, QStatusBar, QFileDialog, QMessageBox,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt

from version import __version__, APP_NAME
from engine import (
    Transaction, analyze_bank_flow, AnalysisResult,
)
from ui.theme_manager import ThemeManager
from ui.parsers import parse_amount, parse_date, resolve_direction
from ui.widgets.left_panel import LeftPanel
from ui.widgets.fund_header import FundHeader
from ui.widgets.summary_tab import SummaryTab
from ui.widgets.card_tab import CardTab


class MainWindow(QMainWindow):
    """主窗口 — 连接 LeftPanel + FundHeader + Tabs"""

    def __init__(self):
        super().__init__()
        self._df: Optional[pd.DataFrame] = None
        self._result: Optional[AnalysisResult] = None
        self._current_file: str = ""
        self._card_tabs: list[CardTab] = []
        self.tm = ThemeManager()

        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1600, 960)
        self._init_ui()
        self.apply_theme()

    # ═══ UI 骨架 ═══════════════════════════════════════

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(10, 10, 10, 10)

        # 左侧面板
        self._left = LeftPanel()
        self._left.data_loaded.connect(self._on_data_loaded)
        self._left.run_requested.connect(self._on_run_requested)
        self._left.export_btn.clicked.connect(self._export_result)
        root.addWidget(self._left)

        # 右侧 — 包裹在 ScrollArea 中支持横向滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        right = QWidget()
        right.setMinimumWidth(700)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)

        # 顶部栏：资金量 + 主题
        top = QHBoxLayout()
        self._fund_header = FundHeader()
        top.addWidget(self._fund_header, stretch=1)
        top.addStretch()
        top.addWidget(QLabel("主题:"))
        self._cmb_theme = QComboBox()
        self._cmb_theme.setFixedWidth(110)
        self._cmb_theme.addItems(self.tm.theme_names)
        idx = self._cmb_theme.findText(
            self.tm.current.name if self.tm.current else "Light")
        if idx >= 0:
            self._cmb_theme.setCurrentIndex(idx)
        self._cmb_theme.currentTextChanged.connect(self._on_theme_changed)
        top.addWidget(self._cmb_theme)
        rv.addLayout(top)

        # Tab 页
        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)
        rv.addWidget(self._tabs, stretch=1)

        scroll.setWidget(right)
        root.addWidget(scroll, stretch=1)

        # 状态栏
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("就绪 | 点击「导入银行流水」开始")

    # ═══ 主题 ═══════════════════════════════════════════

    def apply_theme(self):
        ss = self.tm.get_stylesheet()
        c = self.tm.current.colors if self.tm.current else {}
        primary = c.get("primary", "#1a73e8")
        card_bg = c.get("card_bg", "#ffffff")
        text = c.get("text_primary", "#1a1a1a")
        ss += f"""
            QLabel#fundBig {{
                font-size: 22px; font-weight: bold;
                color: {primary};
                background: {card_bg};
                border: 2px solid {primary};
                border-radius: 10px;
                padding: 8px 16px;
            }}
            QLabel#sectionTitle {{
                font-size: 13px; font-weight: bold;
                color: {text};
                padding: 4px 0;
            }}
        """
        self.setStyleSheet(ss)

    def _on_theme_changed(self, name: str):
        self.tm.set_theme(name)
        self.apply_theme()

    # ═══ 数据流 ═════════════════════════════════════════

    def _on_data_loaded(self, df, path):
        self._df = df
        self._current_file = path
        self._status.showMessage(f"导入: {os.path.basename(path)} | {len(df)} 行")

    def _on_run_requested(self, mappings: dict, params: dict):
        if self._df is None:
            return
        df = self._df.copy()

        # 构建 Transaction 列表
        transactions: List[Transaction] = []
        for idx, (_, row) in enumerate(df.iterrows()):
            d = parse_date(row[mappings["date"]])
            if d is None:
                continue
            amt = parse_amount(row[mappings["amount"]])
            if amt == 0:
                continue
            # 借贷标志
            dc_col = mappings.get("dc", "")
            direction = resolve_direction(row[dc_col]) if dc_col else 0
            amt = abs(amt) if direction == 1 else (-abs(amt) if direction == -1 else amt)
            # 小额过滤
            if params.get("skip_small") and abs(amt) < 100:
                continue
            tx = Transaction(
                date=d,
                card=str(row.get(mappings["card"], "")).strip(),
                name=str(row.get(mappings.get("name", ""), "")).strip(),
                raw_type=str(row.get(mappings["type"], "")).strip(),
                amount=amt,
                counterparty=str(row.get(mappings.get("cp", ""), "")).strip()
                             if mappings.get("cp") else "",
                remark=str(row.get(mappings.get("remark", ""), "")).strip()
                        if mappings.get("remark") else "",
                row_index=idx,
            )
            transactions.append(tx)

        if not transactions:
            QMessageBox.information(self, "提示", "没有有效的交易数据")
            return

        # 执行分析
        self._result = analyze_bank_flow(
            transactions,
            mappings["card"],
            cash_max_days=params.get("cash_max_days", 30),
            finance_max_days=params.get("finance_max_days", 365 * 3),
        )

        # 渲染
        self._render_results()
        self._left.set_export_enabled(True)

        uniq = len(self._result.unique_reports)
        total = len(self._result.reports)
        total_tx = sum(r.total_records for r in self._result.reports)
        dup_note = f"（去重后{uniq}张）" if uniq < total else ""
        self._status.showMessage(f"统计完成 | {total}张卡{dup_note} {total_tx}笔交易")

    # ═══ 渲染结果 ══════════════════════════════════════

    def _render_results(self):
        reports = self._result.reports
        uniq_set = {id(r): i for i, r in enumerate(self._result.unique_reports)}

        self._tabs.blockSignals(True)
        self._tabs.clear()
        self._card_tabs.clear()

        # ── 汇总 Tab (使用去重数据) ──
        self._summary_tab = SummaryTab()
        self._summary_tab.load(self._result)  # 内部会调 unique_reports
        self._tabs.addTab(self._summary_tab, "📊 汇总")

        # ── 各卡 Tab ──
        for i, r in enumerate(reports):
            ct = CardTab()
            ct.load(r)
            label = self._tab_label(i, r)
            # 标记重复卡
            if id(r) not in uniq_set:
                label += " [重复]"
            self._tabs.addTab(ct, label)
            self._card_tabs.append(ct)

        self._tabs.blockSignals(False)
        self._tabs.setCurrentIndex(0)
        self._on_tab_changed(0)

    @staticmethod
    def _tab_label(index: int, report) -> str:
        short = report.card[-16:] if len(report.card) > 16 else report.card
        return f"卡{index + 1}: {short}"

    # ═══ Tab 切换 → 更新顶部 ═══════════════════════════

    def _on_tab_changed(self, index: int):
        if self._result is None or not self._result.reports:
            return

        if index == 0:
            info = self._summary_tab.fund_info()
            self._fund_header.set_fund_text(
                f"💎 总资金量: {info['total_fund']:,.0f} 元  ({info['card_count']}张卡合计)")
            self._fund_header.set_cards([
                ("📈 总历史峰值", f"{info['total_peak']:,.0f}"),
                ("💰 总余额", f"{info['total_balance']:,.0f}"),
                ("📥 总入账", f"{info['total_income']:,.0f}"),
                ("📤 总出账", f"{info['total_expense']:,.0f}"),
                ("🛒 总消费", f"{info['total_consume']:,.0f}"),
                ("📋 卡数", f"{info['card_count']} 张"),
                ("⚖ 入-出", f"{info['total_income'] - info['total_expense']:,.0f}"),
            ])
        else:
            r = self._result.reports[index - 1]
            peak = r.peak_funds
            tp = r.fund_detail.get("=资金通量(throughput)", 0)
            reason = f"取历史峰值 (峰值{peak:,.0f} > 通量{tp:,.0f})" if peak > tp \
                else f"取资金通量 (通量{tp:,.0f} >= 峰值{peak:,.0f})"
            self._fund_header.set_fund_text(
                f"💎 资金量: {r.fund_size:,.0f} 元  — {reason}")
            cash_recycled = r.fund_detail.get("现金循环抵销", 0)
            fin_recycled = r.fund_detail.get("理财循环抵销", 0)
            tx_recycled = r.fund_detail.get("同户转账循环抵销", 0)
            hhi_level = (
                "高度集中" if r.cp_hhi > 2500 else
                ("中度集中" if r.cp_hhi > 1000 else "分散")
            ) if r.cp_hhi > 0 else "-"
            self._fund_header.set_cards([
                ("📈 历史峰值", f"{r.peak_funds:,.0f}"),
                ("💰 卡内余额", f"{r.balance:,.0f}"),
                ("🛒 消费", f"{r.consume_total:,.0f}"),
                ("🔁 循环抵销",
                 f"{cash_recycled:,.0f}/{fin_recycled:,.0f}/{tx_recycled:,.0f}"),
                ("🔍 对手",
                 f"{r.cp_total_players}人 ⇄{r.cp_bi_count} HHI{hhi_level}"),
                ("⚠ 可疑度",
                 f"{r.suspicion_score:.0f}分 {r.suspicion_label}"),
                ("⚖ 入-出", f"{r.total_income - r.total_expense:,.0f}"),
            ])

    # ═══ 导出 ═══════════════════════════════════════════

    def _export_result(self):
        if self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "资金统计结果.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            data = []
            for r in self._result.reports:
                data.append({
                    "卡号": r.card, "姓名": r.name,
                    "交易笔数": r.total_records,
                    "入账合计": r.total_income, "出账合计": r.total_expense,
                    "历史最高资金": r.peak_funds, "卡内余额": r.balance,
                    "资金量": r.fund_size,
                    "消费支出": r.consume_total,
                    "转出": r.transfer_out, "转入": r.transfer_in,
                    "存现": r.income_detail.get("存现(cash_in)", 0),
                    "取现": r.expense_detail.get("取现(cash_out)", 0),
                    "存取经过": r.cash_paired,
                    "理财未赎回": r.finance_unredeemed,
                    "理财本金": r.finance_principal,
                    "理财获利": r.finance_profit,
                    "余额校验": "通过" if r.balance_verified else "不通过",
                })
            pd.DataFrame(data).to_excel(path, sheet_name="资金汇总", index=False)
            self._status.showMessage(f"导出成功: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
