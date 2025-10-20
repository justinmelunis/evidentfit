from __future__ import annotations

from typing import Dict, List, Tuple


def extract_signals_from_messages(messages: List[Dict[str, str]]) -> Dict[str, List[str]]:
    """
    Deterministic extractor for conditions and medication classes from chat messages.
    Returns a dict with keys: "conditions", "meds".
    """
    text = "\n".join([m.get("content", "") for m in messages if isinstance(m, dict)])
    text_lower = text.lower()

    conditions = []
    condition_keywords = {
        "anxiety": ["anxiety", "anxious", "panic", "panic attacks"],
        "insomnia": ["insomnia", "sleep problems", "can't sleep", "trouble sleeping"],
        "hypertension": ["hypertension", "high blood pressure"],
        "diabetes": ["diabetes", "diabetic", "blood sugar"],
        "kidney_disease": ["kidney disease", "ckd", "renal"],
    }
    for cond, kws in condition_keywords.items():
        if any(kw in text_lower for kw in kws):
            conditions.append(cond)

    meds = []
    med_keywords = {
        "ssri": ["ssri", "prozac", "zoloft", "lexapro", "sertraline", "fluoxetine", "escitalopram", "citalopram"],
        "maoi": ["maoi", "phenelzine", "tranylcypromine", "isocarboxazid"],
        "anticoagulants": ["warfarin", "coumadin", "apixaban", "eliquis", "xarelto", "rivaroxaban", "heparin"],
        "bp_meds": ["lisinopril", "amlodipine", "losartan", "metoprolol", "atenolol", "carvedilol"],
    }
    for med_class, kws in med_keywords.items():
        if any(kw in text_lower for kw in kws):
            meds.append(med_class)

    return {"conditions": conditions, "meds": meds}


