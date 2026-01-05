#!/usr/bin/env python3
import json

papers = set()
has_fulltext_sections = 0
abstract_only = set()
fulltext_papers = set()

with open('data/index/chunks.jsonl', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i > 5000:  # Sample first 5000 lines
            break
        d = json.loads(line)
        pmid = d.get('pmid')
        section = d.get('section_norm', '').lower()
        
        papers.add(pmid)
        
        if section in ['methods', 'results', 'discussion']:
            has_fulltext_sections += 1
            fulltext_papers.add(pmid)
        elif section == 'abstract':
            if pmid not in fulltext_papers:
                abstract_only.add(pmid)

print(f'Unique papers: {len(papers)}')
print(f'Fulltext sections: {has_fulltext_sections}')
print(f'Papers with fulltext: {len(fulltext_papers)}')
print(f'Abstract-only papers: {len(abstract_only)}')
if len(papers) > 0:
    print(f'Fulltext ratio: {len(fulltext_papers)/len(papers)*100:.1f}%')

