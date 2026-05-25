#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据清洗与合并 (v5.1)

把多源 Transaction 列表归一化为统一表格行，按时间升序。
配合 B1 分析池：用户可以导入多家银行的不同格式流水 → 合并清洗 →
导出统一格式的 xlsx，供下游核查、二次分析或其他工具使用。

CRITICAL: MERGED_COLUMNS 是对外契约——下游可能编脚本依赖列顺序。
新增字段只能加到末尾，不要改名或调整顺序。
"""


# 标准合并表的列定义（顺序固定）
MERGED_COLUMNS = [
    "日期", "卡号", "姓名", "持卡人身份证",
    "交易类型", "金额",
    "对手姓名", "对手账号", "对手手机号", "对手身份证",
    "渠道", "备注", "数据来源",
]


def transactions_to_rows(transactions: list) -> list:
    """把 Transaction 列表归一化为字典行（按时间升序）。

    - 金额带符号（正入负出）—— 与 Transaction.amount 一致
    - 时间格式 ISO 8601 局部时间（YYYY-MM-DD HH:MM:SS）
    - 字段缺失统一填空串
    - 无 pandas 依赖，纯算法可独立测试

    返回的字典 key 与 MERGED_COLUMNS 顺序一致，便于下游写表。
    """
    sorted_txs = sorted(transactions, key=lambda t: t.date)
    rows = []
    for t in sorted_txs:
        rows.append({
            "日期": t.date.strftime("%Y-%m-%d %H:%M:%S"),
            "卡号": t.card or "",
            "姓名": t.name or "",
            "持卡人身份证": (t.holder_id_card or "").strip(),
            "交易类型": t.raw_type or "",
            "金额": round(t.amount, 2),
            "对手姓名": (t.counterparty or "").strip(),
            "对手账号": (t.counterparty_account or "").strip(),
            "对手手机号": (t.counterparty_phone or "").strip(),
            "对手身份证": (t.counterparty_id_card or "").strip(),
            "渠道": (t.channel or "").strip(),
            "备注": (t.remark or "").strip(),
            "数据来源": (t.source or "").strip(),
        })
    return rows
