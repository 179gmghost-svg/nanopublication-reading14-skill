#!/usr/bin/env python3
"""Automated quality-control auditor for Nanopublication reading outputs.

Checks:
1. Required top-level fields and enum values (zero third-party dependencies).
2. Assertion atomicity heuristics (flags overly broad / compound assertions).
3. Verbatim quote alignment against anchored_source.json (normalized substring check).
4. Provenance completeness (metadata + page/section/para_id anchor).
5. Case contract compliance (case_id match and every output_contract field present).
6. Proper tagging of cited_prior_work, unreported claims, and uncertainties.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_STATUS = {"completed", "partial", "indeterminable", "refused"}
ALLOWED_CLAIM_STATUS = {
    "supported",
    "partially_supported",
    "conflicting",
    "unreported",
    "indeterminable",
}
ALLOWED_PREDICATES = {
    "increases",
    "decreases",
    "causes",
    "correlates_with",
    "outperforms",
    "inhibits",
    "equals",
    "measured_as",
    "contradicts",
    "associated_with",
    "requires",
    "other",
}
ALLOWED_EVIDENCE_TYPES = {
    "direct_experimental",
    "statistical_result",
    "visual_chart_or_table",
    "indirect_inference",
    "cited_prior_work",
    "unreported",
}
COMPOUND_MARKERS_RE = re.compile(
    r"\b(?:moreover|furthermore|in addition|whereas|meanwhile|respectively)\b|;",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize whitespace and smart punctuation for robust verbatim quote alignment."""
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip().lower()


def required_contract_fields(case: Dict[str, Any]) -> List[str]:
    """Read the case's output_contract in any of the shapes it is published in.

    Accepts a list of field names, or a dict keyed by ``required_fields``,
    ``fields``, ``required``, ``keys`` or ``output_fields``; a dict value whose
    keys are field names is also accepted.
    """
    contract = case.get("output_contract")
    if isinstance(contract, list):
        return [str(x) for x in contract]
    if isinstance(contract, dict):
        for key in ("required_fields", "fields", "required", "keys", "output_fields"):
            value = contract.get(key)
            if isinstance(value, list):
                return [str(x) for x in value]
            if isinstance(value, dict):
                return [str(k) for k in value]
    return []


def audit_result(
    data: Dict[str, Any],
    source_index: Optional[Dict[str, Any]] = None,
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    def add_issue(level: str, code: str, path: str, message: str) -> None:
        item = {"level": level, "code": code, "path": path, "message": message}
        (errors if level == "ERROR" else warnings).append(item)

    # 1. Top-level contract check
    for req in ("case_id", "status", "source_metadata", "nanopublications", "uncertainties"):
        if req not in data:
            add_issue("ERROR", "MISSING_TOP_LEVEL", req, f"Missing required field '{req}'.")

    if data.get("status") not in ALLOWED_STATUS:
        add_issue(
            "ERROR",
            "INVALID_STATUS",
            "status",
            f"Status '{data.get('status')}' not in {sorted(ALLOWED_STATUS)}.",
        )

    # 2. Source metadata provenance check
    meta = data.get("source_metadata") or {}
    if isinstance(meta, dict):
        for mkey in ("doc_id", "title", "authors", "year", "source_file"):
            if mkey not in meta:
                add_issue(
                    "ERROR",
                    "MISSING_METADATA_KEY",
                    f"source_metadata.{mkey}",
                    f"Missing metadata key '{mkey}' (use null if absent in source).",
                )
        if not meta.get("doi_or_identifier"):
            warnings.append(
                {
                    "level": "WARNING",
                    "code": "NO_DOI_OR_ID",
                    "path": "source_metadata.doi_or_identifier",
                    "message": "No DOI/arXiv identifier recorded; verify whether source provides one.",
                }
            )

    # Build lookup structures from anchored source if provided
    para_map: Dict[str, str] = {}
    full_source_norm = ""
    if source_index and isinstance(source_index.get("paragraphs"), list):
        parts = []
        for p in source_index["paragraphs"]:
            pid = p.get("para_id")
            norm_p = normalize_text(p.get("text", ""))
            if pid:
                para_map[pid] = norm_p
            parts.append(norm_p)
        full_source_norm = " ".join(parts)

    # 2b. Case contract check (case_id + every output_contract field)
    contract_fields = required_contract_fields(case) if isinstance(case, dict) else []
    if isinstance(case, dict):
        case_id = case.get("case_id")
        if case_id and data.get("case_id") != case_id:
            add_issue(
                "ERROR",
                "CASE_ID_MISMATCH",
                "case_id",
                f"result.case_id '{data.get('case_id')}' does not match case.json case_id '{case_id}'.",
            )
        for field in contract_fields:
            if field not in data:
                add_issue(
                    "ERROR",
                    "MISSING_CONTRACT_FIELD",
                    field,
                    f"output_contract requires '{field}', which result.json does not provide.",
                )

    # 3. Nanopublication-level checks
    nanopubs = data.get("nanopublications") or []
    if not isinstance(nanopubs, list):
        add_issue("ERROR", "INVALID_TYPE", "nanopublications", "'nanopublications' must be a list.")
        nanopubs = []

    seen_ids = set()
    aligned_quotes = 0
    total_quotes_checked = 0

    for idx, npub in enumerate(nanopubs):
        prefix = f"nanopublications[{idx}]"
        nid = npub.get("nanopub_id")
        if not nid:
            add_issue("ERROR", "MISSING_NANOPUB_ID", f"{prefix}.nanopub_id", "Missing nanopub_id.")
        elif nid in seen_ids:
            add_issue("ERROR", "DUPLICATE_NANOPUB_ID", f"{prefix}.nanopub_id", f"Duplicate id '{nid}'.")
        else:
            seen_ids.add(nid)

        cstatus = npub.get("claim_status")
        if cstatus not in ALLOWED_CLAIM_STATUS:
            add_issue(
                "ERROR",
                "INVALID_CLAIM_STATUS",
                f"{prefix}.claim_status",
                f"Invalid claim_status '{cstatus}'.",
            )

        assertion = npub.get("assertion") or {}
        stmt = assertion.get("statement", "")
        if not stmt or len(stmt.strip()) < 5:
            add_issue("ERROR", "EMPTY_ASSERTION", f"{prefix}.assertion.statement", "Assertion statement is empty.")
        else:
            # Atomicity heuristics
            if len(stmt) > 260:
                add_issue(
                    "WARNING",
                    "OVERLY_BROAD_ASSERTION",
                    f"{prefix}.assertion.statement",
                    f"Statement length ({len(stmt)} chars) suggests a compound claim; consider splitting.",
                )
            if COMPOUND_MARKERS_RE.search(stmt):
                add_issue(
                    "WARNING",
                    "COMPOUND_CLAUSE_DETECTED",
                    f"{prefix}.assertion.statement",
                    "Statement contains semicolon or multi-clause connector; verify atomicity.",
                )

        pred = assertion.get("predicate")
        if pred not in ALLOWED_PREDICATES:
            add_issue(
                "ERROR",
                "INVALID_PREDICATE",
                f"{prefix}.assertion.predicate",
                f"Predicate '{pred}' not in controlled vocabulary.",
            )

        for req_a in ("subject", "object", "polarity"):
            if not assertion.get(req_a):
                add_issue(
                    "ERROR",
                    "MISSING_ASSERTION_FIELD",
                    f"{prefix}.assertion.{req_a}",
                    f"Missing required assertion field '{req_a}'.",
                )

        ev_list = npub.get("evidence") or []
        if not isinstance(ev_list, list) or len(ev_list) == 0:
            add_issue("ERROR", "MISSING_EVIDENCE", f"{prefix}.evidence", "At least one evidence item is required.")
            continue

        for e_idx, ev in enumerate(ev_list):
            eprefix = f"{prefix}.evidence[{e_idx}]"
            etype = ev.get("evidence_type")
            if etype not in ALLOWED_EVIDENCE_TYPES:
                add_issue(
                    "ERROR",
                    "INVALID_EVIDENCE_TYPE",
                    f"{eprefix}.evidence_type",
                    f"Invalid evidence_type '{etype}'.",
                )

            if etype == "cited_prior_work" and not ev.get("cited_reference"):
                add_issue(
                    "WARNING",
                    "MISSING_CITED_REF",
                    f"{eprefix}.cited_reference",
                    "evidence_type is 'cited_prior_work' but cited_reference is missing.",
                )

            loc = ev.get("location") or {}
            if not isinstance(loc, dict):
                add_issue("ERROR", "INVALID_LOCATION", f"{eprefix}.location", "location must be an object.")
                continue

            if etype != "unreported":
                if loc.get("page") is None and not loc.get("para_id") and not loc.get("figure_or_table"):
                    add_issue(
                        "ERROR",
                        "MISSING_PROVENANCE_ANCHOR",
                        f"{eprefix}.location",
                        "Non-unreported evidence must specify at least page, para_id, or figure_or_table.",
                    )

                para_ref = loc.get("para_id")
                if isinstance(para_ref, str):
                    match = re.match(r"^p(\d+)_b\d+$", para_ref)
                    if (
                        match
                        and loc.get("page") is not None
                        and int(match.group(1)) != loc.get("page")
                    ):
                        add_issue(
                            "WARNING",
                            "PAGE_PARA_MISMATCH",
                            f"{eprefix}.location.page",
                            f"page {loc.get('page')} contradicts para_id '{para_ref}' "
                            f"(page {match.group(1)}).",
                        )

                quote = (ev.get("quote") or "").strip()
                if not quote:
                    add_issue(
                        "ERROR",
                        "EMPTY_QUOTE",
                        f"{eprefix}.quote",
                        "Non-unreported evidence requires a minimal sufficient verbatim quote.",
                    )
                else:
                    if len(quote) > 600:
                        add_issue(
                            "WARNING",
                            "OVERSIZED_QUOTE",
                            f"{eprefix}.quote",
                            f"Quote is {len(quote)} chars; trim to the minimal sufficient evidence span.",
                        )
                    if full_source_norm:
                        total_quotes_checked += 1
                        norm_q = normalize_text(quote)
                        pid = loc.get("para_id")
                        if pid and pid in para_map and norm_q in para_map[pid]:
                            aligned_quotes += 1
                        elif norm_q in full_source_norm:
                            aligned_quotes += 1
                            if pid and pid in para_map:
                                add_issue(
                                    "WARNING",
                                    "PARA_ID_MISMATCH",
                                    f"{eprefix}.location.para_id",
                                    f"Quote found in source, but not inside declared para_id '{pid}'.",
                                )
                        else:
                            add_issue(
                                "ERROR",
                                "QUOTE_NOT_FOUND_IN_SOURCE",
                                f"{eprefix}.quote",
                                "Verbatim quote does not match anchored source text; verify exact wording.",
                            )

    quote_alignment_rate = (
        round(aligned_quotes / total_quotes_checked, 4) if total_quotes_checked else None
    )

    return {
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "nanopublication_count": len(nanopubs),
        "contract_fields": contract_fields,
        "quotes_checked": total_quotes_checked,
        "quotes_aligned": aligned_quotes,
        "quote_alignment_rate": quote_alignment_rate,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Nanopublication reading output.")
    parser.add_argument("--result", required=True, help="Path to draft or final result.json")
    parser.add_argument("--source", help="Optional path to anchored_source.json for verbatim alignment")
    parser.add_argument(
        "--case",
        help="Optional path to the case definition (case.json); checks case_id and output_contract fields",
    )
    parser.add_argument("--schema", help="Optional path to nanopub_schema.json (checked if jsonschema installed)")
    parser.add_argument("--report", help="Optional path to write JSON audit report")
    args = parser.parse_args()

    result_data = json.loads(Path(args.result).read_text(encoding="utf-8"))
    source_data = (
        json.loads(Path(args.source).read_text(encoding="utf-8")) if args.source else None
    )
    case_data = json.loads(Path(args.case).read_text(encoding="utf-8")) if args.case else None

    report = audit_result(result_data, source_data, case_data)

    # Optional jsonschema validation if available
    if args.schema:
        try:
            import jsonschema  # type: ignore

            schema_data = json.loads(Path(args.schema).read_text(encoding="utf-8"))
            jsonschema.validate(instance=result_data, schema=schema_data)
            report["jsonschema_validated"] = True
        except ImportError:
            report["jsonschema_validated"] = "skipped_no_jsonschema_pkg"
        except Exception as exc:  # noqa: BLE001
            report["jsonschema_validated"] = False
            report["passed"] = False
            report["error_count"] += 1
            report["errors"].append(
                {
                    "level": "ERROR",
                    "code": "JSONSCHEMA_ERROR",
                    "path": "$",
                    "message": str(exc),
                }
            )

    if args.report:
        rpath = Path(args.report)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Audit {'PASSED' if report['passed'] else 'FAILED'}: "
        f"{report['error_count']} error(s), {report['warning_count']} warning(s), "
        f"quotes aligned: {report['quotes_aligned']}/{report['quotes_checked']}"
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
