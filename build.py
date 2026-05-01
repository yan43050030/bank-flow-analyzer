#!/usr/bin/env python3
"""跨平台打包脚本 — PySide6"""

import os, sys, shutil, subprocess, platform
from version import __version__

APP_NAME = "BankFlowAnalyzer"
APP_NAME_CN = "银行流水资金统计"
MAIN_SCRIPT = "fund_analyzer.py"


def build():
    print(f"=== {APP_NAME_CN} v{__version__} 打包构建 ===")
    system = platform.system()
    print(f"平台: {system}")

    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"已清理 {d}/")

    sep = ";" if system == "Windows" else ":"
    add_data = f"ui/themes{sep}ui/themes"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--add-data", add_data,
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PyQt5",
        MAIN_SCRIPT,
    ]

    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("打包失败!", file=sys.stderr)
        sys.exit(1)

    dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", APP_NAME)
    print(f"\nBuild complete! Output: {dist_dir}/")
    print(f"  Executable: {dist_dir}/{APP_NAME}.exe")


if __name__ == "__main__":
    build()
