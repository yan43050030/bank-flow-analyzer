#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨软件联动 — case-interop-v1 JSON 交换包

与话单分析软件 (Call-record-analyzer) 的数据交换接口。
完整 schema 规范见 docs/INTEROP_SPEC.md。

CRITICAL: 修改本模块前必读 docs/INTEROP_SPEC.md + docs/DESIGN_DECISIONS.md#跨软件联动
  - schema 标识 "case-interop-v1" 不能改
  - 字段只增不改，旧字段语义不变；读取方对未知字段宽容（忽略）
  - 破坏性变更才升 case-interop-v2，且必须与话单工具同步
  - 导出时：只填自己那部分数组（transaction_events），对方数组留空 []，不要删字段
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional


# ── schema 常量（CRITICAL: 不要改）──
SCHEMA_ID = "case-interop-v1"
EXPORTER_NAME = "银行流水分析系统"


class InteropError(Exception):
    """交换包格式 / schema 校验错误"""


@dataclass
class InteropPackage:
    """case-interop-v1 交换包的内存表示"""
    case_name: str = ""
    exported_by: str = ""
    exported_at: str = ""
    entities: list = field(default_factory=list)            # 实体（人）
    call_events: list = field(default_factory=list)         # 通话事件 — 话单工具填
    sms_events: list = field(default_factory=list)          # 短信事件 — 话单工具填
    transaction_events: list = field(default_factory=list)  # 交易事件 — 银行工具填
    analysis_summary: dict = field(default_factory=dict)    # 各自关键发现摘要


# ═══════════════════════════════════════════════════════════
# 读 / 写
# ═══════════════════════════════════════════════════════════

def load_interop_package(path: str) -> InteropPackage:
    """读取并校验交换包。schema 不匹配 → 抛 InteropError（不静默）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise InteropError(f"JSON 解析失败: {e}") from e
    except OSError as e:
        raise InteropError(f"文件读取失败: {e}") from e

    if not isinstance(data, dict):
        raise InteropError("交换包根节点必须是 JSON 对象")

    schema = data.get("schema")
    if schema != SCHEMA_ID:
        raise InteropError(
            f"schema 不匹配：期望 {SCHEMA_ID!r}，实际 {schema!r}。"
            f"可能不是案件交换包，或版本不兼容。")

    return InteropPackage(
        case_name=data.get("case_name", "") or "",
        exported_by=data.get("exported_by", "") or "",
        exported_at=data.get("exported_at", "") or "",
        entities=data.get("entities") or [],
        call_events=data.get("call_events") or [],
        sms_events=data.get("sms_events") or [],
        transaction_events=data.get("transaction_events") or [],
        analysis_summary=data.get("analysis_summary") or {},
    )


def save_interop_package(pkg: InteropPackage, path: str) -> None:
    """写出交换包为 UTF-8 JSON（缩进 2，保留中文）。"""
    data = {
        "schema": SCHEMA_ID,
        "exported_by": EXPORTER_NAME,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "case_name": pkg.case_name,
        "entities": pkg.entities,
        "call_events": pkg.call_events,
        "sms_events": pkg.sms_events,
        "transaction_events": pkg.transaction_events,
        "analysis_summary": pkg.analysis_summary,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
# 银行侧：把分析结果填进 transaction_events
# ═══════════════════════════════════════════════════════════

def reports_to_transaction_events(reports: list) -> list:
    """把 CardReport 列表的所有交易转成 transaction_events 数组。

    每条交易遵循 docs/INTEROP_SPEC.md 的 transaction_events schema。
    time 必填；counterparty_phone 是关联话单的主键，尽量带上。
    """
    events = []
    for r in reports:
        for t in r.all_transactions:
            cp_acct = (getattr(t, "counterparty_account", "") or "").strip()
            outflow = t.amount < 0
            events.append({
                "time": t.date.isoformat(timespec="seconds"),
                "amount": round(t.amount, 2),          # 带符号：正入负出
                "from_account": r.card if outflow else cp_acct,
                "to_account": cp_acct if outflow else r.card,
                "counterparty": (t.counterparty or "").strip(),
                "counterparty_phone": (getattr(t, "counterparty_phone", "") or "").strip(),
                "counterparty_id_card": (getattr(t, "counterparty_id_card", "") or "").strip(),
                "channel": (getattr(t, "channel", "") or "").strip(),
                "note": (t.remark or "").strip(),
            })
    return events


def _bank_entities(existing: list, reports: list) -> list:
    """在已有 entities 基础上补充银行侧已知实体（按卡聚合）。

    匹配既有实体：账号包含 或 姓名相同 → 合并账号；否则新增。
    银行新增实体 id 用 'B' 前缀，避免与话单工具的 'E' 前缀冲突。
    """
    entities = [dict(e) for e in existing]  # 深拷贝顶层，避免改到入参
    for r in reports:
        holder_id = (getattr(r, "holder_id_card", "") or "").strip()
        match = None
        for e in entities:
            # 关联键优先级：身份证 > 账号 > 姓名（与 INTEROP_SPEC.md 一致）
            if holder_id and e.get("id_card") == holder_id:
                match = e
                break
            if r.card and r.card in (e.get("accounts") or []):
                match = e
                break
            if r.name and e.get("name") == r.name:
                match = e
                break
        if match is not None:
            accts = match.setdefault("accounts", [])
            if r.card and r.card not in accts:
                accts.append(r.card)
            if holder_id and not match.get("id_card"):
                match["id_card"] = holder_id
        else:
            entities.append({
                "id": f"B{len(entities) + 1}",
                "name": r.name or "",
                "id_card": holder_id,
                "phones": [],
                "accounts": [r.card] if r.card else [],
                "role": "对象",
                "note": "银行流水分析系统补充",
            })
    return entities


def _bank_summary(reports: list) -> dict:
    """银行侧关键发现摘要，写进 analysis_summary['银行流水分析']。"""
    return {
        "卡数": len(reports),
        "总资金量": round(sum(getattr(r, "fund_size", 0) for r in reports), 2),
        "高可疑卡": [r.card for r in reports
                     if "高" in (getattr(r, "suspicion_label", "") or "")],
        "疑似代持卡": [r.card for r in reports
                       if "疑似" in (getattr(r, "nominee_label", "") or "")
                       or "高度" in (getattr(r, "nominee_label", "") or "")],
    }


def build_export_package(reports: list, case_name: str = "",
                         base_package: Optional[InteropPackage] = None
                         ) -> InteropPackage:
    """构造导出用交换包。

    base_package：若提供（之前从话单工具导入的包），保留其
      entities / call_events / sms_events，只补银行侧的 transaction_events。
    若不提供，则新建一个只含银行数据的包。
    """
    pkg = base_package or InteropPackage()
    if case_name:
        pkg.case_name = case_name
    pkg.transaction_events = reports_to_transaction_events(reports)
    pkg.entities = _bank_entities(pkg.entities, reports)
    if not isinstance(pkg.analysis_summary, dict):
        pkg.analysis_summary = {}
    summary = _bank_summary(reports)

    # G3 综合关联评分：若交换包已含通话数据，把核心关系写进摘要
    if pkg.call_events:
        rels = analyze_relationship_strength(
            pkg.transaction_events, pkg.call_events, pkg.sms_events)
        core = [r for r in rels if r["is_core"]]
        summary["综合关联评分"] = {
            "核心关系数": len(core),
            "核心关系": [
                {"手机号": r["phone"],
                 "对手": r["counterparty_names"],
                 "综合分": r["total_score"],
                 "资金分": r["fund_score"],
                 "通讯分": r["comm_score"]}
                for r in core[:20]
            ],
        }

    pkg.analysis_summary["银行流水分析"] = summary
    return pkg


# ═══════════════════════════════════════════════════════════
# 交叉分析（银行视角）：大额转账前的通话
# ═══════════════════════════════════════════════════════════

def _parse_iso(s) -> Optional[datetime]:
    """解析 ISO 8601 时间字符串，失败返回 None。"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).strip())
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def analyze_transfer_call_correlation(
        transaction_events: list,
        call_events: list,
        window_hours: float = 24.0,
        large_threshold: float = 50000.0) -> list:
    """银行视角交叉分析：大额转账「之前」N 小时内的通话。

    识别"先密集通话 → 随后大额转账"模式 —— 受贿/行贿"先沟通后送钱"的
    典型铁证。关联键：交易 counterparty_phone == 通话 other 或 self。

    参数:
      transaction_events : 交易事件数组（本工具或交换包提供）
      call_events        : 通话事件数组（话单工具提供）
      window_hours       : 转账前回看窗口（小时）
      large_threshold    : 只分析金额 ≥ 此值的交易

    返回（按通话次数降序）:
      [{transaction, calls_before, call_count, total_duration_sec}, ...]
    """
    # 预解析通话时间
    parsed_calls = []
    for c in call_events:
        ct = _parse_iso(c.get("time"))
        if ct is not None:
            parsed_calls.append((ct, c))

    results = []
    for tx in transaction_events:
        if abs(_to_float(tx.get("amount"))) < large_threshold:
            continue
        phone = (tx.get("counterparty_phone") or "").strip()
        if not phone:
            continue   # 无手机号无法关联话单
        tx_time = _parse_iso(tx.get("time"))
        if tx_time is None:
            continue
        window_start = tx_time - timedelta(hours=window_hours)

        related = []
        for ct, c in parsed_calls:
            other = (c.get("other") or "").strip()
            self_ = (c.get("self") or "").strip()
            if phone != other and phone != self_:
                continue
            if window_start <= ct <= tx_time:
                related.append(c)

        if related:
            related.sort(key=lambda c: str(c.get("time", "")))
            results.append({
                "transaction": tx,
                "calls_before": related,
                "call_count": len(related),
                "total_duration_sec": sum(
                    _to_int(c.get("duration_sec")) for c in related),
            })

    results.sort(key=lambda r: (r["call_count"], r["total_duration_sec"]),
                 reverse=True)
    return results


# ═══════════════════════════════════════════════════════════
# 综合关联评分 (G3)
# ═══════════════════════════════════════════════════════════

def analyze_relationship_strength(
        transaction_events: list,
        call_events: list,
        sms_events: list = None) -> list:
    """G3 综合关联评分：资金往来 + 通讯往来 → 核心关系识别。

    CRITICAL: 评分常量是经验启发值（非法定/非精算），可调；
    详见 docs/DESIGN_DECISIONS.md#综合关联评分g3。

    按手机号聚合：交易的 counterparty_phone ↔ 通话/短信的 other。
    "核心关系" = 资金维度和通讯维度都密切 —— 受贿/共谋核心圈的最强信号
    （只资金密切可能是正常业务往来，只通讯密切可能是普通社交，二者叠加
    才是值得重点核查的关系）。

    返回（核心关系优先、再按综合分降序）:
      [{phone, counterparty_names, tx_count, tx_amount, net_flow,
        call_count, call_duration_sec, sms_count,
        fund_score, comm_score, total_score, is_core, label}, ...]
    """
    sms_events = sms_events or []

    # 按手机号聚合资金往来
    fund = {}
    for tx in transaction_events:
        phone = (tx.get("counterparty_phone") or "").strip()
        if not phone:
            continue
        rec = fund.setdefault(phone, {"count": 0, "amount": 0.0,
                                      "net": 0.0, "names": set()})
        amt = _to_float(tx.get("amount"))
        rec["count"] += 1
        rec["amount"] += abs(amt)
        rec["net"] += amt
        name = (tx.get("counterparty") or "").strip()
        if name:
            rec["names"].add(name)

    # 按手机号聚合通讯往来（话单的 other = 对方）
    comm = {}
    for c in call_events:
        phone = (c.get("other") or "").strip()
        if not phone:
            continue
        rec = comm.setdefault(phone, {"calls": 0, "duration": 0, "sms": 0})
        rec["calls"] += 1
        rec["duration"] += _to_int(c.get("duration_sec"))
    for s in sms_events:
        phone = (s.get("other") or "").strip()
        if not phone:
            continue
        rec = comm.setdefault(phone, {"calls": 0, "duration": 0, "sms": 0})
        rec["sms"] += 1

    results = []
    for phone in set(fund) | set(comm):
        f = fund.get(phone, {"count": 0, "amount": 0.0, "net": 0.0, "names": set()})
        m = comm.get(phone, {"calls": 0, "duration": 0, "sms": 0})

        # 资金分量 (0-50)：笔数 0-25 + 金额 0-25
        fund_score = round(
            min(25.0, f["count"] * 5.0)
            + min(25.0, f["amount"] / 200000.0 * 25.0), 1)

        # 通讯分量 (0-50)：通话次数 0-30 + 时长 0-15 + 短信 0-5
        comm_score = round(
            min(30.0, m["calls"] * 3.0)
            + min(15.0, m["duration"] / 3600.0 * 15.0)
            + min(5.0, m["sms"] * 1.0), 1)

        total = round(fund_score + comm_score, 1)
        # 核心关系：两个维度都达到"有意义"门槛（各 ≥15）
        is_core = fund_score >= 15.0 and comm_score >= 15.0
        if is_core:
            label = "🔴 核心关系"
        elif total >= 50.0:
            label = "🟡 密切"
        else:
            label = "🟢 一般"

        results.append({
            "phone": phone,
            "counterparty_names": sorted(f["names"]),
            "tx_count": f["count"],
            "tx_amount": round(f["amount"], 2),
            "net_flow": round(f["net"], 2),
            "call_count": m["calls"],
            "call_duration_sec": m["duration"],
            "sms_count": m["sms"],
            "fund_score": fund_score,
            "comm_score": comm_score,
            "total_score": total,
            "is_core": is_core,
            "label": label,
        })

    results.sort(key=lambda r: (r["is_core"], r["total_score"]), reverse=True)
    return results
