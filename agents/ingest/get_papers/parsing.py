"""
PubMed article parsing and scoring

Handles parsing of PubMed XML, study classification, and reliability scoring.
No LLM calls - pure rule-based extraction and scoring.
"""

import os
import re
import logging
import math
from typing import Dict, List, Optional, Any

# ---------- New/expanded keyword maps ----------
GOAL_KEYWORDS = {
    "strength": [
        r"\b1\s?rm\b", r"\b(one|1|3|5|10)(-|\s)?repetition max(imum)?\b", r"\brm\b",
        r"\bmax(imum)? strength\b", r"\bmvc\b", r"\bmaximal voluntary contraction\b",
        r"\bbench press\b", r"\bsquat\b", r"\bdeadlift\b", r"\bleg press\b",
        r"\bisokinetic\b", r"\bhandgrip\b", r"\bgrip strength\b", r"\breps? to failure\b",
        r"\btraining volume\b", r"\bvolume load\b"
    ],
    "muscle_gain": [
        r"\bhypertroph(y|ic)\b", r"\bmuscle (size|thickness|volume|cross[-\s]?sectional area|csa)\b",
        r"\blean mass\b", r"\bfat[-\s]?free mass\b", r"\bffm\b", r"\bfat free mass\b"
    ],
    "endurance": [
        r"\bvo2( ?max| ?peak)?\b", r"\bpeak oxygen uptake\b", r"\btime[-\s]to[-\s]exhaustion\b",
        r"\btime trial\b", r"\bcycling time trial\b", r"\brunning time trial\b", r"\btt\b",
        r"\b6[-\s]?minute walk\b", r"\b6mwt\b", r"\byo[-\s]?yo\b", r"\brepeated sprint ability\b",
        r"\bshuttle run\b"
    ],
    "performance": [
        r"\bathletic performance\b", r"\bsport performance\b", r"\bfunctional performance\b",
        r"\bsprint( 10| 20| 30)? ?m?\b", r"\bagility\b", r"\bjump\b", r"\bcmj\b", r"\bvertical jump\b",
        r"\bpower\b", r"\bpeak power\b", r"\bmean power\b", r"\bwingate\b",
        r"\bsit[-\s]?to[-\s]?stand\b", r"\bsppb\b", r"\bgait speed\b", r"\btug test\b"
    ],
    "weight_loss": [
        r"\bweight (loss|reduction)\b", r"\bfat mass\b", r"\bpercent body fat\b", r"\bbody composition\b", r"\bbmi\b",
        r"\bwaist (circumference|to[-\s]?hip)\b", r"\bvisceral fat\b"
    ],
}

# Exercise-ish fallback cues to avoid "general" when outcomes are hinted at
EXERCISE_FALLBACK_TERMS = [
    "exercise", "training", "workout", "performance", "strength", "endurance", "sprint",
    "agility", "jump", "power", "vo2", "yo-yo", "time trial", "bench press", "squat"
]

SURVEY_SCREEN = [
    r"\b(prevalence|survey|questionnaire|knowledge|attitude|usage|consumption pattern)s?\b",
    r"\bcross[-\s]?sectional\b"
]

NO_GATE_CONTEXT = [
    r"\bnitrate(s)?\b", r"\bbeet(root)?\b", r"\bcitrulline\b", r"\bl-?arginine\b", r"\barginine akg\b"
]

def _window_hit(text: str, patterns: List[str], win: int = 60) -> bool:
    """
    Returns True if any pattern appears near typical outcome/metric words within a token window.
    A light heuristic to reduce spurious 'general'.
    """
    tl = text.lower()
    # cheap token split
    tokens = re.split(r"\W+", tl)
    joined = " ".join(tokens)
    for pat in patterns:
        for m in re.finditer(pat, joined, flags=re.I):
            start = max(0, m.start() - win)
            end = m.end() + win
            if start < end:
                snippet = joined[start:end]
                # look for generic measurement terms near the hit
                if re.search(r"\b(change|increase|decrease|improv(e|ement)|effect|outcome|performance|strength|mass|power|time|trial|reps?)\b", snippet, re.I):
                    return True
    return False

def _infer_primary_goal(title: str, abstract: str) -> str:
    """Prefer explicit outcomes; otherwise infer from goal keywords with local windows."""
    text = f"{title} {abstract or ''}"
    scores = {k: 0 for k in GOAL_KEYWORDS.keys()}
    for goal, pats in GOAL_KEYWORDS.items():
        if _window_hit(text, pats, win=60):
            scores[goal] += 1
    mapping = {
        "strength": "strength",
        "muscle_gain": "muscle_gain",
        "endurance": "performance",   # roll endurance up under performance bucket
        "performance": "performance",
        "weight_loss": "weight_loss"
    }
    if any(scores.values()):
        max_val = max(scores.values())
        candidates = [g for g, v in scores.items() if v == max_val]
        # tie-breaker preference
        priority = ["strength", "muscle_gain", "performance", "endurance", "weight_loss"]
        for p in priority:
            if p in candidates:
                return mapping[p]
    # fallback: if the paper clearly lives in an exercise/training context, don't call it "general"
    tl = text.lower()
    if any(tok in tl for tok in EXERCISE_FALLBACK_TERMS):
        return "performance"
    return "general"

def _is_prevalence_survey(text: str) -> bool:
    """Exclude pure prevalence/usage surveys unless they also report exercise outcomes."""
    tl = text.lower()
    if any(re.search(p, tl, re.I) for p in SURVEY_SCREEN):
        # Only screen out if no performance/strength/hypertrophy/weight-loss outcomes appear
        any_outcome = False
        for pats in GOAL_KEYWORDS.values():
            if any(re.search(p, tl, re.I) for p in pats):
                any_outcome = True
                break
        return not any_outcome
    return False

def _postprocess_supplement_tags(supps: List[str], text: str) -> List[str]:
    """
    Gate 'nitric-oxide' to avoid over-tagging: keep it only if nitrate/beet/citrulline/arginine context exists.
    Also de-duplicate and canonicalize hyphen/space variants.
    """
    out = set()
    tl = text.lower()
    keep_no = False
    if "nitric-oxide" in supps or "nitric oxide" in supps:
        if any(re.search(p, tl, re.I) for p in NO_GATE_CONTEXT):
            keep_no = True
    for s in supps:
        s_norm = s.strip().lower().replace(" ", "-")
        if s_norm in ("nitric-oxide",) and not keep_no:
            continue
        out.add(s_norm)
    return sorted(out)

logger = logging.getLogger(__name__)

# Environment variables
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")

# Enhanced supplement keywords with form-specific detection
SUPP_KEYWORDS = {
    "creatine": [r"\bcreatine\b", r"\bcreatine monohydrate\b", r"\bcreatine supplementation\b"],
    "creatine-monohydrate": [r"\bcreatine monohydrate\b", r"\bcreatine monohydrate supplementation\b"],
    "creatine-hcl": [r"\bcreatine hcl\b", r"\bcreatine hydrochloride\b", r"\bcreatine HCl\b"],
    "creatine-anhydrous": [r"\bcreatine anhydrous\b", r"\banhydrous creatine\b"],
    "creatine-ethyl-ester": [r"\bcreatine ethyl ester\b", r"\bCEE\b"],
    
    "caffeine": [r"\bcaffeine\b", r"\bcoffee\b", r"\bcaffeinated\b"],
    "caffeine-anhydrous": [r"\bcaffeine anhydrous\b", r"\banhydrous caffeine\b"],
    "caffeine-citrate": [r"\bcaffeine citrate\b"],
    
    "beta-alanine": [r"\bbeta-?alanine\b", r"\bβ-alanine\b"],
    
    "citrulline": [r"\bcitrulline\b", r"\bl-citrulline\b"],
    "citrulline-malate": [r"\bcitrulline malate\b", r"\bl-citrulline malate\b"],
    
    "nitrate": [r"\bnitrate(s)?\b", r"\bNO3\b"],
    "beetroot": [r"\bbeet(root)?\b", r"\bbeetroot extract\b", r"\bbeet juice\b"],
    
    "protein": [r"\bprotein supplement(ation)?\b", r"\bprotein powder\b", r"\bprotein intake\b"],
    "whey-protein": [r"\bwhey\b", r"\bwhey protein\b", r"\bwhey isolate\b", r"\bwhey concentrate\b"],
    "casein-protein": [r"\bcasein\b", r"\bcasein protein\b", r"\bmicellar casein\b"],
    "soy-protein": [r"\bsoy protein\b", r"\bsoy isolate\b"],
    "pea-protein": [r"\bpea protein\b", r"\bpea isolate\b"],
    
    "hmb": [r"\bhmb\b", r"\bbeta-hydroxy beta-methylbutyrate\b", r"\bβ-hydroxy β-methylbutyrate\b"],
    "hmb-ca": [r"\bhmb-ca\b", r"\bhmb calcium\b"],
    "hmb-fa": [r"\bhmb-fa\b", r"\bhmb free acid\b"],
    
    "bcaa": [r"\bbcaa(s)?\b", r"\bbranched[- ]chain amino acids\b"],
    "leucine": [r"\bleucine\b", r"\bl-leucine\b"],
    "isoleucine": [r"\bisoleucine\b", r"\bl-isoleucine\b"],
    "valine": [r"\bvaline\b", r"\bl-valine\b"],
    
    "tribulus": [r"\btribulus\b", r"\btribulus terrestris\b"],
    "d-aspartic-acid": [r"\bd-?aspartic\b", r"\bD-aspartic acid\b", r"\bDAA\b"],
    "betaine": [r"\bbetaine\b", r"\btrimethylglycine\b"],
    "taurine": [r"\btaurine\b"],
    
    "carnitine": [r"\bcarnitine\b"],
    "l-carnitine": [r"\bl-carnitine\b", r"\bl-carnitine tartrate\b"],
    "acetyl-l-carnitine": [r"\bacetyl-l-carnitine\b", r"\bALCAR\b"],
    
    "zma": [r"\bzma\b", r"\bzinc magnesium aspartate\b"],
    "glutamine": [r"\bglutamine\b", r"\bl-glutamine\b"],
    "cla": [r"\bconjugated linoleic acid\b", r"\bCLA\b"],
    "ecdysteroids": [r"\becdyster(one|oid)s?\b", r"\brhaponticum\b", r"\b20-HE\b", r"\b20-hydroxyecdysone\b"],
    "deer-antler": [r"\bdeer antler\b", r"\bIGF-1\b", r"\bvelvet antler\b"],
    
    "arginine": [r"\barginine\b", r"\bl-arginine\b"],
    "arginine-akg": [r"\barginine akg\b", r"\barginine alpha-ketoglutarate\b"],
    # Removed "nitric-oxide" as a supplement tag to prevent mechanism-level flooding.
    # Additional supplements:
    "omega-3": [r"\bomega[- ]?3\b", r"\bEPA\b", r"\bDHA\b", r"\bfish oil\b", r"\bn-?3\b"],
    "vitamin-d": [r"\bvitamin\s*d\b", r"\bcholecalciferol\b", r"\b25 ?\(?OH\)?D\b"],
    "magnesium": [r"\bmagnesium\b"],
    "iron": [r"\biron\b", r"\bferrous\b", r"\bferric\b"],
    "sodium-bicarbonate": [r"\bsodium bicarbonate\b", r"\bNaHCO3\b", r"\bbaking soda\b"],
    "sodium-phosphate": [r"\bsodium phosphate\b", r"\bphosphate loading\b"],
    "glycerol": [r"\bglycerol\b"],
    "curcumin": [r"\bcurcumin\b", r"\bturmeric\b"],
    "quercetin": [r"\bquercetin\b"],
    "ashwagandha": [r"\bashwagandha\b", r"\bwithania\s+somnifera\b"],
    "rhodiola": [r"\brhodiola\b", r"\brhodiola\s+rosea\b"],
    "cordyceps": [r"\bcordyceps\b"],
    # --- Added: widely purchased & often-claimed supplements (some low/no evidence) ---
    "alpha-gpc": [r"\balpha[- ]?gpc\b", r"\bL[- ]?alpha[- ]?glycerylphosphorylcholine\b", r"\bglycerylphosphorylcholine\b"],
    "theacrine": [r"\btheacrine\b", r"\bTeaCrine\b"],
    "yohimbine": [r"\byohimbine\b", r"\byohimbe\b"],
    "green-tea-extract": [r"\bgreen tea extract\b", r"\bEGCG\b", r"\b(epi)?gallocatechin\b", r"\bcatechin(s)?\b"],
    "ketone-esters": [r"\bketone ester(s)?\b", r"\b(beta-)?hydroxybutyrate\b", r"\bBHB\b", r"\bketone salt(s)?\b"],
    "collagen": [r"\bcollagen\b", r"\bcollagen peptide(s)?\b", r"\bgelatin\b"],
    "blackcurrant": [r"\bblackcurrant\b", r"\bRibes\s+nigrum\b"],
    "tart-cherry": [r"\btart cherry\b", r"\bMontmorency\b", r"\bPrunus\s+cerasus\b"],
    "pomegranate": [r"\bpomegranate\b", r"\bPunica\s+granatum\b"],
    "pycnogenol": [r"\bpycnogenol\b", r"\bFrench maritime pine\b", r"\bPine bark extract\b"],
    "resveratrol": [r"\bresveratrol\b"],
    "nac": [r"\bN-?acetylcysteine\b", r"\bNAC\b"],
    "coq10": [r"\bco-?enzyme\s*Q10\b", r"\bubiquinone\b", r"\bubiquinol\b"],
    "fenugreek": [r"\bfenugreek\b", r"\bTrigonella\s+foenum[- ]graecum\b"],
    "tongkat-ali": [r"\btongkat ali\b", r"\bEurycoma\s+longifolia\b"],
    "maca": [r"\bmaca\b", r"\bLepidium\s+meyenii\b"],
    "boron": [r"\bboron\b"],
    "shilajit": [r"\bshilajit\b"],
    "d-ribose": [r"\bd-?ribose\b"],
    "phosphatidic-acid": [r"\bphosphatidic acid\b", r"\bPA supplementation\b"],
    "phosphatidylserine": [r"\bphosphatidylserine\b"],
    "epicatechin": [r"\bepicatechin\b", r"\b(-)-?epicatechin\b"],
    "red-spinach": [r"\bred spinach\b", r"\bAmaranthus\b"],
    "synephrine": [r"\bsynephrine\b", r"\bbitter orange\b", r"\bCitrus\s+aurantium\b"],
    "garcinia-cambogia": [r"\bgarcinia\s+cambogia\b", r"\bHCA\b", r"\bhydroxycitric acid\b"],
    "raspberry-ketone": [r"\braspberry ketone(s)?\b"],
    "chromium-picolinate": [r"\bchromium picolinate\b"],
    "sodium-citrate": [r"\bsodium citrate\b"],
    "alpha-lipoic-acid": [r"\balpha[- ]lipoic acid\b", r"\bALA\b", r"\bthioctic acid\b"],
    "theanine": [r"\bL-?theanine\b", r"\btheanine\b"],
    "hica": [r"\bHICA\b", r"\balpha[- ]hydroxy[- ]isocaproic acid\b"]
}

# Mechanism keywords (not supplements)
MECHANISM_KEYWORDS = {"nitric-oxide", "NO", "nitric oxide"}

# Enhanced outcome categories
HYPERTROPHY_OUTCOMES = {
    "muscle_mass": [r"\bmuscle mass\b", r"\blean mass\b", r"\bfat-free mass\b", r"\bFFM\b"],
    "muscle_size": [r"\bmuscle size\b", r"\bCSA\b", r"\bcross-sectional area\b"],
    "muscle_volume": [r"\bmuscle volume\b", r"\bthigh volume\b", r"\barm volume\b"],
    "muscle_thickness": [r"\bmuscle thickness\b", r"\bultrasound\b"],
    "body_composition": [r"\bbody composition\b", r"\bDEXA\b", r"\bbodpod\b"]
}

WEIGHT_LOSS_OUTCOMES = {
    "weight_loss": [r"\bweight loss\b", r"\bweight reduction\b", r"\bbody weight\b"],
    "fat_loss": [r"\bfat loss\b", r"\bfat mass\b", r"\bpercent body fat\b"],
    "waist_circumference": [r"\bwaist circumference\b", r"\bwaist-to-hip\b"],
    "bmi": [r"\bBMI\b", r"\bbody mass index\b"],
    "visceral_fat": [r"\bvisceral fat\b", r"\babdominal fat\b"]
}

STRENGTH_OUTCOMES = {
    "max_strength": [r"\b1RM\b", r"\bmax strength\b", r"\bbench press\b", r"\bsquat\b"],
    "power": [r"\bpower\b", r"\bCMJ\b", r"\bvertical jump\b", r"\bexplosive\b"],
    "recovery": [r"\brecovery\b", r"\bDOMS\b", r"\bsoreness\b"]
}

ENDURANCE_OUTCOMES = {
    "vo2max": [r"\bvo2(max)?\b", r"\bvo₂(max)?\b", r"\bmaximal oxygen uptake\b"],
    "time_trial": [r"\btime[- ]to[- ]exhaustion\b", r"\btime trial\b", r"\btte\b"],
    "yo_yo": [r"\byo[- ]yo\b"],
    "running_economy": [r"\brunning economy\b"],
    "cycling_test": [r"\bwatts\b", r"\bpower output\b", r"\bwingate\b"]
}

PERFORMANCE_OUTCOMES = {
    "sport_performance": [r"\bsport performance\b", r"\bathletic performance\b"],
    "training_adaptation": [r"\btraining adaptation\b", r"\badaptation\b"],
    "muscle_function": [r"\bmuscle function\b", r"\bmuscle performance\b"]
}

SAFETY_INDICATORS = {
    "side_effects": [r"\bside effects?\b", r"\badverse events?\b", r"\btolerability\b"],
    "contraindications": [r"\bcontraindicated\b", r"\bnot recommended\b", r"\bcaution\b"],
    "pregnancy": [r"\bpregnancy\b", r"\bpregnant\b", r"\blactation\b"],
    "diabetes": [r"\bdiabetes\b", r"\bdiabetic\b", r"\bglucose\b"],
    "hypertension": [r"\bhypertension\b", r"\bblood pressure\b", r"\bhypertensive\b"]
}

# Legacy outcome map for backward compatibility
OUTCOME_MAP = {
    "strength": [r"\b1 ?RM\b", r"\bmax(imum)? strength\b", r"\bbench press\b", r"\bsquat\b"],
    "hypertrophy": [r"\blean mass\b", r"\bfat[- ]free mass\b", r"\bCSA\b", r"\bhypertroph(y|ic)\b"],
    "power": [r"\bCMJ\b", r"\bvertical jump\b", r"\bpower\b"],
    "endurance": [r"\bVO2\b", r"\btime to exhaustion\b", r"\bendurance\b"],
    "soreness": [r"\bDOMS\b", r"\bsoreness\b"]
}


def classify_study_type(pub_types, title: str = "", abstract: str = ""):
    s = set([str(pt).lower() for pt in (pub_types or [])])
    # direct mappings (expand beyond the basic four)
    if "meta-analysis" in s:
        return "meta-analysis"
    if "systematic review" in s:
        return "systematic_review"
    if "randomized controlled trial" in s or "randomised controlled trial" in s:
        return "RCT"
    if "controlled clinical trial" in s:
        return "controlled_trial"
    if "clinical trial" in s:
        return "clinical_trial"
    if "cross-over studies" in s or "crossover studies" in s:
        return "crossover"
    if "cohort studies" in s or "prospective studies" in s or "retrospective studies" in s:
        return "cohort"
    if "case-control studies" in s or "case-control study" in s:
        return "case_control"
    if "cross-sectional studies" in s or "cross-sectional study" in s:
        return "cross_sectional"
    if "pilot projects" in s or "pilot study" in s:
        return "pilot"
    if "multicenter study" in s:
        return "clinical_trial"
    if "review" in s:
        return "review"
    # heuristic upgrade: title/abstract hints
    ta = f"{title} {abstract or ''}".lower()
    if ("double-blind" in ta or "placebo-controlled" in ta) and "random" in ta:
        return "RCT"
    if re.search(r"\bcross[-\s]?over\b", ta):
        return "crossover"
    if "systematic review" in ta:
        return "systematic_review"
    if "randomized" in ta or "randomised" in ta:
        return "controlled_trial"
    return "other"


def infer_study_category(pub_types: List[str], title: str, abstract: str) -> str:
    """
    Infer study category from publication types, title, and abstract
    
    Args:
        pub_types: List of publication type strings
        title: Article title
        abstract: Article abstract
        
    Returns:
        Study category string
    """
    # Combine all text for analysis
    text = " ".join(pub_types + [title, abstract]).lower()
    
    # Check for meta-analysis
    if re.search(r'meta-?analysis', text):
        return "meta_analysis"
    
    # Check for systematic review
    if re.search(r'systematic review', text):
        return "systematic_review"
    
    # Check for intervention studies
    intervention_keywords = [
        r'randomized', r'randomised', r'placebo', r'controlled trial',
        r'crossover', r'cross-over'
    ]
    if any(re.search(keyword, text) for keyword in intervention_keywords):
        return "intervention"
    
    # Check for observational usage studies
    usage_keywords = [
        r'cross[- ]sectional', r'survey', r'questionnaire', 
        r'prevalence', r'usage', r'use patterns'
    ]
    if any(re.search(keyword, text) for keyword in usage_keywords):
        return "observational_usage"
    
    # Check for narrative review (review present but not systematic/meta)
    if re.search(r'review', text) and not re.search(r'systematic|meta', text):
        return "narrative_review"
    
    return "other"


def calculate_reliability_score(rec: Dict, dynamic_weights: Optional[Dict] = None) -> float:
    """
    Calculate reliability score based on study type, sample size, and quality indicators
    
    Args:
        rec: PubMed record dictionary
        dynamic_weights: Optional dynamic weights for diversity scoring
        
    Returns:
        Reliability score
    """
    score = 0.0
    
    # Enhanced study type scoring (prioritize high-quality designs)
    study_type = classify_study_type(
        rec.get("MedlineCitation", {}).get("Article", {}).get("PublicationTypeList", {}).get("PublicationType", [])
    )
    if study_type == "meta-analysis":
        score += 12.0  # Highest priority
    elif study_type == "RCT":
        score += 10.0  # Very high priority
    elif study_type == "crossover":
        score += 7.0  # Good priority
    elif study_type == "cohort":
        score += 4.0  # Medium priority
    else:
        score += 1.0  # Lower priority for other designs
    
    # Sample size scoring (extract from abstract if possible)
    abstract = rec.get("MedlineCitation", {}).get("Article", {}).get("Abstract", {})
    if isinstance(abstract, dict):
        ab_text = abstract.get("AbstractText")
        if ab_text:
            # Look for sample size patterns
            n_patterns = [
                r'n\s*=\s*(\d+)', r'(\d+)\s*participants', r'(\d+)\s*subjects',
                r'(\d+)\s*patients', r'(\d+)\s*volunteers', r'(\d+)\s*individuals'
            ]
            max_n = 0
            for pattern in n_patterns:
                matches = re.findall(pattern, str(ab_text), re.I)
                for match in matches:
                    try:
                        n = int(match)
                        max_n = max(max_n, n)
                    except:
                        pass
            
            if max_n > 0:
                # Sample size scoring (logarithmic scale)
                if max_n >= 1000:
                    score += 5.0
                elif max_n >= 500:
                    score += 4.0
                elif max_n >= 100:
                    score += 3.0
                elif max_n >= 50:
                    score += 2.0
                elif max_n >= 20:
                    score += 1.0
    
    # Quality indicators
    title = rec.get("MedlineCitation", {}).get("Article", {}).get("ArticleTitle", "")
    if isinstance(title, dict):
        title = title.get("#text", "") or str(title)
    title_lower = str(title).lower()
    
    # High-quality keywords
    quality_indicators = [
        "systematic review", "meta-analysis", "double-blind", "placebo-controlled",
        "randomized", "controlled trial", "crossover", "longitudinal"
    ]
    for indicator in quality_indicators:
        if indicator in title_lower:
            score += 1.0
    
    # Journal impact (simplified - could be enhanced with actual impact factors)
    journal = rec.get("MedlineCitation", {}).get("Article", {}).get("Journal", {})
    journal_name = journal.get("ISOAbbreviation", "") or journal.get("Title", "")
    high_impact_journals = [
        "J Appl Physiol", "Med Sci Sports Exerc", "J Strength Cond Res",
        "Eur J Appl Physiol", "Int J Sport Nutr Exerc Metab", "Sports Med",
        "Am J Clin Nutr", "Nutrients", "J Int Soc Sports Nutr"
    ]
    if any(j in journal_name for j in high_impact_journals):
        score += 2.0
    
    # Recent papers get slight boost
    year = None
    pubdate = journal.get("JournalIssue", {}).get("PubDate", {})
    for k in ("Year", "MedlineDate"):
        if pubdate.get(k):
            try:
                year = int(str(pubdate.get(k))[:4])
                break
            except:
                pass
    
    if year and year >= 2020:
        score += 1.0
    elif year and year >= 2015:
        score += 0.5
    
    # Dynamic supplement diversity scoring based on existing index
    # Extract content from abstract
    content = ""
    if isinstance(abstract, dict):
        ab_text = abstract.get("AbstractText")
        if ab_text:
            if isinstance(ab_text, list):
                content_parts = []
                for a in ab_text:
                    if isinstance(a, dict):
                        text = a.get("#text", "")
                        if text:
                            content_parts.append(str(text))
                    else:
                        content_parts.append(str(a))
                content = " ".join(content_parts)
            else:
                if isinstance(ab_text, dict):
                    content = str(ab_text.get("#text", ""))
                else:
                    content = str(ab_text)
    
    text_for_diversity = f"{title}\n{content}".lower()
    diversity_bonus = 0.0
    
    if dynamic_weights:
        # Use dynamic weights based on existing supplement distribution
        for supp, weight in dynamic_weights.items():
            if supp in text_for_diversity or supp.replace("-", " ") in text_for_diversity:
                diversity_bonus = max(diversity_bonus, weight)
    else:
        # Fallback to static weights if no dynamic weights provided
        rare_supplements = {
            "tribulus": 3.0, "d-aspartic-acid": 3.0, "deer-antler": 3.0, 
            "ecdysteroids": 3.0, "betaine": 2.5, "taurine": 2.5, "carnitine": 2.0,
            "zma": 2.0, "glutamine": 1.5, "cla": 1.5, "hmb": 1.0
        }
        
        medium_supplements = {
            "citrulline": 1.0, "nitrate": 1.0, "beta-alanine": 0.5
        }
        
        # Check for supplement mentions and apply diversity bonus
        for supp, bonus in rare_supplements.items():
            if supp.replace("-", " ") in text_for_diversity or supp.replace("-", "-") in text_for_diversity:
                diversity_bonus = max(diversity_bonus, bonus)
        
        for supp, bonus in medium_supplements.items():
            if supp in text_for_diversity:
                diversity_bonus = max(diversity_bonus, bonus)
        
        # Creatine penalty to reduce over-representation
        if "creatine" in text_for_diversity:
            diversity_bonus = max(diversity_bonus, -1.0)  # Small penalty
    
    score += diversity_bonus
    
    # Apply study category reliability nudge
    study_category = rec.get("study_category", "other")
    if study_category == "intervention":
        score += 0.25
    elif study_category == "observational_usage":
        score -= 0.25
    
    return score


def _find(text: str, patterns: List[str]) -> bool:
    """Check if any pattern matches in text"""
    return any(re.search(p, text, flags=re.I) for p in patterns)


def _near_supplement_context(text: str, match_span: tuple, window: int = 10) -> bool:
    """
    Check if supplement term appears near relevant context words
    
    Args:
        text: Full text to search
        match_span: (start, end) of the supplement match
        window: Number of tokens to check around the match
        
    Returns:
        True if supplement appears near relevant context
    """
    context_words = [
        "supplement", "supplementation", "dose", "ingest", "randomized", 
        "trial", "placebo", "intervention"
    ]
    
    # Get surrounding text
    start, end = match_span
    context_start = max(0, start - window * 10)  # Approximate token boundary
    context_end = min(len(text), end + window * 10)
    context_text = text[context_start:context_end].lower()
    
    # Check for context words
    return any(word in context_text for word in context_words)


def extract_supplements(text: str, pub_types: List[str] = None) -> List[str]:
    """Extract supplement mentions from text with proximity rules"""
    t = text.lower()
    supplements = []
    
    # Check if this is a trial/meta/systematic study
    is_trial_study = False
    if pub_types:
        pub_text = " ".join([str(pt).lower() for pt in pub_types])
        trial_keywords = ["trial", "meta", "systematic", "randomized", "randomised"]
        is_trial_study = any(keyword in pub_text for keyword in trial_keywords)
    
    for slug, patterns in SUPP_KEYWORDS.items():
        for pattern in patterns:
            match = re.search(pattern, t, re.I)
            if match:
                # Keep if trial study OR proximity context found
                if is_trial_study or _near_supplement_context(t, match.span()):
                    supplements.append(slug)
                    break  # Found this supplement, move to next
    
    return sorted(set(supplements))


def extract_outcomes(text: str) -> List[str]:
    """Extract outcome mentions from text"""
    t = text.lower()
    return sorted({k for k, pats in OUTCOME_MAP.items() if _find(t, pats)})


def extract_goal_specific_outcomes(text: str) -> Dict[str, str]:
    """Extract goal-specific outcomes from paper text"""
    text_lower = text.lower()
    
    # Muscle gain/hypertrophy
    hypertrophy_outcomes = []
    for outcome, patterns in HYPERTROPHY_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            hypertrophy_outcomes.append(outcome)
    
    # Weight loss
    weight_loss_outcomes = []
    for outcome, patterns in WEIGHT_LOSS_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            weight_loss_outcomes.append(outcome)
    
    # Strength/power
    strength_outcomes = []
    for outcome, patterns in STRENGTH_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            strength_outcomes.append(outcome)
    
    # Endurance
    endurance_outcomes = []
    for outcome, patterns in ENDURANCE_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            endurance_outcomes.append(outcome)
    
    # Performance
    performance_outcomes = []
    for outcome, patterns in PERFORMANCE_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            performance_outcomes.append(outcome)
    
    # Determine primary goal with margin requirement
    goal_scores = {
        "muscle_gain": len(hypertrophy_outcomes),
        "weight_loss": len(weight_loss_outcomes),
        "strength": len(strength_outcomes),
        "endurance": len(endurance_outcomes),
        "performance": len(performance_outcomes)
    }
    
    # Find goal with highest count and margin of ≥1 over others
    max_score = max(goal_scores.values()) if any(goal_scores.values()) else 0
    if max_score > 0:
        # Check if any goal has margin of ≥1 over others
        for goal, score in goal_scores.items():
            if score == max_score:
                others_max = max([s for g, s in goal_scores.items() if g != goal], default=0)
                if score >= others_max + 1:
                    primary_goal = goal
                    break
        else:
            # No clear winner, try performance if sport tests present
            if any(re.search(p, text_lower, re.I) for p in ["sport", "athletic", "competition"]):
                primary_goal = "performance"
            else:
                primary_goal = "general"
    else:
        primary_goal = "general"
    
    return {
        "primary_goal": primary_goal,
        "hypertrophy_outcomes": ",".join(hypertrophy_outcomes),
        "weight_loss_outcomes": ",".join(weight_loss_outcomes),
        "strength_outcomes": ",".join(strength_outcomes),
        "endurance_outcomes": ",".join(endurance_outcomes),
        "performance_outcomes": ",".join(performance_outcomes)
    }


def extract_safety_indicators(text: str) -> Dict[str, Any]:
    """Extract safety and contraindication information"""
    text_lower = text.lower()
    
    safety_tags = []
    for indicator, patterns in SAFETY_INDICATORS.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            safety_tags.append(indicator)
    
    return {
        "safety_indicators": ",".join(safety_tags),
        "has_side_effects": "side_effects" in safety_tags,
        "has_contraindications": "contraindications" in safety_tags
    }


def extract_population_attrs(text: str) -> Dict[str, Optional[str]]:
    """Extract structured population attributes"""
    text_lower = text.lower()
    
    # Sex detection
    sex = None
    if any(word in text_lower for word in ["male", "men", "males"]):
        if any(word in text_lower for word in ["female", "women", "females"]):
            sex = "mixed"
        else:
            sex = "male"
    elif any(word in text_lower for word in ["female", "women", "females"]):
        sex = "female"
    
    # Training status
    training_status = None
    if any(word in text_lower for word in ["athlete", "elite", "professional", "competitive"]):
        training_status = "athletes"
    elif any(word in text_lower for word in ["trained", "experienced", "regular exercise"]):
        training_status = "trained"
    elif any(word in text_lower for word in ["untrained", "sedentary", "inactive"]):
        training_status = "untrained"
    elif any(word in text_lower for word in ["sedentary", "inactive", "no exercise"]):
        training_status = "sedentary"
    
    # Age band (approximate via MeSH-like cues)
    age_band = None
    if any(word in text_lower for word in ["young", "college", "university", "18-25", "18-30"]):
        age_band = "young_adult"
    elif any(word in text_lower for word in ["adult", "middle-aged", "30-50", "40-60"]):
        age_band = "adult"
    elif any(word in text_lower for word in ["older", "elderly", "senior", "60+", "65+"]):
        age_band = "older"
    
    return {
        "sex": sex,
        "training_status": training_status,
        "age_band": age_band
    }


def extract_dosage_info(text: str) -> dict:
    """Extract dosage and timing information (more tolerant to prose)."""
    tl = text.lower()
    # capture like "3 g/day", "6.4 g daily", "200 mg pre", "loading 20 g", etc.
    units = r"(g|mg|mcg|gram[s]?|milligram[s]?)"
    pat_amount = rf"(\d+(?:\.\d+)?)\s*{units}"
    pat_daily = rf"{pat_amount}\s*(per\s*day|daily|/day)"
    pat_timing = rf"{pat_amount}\s*(pre|post|before|after)(?:-?\s*workout)?"
    pat_phases = rf"{pat_amount}\s*(loading|maintenance)"
    dosages = []
    for pat in (pat_daily, pat_timing, pat_phases):
        for m in re.finditer(pat, tl, re.I):
            dosages.append(m.group(0))
    return {
        "dosage_info": ",".join(sorted(set(dosages))),
        "has_loading_phase": "loading" in tl,
        "has_maintenance_phase": "maintenance" in tl
    }


def categorize_sample_size(sample_size: int) -> str:
    """Categorize sample size for analysis"""
    if sample_size >= 100:
        return "large"
    elif sample_size >= 30:
        return "medium"
    else:
        return "small"


def categorize_duration(duration: str) -> str:
    """Categorize study duration with ± cases normalized."""
    dl = (duration or "").lower()
    if "year" in dl:
        return "long_term"
    if "month" in dl:
        return "medium_term"
    if "week" in dl or "day" in dl:
        return "short_term"
    return "short_term"


def categorize_population(population: str) -> str:
    """Categorize study population"""
    if "athlete" in population:
        return "athletes"
    elif "trained" in population:
        return "trained"
    elif "untrained" in population:
        return "untrained"
    elif "elderly" in population:
        return "elderly"
    else:
        return "general"


def calculate_study_design_score(study_type: str, sample_size: int, duration: str) -> float:
    """Calculate study design quality score"""
    score = 0.0
    
    # Study type scoring
    if study_type == "meta-analysis":
        score += 3.0
    elif study_type == "RCT":
        score += 2.5
    elif study_type == "crossover":
        score += 2.0
    elif study_type == "cohort":
        score += 1.5
    else:
        score += 1.0
    
    # Sample size scoring
    if sample_size >= 100:
        score += 2.0
    elif sample_size >= 50:
        score += 1.5
    elif sample_size >= 30:
        score += 1.0
    else:
        score += 0.5
    
    # Duration scoring
    if "year" in duration:
        score += 1.5
    elif "month" in duration:
        score += 1.0
    else:
        score += 0.5
    
    return min(score, 10.0)  # Cap at 10


def is_relevant_human_study(title: str, content: str) -> bool:
    """
    Minimal relevance filter - trust PubMed MeSH filtering for humans/exercise.
    Only exclude obvious animal/in-vitro studies that slipped through.
    """
    text = f"{title} {content}".lower()
    
    # Only exclude clear animal/in-vitro studies (PubMed MeSH should handle humans/exercise)
    exclusion_patterns = [
        r"\brat(s)?\b", r"\bmice\b", r"\bmouse\b", r"\bmurine\b",
        r"\bin vitro\b", r"\bcell culture\b", r"\bcellular\b",
        r"\bfish\b", r"\bzebrafish\b", r"\bporcine\b", r"\bbovine\b",
        r"\bcanine\b", r"\bfeline\b", r"\bprimate(s)?\b",
        r"\bpetri dish\b", r"\btissue culture\b", r"\bmitochondrial\b"
    ]
    
    # Only reject if clear animal/in-vitro indicators are found
    has_exclusions = any(re.search(pattern, text, re.I) for pattern in exclusion_patterns)
    
    # Trust PubMed's humans[MeSH] and exercise filtering - only exclude obvious non-human studies
    return not has_exclusions


def parse_pubmed_article(rec: Dict, dynamic_weights: Optional[Dict] = None) -> Optional[Dict]:
    """
    Parse a PubMed article record into standardized format
    
    Args:
        rec: PubMed XML record
        dynamic_weights: Optional dynamic weights for diversity scoring
        
    Returns:
        Parsed article dictionary or None if irrelevant
    """
    art = rec.get("MedlineCitation", {}).get("Article", {})
    pmid = rec.get("MedlineCitation", {}).get("PMID", {}).get("#text") or rec.get("MedlineCitation", {}).get("PMID")
    title_raw = art.get("ArticleTitle") or ""
    if isinstance(title_raw, dict):
        title = title_raw.get("#text", "") or str(title_raw)
    else:
        title = str(title_raw)
    title = title.strip()
    
    abstract = art.get("Abstract", {})
    if isinstance(abstract, dict):
        ab = abstract.get("AbstractText")
        if ab:
            if isinstance(ab, list):
                content_parts = []
                for a in ab:
                    if isinstance(a, dict):
                        text = a.get("#text", "")
                        if text:
                            content_parts.append(str(text))
                    else:
                        content_parts.append(str(a))
                content = " ".join(content_parts)
            else:
                if isinstance(ab, dict):
                    content = str(ab.get("#text", ""))
                else:
                    content = str(ab)
        else:
            content = ""
    else:
        content = ""
    
    jour = art.get("Journal", {})
    journal = jour.get("ISOAbbreviation") or jour.get("Title") or ""
    year = None
    pubdate = jour.get("JournalIssue", {}).get("PubDate", {})
    for k in ("Year", "MedlineDate"):
        if pubdate.get(k):
            try:
                year = int(str(pubdate.get(k))[:4])
            except:
                pass
            break
    
    doi = None
    ids = rec.get("PubmedData", {}).get("ArticleIdList", {}).get("ArticleId", [])
    if isinstance(ids, dict):
        ids = [ids]
    for idn in ids or []:
        if idn.get("@IdType") == "doi":
            doi = idn.get("#text")
            break
    
    pubtypes = art.get("PublicationTypeList", {}).get("PublicationType", [])
    if isinstance(pubtypes, dict):
        pubtypes = [pubtypes]
    pubtypes = [pt.get("#text", "") if isinstance(pt, dict) else str(pt) for pt in pubtypes]
    study_type = classify_study_type(pubtypes, title=title, abstract=content)
    
    # Infer study category
    study_category = infer_study_category(pubtypes, title, content)

    # Calculate reliability score with dynamic weights
    reliability_score = calculate_reliability_score(rec, dynamic_weights)

    text_for_tags = f"{title}\n{content}"
    
    # Check relevance - skip irrelevant studies early
    if not is_relevant_human_study(title, content):
        return None  # Skip this paper
    # Screen out prevalence/usage-only surveys (no exercise outcomes)
    if _is_prevalence_survey(f"{title} {content or ''}"):
        return None
    
    supplements = extract_supplements(text_for_tags, pubtypes)
    supplements = _postprocess_supplement_tags(supplements, text_for_tags)
    outcomes = extract_outcomes(text_for_tags)
    
    # Enhanced metadata extraction
    goal_data = extract_goal_specific_outcomes(text_for_tags)
    inferred_goal = _infer_primary_goal(title, content)
    primary_goal = goal_data.get("primary_goal") if goal_data.get("primary_goal") and goal_data.get("primary_goal") != "general" else inferred_goal
    safety_data = extract_safety_indicators(text_for_tags)
    dosage_data = extract_dosage_info(text_for_tags)
    
    # Extract sample size from content
    sample_size = 0
    if content:
        n_patterns = [
            r'n\s*=\s*(\d+)', r'(\d+)\s*participants', r'(\d+)\s*subjects',
            r'(\d+)\s*patients', r'(\d+)\s*volunteers', r'(\d+)\s*individuals'
        ]
        for pattern in n_patterns:
            matches = re.findall(pattern, content, re.I)
            for match in matches:
                try:
                    n = int(match)
                    sample_size = max(sample_size, n)
                except:
                    pass
    
    # Extract study duration from content (normalize things like "11 ± 4 weeks" -> "11 weeks")
    study_duration = ""
    if content:
        dur = None
        # capture "11 ± 4 weeks", "8 weeks", "12 months"
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?\s*(weeks?|months?|days?|years?)", content, re.I)
        if m:
            val, unit = m.group(1), m.group(2)
            dur = f"{val} {unit}"
        if not dur:
            m2 = re.search(r"(for|over|during)\s+(\d+(?:\.\d+)?)\s*(weeks?|months?|days?|years?)", content, re.I)
            if m2:
                dur = f"{m2.group(2)} {m2.group(3)}"
        study_duration = dur or ""
    
    # Extract population with a small composite (sex + training/athlete + age group)
    population = ""
    if content:
        sex = None
        if re.search(r"\b(male|men|males)\b", content, re.I): sex = "males"
        if re.search(r"\b(female|women|females)\b", content, re.I): sex = "females" if sex is None else sex
        train = None
        if re.search(r"\bathlete[s]?\b", content, re.I): train = "athletes"
        elif re.search(r"\btrained\b", content, re.I): train = "trained"
        elif re.search(r"\buntrained\b", content, re.I): train = "untrained"
        ageg = None
        if re.search(r"\belderly|older adult[s]?\b", content, re.I): ageg = "elderly"
        elif re.search(r"\badult[s]?\b", content, re.I): ageg = "adults"
        bits = [b for b in [train, sex, ageg] if b]
        population = " ".join(bits)
    
    # Calculate enhanced scores
    sample_size_category = categorize_sample_size(sample_size)
    duration_category = categorize_duration(study_duration)
    population_category = categorize_population(population)
    study_design_score = calculate_study_design_score(study_type, sample_size, study_duration)
    
    # Extract author information
    authors = art.get("AuthorList", {}).get("Author", [])
    if isinstance(authors, dict):
        authors = [authors]
    first_author = ""
    author_count = len(authors)
    if authors:
        first_author = f"{authors[0].get('LastName', '')} {authors[0].get('ForeName', '')}".strip()
    
    # Extract MeSH terms
    mesh_terms = []
    mesh_list = rec.get("MedlineCitation", {}).get("MeshHeadingList", {}).get("MeshHeading", [])
    if isinstance(mesh_list, dict):
        mesh_list = [mesh_list]
    for mesh in mesh_list or []:
        if isinstance(mesh, dict):
            mesh_terms.append(mesh.get("DescriptorName", {}).get("#text", ""))
    
    # Extract keywords
    keywords = art.get("KeywordList", {}).get("Keyword", [])
    if isinstance(keywords, dict):
        keywords = [keywords]
    keyword_list = [kw.get("#text", "") for kw in keywords if isinstance(kw, dict)]

    return {
        "id": f"pmid_{pmid}_chunk_0",
        "title": title,
        "doi": doi,
        "pmid": str(pmid) if pmid else None,
        "url_pub": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "journal": journal,
        "year": year if isinstance(year, int) else None,
        "study_type": study_type,
        "study_category": study_category,
        "supplements": ",".join(supplements) if supplements else "",
        "outcomes": ",".join(outcomes) if outcomes else "",
        
        # goal (enhanced)
        "primary_goal": primary_goal,
        
        # Study metadata
        "population": population,
        "sample_size": sample_size,
        "study_duration": study_duration,
        
        # Safety and dosage
        "safety_indicators": safety_data["safety_indicators"],
        "dosage_info": dosage_data["dosage_info"],
        "has_loading_phase": dosage_data["has_loading_phase"],
        "has_maintenance_phase": dosage_data["has_maintenance_phase"],
        "has_side_effects": safety_data["has_side_effects"],
        "has_contraindications": safety_data["has_contraindications"],
        
        # Quality and scoring
        "reliability_score": reliability_score,
        "study_design_score": study_design_score,
        
        # System fields
        "summary": None,
        "content": content.strip(),  # Only store abstract, not full text
        "index_version": INDEX_VERSION
    }

