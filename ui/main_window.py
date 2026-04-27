#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主窗口 — 统计概览卡片 + 统计过程 + 明细表格"""

import sys
import os
import re
from datetime import datetime
from typing import List

import pandas as pd

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLineEdit, QLabel, QTableWidget, QTableWidgetItem,
    QFileDialog, QGroupBox, QMessageBox, QHeaderView, QCheckBox,
    QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QStatusBar,
    QAbstractItemView, QGridLayout, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QAction

from version import __version__, APP_NAME
from engine import (
    Transaction, TransactionClassifier,
    CashChainMatcher, FinanceMatcher,
    CardAnalyzer, CardReport, AnalysisResult,
    analyze_bank_flow
)
from ui.theme_manager import ThemeManager


def smart_read_csv(path: str) -> pd.DataFrame:
    for enc in ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"]:
        for sep in [",", "\t", ";", "|"]:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, nrows=5)
                if len(df.columns) > 1:
                    return pd.read_csv(path, encoding=enc, sep=sep, dtype=str)
            except Exception:
                continue
    raise ValueError("无法识别 CSV 编码或分隔符")


def parse_amount(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(",", "").replace("¥", "").replace("￥", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, errors="raise").to_pydatetime()
    except Exception:
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.df = None
        self.result: AnalysisResult = None
        self.current_file: str = ""
        self.tm = ThemeManager()

        self.init_ui()
        self.apply_theme()

    # ── UI ──────────────────────────────────────────────
    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1500, 920)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(10, 10, 10, 10)

        # ===== 左侧面板 =====
        left = QWidget()
        left.setFixedWidth(380)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        # 文件
        g1 = QGroupBox("文件操作")
        f = QVBoxLayout(g1)
        self.btn_import = QPushButton("📂 导入银行流水")
        self.btn_import.clicked.connect(self.import_data)
        f.addWidget(self.btn_import)
        self.lbl_file = QLabel("未加载文件")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("font-size:11px;")
        f.addWidget(self.lbl_file)
        self.btn_export = QPushButton("💾 导出结果")
        self.btn_export.clicked.connect(self.export_result)
        self.btn_export.setEnabled(False)
        f.addWidget(self.btn_export)
        lv.addWidget(g1)

        # 字段映射
        g2 = QGroupBox("字段映射（自动识别）")
        g = QGridLayout(g2)
        g.setSpacing(6)
        self.cmb_date = QComboBox()
        self.cmb_name = QComboBox()
        self.cmb_card = QComboBox()
        self.cmb_type = QComboBox()
        self.cmb_amount = QComboBox()
        self.cmb_cp = QComboBox()
        self.cmb_remark = QComboBox()
        for i, (lb, cmb) in enumerate([
            ("日期:", self.cmb_date), ("姓名:", self.cmb_name),
            ("卡号:", self.cmb_card), ("交易类型:", self.cmb_type),
            ("金额:", self.cmb_amount), ("交易对手:", self.cmb_cp),
            ("备注:", self.cmb_remark)]):
            g.addWidget(QLabel(lb), i, 0)
            g.addWidget(cmb, i, 1)
        lv.addWidget(g2)

        # 统计参数
        g3 = QGroupBox("统计参数")
        v = QVBoxLayout(g3)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("存取时间窗口(天):"))
        self.spin_cash_days = QSpinBox()
        self.spin_cash_days.setRange(1, 90)
        self.spin_cash_days.setValue(30)
        h1.addWidget(self.spin_cash_days)
        v.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("理财时间窗口(天):"))
        self.spin_finance_days = QSpinBox()
        self.spin_finance_days.setRange(30, 365 * 5)
        self.spin_finance_days.setValue(365 * 3)
        h2.addWidget(self.spin_finance_days)
        v.addLayout(h2)

        self.chk_small = QCheckBox("忽略小额交易 (<100元)")
        v.addWidget(self.chk_small)

        lv.addWidget(g3)

        # 执行按钮
        self.btn_run = QPushButton("▶ 开始统计")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_run.setEnabled(False)
        lv.addWidget(self.btn_run)

        lv.addStretch()
        root.addWidget(left)

        # ===== 右侧主体 =====
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        # 顶部工具栏
        tb = QHBoxLayout()
        tb.addStretch()
        lbl_theme = QLabel("主题:")
        tb.addWidget(lbl_theme)
        self.cmb_theme = QComboBox()
        self.cmb_theme.setFixedWidth(120)
        self.cmb_theme.addItems(self.tm.theme_names)
        idx = self.cmb_theme.findText(self.tm.current.name if self.tm.current else "Light")
        if idx >= 0:
            self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentTextChanged.connect(self.on_theme_changed)
        tb.addWidget(self.cmb_theme)
        rv.addLayout(tb)

        # 概览卡片区域
        self.card_widget = QWidget()
        self.card_layout = QHBoxLayout(self.card_widget)
        self.card_layout.setSpacing(12)
        rv.addWidget(self.card_widget)

        # 统计过程
        rv.addWidget(QLabel("📋 统计过程:"))
        self.txt_steps = QTextEdit()
        self.txt_steps.setReadOnly(True)
        self.txt_steps.setMaximumHeight(200)
        self.txt_steps.setFont(QFont("Monaco", 11))
        rv.addWidget(self.txt_steps)

        # 明细表格
        rv.addWidget(QLabel("📊 统计明细:"))
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rv.addWidget(self.table, stretch=1)

        root.addWidget(right, stretch=1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | 点击「导入银行流水」开始")

    # ── 主题 ────────────────────────────────────────────
    def apply_theme(self):
        self.setStyleSheet(self.tm.get_stylesheet())

    def on_theme_changed(self, name: str):
        self.tm.set_theme(name)
        self.apply_theme()

    # ── 概览卡片 ────────────────────────────────────────
    def _build_cards(self, report: CardReport):
        # 清除旧卡片
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cards = [
            ("📈 历史最高资金", f"{report.peak_funds:,.0f} 元"),
            ("💰 卡内余额", f"{report.balance:,.0f} 元"),
            ("🏦 理财未赎回", f"{report.finance_unredeemed:,.0f} 元"),
            ("🛒 消费支出", f"{report.consume_total:,.0f} 元"),
            ("📤 净转出", f"{report.net_transfer:,.0f} 元"),
            ("💵 存取经过", f"{report.cash_paired:,.0f} 元"),
            ("📊 理财获利", f"{report.finance_profit:,.0f} 元"),
        ]

        for title, value in cards:
            frame = QFrame()
            frame.setObjectName("cardFrame")
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(12, 8, 12, 8)

            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("font-size:11px; font-weight:normal;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_value = QLabel(value)
            lbl_value.setStyleSheet("font-size:16px; font-weight:bold;")
            lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

            fv.addWidget(lbl_title)
            fv.addWidget(lbl_value)
            self.card_layout.addWidget(frame)

    # ── 导入/导出 ───────────────────────────────────────
    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入银行流水", "",
            "Excel (*.xlsx *.xls);;CSV (*.csv);;All Files (*)")
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".xlsx", ".xls"):
                self.df = pd.read_excel(path, dtype=str)
            else:
                self.df = smart_read_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return

        self.current_file = path
        self.lbl_file.setText(f"{os.path.basename(path)}\n{len(self.df)} 行 × {len(self.df.columns)} 列")
        self.status_bar.showMessage(f"导入: {os.path.basename(path)} | {len(self.df)} 行")
        self._auto_map(self.df)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(False)

    def _auto_map(self, df):
        cols = df.columns.tolist()
        col_lower = {c: c.lower() for c in cols}

        def find_col(kws, excl=None):
            best, best_s = None, -1
            for c in cols:
                cl = col_lower[c]
                if excl and any(e in cl for e in excl):
                    continue
                s = sum(10 for k in kws if k in cl) + sum(5 for k in kws if cl.startswith(k))
                if s > best_s:
                    best_s, best = s, c
            return best

        mappings = {
            self.cmb_date: (["时间", "日期", "time", "date"], None),
            self.cmb_name: (["姓名", "户名", "name", "客户"], None),
            self.cmb_card: (["卡号", "账号", "card", "account", "账户"], ["对方", "对手"]),
            self.cmb_type: (["类型", "type", "摘要", "业务类型"], None),
            self.cmb_amount: (["金额", "amount", "money", "发生额", "收支"], None),
            self.cmb_cp: (["对手", "对方", "counter", "交易对手"], None),
            self.cmb_remark: (["备注", "remark", "附言", "用途", "说明"], None),
        }
        for cmb, (kws, excl) in mappings.items():
            cmb.clear()
            cmb.addItems([""] + cols)
            m = find_col(kws, excl)
            if m:
                i = cmb.findText(m)
                if i >= 0:
                    cmb.setCurrentIndex(i)

    # ── 分析 ────────────────────────────────────────────
    def run_analysis(self):
        if self.df is None:
            return

        date_c = self.cmb_date.currentText()
        name_c = self.cmb_name.currentText()
        card_c = self.cmb_card.currentText()
        type_c = self.cmb_type.currentText()
        amt_c = self.cmb_amount.currentText()
        cp_c = self.cmb_cp.currentText()
        rmk_c = self.cmb_remark.currentText()

        if not all([date_c, amt_c, type_c, card_c]):
            QMessageBox.information(self, "提示", "至少需要选择：日期列、卡号列、交易类型列、金额列")
            return

        df = self.df.copy()

        # 构建 Transaction 列表
        transactions: List[Transaction] = []
        for idx, (_, row) in enumerate(df.iterrows()):
            d = parse_date(row[date_c])
            if d is None:
                continue
            amt = parse_amount(row[amt_c])
            if amt == 0:
                continue
            if self.chk_small.isChecked() and abs(amt) < 100:
                continue
            tx = Transaction(
                date=d,
                card=str(row.get(card_c, "")).strip(),
                name=str(row.get(name_c, "")).strip() if name_c else "",
                raw_type=str(row.get(type_c, "")).strip(),
                amount=amt,
                counterparty=str(row.get(cp_c, "")).strip() if cp_c else "",
                remark=str(row.get(rmk_c, "")).strip() if rmk_c else "",
                row_index=idx,
            )
            transactions.append(tx)

        if not transactions:
            QMessageBox.information(self, "提示", "没有有效的交易数据")
            return

        # 执行分析
        cd = self.spin_cash_days.value()
        fd = self.spin_finance_days.value()
        result = analyze_bank_flow(transactions, card_c, cash_max_days=cd, finance_max_days=fd)
        self.result = result

        # 显示结果
        if result.reports:
            r = result.reports[0]  # 默认显示第一张卡
            self._build_cards(r)
            self.txt_steps.setText("\n".join(r.steps))
            self._show_detail_table(r)
            self.btn_export.setEnabled(True)
            self.status_bar.showMessage(
                f"统计完成 | {r.total_records}笔交易 → 峰值{r.peak_funds:,.0f} 余额{r.balance:,.0f}")
        else:
            self.status_bar.showMessage("分析完成，无结果")

    def _show_detail_table(self, report: CardReport):
        rows = []

        # 配对的存取
        for p in report.cash_pairs:
            rows.append(["现金存取配对",
                        p.deposit_tx.date.strftime("%Y-%m-%d"),
                        p.withdraw_tx.date.strftime("%Y-%m-%d"),
                        f"{abs(p.deposit_tx.amount):,.0f}",
                        f"{abs(p.withdraw_tx.amount):,.0f}",
                        f"{p.matched_amount:,.0f}",
                        "配对成功"])

        # 未配对存取
        for d in report.unmatched_deposits:
            rows.append(["现金-未配对存款", d.date.strftime("%Y-%m-%d"), "",
                        f"{abs(d.amount):,.0f}", "", f"{abs(d.amount):,.0f}", "净存入"])
        for w in report.unmatched_withdraws:
            rows.append(["现金-未配对取款", w.date.strftime("%Y-%m-%d"), "",
                        "", f"{abs(w.amount):,.0f}", f"{abs(w.amount):,.0f}", "净取出"])

        # 理财配对
        for fp in report.finance_pairs:
            rows.append(["理财买卖配对",
                        fp.buy_tx.date.strftime("%Y-%m-%d"),
                        fp.sell_tx.date.strftime("%Y-%m-%d") if fp.sell_tx else "未赎回",
                        f"{fp.principal:,.0f}",
                        f"{abs(fp.sell_tx.amount):,.0f}" if fp.sell_tx else "",
                        f"{fp.profit:,.0f}",
                        "利息" if fp.profit > 0 else "无收益"])

        # 消费
        for tx in report.all_transactions:
            if tx.category == "consume":
                rows.append(["消费支出", tx.date.strftime("%Y-%m-%d"), tx.raw_type,
                            "", f"{abs(tx.amount):,.0f}", f"{abs(tx.amount):,.0f}", tx.counterparty])

        # 转账
        for tx in report.all_transactions:
            if tx.category in ("transfer_in", "transfer_out"):
                direction = "转入" if tx.category == "transfer_in" else "转出"
                rows.append([f"转账-{direction}", tx.date.strftime("%Y-%m-%d"), tx.raw_type,
                            f"{tx.amount:,.0f}" if tx.amount > 0 else "",
                            f"{-tx.amount:,.0f}" if tx.amount < 0 else "",
                            f"{abs(tx.amount):,.0f}", tx.counterparty])

        self.table.setRowCount(min(len(rows), 5000))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["分类", "日期", "关联日期/类型", "存入/买入", "取出/赎回", "统计金额", "备注"])

        for r, row in enumerate(rows[:5000]):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)

    def export_result(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "资金统计结果.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            data = []
            for report in self.result.reports:
                data.append({
                    "卡号": report.card,
                    "姓名": report.name,
                    "历史最高资金": report.peak_funds,
                    "卡内余额": report.balance,
                    "理财未赎回": report.finance_unredeemed,
                    "理财本金": report.finance_principal,
                    "理财获利": report.finance_profit,
                    "消费支出": report.consume_total,
                    "转出": report.transfer_out,
                    "转入": report.transfer_in,
                    "净转出": report.net_transfer,
                    "存取经过": report.cash_paired,
                    "交易笔数": report.total_records,
                })
            summary_df = pd.DataFrame(data)
            steps_df = pd.DataFrame({"统计过程": ["\n".join(r.steps) for r in self.result.reports]})

            with pd.ExcelWriter(path, engine="openpyxl") as w:
                summary_df.to_excel(w, sheet_name="资金汇总", index=False)
                steps_df.to_excel(w, sheet_name="统计过程", index=False)

            self.status_bar.showMessage(f"导出成功: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
