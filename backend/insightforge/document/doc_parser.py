"""
doc_parser.py
=============
Generic PDF structure parser for a RAG pipeline that ingests books, policy
documents, standards (ISO/NIST/Common Criteria/etc.), research papers, and
journals.

Design:
  Layer 1 - Raw extraction   : PyMuPDF pulls text spans w/ font, size, position
  Layer 2 - Structure detect : pluggable detectors turn spans into typed Elements
  Layer 3 - Normalized output: same schema regardless of doc type, ready to chunk

Usage:
    from doc_parser import parse_document

    result = parse_document("book.pdf", doc_type="book")
    for el in result["elements"]:
        print(el["type"], el.get("level"), el["text"][:60])

Dependencies:
    pip install pymupdf pdfplumber
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Optional

import pymupdf  # PyMuPDF
import pdfplumber


# ---------------------------------------------------------------------------
# Layer 3 schema
# ---------------------------------------------------------------------------

@dataclass
class Element:
    type: str                      # heading | paragraph | table | list_item |
                                    # definition_term | reference_entry | id_ref
    text: str
    page: int
    level: Optional[int] = None    # heading level, if applicable
    meta: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Layer 1: raw extraction (shared by every doc type)
# ---------------------------------------------------------------------------

def extract_raw_spans_and_toc(pdf_path: str) -> tuple[list[dict], list[tuple]]:
    """
    Single-open variant: extracts spans AND the embedded TOC in one fitz.open()
    call instead of two. Use this instead of calling extract_raw_spans() and
    get_embedded_toc() separately -- halves the redundant PDF parsing cost.

    Ligature handling: some PDFs embed fonts whose ToUnicode CMap maps
    ligature glyphs (ff/fi/fl/ffi/ffl) to the WRONG unicode codepoint --
    commonly landing on IPA phonetic symbols (ʃ, ɹ, ɻ) instead of the real
    letters. Passing flags without TEXT_PRESERVE_LIGATURES tells PyMuPDF to
    decompose ligature glyphs into their base letters itself instead of
    trusting that (sometimes broken) font-supplied mapping.
    """
    doc = pymupdf.open(pdf_path)
    toc = doc.get_toc()
    extract_flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    spans = []
    for page_num, page in enumerate(doc):
        page_height = page.rect.height
        blocks = page.get_text("dict", flags=extract_flags)["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = normalize_ligatures(span["text"].strip())
                    if not text:
                        continue
                    spans.append({
                        "text": text,
                        "size": round(span["size"], 1),
                        "font": span["font"],
                        "bold": "bold" in span["font"].lower(),
                        "page": page_num + 1,
                        "x0": span["bbox"][0],
                        "y0": span["bbox"][1],
                        "x1": span["bbox"][2],
                        "y1": span["bbox"][3],
                        "page_height": page_height,
                    })
    doc.close()
    return spans, toc


# Safety net on top of the flags fix above: covers cases where a font's
# ligature mapping is broken for codepoints PyMuPDF's decomposition doesn't
# catch. Only touches these exact rare glyphs -- won't affect normal text.
_LIGATURE_FIXUPS = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl",
    "\u0283": "ff", "\u0279": "fi", "\u026b": "fl",
}


def normalize_ligatures(text: str) -> str:
    for bad, good in _LIGATURE_FIXUPS.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def extract_raw_spans(pdf_path: str) -> list[dict]:
    """
    Returns a flat list of span dicts across the whole document:
    {text, size, font, bold, page, x0, y0, x1, y1, page_height}
    """
    doc = pymupdf.open(pdf_path)
    spans = []
    for page_num, page in enumerate(doc):
        page_height = page.rect.height
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    spans.append({
                        "text": text,
                        "size": round(span["size"], 1),
                        "font": span["font"],
                        "bold": "bold" in span["font"].lower(),
                        "page": page_num + 1,
                        "x0": span["bbox"][0],
                        "y0": span["bbox"][1],
                        "x1": span["bbox"][2],
                        "y1": span["bbox"][3],
                        "page_height": page_height,
                    })
    doc.close()
    return spans


def get_embedded_toc(pdf_path: str) -> list[tuple[int, str, int]]:
    """Returns [(level, title, page_number), ...] if the PDF has bookmarks."""
    doc = pymupdf.open(pdf_path)
    toc = doc.get_toc()
    doc.close()
    return toc


def compute_body_font_size(spans: list[dict]) -> float:
    """Modal font size = the most common size = body text size."""
    sizes = [s["size"] for s in spans]
    if not sizes:
        return 10.0
    return Counter(sizes).most_common(1)[0][0]


def strip_headers_footers(spans: list[dict], band_pct: float = 0.06) -> list[dict]:
    """
    Detects text that repeats across many pages in the top/bottom margin band
    and removes it (running headers, footers, page numbers).
    """
    num_pages = max(s["page"] for s in spans) if spans else 1
    band_hits: Counter[str] = Counter()

    for s in spans:
        top_band = s["y0"] < s["page_height"] * band_pct
        bottom_band = s["y1"] > s["page_height"] * (1 - band_pct)
        if top_band or bottom_band:
            norm = re.sub(r"\d+", "#", s["text"]).strip()  # normalize page numbers
            band_hits[norm] += 1

    threshold = max(2, int(num_pages * 0.3))
    repeated = {t for t, c in band_hits.items() if c >= threshold}

    def is_noise(s):
        top_band = s["y0"] < s["page_height"] * band_pct
        bottom_band = s["y1"] > s["page_height"] * (1 - band_pct)
        if not (top_band or bottom_band):
            return False
        norm = re.sub(r"\d+", "#", s["text"]).strip()
        if norm in repeated:
            return True
        if re.fullmatch(r"\d+", s["text"]):  # bare page number
            return True
        return False

    return [s for s in spans if not is_noise(s)]


def group_lines(spans: list[dict]) -> list[dict]:
    """
    Merge spans on the same visual line (same page, close y0) into single
    line-records, keeping the dominant font/size/bold for the line.

    Only inserts a space between merged spans when there's an actual
    horizontal gap on the page (checked via x-coordinates). Without this,
    a ligature glyph that PyMuPDF splits into two adjacent spans -- e.g.
    "su" + "ffering" -- gets a spurious space jammed into the middle
    ("su ffering") purely as an artifact of how spans were merged, not
    because the source text had a space there.
    """
    lines = []
    spans_sorted = sorted(spans, key=lambda s: (s["page"], round(s["y0"], 0), s["x0"]))
    current = None
    for s in spans_sorted:
        if (current is not None
                and s["page"] == current["page"]
                and abs(s["y0"] - current["y0"]) < 2.5):
            gap = s["x0"] - current["x1"]
            separator = " " if gap > 1.5 else ""
            current["text"] += separator + s["text"]
            current["x1"] = s["x1"]
            current["size"] = max(current["size"], s["size"])
            current["bold"] = current["bold"] or s["bold"]
        else:
            if current:
                lines.append(current)
            current = dict(s)
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Layer 2: pluggable structure detectors
# ---------------------------------------------------------------------------

class BaseDetector:
    """
    Shared heuristics available to every detector. Subclasses override
    `classify_line` and/or `post_process` for doc-type-specific behaviour.
    """

    #: Optional regex patterns for domain identifiers this doc type uses,
    #: e.g. clause numbers, requirement IDs, equation numbers. Matches are
    #: captured as `id_ref` elements with the pattern name in meta.
    id_patterns: dict[str, str] = {}

    #: Known section-name vocabulary (case-insensitive), used for papers /
    #: any doc with a fixed set of top-level section titles.
    section_vocab: set[str] = set()

    def __init__(self, body_size: float):
        self.body_size = body_size

    def classify_line(self, line: dict) -> Element:
        text = line["text"]
        size_ratio = line["size"] / self.body_size
        pos_meta = {"y0": line["y0"], "y1": line["y1"], "line_size": line["size"]}

        # numbered clause, e.g. "4.1.2 Access Control"
        clause_match = re.match(r"^(\d+(\.\d+)*)\s+([A-Z].{2,80})$", text)
        if clause_match and (line["bold"] or size_ratio > 1.05):
            depth = clause_match.group(1).count(".") + 1
            meta = {"clause_no": clause_match.group(1), **pos_meta}
            return Element(type="heading", text=text, page=line["page"],
                            level=depth, meta=meta)

        # vocabulary-based heading (Abstract, Introduction, References...)
        if text.strip(" :0123456789.").title() in {v.title() for v in self.section_vocab}:
            return Element(type="heading", text=text, page=line["page"],
                            level=1, meta=pos_meta)

        # ALL-CAPS short line at (or above) body size: many books use caps or
        # letter-spacing instead of a bigger font for chapter/section titles,
        # so the size-ratio heuristic below alone misses these.
        if self._is_all_caps_heading(text) and size_ratio >= 0.95:
            return Element(type="heading", text=text, page=line["page"],
                            level=2, meta=pos_meta)

        # generic font-size/bold heading heuristic
        if size_ratio > 1.35 or (line["bold"] and size_ratio > 1.1):
            level = 1 if size_ratio > 1.6 else 2
            return Element(type="heading", text=text, page=line["page"],
                            level=level, meta=pos_meta)

        return Element(type="paragraph", text=text, page=line["page"])

    @staticmethod
    def _is_all_caps_heading(text: str) -> bool:
        letters = [c for c in text if c.isalpha()]
        if len(letters) < 3 or len(text) > 90:
            return False
        return all(c.isupper() for c in letters)

    def merge_wrapped_headings(self, elements: list[Element]) -> list[Element]:
        """
        Reunite a heading that visually wraps across 2+ lines (e.g. a long
        chapter title split by the page layout) WITHOUT merging genuinely
        distinct consecutive headings (e.g. separate TOC entries).

        Distinguishes the two cases using actual vertical spacing: a wrapped
        continuation line sits almost flush against the previous line (gap
        close to normal single-line-height), while distinct entries in a
        list or TOC are typically spaced further apart.
        """
        merged: list[Element] = []
        for el in elements:
            if (el.type == "heading" and merged and merged[-1].type == "heading"
                    and el.page == merged[-1].page
                    and el.level == merged[-1].level
                    and "y0" in el.meta and "y1" in merged[-1].meta):
                gap = el.meta["y0"] - merged[-1].meta["y1"]
                line_height = merged[-1].meta.get("line_size", 12)
                if 0 <= gap <= line_height * 1.4:
                    prev = merged[-1]
                    merged[-1] = Element(
                        type="heading",
                        text=prev.text + " " + el.text,
                        page=prev.page,
                        level=prev.level,
                        meta={**prev.meta, "y1": el.meta["y1"]},
                    )
                    continue
            merged.append(el)
        return merged

    def extract_id_refs(self, text: str, page: int) -> list[Element]:
        """Find domain-specific identifiers embedded in body text."""
        found = []
        for name, pattern in self.id_patterns.items():
            for m in re.finditer(pattern, text):
                found.append(Element(type="id_ref", text=m.group(0), page=page,
                                      meta={"pattern": name}))
        return found

    def merge_paragraphs(self, elements: list[Element]) -> list[Element]:
        """Merge consecutive same-page paragraph lines into full paragraphs."""
        merged: list[Element] = []
        buf: list[Element] = []

        def flush():
            if buf:
                merged.append(Element(
                    type="paragraph",
                    text=" ".join(e.text for e in buf),
                    page=buf[0].page,
                ))
                buf.clear()

        for el in elements:
            if el.type == "paragraph":
                if buf and el.page != buf[-1].page:
                    flush()
                buf.append(el)
            else:
                flush()
                merged.append(el)
        flush()
        return merged

    def reclassify_toc_entries(self, elements: list[Element]) -> list[Element]:
        """
        A "CONTENTS" heading marks the start of a table-of-contents page.
        Every other heading-looking line on that SAME page is a TOC list
        entry, not real document structure -- retag it as `toc_entry` so it
        doesn't get treated (or chunked) as an actual section heading.
        TOC entries are navigational, not content worth indexing for RAG.
        """
        out = []
        toc_page = None
        for el in elements:
            if el.type == "heading" and el.text.strip().lower() in (
                    "contents", "table of contents"):
                toc_page = el.page
                out.append(el)
                continue
            if toc_page is not None and el.page != toc_page:
                toc_page = None
            if toc_page is not None and el.type == "heading":
                out.append(Element(type="toc_entry", text=el.text,
                                    page=el.page, level=el.level))
                continue
            out.append(el)
        return out

    def merge_heading_runs(self, elements: list[Element],
                            max_run: int = 3, max_chars: int = 100) -> list[Element]:
        """
        Titles that wrap across 2-3 physical lines (e.g. "EXPERIENCES IN A" /
        "CONCENTRATION CAMP") get detected as separate heading elements at
        the line level. Merge a short run of consecutive same-page headings
        into one, but only when they look like continuation lines of the
        SAME title rather than two genuinely distinct headings:
          - near-identical font size (a real title and the section after it,
            e.g. "Abstract", are almost always sized differently)
          - tight vertical spacing between them (true wrapped lines sit right
            on top of each other; unrelated headings usually have a bigger
            gap or a paragraph in between)
        Position metadata (y0/y1/line_size) comes from classify_line.
        """
        def same_title_continuation(a: Element, b: Element) -> bool:
            am, bm = a.meta or {}, b.meta or {}
            if "line_size" not in am or "line_size" not in bm:
                return False
            size_close = abs(am["line_size"] - bm["line_size"]) <= 0.5
            gap = bm["y0"] - am["y1"]
            tight_spacing = 0 <= gap <= am["line_size"] * 1.8
            return size_close and tight_spacing

        out = []
        i, n = 0, len(elements)
        while i < n:
            el = elements[i]
            if el.type == "heading":
                run = [el]
                j = i + 1
                while (j < n and elements[j].type == "heading"
                       and elements[j].page == el.page
                       and len(run) < max_run
                       and same_title_continuation(run[-1], elements[j])):
                    run.append(elements[j])
                    j += 1
                combined = " ".join(e.text for e in run)
                if len(run) > 1 and len(combined) <= max_chars:
                    out.append(Element(type="heading", text=combined, page=el.page,
                                        level=min((e.level or 2) for e in run)))
                    i = j
                    continue
            out.append(el)
            i += 1
        return out

    def post_process(self, elements: list[Element]) -> list[Element]:
        elements = self.reclassify_toc_entries(elements)
        elements = self.merge_heading_runs(elements)
        return self.merge_paragraphs(elements)

    def detect(self, lines: list[dict]) -> list[Element]:
        elements: list[Element] = []
        for line in lines:
            el = self.classify_line(line)
            elements.append(el)
            if el.type == "paragraph" and self.id_patterns:
                elements.extend(self.extract_id_refs(el.text, el.page))
        return self.post_process(elements)


class BookDetector(BaseDetector):
    """Chapters/sections driven by font size (and TOC, handled upstream)."""
    pass  # base heuristics are already tuned for this case


class PolicyDetector(BaseDetector):
    """
    Numbered-clause structure + a Definitions section whose terms should be
    tagged specially so they can be surfaced as context elsewhere.
    """
    section_vocab = {"Definitions", "Scope", "Purpose", "Policy Statement",
                      "Responsibilities", "Enforcement"}

    def post_process(self, elements: list[Element]) -> list[Element]:
        elements = super().post_process(elements)
        in_definitions = False
        out = []
        for el in elements:
            if el.type == "heading" and el.text.strip().lower().startswith("definition"):
                in_definitions = True
            elif el.type == "heading":
                in_definitions = False

            if in_definitions and el.type == "paragraph":
                m = re.match(r'^"?([A-Za-z][\w /-]{1,40})"?\s*[:\u2013-]\s*(.+)$', el.text)
                if m:
                    out.append(Element(type="definition_term", text=el.text,
                                        page=el.page,
                                        meta={"term": m.group(1).strip(),
                                              "definition": m.group(2).strip()}))
                    continue
            out.append(el)
        return out


class StandardDetector(BaseDetector):
    """
    Generic 'standard' detector (ISO/NIST/Common Criteria/etc). Not hardcoded
    to one standard family -- pass `id_patterns` for whatever identifier
    convention your standard uses, e.g.:

        StandardDetector(body_size, id_patterns={
            "cc_component": r"\\b[A-Z]{2,4}_[A-Z]{3}\\.\\d+(\\.\\d+)?\\b",
            "iso_clause":   r"\\bclause\\s+\\d+(\\.\\d+)*\\b",
        })
    """
    def __init__(self, body_size: float, id_patterns: Optional[dict[str, str]] = None):
        super().__init__(body_size)
        if id_patterns:
            self.id_patterns = id_patterns


class ResearchPaperDetector(BaseDetector):
    """Fixed section vocabulary + reference-list splitting."""
    section_vocab = {"Abstract", "Introduction", "Related Work", "Background",
                      "Methods", "Methodology", "Results", "Discussion",
                      "Conclusion", "Conclusions", "References", "Appendix",
                      "Acknowledgements", "Acknowledgments"}

    #: a new reference entry must START a line with one of these markers.
    #: matching at line-start (before merging) avoids false splits on stray
    #: numbers/years that show up mid-sentence in already-merged paragraphs.
    _ENTRY_START = re.compile(r"^(\[\d+\]|\d+\.)\s+")

    def post_process(self, elements: list[Element]) -> list[Element]:
        elements = self.reclassify_toc_entries(elements)
        elements = self.merge_heading_runs(elements)

        ref_idx = next((i for i, el in enumerate(elements)
                         if el.type == "heading"
                         and el.text.strip().lower().startswith("reference")), None)
        if ref_idx is None:
            return self.merge_paragraphs(elements)

        # normal merge for everything up to and including the References heading
        before = self.merge_paragraphs(elements[:ref_idx + 1])
        after = elements[ref_idx + 1:]

        entries: list[Element] = []
        current: Optional[Element] = None
        for el in after:
            if el.type != "paragraph":
                if current:
                    entries.append(current)
                    current = None
                before.append(el)
                continue
            stripped = el.text.strip()
            if self._ENTRY_START.match(stripped) or current is None:
                if current:
                    entries.append(current)
                current = Element(type="reference_entry", text=stripped, page=el.page)
            else:
                current.text += " " + stripped
        if current:
            entries.append(current)

        return before + entries


DETECTORS = {
    "book": BookDetector,
    "policy": PolicyDetector,
    "standard": StandardDetector,
    "research_paper": ResearchPaperDetector,
    "journal": ResearchPaperDetector,
    "generic": BaseDetector,
}


# ---------------------------------------------------------------------------
# Optional: cheap doc_type auto-detection for mixed / unlabeled uploads.
# Never crashes or blocks the pipeline -- when confidence is low it returns
# "generic", which is always safe to run (see BaseDetector fallback above).
# ---------------------------------------------------------------------------

def detect_doc_type(pdf_path: str, sample_pages: int = 3) -> tuple[str, dict]:
    """
    Cheap heuristic classifier. Returns (doc_type, scores) so callers can
    inspect confidence rather than trust a black-box guess.

    This is NOT meant to be authoritative -- it's a default for when the
    uploader doesn't specify a type. Always let the user override it, and
    always keep "generic" as a valid, fully-supported result.
    """
    doc = pymupdf.open(pdf_path)
    text = ""
    for page in doc[:sample_pages]:
        text += page.get_text()
    doc.close()
    text_lower = text.lower()

    scores = {
        "research_paper": 0,
        "policy": 0,
        "standard": 0,
        "book": 0,
    }

    # research paper signals
    for kw in ("abstract", "introduction", "references", "methodology",
               "related work", "doi:", "arxiv"):
        if kw in text_lower:
            scores["research_paper"] += 1

    # policy signals
    for kw in ("policy", "shall comply", "definitions", "scope", "purpose",
               "responsibilities", "enforcement", "effective date"):
        if kw in text_lower:
            scores["policy"] += 1

    # standard signals
    if re.search(r"\b[A-Z]{2,5}_[A-Z]{2,5}\.\d", text):        # e.g. FDP_ACC.1
        scores["standard"] += 3
    for kw in ("iso/iec", "requirement", "conformance", "annex",
               "shall", "clause"):
        if kw in text_lower:
            scores["standard"] += 1

    # book signals: has a real TOC/bookmarks, or "chapter" appears repeatedly
    toc = get_embedded_toc(pdf_path)
    if len(toc) > 3:
        scores["book"] += 3
    scores["book"] += text_lower.count("chapter")

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    confidence = best_score / max(sum(scores.values()), 1)

    if best_score == 0 or confidence < 0.35:
        return "generic", scores
    return best_type, scores


# ---------------------------------------------------------------------------
# Table extraction (pdfplumber does this better than PyMuPDF)
# ---------------------------------------------------------------------------

def extract_tables(pdf_path: str) -> list[Element]:
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            for tbl in page.extract_tables():
                if not tbl or len(tbl) < 2:
                    continue
                rows = [[c if c is not None else "" for c in row] for row in tbl]
                tables.append(Element(
                    type="table",
                    text="\n".join(" | ".join(r) for r in rows),
                    page=page_num + 1,
                    meta={"rows": rows, "n_rows": len(rows), "n_cols": len(rows[0])},
                ))
    return tables


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_document(
    pdf_path: str,
    doc_type: str = "auto",
    id_patterns: Optional[dict[str, str]] = None,
    include_tables: bool = True,
) -> dict:
    """
    Parse a text-based PDF into normalized structural elements.

    Args:
        pdf_path: path to the PDF file.
        doc_type: one of "book" | "policy" | "standard" | "research_paper" |
                  "journal" | "generic" | "auto". "auto" runs a cheap
                  heuristic classifier and falls back to "generic" when
                  unsure -- use this for mixed/unlabeled batch ingestion.
                  Prefer an explicit type whenever you know it; auto-detect
                  is a convenience, not a guarantee.
        id_patterns: only used when doc_type == "standard". Dict of
                  {pattern_name: regex} for domain identifiers to tag
                  (e.g. CC component IDs, ISO clause refs, RFC section refs).
        include_tables: whether to run pdfplumber table extraction.

    Returns:
        {
          "doc_type": str,          # the type actually used (post auto-detect)
          "detection_scores": dict, # present only when doc_type=="auto" was passed
          "toc": [(level, title, page), ...],   # empty if no embedded bookmarks
          "elements": [Element.to_dict(), ...],  # in reading order, tables appended
        }
    """
    detection_scores = None
    if doc_type == "auto":
        doc_type, detection_scores = detect_doc_type(pdf_path)

    raw_spans, toc = extract_raw_spans_and_toc(pdf_path)  # single open, not two
    raw_spans = strip_headers_footers(raw_spans)
    lines = group_lines(raw_spans)
    body_size = compute_body_font_size(raw_spans)

    detector_cls = DETECTORS.get(doc_type, BaseDetector)
    if doc_type == "standard":
        detector = detector_cls(body_size, id_patterns=id_patterns)
    else:
        detector = detector_cls(body_size)

    elements = detector.detect(lines)

    if include_tables:
        elements = elements + extract_tables(pdf_path)
        elements.sort(key=lambda e: e.page)

    result = {
        "doc_type": doc_type,
        "toc": toc,
        "elements": [e.to_dict() for e in elements],
    }
    if detection_scores is not None:
        result["detection_scores"] = detection_scores
    return result


if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 2:
        print("Usage: python doc_parser.py <pdf_path> [doc_type]")
        sys.exit(1)

    path = sys.argv[1]
    dtype = sys.argv[2] if len(sys.argv) > 2 else "auto"
    result = parse_document(path, doc_type=dtype)
    print(f"doc_type={result['doc_type']}  toc_entries={len(result['toc'])}  "
          f"elements={len(result['elements'])}")
    for el in result["elements"][:20]:
        print(f"[{el['type']:<16}] p{el['page']:<4} {el['text'][:80]}")