# INTEROP_SPEC.md — 跨软件联动接口规范

> 本文件是**银行流水分析软件**与**话单分析软件 (Call-record-analyzer)** 之间
> 数据交换的契约。两个软件必须遵守同一份规范。
>
> CRITICAL: 修改本规范前必读 [DESIGN_DECISIONS.md#跨软件联动](DESIGN_DECISIONS.md)。
> 这是**跨仓库契约**——单方面改动会导致两个软件对不上。

## 1. 文件格式

- 格式：单个 **UTF-8 编码的 JSON 文件**（不是 CSV / SQLite）
- schema 标识：顶层字段 `"schema": "case-interop-v1"` —— 读取方**必须先校验**
- 扩展名：约定 `.json`（如 `案件交换包_20240601_120000.json`）

## 2. 完整结构

```json
{
  "schema": "case-interop-v1",
  "exported_by": "通话记录分析系统",          // 或 "银行流水分析系统"
  "exported_at": "2024-06-01T12:00:00",      // ISO 8601
  "case_name": "张三受贿案",

  "entities": [                              // 实体（人）—— 两侧都可补充
    {
      "id": "E1",
      "name": "张三",
      "id_card": "110101199001011234",       // 身份证号，可空
      "phones": ["13800001111"],             // 手机号数组
      "accounts": ["6222021234567890"],      // 银行卡号数组
      "role": "目标人",                       // 目标人/对手/同行人 等
      "note": ""
    }
  ],

  "call_events": [...],                      // 通话事件 —— 话单工具填充
  "sms_events": [...],                       // 短信事件 —— 话单工具填充
  "transaction_events": [...],               // 交易事件 —— 银行工具填充
  "analysis_summary": {}                     // 各自关键发现摘要，自由结构
}
```

## 3. transaction_events —— 银行工具必须填充的部分

银行流水工具负责写入这个数组。每条交易：

```json
{
  "time": "2024-01-01T10:30:00",        // 必填，ISO 8601，交易发生时间
  "amount": 50000,                       // 金额（数字，元；带符号：正入负出）
  "from_account": "6222021234567890",    // 付款方账号，可空
  "to_account": "6228480000000000",      // 收款方账号，可空
  "counterparty": "李四",                 // 交易对手姓名，可空
  "counterparty_phone": "13900002222",   // ⭐ 交易对手手机号 —— 关联话单的关键桥梁
  "counterparty_id_card": "",            // 交易对手身份证，可空（二级关联键）
  "channel": "手机银行",                  // 渠道，可空
  "note": ""
}
```

**字段优先级**：`time` 必填；`counterparty_phone` 强烈建议填（和话单对齐"同一个人"的主键）；其余尽量填。

> 话单工具的 `analyze_call_transaction_correlation` 当前只读 `time / amount /
> counterparty / counterparty_phone` 四个字段。银行侧多填的字段不会报错，
> 话单工具忽略即可（未知字段宽容原则）。

## 4. call_events / sms_events —— 话单工具填充

银行工具**只读不写**这两个数组。结构（仅供银行侧交叉分析参考）：

```json
// call_events 单条
{
  "time": "2024-01-01T10:00:00",
  "self": "13800001111",      // 本机号码（被分析人）
  "other": "13900002222",     // 对方号码
  "duration_sec": 60,         // 通话时长（秒），整数
  "type": "呼出",              // 呼出/呼入/未接
  "location": "北京海淀中关村基站"
}
// sms_events 单条
{
  "time": "2024-01-01T10:05:00",
  "self": "13800001111",
  "other": "13900002222",
  "direction": "发送"          // 发送/接收
}
```

## 5. 关联键（怎么把"同一个人"对上）

按优先级三级匹配：

1. **手机号（主键）**：银行交易 `counterparty_phone` ↔ 话单 `other`/`self`/`phones`
   —— 最可靠，银行卡都绑手机号
2. **身份证号（强二级键）**：`entities[].id_card` 之间精确匹配
3. **姓名（弱辅助键）**：仅在前两者都缺失时用，需人工复核（重名风险）

→ 银行侧尽量带 `counterparty_phone`，没有手机号时退而求其次带 `counterparty_id_card`。

## 6. 联动方向 —— 双向

```
话单工具  ──导出──►  交换包.json（含 entities + call_events + sms_events）
                          │
银行工具  ──读取──►  补填 transaction_events ──导出──►  交换包.json（完整）
                          │
话单工具  ──导入──►  做「通话→转账」时序交叉分析
```

反向同理。**关键规则**：谁导出谁就填自己那部分数组，对方的数组留空 `[]`，**不要删字段**。

## 7. 交叉分析 —— 各做各的视角

时序交叉分析两边各自做、各保留本工具视角：

- **话单工具视角**：「通话后 N 小时内的转账」（已实现 `analyze_call_transaction_correlation`）
- **银行工具视角**：「大额转账前 N 小时的密集通话」（本仓库 `interop.analyze_transfer_call_correlation`）
  —— 对受贿案"先沟通→后送钱"的铁证模式更直接

两者结论应一致，UI / 报告侧重不同。

## 8. 银行侧实现（本仓库 `interop.py`）

| 功能 | 函数 |
|------|------|
| 读取 + schema 校验 | `load_interop_package(path)` |
| 写出 | `save_interop_package(pkg, path)` |
| 流水 → transaction_events | `reports_to_transaction_events(reports)` |
| 构造导出包（保留对方数组） | `build_export_package(reports, case_name, base_package)` |
| 交叉分析（银行视角） | `analyze_transfer_call_correlation(tx_events, call_events, ...)` |

校验失败抛 `InteropError`（不静默）。

## 9. 版本演进约定

- 当前版本 `case-interop-v1`
- 未来加字段：**只增不改**，旧字段语义不变，读取方对未知字段宽容（忽略）
- 破坏性变更才升 `case-interop-v2`，并**在两个软件同步**
- `interop.py` 的 `SCHEMA_ID` 常量是唯一真相来源
