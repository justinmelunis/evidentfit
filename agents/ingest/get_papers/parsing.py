"""
PubMed article parsing and scoring

Handles parsing of PubMed XML, study classification, and reliability scoring.
No LLM calls - pure rule-based extraction and scoring.
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any

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
    
    "nitrate": [r"\bnitrate(s)?\b", r"\bbeet(root)?\b", r"\bnitric oxide\b", r"\bNO3\b"],
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
    "nitric-oxide": [r"\bnitric oxide\b", r"\bNO\b"],
}

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
    "endurance": [r"\bendurance\b", r"\bVO2\b", r"\btime to exhaustion\b"],
    "recovery": [r"\brecovery\b", r"\bDOMS\b", r"\bsoreness\b"]
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


def classify_study_type(pub_types: List[str]) -> str:
    """
    Classify study type based on publication types
    
    Args:
        pub_types: List of publication type strings
        
    Returns:
        Study type classification
    """
    s = set([str(pt).lower() for pt in (pub_types or [])])
    if "meta-analysis" in s:
        return "meta-analysis"
    if "randomized controlled trial" in s or "randomised controlled trial" in s:
        return "RCT"
    if "crossover studies" in s or "cross-over studies" in s:
        return "crossover"
    if "cohort studies" in s:
        return "cohort"
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
    
    return score


def _find(text: str, patterns: List[str]) -> bool:
    """Check if any pattern matches in text"""
    return any(re.search(p, text, flags=re.I) for p in patterns)


def extract_supplements(text: str) -> List[str]:
    """Extract supplement mentions from text"""
    t = text.lower()
    return sorted({slug for slug, pats in SUPP_KEYWORDS.items() if _find(t, pats)})


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
    
    # Performance
    performance_outcomes = []
    for outcome, patterns in PERFORMANCE_OUTCOMES.items():
        if any(re.search(p, text_lower, re.I) for p in patterns):
            performance_outcomes.append(outcome)
    
    # Determine primary goal
    goal_scores = {
        "muscle_gain": len(hypertrophy_outcomes),
        "weight_loss": len(weight_loss_outcomes),
        "strength": len(strength_outcomes),
        "performance": len(performance_outcomes)
    }
    primary_goal = max(goal_scores, key=goal_scores.get) if any(goal_scores.values()) else "general"
    
    return {
        "primary_goal": primary_goal,
        "hypertrophy_outcomes": ",".join(hypertrophy_outcomes),
        "weight_loss_outcomes": ",".join(weight_loss_outcomes),
        "strength_outcomes": ",".join(strength_outcomes),
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


def extract_dosage_info(text: str) -> Dict[str, Any]:
    """Extract dosage and timing information"""
    dosage_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:g|mg|mcg|grams?|milligrams?)\s*(?:per day|daily|/day)',
        r'(\d+(?:\.\d+)?)\s*(?:g|mg|mcg|grams?|milligrams?)\s*(?:pre|post|before|after)',
        r'(\d+(?:\.\d+)?)\s*(?:g|mg|mcg|grams?|milligrams?)\s*(?:loading|maintenance)'
    ]
    
    dosages = []
    for pattern in dosage_patterns:
        matches = re.findall(pattern, text, re.I)
        dosages.extend(matches)
    
    return {
        "dosage_info": ",".join(dosages),
        "has_loading_phase": "loading" in text.lower(),
        "has_maintenance_phase": "maintenance" in text.lower()
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
    """Categorize study duration"""
    if "year" in duration:
        return "long_term"
    elif "month" in duration:
        return "medium_term"
    else:
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
    study_type = classify_study_type(pubtypes)

    # Calculate reliability score with dynamic weights
    reliability_score = calculate_reliability_score(rec, dynamic_weights)

    text_for_tags = f"{title}\n{content}"
    
    # Check relevance - skip irrelevant studies early
    if not is_relevant_human_study(title, content):
        return None  # Skip this paper
    
    supplements = extract_supplements(text_for_tags)
    outcomes = extract_outcomes(text_for_tags)
    
    # Enhanced metadata extraction
    goal_data = extract_goal_specific_outcomes(text_for_tags)
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
    
    # Extract study duration from content
    study_duration = ""
    if content:
        duration_patterns = [
            r'(\d+)\s*(?:weeks?|months?|days?|years?)',
            r'(?:for|over|during)\s*(\d+)\s*(?:weeks?|months?|days?|years?)'
        ]
        for pattern in duration_patterns:
            matches = re.findall(pattern, content, re.I)
            if matches:
                study_duration = matches[0] + " " + matches[1] if len(matches) > 1 else matches[0]
                break
    
    # Extract population info
    population = ""
    if content:
        pop_patterns = [
            r'\b(?:men|women|males?|females?|adults?|elderly|athletes?|trained|untrained)\b'
        ]
        for pattern in pop_patterns:
            matches = re.findall(pattern, content, re.I)
            if matches:
                population = matches[0]
                break
    
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
        "supplements": ",".join(supplements) if supplements else "",
        "outcomes": ",".join(outcomes) if outcomes else "",
        
        # Enhanced goal-specific outcomes
        "primary_goal": goal_data["primary_goal"],
        
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

