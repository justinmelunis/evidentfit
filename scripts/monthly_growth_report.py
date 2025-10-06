#!/usr/bin/env python3
"""
Analyze monthly growth from delta files.

Shows trends in corpus growth, per-supplement additions, quality metrics.

Usage:
    python scripts/monthly_growth_report.py [deltas_dir]
    
Default: data/paper_processor/monthly_deltas/
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

def analyze_deltas(deltas_dir):
    """Analyze all monthly delta files and show growth trends."""
    
    delta_files = sorted(deltas_dir.glob("*_delta.jsonl"))
    
    if not delta_files:
        print(f"No delta files found in {deltas_dir}")
        return
    
    print("Monthly Growth Report")
    print("=" * 100)
    print(f"{'Month':<12} {'Papers':>8} {'Cumulative':>12} {'Top Supplements (papers added)'}")
    print("-" * 100)
    
    cumulative = 0
    total_by_supplement = defaultdict(int)
    
    for delta_file in delta_files:
        try:
            with open(delta_file, "r", encoding="utf-8") as f:
                delta_data = json.load(f)
            
            metadata = delta_data.get("delta_metadata", {})
            papers = delta_data.get("papers", [])
            
            date = metadata.get("date", delta_file.stem.replace("_delta", ""))
            papers_added = len(papers)
            cumulative += papers_added
            
            # Count by supplement
            supp_counts = defaultdict(int)
            for p in papers:
                supps = p.get("supplements", [])
                if isinstance(supps, list):
                    for s in supps:
                        supp_counts[s] += 1
                        total_by_supplement[s] += 1
            
            # Top 3 supplements this month
            top_supps = sorted(supp_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            top_str = ", ".join([f"{s}({n})" for s, n in top_supps])
            
            print(f"{date:<12} {papers_added:>8,} {cumulative:>12,}   {top_str}")
            
        except Exception as e:
            print(f"ERROR reading {delta_file.name}: {e}")
    
    print("-" * 100)
    print(f"{'TOTAL':<12} {cumulative:>8,}")
    print()
    
    # Top supplements overall
    print("Top 10 Supplements by Total Additions:")
    print("-" * 60)
    top_overall = sorted(total_by_supplement.items(), key=lambda x: x[1], reverse=True)[:10]
    for s, n in top_overall:
        print(f"  {s:<30} {n:>8,} papers")

if __name__ == "__main__":
    deltas_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/paper_processor/monthly_deltas")
    analyze_deltas(deltas_dir)

