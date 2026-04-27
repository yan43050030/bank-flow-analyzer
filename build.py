#!/usr/bin/env python3
"""跨平台打包脚本"""

import os
import sys
import subprocess
import platform
from version import __version__

APP_NAME_CN = "银行流水资金统计"
MAIN_SCRIPT = "fund_analyzer.py"
THEMES_DIR = "ui/themes"


def build():
    print(f"=== {APP_NAME_CN} v{__version__} 打包构建 ===")
    system = platform.system()
    print(f"平台: {system}")

    # 清理
    for d in ["build", "dist"]:
        if os.path.exists(d):
            import shutil
            shutil.rmtree(d)
            print(f"已清理 {d}/")

    # PyInstaller 参数
    add_data = f"--add-data {THEMES_DIR}:{THEMES_DIR}"
    if system == "Windows":
        add_data = f"--add-data {THEMES_DIR};{THEMES_DIR}"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", APP_NAME_CN,
        add_data,
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        MAIN_SCRIPT,
    ]

    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("打包失败!", file=sys.stderr)
        sys.exit(1)

    print(f"\n✅ 打包完成! 输出在 dist/{APP_NAME_CN}/")


if __name__ == "__main__":
    build()
