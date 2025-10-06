import json
import time
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

from evidentfit_shared.utils import PROJECT_ROOT

def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    tmp.replace(path)

@dataclass
class StoragePaths:
    base_dir: Path
    summaries_dir: Path
    stats_dir: Path
    index_dir: Path
    latest_pointer: Path

class StorageManager:
    """
    Handles persistent storage for paper_processor artifacts under PROJECT_ROOT/data/paper_processor
    """
    def __init__(self, rel_base_dir: str = "data/paper_processor"):
        self.paths = StoragePaths(
            base_dir=(PROJECT_ROOT / rel_base_dir),
            summaries_dir=(PROJECT_ROOT / rel_base_dir / "summaries"),
            stats_dir=(PROJECT_ROOT / rel_base_dir / "stats"),
            index_dir=(PROJECT_ROOT / rel_base_dir / "index"),
            latest_pointer=(PROJECT_ROOT / rel_base_dir / "latest.json"),
        )
        self._last_summaries_path: Path | None = None
        self._last_stats_path: Path | None = None

    def initialize(self) -> None:
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.paths.stats_dir.mkdir(parents=True, exist_ok=True)
        self.paths.index_dir.mkdir(parents=True, exist_ok=True)

    def save_structured_summaries(self, summaries: List[Dict[str, Any]]) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = self.paths.summaries_dir / f"summaries_{ts}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for s in summaries:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        tmp.replace(out)
        self._last_summaries_path = out
        return out

    def save_processing_stats(self, stats: Dict[str, Any]) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = self.paths.stats_dir / f"stats_{ts}.json"
        _atomic_write_text(out, json.dumps(stats, indent=2, ensure_ascii=False))
        self._last_stats_path = out
        # Update latest pointer
        latest = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summaries_path": str(self._last_summaries_path.as_posix() if self._last_summaries_path else ""),
            "stats_path": str(out.as_posix()),
        }
        _atomic_write_text(self.paths.latest_pointer, json.dumps(latest, indent=2))
        return out
