---
name: nanopublication-reader
description: >-
  Decompose scientific literature into atomic, verifiable Nanopublication
  assertions with minimal sufficient verbatim evidence, exact source anchors
  (page, section, paragraph, figure/table, equation), full bibliographic
  provenance, automated quality auditing, and machine-readable JSON-LD / TriG
  export. Designed for Harbor reading benchmarks (/input/case.json + task.md ->
  /app/output/result.json).
---

# Nanopublication Scientific Reading Skill (`nanopublication-reader`)

## 1. Purpose & Applicability

This skill guides an agent to read scientific papers, PDFs, tables, figures, or
structured excerpts and transform key scientific findings into **auditable,
machine-readable Nanopublications** (following the four-graph Nanopublication
model: `head`, `assertion`, `provenance`, `pubinfo`).

Use this skill whenever a task requires:
- Answering scientific reading questions with traceable verbatim evidence.
- Decomposing compound conclusions into atomic, independently verifiable claims.
- Binding each claim to its minimal sufficient evidence span and exact location.
- Preserving bibliographic provenance, experimental conditions, and scope limits.
- Explicitly flagging unreported items, indeterminable claims, or source conflicts.
- Exporting downstream-ready structured JSON / JSON-LD / RDF TriG outputs.

Do **not** fabricate missing numbers, citations, DOIs, or visual readings. If a
PDF figure is unreadable or a value is not reported in the source, mark it
explicitly as `unreported` or `indeterminable` with an exact reason.

## 2. Harbor Runtime Contract & Budget Discipline

- **Skill location**: this file is installed at `/skills/weekly-skill/SKILL.md`.
  Resolve `SKILL_DIR` as the directory containing this `SKILL.md` and invoke the
  bundled scripts as `python3 "$SKILL_DIR/scripts/<name>.py"`. The working
  directory is `/app/work`, so bare relative paths such as `scripts/...` will not
  resolve. Field-level definitions, controlled vocabularies and the evidence
  alignment rules are in `$SKILL_DIR/docs/field_dictionary.md`; the machine
  contract is `$SKILL_DIR/schemas/nanopub_schema.json`.
- **Inputs**: Read `/input/case.json` and `/input/task.md` (or `task.md` in the
  working directory) first. Identify `case_id`, all attached PDF/text paths,
  and the exact `output_contract` fields required.
- **Working Directory**: Store intermediate extracted text, rendered figure PNGs,
  and draft JSON files in `/app/work/`.
- **Final Outputs**: Write final deliverables to `/app/output/`:
  - `/app/output/result.json` — MUST include `case_id`, `status`, all fields
    required by `output_contract`, plus the `nanopublications` array,
    `quality_audit` summary, and `change_records`.
  - `/app/output/nanopublications.jsonld` — JSON-LD export (4-graph model).
  - `/app/output/nanopublications.trig` — RDF TriG export for triple stores.
- **Execution Budget**: Stay well within 64 model requests and 900 s wall-clock
  time. Prefer running the bundled Python scripts
  (`scripts/pdf_anchor_extract.py`, `scripts/nanopub_builder.py`,
  `scripts/validate_nanopub.py`) in batch rather than inspecting a PDF
  page-by-page across many turns.

## 3. Six-Stage Execution Workflow

### Stage 1: Scope & Contract Discovery
1. Inspect `/input/case.json` and `task.md`.
2. Extract:
   - `case_id`
   - Primary task objective (QA, structured extraction, verification, conflict check, or full Nanopublication conversion)
   - Required `output_contract` schema/keys
   - All input source files (PDFs, text, CSV/JSON, images)

### Stage 2: Anchored Source Extraction
1. Run `python3 "$SKILL_DIR/scripts/pdf_anchor_extract.py" <input_pdf_or_txt> --out /app/work/anchored_source.json`.
   - This produces a deterministic page-, section-, paragraph-, and caption-indexed
     JSON file (`page`, `para_id`, `section_hint`, `text`, `figure_table_refs`).
   - PDF backends are tried in order: PyMuPDF, pypdf, pdfplumber, then the
     Poppler `pdftotext` binary; `extraction_backend` in the output records which
     one produced the text. A backend returning only whitespace is skipped, so
     scanned PDFs report `needs_ocr_review: true`.
2. If the PDF is scanned or contains critical quantitative figures/tables with
   missing text layers, render only the relevant pages to PNG using the platform's
   `pdf-render-tool` / `ocr-tool` and record the rendered page numbers in
   provenance (`extraction_method: "ocr_or_visual"`).

### Stage 3: Bibliographic Provenance Extraction (`pubinfo` & `source_metadata`)
Extract exact document metadata from the paper header/frontmatter/input metadata:
- `doc_id`, `title`, `authors` (list), `year`, `venue_or_publisher`, `doi_or_identifier`, `version`, `source_file`.
- For any metadata field not present in the input materials, set the value to `null` and list the field name in `missing_metadata` — never guess.

### Stage 4: Atomic Assertion Decomposition ("拆得细")
Break every relevant conclusion or answer into **atomic assertions**:
- **One verifiable proposition per assertion**: Never pack a whole paragraph or
  multiple independent findings into one assertion string.
- **Split compound structures**:
  - Coordinate lists (`A and B both increased X`) -> split into separate atomic
    assertions unless the claim is explicitly about a joint/synergistic effect.
  - Causal chains (`X activates Y, which reduces Z`) -> split into `X -> Y` and
    `Y -> Z` (and optionally an explicit end-to-end assertion if directly tested).
- **Structured triple + qualifiers**:
  - `subject`: normalized entity + verbatim surface form
  - `predicate`: controlled relation type (`increases`, `decreases`, `causes`,
    `correlates_with`, `outperforms`, `inhibits`, `equals`, `measured_as`,
    `contradicts`, `associated_with`, `requires`, `other`)
  - `object`: normalized target entity or quantitative value with units
  - `conditions_and_scope`: experimental conditions, sample size `n`, species/material,
    temperature/pH/model setting, statistical significance (`p`, CI, effect size),
    and explicit boundary conditions
  - `polarity`: `positive | negative | neutral | conditional | inconclusive`
  - `claim_status`: `supported | partially_supported | conflicting | unreported | indeterminable`

### Stage 5: Minimal Sufficient Evidence Binding ("对得上" & "追得回")
For **each** atomic assertion, attach one or more `evidence_items`:
1. **`quote`**: The *minimal sufficient* verbatim excerpt from the source
   (typically 1–2 sentences or a specific table row/caption) that directly
   justifies the assertion. Do not paste entire pages.
2. **`location`**: Exact anchor object:
   - `page` (1-indexed integer or `null` for plain text)
   - `section` (e.g., `"3.2 Catalytic Performance"`)
   - `para_id` (matching `anchored_source.json`)
   - `figure_or_table` (e.g., `"Figure 3b"`, `"Table 2"`, or `null`)
   - `equation` (e.g., `"Eq. (4)"`, or `null`)
3. **`evidence_type`**: Classify strictly as:
   - `direct_experimental` (primary measurement/result reported in this paper)
   - `statistical_result` (explicit statistical test/metric)
   - `visual_chart_or_table` (value read from a table or figure)
   - `indirect_inference` (derived by combining 2+ statements; explain `reasoning_note`)
   - `cited_prior_work` (statement attributed to an external reference `[k]` — NEVER confuse cited prior work with the current paper's own finding!)
   - `unreported` (explicitly absent from the provided materials)
4. **Conflict & Uncertainty Handling**:
   - If two locations in the source(s) disagree (e.g., abstract vs. Table 2),
     record both anchors, set `claim_status: "conflicting"`, and populate `conflicts`.
   - Record all unanswered sub-questions or missing parameters in `uncertainties`.

### Stage 6: Build, Validate, Repair, and Export ("读得懂")
1. Write the draft structured payload to `/app/work/draft_result.json`.
2. Run the automated quality auditor:
   ```bash
   python3 "$SKILL_DIR/scripts/validate_nanopub.py" \
     --result /app/work/draft_result.json \
     --source /app/work/anchored_source.json \
     --case /input/case.json \
     --schema "$SKILL_DIR/schemas/nanopub_schema.json" \
     --report /app/work/audit_report.json
   ```
3. Inspect `/app/work/audit_report.json`. Fix all `ERROR`-level findings (e.g.,
   `QUOTE_NOT_FOUND_IN_SOURCE`, `MISSING_CONTRACT_FIELD`, `CASE_ID_MISMATCH`,
   compound unsplit assertions, missing provenance anchors) and re-run until
   `error_count == 0`. Record each repair in `change_records`
   (`{"change": ..., "reason": ..., "at": ...}`) so the audit trail shows what
   was revised and why.
4. Generate final Nanopublication exports and copy final `result.json`:
   ```bash
   python3 "$SKILL_DIR/scripts/nanopub_builder.py" \
     --input /app/work/draft_result.json \
     --out-jsonld /app/output/nanopublications.jsonld \
     --out-trig /app/output/nanopublications.trig \
     --out-result /app/output/result.json
   ```
5. Copy the audit report to `/app/output/quality_audit.json` and confirm
   `result.json` contains every `output_contract` field, the original `case_id`,
   and an explicit `status`.

## 4. Failure Modes & Exception Handling

| Scenario | Required Action |
| :--- | :--- |
| PDF has no extractable text layer | Fall back to `pdf-render-tool` + `ocr-tool`; tag `extraction_method: "ocr"`; flag low-confidence numbers in `uncertainties`. |
| Evidence quote fails substring alignment check | Re-verify against `anchored_source.json`; fix OCR hyphenation or copy exact verbatim span; never leave a paraphrased string in `quote`. |
| Claim relies on cited prior work `[12]` | Tag `evidence_type: "cited_prior_work"` and record `cited_reference` so it is not misattributed as the paper's own experimental finding. |
| Source lacks requested metric/condition | Set `claim_status: "unreported"`, `value: null`, and document the gap in `uncertainties`. Never guess. |
| Task asks a question outside provided materials | Set top-level `status: "indeterminable"` or `"refused"` with explicit `status_reason`. |
