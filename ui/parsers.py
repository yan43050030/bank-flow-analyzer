#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据解析工具 — 独立于 UI 框架"""

from datetime import datetime
import pandas as pd


def smart_read_csv(path: str) -> pd.DataFrame:
    """自动检测编码和分隔符读 CSV"""
    for enc in ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"]:
        for sep in [",", "\t", ";", "|"]:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, nrows=5)
                if len(df.columns) > 1:
                    return pd.read_csv(path, encoding=enc, sep=sep, dtype=str)
            except Exception:
                continue
    raise ValueError("无法识别 CSV 编码或分隔符")


def smart_read_excel(path: str, sheet_name: str = None) -> pd.DataFrame:
    """读取 Excel，支持自动选择 sheet"""
    xf = pd.ExcelFile(path)
    sheets = xf.sheet_names
    if sheet_name and sheet_name in sheets:
        return pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    if len(sheets) == 1:
        return pd.read_excel(path, sheet_name=sheets[0], dtype=str)
    # 优先选交易明细/流水 sheet
    for keyword in ["交易明细", "流水", "明细", "交易"]:
        preferred = [s for s in sheets if keyword in s]
        if len(preferred) == 1:
            return pd.read_excel(path, sheet_name=preferred[0], dtype=str)
    # 返回 sheet 列表供 UI 选择
    raise SheetChoiceError(sheets)


class SheetChoiceError(Exception):
    def __init__(self, sheets: list):
        self.sheets = sheets
        super().__init__(f"多 Sheet 需要选择: {sheets}")


def parse_amount(val) -> float:
    """解析金额字符串 → float"""
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(",", "").replace("¥", "").replace("￥", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(val):
    """解析日期 → datetime 或 None"""
    if pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in [
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d%H%M%S", "%Y%m%d",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, errors="raise").to_pydatetime()
    except Exception:
        return None


# 借贷标志 → 方向
_CREDIT_IN = {"进", "借", "贷", "收入", "转入", "汇入", "存入", "入", "credit", "in", "c", "cr"}
_DEBIT_OUT = {"出", "支", "付出", "转出", "汇出", "取出", "out", "debit", "d", "dr"}


def resolve_direction(raw_flag) -> int:
    """借贷标志 → 1=流入, -1=流出, 0=未知"""
    if pd.isna(raw_flag):
        return 0
    s = str(raw_flag).strip()
    if s in _CREDIT_IN:
        return 1
    if s in _DEBIT_OUT:
        return -1
    sl = s.lower()
    if sl in _CREDIT_IN:
        return 1
    if sl in _DEBIT_OUT:
        return -1
    if any(k in s for k in ["进", "入", "存"]):
        return 1
    if any(k in s for k in ["出", "取", "付"]):
        return -1
    return 0
