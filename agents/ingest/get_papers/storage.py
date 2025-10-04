"""
Local storage for get_papers agent

Handles writing selected papers to JSONL and metadata to JSON files.
No Azure calls - pure local file operations.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Default storage paths
DEFAULT_DATA_DIR = "data/ingest/raw"
DEFAULT_PAPERS_FILE = "pm_papers.jsonl"
DEFAULT_METADATA_FILE = "metadata.json"


def ensure_data_directory(data_dir: str = DEFAULT_DATA_DIR) -> Path:
    """
    Ensure the data directory exists
    
    Args:
        data_dir: Directory path for storing data
        
    Returns:
        Path object for the data directory
    """
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory: {path.absolute()}")
    return path


def save_selected_papers(docs: List[Dict], data_dir: str = DEFAULT_DATA_DIR, 
                        filename: str = DEFAULT_PAPERS_FILE) -> Path:
    """
    Save selected papers to JSONL file
    
    Args:
        docs: List of paper dictionaries
        data_dir: Directory to save files
        filename: JSONL filename
        
    Returns:
        Path to the saved file
    """
    ensure_data_directory(data_dir)
    file_path = Path(data_dir) / filename
    
    logger.info(f"Saving {len(docs)} papers to {file_path}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for doc in docs:
            f.write(json.dumps(doc) + '\n')
    
    logger.info(f"Successfully saved papers to {file_path}")
    return file_path


def save_run_metadata(metadata: Dict[str, Any], data_dir: str = DEFAULT_DATA_DIR,
                     filename: str = DEFAULT_METADATA_FILE) -> Path:
    """
    Save run metadata to JSON file
    
    Args:
        metadata: Metadata dictionary
        data_dir: Directory to save files
        filename: JSON filename
        
    Returns:
        Path to the saved file
    """
    ensure_data_directory(data_dir)
    file_path = Path(data_dir) / filename
    
    logger.info(f"Saving metadata to {file_path}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Successfully saved metadata to {file_path}")
    return file_path


def load_selected_papers(data_dir: str = DEFAULT_DATA_DIR, 
                        filename: str = DEFAULT_PAPERS_FILE) -> List[Dict]:
    """
    Load selected papers from JSONL file
    
    Args:
        data_dir: Directory containing the file
        filename: JSONL filename
        
    Returns:
        List of paper dictionaries
    """
    file_path = Path(data_dir) / filename
    
    if not file_path.exists():
        logger.warning(f"Papers file not found: {file_path}")
        return []
    
    papers = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    papers.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing line {line_num} in {file_path}: {e}")
                    continue
    
    logger.info(f"Loaded {len(papers)} papers from {file_path}")
    return papers


def load_run_metadata(data_dir: str = DEFAULT_DATA_DIR,
                     filename: str = DEFAULT_METADATA_FILE) -> Dict[str, Any]:
    """
    Load run metadata from JSON file
    
    Args:
        data_dir: Directory containing the file
        filename: JSON filename
        
    Returns:
        Metadata dictionary
    """
    file_path = Path(data_dir) / filename
    
    if not file_path.exists():
        logger.warning(f"Metadata file not found: {file_path}")
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    logger.info(f"Loaded metadata from {file_path}")
    return metadata


def create_metadata_summary(docs: List[Dict], run_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create metadata summary for the run
    
    Args:
        docs: List of selected papers
        run_info: Run information dictionary
        
    Returns:
        Metadata dictionary
    """
    # Count papers by supplement
    supplement_counts = {}
    for doc in docs:
        supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
        for supp in supplements:
            supp = supp.strip()
            if supp:
                supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
    
    # Count papers by study type
    study_type_counts = {}
    for doc in docs:
        study_type = doc.get("study_type", "unknown")
        study_type_counts[study_type] = study_type_counts.get(study_type, 0) + 1
    
    # Count papers by primary goal
    goal_counts = {}
    for doc in docs:
        goal = doc.get("primary_goal", "unknown")
        goal_counts[goal] = goal_counts.get(goal, 0) + 1
    
    # Quality distribution
    quality_distribution = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    for doc in docs:
        quality = doc.get("reliability_score", 0)
        if quality >= 4.0:
            quality_distribution["4.0+"] += 1
        elif quality >= 3.0:
            quality_distribution["3.0-3.9"] += 1
        elif quality >= 2.0:
            quality_distribution["2.0-2.9"] += 1
        else:
            quality_distribution["<2.0"] += 1
    
    # Top combination pairs (sample from first 100 papers)
    combo_analysis = {"supplement_goal": {}, "goal_population": {}}
    for doc in docs[:100]:  # Analyze top 100 papers
        supplements = doc.get("supplements", "").split(",")
        primary_goal = doc.get("primary_goal", "")
        population = doc.get("population", "")
        
        for supp in supplements:
            if supp.strip() and primary_goal:
                key = f"{supp.strip()}_{primary_goal}"
                combo_analysis["supplement_goal"][key] = combo_analysis["supplement_goal"].get(key, 0) + 1
        
        if primary_goal and population:
            key = f"{primary_goal}_{population}"
            combo_analysis["goal_population"][key] = combo_analysis["goal_population"].get(key, 0) + 1
    
    # Top combinations (sorted by count)
    top_supplement_goals = dict(sorted(combo_analysis["supplement_goal"].items(), 
                                     key=lambda x: x[1], reverse=True)[:10])
    top_goal_populations = dict(sorted(combo_analysis["goal_population"].items(), 
                                     key=lambda x: x[1], reverse=True)[:5])
    
    metadata = {
        "run_info": run_info,
        "summary": {
            "total_papers": len(docs),
            "supplement_distribution": dict(sorted(supplement_counts.items(), 
                                                 key=lambda x: x[1], reverse=True)),
            "study_type_distribution": study_type_counts,
            "goal_distribution": goal_counts,
            "quality_distribution": quality_distribution,
            "top_supplement_goal_combinations": top_supplement_goals,
            "top_goal_population_combinations": top_goal_populations
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    return metadata


def get_storage_stats(data_dir: str = DEFAULT_DATA_DIR) -> Dict[str, Any]:
    """
    Get statistics about stored papers
    
    Args:
        data_dir: Directory to check
        
    Returns:
        Statistics dictionary
    """
    papers = load_selected_papers(data_dir)
    metadata = load_run_metadata(data_dir)
    
    if not papers:
        return {"total": 0, "supplements": {}, "quality_distribution": {}, "metadata": metadata}
    
    supplement_counts = {}
    quality_counts = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    
    for paper in papers:
        # Count supplements
        supplements = paper.get('supplements', [])
        if isinstance(supplements, str):
            supplements = supplements.split(',')
        
        for supp in supplements:
            supp = supp.strip()
            supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        # Count quality distribution
        quality = paper.get('reliability_score', 0)
        if quality >= 4.0:
            quality_counts["4.0+"] += 1
        elif quality >= 3.0:
            quality_counts["3.0-3.9"] += 1
        elif quality >= 2.0:
            quality_counts["2.0-2.9"] += 1
        else:
            quality_counts["<2.0"] += 1
    
    return {
        "total": len(papers),
        "supplements": supplement_counts,
        "quality_distribution": quality_counts,
        "metadata": metadata
    }

