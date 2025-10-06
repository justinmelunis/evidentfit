"""
Diversity analysis and iterative filtering

Handles combination analysis, weight calculation, and iterative diversity filtering
to ensure balanced representation across supplement-goal-population combinations.
No per-supplement caps before diversity - only combination weights and iterative filtering.
"""

import os
import math
import logging
from typing import Dict, List, Any, Set, Optional

logger = logging.getLogger(__name__)

# Environment variables
DIVERSITY_ROUNDS_THRESHOLD = int(os.getenv("DIVERSITY_ROUNDS_THRESHOLD", "50000"))


def _is_survey_like(doc: Dict) -> bool:
    """
    Check if document is survey-like (exclude from weight calculation)
    
    Args:
        doc: Paper dictionary
        
    Returns:
        True if survey-like
    """
    title = (doc.get("title") or "").lower()
    study_type = (doc.get("study_type") or "").lower()
    study_category = (doc.get("study_category") or "").lower()
    
    # Check for survey indicators
    survey_keywords = ["survey", "questionnaire", "prevalence", "cross-sectional"]
    if any(keyword in title for keyword in survey_keywords):
        return True
    
    # Check study type/category
    if study_type == "cross-sectional" or study_category == "observational_usage":
        return True
    
    # Check if observational without trial keywords
    if "observational" in study_type and not any(word in title for word in ["trial", "intervention", "randomized"]):
        return True
    
    return False


def analyze_combination_distribution(docs: List[Dict]) -> Dict[str, Dict[str, int]]:
    """
    Analyze existing papers for factor combinations
    
    Args:
        docs: List of paper dictionaries
        
    Returns:
        Dictionary with combination counts by type
    """
    combinations = {
        "supplement_goal": {},      # creatine + muscle_gain
        "supplement_population": {}, # beta-alanine + athletes  
        "goal_population": {},      # muscle_gain + elderly
        "study_type_goal": {},      # meta-analysis + weight_loss
        "journal_supplement": {}    # J Appl Physiol + creatine
    }
    
    # Filter out survey-like papers for weight calculation
    filtered_docs = [doc for doc in docs if not _is_survey_like(doc)]
    
    for doc in filtered_docs:
        # Extract factors
        supplements = (doc.get("supplements") or "").split(",")
        primary_goal = doc.get("primary_goal") or ""
        population = doc.get("population") or ""
        study_type = doc.get("study_type") or ""
        journal = (doc.get("journal") or "").lower()
        
        # Track supplement + goal combinations
        for supp in supplements:
            if supp.strip() and primary_goal:
                key = f"{supp.strip()}_{primary_goal}"
                combinations["supplement_goal"][key] = combinations["supplement_goal"].get(key, 0) + 1
        
        # Track supplement + population combinations
        for supp in supplements:
            if supp.strip() and population:
                key = f"{supp.strip()}_{population}"
                combinations["supplement_population"][key] = combinations["supplement_population"].get(key, 0) + 1
        
        # Track goal + population combinations
        if primary_goal and population:
            key = f"{primary_goal}_{population}"
            combinations["goal_population"][key] = combinations["goal_population"].get(key, 0) + 1
        
        # Track study type + goal combinations
        if study_type and primary_goal:
            key = f"{study_type}_{primary_goal}"
            combinations["study_type_goal"][key] = combinations["study_type_goal"].get(key, 0) + 1
        
        # Track journal + supplement combinations
        for supp in supplements:
            if supp.strip() and journal:
                key = f"{journal}_{supp.strip()}"
                combinations["journal_supplement"][key] = combinations["journal_supplement"].get(key, 0) + 1
    
    return combinations


def calculate_combination_weights(combinations: Dict[str, Dict[str, int]], total_docs: int) -> Dict[str, Dict[str, float]]:
    """
    Calculate weights based on combination representation
    
    Args:
        combinations: Dictionary with combination counts
        total_docs: Total number of documents
        
    Returns:
        Dictionary with combination weights
    """
    weights = {}
    
    # Dynamic target percentage based on dataset size
    # For small datasets, use higher target percentage to avoid extreme penalties
    if total_docs < 100:
        target_percentage = 0.1  # 10% for small datasets
    elif total_docs < 1000:
        target_percentage = 0.05  # 5% for medium datasets
    else:
        target_percentage = 0.01  # 1% for large datasets
    
    for combo_type, combo_counts in combinations.items():
        weights[combo_type] = {}
        
        for combo, count in combo_counts.items():
            current_percentage = count / total_docs
            
            if current_percentage > target_percentage * 5:  # Severely over-represented
                weights[combo_type][combo] = -4.0  # Strong penalty
            elif current_percentage > target_percentage * 3:  # Over-represented
                weights[combo_type][combo] = -2.0  # Moderate penalty
            elif current_percentage > target_percentage * 2:  # Well-represented
                weights[combo_type][combo] = -1.0  # Small penalty
            elif current_percentage > target_percentage:  # Adequately represented
                weights[combo_type][combo] = 0.0  # Neutral
            elif current_percentage > target_percentage * 0.5:  # Under-represented
                weights[combo_type][combo] = 1.5  # Moderate bonus
            else:  # Severely under-represented
                weights[combo_type][combo] = 3.0  # Strong bonus
    
    return weights


def calculate_combination_score(paper: Dict, combination_weights: Dict[str, Dict[str, float]]) -> float:
    """
    Calculate score based on paper's factor combinations with gating and normalization
    
    Args:
        paper: Paper dictionary
        combination_weights: Dictionary with combination weights
        
    Returns:
        Combination score (gated and normalized)
    """
    # Compute base combination score
    score = 0.0
    
    # Extract paper factors
    supplements = (paper.get("supplements") or "").split(",")
    primary_goal = paper.get("primary_goal") or ""
    population = paper.get("population") or ""
    study_type = paper.get("study_type") or ""
    journal = (paper.get("journal") or "").lower()
    
    # Check supplement + goal combinations
    for supp in supplements:
        if supp.strip() and primary_goal:
            key = f"{supp.strip()}_{primary_goal}"
            weight = combination_weights.get("supplement_goal", {}).get(key, 0.0)
            score += weight
    
    # Check supplement + population combinations
    for supp in supplements:
        if supp.strip() and population:
            key = f"{supp.strip()}_{population}"
            weight = combination_weights.get("supplement_population", {}).get(key, 0.0)
            score += weight
    
    # Check goal + population combinations
    if primary_goal and population:
        key = f"{primary_goal}_{population}"
        weight = combination_weights.get("goal_population", {}).get(key, 0.0)
        score += weight
    
    # Check study type + goal combinations
    if study_type and primary_goal:
        key = f"{study_type}_{primary_goal}"
        weight = combination_weights.get("study_type_goal", {}).get(key, 0.0)
        score += weight
    
    # Check journal + supplement combinations
    for supp in supplements:
        if supp.strip() and journal:
            key = f"{journal}_{supp.strip()}"
            weight = combination_weights.get("journal_supplement", {}).get(key, 0.0)
            score += weight
    
    # Gate boosting (do NOT cap counts)
    category = paper.get("study_category", "other")
    outcomes_str = (paper.get("outcomes") or "").strip()
    outcomes_present = bool(outcomes_str)
    
    if (category == "observational_usage" or 
        (not outcomes_present and category not in {"intervention", "meta_analysis", "systematic_review"})):
        logging.debug(f"combo_gated pmid={paper.get('pmid')} category={category} outcomes={outcomes_present}")
        return 0.0  # Leave reliability untouched
    
    # Normalize by breadth and cap relative to reliability
    if score > 0:
        breadth = max(1, len([s for s in supplements if s.strip()]))
        score *= (1.0 / math.sqrt(breadth))
        base = float(paper.get("reliability_score", 0.0))
        score = min(score, min(5.0, 0.30 * base))
        logging.debug(f"combo_norm pmid={paper.get('pmid')} breadth={breadth} base={base:.1f} final={score:.3f}")
    
    return score


def iterative_diversity_filtering(papers: list, target_count: int, elimination_per_round: int = 1000) -> list:
    """
    Iteratively eliminate papers while recalculating diversity weights each round.
    Supports an optional protected set of IDs that will not be eliminated.
    """
    return _iterative_diversity_filtering_internal(papers, target_count, elimination_per_round, protected_ids=None)

# ---- Minimum-quota / protected IDs support ----

# Env-configurable knobs (documented defaults)
MIN_PER_SUPPLEMENT = int(os.getenv("MIN_PER_SUPPLEMENT", "3"))  # 0 disables
INCLUDE_LOW_QUALITY_IN_MIN = os.getenv("INCLUDE_LOW_QUALITY_IN_MIN", "true").lower() == "true"
MIN_QUOTA_RARE_ONLY = os.getenv("MIN_QUOTA_RARE_ONLY", "false").lower() == "true"
RARE_THRESHOLD = int(os.getenv("RARE_THRESHOLD", "5"))
EXCLUDED_SUPPS_FOR_MIN = {s.strip() for s in os.getenv("EXCLUDED_SUPPS_FOR_MIN", "nitric-oxide").split(",") if s.strip()}

def _get_supps(doc: Dict[str, Any]) -> List[str]:
    raw = (doc.get("supplements") or "").split(",")
    return [s.strip() for s in raw if s.strip()]

def _build_supp_index(docs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_supp: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        for s in _get_supps(d):
            by_supp.setdefault(s, []).append(d)
    # sort each list by reliability desc, then year desc as tie-breaker
    for s, lst in by_supp.items():
        lst.sort(key=lambda x: (x.get("reliability_score", 0.0), x.get("year", 0) or 0), reverse=True)
    return by_supp

def compute_enhanced_quota_ids(
    all_docs: List[Dict[str, Any]],
    min_overall: int = 10,
    min_per_goal: int = 2,
    prefer_fulltext: bool = True,
    quality_floor: float = 0.0,
) -> Set[str]:
    """
    Enhanced quota system:
    - Protects top N overall papers per supplement
    - PLUS top M papers per supplement×goal combination
    - Allows overlaps (typically results in 10-14 protected per supplement)
    - Prefers full-text when quality scores are equal
    
    Returns set of protected doc IDs.
    """
    protected: Set[str] = set()
    if min_overall <= 0 and min_per_goal <= 0:
        return protected
    
    by_supp = _build_supp_index(all_docs)
    
    for supp, supp_docs in by_supp.items():
        # Apply quality floor
        quality_docs = [d for d in supp_docs if d.get("reliability_score", 0.0) >= quality_floor]
        if not quality_docs:
            continue
        
        # Sort by: reliability DESC, then fulltext availability DESC (if prefer_fulltext)
        def sort_key(doc):
            score = doc.get("reliability_score", 0.0)
            # Tiebreaker: full-text availability (from sources metadata or flag)
            has_fulltext = False
            if prefer_fulltext:
                sources = doc.get("sources", {})
                pmc = sources.get("pmc", {}) if isinstance(sources, dict) else {}
                unpaywall = sources.get("unpaywall", {}) if isinstance(sources, dict) else {}
                has_fulltext = (
                    pmc.get("has_body_sections", False) or
                    unpaywall.get("has_body_sections", False) or
                    doc.get("has_fulltext", False)  # Fallback flag
                )
            return (-score, not has_fulltext)  # Negative for DESC, not for tiebreak
        
        sorted_docs = sorted(quality_docs, key=sort_key)
        
        # Protect top N overall
        for d in sorted_docs[:min_overall]:
            if d.get("id"):
                protected.add(d["id"])
        
        # Protect top M per goal
        by_goal: Dict[str, List[Dict[str, Any]]] = {}
        for d in quality_docs:
            goal = d.get("primary_goal", "").strip() or "general"
            by_goal.setdefault(goal, []).append(d)
        
        for goal, goal_docs in by_goal.items():
            sorted_goal = sorted(goal_docs, key=sort_key)
            for d in sorted_goal[:min_per_goal]:
                if d.get("id"):
                    protected.add(d["id"])  # Set union handles overlaps
    
    return protected

def compute_minimum_quota_ids(
    all_docs: List[Dict[str, Any]],
    min_per_supp: Optional[int] = None,
    include_low_quality: Optional[bool] = None,
    rare_only: Optional[bool] = None,
    rare_threshold: Optional[int] = None,
    exclude_supps: Optional[Set[str]] = None,
    quality_floor: float = 0.0,
) -> Set[str]:
    """
    Returns a set of doc IDs that should be protected (not eliminated) to ensure
    each supplement has at least `min_per_supp` papers in the final selection.

    If `include_low_quality=True`, low-reliability docs can be selected to meet the quota.
    If `rare_only=True`, quotas apply only to supplements with <= rare_threshold papers in all_docs.
    Supplements listed in `exclude_supps` are ignored (no quotas).
    """
    if min_per_supp is None:
        min_per_supp = MIN_PER_SUPPLEMENT
    if include_low_quality is None:
        include_low_quality = INCLUDE_LOW_QUALITY_IN_MIN
    if rare_only is None:
        rare_only = MIN_QUOTA_RARE_ONLY
    if rare_threshold is None:
        rare_threshold = RARE_THRESHOLD
    if exclude_supps is None:
        exclude_supps = EXCLUDED_SUPPS_FOR_MIN

    protected: Set[str] = set()
    if min_per_supp <= 0:
        return protected

    by_supp = _build_supp_index(all_docs)
    for supp, docs in by_supp.items():
        if supp in exclude_supps:
            continue
        if rare_only and len(docs) > rare_threshold:
            continue
        picked = 0
        for d in docs:
            # Respect an optional quality floor if include_low_quality is False
            if (include_low_quality or d.get("reliability_score", 0.0) >= quality_floor):
                if d.get("id"):
                    protected.add(d["id"])
                    picked += 1
            if picked >= min_per_supp:
                break
    return protected

def _iterative_diversity_filtering_internal(
    papers: List[Dict[str, Any]],
    target_count: int,
    elimination_per_round: int = 1000,
    protected_ids: Optional[Set[str]] = None,
    tiebreak_threshold: float = 0.8,
    prefer_fulltext: bool = True,
) -> List[Dict[str, Any]]:
    """
    Iteratively eliminate papers while recalculating diversity weights each round.
    
    Args:
        papers: List of papers to filter
        target_count: Target number of papers
        elimination_per_round: How many to eliminate per round
        protected_ids: Set of IDs that cannot be eliminated
        tiebreak_threshold: When enhanced scores are within this value, use full-text as tiebreaker
        prefer_fulltext: If True, prefer papers with full-text in tiebreak situations
    """
    protected_ids = protected_ids or set()
    current_papers = papers.copy()
    round_num = 1

    while len(current_papers) > target_count:
        papers_to_eliminate = min(elimination_per_round, len(current_papers) - target_count)

        # Recalculate combination weights based on current paper set
        combinations = analyze_combination_distribution(current_papers)
        combination_weights = calculate_combination_weights(combinations, len(current_papers))

        # Re-score with updated weights
        for paper in current_papers:
            combination_score = calculate_combination_score(paper, combination_weights)
            paper["combination_score"] = combination_score
            paper["enhanced_score"] = paper.get("reliability_score", 0) + combination_score
            
            # Check full-text availability for tiebreaking
            if prefer_fulltext:
                sources = paper.get("sources", {})
                pmc = sources.get("pmc", {}) if isinstance(sources, dict) else {}
                unpaywall = sources.get("unpaywall", {}) if isinstance(sources, dict) else {}
                paper["_has_fulltext"] = (
                    pmc.get("has_body_sections", False) or
                    unpaywall.get("has_body_sections", False) or
                    paper.get("has_fulltext", False)  # Fallback flag
                )

        # Sort with tiebreaking: enhanced_score ASC, then prefer NOT full-text (eliminate those first)
        def sort_key(doc):
            score = doc.get("enhanced_score", 0)
            has_ft = doc.get("_has_fulltext", False) if prefer_fulltext else False
            return (score, has_ft)  # Lower score first, then non-fulltext first (False < True)
        
        current_papers.sort(key=sort_key)

        # Find cutoff score for this round
        if papers_to_eliminate < len(current_papers):
            cutoff_score = current_papers[papers_to_eliminate - 1].get("enhanced_score", 0)
        else:
            cutoff_score = float('inf')

        # Remove from the bottom up, applying tiebreak in the threshold zone
        eliminated = 0
        survivors: List[Dict[str, Any]] = []
        for d in current_papers:
            if d.get("id") in protected_ids:
                survivors.append(d)
                continue
            
            if eliminated >= papers_to_eliminate:
                survivors.append(d)
                continue
            
            score = d.get("enhanced_score", 0)
            
            # If score is clearly above cutoff, keep it
            if score > cutoff_score + tiebreak_threshold:
                survivors.append(d)
                continue
            
            # If score is within tiebreak threshold of cutoff, consider full-text
            if prefer_fulltext and abs(score - cutoff_score) <= tiebreak_threshold:
                if d.get("_has_fulltext", False):
                    # In tiebreak zone with full-text: keep it
                    survivors.append(d)
                    continue
            
            # Eliminate this paper
            eliminated += 1

        current_papers = survivors
        round_num += 1

        # Safety: if we couldn't eliminate enough because too many are protected, exit.
        if eliminated == 0 and len(current_papers) > target_count:
            break

    # Final sort by enhanced score (desc) for stable output
    current_papers.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
    return current_papers[:target_count]

# Backward-compatible wrapper that allows passing protected IDs
def iterative_diversity_filtering_with_protection(
    papers: List[Dict[str, Any]],
    target_count: int,
    elimination_per_round: int = 1000,
    protected_ids: Optional[Set[str]] = None,
    tiebreak_threshold: float = 0.8,
    prefer_fulltext: bool = True,
) -> List[Dict[str, Any]]:
    return _iterative_diversity_filtering_internal(
        papers, 
        target_count, 
        elimination_per_round, 
        protected_ids,
        tiebreak_threshold,
        prefer_fulltext
    )


def should_run_iterative_diversity(candidate_count: int, target_count: int) -> bool:
    """
    Determine if iterative diversity filtering should be run
    
    Args:
        candidate_count: Number of candidate papers
        target_count: Target number of papers
        
    Returns:
        True if iterative diversity should be run
    """
    return candidate_count > target_count


def get_diversity_threshold() -> int:
    """
    Get the diversity rounds threshold
    
    Returns:
        Threshold value
    """
    return DIVERSITY_ROUNDS_THRESHOLD
