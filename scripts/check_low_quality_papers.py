#!/usr/bin/env python3
import json
import sys

jsonl_path = sys.argv[1] if len(sys.argv) > 1 else "data/ingest/runs/20251005_172726/pm_papers.jsonl"
supplement = sys.argv[2] if len(sys.argv) > 2 else "caffeine"

papers = []
with open(jsonl_path, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            try:
                papers.append(json.loads(line))
            except:
                continue

# Find papers for this supplement with low quality
supp_papers = [p for p in papers if supplement in p.get('supplements', '').lower()]
low_quality = [p for p in supp_papers if p.get('reliability_score', 0) < 2.0]

print(f"Found {len(low_quality)} {supplement} papers with score < 2.0 (out of {len(supp_papers)} total)")
print()

for i, p in enumerate(low_quality[:5], 1):
    print(f"=== Paper {i} ===")
    print(f"PMID: {p.get('pmid')}")
    print(f"Score: {p.get('reliability_score'):.2f}")
    print(f"Title: {p.get('title', '')[:100]}")
    print(f"Supplements: {p.get('supplements')}")
    print(f"Study type: {p.get('study_type')}")
    print(f"Primary goal: {p.get('primary_goal')}")
    print(f"Year: {p.get('year')}")
    print()

