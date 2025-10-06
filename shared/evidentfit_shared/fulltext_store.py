"""
Full-text store utilities for EvidentFit.

Responsibilities:
  - Resolve store root from PROJECT_ROOT and env (FULLTEXT_STORE_DIR)
  - Stable sharding (sha1, 2-level hex: 2 chars / 2 chars)
  - Atomic JSON read/write
  - Keying strategy (prefer pmid_*, fallback to doi_* or title hash)
  - Iteration helpers and a simple manifest
  - Read the latest selection pointer (data/ingest/runs/latest.json)
"""

from __future__ import annotations
import os
import json
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Any, Generator, Iterable, Optional, Tuple

from .utils import PROJECT_ROOT

# Env var can be absolute or relative to PROJECT_ROOT
_FULLTEXT_DIR_ENV = os.getenv("FULLTEXT_STORE_DIR", "data/fulltext_store")

def resolve_fulltext_root() -> Path:
    root = Path(_FULLTEXT_DIR_ENV)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    return root

# ---- Sharding & keys ------------------------------------------------------

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def shard_for_key(key: str) -> Tuple[str, str]:
    """
    Returns (lvl1, lvl2) using first four hex chars of sha1(key), split 2/2.
    """
    h = _sha1(key)
    return h[:2], h[2:4]

def sanitize_doi(doi: str) -> str:
    # keep it readable, remove problematic filesystem characters
    # Keep alphanumeric, dots, hyphens, underscores
    import re
    s = doi.strip().lower()
    # Replace common DOI separators with underscores
    s = s.replace("/", "_").replace("\\", "_").replace(" ", "_")
    # Remove or replace other problematic characters
    s = re.sub(r'[<>:"|?*\(\)\[\]{}]', '', s)
    # Collapse multiple underscores
    s = re.sub(r'_+', '_', s)
    return s

def choose_doc_key(paper_like: Dict[str, Any]) -> Tuple[str, str]:
    """
    Determine a stable key and key_type from a paper dict.
    Priority: pmid_* > doi_* > hash_*
    """
    pmid = str(paper_like.get("pmid") or "").strip()
    if pmid and pmid.isdigit():
        return f"pmid_{pmid}", "pmid"

    doi = paper_like.get("doi")
    if doi:
        sanitized = sanitize_doi(str(doi))
        if sanitized and sanitized != "_":  # Ensure we got something meaningful
            return f"doi_{sanitized}", "doi"

    # Fallback: hash of title+year+journal for better uniqueness
    title = str(paper_like.get("title") or "").strip()
    year = str(paper_like.get("year") or "")
    journal = str(paper_like.get("journal") or "").strip()
    
    # Create a meaningful hash input
    hash_input = f"{title}|{journal}|{year}"
    if not title and not journal:
        # Last resort: use the entire dict representation
        hash_input = str(sorted(paper_like.items()))
    
    h = _sha1(hash_input)
    return f"hash_{h[:16]}", "hash"

def doc_path_for_key(store_root: Path, key: str) -> Path:
    lvl1, lvl2 = shard_for_key(key)
    return store_root / lvl1 / lvl2 / f"{key}.json"

# ---- Atomic I/O -----------------------------------------------------------

def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ---- Public save/load -----------------------------------------------------

def save_fulltext_document(
    paper_stub: Dict[str, Any],
    payload: Dict[str, Any],
    store_root: Optional[Path] = None
) -> Path:
    """
    Save a full-text payload keyed by pmid/doi, returns file path.
    'payload' shape is caller-defined (we don't enforce fields).
    We augment with minimally helpful metadata.
    """
    root = store_root or resolve_fulltext_root()
    key, key_type = choose_doc_key(paper_stub)
    path = doc_path_for_key(root, key)

    record = dict(payload)  # shallow copy
    meta = {
        "key": key,
        "key_type": key_type,
        "pmid": paper_stub.get("pmid"),
        "doi": paper_stub.get("doi"),
        "title": paper_stub.get("title"),
        "journal": paper_stub.get("journal"),
        "year": paper_stub.get("year"),
        "saved_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    # Non-destructively tuck meta under _store
    record.setdefault("_store", {}).update(meta)

    _write_json_atomic(path, record)
    return path

def load_fulltext_document_by_key(key: str, store_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    root = store_root or resolve_fulltext_root()
    path = doc_path_for_key(root, key)
    if not path.exists():
        return None
    return _read_json(path)

def document_exists(paper_stub: Dict[str, Any], store_root: Optional[Path] = None) -> bool:
    """Check if a document already exists in the store."""
    root = store_root or resolve_fulltext_root()
    key, _ = choose_doc_key(paper_stub)
    path = doc_path_for_key(root, key)
    return path.exists()

def get_document_path(paper_stub: Dict[str, Any], store_root: Optional[Path] = None) -> Path:
    """Get the storage path for a document without loading it."""
    root = store_root or resolve_fulltext_root()
    key, _ = choose_doc_key(paper_stub)
    return doc_path_for_key(root, key)

def load_by_pmid(pmid: str, store_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Convenience method to load a document by PMID."""
    return load_fulltext_document_by_key(f"pmid_{pmid}", store_root)

def load_by_doi(doi: str, store_root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Convenience method to load a document by DOI."""
    sanitized = sanitize_doi(doi)
    return load_fulltext_document_by_key(f"doi_{sanitized}", store_root)

# ---- Iteration & manifest -------------------------------------------------

def iter_fulltext_paths(store_root: Optional[Path] = None) -> Generator[Path, None, None]:
    root = store_root or resolve_fulltext_root()
    if not root.exists():
        return
    # two-level shard dirs
    for lvl1 in root.iterdir():
        if not lvl1.is_dir() or len(lvl1.name) != 2:
            continue
        for lvl2 in lvl1.iterdir():
            if not lvl2.is_dir() or len(lvl2.name) != 2:
                continue
            for jf in lvl2.glob("*.json"):
                yield jf

def build_manifest(store_root: Optional[Path] = None) -> Dict[str, Any]:
    root = store_root or resolve_fulltext_root()
    total = 0
    pmc_ok = 0
    supplements: Dict[str, int] = {}

    for p in iter_fulltext_paths(root):
        try:
            data = _read_json(p)
            total += 1
            # Heuristic: if source or flags says 'pmc' ok
            src = str(data.get("source") or data.get("_store", {}).get("source") or "").lower()
            if "pmc" in src:
                pmc_ok += 1
            # Optional supplement tally if present
            supps = data.get("supplements") or data.get("_store", {}).get("supplements")
            # Handle different formats: list, comma-separated string, or single value
            if isinstance(supps, list):
                supp_list = supps
            elif isinstance(supps, str) and supps:
                # Handle comma-separated string
                supp_list = [s.strip() for s in supps.split(",") if s.strip()]
            elif supps:
                supp_list = [supps]
            else:
                supp_list = []
            
            for s in supp_list:
                if not s:
                    continue
                s_norm = str(s).strip().lower()
                if s_norm:
                    supplements[s_norm] = supplements.get(s_norm, 0) + 1
        except Exception:
            # Skip corrupt files
            continue

    pct = (pmc_ok / total * 100.0) if total else 0.0
    return {
        "store_root": str(root.as_posix()),
        "total": total,
        "pmc_ok": pmc_ok,
        "pmc_ok_percent": round(pct, 2),
        "supplement_counts": dict(sorted(supplements.items(), key=lambda x: x[1], reverse=True))
    }

# ---- Latest pointer -------------------------------------------------------

def read_latest_pointer() -> Optional[Dict[str, Any]]:
    """
    Read data/ingest/runs/latest.json to find the most-recent selection output.
    """
    latest = PROJECT_ROOT / "data" / "ingest" / "runs" / "latest.json"
    if not latest.exists():
        return None
    return _read_json(latest)

def read_pm_papers_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    """
    Stream records from pm_papers.jsonl
    """
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
