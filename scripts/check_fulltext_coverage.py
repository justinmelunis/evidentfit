#!/usr/bin/env python3
"""
Check full-text coverage across runs.

Shows metrics like:
- How many papers have full text vs abstract only
- Coverage by supplement, year, study type
- Storage usage
"""

import json
import sys
from pathlib import Path
from collections import Counter

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from evidentfit_shared import read_latest_pointer, read_pm_papers_jsonl, build_manifest

def main():
    print("=" * 70)
    print("FULL-TEXT COVERAGE ANALYSIS")
    print("=" * 70)
    
    # Read latest run info
    pointer = read_latest_pointer()
    if not pointer:
        print("ERROR: No latest.json found. Run get_papers first.")
        return 1
    
    run_id = pointer.get("run_id")
    run_dir = Path(pointer.get("run_dir"))
    
    print(f"\nRun ID: {run_id}")
    print(f"Papers: {pointer.get('papers_path')}")
    
    # Look for manifest in run dir (may not be in latest.json if fetched standalone)
    manifest_path = pointer.get("fulltext_manifest")
    if not manifest_path:
        manifest_path = run_dir / "fulltext_manifest.json"
    else:
        manifest_path = Path(manifest_path)
    
    # Check if fulltext was fetched
    if not manifest_path.exists():
        print("\nNo fulltext manifest found.")
        print("To fetch full texts, run:")
        print(f"  python -m agents.ingest.get_papers.fulltext_fetcher \\")
        print(f"    --jsonl {pointer.get('papers_path')}")
        return 1
    
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Overall stats
    print(f"\n" + "=" * 70)
    print("OVERALL COVERAGE")
    print("=" * 70)
    print(f"Total papers:       {manifest['total']:,}")
    
    # Handle different manifest formats
    if 'unpaywall_total' in manifest:
        # Newest format with Unpaywall tracking
        fulltext_count = manifest.get('full_text_with_body', 0)
        fulltext_pct = manifest.get('full_text_percent', 0)
        pmc_full = manifest.get('pmc_full_text', 0)
        pmc_abstract = manifest.get('pmc_abstract_only', 0)
        unpaywall_full = manifest.get('unpaywall_full_text', 0)
        unpaywall_rescued = manifest.get('unpaywall_rescued', 0)
        abstract_final = manifest.get('abstract_only_final', 0)
        abstract_final_pct = manifest.get('abstract_only_percent', 0)
        
        print(f"Full text (total):  {fulltext_count:,} ({fulltext_pct}%)")
        print(f"  ├─ PMC full:      {pmc_full:,}")
        print(f"  └─ Unpaywall:     {unpaywall_full:,} ({unpaywall_rescued} rescued from PMC abstract-only)")
        print(f"Abstract only:      {abstract_final:,} ({abstract_final_pct}%)")
    elif 'full_text_with_body' in manifest:
        # Old format with quality detection but no Unpaywall
        fulltext_count = manifest.get('full_text_with_body', 0)
        fulltext_pct = manifest.get('full_text_percent', 0)
        abstract_from_pmc = manifest.get('abstract_only_from_pmc', 0)
        abstract_from_pmc_pct = manifest.get('abstract_only_percent', 0)
        pmc_total = manifest.get('pmc_ok', 0)
        no_pmc = manifest['total'] - pmc_total
        no_pmc_pct = round(no_pmc / manifest['total'] * 100, 2) if manifest['total'] else 0
        
        print(f"Full text (w/ body): {fulltext_count:,} ({fulltext_pct}%)")
        print(f"PMC abstract only:  {abstract_from_pmc:,} ({abstract_from_pmc_pct}%)")
        print(f"No PMC content:     {no_pmc:,} ({no_pmc_pct}%)")
    elif 'content_breakdown' in manifest:
        # Old content_breakdown format
        fulltext_count = manifest['content_breakdown']['fulltext_available']
        fulltext_pct = manifest['content_breakdown']['fulltext_percent']
        abstract_only = manifest['content_breakdown']['abstract_only']
        abstract_pct = manifest['content_breakdown']['abstract_only_percent']
        print(f"Full text:          {fulltext_count:,} ({fulltext_pct}%)")
        print(f"Abstract only:      {abstract_only:,} ({abstract_pct}%)")
    else:
        # Legacy format
        fulltext_count = manifest.get('pmc_ok', 0)
        fulltext_pct = manifest.get('pmc_ok_percent', 0)
        abstract_only = manifest['total'] - fulltext_count
        abstract_pct = round(abstract_only / manifest['total'] * 100, 2) if manifest['total'] else 0
        print(f"PMC content:        {fulltext_count:,} ({fulltext_pct}%)")
        print(f"No PMC:             {abstract_only:,} ({abstract_pct}%)")
    
    if 'storage_estimate_mb' in manifest:
        print(f"Storage used:       {manifest['storage_estimate_mb']:.1f} MB")
    
    if 'elapsed_sec' in manifest:
        print(f"Fetch time:         {manifest['elapsed_sec'] / 60:.1f} minutes")
        print(f"Fetch rate:         {manifest['rate_per_sec']:.2f} papers/sec")
    
    # Status breakdown
    print(f"\n" + "=" * 70)
    print("STATUS BREAKDOWN")
    print("=" * 70)
    for status, count in sorted(manifest['status_breakdown'].items(), key=lambda x: -x[1]):
        pct = (count / manifest['total'] * 100) if manifest['total'] else 0
        print(f"  {status:20s}: {count:6,} ({pct:5.1f}%)")
    
    # Load papers to analyze by supplement/year
    papers_path = Path(pointer.get('papers_path'))
    
    print(f"\n" + "=" * 70)
    print("COVERAGE BY SUPPLEMENT (Top 15)")
    print("=" * 70)
    
    # Create lookup of PMID -> has_fulltext
    pmid_to_fulltext = {}
    for entry in manifest['entries']:
        pmid = str(entry.get('pmid', ''))
        has_ft = entry.get('pmc_status') in ('ok', 'ok_efetch')
        pmid_to_fulltext[pmid] = has_ft
    
    # Count by supplement
    supp_total = Counter()
    supp_fulltext = Counter()
    
    for paper in read_pm_papers_jsonl(papers_path):
        pmid = str(paper.get('pmid', ''))
        supplements = (paper.get('supplements') or '').split(',')
        has_ft = pmid_to_fulltext.get(pmid, False)
        
        for supp in supplements:
            supp = supp.strip()
            if supp:
                supp_total[supp] += 1
                if has_ft:
                    supp_fulltext[supp] += 1
    
    # Show top 15 by total count
    for supp, total in supp_total.most_common(15):
        ft = supp_fulltext[supp]
        pct = (ft / total * 100) if total else 0
        print(f"  {supp:20s}: {ft:5,}/{total:5,} ({pct:5.1f}%)")
    
    # Coverage by year
    print(f"\n" + "=" * 70)
    print("COVERAGE BY YEAR")
    print("=" * 70)
    
    year_total = Counter()
    year_fulltext = Counter()
    
    for paper in read_pm_papers_jsonl(papers_path):
        pmid = str(paper.get('pmid', ''))
        year = paper.get('year')
        has_ft = pmid_to_fulltext.get(pmid, False)
        
        if year:
            year_total[year] += 1
            if has_ft:
                year_fulltext[year] += 1
    
    # Show by year (most recent first)
    for year in sorted(year_total.keys(), reverse=True)[:10]:
        total = year_total[year]
        ft = year_fulltext[year]
        pct = (ft / total * 100) if total else 0
        print(f"  {year}: {ft:5,}/{total:5,} ({pct:5.1f}%)")
    
    print("\n" + "=" * 70)
    print(f"[OK] ANALYSIS COMPLETE")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

