#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""左侧控制面板 — 文件导入 / 字段映射 / 参数设置 / 执行"""

import os
from typing import Optional

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QComboBox, QLabel, QGroupBox,
    QCheckBox, QSpinBox, QFileDialog, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Signal

from ui.parsers import smart_read_csv, smart_read_excel, SheetChoiceError


class LeftPanel(QWidget):
    """控制面板 — 所有交互通过 Signal 通知主窗口"""

    # 数据就绪信号: (df, file_path)
    data_loaded = Signal(object, str)
    # 执行分析信号: (mappings_dict, params_dict, suspicion_config_dict)
    run_requested = Signal(dict, dict, dict)
    # 报告导出信号
    report_requested = Signal()
    # 跨软件联动 (G 组): 导入联动包 (路径) / 导出联动包
    interop_import_requested = Signal(str)
    interop_export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pd.DataFrame] = None
        self._current_file: str = ""
        self.setFixedWidth(380)
        self._init_ui()

    def _init_ui(self):
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)

        # ── 文件操作 ──
        g1 = QGroupBox("文件操作")
        f = QVBoxLayout(g1)
        self.btn_import = QPushButton("📂 导入银行流水 (xlsx/csv)")
        self.btn_import.clicked.connect(self._on_import)
        f.addWidget(self.btn_import)
        self.lbl_file = QLabel("未加载文件")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("font-size:11px;")
        f.addWidget(self.lbl_file)
        self.btn_export = QPushButton("💾 导出结果 (xlsx)")
        self.btn_export.setEnabled(False)
        f.addWidget(self.btn_export)
        self.btn_report = QPushButton("📄 导出证据报告 (HTML)")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(self._on_export_report)
        f.addWidget(self.btn_report)
        # 跨软件联动 (G 组)
        self.btn_interop_import = QPushButton("📥 导入话单联动包 (json)")
        self.btn_interop_import.clicked.connect(self._on_interop_import)
        f.addWidget(self.btn_interop_import)
        self.btn_interop_export = QPushButton("🔗 导出案件联动包 (json)")
        self.btn_interop_export.setEnabled(False)
        self.btn_interop_export.clicked.connect(self._on_interop_export)
        f.addWidget(self.btn_interop_export)
        lv.addWidget(g1)

        # ── 字段映射 ──
        g2 = QGroupBox("字段映射（自动识别）")
        g = QGridLayout(g2)
        g.setSpacing(6)
        self._mapping_cmbs = {}
        field_specs = [
            ("date",   "日期"),       ("name",     "姓名"),
            ("card",   "卡号"),       ("type",     "交易摘要"),
            ("amount", "金额"),       ("dc",       "借贷标志"),
            ("cp",     "交易对手"),   ("remark",   "备注"),
            ("cp_phone",   "对手手机号"),  ("cp_id",  "对手身份证"),
            ("cp_account", "对手账号"),
        ]
        for i, (key, label) in enumerate(field_specs):
            cmb = QComboBox()
            g.addWidget(QLabel(f"{label}:"), i, 0)
            g.addWidget(cmb, i, 1)
            self._mapping_cmbs[key] = cmb
        lv.addWidget(g2)

        # ── 参数 ──
        g3 = QGroupBox("统计参数")
        v = QVBoxLayout(g3)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("存取时间窗口(天):"))
        self.spin_cash = QSpinBox(); self.spin_cash.setRange(1, 90); self.spin_cash.setValue(30)
        h1.addWidget(self.spin_cash); v.addLayout(h1)
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("理财时间窗口(天):"))
        self.spin_fin = QSpinBox(); self.spin_fin.setRange(30, 365*5); self.spin_fin.setValue(365*3)
        h2.addWidget(self.spin_fin); v.addLayout(h2)
        self.chk_small = QCheckBox("忽略小额交易 (<100元)")
        v.addWidget(self.chk_small)
        # D4 关键时间点
        from PySide6.QtWidgets import QLineEdit
        v.addWidget(QLabel("关键时间点 (D4):"))
        self.edit_key_dates = QLineEdit()
        self.edit_key_dates.setPlaceholderText("招标日:2024-06-15, 合同日:2024-08-01")
        v.addWidget(self.edit_key_dates)
        lv.addWidget(g3)

        # ── 可调阈值 (B3) ──
        g4 = QGroupBox("可疑度阈值 (B3)")
        v4 = QVBoxLayout(g4)
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("大额阈值(万):"))
        self.spin_large = QSpinBox(); self.spin_large.setRange(1, 1000)
        self.spin_large.setValue(5); self.spin_large.setSuffix("万")
        h3.addWidget(self.spin_large); v4.addLayout(h3)
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("深夜时段:"))
        self.spin_night_start = QSpinBox(); self.spin_night_start.setRange(18, 23)
        self.spin_night_start.setValue(22)
        h4.addWidget(self.spin_night_start)
        h4.addWidget(QLabel("~"))
        self.spin_night_end = QSpinBox(); self.spin_night_end.setRange(0, 8)
        self.spin_night_end.setValue(6)
        h4.addWidget(self.spin_night_end); h4.addWidget(QLabel("时"))
        v4.addLayout(h4)
        from PySide6.QtWidgets import QLineEdit
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("对手黑名单:"))
        self.edit_blacklist = QLineEdit()
        self.edit_blacklist.setPlaceholderText("逗号分隔，如: 博彩,虚拟币")
        h5.addWidget(self.edit_blacklist); v4.addLayout(h5)
        lv.addWidget(g4)

        # ── 执行 ──
        self.btn_run = QPushButton("▶ 开始统计")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.clicked.connect(self._on_run)
        self.btn_run.setEnabled(False)
        lv.addWidget(self.btn_run)
        lv.addStretch()

    # ── 导入 ──────────────────────────────────────────
    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入银行流水", "",
            "Excel (*.xlsx *.xls);;CSV (*.csv);;All (*)")
        if not path: return

        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".xlsx", ".xls"):
                try:
                    self._df = smart_read_excel(path)
                except SheetChoiceError as e:
                    sheet, ok = QInputDialog.getItem(
                        self, "选择Sheet",
                        f"文件包含 {len(e.sheets)} 个工作表，请选择：",
                        e.sheets, 0, False)
                    if not ok: return
                    self._df = pd.read_excel(path, sheet_name=sheet, dtype=str)
            else:
                self._df = smart_read_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return

        self._current_file = path
        self.lbl_file.setText(
            f"{os.path.basename(path)}\n{len(self._df)} 行 × {len(self._df.columns)} 列")
        self._auto_map(self._df)
        self.btn_run.setEnabled(True)
        self.data_loaded.emit(self._df, path)

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

        mappings_spec = {
            "date":   (["时间","日期","time","date"], None),
            "name":   (["姓名","户名","name","客户名称"], ["对方","对手","查询"]),
            "card":   (["卡号","账号","card","account","账户","查询对象","查询卡号"], ["对方","对手","手机","身份证"]),
            "type":   (["交易摘要","摘要","业务类型","type"], None),
            "amount": (["金额","amount","money","发生额","收支"], None),
            "dc":     (["借贷标志","借贷","收支方向","收付","进出标志"], None),
            "cp":     (["对手","对方名称","对手名称","counter","交易对手"], ["账号","卡号","手机","电话","身份证"]),
            "remark": (["备注","remark","附言","用途","说明","注释"], None),
            "cp_phone":   (["对方手机","对手手机","对方电话","对手电话","对方联系电话","手机号"], None),
            "cp_id":      (["对方身份证","对手身份证","对方证件","对手证件","对方证件号码"], None),
            "cp_account": (["对方账号","对手账号","对方卡号","对手卡号","对方账户"], None),
        }
        for key, (kws, excl) in mappings_spec.items():
            cmb = self._mapping_cmbs[key]
            cmb.clear()
            cmb.addItems([""] + cols)
            m = find_col(kws, excl)
            if m:
                i = cmb.findText(m)
                if i >= 0:
                    cmb.setCurrentIndex(i)

    # ── 执行 ──────────────────────────────────────────
    def _on_run(self):
        mappings = {key: cmb.currentText() for key, cmb in self._mapping_cmbs.items()}
        required = ["date", "card", "type", "amount"]
        if not all(mappings[k] for k in required):
            QMessageBox.information(self, "提示",
                "至少需要选择：日期列、卡号列、交易摘要列、金额列")
            return

        params = {
            "cash_max_days": self.spin_cash.value(),
            "finance_max_days": self.spin_fin.value(),
            "skip_small": self.chk_small.isChecked(),
            "key_dates_raw": self.edit_key_dates.text().strip(),
        }
        bl = self.edit_blacklist.text().strip()
        config = {
            "large_threshold": self.spin_large.value() * 10000,
            "night_start": self.spin_night_start.value(),
            "night_end": self.spin_night_end.value(),
            "blacklist_keywords": [kw.strip() for kw in bl.split(",") if kw.strip()] if bl else [],
        }
        self.run_requested.emit(mappings, params, config)

    def _on_export_report(self):
        self.report_requested.emit()

    # ── 跨软件联动 (G 组) ─────────────────────────────
    def _on_interop_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入话单联动包", "", "案件交换包 (*.json);;All (*)")
        if not path:
            return
        self.interop_import_requested.emit(path)

    def _on_interop_export(self):
        self.interop_export_requested.emit()

    # ── 外部可设置 ────────────────────────────────────
    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)
        self.btn_report.setEnabled(enabled)
        self.btn_interop_export.setEnabled(enabled)

    @property
    def export_btn(self):
        return self.btn_export

    @property
    def df(self):
        return self._df

    @property
    def current_file(self):
        return self._current_file
