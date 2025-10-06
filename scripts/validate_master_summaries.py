#!/usr/bin/env python3
"""
Validate master summaries file for duplicates and consistency.

Usage:
    python scripts/validate_master_summaries.py [master_path]
    
Default: data/paper_processor/master/summaries_master.jsonl
"""
import json
import sys
from pathlib import Path
from collections import Counter

def validate_master(master_path, index_path=None):
    """
    Validate master summaries file.
    
    Checks:
    1. No duplicate dedupe_keys
    2. All lines are valid JSON
    3. Index matches file (if index provided)
    """
    print(f"Validating: {master_path}")
    print("=" * 80)
    
    if not master_path.exists():
        print(f"ERROR: Master not found at {master_path}")
        return False
    
    # Check 1: Load all papers and find duplicates
    dedupe_keys = []
    line_count = 0
    invalid_lines = []
    
    with open(master_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            line_count += 1
            
            try:
                obj = json.loads(line)
                dk = obj.get("dedupe_key")
                if dk:
                    dedupe_keys.append(dk)
                else:
                    invalid_lines.append((line_num, "missing dedupe_key"))
            except json.JSONDecodeError as e:
                invalid_lines.append((line_num, f"invalid JSON: {e}"))
    
    print(f"Total lines: {line_count:,}")
    print(f"Dedupe keys found: {len(dedupe_keys):,}")
    
    # Check for duplicates
    key_counts = Counter(dedupe_keys)
    duplicates = {k: v for k, v in key_counts.items() if v > 1}
    
    if duplicates:
        print(f"\nERROR: Found {len(duplicates)} duplicate dedupe keys!")
        for dk, count in list(duplicates.items())[:10]:
            print(f"  {dk}: {count} occurrences")
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates) - 10} more")
        return False
    else:
        print("✓ No duplicate dedupe keys")
    
    # Check for invalid lines
    if invalid_lines:
        print(f"\nWARNING: Found {len(invalid_lines)} invalid lines:")
        for line_num, reason in invalid_lines[:10]:
            print(f"  Line {line_num}: {reason}")
        if len(invalid_lines) > 10:
            print(f"  ... and {len(invalid_lines) - 10} more")
    else:
        print("✓ All lines are valid JSON")
    
    # Check 2: Validate against index if provided
    if index_path and index_path.exists():
        print(f"\nValidating against index: {index_path}")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            
            if len(index) == len(dedupe_keys):
                print(f"✓ Index size matches: {len(index):,} entries")
            else:
                print(f"ERROR: Index size mismatch: {len(index):,} vs {len(dedupe_keys):,}")
                return False
        except Exception as e:
            print(f"ERROR: Could not load index: {e}")
            return False
    
    print("\n" + "=" * 80)
    if not duplicates and not invalid_lines:
        print("VALIDATION PASSED")
        return True
    else:
        print("VALIDATION FAILED" if duplicates else "VALIDATION PASSED WITH WARNINGS")
        return not duplicates

if __name__ == "__main__":
    master_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/paper_processor/master/summaries_master.jsonl")
    index_path = master_path.parent / "master_index.json" if master_path.exists() else None
    
    valid = validate_master(master_path, index_path)
    sys.exit(0 if valid else 1)

