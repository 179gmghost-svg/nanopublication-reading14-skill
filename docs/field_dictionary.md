# 字段字典与受控词表（nanopublication-reader v1）

本文件是 `schemas/nanopub_schema.json` 的人类可读配套说明，逐字段给出类型、取值域与判定规则。字段定义以 schema 为准；两者不一致时以 schema 为准并视为缺陷。所有规则均对应 `scripts/validate_nanopub.py` 的实际检查，便于他人复核判定依据。

## 1. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `case_id` | string | 是 | 输入 `case.json` 的标识；`--case` 校验时须与原值一致（`CASE_ID_MISMATCH`）。 |
| `status` | enum | 是 | `completed` / `partial` / `indeterminable` / `refused`。 |
| `status_reason` | string \| null | 否 | 非 `completed` 时说明原因与人工接管位置。 |
| `answer` | string \| object \| array \| null | 否 | 对应 `output_contract` 的主答案；结构化答案放对象或数组。 |
| `source_metadata` | object | 是 | 见第 2 节。 |
| `nanopublications` | array | 是 | 每条为一条原子断言及其证据，见第 3 节。 |
| `conflicts` | array | 否 | 原文冲突：`{description, locations[]}`，位置为可回到原文的字符串。 |
| `uncertainties` | array | 是 | 未报告/无法判断项：`{item, reason}`；`reason` 须给出原文依据或缺失理由。 |
| `change_records` | array | 否 | 审计后修复记录：`{change, reason, at}`。 |
| `quality_audit` | object | 否 | `validate_nanopub.py` 报告摘要（`error_count`、`warning_count`、`quote_alignment_rate` 等）。 |
| `nanopub_uri` | string | 否 | 由 `nanopub_builder.py` 写入的确定性 URI，勿手工填写。 |
| `export_summary` | object | 否 | 导出来源与计数，由 `nanopub_builder.py` 写入。 |

## 2. `source_metadata`（溯源元数据）

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `doc_id` | string | 是 | 本次输入的稳定标识（可由文件名或平台给出的 ID 派生）。 |
| `title` | string \| null | 是（可空） | 原文标题；原文未给出写 `null`。 |
| `authors` | array\<string\> | 是（可空） | 作者列表，逐项照原文顺序。 |
| `year` | integer \| string \| null | 是（可空） | 年份；无法确认写 `null`。 |
| `venue_or_publisher` | string \| null | 否 | 期刊或出版方。 |
| `doi_or_identifier` | string \| null | 否 | DOI / arXiv ID / 平台编号；缺失触发 `NO_DOI_OR_ID` 警告。 |
| `version` | string \| null | 否 | 版本或预印本版本。 |
| `source_file` | string | 是 | 实际读取的文件路径或文件名。 |
| `missing_metadata` | array\<string\> | 否 | 上述无法确定的字段名清单；禁止猜测填充。 |

## 3. `nanopublications[]`

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `nanopub_id` | string | 是 | 本题范围内唯一；重复触发 `DUPLICATE_NANOPUB_ID`。 |
| `claim_status` | enum | 是 | 见 3.3。 |
| `assertion` | object | 是 | 见 3.1。 |
| `evidence` | array（≥1） | 是 | 见 3.2；空数组触发 `MISSING_EVIDENCE`。 |

### 3.1 `assertion`

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `statement` | string（≥5 字符） | 是 | 一句话、可独立判真假的断言。超过 260 字符触发 `OVERLY_BROAD_ASSERTION`，含分号或 moreover/furthermore/in addition/whereas/meanwhile/respectively 触发 `COMPOUND_CLAUSE_DETECTED`。 |
| `subject` | string | 是 | 规范化主体，附原文表述；主体方向必须与原文一致。 |
| `predicate` | enum | 是 | 受控关系词，见 3.4。 |
| `object` | string | 是 | 规范化客体或带单位的量值。 |
| `quantitative_value` | string \| number \| null | 否 | 数值本身；量纲另置 `units`。 |
| `units` | string \| null | 否 | 单位，照原文写法。 |
| `conditions_and_scope` | string \| null | 否 | 实验条件与限定范围：体系/材料、温度、pH、电位、模型设定、`n`、统计量（`p`、CI、效应量）等。 |
| `polarity` | enum | 是 | 见 3.5。 |

### 3.2 `evidence[]`

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `quote` | string | 非 `unreported` 时必填 | 最小充分原文片段；须在规范化后仍是`anchored_source.json`的子串，否则 `QUOTE_NOT_FOUND_IN_SOURCE`。超过 600 字符触发 `OVERSIZED_QUOTE`。禁止改写、拼接、翻译。 |
| `evidence_type` | enum | 是 | 见 3.6。 |
| `extraction_method` | enum | 否 | `text_layer` / `ocr` / `visual_inspection` / `table_parse` / `metadata`。 |
| `cited_reference` | string \| null | `cited_prior_work` 时建议填写 | 被引文献编号（如 `[12]`）；缺失触发 `MISSING_CITED_REF`。 |
| `reasoning_note` | string \| null | `indirect_inference` 时建议填写 | 说明由哪些陈述推出该断言。 |
| `location` | object | 是 | 见下。 |

`location` 字段：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `page` | integer \| null | 1 起始页码。 |
| `section` | string \| null | 章节名或 `section_hint`。 |
| `para_id` | string \| null | 形如 `p{page}_b{index}`，须存在于 `anchored_source.json`；与 `page` 不一致时触发 `PAGE_PARA_MISMATCH`。 |
| `figure_or_table` | string \| null | 如 `Figure 3b`、`Table 2`。 |
| `equation` | string \| null | 如 `Eq. (4)`。 |

非 `unreported` 证据必须至少给出 `page`、`para_id`、`figure_or_table` 之一，否则 `MISSING_PROVENANCE_ANCHOR`。

### 3.3 `claim_status` 判定

| 取值 | 判定规则 |
| :--- | :--- |
| `supported` | 输入材料中存在直接或统计证据，断言的范围不超过证据范围。 |
| `partially_supported` | 仅部分条件/子结论有证据，或证据仅覆盖更窄的体系、剂量、时间窗。 |
| `conflicting` | 两处及以上原文位置相互矛盾（如摘要与表格），须同时给出全部锚点并写入 `conflicts`。 |
| `unreported` | 材料明确未报告该指标/条件；`quote` 记录“未报告”表述或留空并写入 `uncertainties`。 |
| `indeterminable` | 材料无法判断（无文本层、图内数值不可读、OCR 低置信等）。 |

### 3.4 `predicate` 受控词表

`increases`、`decreases`、`causes`、`correlates_with`、`outperforms`、`inhibits`、`equals`、`measured_as`、`contradicts`、`associated_with`、`requires`、`other`。

选用规则：先取原文的因果/比较/相关表述，再映射；方向由 `subject`→`object` 决定，禁止反向书写。相关性不得映射为 `causes`；仅比较优劣用 `outperforms`；给出具体数值用 `measured_as`；受控词表无法表达时用 `other` 并在 `conditions_and_scope` 补足语义。

### 3.5 `polarity` 受控词表

`positive`、`negative`、`neutral`、`conditional`、`inconclusive`。方向性结论用 `positive`/`negative`（相对 `subject` 而言）；仅在特定条件下成立用 `conditional`；无方向或方向不明用 `neutral`/`inconclusive`。

### 3.6 `evidence_type` 受控词表与判据

| 取值 | 判据 |
| :--- | :--- |
| `direct_experimental` | 本文自身的一手测量或观测结果。 |
| `statistical_result` | 显式统计检验或统计量（`p`、CI、效应量、回归系数）。 |
| `visual_chart_or_table` | 从表格或图中读出的数值，`extraction_method` 记为 `table_parse` 或 `visual_inspection`。 |
| `indirect_inference` | 由两条及以上陈述推出；必须在 `reasoning_note` 说明推理链。 |
| `cited_prior_work` | 归属于外部参考文献的陈述；必须标注 `cited_reference`，严禁当作本文发现。 |
| `unreported` | 材料中明确缺失。 |

## 4. 去重与标识

`nanopub_builder.py` 以 `case_id | subject | predicate | object | conditions_and_scope`（小写、去首尾空白）的 SHA-256 前 16 位生成 `urn:nanopub:reading14:<digest>`，写入 `nanopub_uri`。相同内容在不同运行中产生相同 URI，便于跨次去重与回溯；同一案例内 `nanopub_id` 仍须唯一。

## 5. 引文对齐的规范化规则

`validate_nanopub.py` 在比对前对文本与引用做统一规范化：折叠所有空白为单空格、去首尾空白、转小写，并把弯引号（`‘ ’ “ ”`）、连字符变体（`– —`）与不换行空格（`U+00A0`）归一。原文若存在跨行连字符断词（`-\n` 后接小写字母），`pdf_anchor_extract.py` 会在段落切分时先修复再写入 `text`。因此引用应直接从 `anchored_source.json` 的 `text` 复制，不要手工重排。

## 6. 交付与自检

```bash
# 完整自检：契约字段、原文对齐、原子性、导出格式
python3 scripts/pdf_anchor_extract.py <input> --out /app/work/anchored_source.json
python3 scripts/validate_nanopub.py --result /app/work/draft_result.json \
  --source /app/work/anchored_source.json --case /input/case.json \
  --schema schemas/nanopub_schema.json --report /app/work/audit_report.json
python3 scripts/nanopub_builder.py --input /app/work/draft_result.json \
  --out-jsonld /app/output/nanopublications.jsonld \
  --out-trig /app/output/nanopublications.trig \
  --out-result /app/output/result.json
```

`validate_nanopub.py` 退出码：`0` 表示无 ERROR，`2` 表示存在 ERROR。ERROR 必须清零后才导出最终结果；WARNING（超长断言、超长引用、页码与段落锚点不一致等）需逐条判断并记录在 `change_records` 或 `uncertainties`。
