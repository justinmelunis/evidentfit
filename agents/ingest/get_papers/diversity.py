"""
Diversity analysis and iterative filtering

Handles combination analysis, weight calculation, and iterative diversity filtering
to ensure balanced representation across supplement-goal-population combinations.
No per-supplement caps before diversity - only combination weights and iterative filtering.
"""

import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Environment variables
DIVERSITY_ROUNDS_THRESHOLD = int(os.getenv("DIVERSITY_ROUNDS_THRESHOLD", "50000"))


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
    
    for doc in docs:
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
    Calculate score based on paper's factor combinations with quality safeguards
    
    Args:
        paper: Paper dictionary
        combination_weights: Dictionary with combination weights
        
    Returns:
        Combination score
    """
    score = 0.0
    
    # Extract paper factors
    supplements = (paper.get("supplements") or "").split(",")
    primary_goal = paper.get("primary_goal") or ""
    population = paper.get("population") or ""
    study_type = paper.get("study_type") or ""
    journal = (paper.get("journal") or "").lower()
    
    # Quality safeguards: Don't boost low-quality papers too much
    base_reliability = paper.get("reliability_score", 0)
    max_combination_boost = min(5.0, base_reliability * 0.3)  # Cap boost at 30% of base score
    
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
    
    # Apply quality safeguard: Cap positive combination scores for low-quality papers
    if score > 0 and base_reliability < 5.0:  # Low-quality paper
        score = min(score, max_combination_boost)
    
    return score


def iterative_diversity_filtering(papers: List[Dict], target_count: int, 
                                 elimination_per_round: int = 2000) -> List[Dict]:
    """
    Iteratively eliminate papers while recalculating diversity weights each round.
    
    This provides better diversity outcomes than single-pass selection by:
    1. Eliminating lowest-scoring papers in batches
    2. Recalculating combination weights after each elimination
    3. Re-scoring remaining papers with updated weights
    4. Repeating until target count is reached
    
    Args:
        papers: List of papers with reliability scores
        target_count: Final number of papers to select
        elimination_per_round: Number of papers to eliminate each round
        
    Returns:
        List of selected papers with optimal diversity balance
    """
    current_papers = papers.copy()
    round_num = 1
    
    logger.info(f"Starting iterative diversity filtering:")
    logger.info(f"  Initial papers: {len(current_papers):,}")
    logger.info(f"  Target papers: {target_count:,}")
    logger.info(f"  Elimination per round: {elimination_per_round:,}")
    logger.info(f"  Estimated rounds: {(len(current_papers) - target_count) // elimination_per_round + 1}")
    
    while len(current_papers) > target_count:
        papers_to_eliminate = min(elimination_per_round, len(current_papers) - target_count)
        
        logger.info(f"Round {round_num}: {len(current_papers):,} papers -> eliminating {papers_to_eliminate:,}")
        
        # Recalculate combination weights based on current paper set
        combinations = analyze_combination_distribution(current_papers)
        combination_weights = calculate_combination_weights(combinations, len(current_papers))
        
        # Re-score all current papers with updated weights
        for paper in current_papers:
            combination_score = calculate_combination_score(paper, combination_weights)
            paper["combination_score"] = combination_score
            paper["enhanced_score"] = paper.get("reliability_score", 0) + combination_score
        
        # Sort by enhanced score and eliminate lowest-scoring papers
        current_papers.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
        current_papers = current_papers[:-papers_to_eliminate]  # Remove bottom papers
        
        # Show progress
        if round_num <= 3 or round_num % 5 == 0:
            # Show top combination weights for first few rounds and every 5th round
            # Flatten nested weights structure for display
            flat_weights = []
            for combo_type, combo_dict in combination_weights.items():
                for combo, weight in combo_dict.items():
                    flat_weights.append((f"{combo_type}:{combo}", weight))
            top_weights = sorted(flat_weights, key=lambda x: abs(x[1]), reverse=True)[:5]
            logger.info(f"  Top combination weights: {dict(top_weights)}")
        
        round_num += 1
        
        # Safety check
        if round_num > 50:  # Prevent infinite loops
            logger.warning(f"⚠️  Safety limit reached at round {round_num}. Stopping.")
            break
    
    logger.info(f"Iterative filtering complete:")
    logger.info(f"  Final papers: {len(current_papers):,}")
    logger.info(f"  Rounds completed: {round_num - 1}")
    
    # Final sort by enhanced score
    current_papers.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
    
    return current_papers[:target_count]


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
