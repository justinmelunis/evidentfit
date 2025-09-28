import os, re, json, time, argparse, datetime
from dateutil import tz
import httpx, xmltodict

# --- Shared helpers ---
try:
    from evidentfit_shared.foundry_client import embed_texts
    from evidentfit_shared.search_client import ensure_index, upsert_docs, get_doc
except ImportError:
    raise SystemExit("shared/ package not installed; ensure Dockerfile copies shared/ and pip installs -e /opt/shared")

# --- Env ---
INDEX_VERSION = os.getenv("INDEX_VERSION", "v1")
SEARCH_INDEX   = os.getenv("SEARCH_INDEX", "evidentfit-index")
PM_SEARCH_QUERY = os.getenv("PM_SEARCH_QUERY") or \
  '(creatine OR "beta-alanine" OR caffeine OR citrulline OR nitrate OR "nitric oxide" OR HMB OR "branched chain amino acids" OR BCAA OR tribulus OR "d-aspartic acid" OR betaine OR taurine OR carnitine OR ZMA OR glutamine OR CLA OR ecdysterone OR "deer antler") AND (resistance OR "strength" OR "1RM" OR hypertrophy OR "lean mass") NOT ("nitrogen dioxide" OR NO2 OR pollution)'

NCBI_EMAIL = os.getenv("NCBI_EMAIL","you@example.com")
NCBI_API_KEY = os.getenv("NCBI_API_KEY")  # optional
WATERMARK_KEY = os.getenv("WATERMARK_KEY","meta:last_ingest")
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT","10000"))  # Final target
MAX_TEMP_LIMIT = int(os.getenv("MAX_TEMP_LIMIT","15000"))  # Temporary limit during processing

# --- Enhanced maps/heuristics ---
SUPP_KEYWORDS = {
  "creatine": [r"\bcreatine\b"],
  "caffeine": [r"\bcaffeine\b", r"\bcoffee\b"],
  "beta-alanine": [r"\bbeta-?alanine\b"],
  "citrulline": [r"\bcitrulline\b"],
  "nitrate": [r"\bnitrate(s)?\b", r"\bbeet(root)?\b", r"\bnitric oxide\b"],
  "protein": [r"\bwhey\b", r"\bcasein\b", r"\bprotein supplement\b"],
  "hmb": [r"\bhmb\b", r"\b(beta-hydroxy beta-methylbutyrate)\b"],
  "bcaa": [r"\bbcaa(s)?\b", r"\bbranched[- ]chain amino acids\b"],
  "tribulus": [r"\btribulus\b"],
  "d-aspartic-acid": [r"\bd-?aspartic\b"],
  "betaine": [r"\bbetaine\b"],
  "taurine": [r"\btaurine\b"],
  "carnitine": [r"\bcarnitine\b"],
  "zma": [r"\bzma\b"],
  "glutamine": [r"\bglutamine\b"],
  "cla": [r"\bconjugated linoleic acid\b", r"\bCLA\b"],
  "ecdysteroids": [r"\becdyster(one|oid)s?\b", r"\brhaponticum\b", r"\b20-HE\b"],
  "deer-antler": [r"\bdeer antler\b", r"\bIGF-1\b"],
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

def classify_study_type(pub_types):
    s = set([str(pt).lower() for pt in (pub_types or [])])
    if "meta-analysis" in s: return "meta-analysis"
    if "randomized controlled trial" in s or "randomised controlled trial" in s: return "RCT"
    if "crossover studies" in s or "cross-over studies" in s: return "crossover"
    if "cohort studies" in s: return "cohort"
    return "other"

def calculate_reliability_score(rec: dict, dynamic_weights: dict = None) -> float:
    """Calculate reliability score based on study type, sample size, and quality indicators"""
    score = 0.0
    
    # Study type scoring (highest to lowest)
    study_type = classify_study_type(rec.get("MedlineCitation", {}).get("Article", {}).get("PublicationTypeList", {}).get("PublicationType", []))
    if study_type == "meta-analysis": score += 10.0
    elif study_type == "RCT": score += 8.0
    elif study_type == "crossover": score += 6.0
    elif study_type == "cohort": score += 4.0
    else: score += 2.0
    
    # Sample size scoring (extract from abstract if possible)
    abstract = rec.get("MedlineCitation", {}).get("Article", {}).get("Abstract", {})
    if isinstance(abstract, dict):
        ab_text = abstract.get("AbstractText")
        if ab_text:
            import re
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
                if max_n >= 1000: score += 5.0
                elif max_n >= 500: score += 4.0
                elif max_n >= 100: score += 3.0
                elif max_n >= 50: score += 2.0
                elif max_n >= 20: score += 1.0
    
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
    
    if year and year >= 2020: score += 1.0
    elif year and year >= 2015: score += 0.5
    
    # Dynamic supplement diversity scoring based on existing index
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

def _find(text, patterns): return any(re.search(p, text, flags=re.I) for p in patterns)

def extract_supplements(text: str):
    t = text.lower()
    return sorted({slug for slug, pats in SUPP_KEYWORDS.items() if _find(t, pats)})

def extract_outcomes(text: str):
    t = text.lower()
    return sorted({k for k, pats in OUTCOME_MAP.items() if _find(t, pats)})

# Enhanced extraction functions
def extract_goal_specific_outcomes(text: str) -> dict:
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

def extract_safety_indicators(text: str) -> dict:
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

def extract_dosage_info(text: str) -> dict:
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
    if sample_size >= 100: return "large"
    elif sample_size >= 30: return "medium" 
    else: return "small"

def categorize_duration(duration: str) -> str:
    """Categorize study duration"""
    if "year" in duration: return "long_term"
    elif "month" in duration: return "medium_term"
    else: return "short_term"

def categorize_population(population: str) -> str:
    """Categorize study population"""
    if "athlete" in population: return "athletes"
    elif "trained" in population: return "trained"
    elif "untrained" in population: return "untrained"
    elif "elderly" in population: return "elderly"
    else: return "general"

def calculate_study_design_score(study_type: str, sample_size: int, duration: str) -> float:
    """Calculate study design quality score"""
    score = 0.0
    
    # Study type scoring
    if study_type == "meta-analysis": score += 3.0
    elif study_type == "RCT": score += 2.5
    elif study_type == "crossover": score += 2.0
    elif study_type == "cohort": score += 1.5
    else: score += 1.0
    
    # Sample size scoring
    if sample_size >= 100: score += 2.0
    elif sample_size >= 50: score += 1.5
    elif sample_size >= 30: score += 1.0
    else: score += 0.5
    
    # Duration scoring
    if "year" in duration: score += 1.5
    elif "month" in duration: score += 1.0
    else: score += 0.5
    
    return min(score, 10.0)  # Cap at 10

# --- PubMed E-utilities ---
def pubmed_esearch(term: str, mindate: str|None=None, retmax: int=200, retstart:int=0) -> dict:
    params = {"db":"pubmed","retmode":"json","term":term,"retmax":str(retmax),"retstart":str(retstart),"email":NCBI_EMAIL}
    if NCBI_API_KEY: params["api_key"]=NCBI_API_KEY
    if mindate: params.update({"datetype":"pdat","mindate":mindate})  # YYYY/MM/DD
    with httpx.Client(timeout=60) as c:
        r = c.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params)
        r.raise_for_status(); return r.json()

def pubmed_efetch_xml(pmids: list[str]) -> dict:
    params = {"db":"pubmed","retmode":"xml","id":",".join(pmids),"email":NCBI_EMAIL}
    if NCBI_API_KEY: params["api_key"]=NCBI_API_KEY
    with httpx.Client(timeout=120) as c:
        r = c.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=params)
        r.raise_for_status(); return xmltodict.parse(r.text)

def parse_pubmed_article(rec: dict, dynamic_weights: dict = None) -> dict:
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
        content = " ".join([a.get("#text", a) if isinstance(a, dict) else a for a in (ab if isinstance(ab, list) else [ab] if ab else [])])
    else:
        content = ""
    jour = art.get("Journal", {})
    journal = jour.get("ISOAbbreviation") or jour.get("Title") or ""
    year = None
    pubdate = jour.get("JournalIssue", {}).get("PubDate", {})
    for k in ("Year","MedlineDate"):
        if pubdate.get(k):
            try: year = int(str(pubdate.get(k))[:4])
            except: pass
            break
    doi = None
    ids = rec.get("PubmedData", {}).get("ArticleIdList", {}).get("ArticleId", [])
    if isinstance(ids, dict): ids = [ids]
    for idn in ids or []:
        if idn.get("@IdType") == "doi": doi = idn.get("#text"); break
    pubtypes = art.get("PublicationTypeList", {}).get("PublicationType", [])
    if isinstance(pubtypes, dict): pubtypes = [pubtypes]
    pubtypes = [pt.get("#text","") if isinstance(pt, dict) else str(pt) for pt in pubtypes]
    study_type = classify_study_type(pubtypes)

    # Calculate reliability score with dynamic weights
    reliability_score = calculate_reliability_score(rec, dynamic_weights)

    text_for_tags = f"{title}\n{content}"
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
    if isinstance(authors, dict): authors = [authors]
    first_author = ""
    author_count = len(authors)
    if authors:
        first_author = f"{authors[0].get('LastName', '')} {authors[0].get('ForeName', '')}".strip()
    
    # Extract MeSH terms
    mesh_terms = []
    mesh_list = rec.get("MedlineCitation", {}).get("MeshHeadingList", {}).get("MeshHeading", [])
    if isinstance(mesh_list, dict): mesh_list = [mesh_list]
    for mesh in mesh_list or []:
        if isinstance(mesh, dict):
            mesh_terms.append(mesh.get("DescriptorName", {}).get("#text", ""))
    
    # Extract keywords
    keywords = art.get("KeywordList", {}).get("Keyword", [])
    if isinstance(keywords, dict): keywords = [keywords]
    keyword_list = [kw.get("#text", "") for kw in keywords if isinstance(kw, dict)]

    return {
        "id": f"pmid_{pmid}_chunk_0",
        "title": title,
        "doi": doi,
        "pmid": str(pmid) if pmid else None,
        "url_pub": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "journal": journal,
        "year": year if isinstance(year,int) else None,
        "study_type": study_type,
        "supplements": ",".join(supplements) if supplements else "",
        "outcomes": ",".join(outcomes) if outcomes else "",
        
        # Enhanced goal-specific outcomes
        "primary_goal": goal_data["primary_goal"],
        "hypertrophy_outcomes": goal_data["hypertrophy_outcomes"],
        "weight_loss_outcomes": goal_data["weight_loss_outcomes"],
        "strength_outcomes": goal_data["strength_outcomes"],
        "performance_outcomes": goal_data["performance_outcomes"],
        
        # Study metadata
        "population": population,
        "sample_size": sample_size,
        "study_duration": study_duration,
        "sample_size_category": sample_size_category,
        "duration_category": duration_category,
        "population_category": population_category,
        
        # Safety and dosage
        "safety_indicators": safety_data["safety_indicators"],
        "dosage_info": dosage_data["dosage_info"],
        "has_loading_phase": dosage_data["has_loading_phase"],
        "has_maintenance_phase": dosage_data["has_maintenance_phase"],
        "has_side_effects": safety_data["has_side_effects"],
        "has_contraindications": safety_data["has_contraindications"],
        
        # Author and credibility
        "first_author": first_author,
        "author_count": author_count,
        "funding_sources": "",  # TODO: Extract from funding info
        
        # Categorization
        "mesh_terms": ",".join(mesh_terms),
        "keywords": ",".join(keyword_list),
        
        # Quality and scoring
        "reliability_score": reliability_score,
        "study_design_score": study_design_score,
        
        # System fields
        "summary": None,
        "content": content.strip(),  # Only store abstract, not full text
        "content_vector": "",  # Will be filled during processing
        "index_version": INDEX_VERSION
    }

def analyze_existing_supplements():
    """Analyze existing index to see supplement distribution and adjust scoring"""
    try:
        from evidentfit_shared.search_client import search_docs
        
        # Search for all documents to analyze supplement distribution
        results = search_docs("*", top=1000)  # Get a sample of existing docs
        
        supplement_counts = {}
        total_docs = len(results.get("value", []))
        
        for doc in results.get("value", []):
            supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
            for supp in supplements:
                supp = supp.strip()
                if supp:
                    supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        print(f"Found {total_docs} existing documents")
        print(f"Current supplement distribution: {dict(sorted(supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10])}")
        
        return supplement_counts, total_docs
    except Exception as e:
        print(f"Could not analyze existing supplements: {e}")
        return {}, 0

def get_dynamic_scoring_weights(existing_counts: dict, total_docs: int):
    """Generate dynamic scoring weights based on existing supplement distribution"""
    if total_docs == 0:
        # No existing data, use default weights
        return {
            "rare_supplements": {"tribulus": 3.0, "d-aspartic-acid": 3.0, "deer-antler": 3.0, 
                               "ecdysteroids": 3.0, "betaine": 2.5, "taurine": 2.5, "carnitine": 2.0,
                               "zma": 2.0, "glutamine": 1.5, "cla": 1.5, "hmb": 1.0},
            "medium_supplements": {"citrulline": 1.0, "nitrate": 1.0, "beta-alanine": 0.5},
            "creatine_penalty": -1.0
        }
    
    # Calculate relative representation
    weights = {}
    for supp, count in existing_counts.items():
        representation = count / total_docs
        if representation > 0.3:  # Over-represented (>30%)
            weights[supp] = -2.0
        elif representation > 0.15:  # Well-represented (15-30%)
            weights[supp] = -1.0
        elif representation > 0.05:  # Adequately represented (5-15%)
            weights[supp] = 0.0
        else:  # Under-represented (<5%)
            weights[supp] = 2.0
    
    print(f"Dynamic scoring weights: {dict(sorted(weights.items(), key=lambda x: x[1], reverse=True)[:10])}")
    return weights

def run_ingest(mode: str):
    ensure_index(vector_dim=1536)

    # Analyze existing supplement distribution
    existing_counts, total_docs = analyze_existing_supplements()
    dynamic_weights = get_dynamic_scoring_weights(existing_counts, total_docs)

    # Watermark → mindate
    mindate = None
    wm = get_doc(WATERMARK_KEY)
    if mode == "bootstrap":
        mindate = "2000/01/01"
    else:
        if wm and wm.get("summary"):
            try:
                meta = json.loads(wm["summary"])
                iso = meta.get("last_ingest_iso")
                if iso:
                    dt = datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
                    mindate = dt.strftime("%Y/%m/%d")
            except Exception:
                mindate = None

    # Dynamic rolling window system: Maintain 10,000, temporarily go to 15,000
    if mode == "bootstrap":
        # Bootstrap: Get large batch, filter to best 10,000
        ids, retstart = [], 0
        search_limit = MAX_TEMP_LIMIT * 2  # Get 2x more to filter down
        while len(ids) < search_limit:
            batch = pubmed_esearch(PM_SEARCH_QUERY, mindate=mindate, retmax=200, retstart=retstart)
            idlist = batch.get("esearchresult", {}).get("idlist", [])
            if not idlist: break
            ids.extend(idlist)
            retstart += len(idlist)
            if retstart >= int(batch["esearchresult"].get("count","0")): break
            time.sleep(0.34)
        
        print(f"Bootstrap: Found {len(ids)} PMIDs (will filter to best {INGEST_LIMIT})")
    else:
        # Monthly: Get new papers since last run
        ids, retstart = [], 0
        while len(ids) < 3000:  # Reasonable limit for monthly updates
            batch = pubmed_esearch(PM_SEARCH_QUERY, mindate=mindate, retmax=200, retstart=retstart)
            idlist = batch.get("esearchresult", {}).get("idlist", [])
            if not idlist: break
            ids.extend(idlist)
            retstart += len(idlist)
            if retstart >= int(batch["esearchresult"].get("count","0")): break
            time.sleep(0.34)
        
        print(f"Monthly: Found {len(ids)} new PMIDs since last run")

    if not ids:
        print("No new PubMed IDs."); return

    # Fetch → parse → score → filter → upsert
    all_docs = []
    total_processed = 0
    
    for i in range(0, len(ids), 200):
        pid_batch = ids[i:i+200]
        xml = pubmed_efetch_xml(pid_batch)
        arts = xml.get("PubmedArticleSet", {}).get("PubmedArticle", [])
        if isinstance(arts, dict): arts = [arts]

        for rec in arts:
            d = parse_pubmed_article(rec, dynamic_weights)
            if not d["title"] and not d["content"]: continue
            all_docs.append(d)
            total_processed += 1
            
            if total_processed % 100 == 0:
                print(f"Processed {total_processed} papers...")

    # Dynamic rolling window system: Maintain 10,000, temporarily go to 15,000
    print(f"Processing {len(all_docs)} papers with dynamic rolling window system...")
    
    if mode == "bootstrap":
        # Bootstrap: Get best 10,000 from large batch
        print("Bootstrap mode: Selecting best 10,000 papers from all available...")
        
        # Score all papers with diversity weighting
        all_docs.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)
        
        # Apply diversity filtering to get balanced representation
        selected_docs = []
        supplement_counts = {}
        max_per_supplement = INGEST_LIMIT // 20  # Max 5% per supplement (500 papers)
        
        for doc in all_docs:
            if len(selected_docs) >= INGEST_LIMIT:
                break
                
            supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
            supplements = [s.strip() for s in supplements if s.strip()]
            
            # Check if we can add this paper without exceeding limits
            can_add = True
            for supp in supplements:
                if supplement_counts.get(supp, 0) >= max_per_supplement:
                    can_add = False
                    break
            
            if can_add:
                selected_docs.append(doc)
                for supp in supplements:
                    supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        # Fill remaining slots with highest scoring papers
        remaining_slots = INGEST_LIMIT - len(selected_docs)
        if remaining_slots > 0:
            used_ids = {doc["id"] for doc in selected_docs}
            for doc in all_docs:
                if doc["id"] not in used_ids and remaining_slots > 0:
                    selected_docs.append(doc)
                    remaining_slots -= 1
        
        top_docs = selected_docs
        
    else:
        # Monthly: Dynamic rolling window - merge, temporarily go to 15,000, then trim to 10,000
        print("Monthly mode: Dynamic rolling window with temporary expansion...")
        
        # Get existing papers from index
        try:
            existing_results = search_docs("*", top=MAX_TEMP_LIMIT)  # Get up to 15,000 existing
            existing_docs = []
            for doc in existing_results.get("value", []):
                # Convert existing doc to same format
                existing_doc = {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "reliability_score": doc.get("reliability_score", 0),
                    "supplements": doc.get("supplements", ""),
                    "year": doc.get("year"),
                    "study_type": doc.get("study_type")
                }
                existing_docs.append(existing_doc)
            
            print(f"Found {len(existing_docs)} existing papers in index")
            
            # Combine existing and new papers
            combined_docs = existing_docs + all_docs
            
            # Remove duplicates (by ID)
            seen_ids = set()
            unique_docs = []
            for doc in combined_docs:
                if doc["id"] not in seen_ids:
                    unique_docs.append(doc)
                    seen_ids.add(doc["id"])
            
            print(f"Combined unique papers: {len(unique_docs)}")
            
            # Sort by reliability score
            unique_docs.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)
            
            # If we have more than 15,000, temporarily keep top 15,000 for processing
            if len(unique_docs) > MAX_TEMP_LIMIT:
                print(f"Temporarily keeping top {MAX_TEMP_LIMIT} papers for processing...")
                temp_docs = unique_docs[:MAX_TEMP_LIMIT]
            else:
                temp_docs = unique_docs
            
            # Apply diversity filtering to get balanced representation
            selected_docs = []
            supplement_counts = {}
            max_per_supplement = INGEST_LIMIT // 20  # Max 5% per supplement (500 papers)
            
            for doc in temp_docs:
                if len(selected_docs) >= INGEST_LIMIT:
                    break
                    
                supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
                supplements = [s.strip() for s in supplements if s.strip()]
                
                # Check if we can add this paper without exceeding limits
                can_add = True
                for supp in supplements:
                    if supplement_counts.get(supp, 0) >= max_per_supplement:
                        can_add = False
                        break
                
                if can_add:
                    selected_docs.append(doc)
                    for supp in supplements:
                        supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
            
            # Fill remaining slots with highest scoring papers
            remaining_slots = INGEST_LIMIT - len(selected_docs)
            if remaining_slots > 0:
                used_ids = {doc["id"] for doc in selected_docs}
                for doc in temp_docs:
                    if doc["id"] not in used_ids and remaining_slots > 0:
                        selected_docs.append(doc)
                        remaining_slots -= 1
            
            top_docs = selected_docs
            print(f"Trimmed from {len(temp_docs)} to {len(top_docs)} papers")
            
        except Exception as e:
            print(f"Could not merge with existing index: {e}")
            print("Falling back to bootstrap mode...")
            # Fallback to bootstrap logic
            all_docs.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)
            top_docs = all_docs[:INGEST_LIMIT]
    
    # Final analysis
    final_supplement_counts = {}
    for doc in top_docs:
        supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
        for supp in supplements:
            supp = supp.strip()
            if supp:
                final_supplement_counts[supp] = final_supplement_counts.get(supp, 0) + 1
    
    print(f"Final selection: {len(top_docs)} papers")
    print(f"Final supplement distribution: {dict(sorted(final_supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10])}")
    print(f"Top reliability scores: {[d.get('reliability_score', 0) for d in top_docs[:5]]}")
    
    # Process in batches
    total = 0
    batch_size = 50  # Larger batches since we're not doing embeddings
    for i in range(0, len(top_docs), batch_size):
        batch_docs = top_docs[i:i+batch_size]
        
        try:
            upsert_docs(batch_docs)
            total += len(batch_docs)
            print(f"Upserted {len(batch_docs)} docs (total {total})")
            
            # Small delay between batches
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing batch {i//batch_size + 1}: {e}")
            continue

    # Update watermark
    now_iso = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00","Z")
    wm_doc = {
        "id": WATERMARK_KEY.replace(":", "_"),
        "title": "watermark",
        "summary": json.dumps({"last_ingest_iso": now_iso}),
        "year": int(now_iso[:4]),
        "index_version": INDEX_VERSION
    }
    upsert_docs([wm_doc])
    print(f"Watermark updated to {now_iso}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bootstrap","monthly"], default="monthly")
    args = ap.parse_args()
    run_ingest(args.mode)
