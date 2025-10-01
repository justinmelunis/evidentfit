"""
Agent D: Deterministic stack builder with CME dosing and protein GAP logic
"""
import math
from typing import Dict, List, Optional, Union

def creatine_plan_by_form(weight_kg: float, form: str = None, include_loading: bool = False) -> Dict:
    """
    Generate creatine plan using CME (Creatine Monohydrate Equivalent) dosing
    
    Args:
        weight_kg: User weight in kg
        form: "monohydrate"|"anhydrous"|"hcl"|None (defaults to monohydrate)
        include_loading: Whether to include loading phase
    
    Returns:
        Dict with supplement, form, doses, timing, evidence, why, notes
    """
    if form is None:
        form = "monohydrate"
    
    # Base fractions (creatine base per gram of product)
    base_fractions = {
        "monohydrate": 0.879,  # baseline; CME factor 1.00
        "anhydrous": 1.000,
        "hcl": 0.782
    }
    
    if form not in base_fractions:
        raise ValueError(f"Unsupported creatine form: {form}. Supported: {list(base_fractions.keys())}")
    
    # CME maintenance targets
    if weight_kg < 70:
        cme_maintenance = 3.0
    else:
        cme_maintenance = 5.0
    
    # Calculate form grams needed for CME target
    base_frac = base_fractions[form]
    form_g_maintenance = round_to_0_25(cme_maintenance * 0.879 / base_frac)
    
    doses = []
    
    if include_loading:
        # Loading phase: 0.3 g/kg/day for 5-7 days
        cme_loading = 0.3 * weight_kg
        form_g_loading = round_to_0_25(cme_loading * 0.879 / base_frac)
        doses.append({
            "value": form_g_loading,
            "unit": "g",
            "days": 7,
            "split": 3  # 2-3x daily, use middle value
        })
    
    # Maintenance phase
    doses.append({
        "value": form_g_maintenance,
        "unit": "g",
        "days": None,  # ongoing
        "split": 1  # 1x daily
    })
    
    # Notes
    notes = [f"≈ equivalent to {cme_maintenance} g creatine monohydrate (CME)"]
    if form == "monohydrate":
        notes.append("Most researched form with proven efficacy")
    elif form == "anhydrous":
        notes.append("Higher creatine content per gram")
    elif form == "hcl":
        notes.append("May have better solubility")
    
    return {
        "supplement": "creatine",
        "form": form,
        "doses": doses,
        "timing": "Post-workout or with meals",
        "evidence": "A",
        "why": "Well-established for strength and muscle mass gains",
        "notes": notes
    }

def protein_gap_plan(
    goal: str, 
    weight_kg: float, 
    diet_g_per_day: Optional[float] = None, 
    diet_g_per_kg: Optional[float] = None,
    serving_protein_g: int = 25,
    include_threshold_g: int = 20
) -> Optional[Dict]:
    """
    Calculate protein gap and return supplement plan if gap >= threshold
    
    Args:
        goal: "strength"|"hypertrophy"|"endurance"|"weight_loss"|"general"
        weight_kg: User weight in kg
        diet_g_per_day: Current protein intake per day (optional)
        diet_g_per_kg: Current protein intake per kg (optional)
        serving_protein_g: Protein per serving (default 25g)
        include_threshold_g: Minimum gap to include supplement (default 20g)
    
    Returns:
        Dict with supplement plan or None if gap < threshold
    """
    # Target protein per kg per day based on goal
    target_per_kg = {
        "strength": 1.8,
        "hypertrophy": 1.8,
        "endurance": 1.4,
        "weight_loss": 2.0,
        "general": 1.5
    }.get(goal, 1.5)
    
    # Calculate target and current protein
    target_g = target_per_kg * weight_kg
    current_g = 0
    
    if diet_g_per_day is not None:
        current_g = diet_g_per_day
    elif diet_g_per_kg is not None:
        current_g = diet_g_per_kg * weight_kg
    
    # Calculate gap
    gap_g = max(0, target_g - current_g)
    gap_g_rounded = round_to_5(gap_g)
    
    # Only include if gap >= threshold
    if gap_g_rounded < include_threshold_g:
        return None
    
    # Calculate servings
    servings = math.ceil(gap_g_rounded / serving_protein_g)
    
    return {
        "supplement": "protein",
        "doses": [{
            "value": gap_g_rounded,
            "unit": "g",
            "days": None,
            "split": f"{servings} serving{'s' if servings > 1 else ''}"
        }],
        "timing": "Post-workout or between meals",
        "evidence": "A",
        "why": f"Close protein gap to reach {target_per_kg} g/kg/day target",
        "notes": [
            "Prefer food first; supplement only to close the gap",
            "Kidney disease → consult clinician"
        ]
    }

def round_to_0_25(value: float) -> float:
    """Round to nearest 0.25"""
    return round(value * 4) / 4

def round_to_5(value: float) -> float:
    """Round to nearest 5"""
    return round(value / 5) * 5

# Additional helper functions for stack building
def get_evidence_grade(supplement: str) -> str:
    """Get evidence grade for supplement"""
    grades = {
        "creatine": "A",
        "caffeine": "A", 
        "beta-alanine": "B",
        "protein": "A",
        "citrulline": "B",
        "nitrate": "B",
        "hmb": "C",
        "bcaa": "C",
        "tribulus": "D",
        "d-aspartic-acid": "D",
        "betaine": "C",
        "taurine": "C",
        "carnitine": "C",
        "zma": "C",
        "glutamine": "C",
        "cla": "C",
        "ecdysteroids": "D",
        "deer-antler": "D"
    }
    return grades.get(supplement, "D")

def get_supplement_timing(supplement: str) -> str:
    """Get recommended timing for supplement"""
    timings = {
        "creatine": "Post-workout or with meals",
        "caffeine": "Pre-workout (avoid late in day)",
        "beta-alanine": "Split throughout day",
        "protein": "Post-workout or between meals",
        "citrulline": "Pre-workout",
        "nitrate": "Pre-workout",
        "hmb": "Post-workout",
        "bcaa": "Pre/during/post workout",
        "tribulus": "Morning",
        "d-aspartic-acid": "Morning",
        "betaine": "Pre-workout",
        "taurine": "Pre-workout",
        "carnitine": "Pre-workout",
        "zma": "Evening",
        "glutamine": "Post-workout",
        "cla": "With meals",
        "ecdysteroids": "Pre-workout",
        "deer-antler": "Morning"
    }
    return timings.get(supplement, "As directed")

def get_supplement_why(supplement: str) -> str:
    """Get brief explanation of why supplement is recommended"""
    reasons = {
        "creatine": "Well-established for strength and muscle mass gains",
        "caffeine": "Improves focus, energy, and performance",
        "beta-alanine": "Buffers muscle acidity, delays fatigue",
        "protein": "Essential for muscle protein synthesis",
        "citrulline": "May improve blood flow and performance",
        "nitrate": "May improve blood flow and endurance",
        "hmb": "May help preserve muscle during cutting",
        "bcaa": "May reduce muscle breakdown during training",
        "tribulus": "Limited evidence for testosterone support",
        "d-aspartic-acid": "Limited evidence for testosterone support",
        "betaine": "May improve power output",
        "taurine": "May improve performance and recovery",
        "carnitine": "May improve fat oxidation",
        "zma": "May improve sleep and recovery",
        "glutamine": "May support immune function and recovery",
        "cla": "Limited evidence for fat loss",
        "ecdysteroids": "Limited evidence for muscle growth",
        "deer-antler": "Limited evidence, not recommended"
    }
    return reasons.get(supplement, "Limited evidence")
