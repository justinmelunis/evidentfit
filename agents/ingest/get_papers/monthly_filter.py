"""
Monthly quality filtering using hard-coded thresholds.

Evaluates each paper against each supplement tag independently:
- Uses hard-coded quality thresholds (from bootstrap corpus analysis)
- Includes top N most recent papers per supplement (recency guarantee)
- Multi-supplement papers evaluated per-tag (use lowest threshold)
- Filters supplement tags based on which ones qualify
"""

import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from monthly_thresholds import (
    MONTHLY_THRESHOLDS,
    RECENCY_TOP_N,
    ALWAYS_ADD_STUDY_TYPES,
    EXCEPTIONAL_QUALITY_THRESHOLD,
    RECENCY_MIN_QUALITY,
)

logger = logging.getLogger(__name__)


def parse_supplements(paper: Dict[str, Any]) -> List[str]:
    """Extract supplement list from paper."""
    supps = paper.get('supplements', '')
    if isinstance(supps, str):
        supps = [s.strip() for s in supps.split(',') if s.strip()]
    return supps


def apply_recency_guarantee(papers: List[Dict[str, Any]]) -> None:
    """
    Mark the top N most recent papers per supplement for guaranteed inclusion.
    Modifies papers in-place by adding '_recency_guaranteed' flag.
    
    Rules:
    - Large supplements (500+ papers): Top 10 most recent
    - Small supplements: Top 2 most recent
    - Must meet minimum quality (2.5)
    """
    by_supplement = defaultdict(list)
    
    for p in papers:
        for s in parse_supplements(p):
            by_supplement[s].append(p)
    
    guaranteed_count = 0
    
    for supplement, supp_papers in by_supplement.items():
        # Determine N based on supplement size
        is_large = supplement in RECENCY_TOP_N["large_supplements"]
        n = RECENCY_TOP_N["large_supplement_n"] if is_large else RECENCY_TOP_N["default"]
        
        # Sort by year (desc), then by pmid (for stable sorting)
        supp_papers_sorted = sorted(
            supp_papers,
            key=lambda p: (p.get("year", 0), p.get("pmid", "")),
            reverse=True
        )
        
        # Mark top N that meet minimum quality
        count = 0
        for p in supp_papers_sorted:
            if count >= n:
                break
            if p.get("reliability_score", 0) >= RECENCY_MIN_QUALITY:
                if "_recency_guaranteed_for" not in p:
                    p["_recency_guaranteed_for"] = []
                p["_recency_guaranteed_for"].append(supplement)
                count += 1
                guaranteed_count += 1
    
    logger.info(f"Recency guarantee: Marked {guaranteed_count} paper-supplement combinations")


def evaluate_paper_for_supplement(
    paper: Dict[str, Any],
    supplement: str
) -> Tuple[bool, str]:
    """
    Decide if this paper should be included for this specific supplement.
    
    Returns: (include: bool, reason: str)
    """
    quality = paper.get("reliability_score", 0)
    study_type = paper.get("study_type", "")
    
    # Tier 1A: Always add study types
    if study_type in ALWAYS_ADD_STUDY_TYPES:
        return True, "meta_analysis_or_review"
    
    # Tier 1B: Exceptional quality
    if quality >= EXCEPTIONAL_QUALITY_THRESHOLD:
        return True, f"exceptional_quality_{quality:.2f}"
    
    # Tier 1C: Recency guarantee
    if "_recency_guaranteed_for" in paper and supplement in paper["_recency_guaranteed_for"]:
        return True, f"recency_guarantee_{quality:.2f}"
    
    # Tier 2: Quality threshold check
    threshold = MONTHLY_THRESHOLDS.get(supplement, 3.0)  # Default 3.0 for unknown supplements
    
    if quality >= threshold:
        return True, f"meets_threshold_{threshold:.2f}"
    
    # Tier 3: Reject
    return False, f"below_threshold_{threshold:.2f}"


def apply_monthly_quality_filter(
    papers: List[Dict[str, Any]],
    mode: str
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Apply monthly quality filtering using hard-coded thresholds.
    
    For each paper:
    1. Evaluate against each supplement tag
    2. Keep only supplement tags that qualify
    3. Include paper if it qualifies for AT LEAST ONE supplement
    
    Args:
        papers: List of papers from get_papers
        mode: 'bootstrap' or 'monthly'
        
    Returns:
        (filtered_papers, removal_stats)
    """
    if mode != "monthly":
        logger.info("Monthly filter skipped (mode != monthly)")
        return papers, {}
    
    logger.info(f"Applying monthly quality filter to {len(papers)} papers...")
    
    # First pass: Apply recency guarantee
    apply_recency_guarantee(papers)
    
    # Second pass: Evaluate each paper against each supplement
    qualified_papers = []
    removal_stats = defaultdict(int)
    
    for paper in papers:
        original_supplements = parse_supplements(paper)
        qualified_supplements = []
        rejection_reasons = {}
        
        for supplement in original_supplements:
            include, reason = evaluate_paper_for_supplement(paper, supplement)
            
            if include:
                qualified_supplements.append(supplement)
            else:
                rejection_reasons[supplement] = reason
                removal_stats[f"{supplement}_{reason}"] += 1
        
        # Keep paper if it qualifies for AT LEAST ONE supplement
        if qualified_supplements:
            paper_copy = dict(paper)
            paper_copy["supplements"] = ",".join(qualified_supplements)
            
            # Track removed supplements for audit
            removed = list(set(original_supplements) - set(qualified_supplements))
            if removed:
                paper_copy["_removed_supplements"] = removed
                paper_copy["_removal_reasons"] = rejection_reasons
            
            qualified_papers.append(paper_copy)
        else:
            # Paper doesn't qualify for ANY supplement
            removal_stats["rejected_all_supplements"] += 1
    
    logger.info(f"Monthly filter: {len(papers)} → {len(qualified_papers)} papers")
    logger.info(f"  Kept for at least one supplement: {len(qualified_papers)}")
    logger.info(f"  Rejected completely: {len(papers) - len(qualified_papers)}")
    
    # Log top removal reasons
    top_reasons = sorted(removal_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_reasons:
        logger.info("  Top removal reasons:")
        for reason, count in top_reasons:
            logger.info(f"    {reason}: {count}")
    
    return qualified_papers, dict(removal_stats)

