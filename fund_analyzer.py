#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
银行流水资金统计工具
纯本地运行，零联网，数据不外泄
功能：
  1. 重复购买理财产品 — 去重后计算（同账户短期重复购买合并）
  2. 取现/存现反复 — 配对后按最小金额计算
"""

import sys
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLineEdit, QLabel, QTableWidget, QTableWidgetItem,
    QFileDialog, QFrame, QGroupBox, QTabWidget,
    QMessageBox, QHeaderView, QCheckBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar, QSplitter, QSizePolicy,
    QAbstractItemView, QDialog, QDialogButtonBox, QGridLayout,
    QRadioButton, QButtonGroup, QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QAction

APP_NAME = "银行流水资金统计工具"
APP_VERSION = "1.0.0"


def smart_read_csv(path):
    """智能读取 CSV，自动检测编码和分隔符"""
    for enc in ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"]:
        for sep in [",", "\t", ";", "|"]:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, nrows=5)
                if len(df.columns) > 1:
                    df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str)
                    return df
            except Exception:
                continue
    raise ValueError("无法识别 CSV 编码或分隔符")


def parse_amount(val):
    """解析金额字符串为数值"""
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(",", "").replace("¥", "").replace("￥", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(val):
    """解析日期字符串"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d",
                "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, errors="raise")
    except Exception:
        return None


class FundAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.df = None
        self.original_df = None
        self.stat_result = None

        self.init_ui()
        self.apply_styles()

    # ── UI 初始化 ─────────────────────────────────────────────
    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ===== 左侧控制面板 =====
        left = QWidget()
        left.setFixedWidth(420)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 文件操作
        grp_file = QGroupBox("文件操作")
        f = QVBoxLayout(grp_file)
        self.btn_import = QPushButton("📂 导入银行流水")
        self.btn_import.setToolTip("支持 Excel(.xlsx/.xls)、CSV 格式")
        self.btn_import.clicked.connect(self.import_data)
        f.addWidget(self.btn_import)

        self.lbl_file = QLabel("未加载文件")
        self.lbl_file.setStyleSheet("color:#666; font-size:12px;")
        self.lbl_file.setWordWrap(True)
        f.addWidget(self.lbl_file)

        self.btn_export = QPushButton("💾 导出统计结果")
        self.btn_export.clicked.connect(self.export_result)
        self.btn_export.setEnabled(False)
        f.addWidget(self.btn_export)
        left_layout.addWidget(grp_file)

        # 字段映射
        grp_map = QGroupBox("字段映射（自动识别）")
        g = QGridLayout(grp_map)
        g.setSpacing(8)

        self.cmb_date = QComboBox()
        self.cmb_name = QComboBox()
        self.cmb_card = QComboBox()
        self.cmb_type = QComboBox()
        self.cmb_amount = QComboBox()
        self.cmb_counterparty = QComboBox()
        self.cmb_remark = QComboBox()

        combos = [
            ("日期列:", self.cmb_date),
            ("姓名列:", self.cmb_name),
            ("卡号列:", self.cmb_card),
            ("交易类型列:", self.cmb_type),
            ("金额列:", self.cmb_amount),
            ("交易对手列:", self.cmb_counterparty),
            ("备注列:", self.cmb_remark),
        ]
        for i, (label, cmb) in enumerate(combos):
            g.addWidget(QLabel(label), i, 0)
            g.addWidget(cmb, i, 1)

        left_layout.addWidget(grp_map)

        # 统计设置
        grp_cfg = QGroupBox("统计设置")
        v = QVBoxLayout(grp_cfg)

        # 理财产品去重
        self.chk_licai = QCheckBox("✅ 理财产品去重")
        self.chk_licai.setChecked(True)
        self.chk_licai.setToolTip("同一账户短期内重复购买同金额理财的，合并为一条")
        v.addWidget(self.chk_licai)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("金额容差（±%）:"))
        self.spin_licai_pct = QDoubleSpinBox()
        self.spin_licai_pct.setRange(0.1, 20.0)
        self.spin_licai_pct.setValue(5.0)
        self.spin_licai_pct.setDecimals(1)
        self.spin_licai_pct.setSuffix("%")
        h1.addWidget(self.spin_licai_pct)
        v.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("时间窗口（天）:"))
        self.spin_licai_days = QSpinBox()
        self.spin_licai_days.setRange(1, 90)
        self.spin_licai_days.setValue(30)
        h2.addWidget(self.spin_licai_days)
        v.addLayout(h2)

        v.addSpacing(10)

        # 取现存现配对
        self.chk_cash = QCheckBox("✅ 取现/存现配对")
        self.chk_cash.setChecked(True)
        self.chk_cash.setToolTip("同一账户取款后短期内有存款的，视为反复操作，按最小金额统计")
        v.addWidget(self.chk_cash)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("金额容差（±%）:"))
        self.spin_cash_pct = QDoubleSpinBox()
        self.spin_cash_pct.setRange(0.1, 50.0)
        self.spin_cash_pct.setValue(20.0)
        self.spin_cash_pct.setDecimals(1)
        self.spin_cash_pct.setSuffix("%")
        h3.addWidget(self.spin_cash_pct)
        v.addLayout(h3)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel("时间窗口（天）:"))
        self.spin_cash_days = QSpinBox()
        self.spin_cash_days.setRange(1, 60)
        self.spin_cash_days.setValue(14)
        h4.addWidget(self.spin_cash_days)
        v.addLayout(h4)

        h5 = QHBoxLayout()
        h5.addWidget(QLabel("最小配对金额:"))
        self.spin_cash_min = QDoubleSpinBox()
        self.spin_cash_min.setRange(0, 1000000)
        self.spin_cash_min.setValue(1000)
        self.spin_cash_min.setDecimals(0)
        h5.addWidget(self.spin_cash_min)
        v.addLayout(h5)

        v.addSpacing(10)

        # 交易类型关键词
        self.chk_ignore_small = QCheckBox("忽略小额交易（<100元）")
        self.chk_ignore_small.setChecked(False)
        v.addWidget(self.chk_ignore_small)

        left_layout.addWidget(grp_cfg)

        # 执行按钮
        self.btn_run = QPushButton("▶ 开始统计")
        self.btn_run.setStyleSheet(
            "QPushButton{background:#409EFF;color:white;font-weight:bold;padding:10px;font-size:14px;}"
            "QPushButton:hover{background:#66b1ff;}"
        )
        self.btn_run.clicked.connect(self.run_analysis)
        self.btn_run.setEnabled(False)
        left_layout.addWidget(self.btn_run)

        left_layout.addStretch()
        main_layout.addWidget(left)

        # ===== 右侧结果区域 =====
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 统计摘要
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(180)
        self.summary_text.setPlaceholderText("统计摘要将显示在这里...")
        right_layout.addWidget(QLabel("📋 统计摘要:"))
        right_layout.addWidget(self.summary_text)

        # 明细表格
        right_layout.addWidget(QLabel("📊 统计明细（配对/去重结果）:"))
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        right_layout.addWidget(self.table, stretch=1)

        # 汇总表格
        right_layout.addWidget(QLabel("📈 按账户汇总:"))
        self.table_summary = QTableWidget()
        self.table_summary.setAlternatingRowColors(True)
        self.table_summary.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr2 = self.table_summary.horizontalHeader()
        hdr2.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.table_summary, stretch=1)

        main_layout.addWidget(right, stretch=1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | 请点击「导入银行流水」开始")

    # ── 样式 ─────────────────────────────────────────────────
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow{background:#f5f7fa;}
            QGroupBox{font-weight:bold; border:1px solid #dcdfe6; border-radius:4px; margin-top:8px; padding-top:8px;}
            QGroupBox::title{subcontrol-origin:margin; left:6px; padding:0 4px;}
            QPushButton{background:#fff; border:1px solid #dcdfe6; border-radius:4px; padding:6px 12px;}
            QPushButton:hover{background:#ecf5ff; border-color:#409EFF;}
            QPushButton:disabled{color:#999; background:#f5f7fa; border-color:#e4e7ed;}
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox{padding:5px; border:1px solid #dcdfe6; border-radius:4px; background:#fff;}
            QTableWidget{border:1px solid #dcdfe6; gridline-color:#ebeef5; background:#fff;}
            QTableWidget::item{padding:4px;}
            QHeaderView::section{background:#f5f7fa; padding:6px; border:1px solid #dcdfe6; font-weight:bold;}
            QTextEdit{border:1px solid #dcdfe6; border-radius:4px; background:#fff;}
            QCheckBox{padding:4px 0;}
        """)

    # ═══════════════════════════════════════════════════════════
    #  数据导入
    # ═══════════════════════════════════════════════════════════
    def import_data(self):
        filters = "Excel (*.xlsx *.xls);;CSV (*.csv);;All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "导入银行流水", "", filters)
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(path, dtype=str)
            elif ext == ".csv":
                df = smart_read_csv(path)
            else:
                try:
                    df = smart_read_csv(path)
                except Exception:
                    raise ValueError(f"不支持的文件格式: {ext}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法读取文件:\n{e}")
            return

        self.original_df = df.copy()
        self.df = df.copy()
        self.lbl_file.setText(f"{os.path.basename(path)}\n{len(df)} 行 × {len(df.columns)} 列")
        self.status_bar.showMessage(f"导入成功: {os.path.basename(path)} | {len(df)} 行")

        self._auto_map_columns(df)
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(False)

        # 清空结果
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table_summary.setRowCount(0)
        self.table_summary.setColumnCount(0)
        self.summary_text.clear()

    def _auto_map_columns(self, df):
        """自动识别并映射字段"""
        cols = df.columns.tolist()
        col_lower = {c: c.lower() for c in cols}

        def find_col(keywords, exclude=None):
            best = None
            best_score = -1
            for c in cols:
                cl = col_lower[c]
                if exclude and any(ex in cl for ex in exclude):
                    continue
                score = 0
                for kw in keywords:
                    if kw in cl:
                        score += 10
                        if cl.startswith(kw):
                            score += 5
                if score > best_score:
                    best_score = score
                    best = c
            return best

        mappings = {
            self.cmb_date: (["时间", "日期", "time", "date", "交易时间"], None),
            self.cmb_name: (["姓名", "户名", "name", "客户", "持卡人"], None),
            self.cmb_card: (["卡号", "账号", "card", "account", "银行卡", "银行账户", "账户"],
                            ["对方", "对手", "counter", "交易对手", "转入", "转出"]),
            self.cmb_type: (["类型", "type", "交易类型", "摘要", "业务类型", "业务种类"], None),
            self.cmb_amount: (["金额", "amount", "money", "sum", "交易金额", "发生额", "收支"], None),
            self.cmb_counterparty: (["对手", "对方", "counter", "交易对手", "对方账号", "对方户名", "对方名称"], None),
            self.cmb_remark: (["备注", "remark", "附言", "用途", "说明"], None),
        }

        for cmb, (keywords, exclude) in mappings.items():
            cmb.clear()
            cmb.addItems([""] + cols)
            match = find_col(keywords, exclude)
            if match:
                idx = cmb.findText(match)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)

    # ═══════════════════════════════════════════════════════════
    #  核心统计逻辑
    # ═══════════════════════════════════════════════════════════
    def run_analysis(self):
        if self.df is None:
            return

        date_col = self.cmb_date.currentText()
        name_col = self.cmb_name.currentText()
        card_col = self.cmb_card.currentText()
        type_col = self.cmb_type.currentText()
        amount_col = self.cmb_amount.currentText()
        cp_col = self.cmb_counterparty.currentText()
        remark_col = self.cmb_remark.currentText()

        if not all([date_col, amount_col, type_col]):
            QMessageBox.information(self, "提示", "请先选择日期列、金额列和交易类型列")
            return

        df = self.df.copy()

        # 解析金额
        df["_amount"] = df[amount_col].apply(parse_amount)
        df["_date"] = df[date_col].apply(parse_date)

        # 过滤无效数据
        df = df[df["_amount"].notna() & (df["_amount"] != 0) & df["_date"].notna()].copy()

        # 忽略小额
        if self.chk_ignore_small.isChecked():
            df = df[df["_amount"].abs() >= 100].copy()

        if len(df) == 0:
            QMessageBox.information(self, "提示", "没有有效的交易数据")
            return

        # 账户标识列（优先卡号，其次姓名）
        account_col = card_col if card_col else name_col
        if not account_col:
            account_col = "_index"
            df[account_col] = "全部"

        # 统一账户标识
        df["_account"] = df[account_col].astype(str).str.strip()

        # 标准化交易类型
        df["_type"] = df[type_col].astype(str).str.strip()

        results = []
        summary_lines = []
        total_raw = df["_amount"].abs().sum()

        summary_lines.append(f"原始记录总数: {len(self.df)} 条")
        summary_lines.append(f"有效记录数: {len(df)} 条")
        summary_lines.append(f"原始资金总额（绝对值）: {total_raw:,.2f} 元")
        summary_lines.append("")

        # ── 1. 理财产品去重 ────────────────────────────
        licai_records = []
        if self.chk_licai.isChecked():
            lc_pct = self.spin_licai_pct.value() / 100.0
            lc_days = self.spin_licai_days.value()

            # 识别理财交易
            lc_mask = df["_type"].str.contains("理财", na=False)
            lc_df = df[lc_mask].copy()

            if len(lc_df) > 0:
                removed_count = 0
                kept_count = 0
                lc_total_before = lc_df["_amount"].abs().sum()
                lc_total_after = 0.0

                for account, group in lc_df.groupby("_account"):
                    group = group.sort_values("_date").reset_index(drop=True)
                    used = [False] * len(group)

                    for i in range(len(group)):
                        if used[i]:
                            continue
                        row_i = group.iloc[i]
                        amt_i = abs(row_i["_amount"])
                        date_i = row_i["_date"]

                        # 找相似记录
                        similar = []
                        for j in range(i + 1, len(group)):
                            if used[j]:
                                continue
                            row_j = group.iloc[j]
                            amt_j = abs(row_j["_amount"])
                            date_j = row_j["_date"]

                            days_diff = (date_j - date_i).days if date_j >= date_i else (date_i - date_j).days
                            if days_diff <= lc_days:
                                ratio = abs(amt_i - amt_j) / max(amt_i, amt_j) if max(amt_i, amt_j) > 0 else 0
                                if ratio <= lc_pct:
                                    similar.append(j)

                        if similar:
                            # 合并为一条，取金额最大的那条的日期和金额
                            all_idx = [i] + similar
                            max_idx = max(all_idx, key=lambda x: abs(group.iloc[x]["_amount"]))
                            row_kept = group.iloc[max_idx]
                            amt_kept = abs(row_kept["_amount"])
                            lc_total_after += amt_kept

                            licai_records.append({
                                "账户": account,
                                "日期": row_kept[date_col],
                                "交易类型": "理财（去重后）",
                                "金额": amt_kept,
                                "原始笔数": len(all_idx),
                                "处理方式": f"合并 {len(all_idx)} 笔（金额容差±{self.spin_licai_pct.value()}%，{lc_days}天内）",
                                "原始金额合计": sum(abs(group.iloc[x]["_amount"]) for x in all_idx),
                            })

                            for idx in all_idx:
                                used[idx] = True
                            removed_count += len(all_idx) - 1
                            kept_count += 1
                        else:
                            lc_total_after += amt_i
                            licai_records.append({
                                "账户": account,
                                "日期": row_i[date_col],
                                "交易类型": "理财",
                                "金额": amt_i,
                                "原始笔数": 1,
                                "处理方式": "无重复",
                                "原始金额合计": amt_i,
                            })
                            used[i] = True
                            kept_count += 1

                summary_lines.append(f"【理财产品去重】")
                summary_lines.append(f"  原始理财笔数: {len(lc_df)} 笔，金额合计: {lc_total_before:,.2f} 元")
                summary_lines.append(f"  合并重复笔数: {removed_count} 笔")
                summary_lines.append(f"  去重后笔数: {kept_count} 笔，金额合计: {lc_total_after:,.2f} 元")
                summary_lines.append(f"  压缩率: {(1 - lc_total_after / lc_total_before) * 100:.1f}%")
                summary_lines.append("")
            else:
                summary_lines.append("【理财产品去重】未检测到理财交易")
                summary_lines.append("")

        # ── 2. 取现存现配对 ────────────────────────────
        cash_records = []
        if self.chk_cash.isChecked():
            cash_pct = self.spin_cash_pct.value() / 100.0
            cash_days = self.spin_cash_days.value()
            cash_min = self.spin_cash_min.value()

            # 识别取现和存现
            withdraw_mask = df["_type"].str.contains("取|提款|取款|取现|ATM取款", na=False, regex=True)
            deposit_mask = df["_type"].str.contains("存|存款|存现|现金存入|ATM存款", na=False, regex=True)

            wd_df = df[withdraw_mask].copy()
            dp_df = df[deposit_mask].copy()

            if len(wd_df) > 0 or len(dp_df) > 0:
                wd_total_before = wd_df["_amount"].abs().sum() if len(wd_df) > 0 else 0
                dp_total_before = dp_df["_amount"].abs().sum() if len(dp_df) > 0 else 0
                paired_count = 0
                unpaired_wd = []
                unpaired_dp = []

                for account in set(wd_df["_account"].unique()) | set(dp_df["_account"].unique()):
                    wd_group = wd_df[wd_df["_account"] == account].sort_values("_date").reset_index(drop=True)
                    dp_group = dp_df[dp_df["_account"] == account].sort_values("_date").reset_index(drop=True)

                    wd_used = [False] * len(wd_group)
                    dp_used = [False] * len(dp_group)

                    for i in range(len(wd_group)):
                        if wd_used[i]:
                            continue
                        wd_row = wd_group.iloc[i]
                        wd_amt = abs(wd_row["_amount"])
                        wd_date = wd_row["_date"]

                        if wd_amt < cash_min:
                            continue

                        best_j = -1
                        best_score = float("inf")

                        for j in range(len(dp_group)):
                            if dp_used[j]:
                                continue
                            dp_row = dp_group.iloc[j]
                            dp_amt = abs(dp_row["_amount"])
                            dp_date = dp_row["_date"]

                            if dp_amt < cash_min:
                                continue

                            days_diff = abs((dp_date - wd_date).days)
                            if days_diff > cash_days:
                                continue

                            ratio = abs(wd_amt - dp_amt) / max(wd_amt, dp_amt) if max(wd_amt, dp_amt) > 0 else 0
                            if ratio > cash_pct:
                                continue

                            # 时间越近、金额越接近，分数越低越好
                            score = days_diff + ratio * 100
                            if score < best_score:
                                best_score = score
                                best_j = j

                        if best_j >= 0:
                            dp_row = dp_group.iloc[best_j]
                            dp_amt = abs(dp_row["_amount"])
                            min_amt = min(wd_amt, dp_amt)

                            cash_records.append({
                                "账户": account,
                                "取款日期": wd_row[date_col],
                                "存款日期": dp_row[date_col],
                                "取款金额": wd_amt,
                                "存款金额": dp_amt,
                                "统计金额": min_amt,
                                "处理方式": f"配对成功（取{wd_amt:,.2f}/存{dp_amt:,.2f}→按最小额{min_amt:,.2f}计）",
                            })
                            paired_count += 1
                            wd_used[i] = True
                            dp_used[best_j] = True
                        else:
                            unpaired_wd.append(wd_row)

                    for j in range(len(dp_group)):
                        if not dp_used[j]:
                            unpaired_dp.append(dp_group.iloc[j])

                # 未配对的取款
                for row in unpaired_wd:
                    amt = abs(row["_amount"])
                    cash_records.append({
                        "账户": row["_account"],
                        "取款日期": row[date_col],
                        "存款日期": "—",
                        "取款金额": amt,
                        "存款金额": 0,
                        "统计金额": amt,
                        "处理方式": "未配对取款",
                    })

                # 未配对的存款
                for row in unpaired_dp:
                    amt = abs(row["_amount"])
                    cash_records.append({
                        "账户": row["_account"],
                        "取款日期": "—",
                        "存款日期": row[date_col],
                        "取款金额": 0,
                        "存款金额": amt,
                        "统计金额": amt,
                        "处理方式": "未配对存款",
                    })

                # 配对后现金统计 = 配对成功按min计 + 未配对按原额计
                paired_total = sum(r["统计金额"] for r in cash_records if "配对成功" in r["处理方式"])
                unpaired_wd_total = sum(r["统计金额"] for r in cash_records if "未配对取款" in r["处理方式"])
                unpaired_dp_total = sum(r["统计金额"] for r in cash_records if "未配对存款" in r["处理方式"])
                cash_total_after = paired_total + unpaired_wd_total + unpaired_dp_total

                summary_lines.append(f"【取现/存现配对】")
                summary_lines.append(f"  原始取款笔数: {len(wd_df)} 笔，金额合计: {wd_total_before:,.2f} 元")
                summary_lines.append(f"  原始存款笔数: {len(dp_df)} 笔，金额合计: {dp_total_before:,.2f} 元")
                summary_lines.append(f"  成功配对: {paired_count} 对，配对统计: {paired_total:,.2f} 元")
                summary_lines.append(f"  未配对取款: {len(unpaired_wd)} 笔，金额: {unpaired_wd_total:,.2f} 元")
                summary_lines.append(f"  未配对存款: {len(unpaired_dp)} 笔，金额: {unpaired_dp_total:,.2f} 元")
                summary_lines.append(f"  配对后现金合计: {cash_total_after:,.2f} 元")
                summary_lines.append(f"  配对压缩率: {(1 - cash_total_after / max(wd_total_before + dp_total_before, 1)) * 100:.1f}%")
                summary_lines.append("")
            else:
                summary_lines.append("【取现/存现配对】未检测到取现或存现交易")
                summary_lines.append("")

        # ── 3. 其他交易统计 ────────────────────────────
        other_mask = pd.Series([True] * len(df))
        if self.chk_licai.isChecked():
            lc_mask = df["_type"].str.contains("理财", na=False)
            other_mask &= ~lc_mask
        if self.chk_cash.isChecked():
            wd_mask = df["_type"].str.contains("取|提款|取款|取现|ATM取款", na=False, regex=True)
            dp_mask = df["_type"].str.contains("存|存款|存现|现金存入|ATM存款", na=False, regex=True)
            other_mask &= ~(wd_mask | dp_mask)

        other_df = df[other_mask].copy()
        other_records = []
        for _, row in other_df.iterrows():
            other_records.append({
                "账户": row["_account"],
                "日期": row[date_col],
                "交易类型": row[type_col],
                "金额": abs(row["_amount"]),
                "处理方式": "常规统计",
                "交易对手": row.get(cp_col, "") if cp_col else "",
                "备注": row.get(remark_col, "") if remark_col else "",
            })

        # ── 汇总 ──────────────────────────────────────
        all_detail = licai_records + cash_records + other_records

        # 按账户汇总
        account_summary = defaultdict(lambda: {
            "理财金额": 0.0, "理财笔数": 0,
            "现金配对金额": 0.0, "未配对取款": 0.0, "未配对存款": 0.0, "现金配对对数": 0,
            "其他金额": 0.0, "其他笔数": 0,
            "合计": 0.0,
        })

        for r in licai_records:
            account_summary[r["账户"]]["理财金额"] += r["金额"]
            account_summary[r["账户"]]["理财笔数"] += 1

        for r in cash_records:
            if "配对成功" in r["处理方式"]:
                account_summary[r["账户"]]["现金配对金额"] += r["统计金额"]
                account_summary[r["账户"]]["现金配对对数"] += 1
            elif "未配对取款" in r["处理方式"]:
                account_summary[r["账户"]]["未配对取款"] += r["统计金额"]
            elif "未配对存款" in r["处理方式"]:
                account_summary[r["账户"]]["未配对存款"] += r["统计金额"]

        for r in other_records:
            account_summary[r["账户"]]["其他金额"] += r["金额"]
            account_summary[r["账户"]]["其他笔数"] += 1

        for acc in account_summary:
            s = account_summary[acc]
            s["合计"] = s["理财金额"] + s["现金配对金额"] + s["未配对取款"] + s["未配对存款"] + s["其他金额"]

        # 显示明细表格
        if all_detail:
            detail_df = pd.DataFrame(all_detail)
            self._show_table(self.table, detail_df)

        # 显示汇总表格
        if account_summary:
            summary_data = []
            for acc, s in sorted(account_summary.items()):
                summary_data.append({
                    "账户": acc,
                    "理财金额": f"{s['理财金额']:,.2f}",
                    "理财笔数": s["理财笔数"],
                    "现金配对": f"{s['现金配对金额']:,.2f}",
                    "配对对数": s["现金配对对数"],
                    "未配对取款": f"{s['未配对取款']:,.2f}",
                    "未配对存款": f"{s['未配对存款']:,.2f}",
                    "其他金额": f"{s['其他金额']:,.2f}",
                    "其他笔数": s["其他笔数"],
                    "合计": f"{s['合计']:,.2f}",
                })
            summary_df = pd.DataFrame(summary_data)
            self._show_table(self.table_summary, summary_df)

        # 保存结果用于导出
        self.stat_result = {
            "明细": pd.DataFrame(all_detail) if all_detail else None,
            "汇总": pd.DataFrame(summary_data) if account_summary else None,
        }

        # 显示摘要
        grand_total = sum(s["合计"] for s in account_summary.values())
        summary_lines.append(f"【综合统计】")
        summary_lines.append(f"  处理后资金合计: {grand_total:,.2f} 元")
        summary_lines.append(f"  原始资金合计: {total_raw:,.2f} 元")
        if total_raw > 0:
            summary_lines.append(f"  整体压缩率: {(1 - grand_total / total_raw) * 100:.1f}%")
        self.summary_text.setText("\n".join(summary_lines))
        self.btn_export.setEnabled(True)
        self.status_bar.showMessage("统计完成")

    def _show_table(self, table, df):
        table.setRowCount(min(len(df), 5000))
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels(df.columns.tolist())

        for r in range(min(len(df), 5000)):
            for c in range(len(df.columns)):
                val = str(df.iloc[r, c])
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # 处理行高亮
                if "去重后" in val or "配对成功" in val:
                    item.setBackground(QColor(232, 245, 233))  # 绿色
                elif "未配对" in val or "常规统计" in val:
                    pass
                elif c == 0 and "配对" in val:
                    item.setBackground(QColor(232, 245, 233))

                table.setItem(r, c, item)

        if len(df) > 5000:
            table.setRowCount(5001)
            for c in range(len(df.columns)):
                item = QTableWidgetItem("...")
                table.setItem(5000, c, item)

    # ═══════════════════════════════════════════════════════════
    #  导出
    # ═══════════════════════════════════════════════════════════
    def export_result(self):
        if self.stat_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出统计结果", "资金统计结果.xlsx",
            "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                if self.stat_result["明细"] is not None and len(self.stat_result["明细"]) > 0:
                    self.stat_result["明细"].to_excel(writer, sheet_name="统计明细", index=False)
                if self.stat_result["汇总"] is not None and len(self.stat_result["汇总"]) > 0:
                    self.stat_result["汇总"].to_excel(writer, sheet_name="账户汇总", index=False)

                # 统计摘要
                summary_df = pd.DataFrame({"统计摘要": self.summary_text.toPlainText().split("\n")})
                summary_df.to_excel(writer, sheet_name="统计摘要", index=False)

            self.status_bar.showMessage(f"导出成功: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = FundAnalyzer()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
