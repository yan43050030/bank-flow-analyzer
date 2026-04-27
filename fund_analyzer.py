#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
银行流水资金统计工具 v2.0
纯本地运行，零联网，数据不外泄
"""

import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from version import APP_NAME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
