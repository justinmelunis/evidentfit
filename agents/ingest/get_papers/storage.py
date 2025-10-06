"""
Local storage for get_papers agent

Handles writing selected papers to JSONL and metadata to JSON files.
No Azure calls - pure local file operations.
"""

import os
import json
import shutil
import gzip
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from evidentfit_shared.utils import PROJECT_ROOT

RUNS_BASE_DIR = PROJECT_ROOT / os.getenv("RUNS_BASE_DIR", "data/ingest/runs")
COMPRESS_PAPERS = os.getenv("COMPRESS_PAPERS", "false").lower() == "true"
KEEP_LAST_RUNS = int(os.getenv("KEEP_LAST_RUNS", "8"))

def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)

def _now_run_id() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def create_run_dir(run_id: str | None = None) -> Tuple[str, Path]:
    rid = run_id or _now_run_id()
    run_dir = RUNS_BASE_DIR / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    return rid, run_dir

def prune_old_runs(keep_last: int = KEEP_LAST_RUNS) -> None:
    if keep_last <= 0 or not RUNS_BASE_DIR.exists():
        return
    # keep only the most recent N timestamped dirs (YYYYMMDD_HHMMSS)
    dirs = [p for p in RUNS_BASE_DIR.iterdir() if p.is_dir()]
    dirs = [p for p in dirs if len(p.name) == 15 and "_" in p.name and p.name.replace("_","").isdigit()]
    dirs.sort(key=lambda p: p.name, reverse=True)
    for d in dirs[keep_last:]:
        shutil.rmtree(d, ignore_errors=True)

def _papers_filename(run_dir: Path) -> Path:
    return run_dir / ("pm_papers.jsonl.gz" if COMPRESS_PAPERS else "pm_papers.jsonl")

def _metadata_filename(run_dir: Path) -> Path:
    return run_dir / "metadata.json"

def save_selected_papers(selected_docs: List[Dict], run_dir: Path) -> Path:
    """Write selected docs as JSONL (optionally gz) into the run dir. Returns file path."""
    out_path = _papers_filename(run_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    if COMPRESS_PAPERS:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            for d in selected_docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    else:
        with open(tmp, "w", encoding="utf-8") as f:
            for d in selected_docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    os.replace(tmp, out_path)
    return out_path

def save_run_metadata(metadata: Dict[str, Any], run_dir: Path) -> Path:
    """Write metadata.json into the run dir."""
    meta_path = _metadata_filename(run_dir)
    _atomic_write_text(meta_path, json.dumps(metadata, indent=2, ensure_ascii=False))
    return meta_path

def save_protected_quota_report(report: Dict[str, Any], run_dir: Path) -> Path:
    """Write protected-quota report (per-supp reserved vs kept) into the run dir."""
    out = run_dir / "protected_quota_report.json"
    _atomic_write_text(out, json.dumps(report, indent=2, ensure_ascii=False))
    return out

def update_latest_pointer(
    run_id: str,
    run_dir: Path,
    papers_path: Path,
    metadata_path: Path,
    fulltext_dir: Optional[Path] = None,
    fulltext_store_dir: Optional[Path] = None,
    fulltext_manifest: Optional[Path] = None,
) -> Path:
    """Write a small pointer file with paths to latest artifacts."""
    pointer = {
        "run_id": run_id,
        "run_dir": str(run_dir.as_posix()),
        "papers_path": str(papers_path.as_posix()),
        "metadata_path": str(metadata_path.as_posix()),
        "created_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    if fulltext_dir and fulltext_dir.exists():
        pointer["fulltext_dir"] = str(fulltext_dir.as_posix())  # kept for backward compat if ever used
    if fulltext_store_dir:
        pointer["fulltext_store_dir"] = str(Path(fulltext_store_dir).as_posix())
    if fulltext_manifest and Path(fulltext_manifest).exists():
        pointer["fulltext_manifest"] = str(Path(fulltext_manifest).as_posix())
    latest = RUNS_BASE_DIR / "latest.json"
    _atomic_write_text(latest, json.dumps(pointer, indent=2))
    return latest

def read_latest_pointer() -> Dict[str, Any]:
    latest = RUNS_BASE_DIR / "latest.json"
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)

def get_latest_run_paths() -> Tuple[str, Path, Path]:
    """Return (run_id, papers_path, metadata_path) from latest.json."""
    p = read_latest_pointer()
    return p["run_id"], Path(p["papers_path"]), Path(p["metadata_path"])

logger = logging.getLogger(__name__)

# Default storage paths
DEFAULT_DATA_DIR = "data/ingest/raw"
DEFAULT_PAPERS_FILE = "pm_papers.jsonl"
DEFAULT_METADATA_FILE = "metadata.json"


def ensure_data_directory(data_dir: str = DEFAULT_DATA_DIR) -> Path:
    """
    Ensure the data directory exists
    
    Args:
        data_dir: Directory path for storing data
        
    Returns:
        Path object for the data directory
    """
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory: {path.absolute()}")
    return path


def save_selected_papers(docs: List[Dict], data_dir: str = DEFAULT_DATA_DIR, 
                        filename: str = DEFAULT_PAPERS_FILE) -> Path:
    """
    Save selected papers to JSONL file
    
    Args:
        docs: List of paper dictionaries
        data_dir: Directory to save files
        filename: JSONL filename
        
    Returns:
        Path to the saved file
    """
    ensure_data_directory(data_dir)
    file_path = Path(data_dir) / filename
    
    logger.info(f"Saving {len(docs)} papers to {file_path}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for doc in docs:
            f.write(json.dumps(doc) + '\n')
    
    logger.info(f"Successfully saved papers to {file_path}")
    return file_path


def save_run_metadata(metadata: Dict[str, Any], data_dir: str = DEFAULT_DATA_DIR,
                     filename: str = DEFAULT_METADATA_FILE) -> Path:
    """
    Save run metadata to JSON file
    
    Args:
        metadata: Metadata dictionary
        data_dir: Directory to save files
        filename: JSON filename
        
    Returns:
        Path to the saved file
    """
    ensure_data_directory(data_dir)
    file_path = Path(data_dir) / filename
    
    logger.info(f"Saving metadata to {file_path}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Successfully saved metadata to {file_path}")
    return file_path


def load_selected_papers(data_dir: str = DEFAULT_DATA_DIR, 
                        filename: str = DEFAULT_PAPERS_FILE) -> List[Dict]:
    """
    Load selected papers from JSONL file
    
    Args:
        data_dir: Directory containing the file
        filename: JSONL filename
        
    Returns:
        List of paper dictionaries
    """
    file_path = Path(data_dir) / filename
    
    if not file_path.exists():
        logger.warning(f"Papers file not found: {file_path}")
        return []
    
    papers = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    papers.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing line {line_num} in {file_path}: {e}")
                    continue
    
    logger.info(f"Loaded {len(papers)} papers from {file_path}")
    return papers


def load_run_metadata(data_dir: str = DEFAULT_DATA_DIR,
                     filename: str = DEFAULT_METADATA_FILE) -> Dict[str, Any]:
    """
    Load run metadata from JSON file
    
    Args:
        data_dir: Directory containing the file
        filename: JSON filename
        
    Returns:
        Metadata dictionary
    """
    file_path = Path(data_dir) / filename
    
    if not file_path.exists():
        logger.warning(f"Metadata file not found: {file_path}")
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    logger.info(f"Loaded metadata from {file_path}")
    return metadata


def create_metadata_summary(selected_docs: List[Dict[str, Any]], run_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a rich, human-auditable metadata summary from the selected docs.
    Computes: supplement_distribution, study_type_distribution, goal_distribution,
    quality_distribution, top_supplement_goal_combinations, top_goal_population_combinations,
    and simple diagnostics (general/other shares).
    """
    total = len(selected_docs)
    supp_counts: Dict[str, int] = {}
    study_type_counts: Dict[str, int] = {}
    study_category_counts: Dict[str, int] = {}
    goal_counts: Dict[str, int] = {}
    quality_bins = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    combo_supp_goal: Dict[str, int] = {}
    combo_goal_pop: Dict[str, int] = {}

    def bump(d: Dict[str, int], k: str, inc: int = 1):
        if not k:
            return
        d[k] = d.get(k, 0) + inc

    for doc in selected_docs:
        # Supplements
        supps = []
        s = (doc.get("supplements") or "").strip()
        if s:
            supps = [x.strip() for x in s.split(",") if x.strip()]
            for sp in supps:
                bump(supp_counts, sp)

        # Study type
        bump(study_type_counts, (doc.get("study_type") or "other"))
        # Study category
        bump(study_category_counts, (doc.get("study_category") or "other"))

        # Goals
        bump(goal_counts, (doc.get("primary_goal") or "general"))

        # Quality bins
        q = float(doc.get("reliability_score", 0.0) or 0.0)
        if q >= 4.0:
            quality_bins["4.0+"] += 1
        elif q >= 3.0:
            quality_bins["3.0-3.9"] += 1
        elif q >= 2.0:
            quality_bins["2.0-2.9"] += 1
        else:
            quality_bins["<2.0"] += 1

        # Combos
        primary_goal = (doc.get("primary_goal") or "").strip()
        population = (doc.get("population") or "").strip()
        if supps and primary_goal:
            for sp in supps:
                bump(combo_supp_goal, f"{sp}_{primary_goal}")
        if primary_goal and population:
            bump(combo_goal_pop, f"{primary_goal}_{population}")

    # Sort and truncate "top" combos
    top_sg = dict(sorted(combo_supp_goal.items(), key=lambda x: x[1], reverse=True)[:10])
    top_gp = dict(sorted(combo_goal_pop.items(), key=lambda x: x[1], reverse=True)[:5])

    # Diagnostics
    general_share = (goal_counts.get("general", 0) / total * 100.0) if total else 0.0
    other_study_share = (study_type_counts.get("other", 0) / total * 100.0) if total else 0.0
    nitric_oxide_count = supp_counts.get("nitric-oxide", 0)
    nitric_oxide_share = (nitric_oxide_count / total * 100.0) if total else 0.0

    summary = {
        "total_papers": total,
        "supplement_distribution": dict(sorted(supp_counts.items(), key=lambda x: x[1], reverse=True)),
        "study_type_distribution": dict(sorted(study_type_counts.items(), key=lambda x: x[1], reverse=True)),
        "study_category_distribution": dict(sorted(study_category_counts.items(), key=lambda x: x[1], reverse=True)),
        "goal_distribution": dict(sorted(goal_counts.items(), key=lambda x: x[1], reverse=True)),
        "quality_distribution": quality_bins,
        "top_supplement_goal_combinations": top_sg,
        "top_goal_population_combinations": top_gp,
        "diagnostics": {
            "general_share_percent": round(general_share, 2),
            "other_study_type_share_percent": round(other_study_share, 2),
            "nitric_oxide_share_percent": round(nitric_oxide_share, 2),
        }
    }

    return {"run_info": run_info, "summary": summary}


def get_storage_stats(data_dir: str = DEFAULT_DATA_DIR) -> Dict[str, Any]:
    """
    Get statistics about stored papers
    
    Args:
        data_dir: Directory to check
        
    Returns:
        Statistics dictionary
    """
    papers = load_selected_papers(data_dir)
    metadata = load_run_metadata(data_dir)
    
    if not papers:
        return {"total": 0, "supplements": {}, "quality_distribution": {}, "metadata": metadata}
    
    supplement_counts = {}
    quality_counts = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    
    for paper in papers:
        # Count supplements
        supplements = paper.get('supplements', [])
        if isinstance(supplements, str):
            supplements = supplements.split(',')
        
        for supp in supplements:
            supp = supp.strip()
            supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        # Count quality distribution
        quality = paper.get('reliability_score', 0)
        if quality >= 4.0:
            quality_counts["4.0+"] += 1
        elif quality >= 3.0:
            quality_counts["3.0-3.9"] += 1
        elif quality >= 2.0:
            quality_counts["2.0-2.9"] += 1
        else:
            quality_counts["<2.0"] += 1
    
    return {
        "total": len(papers),
        "supplements": supplement_counts,
        "quality_distribution": quality_counts,
        "metadata": metadata
    }

