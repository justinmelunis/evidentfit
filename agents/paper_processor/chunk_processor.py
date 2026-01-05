#!/usr/bin/env python3
"""
Chunk-based processing with section-targeted extraction.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

LOG = logging.getLogger(__name__)

@dataclass
class ChunkResult:
    """Result from processing a single chunk."""
    chunk_id: str
    section: str
    start: int
    result: Dict[str, Any]
    processing_time: float

class ChunkProcessor:
    """Processes paper chunks with section-targeted extraction."""
    
    def __init__(self, client=None):
        self.client = client
        self.section_strategies = {
            'abstract': {
                'focus': 'overview and key findings',
                'fields': ['population_size', 'main_outcomes', 'key_findings', 'study_type'],
                'prompt_template': """
Extract key information from this abstract:

{text}

Focus on:
- population_size: number of participants
- main_outcomes: primary study outcomes
- key_findings: main conclusions
- study_type: type of study (RCT, meta-analysis, etc.)

Return JSON with only the relevant fields found.
"""
            },
            'methods': {
                'focus': 'study design and procedures',
                'fields': ['population_size', 'intervention_details', 'duration_weeks', 'study_design', 'dose_g_per_day'],
                'prompt_template': """
Extract study design information from this methods section:

{text}

Focus on:
- population_size: number of participants
- intervention_details: supplement details, dosing
- duration_weeks: study duration in weeks
- study_design: study type and design
- dose_g_per_day: supplement dose in grams per day

Return JSON with only the relevant fields found.
"""
            },
            'results': {
                'focus': 'statistical results and effect sizes',
                'fields': ['effect_sizes', 'statistical_significance', 'outcome_measures', 'p_values'],
                'prompt_template': """
Extract statistical results from this results section:

{text}

Focus on:
- effect_sizes: Cohen's d, odds ratios, mean differences, etc.
- statistical_significance: significant results
- outcome_measures: what was measured
- p_values: statistical significance values

Return JSON with only the relevant fields found.
"""
            },
            'discussion': {
                'focus': 'safety and clinical implications',
                'fields': ['safety_notes', 'adverse_events', 'clinical_implications', 'contraindications'],
                'prompt_template': """
Extract safety and clinical information from this discussion section:

{text}

Focus on:
- safety_notes: general safety information
- adverse_events: any adverse events mentioned
- clinical_implications: clinical relevance
- contraindications: any contraindications

Return JSON with only the relevant fields found.
"""
            }
        }
    
    def process_chunk(self, chunk_id: str, section: str, start: int, text: str) -> ChunkResult:
        """Process a single chunk with section-targeted extraction."""
        import time
        
        start_time = time.time()
        
        # Get strategy for this section
        strategy = self.section_strategies.get(section, self.section_strategies['abstract'])
        
        # Create prompt
        prompt = strategy['prompt_template'].format(text=text)
        
        # Process with LLM
        try:
            result = self.client.generate_json(
                system_prompt="You are an expert research extractor. Return only valid JSON.",
                user_prompt=prompt,
                max_new_tokens=512,
                temperature=0.0
            )
        except Exception as e:
            LOG.warning(f"LLM processing failed for chunk {chunk_id}: {e}")
            result = {}
        
        processing_time = time.time() - start_time
        
        return ChunkResult(
            chunk_id=chunk_id,
            section=section,
            start=start,
            result=result if isinstance(result, dict) else {},
            processing_time=processing_time
        )
    
    def process_chunks_parallel(self, chunks: List[tuple]) -> List[ChunkResult]:
        """Process multiple chunks in parallel."""
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        start_time = time.time()
        results = []
        
        # Process chunks in parallel (limited by GPU memory)
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit all chunks
            future_to_chunk = {}
            for chunk_id, section, start, text in chunks:
                future = executor.submit(self.process_chunk, chunk_id, section, start, text)
                future_to_chunk[future] = (chunk_id, section, start, text)
            
            # Collect results
            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    chunk_id, section, start, text = future_to_chunk[future]
                    LOG.error(f"Failed to process chunk {chunk_id}: {e}")
        
        total_time = time.time() - start_time
        LOG.info(f"Processed {len(chunks)} chunks in {total_time:.2f}s (avg: {total_time/len(chunks):.2f}s per chunk)")
        
        return results
    
    def aggregate_results(self, chunk_results: List[ChunkResult]) -> Dict[str, Any]:
        """Aggregate results from multiple chunks intelligently."""
        aggregated = {
            'population': {},
            'intervention': {},
            'outcomes': {},
            'safety': {}
        }
        
        # Priority order for different sections
        section_priority = {
            'methods': 1,      # Most reliable for population and intervention
            'abstract': 2,     # Good overview
            'results': 3,      # Best for outcomes
            'discussion': 4    # Best for safety
        }
        
        # Process results by priority
        for result in sorted(chunk_results, key=lambda x: section_priority.get(x.section, 5)):
            section = result.section
            data = result.result
            
            # Population data (prefer methods, then abstract)
            if section in ['methods', 'abstract']:
                if 'population_size' in data and data['population_size']:
                    aggregated['population']['n'] = data['population_size']
            
            # Intervention data (prefer methods)
            if section == 'methods':
                if 'dose_g_per_day' in data and data['dose_g_per_day']:
                    aggregated['intervention']['dose_g_per_day'] = data['dose_g_per_day']
                if 'duration_weeks' in data and data['duration_weeks']:
                    aggregated['intervention']['duration_weeks'] = data['duration_weeks']
                if 'intervention_details' in data and data['intervention_details']:
                    aggregated['intervention']['details'] = data['intervention_details']
            
            # Outcomes data (prefer results)
            if section == 'results':
                if 'effect_sizes' in data and data['effect_sizes']:
                    aggregated['outcomes']['effect_sizes'] = data['effect_sizes']
                if 'outcome_measures' in data and data['outcome_measures']:
                    aggregated['outcomes']['measures'] = data['outcome_measures']
                if 'statistical_significance' in data and data['statistical_significance']:
                    aggregated['outcomes']['significance'] = data['statistical_significance']
            
            # Safety data (prefer discussion)
            if section == 'discussion':
                if 'safety_notes' in data and data['safety_notes']:
                    aggregated['safety']['notes'] = data['safety_notes']
                if 'adverse_events' in data and data['adverse_events']:
                    aggregated['safety']['adverse_events'] = data['adverse_events']
                if 'contraindications' in data and data['contraindications']:
                    aggregated['safety']['contraindications'] = data['contraindications']
        
        return aggregated
