from __future__ import annotations

import argparse
import json
import os
import time
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, NamedTuple
import multiprocessing as mp


# Canonical section labels we emit
CANON = {"abstract", "introduction", "methods", "results", "complications", "discussion", "other"}
CANONICAL_PATH_DEFAULT = Path("data/index/canonical_papers.jsonl")


# Chunk sizes
CHUNK_SIZE = 2400
CHUNK_OVERLAP = 200
ABSTRACT_CHUNK_SIZE = 1400
ABSTRACT_OVERLAP = 150


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[\t\f\v]+", " ", s)
    return s.strip()


_CITES_RE = re.compile(r"\[\s*\d+(?:\s*[\-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[\-–]\s*\d+)?)*\s*\]")
def strip_inline_citations(s: str) -> str:
    if not s:
        return s
    return _CITES_RE.sub("", s)


def iter_windows(text: str, start: int, end: int, size: int, overlap: int) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    pos = start
    while pos < end:
        ce = min(pos + size, end)
        spans.append((pos, ce))
        if ce >= end:
            break
        pos = max(pos + size - overlap, pos + 1)
    return spans


# Header detection stoplist (boundaries but skipped)

STOP_HEADER_PATTERNS = [
    re.compile(r"(?m)^\s*TITLE\s*:?$", re.I),
    re.compile(r"(?m)^\s*ABBREVIATIONS\s*:?$", re.I),
    re.compile(r"(?m)^\s*ACKNOWLEDG(E)?MENTS?\s*:?$", re.I),
    re.compile(r"(?m)^\s*FUNDING\s*:?$", re.I),
    re.compile(r"(?m)^\s*AUTHOR(S)?\s+AND\s+AFFILIATIONS\s*:?$", re.I),
    re.compile(r"(?m)^\s*AUTHOR\s+INFORMATION\s*:?$", re.I),
    re.compile(r"(?m)^\s*CONTRIBUTIONS\s*:?$", re.I),
    re.compile(r"(?m)^\s*CORRESPONDING\s+AUTHORS?\s*:?$", re.I),
    re.compile(r"(?m)^\s*ETHICS(\s+DECLARATIONS?)?\s*:?$", re.I),
    re.compile(r"(?m)^\s*ETHICAL\s+APPROVAL.*$", re.I),
    re.compile(r"(?m)^\s*CONSENT\s+FOR\s+PUBLICATION\s*:?$", re.I),
    re.compile(r"(?m)^\s*CLINICAL\s+TRIALS?\s+REGISTRATION\s*:?$", re.I),
    re.compile(r"(?m)^\s*TRIAL\s+REGISTRATION\s*:?$", re.I),
    re.compile(r"(?m)^\s*SUPPLEMENTARY\s+INFORMATION\s*:?$", re.I),
    re.compile(r"(?m)^\s*RIGHTS\s+AND\s+PERMISSIONS\s*:?$", re.I),
    re.compile(r"(?m)^\s*ABOUT\s+THIS\s+ARTICLE\s*:?$", re.I),
    re.compile(r"(?m)^\s*DATA\s+AVAILABILITY\s*:?$", re.I),
    re.compile(r"(?m)^\s*SIMILAR\s+CONTENT\s+BEING\s+VIEWED\s+BY\s+OTHERS\s*:?$", re.I),
    re.compile(r"(?m)^\s*REFERENCES\s*:?$", re.I),
]


class HeaderHit(NamedTuple):
    title: str
    start: int
    end: int
    is_stop: bool


def _build_master_header_patterns() -> Tuple[re.Pattern, re.Pattern]:
    """
    Build master regexes for *single-line* fullmatches (candidate lines only).
    Keep patterns bounded to avoid catastrophic backtracking.
    """
    core_terms = [
        r"ABSTRACT", r"INTRODUCTION", r"BACKGROUND", r"AIM", r"AIMS", r"OBJECTIVE", r"OBJECTIVES",
        r"MATERIALS\s+AND\s+METHODS", r"(?:SUBJECTS|PATIENTS)\s+AND\s+METHODS",
        r"STUDY\s+DESIGN", r"PARTICIPANTS", r"METHODS", r"METHODOLOGY", r"RESULTS", r"RESULT", r"FINDINGS",
        r"DISCUSSION", r"CONCLUSION", r"CONCLUSIONS", r"DISCUSSION\s+AND\s+CONCLUSIONS?",
        r"COMPLICATIONS"
    ]
    # Accept ASCII ':' and common Unicode colon variants
    COLON = r"[:\uFF1A\uFE55\uA789]"
    numbered = rf"(?:\d+\.?\s*)?(?:{'|'.join(core_terms)})\s*{COLON}?$"
    bare     = rf"(?:{'|'.join(core_terms)})\s*{COLON}?$"

    # Generic ALL-CAPS and Title Case with colon (safe, good recall)
    # Uppercase-only (no lowercase letters) generic header with optional numeric prefix
    generic_caps_with_colon = rf"(?:\d+\.?\s*)?(?!.*[a-z])[A-Z0-9\s()\[\]{{}}&/\\+,:;\.-]{1,160}{COLON}\s*$"
    patterns = [numbered, bare, generic_caps_with_colon]

    # Title Case like "Related Work:" or "Key Takeaways" (require colon to limit false positives)
    title_word = r"(?:[A-Z][a-z]+|[A-Z]{2,})"
    title_case_with_colon = rf"(?:\d+\.?\s*)?{title_word}(?:\s+{title_word}){0,6}\s*{COLON}\s*$"
    patterns.append(title_case_with_colon)

    target_pat = re.compile(rf"(?m)^\s*(?:{'|'.join(patterns)})", re.IGNORECASE)

    stop_terms = [
        r"TITLE", r"ABBREVIATIONS", r"ACKNOWLEDG(?:E)?MENTS?", r"FUNDING",
        r"AUTHOR(?:S)?\s+AND\s+AFFILIATIONS", r"AUTHOR\s+INFORMATION", r"CONTRIBUTIONS",
        r"CORRESPONDING\s+AUTHORS?", r"ETHICS(?:\s+DECLARATIONS?)?", r"ETHICAL\s+APPROVAL.*",
        r"CONSENT\s+FOR\s+PUBLICATION", r"CLINICAL\s+TRIALS?\s+REGISTRATION",
        r"TRIAL\s+REGISTRATION", r"SUPPLEMENTARY\s+INFORMATION", r"RIGHTS\s+AND\s+PERMISSIONS",
        r"ABOUT\s+THIS\s+ARTICLE", r"DATA\s+AVAILABILITY", r"SIMILAR\s+CONTENT\s+BEING\s+VIEWED\s+BY\s+OTHERS",
        r"REFERENCES"
    ]
    stop_pat = re.compile(rf"(?m)^\s*(?:{'|'.join(stop_terms)})\s*{COLON}?\s*$", re.IGNORECASE)
    return target_pat, stop_pat


_MASTER_TARGET_PAT, _MASTER_STOP_PAT = _build_master_header_patterns()


def _line_candidates(text: str) -> List[Tuple[int, int, str]]:
    """Return [(line_start, line_end, line_text_with_nl), ...] with original offsets preserved."""
    lines: List[Tuple[int, int, str]] = []
    pos = 0
    for ln in text.splitlines(keepends=True):
        start = pos
        end = start + len(ln)
        pos = end
        lines.append((start, end, ln))
    return lines


def _is_quick_header_candidate(ln: str) -> bool:
    """Cheap prefilter: short, endswith ':', numbered prefix, uppercase ratio, or exact common headings."""
    s = ln.strip()
    if not s:
        return False
    if len(s) > 140:
        return False
    if s.endswith(":") or s.endswith("：") or s.endswith("﹕") or s.endswith("꞉"):
        return True
    # "1. INTRODUCTION" etc.
    first = s.split(" ", 1)[0].rstrip(".")
    if first.isdigit():
        return True
    # Uppercase ratio heuristic
    alpha = sum(ch.isalpha() for ch in s)
    if alpha >= 4:
        upper = sum(ch.isupper() for ch in s)
        if upper / max(1, alpha) >= 0.6:
            return True
    # Common bare headers
    if s.lower() in {"introduction", "background", "methods", "results", "discussion", "conclusion", "conclusions", "findings", "participants"}:
        return True
    return False


def fast_find_headers(text: str) -> List[HeaderHit]:
    """Single-pass, line-based header detection using master patterns on filtered candidates."""
    if not text:
        return []
    out: List[HeaderHit] = []
    debug = os.environ.get("EF_CHUNKER_DEBUG") == "1"
    debug_missed = 0

    for (ls, le, ln) in _line_candidates(text):
        if not _is_quick_header_candidate(ln):
            continue
        stripped = ln.strip()
        # Fallback: always accept conclusion-like headers with colon
        if stripped.endswith(":") and ("conclusion" in stripped.lower()):
            out.append(HeaderHit(stripped, ls, le, False))
            continue
        if _MASTER_STOP_PAT.fullmatch(stripped):
            out.append(HeaderHit(stripped, ls, le, True))
        elif _MASTER_TARGET_PAT.fullmatch(stripped):
            out.append(HeaderHit(stripped, ls, le, False))
        elif debug and debug_missed < 10:
            debug_missed += 1
            try:
                print(f"[EF_CHUNKER_DEBUG] candidate not matched: '{stripped[:160]}'", flush=True)
            except Exception:
                pass

    if not out:
        return []
    # Dedup by start index; keep first occurrence
    by_start: Dict[int, HeaderHit] = {}
    for h in out:
        by_start.setdefault(h.start, h)
    return sorted(by_start.values(), key=lambda h: h.start)


def find_headers(text: str) -> List[Tuple[str, int, int]]:
    """Detect section headers with time and count guards to avoid pathological cases."""
    hits_fast = fast_find_headers(text)
    return [(h.title, h.start, h.end) for h in hits_fast]


def is_stop_header(title: str) -> bool:
    t = (title or "").strip()
    if _MASTER_STOP_PAT.fullmatch(t):
        return True
    for pat in STOP_HEADER_PATTERNS:  # fallback
        if pat.search(t):
            return True
    return False


def canonicalize(title: str) -> str:
    t = (title or "").lower()
    if "abstract" in t:
        return "abstract"
    if "introduction" in t:
        return "introduction"
    if "background" in t:
        return "introduction"
    # Review-style topical headings → discussion
    if "pathophysiology" in t:
        return "introduction"
    if any(k in t for k in ("management", "treatment", "therapy", "pharmacotherapy")):
        return "discussion"
    if any(k in t for k in ("future directions", "limitations", "perspectives", "outlook", "conclusion")):
        return "discussion"
    if re.search(r"\b(aim|aims|objective|objectives)\b", t):
        return "introduction"
    if "method" in t or re.search(r"\b(subjects|patients)\s+and\s+methods\b", t) or "study design" in t or "participants" in t:
        return "methods"
    if re.search(r"\bresults\b", t) or "findings" in t:
        return "results"
    if "complications" in t or "adverse" in t:
        return "complications"
    if any(k in t for k in ("discussion", "conclusion")):
        return "discussion"
    return "other"


def detect_structured_abstract_range(text: str) -> Optional[Tuple[int, int]]:
    """Detect a structured abstract region embedded near the top of fulltext and bound it conservatively.

    Heuristic:
    - Look for an ABSTRACT header within the first ~1000 chars
    - Consider the structured abstract to end at the first INTRODUCTION header (numbered or plain),
      if it appears within a reasonable window (e.g., 20k chars) after the ABSTRACT.
    - This avoids capturing the entire paper when stop-list headers (e.g., REFERENCES) occur much later.
    """
    if not text:
        return None
    m_abs = re.search(r"(?m)^\s*Abstract\s*:?$", text[:1000]) or re.search(r"(?m)^\s*ABSTRACT\s*:?$", text[:1000])
    if not m_abs:
        return None
    start = m_abs.start()
    # Find the first INTRODUCTION-style header after ABSTRACT (numbered or plain), bounded window
    intro_pat = re.compile(r"(?m)^\s*(?:\d+\.?\s*)?INTRODUCTION\s*:?\s*$", re.I)
    SEARCH_WINDOW = 20000
    search_end = min(len(text), start + SEARCH_WINDOW)
    m_intro = intro_pat.search(text, pos=start + 1, endpos=search_end)
    if not m_intro:
        return None
    end = m_intro.start()
    if end <= start:
        return None
    region = text[start:end]
    # Require at least two structured-abstract components inside the region to reduce false positives
    comps = 0
    for pat in (
        re.compile(r"(?m)^\s*Background\s*:?$", re.I),
        re.compile(r"(?m)^\s*Methods\s*:?$", re.I),
        re.compile(r"(?m)^\s*Results\s*:?$", re.I),
        re.compile(r"(?m)^\s*Conclusions?\s*:?$", re.I),
    ):
        if pat.search(region):
            comps += 1
    return (start, end) if comps >= 2 else None


def process_single_store_json(store_json_path: Path) -> Tuple[List[Dict], Optional[Dict[str, Any]]]:
    rec = json.loads(store_json_path.read_text(encoding="utf-8"))
    pmid = str(rec.get("pmid") or "")
    abstract = normalize_text(rec.get("abstract") or rec.get("abstract_text") or "")
    fulltext = normalize_text(rec.get("fulltext_text") or "")
    fulltext = strip_inline_citations(fulltext)

    # Detect abstract-only
    abstract_only = False
    sources = rec.get("sources") or {}
    if isinstance(sources, dict):
        for _k, src in sources.items():
            try:
                if str((src or {}).get("status") or "").lower() == "abstract_only":
                    abstract_only = True
                    break
            except Exception:
                pass
    if not abstract_only and abstract and fulltext and abstract.strip() == fulltext.strip():
        abstract_only = True

    chunks: List[Dict] = []
    relabel_meta: Optional[Dict[str, Any]] = None

    # Emit abstract first
    if abstract:
        a = strip_inline_citations(abstract)
        if len(a) <= ABSTRACT_CHUNK_SIZE * 1.25:
            chunks.extend(_chunk_section(a, "Abstract", "abstract", len(a), 0))
        else:
            chunks.extend(_chunk_section(a, "Abstract", "abstract", ABSTRACT_CHUNK_SIZE, ABSTRACT_OVERLAP))

    if abstract_only or not fulltext:
        for c in chunks:
            c["pmid"] = pmid
        return chunks, None

    # Remove structured abstract region from fulltext for section detection
    sa = detect_structured_abstract_range(fulltext)
    full_for_sections = fulltext
    if sa:
        s0, e0 = sa
        # Emit the structured abstract region as abstract if no separate abstract was provided
        if not abstract:
            sa_text = fulltext[s0:e0]
            a = strip_inline_citations(sa_text)
            if len(a) <= ABSTRACT_CHUNK_SIZE * 1.25:
                chunks.extend(_chunk_section(a, "Abstract", "abstract", len(a), 0))
            else:
                chunks.extend(_chunk_section(a, "Abstract", "abstract", ABSTRACT_CHUNK_SIZE, ABSTRACT_OVERLAP))
        full_for_sections = fulltext[:s0] + "\n" * (e0 - s0) + fulltext[e0:]

    # Detect headers (targets + stops) and slice sections header → next_header
    hits = fast_find_headers(full_for_sections)

    if hits:
        for i, h in enumerate(hits):
            if h.is_stop:
                continue  # skip emitting stop sections but keep as boundaries
            sec_start = h.end  # content starts after the header line
            sec_end = hits[i + 1].start if (i + 1) < len(hits) else len(fulltext)
            if sec_end <= sec_start:
                continue
            body = fulltext[sec_start:sec_end]
            if not body.strip():
                continue
            canon = canonicalize(h.title)
            if canon == "abstract":
                continue
            if canon not in CANON:
                canon = "other"
            chunks.extend(_chunk_section(body, h.title.strip(), canon, CHUNK_SIZE, CHUNK_OVERLAP))
    else:
        # Fallback: no headers detected → chunk the whole body (excluding structured abstract)
        if sa:
            s0, e0 = sa
            body_fallback = (fulltext[:s0] + fulltext[e0:]).strip()
        else:
            body_fallback = fulltext.strip()
        if body_fallback:
            chunks.extend(_chunk_section(body_fallback, "Body", "other", CHUNK_SIZE, CHUNK_OVERLAP))

    # Chunk-time relabel based on section distribution: relaxed narrative-review heuristic
    try:
        sec_counts = Counter(c.get("section_norm") for c in chunks)
        total_chunks = len(chunks)
        no_methods = sec_counts.get("methods", 0) == 0
        no_results = sec_counts.get("results", 0) == 0
        has_core_text = (
            sec_counts.get("abstract", 0) >= 1
            or sec_counts.get("introduction", 0) >= 1
            or sec_counts.get("discussion", 0) >= 1
        )
        # Assume narrative-review if there are no methods and no results, and at least some core text
        # Require minimal chunk count to avoid trivial/abstract-only mislabels
        if no_methods and no_results and has_core_text and total_chunks >= 3:
            relabel_meta = {
                "pmid": pmid,
                "doc_kind": "narrative_review",
                "banking_eligible": False,
                "study_strength": 0.2,
                "override_source": "chunk-distribution",
            }
            for c in chunks:
                c["doc_kind"] = relabel_meta["doc_kind"]
                c["banking_eligible"] = relabel_meta["banking_eligible"]
                c["study_strength"] = relabel_meta["study_strength"]
                c["override_source"] = relabel_meta["override_source"]
        # Banking eligibility rule: require a results section
        if no_results:
            for c in chunks:
                c["banking_eligible"] = False
    except Exception:
        pass
    # Annotate pmid once at the end
    for c in chunks:
        c["pmid"] = pmid
    return chunks, relabel_meta


def _chunk_section(text: str, sec_raw: str, canon: str, chunk_size: int, overlap: int) -> List[Dict]:
    out: List[Dict] = []
    for cs, ce in iter_windows(text, 0, len(text), chunk_size, overlap):
        out.append({
            "section": sec_raw,
            "section_norm": canon,
            "start": cs,
            "end": ce,
            "text": text[cs:ce],
        })
    return out


def _write_chunks(out_path: Path, chunks: List[Dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.parent / (out_path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in chunks:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _safe_replace(tmp_path, out_path)


def _safe_replace(src_tmp: Path, dst_final: Path, attempts: int = 8, delay: float = 0.15) -> None:
    last_err: Optional[Exception] = None
    for _ in range(attempts):
        try:
            os.replace(src_tmp, dst_final)
            return
        except (PermissionError, FileNotFoundError) as e:
            last_err = e
            time.sleep(delay)
    # Final attempt: remove destination and replace
    try:
        if dst_final.exists():
            os.remove(dst_final)
        os.replace(src_tmp, dst_final)
        return
    except Exception:
        pass
    # If still failing, raise last error
    if last_err:
        raise last_err


def _write_report_atomic(report_path: Path, reports: List[Dict]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = report_path.parent / (report_path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as rf:
        for r in reports:
            rf.write(json.dumps(r, ensure_ascii=False) + "\n")
    _safe_replace(tmp_path, report_path)


def _batch_update_canonical(canonical_path: Path, relabel_updates: Dict[str, Dict[str, Any]]) -> None:
    """Retro-update canonical_papers.jsonl with relabeled doc_kind/banking_eligible/study_strength.
    Keeps other fields intact; writes to .tmp then atomic replace.
    """
    if not canonical_path.exists():
        return
    updated_lines: List[str] = []
    with canonical_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                updated_lines.append(line)
                continue
            pmid_key = str(obj.get("pmid") or obj.get("paper_id") or obj.get("id") or "")
            upd = relabel_updates.get(pmid_key)
            if upd:
                obj["study_type"] = upd.get("doc_kind", obj.get("study_type"))
                obj["banking_eligible"] = upd.get("banking_eligible", obj.get("banking_eligible"))
                obj["study_strength"] = upd.get("study_strength", obj.get("study_strength"))
                obj["reliability_score"] = 3  # per rules for narrative-review
                obj["override_source"] = upd.get("override_source", "chunk-distribution")
            updated_lines.append(json.dumps(obj, ensure_ascii=False))
    tmp = canonical_path.with_suffix(canonical_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for ln in updated_lines:
            f.write(ln + "\n")
    _safe_replace(tmp, canonical_path)


def _validate_lengths(store_json: Path, chunks: List[Dict]) -> Dict:
    rec = json.loads(store_json.read_text(encoding="utf-8"))
    ft = strip_inline_citations(normalize_text(rec.get("fulltext_text") or ""))
    ab = strip_inline_citations(normalize_text(rec.get("abstract") or rec.get("abstract_text") or ""))
    cnt = Counter(c.get("section_norm") for c in chunks)
    total_chars = sum(len(c.get("text") or "") for c in chunks)
    return {
        "pmid": rec.get("pmid"),
        "sections": dict(cnt),
        "chunks": len(chunks),
        "sum_chunk_text": total_chars,
        "len_fulltext_norm_no_cites": len(ft),
        "len_abstract_norm_no_cites": len(ab),
    }


def _process_path(p: Path) -> Tuple[Path, Tuple[List[Dict], Optional[Dict[str, Any]]]]:
    return p, process_single_store_json(p)


def process_dir(
    store_dir: Path,
    out_path: Path,
    report_path: Optional[Path] = None,
    max_files: Optional[int] = None,
    update_canonical: bool = False,
    canonical_path: Path = CANONICAL_PATH_DEFAULT,
    workers: int = 1,
) -> None:
    all_chunks: List[Dict] = []
    reports: List[Dict] = []
    processed = 0
    relabel_updates: Dict[str, Dict[str, Any]] = {}
    total_chunks_emitted = 0
    t_start = time.perf_counter()
    last_print = t_start
    PRINT_EVERY_N = 1000
    PRINT_EVERY_S = 5.0
    # Preselect up to max_files paths to avoid full-tree traversal cost
    selected_paths: List[Path] = []
    for root, _dirs, files in os.walk(store_dir):
        for fn in files:
            if not fn.startswith("pmid_") or not fn.endswith(".json"):
                continue
            selected_paths.append(Path(root) / fn)
            if max_files and len(selected_paths) >= max_files:
                break
        if max_files and len(selected_paths) >= max_files:
            break
    # Announce start to ensure immediate user-visible progress
    try:
        print(f"starting {len(selected_paths)} files...", flush=True)
    except Exception:
        pass
    if workers and workers > 1:
        with mp.Pool(processes=workers) as pool:
            for idx, (p, result) in enumerate(pool.imap_unordered(_process_path, selected_paths, chunksize=8), start=1):
                try:
                    chunks, relabel_meta = result
                except Exception:
                    continue
                all_chunks.extend(chunks)
                if report_path is not None:
                    try:
                        r = _validate_lengths(p, chunks)
                        if relabel_meta:
                            r.update(relabel_meta)
                            relabel_updates[str(relabel_meta.get("pmid") or "")] = relabel_meta
                        reports.append(r)
                    except Exception:
                        pass
                processed += 1
                now = time.perf_counter()
                if (idx % PRINT_EVERY_N == 0) or (now - last_print >= PRINT_EVERY_S):
                    elapsed = now - t_start
                    speed = idx / elapsed if elapsed > 0 else 0.0
                    remaining = max(0, len(selected_paths) - idx)
                    eta = remaining / speed if speed > 0 else 0.0
                    print(f"status: {idx}/{len(selected_paths)} done | {speed:.1f} papers/s | eta {eta:.1f}s", flush=True)
                    last_print = now
    else:
        for idx, p in enumerate(selected_paths, start=1):
            t0 = time.perf_counter()
            try:
                chunks, relabel_meta = process_single_store_json(p)
            except Exception:
                continue
            all_chunks.extend(chunks)
            if report_path is not None:
                try:
                    r = _validate_lengths(p, chunks)
                    if relabel_meta:
                        r.update(relabel_meta)
                        relabel_updates[str(relabel_meta.get("pmid") or "")] = relabel_meta
                    reports.append(r)
                except Exception:
                    pass
            processed += 1
            now = time.perf_counter()
            if (idx % PRINT_EVERY_N == 0) or (now - last_print >= PRINT_EVERY_S):
                elapsed = now - t_start
                speed = idx / elapsed if elapsed > 0 else 0.0
                remaining = max(0, len(selected_paths) - idx)
                eta = remaining / speed if speed > 0 else 0.0
                print(f"status: {idx}/{len(selected_paths)} done | {speed:.1f} papers/s | eta {eta:.1f}s", flush=True)
                last_print = now
    # Finalize outputs
    _write_chunks(out_path, all_chunks)
    print("wrote chunks:", str(out_path), "rows:", len(all_chunks))
    if report_path is not None:
        _write_report_atomic(report_path, reports)
        print("wrote report:", str(report_path), "rows:", len(reports))

    # Optional canonical updates
    if update_canonical and relabel_updates:
        _batch_update_canonical(canonical_path, relabel_updates)


def main() -> None:
    ap = argparse.ArgumentParser(prog="index_prep", description="Splitter + chunker (single file or directory)")
    ap.add_argument("input_path", help="Path to a pmid_XXXX.json file or a fulltext_store directory")
    ap.add_argument("--out", required=True, help="Output chunks JSONL path")
    ap.add_argument("--report", default=None, help="Optional validation report JSONL (defaults to <out>.report.jsonl)")
    ap.add_argument("--max", type=int, default=None, help="Limit files when input_path is a directory")
    ap.add_argument("--update-canonical", action="store_true", help="Update canonical_papers.jsonl with relabels")
    ap.add_argument("--canonical-path", type=Path, default=CANONICAL_PATH_DEFAULT, help="Path to canonical_papers.jsonl")
    args = ap.parse_args()

    input_path = Path(args.input_path)
    out_path = Path(args.out)
    # Default report path if omitted
    report_path: Optional[Path] = Path(args.report) if args.report else Path(str(out_path) + ".report.jsonl")

    if input_path.is_file():
        chunks, relabel_meta = process_single_store_json(input_path)
        _write_chunks(out_path, chunks)
        # Emit single-file report if requested
        if report_path is not None:
            try:
                r = _validate_lengths(input_path, chunks)
                if relabel_meta:
                    r.update(relabel_meta)
                _write_report_atomic(report_path, [r])
            except Exception:
                pass
        cnt = Counter(c["section_norm"] for c in chunks)
        total_chars = sum(len(c.get("text") or "") for c in chunks)
        print("sections:", dict(cnt))
        print("chunks:", len(chunks), "total_chars:", total_chars)
        print("wrote:", str(out_path))
        if relabel_meta and args.update_canonical:
            _batch_update_canonical(args.canonical_path, {str(relabel_meta.get("pmid") or ""): relabel_meta})
    elif input_path.is_dir():
        # Auto workers: min(8, max(1, cpu_count()-1))
        cpu = os.cpu_count() or 1
        auto_workers = max(1, min(8, cpu - 1))
        process_dir(
            input_path,
            out_path,
            report_path,
            args.max,
            update_canonical=bool(args.update_canonical),
            canonical_path=args.canonical_path,
            workers=auto_workers,
        )
    else:
        raise SystemExit(f"input_path not found: {input_path}")


if __name__ == "__main__":
    main()

