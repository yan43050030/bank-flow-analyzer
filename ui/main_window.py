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
    Transaction, analyze_bank_flow, AnalysisResult, SuspicionConfig,
    generate_report,
)
from interop import (
    InteropError, load_interop_package, save_interop_package,
    build_export_package, reports_to_transaction_events,
    analyze_transfer_call_correlation,
)
from ui.theme_manager import ThemeManager
from ui.parsers import parse_amount, parse_date, resolve_direction
from ui.widgets.left_panel import LeftPanel
from ui.widgets.fund_header import FundHeader
from ui.widgets.summary_tab import SummaryTab
from ui.widgets.card_tab import CardTab
from ui.widgets.interop_tab import InteropTab


class MainWindow(QMainWindow):
    """主窗口 — 连接 LeftPanel + FundHeader + Tabs"""

    def __init__(self):
        super().__init__()
        self._df: Optional[pd.DataFrame] = None
        self._result: Optional[AnalysisResult] = None
        self._current_file: str = ""
        self._card_tabs: list[CardTab] = []
        # 跨软件联动 (G 组)
        self._interop_pkg = None          # 从话单工具导入的交换包
        self._correlations: list = []     # 转账-通话交叉分析结果
        self._last_large_threshold: float = 50000.0
        self._has_interop_tab: bool = False
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
        self._left.report_requested.connect(self._export_report)
        self._left.interop_import_requested.connect(self._on_interop_import)
        self._left.interop_export_requested.connect(self._on_interop_export)
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

    def _on_run_requested(self, mappings: dict, params: dict, config: dict):
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
            dc_col = mappings.get("dc", "")
            direction = resolve_direction(row[dc_col]) if dc_col else 0
            amt = abs(amt) if direction == 1 else (-abs(amt) if direction == -1 else amt)
            if params.get("skip_small") and abs(amt) < 100:
                continue
            def col(key):
                """读取可选映射列的值，未映射返回空串"""
                c = mappings.get(key, "")
                return str(row.get(c, "")).strip() if c else ""

            tx = Transaction(
                date=d,
                card=str(row.get(mappings["card"], "")).strip(),
                name=str(row.get(mappings.get("name", ""), "")).strip(),
                raw_type=str(row.get(mappings["type"], "")).strip(),
                amount=amt,
                counterparty=col("cp"),
                remark=col("remark"),
                row_index=idx,
                counterparty_account=col("cp_account"),
                counterparty_phone=col("cp_phone"),
                counterparty_id_card=col("cp_id"),
            )
            transactions.append(tx)

        if not transactions:
            QMessageBox.information(self, "提示", "没有有效的交易数据")
            return

        # 构建可调阈值配置
        self._last_large_threshold = float(config.get("large_threshold", 50000))
        sconfig = SuspicionConfig(
            large_threshold=self._last_large_threshold,
            night_start=int(config.get("night_start", 22)),
            night_end=int(config.get("night_end", 6)),
            blacklist_keywords=config.get("blacklist_keywords", []),
        )

        # D4 关键时间点：解析 "标签:日期, 标签:日期" 文本
        key_dates = self._parse_key_dates(params.get("key_dates_raw", ""))

        # 执行分析
        self._result = analyze_bank_flow(
            transactions,
            mappings["card"],
            cash_max_days=params.get("cash_max_days", 30),
            finance_max_days=params.get("finance_max_days", 365 * 3),
            suspicion_config=sconfig,
            key_dates=key_dates,
        )

        # 通联交叉分析（若已导入话单联动包）
        self._run_correlation()

        # 渲染
        self._render_results()
        self._left.set_export_enabled(True)

        uniq = len(self._result.unique_reports)
        total = len(self._result.reports)
        total_tx = sum(r.total_records for r in self._result.reports)
        dup_note = f"（去重后{uniq}张）" if uniq < total else ""
        sync_n = len(self._result.synchronized_inflows)
        sync_note = f" | ⚠ {sync_n}组同步入账(疑分赃)" if sync_n else ""
        self._status.showMessage(
            f"统计完成 | {total}张卡{dup_note} {total_tx}笔交易{sync_note}")

    @staticmethod
    def _parse_key_dates(raw: str) -> list:
        """解析 D4 关键时间点文本 '标签:YYYY-MM-DD, 标签:YYYY-MM-DD' → [(label, datetime)]"""
        if not raw:
            return []
        result = []
        for part in raw.replace("，", ",").split(","):
            part = part.strip()
            if not part or ":" not in part.replace("：", ":"):
                continue
            label, _, datestr = part.replace("：", ":").partition(":")
            d = parse_date(datestr.strip())
            if d is not None:
                result.append((label.strip(), d))
        return result

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

        # ── 通联交叉 Tab（仅在导入了话单联动包时显示）──
        self._has_interop_tab = bool(
            self._interop_pkg is not None and self._interop_pkg.call_events)
        if self._has_interop_tab:
            interop_tab = InteropTab()
            interop_tab.load(self._correlations)
            self._tabs.addTab(interop_tab, "🔗 通联交叉")

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
        elif self._has_interop_tab and index == 1:
            # 通联交叉 Tab
            n = len(self._correlations)
            self._fund_header.set_fund_text(
                f"🔗 通联交叉分析 — {n} 笔大额转账在转账前有通话往来")
            self._fund_header.set_cards([
                ("🔗 关联转账数", f"{n}"),
                ("📞 已导入通话", f"{len(self._interop_pkg.call_events)}"),
            ])
        else:
            # 卡片 Tab：汇总占 1 个，通联交叉（若有）再占 1 个
            offset = 2 if self._has_interop_tab else 1
            r = self._result.reports[index - offset]
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

    def _export_report(self):
        """导出 HTML 证据报告"""
        if self._result is None or not self._result.reports:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出证据报告", "资金分析报告.html", "HTML (*.html)")
        if not path:
            return
        try:
            all_html = ["<!DOCTYPE html><html><head><meta charset='utf-8'><title>银行流水分析报告</title></head><body>"]
            for r in self._result.unique_reports:
                html = generate_report(r, f"银行流水分析报告 — {r.name}")
                all_html.append(html)
                all_html.append("<hr style='margin:40px 0'>")
            all_html.append("</body></html>")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(all_html))
            self._status.showMessage(f"报告已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

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

    # ═══ 跨软件联动 (G 组) ══════════════════════════════

    def _run_correlation(self):
        """对当前分析结果做转账-通话交叉分析（需已导入话单联动包）"""
        self._correlations = []
        if (self._interop_pkg is None
                or not self._interop_pkg.call_events
                or self._result is None):
            return
        tx_events = reports_to_transaction_events(self._result.unique_reports)
        self._correlations = analyze_transfer_call_correlation(
            tx_events, self._interop_pkg.call_events,
            window_hours=24.0,
            large_threshold=self._last_large_threshold)

    def _on_interop_import(self, path: str):
        """导入话单工具导出的 case-interop-v1 联动包"""
        try:
            pkg = load_interop_package(path)
        except InteropError as e:
            QMessageBox.critical(self, "联动包导入失败", str(e))
            return
        self._interop_pkg = pkg
        self._status.showMessage(
            f"已导入联动包: {os.path.basename(path)} | "
            f"实体{len(pkg.entities)} 通话{len(pkg.call_events)} "
            f"短信{len(pkg.sms_events)}")
        QMessageBox.information(
            self, "联动包已导入",
            f"案件: {pkg.case_name or '(未命名)'}\n"
            f"来源: {pkg.exported_by or '(未知)'}\n"
            f"通话事件: {len(pkg.call_events)} 条\n\n"
            f"完成流水分析后将自动生成「通联交叉」分析。")
        # 若已有分析结果，立即重算并刷新
        if self._result is not None:
            self._run_correlation()
            self._render_results()

    def _on_interop_export(self):
        """导出 case-interop-v1 联动包（含银行侧 transaction_events）"""
        if self._result is None or not self._result.reports:
            QMessageBox.information(self, "提示", "请先完成流水分析再导出联动包")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出案件联动包", "案件交换包.json", "案件交换包 (*.json)")
        if not path:
            return
        try:
            case_name = self._interop_pkg.case_name if self._interop_pkg else ""
            pkg = build_export_package(
                self._result.unique_reports,
                case_name=case_name,
                base_package=self._interop_pkg)
            save_interop_package(pkg, path)
            self._status.showMessage(
                f"联动包已导出: {path} | 交易{len(pkg.transaction_events)}条")
        except Exception as e:
            QMessageBox.critical(self, "联动包导出失败", str(e))
