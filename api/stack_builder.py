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
# Banking System Configuration
# ============================================================================

# Banking buckets for caching base recommendations
BANKING_BUCKETS = {
    "goal": ["strength", "hypertrophy", "endurance", "weight_loss", "performance", "general"],  # 6
    "weight_bin": ["xs", "small", "medium", "large", "xl"],  # 5 (<60, 60-70, 70-85, 85-100, 100+)
    "sex": ["male", "female", "other"],  # 3  
    "age_bin": ["minor", "young", "adult", "mature"]  # 4 (13-17, 18-29, 30-49, 50+)
}
# Total combinations: 6 × 5 × 3 × 4 = 360 profiles (2.2 MB storage)

def get_weight_bin(weight_kg: float) -> str:
    """Map weight to bins that affect dosing recommendations"""
    if weight_kg < 60:
        return "xs"      # <60kg - lower doses for most supplements
    elif weight_kg < 70:
        return "small"   # 60-70kg - standard doses, some adjustments
    elif weight_kg < 85:
        return "medium"  # 70-85kg - standard doses (most research)
    elif weight_kg < 100:
        return "large"   # 85-100kg - higher doses for weight-based supplements
    else:
        return "xl"      # 100kg+ - maximum doses, loading phases

def get_age_bin(age: Optional[int]) -> str:
    """Map age to bins for banking"""
    if not age:
        return "adult"  # Default assumption
    elif age < 18:
        return "minor"
    elif age < 30:
        return "young"
    elif age < 50:
        return "adult"
    else:
        return "mature"

def generate_bank_key(profile: UserProfile) -> str:
    """Generate banking key from core profile attributes"""
    goal = profile.goal
    weight_bin = get_weight_bin(profile.weight_kg)
    sex = profile.sex if hasattr(profile, 'sex') and profile.sex else "other"
    age_bin = get_age_bin(profile.age)
    
    return f"{goal}:{weight_bin}:{sex}:{age_bin}"

# Common supplements to evaluate for every user
COMMON_SUPPLEMENTS = [
    "creatine", "protein", "caffeine", "beta-alanine", "citrulline", 
    "nitrate", "hmb", "bcaa", "taurine", "carnitine", "glutamine",
    "ashwagandha", "rhodiola", "omega-3", "vitamin-d", "magnesium",
    "collagen", "curcumin", "b12", "iron", "folate", "leucine", "betaine",
    "zma", "tribulus", "d-aspartic-acid", "tongkat-ali"
]

# Special handling for high-risk populations
PREGNANCY_SAFE_SUPPLEMENTS = ["protein", "prenatal-vitamin", "omega-3", "vitamin-d", "folate"]
MINOR_BLOCKED_SUPPLEMENTS = ["caffeine", "stimulants", "experimental", "tribulus", "d-aspartic-acid"]

# Base evidence grades by goal (before profile adjustments)
BASE_GRADES = {
    "strength": {
        "creatine": "A", "protein": "A", "caffeine": "A", 
        "beta-alanine": "B", "hmb": "B", "leucine": "B",
        "citrulline": "C", "nitrate": "C", "carnitine": "C",
        "omega-3": "B", "vitamin-d": "B", "magnesium": "C",
        "bcaa": "D", "glutamine": "D", "zma": "C", "taurine": "C"
    },
    "hypertrophy": {
        "creatine": "A", "protein": "A", "leucine": "A",
        "hmb": "B", "beta-alanine": "B", "caffeine": "B",
        "citrulline": "B", "omega-3": "B", "vitamin-d": "B",
        "carnitine": "C", "nitrate": "C", "magnesium": "C",
        "bcaa": "D", "glutamine": "D", "zma": "C", "taurine": "C"
    },
    "endurance": {
        "caffeine": "A", "beta-alanine": "A", "nitrate": "A",
        "citrulline": "B", "carnitine": "B", "protein": "B",
        "creatine": "C", "omega-3": "B", "vitamin-d": "B",
        "magnesium": "B", "taurine": "C", "bcaa": "C",
        "hmb": "D", "glutamine": "D", "zma": "C", "leucine": "C"
    },
    "weight_loss": {
        "protein": "A", "caffeine": "A", "carnitine": "B",
        "omega-3": "B", "vitamin-d": "B", "magnesium": "C",
        "creatine": "C", "beta-alanine": "C", "citrulline": "C",
        "hmb": "C", "leucine": "B", "taurine": "C",
        "bcaa": "D", "glutamine": "D", "zma": "C", "nitrate": "D"
    },
    "performance": {
        "caffeine": "A", "creatine": "A", "beta-alanine": "A",
        "nitrate": "B", "citrulline": "B", "protein": "B",
        "carnitine": "B", "omega-3": "B", "vitamin-d": "B",
        "hmb": "C", "leucine": "B", "magnesium": "C",
        "bcaa": "C", "glutamine": "D", "zma": "C", "taurine": "C"
    },
    "general": {
        "protein": "A", "omega-3": "A", "vitamin-d": "A",
        "magnesium": "B", "creatine": "B", "caffeine": "C",
        "beta-alanine": "C", "citrulline": "C", "carnitine": "C",
        "hmb": "C", "leucine": "C", "taurine": "C",
        "bcaa": "D", "glutamine": "D", "zma": "C", "nitrate": "D"
    }
}

# ============================================================================
# Special Population Handling
# ============================================================================

def get_pregnancy_stack() -> StackPlan:
    """Return safe, limited supplement stack for pregnancy"""
    items = []
    
    # Protein - safe and often needed
    protein_item = StackItem(
        supplement="protein",
        evidence_grade="A",
        included=True,
        why="Safe protein powder to meet increased protein needs during pregnancy (1.2g/kg body weight)",
        doses=[Dose(
            value=25, unit="g", timing="with meals",
            notes=["Choose unflavored or naturally flavored options", "Avoid artificial sweeteners"]
        )],
        tier="core"
    )
    items.append(protein_item)
    
    # Prenatal vitamin recommendation
    prenatal_item = StackItem(
        supplement="prenatal-vitamin",
        evidence_grade="A", 
        included=True,
        why="Comprehensive nutrition support during pregnancy with folate, iron, and other essentials",
        doses=[Dose(
            value=1, unit="tablet", timing="daily with food",
            notes=["Consult healthcare provider for specific prenatal vitamin recommendations"]
        )],
        tier="core"
    )
    items.append(prenatal_item)
    
    return StackPlan(
        recommended=items,
        optional=[],
        not_recommended=[],
        exclusions=["Most supplements not recommended during pregnancy - consult healthcare provider"],
        safety=["⚠️ PREGNANCY: Consult your healthcare provider before starting any supplements. This is educational information only."],
        profile_notes="Focus on whole foods and prenatal vitamins. Avoid experimental supplements."
    )

def apply_minor_adjustments(items: List[StackItem]) -> List[StackItem]:
    """Apply conservative adjustments for users under 18"""
    adjusted = []
    
    for item in items:
        if item.supplement in MINOR_BLOCKED_SUPPLEMENTS:
            # Block risky supplements
            item.included = False
            item.reason = "Not recommended for minors (age < 18) - focus on food-first approach"
            item.tier = "not_recommended"
        elif item.supplement == "creatine":
            # Conservative creatine dosing
            if item.doses:
                item.doses[0].notes.append("Conservative dosing for developing athletes")
                item.doses[0].notes.append("Ensure adequate hydration and proper training supervision")
        elif item.supplement == "protein":
            # Conservative protein limits
            if item.doses:
                item.doses[0].notes.append("Focus on whole food protein sources first")
                item.doses[0].notes.append("Maximum 2.0g/kg body weight total protein")
        
        adjusted.append(item)
    
    return adjusted

def extract_conditions_from_text(text: str) -> List[str]:
    """Extract medical conditions mentioned in user text"""
    text_lower = text.lower()
    conditions = []
    
    condition_keywords = {
        "anxiety": ["anxiety", "anxious", "panic", "worry"],
        "depression": ["depression", "depressed", "sad", "mood"],
        "hypertension": ["high blood pressure", "hypertension", "bp"],
        "diabetes": ["diabetes", "diabetic", "blood sugar", "insulin"],
        "insomnia": ["insomnia", "sleep problems", "can't sleep", "trouble sleeping"],
        "heart_disease": ["heart disease", "cardiac", "heart problems"],
        "kidney_disease": ["kidney", "renal", "kidney disease"]
    }
    
    for condition, keywords in condition_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            conditions.append(condition)
    
    return conditions

def extract_medications_from_text(text: str) -> List[str]:
    """Extract medication classes mentioned in user text"""
    text_lower = text.lower()
    medications = []
    
    med_keywords = {
        "ssri": ["ssri", "antidepressant", "prozac", "zoloft", "lexapro", "citalopram", "sertraline"],
        "maoi": ["maoi", "phenelzine", "tranylcypromine"],
        "anticoagulant": ["blood thinner", "warfarin", "coumadin", "anticoagulant"],
        "bp_med": ["blood pressure medication", "ace inhibitor", "beta blocker", "lisinopril", "metoprolol"]
    }
    
    for med_class, keywords in med_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            medications.append(med_class)
    
    return medications

def apply_text_based_adjustments(items: List[StackItem], context: str, profile: UserProfile) -> List[StackItem]:
    """Apply real-time adjustments based on user text input"""
    if not context:
        return items
    
    conditions = extract_conditions_from_text(context)
    medications = extract_medications_from_text(context)
    
    adjusted = []
    for item in items:
        # Check contraindications from guardrails
        safe, reason = check_contraindications(profile.dict(), item.supplement)
        
        if not safe:
            item.included = False
            item.reason = reason
            item.tier = "not_recommended"
        else:
            # Apply condition-specific adjustments
            if "anxiety" in conditions and item.supplement == "caffeine":
                item.included = False
                item.reason = "Caffeine can worsen anxiety symptoms"
                item.tier = "not_recommended"
            elif "insomnia" in conditions and item.supplement == "caffeine":
                item.included = False  
                item.reason = "Caffeine can interfere with sleep"
                item.tier = "not_recommended"
            elif "hypertension" in conditions and item.supplement == "caffeine":
                if item.doses:
                    item.doses[0].value = min(item.doses[0].value, 200)  # Cap at 200mg
                    item.doses[0].notes.append("Reduced dose due to blood pressure concerns")
        
        adjusted.append(item)
    
    return adjusted


# ============================================================================
# Evidence Grade Calculation
# ============================================================================

def calculate_evidence_grade_from_papers(supplement: str, docs: List[dict], goal: str) -> str:
    """
    Dynamically calculate evidence grade based on retrieved papers.
    
    Args:
        supplement: Supplement name
        docs: Retrieved research papers
        goal: User's goal
        
    Returns:
        Evidence grade: A, B, C, or D
    """
    relevant_papers = []
    
    for doc in docs:
        doc_supplements = (doc.get("supplements") or "").lower().split(",")
        if supplement.lower() in [s.strip() for s in doc_supplements]:
            relevant_papers.append(doc)
    
    if not relevant_papers:
        return "D"  # No evidence in our database
    
    # Score based on study types and relevance to goal
    score = 0
    meta_count = 0
    rct_count = 0
    goal_relevant_count = 0
    
    for paper in relevant_papers:
        study_type = (paper.get("study_type") or "").lower()
        primary_goal = (paper.get("primary_goal") or "").lower()
        reliability = paper.get("reliability_score", 0)
        
        # Study design scoring
        if "meta" in study_type:
            score += 3
            meta_count += 1
        elif "rct" in study_type or "randomized" in study_type:
            score += 2
            rct_count += 1
        elif "crossover" in study_type:
            score += 1.5
        else:
            score += 0.5
        
        # Goal relevance
        if goal.lower() in primary_goal or primary_goal in goal.lower():
            score += 1
            goal_relevant_count += 1
        
        # High reliability bonus
        if reliability >= 8:
            score += 0.5
    
    # Determine grade based on score and paper count
    paper_count = len(relevant_papers)
    
    if meta_count >= 1 and score >= 5 and paper_count >= 3:
        return "A"  # Strong evidence: meta-analyses + multiple studies
    elif (rct_count >= 2 or meta_count >= 1) and score >= 3:
        return "B"  # Moderate evidence: RCTs or meta-analysis
    elif paper_count >= 2 and score >= 1.5:
        return "C"  # Limited evidence: some studies
    else:
        return "D"  # Insufficient evidence


# ============================================================================
# Candidate Selection
# ============================================================================

def _get_llm_supplement_suggestions(profile: UserProfile, context: Optional[str] = None) -> List[str]:
    """
    Use LLM to suggest supplement candidates based on user profile and context.
    
    Returns:
        List of supplement names suggested by LLM
    """
    try:
        from clients.foundry_chat import chat as foundry_chat
    except ImportError:
        print("Warning: foundry_chat not available for LLM suggestions")
        return []
    
    # Build prompt for LLM
    profile_summary = f"""
User Profile:
- Goal: {profile.goal}
- Weight: {profile.weight_kg} kg
- Age: {profile.age or 'Not specified'}
- Sex: {getattr(profile, 'sex', 'Not specified')}
- Caffeine sensitive: {'Yes' if profile.caffeine_sensitive else 'No'}
- Pregnant/breastfeeding: {'Yes' if profile.pregnancy else 'No'}
- Diet: {getattr(profile, 'diet', 'any')}
- Training frequency: {getattr(profile, 'training_freq', 'medium')}
- Medical conditions: {', '.join(profile.conditions) if profile.conditions else 'None'}
- Medications: {', '.join(profile.meds) if profile.meds else 'None'}
"""
    
    if context:
        profile_summary += f"\nUser's additional context: {context}"
    
    prompt = f"""Based on this user's profile, suggest specific supplements that would be most beneficial.

{profile_summary}

Instructions:
1. Consider their age, sex, goal, and any conditions/medications
2. Suggest supplements that have research support for their specific demographic
3. Be specific - if they're over 50, suggest supplements proven for older adults
4. If they mention specific concerns (stress, sleep, joints), address those
5. Only suggest supplements from this list: creatine, caffeine, protein, beta-alanine, citrulline, nitrate, hmb, bcaa, taurine, carnitine, glutamine, zma, ashwagandha, rhodiola, fish-oil, omega-3, vitamin-d, magnesium, glycine, collagen, glucosamine, curcumin, b12, iron, folate, leucine, betaine

Return ONLY a comma-separated list of supplement names, nothing else.
Example: creatine, protein, hmb, vitamin-d"""
    
    try:
        response = foundry_chat(
            messages=[{"role": "user", "content": prompt}],
            model=os.getenv("FOUNDATION_CHAT_MODEL", "gpt-4o-mini"),
            max_tokens=150,
            temperature=0.3  # Lower temperature for more consistent suggestions
        )
        
        # Parse response
        suggestions_text = response.strip().lower()
        suggestions = [s.strip() for s in suggestions_text.split(',')]
        
        # Normalize names
        normalized = []
        for sugg in suggestions:
            # Remove any extra text, just get the supplement name
            sugg_clean = sugg.split('(')[0].strip()
            if sugg_clean and len(sugg_clean) < 30:  # Sanity check
                normalized.append(sugg_clean)
        
        print(f"LLM suggested supplements: {normalized}")
        return normalized
        
    except Exception as e:
        print(f"LLM suggestion failed: {e}")
        return []


def select_candidates(
    profile: UserProfile,
    retrieved_docs: List[dict],
    conversation_context: Optional[str] = None
) -> List[str]:
    """
    HYBRID approach: Use LLM to suggest personalized candidates, then filter through
    deterministic guardrails and evidence base.
    
    Args:
        profile: User profile
        retrieved_docs: Papers from Azure AI Search
        conversation_context: Optional user message for context
        
    Returns:
        List of supplement names to consider
    """
    # Get LLM-suggested candidates based on user profile and context
    llm_candidates = _get_llm_supplement_suggestions(profile, conversation_context)
    
    # Start with LLM suggestions as the primary list
    base = list(llm_candidates) if llm_candidates else []
    
    goal = profile.goal
    
    # Fallback: If LLM didn't suggest anything, use goal-based foundation
    if not base:
        base_stacks = {
            "strength": ["creatine", "protein", "caffeine"],
            "hypertrophy": ["creatine", "protein"],
            "endurance": ["protein", "beta-alanine", "caffeine"],
            "weight_loss": ["protein", "caffeine"],
            "performance": ["creatine", "protein", "caffeine"],
            "general": ["protein"]
        }
        base = base_stacks.get(goal, ["protein"])
    
    # Always ensure protein is included (fundamental for all goals)
    if "protein" not in base:
        base.append("protein")
    
    # Analyze conversation context for explicitly mentioned supplements
    if conversation_context:
        mentioned_supplements = _extract_mentioned_supplements(conversation_context)
        for supp in mentioned_supplements:
            if supp not in base:
                base.append(supp)
    
    # Analyze retrieved papers for additional evidence-backed candidates
    supplement_evidence = _analyze_paper_evidence(retrieved_docs, goal)
    
    # Add supplements with strong evidence (Grade A/B) from retrieved papers
    for supp, evidence in supplement_evidence.items():
        if supp not in base and evidence["grade"] in ["A", "B"] and evidence["count"] >= 2:
            base.append(supp)
    
    # Keep low-evidence supplements if user explicitly mentioned them
    mentioned_supplements_in_context = []
    if conversation_context:
        mentioned_supplements_in_context = _extract_mentioned_supplements(conversation_context)
    
    # Remove low-evidence supplements UNLESS user asked about them
    low_evidence = ["tribulus", "d-aspartic-acid", "deer-antler", "ecdysteroids"]
    base = [s for s in base if s not in low_evidence or s in mentioned_supplements_in_context]
    
    return base


def _extract_mentioned_supplements(text: str) -> List[str]:
    """
    Extract supplement names mentioned in user's text.
    
    Returns:
        List of supplement names found in text
    """
    text_lower = text.lower()
    
    # Comprehensive supplement keywords to check
    supplement_keywords = {
        "creatine": ["creatine", "monohydrate", "hcl", "anhydrous"],
        "caffeine": ["caffeine", "coffee", "pre-workout"],
        "protein": ["protein", "whey", "casein"],
        "beta-alanine": ["beta-alanine", "beta alanine", "carnosine"],
        "citrulline": ["citrulline", "l-citrulline"],
        "nitrate": ["nitrate", "beetroot", "beet juice"],
        "hmb": ["hmb", "beta-hydroxy"],
        "bcaa": ["bcaa", "branched chain"],
        "taurine": ["taurine"],
        "carnitine": ["carnitine", "l-carnitine"],
        "glutamine": ["glutamine", "l-glutamine"],
        "zma": ["zma", "zinc magnesium"],
        "ashwagandha": ["ashwagandha"],
        "rhodiola": ["rhodiola"],
        "fish-oil": ["fish oil", "omega-3", "omega 3", "omega3"],
        "omega-3": ["omega-3", "omega 3", "fish oil", "dha", "epa"],
        "vitamin-d": ["vitamin d", "vitamin-d", "vit d"],
        "magnesium": ["magnesium", "mag"],
        "glycine": ["glycine"],
        "collagen": ["collagen"],
        "glucosamine": ["glucosamine"],
        "curcumin": ["curcumin", "turmeric"],
        "b12": ["b12", "b-12", "vitamin b12", "cobalamin"],
        "iron": ["iron", "ferrous"],
        "folate": ["folate", "folic acid"],
        "leucine": ["leucine", "l-leucine"],
        "tribulus": ["tribulus"],
        "d-aspartic-acid": ["d-aspartic", "daa", "d aspartic acid"],
        "tongkat-ali": ["tongkat", "tongkat ali"],
        "deer-antler": ["deer antler", "velvet antler"],
        "ecdysteroids": ["ecdysteroid", "turkesterone"],
        "betaine": ["betaine", "tmg"],
        "cla": ["cla", "conjugated linoleic"]
    }
    
    mentioned = []
    for supplement, keywords in supplement_keywords.items():
        for keyword in keywords:
            if keyword in text_lower:
                mentioned.append(supplement)
                break  # Only add once per supplement
    
    return mentioned


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
    # Check contraindications (e.g., certain meds, pregnancy, heart conditions)
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
    
    # Determine dose range based on sensitivity (reduce dose, but don't exclude)
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

def build_conversational_stack_with_banking(
    profile: UserProfile,
    retrieved_docs: List[dict],
    conversation_context: Optional[str] = None
) -> StackPlan:
    """
    Build personalized supplement stack using banking system + real-time adjustments.
    
    Flow:
    1. Check for special populations (pregnancy, minor)
    2. Generate bank key and lookup cached base recommendations
    3. Apply real-time adjustments based on conversation context
    4. Apply safety guardrails
    5. Return final stack plan
    """
    
    # Special population handling
    if profile.pregnancy:
        return get_pregnancy_stack()
    
    # Generate bank key for caching
    bank_key = generate_bank_key(profile)
    
    # For now, generate base stack (later we'll add actual banking/caching)
    base_items = generate_base_stack_items(profile, retrieved_docs)
    
    # Apply age-specific adjustments
    if profile.age and profile.age < 18:
        base_items = apply_minor_adjustments(base_items)
    
    # Apply text-based adjustments (conditions, medications from conversation)
    adjusted_items = apply_text_based_adjustments(base_items, conversation_context or "", profile)
    
    # Apply caffeine sensitivity and pregnancy rules
    final_items = apply_profile_rules(adjusted_items, profile)
    
    # Categorize into tiers
    recommended = [item for item in final_items if item.tier == "core" and item.included]
    optional = [item for item in final_items if item.tier == "optional" and item.included]
    not_recommended = [item for item in final_items if not item.included or item.tier == "not_recommended"]
    
    # Generate safety warnings
    safety_warnings = generate_safety_warnings(profile, final_items)
    
    return StackPlan(
        recommended=recommended,
        optional=optional,
        not_recommended=not_recommended,
        exclusions=[item.reason for item in not_recommended if item.reason],
        safety=safety_warnings,
        profile_notes=f"Bank key: {bank_key}"  # For debugging
    )

def generate_base_stack_items(profile: UserProfile, docs: List[dict]) -> List[StackItem]:
    """Generate base supplement recommendations using goal-based grades + weight-adjusted dosing"""
    items = []
    goal = profile.goal
    base_grades = BASE_GRADES.get(goal, BASE_GRADES["general"])
    
    # Get LLM suggestions for personalization
    llm_suggestions = _get_llm_supplement_suggestions(profile, "")
    
    # Combine base supplements with LLM suggestions
    supplements_to_evaluate = set(base_grades.keys()) | set(llm_suggestions) | set(COMMON_SUPPLEMENTS[:15])
    
    for supplement in supplements_to_evaluate:
        # Get base grade for this goal
        base_grade = base_grades.get(supplement, "D")
        
        # Skip very low evidence unless specifically requested
        if base_grade == "D" and supplement not in llm_suggestions:
            continue
            
        # Build supplement item based on type
        item = None
        if supplement == "creatine":
            item = build_creatine_item(profile, docs, include_form_info=True)
        elif supplement == "caffeine":
            item = build_caffeine_item(profile, docs)
        elif supplement == "protein":
            item = build_protein_item(profile, docs)
        elif supplement == "beta-alanine":
            item = build_beta_alanine_item(profile, docs)
        else:
            # Generic supplement builder
            item = build_generic_supplement_item(supplement, profile, docs, base_grade)
        
        if item:
            # Override grade with base grade (banking system)
            item.evidence_grade = base_grade
            
            # Set tier based on grade and goal relevance
            if base_grade in ["A", "B"] and supplement in base_grades:
                item.tier = "core"
            elif base_grade in ["B", "C"]:
                item.tier = "optional"  
            else:
                item.tier = "not_recommended"
                item.included = False
                item.reason = f"Limited evidence for {goal} goals (Grade {base_grade})"
            
            items.append(item)
    
    return items

def build_generic_supplement_item(
    supplement: str, 
    profile: UserProfile, 
    docs: List[dict], 
    base_grade: str
) -> StackItem:
    """Build a generic supplement item with basic dosing"""
    
    # Get citations
    citations = _get_citations_for_supplement(supplement, docs, max_citations=2)
    
    # Basic dosing by supplement type (weight-adjusted where appropriate)
    weight_kg = profile.weight_kg
    weight_bin = get_weight_bin(weight_kg)
    
    dose_info = {
        "omega-3": {"value": 1000, "unit": "mg", "timing": "with meals"},
        "vitamin-d": {"value": 2000, "unit": "IU", "timing": "daily"},
        "magnesium": {"value": 200 if weight_bin in ["xs", "small"] else 400, "unit": "mg", "timing": "evening"},
        "hmb": {"value": 3, "unit": "g", "timing": "divided doses with meals"},
        "citrulline": {"value": 6 if weight_bin in ["xs", "small"] else 8, "unit": "g", "timing": "pre-workout"},
        "carnitine": {"value": 2, "unit": "g", "timing": "pre-workout"},
        "leucine": {"value": 2.5, "unit": "g", "timing": "post-workout"},
        "taurine": {"value": 1, "unit": "g", "timing": "daily"},
    }
    
    default_dose = dose_info.get(supplement, {"value": 1, "unit": "serving", "timing": "daily"})
    
    dose = Dose(
        value=default_dose["value"],
        unit=default_dose["unit"], 
        timing=default_dose["timing"],
        notes=[]
    )
    
    # Generic "why" based on goal
    why_templates = {
        "strength": f"May support strength and power development",
        "hypertrophy": f"May support muscle growth and recovery", 
        "endurance": f"May support endurance performance and recovery",
        "weight_loss": f"May support metabolism and body composition",
        "performance": f"May support athletic performance",
        "general": f"May support general health and wellness"
    }
    
    why = why_templates.get(profile.goal, "May provide health benefits")
    
    return StackItem(
        supplement=supplement,
        evidence_grade=base_grade,
        included=True,
        why=why,
        doses=[dose],
        citations=citations,
        tier="optional"
    )

def apply_profile_rules(items: List[StackItem], profile: UserProfile) -> List[StackItem]:
    """Apply caffeine sensitivity, pregnancy, and other profile-based rules"""
    adjusted = []
    
    for item in items:
        # Caffeine sensitivity
        if profile.caffeine_sensitive and item.supplement == "caffeine":
            if item.doses:
                item.doses[0].value = min(item.doses[0].value, 100)  # Cap at 100mg
                item.doses[0].notes.append("Reduced dose due to caffeine sensitivity")
        
        # Pregnancy (shouldn't reach here due to early return, but safety check)
        if profile.pregnancy and item.supplement not in PREGNANCY_SAFE_SUPPLEMENTS:
            item.included = False
            item.reason = "Not recommended during pregnancy"
            item.tier = "not_recommended"
            
        adjusted.append(item)
    
    return adjusted

def generate_safety_warnings(profile: UserProfile, items: List[StackItem]) -> List[str]:
    """Generate safety warnings based on profile and recommendations"""
    warnings = []
    
    if profile.age and profile.age < 18:
        warnings.append("⚠️ Minor (age < 18): Food-first approach strongly recommended. Parental guidance advised.")
    
    if profile.pregnancy:
        warnings.append("⚠️ PREGNANCY: Consult your healthcare provider before starting any supplements.")
    
    if profile.caffeine_sensitive:
        caffeine_items = [item for item in items if item.supplement == "caffeine" and item.included]
        if caffeine_items:
            warnings.append("⚠️ Caffeine sensitivity: Start with lower doses and monitor response.")
    
    # Add general disclaimer
    warnings.append("Educational information only. Not medical advice. Consult healthcare provider for personalized guidance.")
    
    return warnings

# Keep original function for backward compatibility
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

