#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志 (C3) — 办案程序合法性证据

记录每次导入/分析/导出/阈值修改等操作的元信息（不含原始流水内容）。
日志为 JSONL append-only 格式，可作为"工具如何被使用过"的程序证据材料。

CRITICAL: 修改前必读 docs/DESIGN_DECISIONS.md#审计日志c3
  - 仅追加，永不修改/删除已有日志（程序合法性的基本要求）
  - 默认存 ~/.bank-flow-analyzer/audit.log，不入 Git
    （.gitignore 已用 *.log 兜底）
  - 只记元信息（路径、笔数、参数），不记原始流水内容 —— 数据隐私
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_LOG_DIR = Path.home() / ".bank-flow-analyzer"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "audit.log"


class AuditLogger:
    """JSONL append-only 审计日志"""

    def __init__(self, log_file: Optional[str] = None):
        self.log_file = Path(log_file) if log_file else DEFAULT_LOG_FILE
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 父目录创建失败（极少见，如只读环境）—— 仍允许实例化，写入时再失败
            pass

    def log(self, operation: str, **details) -> None:
        """追加一条审计日志。details 应只含元信息，不要传原始流水/敏感内容。"""
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "op": operation,
            **details,
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # 写入失败不应阻塞主流程（如磁盘满），但调用方仍可以处理
            pass

    def read_all(self) -> list:
        """读取全部日志条目。文件不存在或行损坏会被宽容处理。"""
        if not self.log_file.exists():
            return []
        entries = []
        try:
            with open(self.log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        # 损坏行跳过，不影响其余日志的可读性
                        pass
        except OSError:
            pass
        return entries

    def export(self, target_path: str) -> int:
        """导出审计日志到指定路径（供法庭/纪委证据材料用）。

        返回导出的条目数。文件不存在或为空时返回 0。
        """
        if not self.log_file.exists():
            return 0
        shutil.copy2(self.log_file, target_path)
        return sum(1 for _ in open(target_path, encoding="utf-8"))
