#!/usr/bin/env python3
"""
Rebuild master summaries from monthly delta files.

Useful for rollback or recovery if master gets corrupted.

Usage:
    python scripts/rebuild_master_from_deltas.py [deltas_dir] [output_path]
    
Defaults:
    deltas_dir: data/paper_processor/monthly_deltas
    output_path: data/paper_processor/master/summaries_master_rebuilt.jsonl
"""
import json
import sys
from pathlib import Path

def rebuild_master(deltas_dir, output_path):
    """
    Rebuild master from all delta files in chronological order.
    """
    delta_files = sorted(deltas_dir.glob("*_delta.jsonl"))
    
    if not delta_files:
        print(f"ERROR: No delta files found in {deltas_dir}")
        return False
    
    print(f"Rebuilding master from {len(delta_files)} delta files...")
    print("=" * 80)
    
    total_papers = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use temporary file for safety
    tmp_path = output_path.with_suffix(".rebuilding")
    
    with open(tmp_path, "w", encoding="utf-8") as out:
        for delta_file in delta_files:
            try:
                with open(delta_file, "r", encoding="utf-8") as f:
                    delta_data = json.load(f)
                
                metadata = delta_data.get("delta_metadata", {})
                papers = delta_data.get("papers", [])
                
                date = metadata.get("date", "unknown")
                print(f"  {date}: {len(papers):,} papers")
                
                # Write papers to output
                for paper in papers:
                    out.write(json.dumps(paper, ensure_ascii=False) + "\n")
                    total_papers += 1
                    
            except Exception as e:
                print(f"  ERROR reading {delta_file.name}: {e}")
                return False
    
    # Atomic replace
    tmp_path.replace(output_path)
    
    print("=" * 80)
    print(f"✓ Master rebuilt: {output_path}")
    print(f"  Total papers: {total_papers:,}")
    print()
    print("Next steps:")
    print("  1. Validate: python scripts/validate_master_summaries.py")
    print("  2. Build index: Run paper_processor in monthly mode (auto-builds)")
    print(f"  3. Replace master: mv {output_path} data/paper_processor/master/summaries_master.jsonl")
    
    return True

if __name__ == "__main__":
    deltas_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/paper_processor/monthly_deltas")
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/paper_processor/master/summaries_master_rebuilt.jsonl")
    
    success = rebuild_master(deltas_dir, output_path)
    sys.exit(0 if success else 1)

