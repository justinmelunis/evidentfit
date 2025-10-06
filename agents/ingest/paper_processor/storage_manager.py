"""
Local storage management for processed paper summaries and search index.
Handles JSON file storage, indexing, and retrieval.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import time
from datetime import datetime
import os

from evidentfit_shared.utils import PROJECT_ROOT

logger = logging.getLogger(__name__)

class StorageManager:
    """Manages local storage for processed paper summaries and search index."""
    
    def __init__(self, base_dir: str = "data/paper_processor"):
        self.base_dir = PROJECT_ROOT / base_dir
        self.summaries_dir = self.base_dir / "summaries"
        self.index_dir = self.base_dir / "index"
        self.stats_dir = self.base_dir / "stats"
        
        # Create directories
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.stats_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------
    # Helpers / migrations
    # --------------------------
    def _now_ts(self) -> int:
        return int(time.time())

    def _as_summary_list(self, payload: Any) -> List[Dict[str, Any]]:
        """
        Accept either:
          - a list of summary dicts
          - a dict with key 'summaries' mapping to a list
        Return a clean list[dict]; drop non-dict items.
        """
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            inner = payload.get("summaries")
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        return []

    def _ensure_index_shape(self, idx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Normalize index to canonical shape:
          {
            "version": "1.0",
            "created_at": <ts>,
            "last_updated": <ts>,
            "total_papers": <int>,
            "papers": { <paper_id>: {...}, ... }
          }
        If an older file had 'papers' as a list, migrate it to a dict keyed by id.
        """
        if not isinstance(idx, dict):
            return {
                "version": "1.0",
                "created_at": time.time(),
                "last_updated": time.time(),
                "total_papers": 0,
                "papers": {}
            }
        idx.setdefault("version", "1.0")
        idx.setdefault("created_at", time.time())
        idx.setdefault("last_updated", time.time())
        papers = idx.get("papers", {})
        if isinstance(papers, list):
            migrated = {}
            for item in papers:
                if isinstance(item, dict):
                    pid = item.get("paper_id") or item.get("id")
                    if pid:
                        migrated[str(pid)] = item
            papers = migrated
        elif not isinstance(papers, dict):
            papers = {}
        idx["papers"] = papers
        idx["total_papers"] = len(papers)
        return idx
    
    def initialize(self):
        """Initialize storage directories and files."""
        try:
            logger.info(f"Initializing storage manager at {self.base_dir}")
            
            # Create directories
            self.summaries_dir.mkdir(parents=True, exist_ok=True)
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize index files if they don't exist
            self._initialize_index_files()
            
            logger.info("Storage manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize storage manager: {e}")
            raise
    
    def _initialize_index_files(self):
        """Initialize index files if they don't exist."""
        index_file = self.index_dir / "paper_index.json"
        if not index_file.exists():
            initial_index = {
                "version": "1.0",
                "created_at": time.time(),
                "total_papers": 0,
                "last_updated": time.time(),
                "papers": {}
            }
            self._save_json(index_file, initial_index)
    
    def save_structured_summaries(self, summaries: Any):
        """Save structured summaries to local storage."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"summaries_{timestamp}.json"
            filepath = self.summaries_dir / filename
            
            items = self._as_summary_list(summaries) if not isinstance(summaries, list) else summaries

            data = {
                "version": "1.0",
                "created_at": time.time(),
                "total_summaries": len(items),
                "summaries": items
            }
            # Save to file
            self._save_json(filepath, data)

            # Update index
            self._update_paper_index(items)

            logger.info(f"STORAGE: save_structured_summaries | {len(items)} items | {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving structured summaries: {e}")
            raise
    
    def _update_paper_index(self, summaries: Any):
        """Update the paper index with new summaries."""
        try:
            index_file = self.index_dir / "paper_index.json"
            
            # Load existing index
            if index_file.exists():
                try:
                    with open(index_file, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                except Exception:
                    raw = None
            else:
                raw = None
            index_data = self._ensure_index_shape(raw)
            papers = index_data["papers"]

            items = self._as_summary_list(summaries) if not isinstance(summaries, list) else summaries
            
            # Update index with new summaries
            updated = 0
            for summary in items:
                if not isinstance(summary, dict):
                    continue
                # prefer model-added metadata; fall back to core fields
                pid = summary.get('paper_id') or summary.get('id')
                if not pid:
                    # create a unique key to avoid overwriting "unknown"
                    pid = f"unknown_{self._now_ts()}_{updated}"
                key = str(pid)

                # Coerce year if string int
                yr = summary.get('paper_year', summary.get('year', ''))
                try:
                    if isinstance(yr, str) and yr.isdigit():
                        yr = int(yr)
                except Exception:
                    pass

                papers[key] = {
                    "title": summary.get('paper_title') or summary.get('title', ''),
                    "journal": summary.get('paper_journal') or summary.get('journal', ''),
                    "year": yr,
                    "study_type": summary.get('paper_study_type') or summary.get('study_type', ''),
                    "study_design": summary.get('study_design', ''),
                    "supplements": summary.get('supplements', []),
                    "goals": summary.get('goals', []),
                    "primary_goal": summary.get('primary_goal', ''),
                    "sample_size": summary.get('sample_size', ''),
                    "duration": summary.get('duration', ''),
                    "population": summary.get('population', {}),
                    "primary_outcomes": summary.get('primary_outcomes', []),
                    "secondary_outcomes": summary.get('secondary_outcomes', []),
                    "outcome_measures": summary.get('outcome_measures', {}),
                    "safety_data": summary.get('safety_data', {}),
                    "dosage": summary.get('dosage', {}),
                    "quality_scores": summary.get('quality_scores', {}),
                    "context": summary.get('context', {}),
                    "search_terms": summary.get('search_terms', []),
                    "relevance_scores": summary.get('relevance_scores', {}),
                    "summary": summary.get('summary', ''),
                    "processing_timestamp": summary.get('processing_timestamp', time.time()),
                    "fallback": summary.get('fallback', False)
                }
                updated += 1
            
            # Update metadata
            index_data["papers"] = papers
            index_data["total_papers"] = len(papers)
            index_data["last_updated"] = time.time()
            
            # Save updated index
            self._save_json(index_file, index_data)
            
            logger.info(f"STORAGE: update_paper_index | +{updated} | total={index_data['total_papers']} | {index_file}")
            
        except Exception as e:
            logger.error(f"Error updating paper index: {e}")
            raise
    
    def save_processing_stats(self, stats: Dict[str, Any]):
        """Save processing statistics."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"processing_stats_{timestamp}.json"
            filepath = self.stats_dir / filename
            
            self._save_json(filepath, stats)
            
            logger.info(f"Saved processing stats to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving processing stats: {e}")
            raise
    
    def load_paper_index(self) -> Dict[str, Any]:
        """Load the paper index."""
        try:
            index_file = self.index_dir / "paper_index.json"
            
            if not index_file.exists():
                return {"papers": {}, "total_papers": 0, "last_updated": 0}
            
            with open(index_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            return self._ensure_index_shape(raw)
                
        except Exception as e:
            logger.error(f"Error loading paper index: {e}")
            return {"papers": {}, "total_papers": 0}
    
    def search_papers(self, query: str, filters: Dict[str, Any] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search papers in the local index.
        
        Args:
            query: Search query
            filters: Optional filters (supplement, study_type, etc.)
            limit: Maximum number of results
            
        Returns:
            List of matching papers
        """
        try:
            # Load index
            index_data = self.load_paper_index()
            papers = index_data.get("papers", {})
            
            # Simple text search for now (can be enhanced with vector search)
            results = []
            query_lower = query.lower()
            
            for paper_id, paper_data in papers.items():
                # Check if query matches title, findings, intervention, or paper_title
                kf = paper_data.get("key_findings", "")
                if isinstance(kf, list):
                    kf_text = " ".join(str(x) for x in kf)
                else:
                    kf_text = str(kf)
                if (query_lower in str(paper_data.get("title", "")).lower() or
                    query_lower in str(paper_data.get("paper_title", "")).lower() or
                    query_lower in kf_text.lower() or
                    query_lower in str(paper_data.get("intervention", "")).lower()):
                    
                    # Apply filters if provided
                    if filters:
                        if not self._matches_filters(paper_data, filters):
                            continue
                    
                    results.append({
                        "paper_id": paper_id,
                        **paper_data
                    })
            
            # Sort by evidence quality and relevance
            results.sort(key=lambda x: (
                x.get("evidence_quality", "C"),
                x.get("processing_timestamp", 0)
            ), reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error searching papers: {e}")
            return []
    
    def _matches_filters(self, paper_data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if paper matches the given filters."""
        try:
            for key, value in filters.items():
                if key == "supplement":
                    # Check if supplement is mentioned in various fields
                    supplement_lower = value.lower()
                    
                    # Check in supplements field
                    supplements = paper_data.get("supplements", [])
                    if isinstance(supplements, list):
                        found_in_supplements = any(supplement_lower in str(supp).lower() for supp in supplements)
                    else:
                        found_in_supplements = False
                    
                    # Check in intervention field (legacy support)
                    intervention = paper_data.get("intervention", "").lower()
                    found_in_intervention = supplement_lower in intervention
                    
                    # Check in findings field (legacy support)
                    findings = paper_data.get("key_findings", "").lower()
                    found_in_findings = supplement_lower in findings
                    
                    # Check in title
                    title = paper_data.get("title", paper_data.get("paper_title", "")).lower()
                    found_in_title = supplement_lower in title
                    
                    # Check in search terms
                    search_terms = paper_data.get("search_terms", [])
                    if isinstance(search_terms, list):
                        found_in_search_terms = any(supplement_lower in str(term).lower() for term in search_terms)
                    else:
                        found_in_search_terms = False
                    
                    if not (found_in_supplements or found_in_intervention or found_in_findings or 
                           found_in_title or found_in_search_terms):
                        return False
                
                elif key == "study_type":
                    if paper_data.get("study_type", "").lower() != value.lower():
                        return False
                
                elif key == "evidence_quality":
                    if paper_data.get("evidence_quality", "C") != value:
                        return False
                
                elif key == "year_min":
                    try:
                        py = paper_data.get("year", "0")
                        paper_year = int(py) if isinstance(py, str) else int(py or 0)
                        if paper_year < int(value):
                            return False
                    except ValueError:
                        continue
                
                elif key == "year_max":
                    try:
                        py = paper_data.get("year", "0")
                        paper_year = int(py) if isinstance(py, str) else int(py or 0)
                        if paper_year > int(value):
                            return False
                    except ValueError:
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking filters: {e}")
            return False
    
    def get_paper_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific paper by ID."""
        try:
            index_data = self.load_paper_index()
            papers = index_data.get("papers", {})
            
            if paper_id in papers:
                return {
                    "paper_id": paper_id,
                    **papers[paper_id]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting paper by ID: {e}")
            return None
    
    def get_supplement_evidence(self, supplement: str, goal: str = None) -> List[Dict[str, Any]]:
        """
        Get evidence for a specific supplement.
        
        Args:
            supplement: Supplement name
            goal: Optional fitness goal
            
        Returns:
            List of relevant papers
        """
        try:
            # Search for papers mentioning the supplement
            results = self.search_papers(
                query=supplement,
                filters={"supplement": supplement},
                limit=1000
            )
            
            # Filter by goal if specified
            if goal:
                goal_results = []
                for paper in results:
                    # Check if paper is relevant to the goal
                    if self._is_relevant_to_goal(paper, goal):
                        goal_results.append(paper)
                results = goal_results
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting supplement evidence: {e}")
            return []
    
    def _is_relevant_to_goal(self, paper: Dict[str, Any], goal: str) -> bool:
        """Check if paper is relevant to a specific fitness goal."""
        try:
            goal_lower = goal.lower()
            
            # Check if goal is in the paper's goals list
            paper_goals = paper.get("goals", [])
            if isinstance(paper_goals, list):
                for paper_goal in paper_goals:
                    if goal_lower in str(paper_goal).lower():
                        return True
            
            # Check primary goal
            primary_goal = paper.get("primary_goal", "").lower()
            if goal_lower in primary_goal:
                return True
            
            # Check key fields for goal relevance
            fields_to_check = [
                "summary",
                "title",
                "primary_outcomes",
                "secondary_outcomes"
            ]
            
            # Goal keywords
            goal_keywords = {
                "strength": ["strength", "power", "1rm", "maximal", "force", "muscle strength"],
                "hypertrophy": ["muscle", "mass", "size", "hypertrophy", "growth", "muscle size"],
                "endurance": ["endurance", "aerobic", "cardio", "stamina", "vo2", "cardiorespiratory"],
                "weight_loss": ["weight", "fat", "body composition", "lean mass", "weight loss"],
                "performance": ["performance", "athletic", "sport", "competition", "athletic performance"],
                "general": ["health", "wellness", "general", "overall", "general health"]
            }
            
            keywords = goal_keywords.get(goal_lower, [])
            
            for field in fields_to_check:
                content = paper.get(field, "")
                if isinstance(content, list):
                    content = " ".join(str(item) for item in content)
                content = str(content).lower()
                
                for keyword in keywords:
                    if keyword in content:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking goal relevance: {e}")
            return False
    
    def _save_json(self, filepath: Path, data: Dict[str, Any]):
        """Save data to JSON file."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"STORAGE: wrote {filepath}")
                
        except Exception as e:
            logger.error(f"Error saving JSON file {filepath}: {e}")
            raise
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        try:
            index_data = self.load_paper_index()
            
            # Count files in directories
            summary_files = len(list(self.summaries_dir.glob("*.json")))
            stats_files = len(list(self.stats_dir.glob("*.json")))
            
            return {
                "total_papers": index_data.get("total_papers", 0),
                "summary_files": summary_files,
                "stats_files": stats_files,
                "last_updated": index_data.get("last_updated", 0),
                "base_dir": str(self.base_dir)
            }
            
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {}
