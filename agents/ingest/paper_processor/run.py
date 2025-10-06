#!/usr/bin/env python3
"""
Optimized pipeline for processing papers with Q&A-focused schema.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
import logging

from evidentfit_shared.utils import PROJECT_ROOT

from mistral_client import MistralClient, ProcessingConfig
from storage_manager import StorageManager
from logging_config import setup_logging
from schema import (
    create_optimized_prompt, validate_optimized_schema, create_search_index,
    normalize_data, create_dedupe_key, OptimizedPaper, OutcomeItem
)
import torch

def load_paper_from_file(file_path: Path) -> Dict[str, Any]:
    """Load a single paper from a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_papers_from_directory(directory: Path, limit: int = None) -> List[Dict[str, Any]]:
    """Load papers from a directory of JSON files."""
    papers = []
    json_files = list(directory.glob('*.json'))
    
    # Skip summary files
    json_files = [f for f in json_files if f.name not in ['fetch_summary.json']]
    
    if limit:
        json_files = json_files[:limit]
    
    for file_path in json_files:
        try:
            paper = load_paper_from_file(file_path)
            papers.append(paper)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            continue
    
    return papers

def parse_optimized_summary(response: str, paper_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Parse response into optimized schema."""
    try:
        # Clean and extract JSON
        response = response.strip()
        if "### END_JSON" in response:
            response = response.split("### END_JSON", 1)[0].rstrip()
        
        # Find JSON object
        start = response.find('{')
        if start == -1:
            raise ValueError("No JSON object found")
        
        # Find matching closing brace
        depth = 0
        end = -1
        for i, ch in enumerate(response[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        if end == -1:
            raise ValueError("Unclosed JSON object")
        
        json_str = response[start:end]
        
        # Fix common JSON issues
        json_str = json_str.replace(',}', '}').replace(',]', ']')
        
        # Parse JSON
        structured_data = json.loads(json_str)
        
        # Normalize data
        structured_data = normalize_data(structured_data)
        
        # Add dedupe key
        structured_data['dedupe_key'] = create_dedupe_key(structured_data)
        
        # Validate schema
        if not validate_optimized_schema(structured_data):
            print(f"  Schema validation failed, attempting to fix...")
            # Try to fix common issues
            structured_data = fill_required_defaults(structured_data)
            if not validate_optimized_schema(structured_data):
                raise ValueError("Schema validation failed after fixes")
        
        # Add metadata
        structured_data['processing_timestamp'] = time.time()
        structured_data['llm_model'] = model_name
        structured_data['schema_version'] = 'v1.2'
        
        return structured_data
        
    except Exception as e:
        print(f"Error parsing optimized summary: {e}")
        # Return fallback summary
        return create_fallback_optimized_summary(paper_data, model_name)

def create_fallback_optimized_summary(paper_data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Create fallback summary with optimized schema."""
    return {
        "id": paper_data.get('id', 'unknown'),
        "title": paper_data.get('title', 'Unknown Title'),
        "journal": paper_data.get('journal', 'Unknown Journal'),
        "year": paper_data.get('year', 'Unknown Year'),
        "doi": paper_data.get('doi'),
        "pmid": paper_data.get('pmid'),
        "study_type": paper_data.get('study_type', 'unknown'),
        "study_design": "Not specified",
        "population": {
            "age_range": "Not specified",
            "sex": "Not specified",
            "training_status": "not_reported",
            "sample_size": "Not specified"
        },
        "summary": "Paper analysis failed - fallback summary",
        "key_findings": ["Analysis incomplete"],
        "supplements": ["Not specified"],
        "supplement_primary": "Not specified",
        "dosage": {
            "loading": "Not specified",
            "maintenance": "Not specified",
            "timing": "Not specified",
            "form": "Not specified"
        },
        "primary_outcome": "Not specified",
        "outcome_measures": {
            "strength": [],
            "endurance": [],
            "power": []
        },
        "safety_issues": [],
        "adverse_events": "Not specified",
        "evidence_grade": "D",
        "quality_score": 1.0,
        "limitations": ["Analysis failed"],
        "clinical_relevance": "Not specified",
        "keywords": [],
        "relevance_tags": [],
        "processing_timestamp": time.time(),
        "llm_model": model_name,
        "schema_version": "v1.2"
    }

def fill_required_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in required fields with defaults if missing."""
    # Required fields with defaults
    defaults = {
        'id': data.get('id', 'unknown'),
        'title': data.get('title', 'Unknown Title'),
        'journal': data.get('journal', 'Unknown Journal'),
        'year': data.get('year', 2023),
        'study_type': data.get('study_type', 'unknown'),
        'population': data.get('population', {}),
        'summary': data.get('summary', 'No summary available'),
        'key_findings': data.get('key_findings', []),
        'supplements': data.get('supplements', []),
        'outcome_measures': data.get('outcome_measures', {
            "strength": [], "endurance": [], "power": []
        }),
        'evidence_grade': data.get('evidence_grade', 'D'),
        'quality_score': data.get('quality_score', 1.0)
    }
    
    # Fill missing required fields
    for key, default_value in defaults.items():
        if key not in data or data[key] is None:
            data[key] = default_value
    
    # Ensure population is a dict
    if not isinstance(data.get('population'), dict):
        data['population'] = {}
    
    # Ensure key_findings is a list
    if not isinstance(data.get('key_findings'), list):
        data['key_findings'] = []
    
    # Ensure supplements is a list
    if not isinstance(data.get('supplements'), list):
        data['supplements'] = []
    
    # Ensure outcome_measures is a dict
    if not isinstance(data.get('outcome_measures'), dict):
        data['outcome_measures'] = {
            "strength": [], "endurance": [], "power": []
        }
    
    return data

def main():
    """Main function to process papers with optimized schema."""
    # Setup logging
    run_id = f"optimized_processing_{int(time.time())}"
    setup_logging(run_id)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("OPTIMIZED PAPER PROCESSING PIPELINE STARTED")
    logger.info("=" * 80)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load papers from directory
    papers_dir = PROJECT_ROOT / 'data' / 'full_text_papers'
    if not papers_dir.exists():
        print(f"Papers directory not found: {papers_dir}")
        return
    
    # Load 2 papers for testing
    papers = load_papers_from_directory(papers_dir, limit=2)
    
    if not papers:
        print("No papers found in directory")
        return
    
    print(f"Loaded {len(papers)} full-text paper(s)")
    
    # Initialize optimized Mistral client with reduced memory usage
    config = ProcessingConfig(
        model_name="mistralai/Mistral-7B-Instruct-v0.3",
        ctx_tokens=16384,  # Full context window as agreed
        max_new_tokens=640,  # Full output tokens as agreed
        temperature=0.2,
        batch_size=2,  # Process two papers at a time
        microbatch_size=1,  # Single paper per microbatch
        use_4bit=True,
        device_map="auto",
        enable_schema_validation=True,
        enable_model_repair=False,
        schema_version="v1.2"
    )
    
    print("Initializing optimized Mistral client...")
    client = OptimizedMistralClient(config)
    
    # Initialize storage manager
    storage_manager = StorageManager("data/paper_processor")
    
    print("Processing papers with optimized schema...")
    start_time = time.time()
    
    # Process papers in batches of 2 to avoid memory issues
    try:
        batch_size = 2
        total_papers = len(papers)
        all_summaries = []
        
        for i in range(0, total_papers, batch_size):
            batch = papers[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_papers + batch_size - 1) // batch_size
            
            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} papers)")
            for j, paper in enumerate(batch):
                print(f"  Paper {i+j+1}: {paper.get('title', 'Unknown')[:60]}...")
            
            # Process batch
            summaries = client.generate_optimized_summaries(batch)
            if summaries:
                all_summaries.extend(summaries)
                print(f"  + Processed {len(summaries)} papers successfully")
            else:
                print(f"  X Failed to process batch")
            
            # Clear GPU cache after each batch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        
        if all_summaries:
            # Create optimized search index
            print("Creating optimized search index...")
            search_index = create_search_index(all_summaries)
            
            # Save results
            with open(storage_dir / 'optimized_papers.json', 'w', encoding='utf-8') as f:
                json.dump(all_summaries, f, indent=2, ensure_ascii=False)
            
            with open(storage_dir / 'search_index.json', 'w', encoding='utf-8') as f:
                json.dump(search_index, f, indent=2, ensure_ascii=False)
            
            # Print results
            print(f"\nProcessing completed successfully!")
            print(f"Total papers processed: {len(all_summaries)}")
            
            # Show sample results
            if all_summaries:
                sample = all_summaries[0]
                print(f"\nSample optimized paper:")
                print(f"  ID: {sample.get('id', 'Unknown')}")
                print(f"  Title: {sample.get('title', 'Unknown')}")
                print(f"  Summary: {sample.get('summary', 'Unknown')}")
                print(f"  Key Findings: {len(sample.get('key_findings', []))} findings")
                print(f"  Evidence Grade: {sample.get('evidence_grade', 'Unknown')}")
                print(f"  Quality Score: {sample.get('quality_score', 'Unknown')}")
            
            # Show index statistics
            stats = search_index['statistics']
            print(f"\nIndex Statistics:")
            print(f"  Total Papers: {stats['total_papers']}")
            print(f"  Study Types: {stats['study_types']}")
            print(f"  Evidence Grades: {stats['evidence_grades']}")
            print(f"  Year Range: {stats['year_range']['min']}-{stats['year_range']['max']}")
            print(f"  Supplements: {stats['supplements']}")
            
        else:
            print("No summaries generated")
            
    except Exception as e:
        print(f"Error processing papers: {e}")
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"\nProcessing completed in {processing_time:.2f} seconds")
    print(f"Processing rate: {len(papers)/processing_time:.3f} papers/sec")

if __name__ == "__main__":
    main()
