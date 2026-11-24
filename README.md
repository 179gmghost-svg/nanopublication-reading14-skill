# Nanopublication Scientific Reading Skill (`nanopublication-reader`)

> 面向 Bohrium Product Arena **“阅读14｜Nanopublication（科研阅读：回答问题，也给出依据）”** 赛题的可复用 Harbor Skill 实现。

## 1. 核心设计思路

针对科研阅读中常见的四大痛点，本 Skill 通过 **“六阶段工作流 + 确定性脚本校验 + 标准 Nanopublication 四图导出”** 提供可核验的质量增益：

1. **拆得细（Atomic Assertion Decomposition）**：强制将复合结论拆解为单一、可独立验证的原子断言（`subject` / `predicate` / `object` / `conditions_and_scope` / `polarity`），并通过规则检测未拆分的复合句与超长断言。
2. **对得上（Minimal Sufficient Evidence Binding）**：每条断言绑定最小充分原文证据片段（`quote`）及精确位置锚点（`page`、`section`、`para_id`、`figure_or_table`、`equation`），并严格区分直接实验证据、统计结果、图表证据、间接推论与**引用前人工作（`cited_prior_work`）**。
3. **追得回（End-to-End Provenance Chain）**：完整记录论文标题、作者、年份、DOI/标识符、版本、文件路径，并为每条断言生成基于内容的确定性 SHA-256 URI，支持双向回溯与去重。
4. **读得懂（Machine-Readable Export & QC）**：严格遵循 `schemas/nanopub_schema.json`，并自动导出标准 W3C/Nanopublication 四图模型（`head` / `assertion` / `provenance` / `pubinfo`）的 **JSON-LD** 与 **RDF TriG** 文件，下游程序可直接解析。

## 2. 目录结构

```text
nanopub-skill/
├── SKILL.md                         # Skill 主定义文件（Harbor 入口）
├── README.md                        # 使用说明、方法论与自检指南
├── GITHUB_URL.txt                   # 公开仓库链接（第一行仓库地址，第二行作品入口 SKILL.md）
├── docs/
│   └── field_dictionary.md          # 字段字典、受控词表与判定规则（与 schema 一一对应）
├── schemas/
│   └── nanopub_schema.json          # 输出 JSON Schema 规范
├── scripts/
│   ├── pdf_anchor_extract.py        # PDF/文本页码-章节-段落-图表锚点提取工具
│   ├── validate_nanopub.py          # 自动化质量审查与原文引用对齐校验脚本
│   └── nanopub_builder.py           # Nanopublication JSON-LD / TriG 生成与汇总脚本
└── examples/
    ├── sample_input_case.json       # 最小示意输入（仅作示例，非正式评测案例）
    ├── sample_source_excerpt.txt    # 最小示意文献片段（仅作示例）
    └── sample_output_result.json    # 示意输出结果（由脚本实测生成）
```

## 3. 依赖与运行环境

- **Python 版本**：Python 3.9+（核心校验与导出脚本 `validate_nanopub.py`、`nanopub_builder.py` **零第三方依赖**，仅使用 Python 标准库）。
- **PDF 解析依赖（可选，按可用性自动降级）**：`pdf_anchor_extract.py` 依次尝试 `pymupdf (fitz)` -> `pypdf` -> `pdfplumber` -> Poppler `pdftotext`，适配 Harbor 内置 `scientific-python` / `pdf-text-tool` 环境；某后端只返回空白（典型为无文本层扫描件）时自动尝试下一后端，并在 `extraction_backend` 与 `needs_ocr_review` 中如实记录。

## 4. 快速调用与本地自检

以下命令假定 `SKILL_DIR` 为本目录（即 `SKILL.md` 所在目录）。Harbor 运行时 Skill 安装在 `/skills/weekly-skill`，工作目录为 `/app/work`，因此必须以绝对路径调用脚本：

```bash
SKILL_DIR=/skills/weekly-skill

# 1. 提取带页码与段落锚点的文本索引
python3 "$SKILL_DIR/scripts/pdf_anchor_extract.py" \
  /input/paper.pdf \
  --out /app/work/anchored_source.json

# 2. 对草稿结果执行自动质量审计（原子性、原文对齐、来源完整性、case 契约与不确定性）
python3 "$SKILL_DIR/scripts/validate_nanopub.py" \
  --result /app/work/draft_result.json \
  --source /app/work/anchored_source.json \
  --case /input/case.json \
  --schema "$SKILL_DIR/schemas/nanopub_schema.json" \
  --report /app/work/audit_report.json

# 3. 构建标准 Nanopublication JSON-LD 与 RDF TriG，并输出最终 result.json
python3 "$SKILL_DIR/scripts/nanopub_builder.py" \
  --input /app/work/draft_result.json \
  --out-jsonld /app/output/nanopublications.jsonld \
  --out-trig /app/output/nanopublications.trig \
  --out-result /app/output/result.json
```

本地自检可把上述 `/input`、`/app/work`、`/app/output` 换成仓库内路径，并以 `examples/sample_input_case.json` 充当 `--case`：

```bash
python3 scripts/pdf_anchor_extract.py examples/sample_source_excerpt.txt --out /tmp/anchored_source.json
python3 scripts/validate_nanopub.py --result examples/sample_output_result.json \
  --source /tmp/anchored_source.json --case examples/sample_input_case.json \
  --schema schemas/nanopub_schema.json --report /tmp/audit_report.json
python3 scripts/nanopub_builder.py --input examples/sample_output_result.json \
  --out-jsonld /tmp/nanopublications.jsonld --out-trig /tmp/nanopublications.trig \
  --out-result /tmp/result.json
```

2026-11-23 的自检结果：审计 `0 error / 0 warning`，原文引用对齐 `4/4`，两页 PDF 经 `pdftotext` 后端成功提取 6 个段落并正确标记页码。该结果仅验证脚本可运行，不代表任何正式案例成绩。

## 5. 适用边界与限制

- **扫描件与复杂多栏图注**：纯文本提取无法读取无文字层的扫描 PDF 或柱状图内部未标注数值；此时 `SKILL.md` 指示 Agent 调用平台 `pdf-render-tool` / `ocr-tool` 并在 `extraction_method` 中显式标注，无法准确读数时标记为 `indeterminable`。
- **复合断言启发式检查**：`validate_nanopub.py` 对超长断言和多从句连接词发出 `WARNING` 提示人工或 Agent 二次复核，但不会误杀确实需要条件限定的单条断言。
- **Harbor 部署方式**：将本目录内容直接放入 `/app/submission/`（确保 `SKILL.md` 位于 `/app/submission/SKILL.md`，无符号链接，总大小远小于 2MB 上限）。

## 6. 交付限制与变更记录

本题 Skill 资源上限为 50 个 UTF-8 文本文件、单文件 500KB、合计 2MB，且不允许符号链接。当前提交含 11 个 UTF-8 文本文件（无 BOM）、合计 74,380 字节、单文件最大 15,792 字节，无符号链接，均在限制之内。

2026-11-23 对照赛题与 Harbor 技术提交约定完成的适配：

1. `SKILL.md` 改为以 `SKILL_DIR` 绝对路径调用脚本，避免工作目录为 `/app/work` 时 `scripts/...` 解析失败；预算表述统一为 64 次模型请求 / 900 秒。
2. `validate_nanopub.py` 新增 `--case`：校验 `case_id` 与 `output_contract` 必需字段，并检查 `page` 与 `para_id` 的页码一致性；审计报告的 `contract_fields` 记录所检查的字段清单。
3. `pdf_anchor_extract.py` 新增 Poppler `pdftotext` 后备后端，并跳过仅返回空白的后端，使无文本层扫描件能被标记为 `needs_ocr_review` 而非静默产出空索引。
4. `schemas/nanopub_schema.json` 补充可选的 `change_records` 与 `quality_audit` 字段，对应 Harbor 约定的“变更记录”和审计摘要。
5. `examples/sample_output_result.json` 增补自检产生的审计摘要，并保留“合成示例、非正式成绩”标注。
6. `nanopub_builder.py` 不再输出空值：JSON-LD 中删除 `null` 字段，TriG 中 `page` 改为 `xsd:integer` 字面量且仅在确有页码时输出，并补出 `figureOrTable`、`citedReference`、`equation`；避免下游解析到 `"None"` 这类伪值。
7. 新增 `docs/field_dictionary.md`：逐字段给出类型、必填性与取值域，并把 `claim_status`、`evidence_type`、`polarity`、`predicate` 的判定规则、引文对齐的规范化规则与去重 URI 规则写成可复核条文，供其他用户直接复用。
8. `GITHUB_URL.txt` 的占位链接已替换为实际公开仓库 `https://github.com/179gmghost-svg/nanopublication-reading14-skill`，第二行给出提交目录内的作品入口 `SKILL.md`；仓库以本目录内容同步推送，评审无需登录即可访问。

格式自检（2026-11-23，使用 rdflib 7.6.0 / jsonschema 4.9.1 独立复核）：`examples/sample_output_result.json` 与脚本生成的 `result.json` 均通过 `schemas/nanopub_schema.json` 校验；`nanopublications.jsonld` 解析出 102 条三元组，`nanopublications.trig` 解析出 87 条三元组（4 图 × 4 断言）。
