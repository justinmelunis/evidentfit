#!/usr/bin/env python3
from pathlib import Path
import json

store = Path('data/fulltext_store')
total = 0
fulltext = 0
abstract_only = 0

for subdir in store.iterdir():
    if not subdir.is_dir():
        continue
    files = list(subdir.glob('*.json'))
    for f in files[:50]:  # Sample 50 per subdir
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            total += 1
            if data.get('fulltext_text', '').strip():
                fulltext += 1
            else:
                abstract_only += 1
        except Exception:
            pass
    if total > 2000:
        break

print(f'Sampled {total} files:')
print(f'  Fulltext: {fulltext} ({fulltext/total*100:.1f}%)')
print(f'  Abstract-only: {abstract_only} ({abstract_only/total*100:.1f}%)')

