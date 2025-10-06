#!/usr/bin/env python3
"""
Analyze quality distribution per supplement in the corpus.
Shows min/median/max reliability scores to inform monthly threshold strategy.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

def analyze(jsonl_path):
    papers = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    papers.append(json.loads(line))
                except:
                    continue
    
    by_supp = defaultdict(list)
    for p in papers:
        supps = p.get('supplements', '')
        if isinstance(supps, str):
            supps = [s.strip() for s in supps.split(',') if s.strip()]
        for s in supps:
            by_supp[s].append(p.get('reliability_score', 0.0))
    
    print(f"{'Supplement':<25} {'Count':>6} {'Min':>6} {'Median':>6} {'P75':>6} {'Max':>6}")
    print("=" * 80)
    
    for supp in sorted(by_supp.keys()):
        scores = sorted(by_supp[supp])
        if not scores:
            continue
        n = len(scores)
        min_s = min(scores)
        median_s = scores[n//2]
        p75_s = scores[int(n*0.75)]
        max_s = max(scores)
        
        # Flag supplements with min < 2.0
        flag = " [LOW]" if min_s < 2.0 else ""
        print(f"{supp:<25} {n:>6} {min_s:>6.2f} {median_s:>6.2f} {p75_s:>6.2f} {max_s:>6.2f}{flag}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/ingest/runs/20251005_172726/pm_papers.jsonl"
    analyze(Path(path))

