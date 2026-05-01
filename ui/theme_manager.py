#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主题管理器 — 通过 JSON 文件定义多套主题，运行时热切换"""

import json
import os

THEMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")


class Theme:
    def __init__(self, data: dict):
        self.name = data["name"]
        self.description = data.get("description", "")
        self.colors = data["colors"]
        # 设置属性访问
        for k, v in self.colors.items():
            setattr(self, k, v)
        self._data = data

    def to_stylesheet(self) -> str:
        """生成 QSS 样式表"""
        c = self.colors
        return f"""
            QMainWindow {{
                background: {c['window_bg']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {c['card_border']};
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
                color: {c['group_title']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 6px;
                color: {c['group_title']};
            }}
            QPushButton {{
                background: {c['btn_bg']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 6px 14px;
                color: {c['text_primary']};
            }}
            QPushButton:hover {{
                background: {c['btn_hover']};
                border-color: {c['primary']};
            }}
            QPushButton:disabled {{
                color: {c['text_placeholder']};
                background: {c['window_bg']};
                border-color: {c['border']};
            }}
            QPushButton#btnRun {{
                background: {c['primary']};
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
                border: none;
            }}
            QPushButton#btnRun:hover {{
                background: {c['primary_hover']};
            }}
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
                padding: 5px 8px;
                border: 1px solid {c['border']};
                border-radius: 4px;
                background: {c['input_bg']};
                color: {c['text_primary']};
            }}
            QComboBox QAbstractItemView {{
                background: {c['input_bg']};
                color: {c['text_primary']};
                selection-background-color: {c['primary']};
                selection-color: white;
                border: 1px solid {c['border']};
                outline: none;
            }}
            QTableWidget {{
                border: 1px solid {c['border']};
                gridline-color: {c['card_border']};
                background: {c['table_bg']};
                color: {c['text_primary']};
                alternate-background-color: {c['table_alt']};
            }}
            QTableWidget::item {{
                padding: 4px 8px;
            }}
            QHeaderView::section {{
                background: {c['header_bg']};
                padding: 6px 8px;
                border: 1px solid {c['border']};
                font-weight: bold;
                color: {c['text_primary']};
            }}
            QTextEdit, QPlainTextEdit {{
                border: 1px solid {c['border']};
                border-radius: 4px;
                background: {c['input_bg']};
                color: {c['text_primary']};
            }}
            QLabel {{
                color: {c['text_primary']};
            }}
            QCheckBox {{
                padding: 4px 0;
                color: {c['text_primary']};
            }}
            QStatusBar {{
                background: {c['header_bg']};
                color: {c['text_secondary']};
            }}
            QTabWidget::pane {{
                border: 1px solid {c['border']};
                border-radius: 4px;
                background: {c['card_bg']};
            }}
            QTabBar::tab {{
                padding: 8px 16px;
                background: {c['window_bg']};
                border: 1px solid {c['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: {c['text_secondary']};
            }}
            QTabBar::tab:selected {{
                background: {c['card_bg']};
                border-bottom: 2px solid {c['primary']};
                color: {c['text_primary']};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QFrame#cardFrame {{
                background: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 8px;
                padding: 12px;
            }}
        """


class ThemeManager:
    _instance = None
    _themes: dict = {}
    _current: Theme = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_themes()
        return cls._instance

    def _load_themes(self):
        if not os.path.isdir(THEMES_DIR):
            return
        for fname in sorted(os.listdir(THEMES_DIR)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(THEMES_DIR, fname), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    theme = Theme(data)
                    self._themes[theme.name] = theme
                except Exception:
                    pass
        # 默认 light
        self._current = self._themes.get("Light", list(self._themes.values())[0] if self._themes else None)

    @property
    def current(self) -> Theme:
        return self._current

    @property
    def theme_names(self) -> list:
        return list(self._themes.keys())

    def get_theme(self, name: str) -> Theme:
        return self._themes.get(name)

    def set_theme(self, name: str):
        if name in self._themes:
            self._current = self._themes[name]

    def get_stylesheet(self) -> str:
        if self._current:
            return self._current.to_stylesheet()
        return ""

    def get_color(self, key: str, default: str = "#000000") -> str:
        if self._current and hasattr(self._current, key):
            return getattr(self._current, key)
        return default
