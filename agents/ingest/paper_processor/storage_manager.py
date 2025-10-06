import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator

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
    Persistent storage for paper_processor artifacts under PROJECT_ROOT/data/paper_processor.

    Supports streaming writes and resuming:
      - open_summaries_writer(resume_path: Optional[str] = None)
      - write_summary_line(obj)
      - close_summaries_writer()
      - iter_dedupe_keys(path): yields dedupe_key from an existing summaries file
    """
    def __init__(self, rel_base_dir: str = "data/paper_processor"):
        self.paths = StoragePaths(
            base_dir=(PROJECT_ROOT / rel_base_dir),
            summaries_dir=(PROJECT_ROOT / rel_base_dir / "summaries"),
            stats_dir=(PROJECT_ROOT / rel_base_dir / "stats"),
            index_dir=(PROJECT_ROOT / rel_base_dir / "index"),
            latest_pointer=(PROJECT_ROOT / rel_base_dir / "latest.json"),
        )
        self._last_summaries_path: Optional[Path] = None
        self._last_stats_path: Optional[Path] = None
        # Streaming writer state
        self._writer_file = None
        self._writer_tmp_path: Optional[Path] = None
        self._writer_final_path: Optional[Path] = None

    def initialize(self) -> None:
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.paths.stats_dir.mkdir(parents=True, exist_ok=True)
        self.paths.index_dir.mkdir(parents=True, exist_ok=True)

    # -------- Legacy batch save (kept for compatibility) --------
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

    # -------- Streaming writer API (+ resume) --------
    def open_summaries_writer(self, resume_path: Optional[str] = None) -> Path:
        """
        Open a temporary JSONL for streaming writes.
        If resume_path is provided:
          - If resume_path ends with .tmp and exists: append to it.
          - If resume_path is final (.jsonl): create a new .tmp next to it and append there.
        Returns the FINAL path that will exist after close().
        """
        if self._writer_file is not None:
            return self._writer_final_path  # already open

        if resume_path:
            final_path = Path(resume_path)
            if final_path.suffix.endswith(".tmp"):
                # direct append resume on tmp
                tmp_path = final_path
                final_path = Path(str(final_path)[:-4]) if str(final_path).endswith(".tmp") else final_path.with_suffix("")
            else:
                # resume into a new tmp next to final
                tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
            final_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer_file = open(tmp_path, "a", encoding="utf-8")
            self._writer_tmp_path = tmp_path
            self._writer_final_path = final_path
            return final_path

        # Fresh file
        ts = time.strftime("%Y%m%d_%H%M%S")
        final_path = self.paths.summaries_dir / f"summaries_{ts}.jsonl"
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer_file = open(tmp_path, "w", encoding="utf-8")
        self._writer_tmp_path = tmp_path
        self._writer_final_path = final_path
        return final_path

    def write_summary_line(self, obj: Dict[str, Any]) -> None:
        if self._writer_file is None:
            raise RuntimeError("open_summaries_writer() must be called before write_summary_line()")
        self._writer_file.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def close_summaries_writer(self) -> Path:
        """Close and atomically finalize the summaries file; return the final path."""
        if self._writer_file is None:
            return self._last_summaries_path if self._last_summaries_path else self.paths.summaries_dir
        self._writer_file.flush()
        self._writer_file.close()
        self._writer_file = None
        assert self._writer_tmp_path is not None and self._writer_final_path is not None
        self._writer_tmp_path.replace(self._writer_final_path)
        self._last_summaries_path = self._writer_final_path
        self._writer_tmp_path = None
        final = self._writer_final_path
        self._writer_final_path = None
        return final

    # -------- Stats & latest pointer --------
    def save_processing_stats(self, stats: Dict[str, Any]) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = self.paths.stats_dir / f"stats_{ts}.json"
        _atomic_write_text(out, json.dumps(stats, indent=2, ensure_ascii=False))
        self._last_stats_path = out
        latest = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summaries_path": str(self._last_summaries_path.as_posix() if self._last_summaries_path else ""),
            "stats_path": str(out.as_posix()),
        }
        _atomic_write_text(self.paths.latest_pointer, json.dumps(latest, indent=2))
        return out

    # -------- Resume helpers --------
    @staticmethod
    def iter_dedupe_keys(path: Path) -> Iterator[str]:
        """
        Stream dedupe_key values from an existing summaries file (.jsonl or .jsonl.tmp).
        """
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    dk = obj.get("dedupe_key")
                    if dk:
                        yield dk
                except Exception:
                    continue
