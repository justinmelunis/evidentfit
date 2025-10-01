"""
Enhanced conversational stack builder for Agent D.

Builds on existing stack_rules.py helpers with:
- Conversation-aware candidate selection
- Evidence-based filtering from retrieved papers
- Guardrail integration
- Interaction checking
"""

import os
from typing import List, Dict, Optional
from datetime import datetime

# Import shared types and guardrails
try:
    from evidentfit_shared.types import (
        UserProfile, StackItem, StackPlan, Dose, Citation, EvidenceDoc
    )
    from evidentfit_shared.guardrails import (
        check_contraindications, get_dose_caps, get_cautions, get_global_warnings
    )
except ImportError:
    raise SystemExit("shared/ package not installed; ensure evidentfit_shared is available")

# Import existing helpers
from stack_rules import (
    creatine_plan_by_form, protein_gap_plan,
    get_evidence_grade, get_supplement_timing, get_supplement_why
)


INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")


# ============================================================================
# Candidate Selection
# ============================================================================

def select_candidates(
    profile: UserProfile,
    retrieved_docs: List[dict],
    conversation_context: Optional[str] = None
) -> List[str]:
    """
    Select supplement candidates based on profile, evidence, and conversation.
    
    Args:
        profile: User profile
        retrieved_docs: Papers from Azure AI Search
        conversation_context: Optional user message for context
        
    Returns:
        List of supplement names to consider
    """
    goal = profile.goal
    
    # Base stacks by goal (evidence-backed core supplements)
    base_stacks = {
        "strength": ["creatine", "caffeine", "protein"],
        "hypertrophy": ["creatine", "protein", "beta-alanine"],
        "endurance": ["caffeine", "beta-alanine", "nitrate", "protein"],
        "weight_loss": ["caffeine", "protein"],
        "performance": ["creatine", "caffeine", "beta-alanine", "citrulline", "protein"],
        "general": ["protein"]
    }
    
    base = base_stacks.get(goal, ["protein"])
    
    # Analyze retrieved papers for additional evidence-backed candidates
    supplement_evidence = _analyze_paper_evidence(retrieved_docs, goal)
    
    # Add supplements with strong evidence (Grade A/B) from retrieved papers
    for supp, evidence in supplement_evidence.items():
        if supp not in base and evidence["grade"] in ["A", "B"] and evidence["count"] >= 2:
            base.append(supp)
    
    # Remove low-evidence supplements by default (unless explicitly mentioned)
    low_evidence = ["tribulus", "d-aspartic-acid", "deer-antler", "ecdysteroids"]
    base = [s for s in base if s not in low_evidence]
    
    return base


def _analyze_paper_evidence(docs: List[dict], goal: str) -> Dict[str, dict]:
    """
    Analyze retrieved papers to find evidence-backed supplements.
    
    Returns:
        Dict mapping supplement to evidence summary
    """
    evidence = {}
    
    for doc in docs:
        # Extract supplements from paper
        supps = (doc.get("supplements") or "").split(",")
        doc_goal = doc.get("primary_goal", "")
        study_type = doc.get("study_type", "")
        reliability = doc.get("reliability_score", 0)
        
        # Only count if goal matches and quality is decent
        if doc_goal == goal and reliability >= 5:
            for supp in supps:
                supp = supp.strip().lower()
                if not supp:
                    continue
                    
                if supp not in evidence:
                    evidence[supp] = {
                        "count": 0,
                        "grade": _infer_grade_from_study_type(study_type),
                        "avg_reliability": 0
                    }
                
                evidence[supp]["count"] += 1
                evidence[supp]["avg_reliability"] = (
                    (evidence[supp]["avg_reliability"] * (evidence[supp]["count"] - 1) + reliability) 
                    / evidence[supp]["count"]
                )
    
    return evidence


def _infer_grade_from_study_type(study_type: str) -> str:
    """Infer evidence grade from study type."""
    st = study_type.lower() if study_type else ""
    if "meta-analysis" in st or "systematic review" in st:
        return "A"
    if "rct" in st or "randomized" in st:
        return "A"
    if "crossover" in st:
        return "B"
    return "C"


# ============================================================================
# Stack Item Builders
# ============================================================================

def build_creatine_item(
    profile: UserProfile, 
    docs: List[dict],
    include_form_info: bool = True
) -> Optional[StackItem]:
    """
    Build creatine stack item with guardrails and form recommendations.
    
    Args:
        profile: User profile
        docs: Retrieved papers
        include_form_info: Whether to include notes about alternative forms
    """
    # Check contraindications
    safe, reason = check_contraindications(profile.dict(), "creatine")
    if not safe:
        return StackItem(
            supplement="creatine",
            evidence_grade="A",
            included=False,
            reason=reason,
            why="",
            doses=[],
            tier="core"
        )
    
    # Determine form (default to monohydrate)
    form = profile.creatine_form or "monohydrate"
    
    # Build plan using existing helper
    plan = creatine_plan_by_form(
        weight_kg=profile.weight_kg,
        form=form,
        include_loading=False  # Default to maintenance only
    )
    
    # Convert to StackItem
    doses = [
        Dose(
            value=d["value"],
            unit=d["unit"],
            timing=plan["timing"],
            days=d.get("days"),
            split=d.get("split"),
            notes=list(plan.get("notes", []))  # Copy list to avoid mutation
        )
        for d in plan["doses"]
    ]
    
    # Add form comparison info if requested
    if include_form_info and form == "monohydrate":
        doses[0].notes.append("Alternative forms: Anhydrous (higher % per gram), HCl (better solubility)")
    elif include_form_info and form == "anhydrous":
        doses[0].notes.append("Anhydrous = 100% creatine (vs 87.9% in monohydrate)")
    elif include_form_info and form == "hcl":
        doses[0].notes.append("HCl may dissolve better, but monohydrate has more research")
    
    # Add form-specific notes
    form_notes = _get_creatine_form_notes(form, profile.weight_kg)
    doses[0].notes.extend(form_notes)
    
    # Get citations from docs
    citations = _get_citations_for_supplement("creatine", docs, max_citations=3)
    
    # Get cautions
    cautions = get_cautions(profile.dict(), "creatine")
    if cautions:
        doses[0].notes.extend(cautions)
    
    return StackItem(
        supplement="creatine",
        evidence_grade="A",
        included=True,
        why=plan["why"],
        doses=doses,
        citations=citations,
        tier="core"
    )


def _get_creatine_form_notes(form: str, weight_kg: float) -> List[str]:
    """
    Get form-specific notes for creatine recommendations.
    
    Returns tips and considerations for each creatine form.
    """
    notes = []
    
    if form == "monohydrate":
        notes.append("✓ Most researched form with proven efficacy")
        notes.append("✓ Cost-effective and widely available")
        if weight_kg < 70:
            notes.append("Consider loading: 0.3g/kg/day for 5-7 days, then maintenance")
    
    elif form == "anhydrous":
        notes.append("✓ 100% creatine (no water molecule)")
        notes.append("✓ Need slightly less by weight than monohydrate")
        notes.append("Note: Less research than monohydrate, but theoretically equivalent")
    
    elif form == "hcl":
        notes.append("✓ May have better solubility and absorption")
        notes.append("✓ Some users report less GI discomfort")
        notes.append("⚠ Less research support; adjust dose for creatine base content (78.2%)")
        notes.append("Alternative: Try monohydrate with more water if tolerability is concern")
    
    # Not recommended forms
    if form == "ethyl-ester":
        notes.append("⚠ NOT RECOMMENDED: Inferior to monohydrate in studies")
        notes.append("Consider switching to monohydrate for better results")
    
    return notes


def get_creatine_form_comparison() -> Dict[str, dict]:
    """
    Get comprehensive comparison of creatine forms.
    
    Useful for answering user questions about which form to choose.
    """
    return {
        "monohydrate": {
            "creatine_content_percent": 87.9,
            "evidence_grade": "A",
            "research_support": "Extensive (gold standard)",
            "cost": "Low",
            "solubility": "Moderate",
            "pros": [
                "Most researched form",
                "Proven efficacy in hundreds of studies",
                "Cost-effective",
                "Widely available"
            ],
            "cons": [
                "Some users report GI discomfort at high doses",
                "May require loading phase for faster results"
            ],
            "recommended_for": "Everyone (default choice)"
        },
        "anhydrous": {
            "creatine_content_percent": 100.0,
            "evidence_grade": "A",
            "research_support": "Good (equivalent to monohydrate)",
            "cost": "Low-Moderate",
            "solubility": "Moderate",
            "pros": [
                "100% creatine by weight",
                "Need slightly less per dose",
                "No water molecule"
            ],
            "cons": [
                "Slightly more expensive",
                "Less research than monohydrate (but theoretically same)"
            ],
            "recommended_for": "Those who want maximum creatine per gram"
        },
        "hcl": {
            "creatine_content_percent": 78.2,
            "evidence_grade": "B",
            "research_support": "Limited but promising",
            "cost": "Moderate-High",
            "solubility": "High",
            "pros": [
                "Better solubility",
                "May reduce GI discomfort",
                "Smaller doses by volume"
            ],
            "cons": [
                "More expensive",
                "Less research support",
                "Need to adjust for lower creatine content"
            ],
            "recommended_for": "Those with GI issues on monohydrate"
        },
        "ethyl-ester": {
            "creatine_content_percent": None,
            "evidence_grade": "D",
            "research_support": "Poor (inferior to monohydrate)",
            "cost": "Moderate",
            "solubility": "High",
            "pros": [
                "None over monohydrate"
            ],
            "cons": [
                "Degrades to creatinine in stomach",
                "Inferior results vs monohydrate in studies",
                "Not recommended"
            ],
            "recommended_for": "Not recommended; use monohydrate instead"
        },
        "buffered": {
            "creatine_content_percent": None,
            "evidence_grade": "C",
            "research_support": "Limited (no clear advantage)",
            "cost": "Moderate-High",
            "solubility": "Moderate",
            "pros": [
                "Marketed as pH-buffered for stability"
            ],
            "cons": [
                "No clear advantage over monohydrate in studies",
                "More expensive",
                "Limited research"
            ],
            "recommended_for": "Monohydrate is preferred unless specific tolerance issue"
        }
    }


def build_caffeine_item(profile: UserProfile, docs: List[dict]) -> Optional[StackItem]:
    """Build caffeine stack item with sensitivity and caps."""
    # Check contraindications
    safe, reason = check_contraindications(profile.dict(), "caffeine")
    if not safe:
        return StackItem(
            supplement="caffeine",
            evidence_grade="A",
            included=False,
            reason=reason,
            why="",
            doses=[],
            tier="core"
        )
    
    # Determine dose range based on sensitivity
    if profile.caffeine_sensitive:
        mg_per_kg_range = "3-4"
        max_dose = min(4 * profile.weight_kg, 200)
    else:
        mg_per_kg_range = "4-6"
        max_dose = min(6 * profile.weight_kg, 400)
    
    # Apply caps from guardrails
    caps = get_dose_caps(profile.dict(), "caffeine")
    if "max_mg_day" in caps:
        max_dose = min(max_dose, caps["max_mg_day"])
    
    dose = Dose(
        value=mg_per_kg_range,
        unit="mg/kg",
        timing="30-60 min pre-workout",
        notes=["Avoid within 6 hours of bedtime"]
    )
    
    if caps:
        dose.cap_reason = caps.get("reason", "safety cap")
        dose.notes.append(f"Capped at {max_dose} mg/day ({caps.get('reason', 'safety')})")
    
    # Get cautions
    cautions = get_cautions(profile.dict(), "caffeine")
    if cautions:
        dose.notes.extend(cautions)
    
    citations = _get_citations_for_supplement("caffeine", docs, max_citations=3)
    
    return StackItem(
        supplement="caffeine",
        evidence_grade="A",
        included=True,
        why="Improves focus, energy, and performance",
        doses=[dose],
        citations=citations,
        tier="core"
    )


def build_protein_item(profile: UserProfile, docs: List[dict]) -> Optional[StackItem]:
    """Build protein stack item with gap analysis."""
    # Use existing helper
    plan = protein_gap_plan(
        goal=profile.goal,
        weight_kg=profile.weight_kg,
        diet_g_per_day=profile.diet_protein_g_per_day,
        diet_g_per_kg=profile.diet_protein_g_per_kg,
        include_threshold_g=20
    )
    
    # If no gap or gap too small, don't include
    if not plan:
        return None
    
    # Convert to StackItem
    doses = [
        Dose(
            value=d["value"],
            unit=d["unit"],
            timing=plan["timing"],
            days=d.get("days"),
            notes=plan.get("notes", [])
        )
        for d in plan["doses"]
    ]
    
    citations = _get_citations_for_supplement("protein", docs, max_citations=3)
    
    return StackItem(
        supplement="protein",
        evidence_grade="A",
        included=True,
        why=plan["why"],
        doses=doses,
        citations=citations,
        tier="core"
    )


def build_beta_alanine_item(profile: UserProfile, docs: List[dict]) -> Optional[StackItem]:
    """Build beta-alanine stack item."""
    safe, reason = check_contraindications(profile.dict(), "beta-alanine")
    if not safe:
        return StackItem(
            supplement="beta-alanine",
            evidence_grade="B",
            included=False,
            reason=reason,
            why="",
            doses=[],
            tier="optional"
        )
    
    dose = Dose(
        value="3.2-6.4",
        unit="g/day",
        timing="Split into 2-4 doses",
        days="ongoing",
        notes=["Tingling (paresthesia) is normal and harmless", "SR (slow-release) forms reduce tingling"]
    )
    
    citations = _get_citations_for_supplement("beta-alanine", docs, max_citations=3)
    
    return StackItem(
        supplement="beta-alanine",
        evidence_grade="B",
        included=True,
        why="Buffers muscle acidity, delays fatigue in high-intensity exercise",
        doses=[dose],
        citations=citations,
        tier="optional"
    )


def build_citrulline_item(profile: UserProfile, docs: List[dict]) -> Optional[StackItem]:
    """Build citrulline stack item."""
    safe, reason = check_contraindications(profile.dict(), "citrulline")
    if not safe:
        return StackItem(
            supplement="citrulline",
            evidence_grade="B",
            included=False,
            reason=reason,
            why="",
            doses=[],
            tier="optional"
        )
    
    dose = Dose(
        value="6-8",
        unit="g",
        timing="30-60 min pre-workout",
        notes=["L-citrulline preferred over citrulline malate for pure dosing"]
    )
    
    citations = _get_citations_for_supplement("citrulline", docs, max_citations=3)
    
    return StackItem(
        supplement="citrulline",
        evidence_grade="B",
        included=True,
        why="May improve blood flow and reduce fatigue",
        doses=[dose],
        citations=citations,
        tier="optional"
    )


def build_nitrate_item(profile: UserProfile, docs: List[dict]) -> Optional[StackItem]:
    """Build nitrate stack item (beetroot juice)."""
    safe, reason = check_contraindications(profile.dict(), "nitrate")
    if not safe:
        return StackItem(
            supplement="nitrate",
            evidence_grade="B",
            included=False,
            reason=reason,
            why="",
            doses=[],
            tier="optional"
        )
    
    dose = Dose(
        value="250-500",
        unit="ml beetroot juice",
        timing="2-3 hours pre-workout",
        notes=["May cause red urine/stool (harmless)", "Look for high-nitrate content"]
    )
    
    citations = _get_citations_for_supplement("nitrate", docs, max_citations=3)
    
    return StackItem(
        supplement="nitrate",
        evidence_grade="B",
        included=True,
        why="May improve blood flow and endurance performance",
        doses=[dose],
        citations=citations,
        tier="optional"
    )


# ============================================================================
# Citation Extraction
# ============================================================================

def _get_citations_for_supplement(
    supplement: str,
    docs: List[dict],
    max_citations: int = 3
) -> List[Citation]:
    """Extract citations for a supplement from retrieved papers."""
    citations = []
    
    for doc in docs:
        if len(citations) >= max_citations:
            break
            
        # Check if this paper is about the supplement
        supps = (doc.get("supplements") or "").lower()
        if supplement.lower() not in supps:
            continue
        
        # Extract citation info
        pmid = doc.get("pmid")
        if not pmid:
            continue
            
        citation = Citation(
            title=doc.get("title", ""),
            url=doc.get("url_pub", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"),
            pmid=pmid,
            study_type=doc.get("study_type"),
            journal=doc.get("journal"),
            year=doc.get("year")
        )
        citations.append(citation)
    
    return citations


# ============================================================================
# Main Stack Builder
# ============================================================================

def build_conversational_stack(
    profile: UserProfile,
    retrieved_docs: List[dict],
    conversation_context: Optional[str] = None
) -> StackPlan:
    """
    Build a personalized supplement stack with guardrails and evidence.
    
    Args:
        profile: User profile with goals, weight, sensitivities, conditions
        retrieved_docs: Papers from Azure AI Search relevant to profile/query
        conversation_context: Optional user message for context-aware adjustments
        
    Returns:
        Complete StackPlan with items, interactions, warnings
    """
    # 1. Select candidates based on profile + evidence
    candidates = select_candidates(profile, retrieved_docs, conversation_context)
    
    # 2. Build stack items with deterministic dosing
    items = []
    
    for supplement in candidates:
        item = None
        
        if supplement == "creatine":
            item = build_creatine_item(profile, retrieved_docs)
        elif supplement == "caffeine":
            item = build_caffeine_item(profile, retrieved_docs)
        elif supplement == "protein":
            item = build_protein_item(profile, retrieved_docs)
        elif supplement == "beta-alanine":
            item = build_beta_alanine_item(profile, retrieved_docs)
        elif supplement == "citrulline":
            item = build_citrulline_item(profile, retrieved_docs)
        elif supplement == "nitrate":
            item = build_nitrate_item(profile, retrieved_docs)
        
        if item:
            items.append(item)
    
    # 3. Get global warnings
    warnings = get_global_warnings(profile.dict())
    
    # 4. Extract exclusions
    exclusions = [
        f"{item.supplement}: {item.reason}"
        for item in items
        if not item.included
    ]
    
    # 5. Filter to only included items
    included_items = [item for item in items if item.included]
    
    # 6. Build stack plan
    return StackPlan(
        profile=profile,
        items=included_items,
        interactions=[],  # Will be populated by interaction checker
        warnings=warnings,
        exclusions=exclusions,
        index_version=INDEX_VERSION,
        updated_at=datetime.utcnow().isoformat() + "Z"
    )

