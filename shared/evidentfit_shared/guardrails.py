"""
Deterministic safety and dosing guardrails for EvidentFit.

All safety logic is rule-based, not LLM-generated.
This ensures consistent, predictable safety checks.
"""

from typing import Dict, List, Tuple, Optional


# ============================================================================
# Contraindications
# ============================================================================

CONTRAINDICATIONS = {
    "creatine": [
        "renal_disease", "kidney_disease", "chronic_kidney_disease", "ckd",
        "dialysis", "nephropathy", "kidney_failure"
    ],
    "caffeine": [
        "arrhythmia", "atrial_fibrillation", "severe_anxiety", "panic_disorder",
        "insomnia", "tachycardia", "heart_palpitations"
    ],
    "nitrate": [
        "hypotension", "low_blood_pressure", "nitrate_medications", "viagra",
        "sildenafil", "tadalafil", "phosphodiesterase_inhibitors"
    ],
    "beta-alanine": [],  # Generally safe; paresthesia is benign
    "citrulline": ["hypotension"],
    "hmb": [],
    "bcaa": [],
    "protein": ["severe_kidney_disease"],  # Only severe cases
    "taurine": [],
    "carnitine": [],
    "zma": [],
    "glutamine": []
}


# ============================================================================
# Age-Based Restrictions
# ============================================================================

AGE_RESTRICTIONS = {
    "minor": {  # age < 18
        "block": ["caffeine", "stimulants", "experimental"],
        "caution": ["high-dose-protein", "creatine"],
        "note": "Recommend food-first approach for minors. Stimulants not advised.",
        "protein_max_g_per_kg": 2.0  # Conservative for growing adolescents
    },
    "pregnancy": {
        "block": ["high-dose-caffeine", "experimental", "ecdysteroids", "tribulus", "d-aspartic-acid"],
        "cap": {
            "caffeine": 200,  # mg/day max (ACOG guideline)
        },
        "caution": ["nitrate", "beta-alanine"],
        "note": "Conservative approach recommended during pregnancy. Consult healthcare provider."
    },
    "older_adult": {  # age >= 65
        "caution": ["high-dose-stimulants"],
        "note": "May benefit from HMB for muscle preservation. Start caffeine doses lower.",
        "caffeine_multiplier": 0.75  # Reduce caffeine dose by 25%
    }
}


# ============================================================================
# Condition-Based Adjustments
# ============================================================================

CONDITION_ADJUSTMENTS = {
    "hypertension": {
        "cap": {"caffeine": 200},  # mg/day
        "caution": ["nitrate", "stimulants", "licorice"],
        "note": "Blood pressure monitoring recommended. Caffeine may increase BP transiently."
    },
    "diabetes": {
        "caution": ["carb-based-supplements", "high-dose-carnitine"],
        "monitor": ["blood_glucose"],
        "note": "Monitor blood glucose response to supplements. Some may affect insulin sensitivity."
    },
    "anxiety": {
        "block": ["caffeine", "stimulants"],
        "note": "Stimulants may exacerbate anxiety symptoms."
    },
    "insomnia": {
        "block": ["caffeine", "stimulants"],
        "note": "Avoid stimulants if sleep issues present."
    },
    "gerd": {
        "caution": ["caffeine", "citric_acid_supplements"],
        "note": "Caffeine may worsen acid reflux in some individuals."
    }
}


# ============================================================================
# Medication Interactions
# ============================================================================

MEDICATION_INTERACTIONS = {
    "ssri": {
        "caution": ["caffeine", "stimulants", "5-htp", "st-johns-wort"],
        "note": "Stimulants may increase anxiety or interact with serotonergic medications."
    },
    "maoi": {
        "avoid": ["stimulants", "tyramine", "caffeine"],
        "note": "Serious interaction risk with MAOIs. Avoid all stimulants."
    },
    "anticoagulants": {
        "caution": ["high-dose-omega3", "garlic", "ginger", "vitamin-e", "vitamin-k"],
        "monitor": ["bleeding", "inr"],
        "note": "May affect clotting. Monitor INR if on warfarin."
    },
    "bp_meds": {
        "caution": ["stimulants", "nitrate", "licorice"],
        "monitor": ["blood_pressure"],
        "note": "May alter blood pressure response. Monitor BP regularly."
    },
    "diabetes_meds": {
        "caution": ["carb-based-supplements"],
        "monitor": ["blood_glucose"],
        "note": "May affect blood sugar. Monitor glucose levels."
    },
    "thyroid_meds": {
        "caution": ["kelp", "iodine", "soy"],
        "note": "Some supplements may interfere with thyroid hormone absorption."
    }
}


# ============================================================================
# Helper Functions
# ============================================================================

def normalize_condition(condition: str) -> str:
    """Normalize a condition string for matching."""
    return condition.lower().strip().replace(" ", "_").replace("-", "_")


def normalize_medication(med: str) -> str:
    """
    Normalize a medication string and map to drug class.
    
    This is a simple version; production would use a drug database.
    """
    med = med.lower().strip()
    
    # Map common brand/generic names to classes
    ssri_keywords = ["fluoxetine", "sertraline", "escitalopram", "citalopram", "paroxetine", "prozac", "zoloft", "lexapro"]
    maoi_keywords = ["phenelzine", "tranylcypromine", "isocarboxazid", "nardil", "parnate"]
    anticoag_keywords = ["warfarin", "coumadin", "apixaban", "rivaroxaban", "eliquis", "xarelto", "heparin"]
    bp_keywords = ["lisinopril", "amlodipine", "losartan", "metoprolol", "atenolol", "carvedilol"]
    diabetes_keywords = ["metformin", "insulin", "glipizide", "glyburide", "januvia", "jardiance"]
    
    if any(kw in med for kw in ssri_keywords):
        return "ssri"
    if any(kw in med for kw in maoi_keywords):
        return "maoi"
    if any(kw in med for kw in anticoag_keywords):
        return "anticoagulants"
    if any(kw in med for kw in bp_keywords):
        return "bp_meds"
    if any(kw in med for kw in diabetes_keywords):
        return "diabetes_meds"
    
    return "other"


def check_contraindications(profile: dict, supplement: str) -> Tuple[bool, str]:
    """
    Check if a supplement is contraindicated for a user.
    
    Args:
        profile: User profile dict
        supplement: Supplement name
        
    Returns:
        (is_safe, reason) tuple
    """
    conditions = [normalize_condition(c) for c in profile.get("conditions", [])]
    
    # Check direct contraindications
    blocked = CONTRAINDICATIONS.get(supplement, [])
    for condition in conditions:
        if condition in blocked:
            return False, f"Contraindicated with {condition.replace('_', ' ')}"
    
    # Age-based restrictions
    age = profile.get("age")
    if age and age < 18:
        if supplement in AGE_RESTRICTIONS["minor"]["block"]:
            return False, "Not recommended for minors (age < 18)"
    
    if profile.get("pregnancy"):
        if supplement in AGE_RESTRICTIONS["pregnancy"]["block"]:
            return False, "Not recommended during pregnancy"
    
    # Medication interactions (hard blocks only)
    meds = [normalize_medication(m) for m in profile.get("meds", [])]
    for med_class in meds:
        if med_class in MEDICATION_INTERACTIONS:
            interaction = MEDICATION_INTERACTIONS[med_class]
            if supplement in interaction.get("avoid", []):
                return False, f"Avoid with {med_class} medications"
    
    return True, ""


def get_dose_caps(profile: dict, supplement: str) -> Dict[str, any]:
    """
    Get any dose caps that should be applied based on profile.
    
    Args:
        profile: User profile dict
        supplement: Supplement name
        
    Returns:
        Dict with cap info (e.g., {"max_mg_day": 200, "reason": "pregnancy limit"})
    """
    caps = {}
    
    # Pregnancy caps
    if profile.get("pregnancy"):
        if supplement == "caffeine":
            pregnancy_cap = AGE_RESTRICTIONS["pregnancy"]["cap"].get("caffeine", 200)
            caps["max_mg_day"] = pregnancy_cap
            caps["reason"] = "pregnancy limit (ACOG guideline)"
    
    # Condition-based caps
    conditions = [normalize_condition(c) for c in profile.get("conditions", [])]
    for condition in conditions:
        if condition in CONDITION_ADJUSTMENTS:
            adj = CONDITION_ADJUSTMENTS[condition]
            if "cap" in adj and supplement in adj["cap"]:
                caps["max_mg_day"] = adj["cap"][supplement]
                caps["reason"] = f"{condition.replace('_', ' ')} limit"
    
    # Age-based caps
    age = profile.get("age")
    if age and age < 18 and supplement == "caffeine":
        caps["max_mg_day"] = 100
        caps["reason"] = "minor limit (conservative)"
    
    # Older adult adjustments
    if age and age >= 65:
        if supplement == "caffeine" and "older_adult" in AGE_RESTRICTIONS:
            multiplier = AGE_RESTRICTIONS["older_adult"].get("caffeine_multiplier", 1.0)
            caps["multiplier"] = multiplier
            caps["reason"] = "reduced for older adults"
    
    return caps


def get_cautions(profile: dict, supplement: str) -> List[str]:
    """
    Get caution notes for a supplement based on profile.
    
    Args:
        profile: User profile dict
        supplement: Supplement name
        
    Returns:
        List of caution strings
    """
    cautions = []
    
    # Age-based cautions
    age = profile.get("age")
    if age and age < 18:
        if supplement in AGE_RESTRICTIONS["minor"]["caution"]:
            cautions.append(AGE_RESTRICTIONS["minor"]["note"])
    
    if profile.get("pregnancy"):
        if supplement in AGE_RESTRICTIONS["pregnancy"]["caution"]:
            cautions.append(AGE_RESTRICTIONS["pregnancy"]["note"])
    
    # Condition-based cautions
    conditions = [normalize_condition(c) for c in profile.get("conditions", [])]
    for condition in conditions:
        if condition in CONDITION_ADJUSTMENTS:
            adj = CONDITION_ADJUSTMENTS[condition]
            if supplement in adj.get("caution", []):
                cautions.append(adj["note"])
    
    # Medication-based cautions
    meds = [normalize_medication(m) for m in profile.get("meds", [])]
    for med_class in meds:
        if med_class in MEDICATION_INTERACTIONS:
            interaction = MEDICATION_INTERACTIONS[med_class]
            if supplement in interaction.get("caution", []):
                cautions.append(f"{med_class.upper()}: {interaction['note']}")
    
    return cautions


def get_global_warnings(profile: dict) -> List[str]:
    """
    Get global warnings that apply to the entire stack.
    
    Args:
        profile: User profile dict
        
    Returns:
        List of warning strings
    """
    warnings = []
    
    if profile.get("pregnancy"):
        warnings.append("⚠️ Pregnancy: Conservative supplement approach recommended. Consult OB/GYN before use.")
    
    age = profile.get("age")
    if age and age < 18:
        warnings.append("⚠️ Minor (age < 18): Food-first approach strongly recommended. Avoid stimulants.")
    
    if age and age >= 65:
        warnings.append("ℹ️ Older adult: May benefit from protein and HMB for muscle preservation.")
    
    # Condition warnings
    conditions = [normalize_condition(c) for c in profile.get("conditions", [])]
    if "hypertension" in conditions or "high_blood_pressure" in conditions:
        warnings.append("⚠️ Hypertension: Monitor blood pressure. Caffeine may cause transient increases.")
    
    if "diabetes" in conditions:
        warnings.append("⚠️ Diabetes: Monitor blood glucose response to supplements.")
    
    if "anxiety" in conditions or "panic_disorder" in conditions:
        warnings.append("⚠️ Anxiety: Stimulants avoided due to potential to worsen symptoms.")
    
    # Medication warnings
    meds = [normalize_medication(m) for m in profile.get("meds", [])]
    if "maoi" in meds:
        warnings.append("🚫 MAOI: All stimulants avoided due to serious interaction risk.")
    
    if "anticoagulants" in meds:
        warnings.append("⚠️ Anticoagulants: Monitor for bleeding. Some supplements may affect clotting.")
    
    return warnings

