#!/usr/bin/env python3
"""Extract page-, section-, paragraph-, and figure/table-anchored text from PDF or text files.

Tries PyMuPDF (fitz) -> pypdf -> pdfplumber for PDFs, and handles UTF-8 text/Markdown directly.
Outputs a deterministic JSON index usable by validate_nanopub.py for verbatim quote verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

SECTION_RE = re.compile(
    r"^(?:(?:\d+(?:\.\d+)*\.?\s+)[A-Z][^\n]{2,80}|"
    r"(?:Abstract|Introduction|Background|Methods|Materials and Methods|"
    r"Experimental|Results|Discussion|Results and Discussion|Conclusion|"
    r"Conclusions|Acknowledgments|References|Supplementary Information)\b[^\n]{0,60})$"
)
FIG_TABLE_RE = re.compile(
    r"\b(?:Fig(?:ure)?\.?\s*\d+[a-zA-Z]?|Table\s*\d+[a-zA-Z]?|Scheme\s*\d+|"
    r"Eq(?:uation)?\.?\s*\(?\d+\)?|Supplementary\s+(?:Fig(?:ure)?|Table)\s*\w+)\b"
)


def extract_pdf_pages(pdf_path: Path, scratch_dir: Path) -> Tuple[List[Tuple[int, str]], str]:
    """Return list of (1-indexed page_no, raw_text) and backend name.

    Backends are tried in order of fidelity: PyMuPDF -> pypdf -> pdfplumber ->
    the Poppler ``pdftotext`` binary. A backend that returns only whitespace
    (typical for scanned PDFs without a text layer) is treated as unavailable so
    that the next one gets a chance and ``empty_text_pages`` stays meaningful.
    """

    def has_text(pages: List[Tuple[int, str]]) -> bool:
        return any(text.strip() for _, text in pages)

    try:
        import fitz  # type: ignore

        pages = []
        with fitz.open(str(pdf_path)) as doc:
            for idx, page in enumerate(doc, start=1):
                pages.append((idx, page.get_text("text") or ""))
        if has_text(pages):
            return pages, "pymupdf"
    except ImportError:
        pass

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        pages = [
            (idx, page.extract_text() or "")
            for idx, page in enumerate(reader.pages, start=1)
        ]
        if has_text(pages):
            return pages, "pypdf"
    except ImportError:
        pass

    try:
        import pdfplumber  # type: ignore

        pages = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                pages.append((idx, page.extract_text() or ""))
        if has_text(pages):
            return pages, "pdfplumber"
    except ImportError:
        pass

    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        out_txt = scratch_dir / f".pdftotext-{uuid.uuid4().hex}.txt"
        try:
            proc = subprocess.run(
                [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path), str(out_txt)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.returncode != 0 or not out_txt.is_file():
                raise RuntimeError(
                    f"pdftotext exited with code {proc.returncode} and produced no text; "
                    "use the platform pdf-text-tool or pass a pre-extracted .txt file."
                )
            text = out_txt.read_text(encoding="utf-8", errors="replace")
        finally:
            out_txt.unlink(missing_ok=True)
        pages = [
            (idx, chunk) for idx, chunk in enumerate(text.split("\f"), start=1)
        ]
        if pages and not pages[-1][1].strip():
            pages.pop()
        return pages, "pdftotext"

    raise RuntimeError(
        "No PDF text backend is available (pymupdf, pypdf, pdfplumber, pdftotext). "
        "Use the platform pdf-text-tool or pass a pre-extracted .txt file."
    )


def split_paragraphs(raw_text: str) -> List[str]:
    """Normalize line wraps and split text into paragraphs."""
    # Fix soft hyphenation across line breaks
    cleaned = re.sub(r"-\n([a-z])", r"\1", raw_text)
    blocks = re.split(r"\n\s*\n+", cleaned.strip())
    paragraphs: List[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        paragraphs.append(" ".join(lines))
    return paragraphs


def build_anchored_index(source_path: Path, scratch_dir: Path) -> Dict[str, Any]:
    raw_bytes = source_path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        pages, backend = extract_pdf_pages(source_path, scratch_dir)
    else:
        text = raw_bytes.decode("utf-8", errors="replace")
        # Support optional form-feed page breaks in text files
        if "\f" in text:
            pages = [(i + 1, chunk) for i, chunk in enumerate(text.split("\f"))]
        else:
            pages = [(1, text)]
        backend = "plain_text"

    current_section = "Frontmatter"
    anchored_paragraphs: List[Dict[str, Any]] = []
    empty_pages: List[int] = []

    for page_no, raw_text in pages:
        paras = split_paragraphs(raw_text)
        if not paras:
            empty_pages.append(page_no)
            continue
        for p_idx, para_text in enumerate(paras, start=1):
            if len(para_text) <= 95 and SECTION_RE.match(para_text):
                current_section = para_text
            refs = sorted(set(FIG_TABLE_RE.findall(para_text)))
            anchored_paragraphs.append(
                {
                    "para_id": f"p{page_no}_b{p_idx}",
                    "page": page_no,
                    "section_hint": current_section,
                    "text": para_text,
                    "figure_table_refs": refs,
                    "char_count": len(para_text),
                }
            )

    return {
        "source_file": source_path.name,
        "source_sha256": sha256,
        "extraction_backend": backend,
        "total_pages": len(pages),
        "empty_text_pages": empty_pages,
        "needs_ocr_review": bool(empty_pages),
        "paragraph_count": len(anchored_paragraphs),
        "paragraphs": anchored_paragraphs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract page/section/paragraph-anchored JSON from PDF or text."
    )
    parser.add_argument("input_file", help="Path to PDF, TXT, or MD file")
    parser.add_argument("--out", required=True, help="Path to output anchored JSON")
    args = parser.parse_args()

    src = Path(args.input_file)
    if not src.is_file():
        print(f"ERROR: input file not found: {src}", file=sys.stderr)
        return 1

    index = build_anchored_index(src, Path(args.out).parent)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Extracted {index['paragraph_count']} paragraphs across {index['total_pages']} page(s) "
        f"using {index['extraction_backend']} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
