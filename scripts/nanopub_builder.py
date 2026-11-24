#!/usr/bin/env python3
"""Serialize validated scientific assertions into standard 4-graph Nanopublications.

Outputs:
1. JSON-LD (head, assertion, provenance, pubinfo graphs with deterministic SHA-256 URIs)
2. RDF TriG (standard Nanopublication triple-store format)
3. Enriched result.json with deterministic nanopub URIs and export summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def make_deterministic_uri(case_id: str, npub: Dict[str, Any]) -> str:
    """Create a reproducible content-addressed Nanopublication URI for deduplication."""
    assertion = npub.get("assertion", {})
    payload = "|".join(
        [
            case_id,
            str(assertion.get("subject", "")).strip().lower(),
            str(assertion.get("predicate", "")).strip().lower(),
            str(assertion.get("object", "")).strip().lower(),
            str(assertion.get("conditions_and_scope", "")).strip().lower(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"urn:nanopub:reading14:{digest}"


def escape_trig(value: Any) -> str:
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def drop_none(value: Any) -> Any:
    """Drop null-valued keys so downstream JSON-LD/RDF readers never see "null" nodes."""
    if isinstance(value, dict):
        return {k: drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_none(v) for v in value]
    return value


def build_jsonld_and_trig(data: Dict[str, Any]) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    case_id = data.get("case_id", "unknown-case")
    meta = data.get("source_metadata", {})
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    jsonld_items: List[Dict[str, Any]] = []
    trig_blocks: List[str] = [
        "@prefix np: <http://www.nanopub.org/nschema#> .",
        "@prefix prov: <http://www.w3.org/ns/prov#> .",
        "@prefix dct: <http://purl.org/dc/terms/> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix sciread: <https://play.bohrium.com/vocab/nanopub-reading#> .",
        "",
    ]

    enriched = json.loads(json.dumps(data))

    for idx, npub in enumerate(enriched.get("nanopublications", [])):
        uri = make_deterministic_uri(case_id, npub)
        npub["nanopub_uri"] = uri
        head_uri = f"{uri}#Head"
        assertion_uri = f"{uri}#assertion"
        prov_uri = f"{uri}#provenance"
        pubinfo_uri = f"{uri}#pubinfo"

        assertion = npub.get("assertion", {})
        ev_list = npub.get("evidence", [])

        jsonld_items.append(
            drop_none(
                {
                    "@id": uri,
                    "@type": "np:Nanopublication",
                    "np:hasHead": {"@id": head_uri},
                    "np:hasAssertion": {
                        "@id": assertion_uri,
                        "sciread:statement": assertion.get("statement"),
                        "sciread:subject": assertion.get("subject"),
                        "sciread:predicate": assertion.get("predicate"),
                        "sciread:object": assertion.get("object"),
                        "sciread:quantitativeValue": assertion.get("quantitative_value"),
                        "sciread:units": assertion.get("units"),
                        "sciread:conditionsAndScope": assertion.get("conditions_and_scope"),
                        "sciread:polarity": assertion.get("polarity"),
                        "sciread:claimStatus": npub.get("claim_status"),
                    },
                    "np:hasProvenance": {
                        "@id": prov_uri,
                        "prov:wasDerivedFrom": {
                            "dct:identifier": meta.get("doi_or_identifier") or meta.get("doc_id"),
                            "dct:title": meta.get("title"),
                            "dct:creator": meta.get("authors", []),
                            "dct:issued": meta.get("year"),
                            "sciread:version": meta.get("version"),
                            "sciread:sourceFile": meta.get("source_file"),
                        },
                        "sciread:evidence": ev_list,
                    },
                    "np:hasPublicationInfo": {
                        "@id": pubinfo_uri,
                        "dct:created": created_at,
                        "prov:wasGeneratedBy": "nanopublication-reader-skill/v1",
                        "sciread:caseId": case_id,
                    },
                }
            )
        )

        # Build RDF TriG block
        trig_lines = [
            f"<{head_uri}> {{",
            f"  <{uri}> a np:Nanopublication ;",
            f"    np:hasAssertion <{assertion_uri}> ;",
            f"    np:hasProvenance <{prov_uri}> ;",
            f"    np:hasPublicationInfo <{pubinfo_uri}> .",
            "}",
            f"<{assertion_uri}> {{",
            f'  <{assertion_uri}#claim> sciread:statement "{escape_trig(assertion.get("statement", ""))}" ;',
            f'    sciread:subject "{escape_trig(assertion.get("subject", ""))}" ;',
            f'    sciread:predicate "{escape_trig(assertion.get("predicate", ""))}" ;',
            f'    sciread:object "{escape_trig(assertion.get("object", ""))}" ;',
            f'    sciread:polarity "{escape_trig(assertion.get("polarity", ""))}" ;',
            f'    sciread:claimStatus "{escape_trig(npub.get("claim_status", ""))}" .',
            "}",
            f"<{prov_uri}> {{",
            f'  <{assertion_uri}> prov:wasDerivedFrom "{escape_trig(meta.get("doi_or_identifier") or meta.get("source_file", ""))}" ;',
            f'    dct:title "{escape_trig(meta.get("title") or "")}" ;',
            f'    dct:issued "{escape_trig(meta.get("year") or "")}" .',
        ]
        for e_i, ev in enumerate(ev_list):
            loc = ev.get("location", {})
            ev_node = f"<{prov_uri}#ev{e_i + 1}>"
            predicates = [
                f'sciread:evidenceType "{escape_trig(ev.get("evidence_type", ""))}"',
                f'sciread:quote "{escape_trig(ev.get("quote", ""))}"',
            ]
            page = loc.get("page")
            if isinstance(page, int):
                predicates.append(f'sciread:page "{page}"^^xsd:integer')
            if loc.get("section"):
                predicates.append(f'sciread:section "{escape_trig(loc["section"])}"')
            if loc.get("para_id"):
                predicates.append(f'sciread:paraId "{escape_trig(loc["para_id"])}"')
            if loc.get("figure_or_table"):
                predicates.append(
                    f'sciread:figureOrTable "{escape_trig(loc["figure_or_table"])}"'
                )
            if loc.get("equation"):
                predicates.append(f'sciread:equation "{escape_trig(loc["equation"])}"')
            if ev.get("cited_reference"):
                predicates.append(
                    f'sciread:citedReference "{escape_trig(ev["cited_reference"])}"'
                )
            trig_lines.append(f"  {ev_node} " + " ;\n    ".join(predicates) + " .")
        trig_lines.extend(
            [
                "}",
                f"<{pubinfo_uri}> {{",
                f'  <{uri}> dct:created "{created_at}"^^xsd:dateTime ;',
                f'    prov:wasGeneratedBy "nanopublication-reader-skill/v1" ;',
                f'    sciread:caseId "{escape_trig(case_id)}" .',
                "}",
                "",
            ]
        )
        trig_blocks.extend(trig_lines)

    jsonld_doc = {
        "@context": {
            "np": "http://www.nanopub.org/nschema#",
            "prov": "http://www.w3.org/ns/prov#",
            "dct": "http://purl.org/dc/terms/",
            "sciread": "https://play.bohrium.com/vocab/nanopub-reading#",
        },
        "@graph": jsonld_items,
    }

    enriched["export_summary"] = {
        "nanopublication_count": len(jsonld_items),
        "generated_at_utc": created_at,
        "formats": ["json", "json-ld", "rdf-trig"],
    }
    return jsonld_doc, "\n".join(trig_blocks), enriched


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Nanopublication JSON-LD and TriG exports.")
    parser.add_argument("--input", required=True, help="Validated draft result.json")
    parser.add_argument("--out-jsonld", required=True, help="Output JSON-LD path")
    parser.add_argument("--out-trig", required=True, help="Output RDF TriG path")
    parser.add_argument("--out-result", required=True, help="Output enriched result.json path")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    jsonld_doc, trig_text, enriched = build_jsonld_and_trig(data)

    for path_str, content in (
        (args.out_jsonld, json.dumps(jsonld_doc, ensure_ascii=False, indent=2)),
        (args.out_trig, trig_text),
        (args.out_result, json.dumps(enriched, ensure_ascii=False, indent=2)),
    ):
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    print(
        f"Generated {enriched['export_summary']['nanopublication_count']} Nanopublications -> "
        f"{args.out_jsonld}, {args.out_trig}, {args.out_result}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
