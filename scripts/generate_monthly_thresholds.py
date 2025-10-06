#!/usr/bin/env python3
"""
ONE-TIME SCRIPT: Generate hard-coded monthly quality thresholds from bootstrap corpus.

Usage:
    python scripts/generate_monthly_thresholds.py data/ingest/runs/<bootstrap_run>/pm_papers.jsonl

Outputs:
    agents/ingest/get_papers/monthly_thresholds.py (hard-coded thresholds)
"""
import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def generate_thresholds(jsonl_path):
    """Generate hard-coded thresholds from bootstrap corpus."""
    
    # Load all papers
    papers = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    papers.append(json.loads(line))
                except:
                    continue
    
    print(f"Loaded {len(papers)} papers from bootstrap corpus")
    
    # Group by supplement
    by_supplement = defaultdict(list)
    for p in papers:
        supps = p.get('supplements', '')
        if isinstance(supps, str):
            supps = [s.strip() for s in supps.split(',') if s.strip()]
        for s in supps:
            by_supplement[s].append(p.get('reliability_score', 0.0))
    
    # Calculate thresholds
    thresholds = {}
    small_supplements = []
    large_supplements = []
    
    for supp in sorted(by_supplement.keys()):
        scores = sorted(by_supplement[supp])
        n = len(scores)
        
        if n == 0:
            continue
        
        p25 = scores[int(n * 0.25)]
        median = scores[n // 2]
        
        if n < 100:
            # Small corpus: Use P25
            threshold = max(1.5, p25)
            small_supplements.append(supp)
        else:
            # Large corpus: Use Median
            threshold = max(2.0, median)
            large_supplements.append(supp)
        
        thresholds[supp] = round(threshold, 2)
    
    # Generate Python file
    output_lines = [
        '"""',
        'Hard-coded monthly quality thresholds per supplement.',
        '',
        f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        f'Source: {Path(jsonl_path).name}',
        f'Total papers analyzed: {len(papers):,}',
        f'Supplements: {len(thresholds)}',
        '',
        'Logic:',
        '- Small corpus (<100 papers): P25 (25th percentile) to build diversity',
        '- Large corpus (≥100 papers): Median (50th percentile) to maintain quality',
        '',
        'These thresholds are STATIC - they never change month-to-month.',
        'This provides predictable, explainable filtering behavior.',
        '"""',
        '',
        '# Generated thresholds',
        'MONTHLY_THRESHOLDS = {',
    ]
    
    # Add small supplements first
    if small_supplements:
        output_lines.append('    # Small corpora (<100 papers) - P25 threshold')
        for s in sorted(small_supplements):
            output_lines.append(f'    "{s}": {thresholds[s]},')
        output_lines.append('')
    
    # Add large supplements
    if large_supplements:
        output_lines.append('    # Large corpora (>=100 papers) - Median threshold')
        for s in sorted(large_supplements):
            output_lines.append(f'    "{s}": {thresholds[s]},')
    
    output_lines.append('}')
    output_lines.append('')
    output_lines.append('# Recency guarantee: Top N most recent papers per supplement')
    output_lines.append('# These are ALWAYS included (if quality >= 2.5) to keep research fresh')
    output_lines.append('RECENCY_TOP_N = {')
    output_lines.append('    "default": 2,  # Top 2 for small supplements')
    output_lines.append('    "large_supplements": [')
    
    # Identify large supplements (500+ papers)
    very_large = [s for s, scores in by_supplement.items() if len(scores) >= 500]
    for s in sorted(very_large):
        output_lines.append(f'        "{s}",')
    
    output_lines.append('    ],')
    output_lines.append('    "large_supplement_n": 10,  # Top 10 for large supplements')
    output_lines.append('}')
    output_lines.append('')
    output_lines.append('# Always add study types (bypass all thresholds)')
    output_lines.append('ALWAYS_ADD_STUDY_TYPES = ["meta-analysis", "systematic_review"]')
    output_lines.append('')
    output_lines.append('# Exceptional quality bypass')
    output_lines.append('EXCEPTIONAL_QUALITY_THRESHOLD = 4.5')
    output_lines.append('')
    output_lines.append('# Minimum quality for recency guarantee')
    output_lines.append('RECENCY_MIN_QUALITY = 2.5')
    output_lines.append('')
    
    # Write file
    output_path = Path("agents/ingest/get_papers/monthly_thresholds.py")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"\n[OK] Generated: {output_path}")
    print(f"  Small supplements (<100): {len(small_supplements)}")
    print(f"  Large supplements (>=100): {len(large_supplements)}")
    print(f"  Very large supplements (>=500): {len(very_large)}")
    print(f"\nRecency guarantee:")
    print(f"  Small supplements: Top 2 per month")
    print(f"  Large supplements: Top 10 per month")
    
    # Summary stats
    print("\nSample thresholds:")
    samples = ["caffeine", "creatine", "raspberry-ketone", "betaine", "vitamin-d"]
    for s in samples:
        if s in thresholds:
            n = len(by_supplement[s])
            print(f"  {s:20} (n={n:4}): {thresholds[s]:.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_monthly_thresholds.py <bootstrap_pm_papers.jsonl>")
        sys.exit(1)
    
    generate_thresholds(sys.argv[1])

