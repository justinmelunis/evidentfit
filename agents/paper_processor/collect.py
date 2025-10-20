from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Optional DB import; we fall back to JSONL if not available
try:
    import psycopg  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None

SECTION_ORDER = ["abstract", "methods", "results", "discussion"]


def _read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    tmp.replace(path)


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


@dataclass
class SectionBundle:
    paper_id: str
    meta: dict
    sections: Dict[str, dict]
    stats: dict
    input_hash: str
    generated_at: str


def _load_meta_map(canonical_path: Path) -> Dict[str, dict]:
    meta_map: Dict[str, dict] = {}
    for rec in _read_jsonl(canonical_path):
        pid = str(rec.get("paper_id") or rec.get("pmid") or rec.get("id"))
        if not pid:
            continue
        # store the whole record so we can fallback to abstract if needed
        meta_map[pid] = rec
    return meta_map


def _collect_from_db(paper_id: str) -> List[Tuple[str, str, int, str]]:
    """
    Returns list of (chunk_id, section_norm, start, text)
    """
    dsn = os.getenv("EVIDENTFIT_DB_DSN")
    if not dsn or psycopg is None:
        return []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, section_norm, start, text
                FROM ef_chunks
                WHERE paper_id = %s
                  AND section_norm IN ('abstract','methods','results','discussion')
                ORDER BY section_norm, start
                """,
                (paper_id,),
            )
            rows = cur.fetchall()
    return [(r[0], r[1], int(r[2] or 0), r[3]) for r in rows]


def _collect_from_jsonl(paper_id: str, chunks_path: Path) -> List[Tuple[str, str, int, str]]:
    out: List[Tuple[str, str, int, str]] = []
    for rec in _read_jsonl(chunks_path):
        if str(rec.get("paper_id")) != str(paper_id):
            continue
        sec = (rec.get("section_norm") or "").lower()
        if sec not in SECTION_ORDER:
            continue
        out.append((rec.get("chunk_id"), sec, int(rec.get("start") or 0), rec.get("text") or ""))
    # preserve ordering by section then start
    out.sort(key=lambda r: (SECTION_ORDER.index(r[1]), r[2]))
    return out


def build_section_bundle(
    paper_id: str,
    canonical_path: Path,
    chunks_path: Optional[Path] = None,
    meta_map: Optional[Dict[str, dict]] = None,
) -> SectionBundle:
    log = logging.getLogger("paper_processor.collect")
    """
    Build a deterministic section bundle for a paper_id.
    Prefers DB; falls back to chunks.jsonl if DSN/driver not available.
    """
    meta_map = meta_map or _load_meta_map(canonical_path)
    meta = meta_map.get(str(paper_id), {})

    rows = _collect_from_db(paper_id)
    if not rows:
        if not chunks_path:
            raise RuntimeError("No DB available and chunks_path was not provided")
        rows = _collect_from_jsonl(paper_id, chunks_path)

    by_section: Dict[str, List[Tuple[str, int, str]]] = defaultdict(list)
    ordered_chunk_ids: List[str] = []
    for chunk_id, section, start, text in rows:
        by_section[section].append((chunk_id, start, text))
        ordered_chunk_ids.append(chunk_id)

    sections_payload: Dict[str, dict] = {}
    total_chunks = 0
    for sec in SECTION_ORDER:
        items = sorted(by_section.get(sec, []), key=lambda r: r[1])
        texts = [t for _, __, t in items]
        text = ("\n\n").join(texts) if texts else ""
        cids = [cid for cid, __, ___ in items]
        sections_payload[sec] = {
            "text": text,
            "chunks": cids,
            "char_len": len(text),
        }
        total_chunks += len(items)

    has_fulltext = any(sections_payload[sec]["char_len"] > 0 for sec in ("methods", "results", "discussion"))

    # Abstract fallback from canonical if no abstract text in chunks
    # We only fill abstract; we do not change has_fulltext and we keep chunk list empty.
    if sections_payload["abstract"]["char_len"] == 0:
        canon_abs = meta.get("abstract") if isinstance(meta, dict) else None
        if not canon_abs:
            canon_abs = (meta.get("title_abstract") if isinstance(meta, dict) else None) or (meta.get("summary") if isinstance(meta, dict) else None)
        if isinstance(canon_abs, str) and canon_abs.strip():
            abs_text = canon_abs.strip()
            sections_payload["abstract"]["text"] = abs_text
            sections_payload["abstract"]["char_len"] = len(abs_text)
            sections_payload["abstract"]["chunks"] = []  # no chunk provenance for canonical abstract fallback
            log.info("Abstract fallback used for paper_id=%s from canonical file", paper_id)

    # Deterministic input hash
    per_section_lengths = [str(sections_payload[s]["char_len"]) for s in SECTION_ORDER]
    input_key = "|".join([str(paper_id)] + ordered_chunk_ids + per_section_lengths)
    input_hash = _sha1(input_key)

    bundle = SectionBundle(
        paper_id=str(paper_id),
        meta=meta,
        sections=sections_payload,
        stats={"n_chunks": total_chunks, "has_fulltext": bool(has_fulltext)},
        input_hash=input_hash,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return bundle


def write_bundle(bundle: SectionBundle, dest_dir: Path) -> Path:
    out_path = dest_dir / f"{bundle.paper_id}.json"
    payload = {
        "paper_id": bundle.paper_id,
        "meta": bundle.meta,
        "sections": bundle.sections,
        "stats": bundle.stats,
        "input_hash": bundle.input_hash,
        "generated_at": bundle.generated_at,
    }
    _atomic_write_json(out_path, payload)
    return out_path


if __name__ == "__main__":
    # Quick manual smoke:
    # python -m agents.paper_processor.collect 33562750
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("paper_id")
    parser.add_argument("--canonical", default="data/index/canonical_papers.jsonl")
    parser.add_argument("--chunks", default="data/index/chunks.jsonl")
    parser.add_argument("--outdir", default="data/cards/_raw")
    args = parser.parse_args()
    bundle = build_section_bundle(
        paper_id=args.paper_id,
        canonical_path=Path(args.canonical),
        chunks_path=Path(args.chunks),
    )
    path = write_bundle(bundle, Path(args.outdir))
    print(str(path))


