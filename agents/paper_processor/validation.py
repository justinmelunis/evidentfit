"""
Validation module for paper processor output quality.
"""
import logging
from typing import Dict, List, Tuple, Any

LOG = logging.getLogger("paper_processor.validation")


def validate_card(card: Dict[str, Any]) -> Tuple[bool, float, List[str]]:
    """
    Validate card quality and return quality score.
    
    Returns:
        (is_valid, quality_score, missing_critical_fields)
        
    Quality scoring (0-1):
    - population_size present: +0.20
    - dose_g_per_day present: +0.20
    - duration_weeks present: +0.15
    - effect_sizes with p_values: +0.25
    - safety information: +0.10
    - study metadata complete: +0.10
    """
    missing = []
    score = 0.0
    
    # Check population size
    if card.get("population_size") is not None:
        score += 0.20
    else:
        missing.append("population_size")
    
    # Check intervention dose
    intervention_details = card.get("intervention_details", {})
    if intervention_details.get("dose_g_per_day") is not None:
        score += 0.20
    else:
        missing.append("dose_g_per_day")
    
    # Check duration
    if intervention_details.get("duration_weeks") is not None:
        score += 0.15
    else:
        missing.append("duration_weeks")
    
    # Check effect sizes with p-values
    effect_sizes = card.get("effect_sizes", [])
    has_effect_sizes = False
    for effect in effect_sizes:
        if effect.get("value") is not None and effect.get("p_value") is not None:
            has_effect_sizes = True
            break
    
    if has_effect_sizes:
        score += 0.25
    else:
        missing.append("effect_sizes_with_p_values")
    
    # Check safety information
    safety_details = card.get("safety_details", {})
    has_safety = (
        safety_details.get("adverse_events") or 
        safety_details.get("contraindications") or 
        safety_details.get("safety_grade") or
        card.get("safety", {}).get("notes")
    )
    
    if has_safety:
        score += 0.10
    else:
        missing.append("safety_information")
    
    # Check study metadata completeness
    meta = card.get("meta", {})
    has_metadata = (
        meta.get("title") and 
        meta.get("journal") and 
        meta.get("year") and 
        meta.get("pmid")
    )
    
    if has_metadata:
        score += 0.10
    else:
        missing.append("complete_metadata")
    
    # Card is valid if quality score >= 0.60
    is_valid = score >= 0.60
    
    return is_valid, score, missing


def validate_batch(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate a batch of cards and return summary statistics.
    """
    total = len(cards)
    valid_count = 0
    high_quality_count = 0  # >= 0.80
    quality_scores = []
    missing_fields = {}
    
    for card in cards:
        is_valid, score, missing = validate_card(card)
        quality_scores.append(score)
        
        if is_valid:
            valid_count += 1
        
        if score >= 0.80:
            high_quality_count += 1
        
        # Track missing fields
        for field in missing:
            missing_fields[field] = missing_fields.get(field, 0) + 1
    
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    
    return {
        "total_cards": total,
        "valid_cards": valid_count,
        "high_quality_cards": high_quality_count,
        "validity_rate": valid_count / total if total > 0 else 0.0,
        "high_quality_rate": high_quality_count / total if total > 0 else 0.0,
        "average_quality_score": avg_quality,
        "missing_fields": missing_fields,
        "quality_distribution": {
            "excellent": sum(1 for s in quality_scores if s >= 0.90),
            "good": sum(1 for s in quality_scores if 0.80 <= s < 0.90),
            "fair": sum(1 for s in quality_scores if 0.60 <= s < 0.80),
            "poor": sum(1 for s in quality_scores if s < 0.60)
        }
    }


def get_quality_recommendations(validation_result: Dict[str, Any]) -> List[str]:
    """
    Generate recommendations based on validation results.
    """
    recommendations = []
    
    if validation_result["average_quality_score"] < 0.70:
        recommendations.append("Average quality score is below 70%. Consider improving LLM prompts or extraction logic.")
    
    if validation_result["validity_rate"] < 0.80:
        recommendations.append("Validity rate is below 80%. Many cards are missing critical fields.")
    
    missing_fields = validation_result["missing_fields"]
    if missing_fields.get("population_size", 0) > validation_result["total_cards"] * 0.3:
        recommendations.append("Population size missing in >30% of cards. Improve extraction from Methods section.")
    
    if missing_fields.get("dose_g_per_day", 0) > validation_result["total_cards"] * 0.3:
        recommendations.append("Dose information missing in >30% of cards. Improve extraction from Methods section.")
    
    if missing_fields.get("effect_sizes_with_p_values", 0) > validation_result["total_cards"] * 0.5:
        recommendations.append("Effect sizes missing in >50% of cards. Improve extraction from Results section.")
    
    if missing_fields.get("safety_information", 0) > validation_result["total_cards"] * 0.4:
        recommendations.append("Safety information missing in >40% of cards. Improve extraction from Discussion section.")
    
    return recommendations


def log_validation_results(validation_result: Dict[str, Any], logger: logging.Logger = None):
    """
    Log validation results in a structured format.
    """
    if logger is None:
        logger = LOG
    
    logger.info("=== VALIDATION RESULTS ===")
    logger.info(f"Total cards: {validation_result['total_cards']}")
    logger.info(f"Valid cards: {validation_result['valid_cards']} ({validation_result['validity_rate']:.1%})")
    logger.info(f"High quality cards: {validation_result['high_quality_cards']} ({validation_result['high_quality_rate']:.1%})")
    logger.info(f"Average quality score: {validation_result['average_quality_score']:.3f}")
    
    logger.info("Quality distribution:")
    dist = validation_result["quality_distribution"]
    logger.info(f"  Excellent (≥0.90): {dist['excellent']}")
    logger.info(f"  Good (0.80-0.89): {dist['good']}")
    logger.info(f"  Fair (0.60-0.79): {dist['fair']}")
    logger.info(f"  Poor (<0.60): {dist['poor']}")
    
    if validation_result["missing_fields"]:
        logger.info("Missing fields:")
        for field, count in sorted(validation_result["missing_fields"].items()):
            percentage = count / validation_result["total_cards"] * 100
            logger.info(f"  {field}: {count} ({percentage:.1f}%)")
    
    recommendations = get_quality_recommendations(validation_result)
    if recommendations:
        logger.info("Recommendations:")
        for rec in recommendations:
            logger.info(f"  - {rec}")


if __name__ == "__main__":
    # Test the validation module
    test_card = {
        "population_size": 45,
        "intervention_details": {
            "dose_g_per_day": 5.0,
            "duration_weeks": 8
        },
        "effect_sizes": [
            {"value": 0.45, "p_value": 0.02}
        ],
        "safety_details": {
            "adverse_events": ["mild GI discomfort"]
        },
        "meta": {
            "title": "Test Study",
            "journal": "Test Journal",
            "year": 2020,
            "pmid": "12345678"
        }
    }
    
    is_valid, score, missing = validate_card(test_card)
    print(f"Test card: valid={is_valid}, score={score:.3f}, missing={missing}")
    
    batch_result = validate_batch([test_card])
    log_validation_results(batch_result)
