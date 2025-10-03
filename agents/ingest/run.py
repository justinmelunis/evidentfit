import os, re, json, time, argparse, datetime, logging, math
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

# --- Logging Setup ---
def setup_logging():
    """Setup comprehensive logging to both console and file"""
    log_level = os.getenv("LOG_LEVEL", "info").upper()
    log_level = getattr(logging, log_level, logging.INFO)
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/ingest_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()  # Also print to console
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized - Level: {log_level}, File: {log_file}")
    return logger

# Initialize logging
logger = setup_logging()
PM_SEARCH_QUERY = os.getenv("PM_SEARCH_QUERY") or \
  '(creatine OR "beta-alanine" OR caffeine OR citrulline OR nitrate OR "nitric oxide" OR HMB OR "branched chain amino acids" OR BCAA OR tribulus OR "d-aspartic acid" OR betaine OR taurine OR carnitine OR ZMA OR glutamine OR CLA OR ecdysterone OR "deer antler" OR "whey protein" OR "protein supplementation") AND (resistance OR "strength training" OR "1RM" OR hypertrophy OR "lean mass" OR "muscle mass" OR "exercise" OR "athletic performance") AND (humans[MeSH] OR adult OR adults OR participants OR subjects OR volunteers OR athletes) NOT ("nitrogen dioxide" OR NO2 OR pollution OR "cardiac hypertrophy" OR "ventricular hypertrophy" OR "fish" OR "rat" OR "mice" OR "mouse" OR "in vitro" OR "cell culture" OR animals[MeSH])'

NCBI_EMAIL = os.getenv("NCBI_EMAIL","you@example.com")
NCBI_API_KEY = os.getenv("NCBI_API_KEY")  # optional
WATERMARK_KEY = os.getenv("WATERMARK_KEY","meta:last_ingest")
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT","10000"))  # Final target (~47MB, fits 50MB limit with buffer)
MAX_TEMP_LIMIT = int(os.getenv("MAX_TEMP_LIMIT","20000"))  # Temporary limit during processing

# --- Multi-Query Strategy ---
# Supplement-specific PubMed queries for comprehensive coverage
SUPPLEMENT_QUERIES = {
    # Core performance supplements - simplified queries that actually work
    "creatine": 'creatine AND (exercise OR training OR performance OR strength OR muscle) AND humans[MeSH]',
    "caffeine": 'caffeine AND (exercise OR training OR performance OR endurance OR strength) AND humans[MeSH]',
    "beta-alanine": '"beta-alanine" AND (exercise OR training OR performance OR muscle OR fatigue) AND humans[MeSH]',
    "protein": '"protein supplementation" AND (exercise OR training OR muscle OR hypertrophy OR strength) AND humans[MeSH]',
    
    # Nitric oxide boosters
    "citrulline": 'citrulline AND (exercise OR training OR performance) AND humans[MeSH]',
    "nitrate": '(nitrate OR beetroot) AND (exercise OR training OR performance OR endurance) AND humans[MeSH] NOT pollution',
    "arginine": 'arginine AND (exercise OR training OR performance) AND humans[MeSH]',
    
    # Amino acids and derivatives
    "hmb": 'HMB AND (exercise OR training OR muscle OR strength OR recovery) AND humans[MeSH]',
    "bcaa": 'BCAA AND (exercise OR training OR muscle OR recovery OR endurance) AND humans[MeSH]',
    "leucine": 'leucine AND (exercise OR training OR muscle) AND humans[MeSH]',
    "glutamine": 'glutamine AND (exercise OR training OR recovery OR muscle) AND humans[MeSH]',
    
    # Other performance compounds
    "betaine": 'betaine AND (exercise OR training OR performance OR strength OR power) AND humans[MeSH]',
    "taurine": 'taurine AND (exercise OR training OR performance OR endurance OR muscle) AND humans[MeSH]',
    "carnitine": 'carnitine AND (exercise OR training OR performance) AND humans[MeSH]',
    
    # Hormonal/anabolic
    "tribulus": 'tribulus AND (exercise OR training OR testosterone OR performance OR strength) AND humans[MeSH]',
    "d-aspartic-acid": '"d-aspartic acid" AND (exercise OR training OR testosterone OR hormone OR strength) AND humans[MeSH]',
    
    # Essential nutrients
    "omega-3": '"omega-3" AND (exercise OR training OR performance OR recovery OR inflammation) AND humans[MeSH]',
    "vitamin-d": '"vitamin D" AND (exercise OR training OR performance OR muscle OR strength) AND humans[MeSH]',
    "magnesium": 'magnesium AND (exercise OR training OR performance OR muscle OR recovery) AND humans[MeSH]',
    "iron": 'iron AND (exercise OR training OR performance OR endurance OR fatigue) AND humans[MeSH]',
    
    # Specialized compounds
    "sodium-bicarbonate": '"sodium bicarbonate" AND (exercise OR training OR performance) AND humans[MeSH]',
    "glycerol": 'glycerol AND (exercise OR training OR performance OR hydration OR endurance) AND humans[MeSH]',
    "curcumin": 'curcumin AND (exercise OR training OR performance OR inflammation OR recovery) AND humans[MeSH]',
    "quercetin": 'quercetin AND (exercise OR training OR performance OR antioxidant OR endurance) AND humans[MeSH]',
    
    # Adaptogens and herbs
    "ashwagandha": 'ashwagandha AND (exercise OR training OR performance OR stress OR strength) AND humans[MeSH]',
    "rhodiola": 'rhodiola AND (exercise OR training OR performance OR fatigue OR endurance OR stress) AND humans[MeSH]',
    "cordyceps": 'cordyceps AND (exercise OR training OR performance OR endurance) AND humans[MeSH]',
    
    # Other compounds
    "tyrosine": 'tyrosine AND (exercise OR training OR performance OR stress OR cognitive OR focus) AND humans[MeSH]',
    "cla": '"conjugated linoleic acid" AND (exercise OR training OR body composition) AND humans[MeSH]',
    "zma": 'ZMA AND (exercise OR training OR recovery OR sleep OR testosterone) AND humans[MeSH]',
}

# NOTE: No per-supplement limits - we get ALL available papers for each supplement

# Local staging configuration
LOCAL_STAGING_DIR = os.getenv("LOCAL_STAGING_DIR", "./staging")
LOCAL_PAPERS_DB = os.path.join(LOCAL_STAGING_DIR, "papers_staging.jsonl")
LOCAL_METADATA_FILE = os.path.join(LOCAL_STAGING_DIR, "staging_metadata.json")

# Conservative global safety limit (much higher than expected need)
MAX_TOTAL_PAPERS = 200000   # Global safety net (2x our highest estimate)
AZURE_FINAL_LIMIT = 15000   # Final upload to Azure (only real constraint)

# Multi-query will get ALL available papers for each supplement (up to global limit)
logger.info(f"Multi-query: Comprehensive coverage for {len(SUPPLEMENT_QUERIES)} supplements (up to {MAX_TOTAL_PAPERS:,} global limit)")

# --- Enhanced maps/heuristics ---
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
    
    # Enhanced study type scoring (prioritize high-quality designs for 15K papers)
    study_type = classify_study_type(rec.get("MedlineCitation", {}).get("Article", {}).get("PublicationTypeList", {}).get("PublicationType", []))
    if study_type == "meta-analysis": score += 12.0  # Highest priority
    elif study_type == "RCT": score += 10.0  # Very high priority
    elif study_type == "crossover": score += 7.0  # Good priority
    elif study_type == "cohort": score += 4.0  # Medium priority
    else: score += 1.0  # Lower priority for other designs
    
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

# --- Local Staging Functions ---
def ensure_staging_dir():
    """Ensure local staging directory exists"""
    os.makedirs(LOCAL_STAGING_DIR, exist_ok=True)
    print(f"Staging directory: {LOCAL_STAGING_DIR}")

def save_paper_to_staging(paper_data: dict):
    """Save a paper to local staging file (JSONL format)"""
    ensure_staging_dir()
    with open(LOCAL_PAPERS_DB, 'a', encoding='utf-8') as f:
        f.write(json.dumps(paper_data) + '\n')

def load_papers_from_staging() -> list:
    """Load all papers from local staging"""
    if not os.path.exists(LOCAL_PAPERS_DB):
        return []
    
    papers = []
    with open(LOCAL_PAPERS_DB, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                papers.append(json.loads(line))
    
    return papers

def save_staging_metadata(metadata: dict):
    """Save staging metadata (counts, timestamps, etc.)"""
    ensure_staging_dir()
    with open(LOCAL_METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

def load_staging_metadata() -> dict:
    """Load staging metadata"""
    if not os.path.exists(LOCAL_METADATA_FILE):
        return {}
    
    with open(LOCAL_METADATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def clear_staging():
    """Clear local staging files"""
    if os.path.exists(LOCAL_PAPERS_DB):
        os.remove(LOCAL_PAPERS_DB)
    if os.path.exists(LOCAL_METADATA_FILE):
        os.remove(LOCAL_METADATA_FILE)
    print("Staging files cleared")

def get_staging_stats() -> dict:
    """Get statistics about staged papers"""
    papers = load_papers_from_staging()
    
    if not papers:
        return {"total": 0, "supplements": {}, "quality_distribution": {}}
    
    supplement_counts = {}
    quality_counts = {"4.0+": 0, "3.0-3.9": 0, "2.0-2.9": 0, "<2.0": 0}
    
    for paper in papers:
        # Count supplements
        supplements = paper.get('supplements', [])
        if isinstance(supplements, str):
            supplements = supplements.split(',')
        
        for supp in supplements:
            supp = supp.strip()
            supplement_counts[supp] = supplement_counts.get(supp, 0) + 1
        
        # Count quality distribution
        quality = paper.get('reliability_score', 0)
        if quality >= 4.0:
            quality_counts["4.0+"] += 1
        elif quality >= 3.0:
            quality_counts["3.0-3.9"] += 1
        elif quality >= 2.0:
            quality_counts["2.0-2.9"] += 1
        else:
            quality_counts["<2.0"] += 1
    
    return {
        "total": len(papers),
        "supplements": supplement_counts,
        "quality_distribution": quality_counts
    }

# --- PubMed E-utilities ---
def search_supplement_with_chunking(supplement: str, query: str, mindate: str|None=None) -> list:
    """
    Search for a supplement using dynamic chunking to bypass PubMed's 10K limit.
    
    If we hit exactly 9,999 papers (the 10K limit), we automatically switch to chunking
    to ensure we capture all available papers.
    
    Args:
        supplement: Supplement name for logging
        query: PubMed search query
        mindate: Minimum publication date (YYYY/MM/DD format)
        
    Returns:
        List of PMIDs for this supplement
    """
    # First, get total count to see if we need chunking
    try:
        initial_batch = pubmed_esearch(query, mindate=mindate, retmax=1, retstart=0)
        total_count = int(initial_batch.get("esearchresult", {}).get("count", "0"))
        
        if total_count < 9999:
            # Simple case - can get all results in one go
            logger.info(f"  {supplement}: {total_count:,} papers (single query - no chunking needed)")
            pmids = search_supplement_simple(query, mindate)
            
            # Check if simple search hit the 9,999 limit and switched to chunking
            if len(pmids) == 9999:
                logger.warning(f"  {supplement}: DYNAMIC CHUNKING TRIGGERED - Simple search hit 9,999 limit during execution")
                logger.warning(f"  {supplement}: Switching to chunking to capture ALL papers beyond 10K limit")
                return search_supplement_chunked(query, mindate or "1990/01/01", total_count)
            else:
                logger.info(f"  {supplement}: Simple search completed successfully - {len(pmids):,} papers retrieved")
                return pmids
        else:
            # Need chunking (either exactly 9,999 or more)
            if total_count == 9999:
                logger.warning(f"  {supplement}: DYNAMIC CHUNKING TRIGGERED - {total_count:,} papers (exactly hit 10K limit)")
                logger.warning(f"  {supplement}: Using chunking to ensure complete coverage beyond PubMed's 10K limit")
            else:
                logger.info(f"  {supplement}: {total_count:,} papers (over 10K limit, using date chunking)")
            return search_supplement_chunked(query, mindate or "1990/01/01", total_count)
            
    except Exception as e:
        logger.error(f"  Error getting count for {supplement}: {e}")
        return []

def search_supplement_simple(query: str, mindate: str|None=None) -> list:
    """Simple search for supplements with <10K results."""
    pmids = []
    retstart = 0
    
    while True:
        try:
            batch = pubmed_esearch(query, mindate=mindate, retmax=200, retstart=retstart)
            idlist = batch.get("esearchresult", {}).get("idlist", [])
            
            if not idlist:
                break
                
            pmids.extend(idlist)
            retstart += len(idlist)
            
            # Check if we've reached the end
            total_count = int(batch.get("esearchresult", {}).get("count", "0"))
            if retstart >= total_count:
                break
            
            # Dynamic chunking: if we hit exactly 9,999 results, switch to chunking
            if total_count == 9999 and retstart >= 9999:
                logger.warning(f"    DYNAMIC CHUNKING DETECTED - Hit 9,999 paper limit during simple search")
                logger.warning(f"    Returning {len(pmids):,} papers so far, caller will switch to chunking")
                # Return what we have so far, chunking will be handled by caller
                return pmids
                
            time.sleep(1.0)  # Rate limiting - 1 second between requests
            
        except Exception as e:
            logger.error(f"    Error in simple search: {e}")
            break
    
    return pmids

def search_supplement_chunked(query: str, start_date: str, total_count: int, recursion_depth: int = 0) -> list:
    """Search using date-based chunks to bypass 10K limit."""
    from datetime import datetime, timedelta
    
    # Prevent infinite recursion
    if recursion_depth >= 3:
        logger.warning(f"    Maximum recursion depth reached ({recursion_depth}), stopping chunking")
        return []
    
    all_pmids = []
    
    # Create date ranges from start_date to present
    start_dt = datetime.strptime(start_date, "%Y/%m/%d")
    end_dt = datetime.now()
    
    # Calculate chunk size in years to aim for ~8K results per chunk
    years_total = (end_dt - start_dt).days / 365.25
    target_per_chunk = 8000  # Stay well under 10K limit
    estimated_chunks = max(1, math.ceil(total_count / target_per_chunk))
    years_per_chunk = max(1, years_total / estimated_chunks)
    
    logger.info(f"    DYNAMIC CHUNKING: Splitting into ~{estimated_chunks} date ranges ({years_per_chunk:.1f} years each)")
    logger.info(f"    Target: {target_per_chunk:,} papers per chunk (staying under 10K limit)")
    if recursion_depth > 0:
        logger.info(f"    RECURSIVE CHUNKING: Depth {recursion_depth} (max 3)")
    
    current_dt = start_dt
    chunk_num = 1
    
    while current_dt < end_dt:
        # Calculate end of this chunk
        chunk_end_dt = min(current_dt + timedelta(days=years_per_chunk * 365.25), end_dt)
        
        # Format dates for PubMed
        chunk_start = current_dt.strftime("%Y/%m/%d")
        chunk_end = chunk_end_dt.strftime("%Y/%m/%d")
        
        logger.info(f"    CHUNK {chunk_num}: {chunk_start} to {chunk_end}")
        
        # Search this date range
        chunk_pmids = []
        retstart = 0
        
        while True:
            try:
                # Add date range to query
                batch = pubmed_esearch(query, mindate=chunk_start, maxdate=chunk_end, retmax=200, retstart=retstart)
                idlist = batch.get("esearchresult", {}).get("idlist", [])
                
                if not idlist:
                    break
                    
                chunk_pmids.extend(idlist)
                retstart += len(idlist)
                
                # Check if we've reached the end of this chunk
                chunk_total = int(batch.get("esearchresult", {}).get("count", "0"))
                if retstart >= chunk_total:
                    break
                
                # Check if this chunk hit the 9,999 limit (needs recursive chunking)
                if retstart >= 9999 and chunk_total > 9999:
                    logger.warning(f"      CHUNK {chunk_num} HIT 9,999 LIMIT: {chunk_total:,} total papers in this date range")
                    logger.warning(f"      Recursively chunking this date range: {chunk_start} to {chunk_end}")
                    
                    # Recursively chunk this date range
                    recursive_pmids = search_supplement_chunked(
                        query, 
                        chunk_start, 
                        chunk_total,
                        recursion_depth + 1
                    )
                    chunk_pmids.extend(recursive_pmids)
                    logger.info(f"      Recursive chunking complete: {len(recursive_pmids):,} additional papers")
                    break
                    
                time.sleep(1.0)  # Rate limiting - 1 second between requests
                
            except Exception as e:
                logger.error(f"      Error in chunk {chunk_num}: {e}")
                break
        
        logger.info(f"      CHUNK {chunk_num} COMPLETE: {len(chunk_pmids):,} papers retrieved")
        all_pmids.extend(chunk_pmids)
        
        # Move to next chunk
        current_dt = chunk_end_dt + timedelta(days=1)
        chunk_num += 1
        
        # Safety limit
        if chunk_num > 20:  # Don't create too many chunks
            logger.warning(f"      Reached chunk limit, stopping")
            break
    
    # Remove duplicates while preserving order
    unique_pmids = []
    seen = set()
    for pmid in all_pmids:
        if pmid not in seen:
            unique_pmids.append(pmid)
            seen.add(pmid)
    
    logger.info(f"    DYNAMIC CHUNKING COMPLETE: {len(unique_pmids):,} unique PMIDs (deduplicated across chunks)")
    return unique_pmids

def multi_supplement_search(mindate: str|None=None) -> list:
    """
    Run multiple supplement-specific searches to get comprehensive coverage.
    Uses date-based chunking to bypass PubMed's 10K limit.
    
    Args:
        mindate: Minimum publication date (YYYY/MM/DD format)
        
    Returns:
        List of unique PMIDs from all supplement searches
    """
    all_pmids = set()
    search_results = {}
    
    logger.info(f"Running comprehensive multi-supplement search for {len(SUPPLEMENT_QUERIES)} supplements...")
    logger.info(f"Using date-based chunking to bypass PubMed 10K limit")
    logger.info(f"Global limit: {MAX_TOTAL_PAPERS:,} papers")
    
    for supplement, query in SUPPLEMENT_QUERIES.items():
        # Check global limit
        if len(all_pmids) >= MAX_TOTAL_PAPERS:
            logger.warning(f"⚠️  Reached global limit of {MAX_TOTAL_PAPERS:,} papers. Stopping search.")
            break
            
        logger.info(f"Searching {supplement}:")
        
        # Use chunking-aware search
        pmids = search_supplement_with_chunking(supplement, query, mindate)
        
        # Add unique PMIDs (respecting global limit)
        unique_pmids = []
        for pmid in pmids:
            if pmid not in all_pmids and len(all_pmids) < MAX_TOTAL_PAPERS:
                unique_pmids.append(pmid)
                all_pmids.add(pmid)
            elif len(all_pmids) >= MAX_TOTAL_PAPERS:
                break
        
        search_results[supplement] = len(unique_pmids)
        logger.info(f"  {supplement}: {len(unique_pmids)} unique papers (total: {len(all_pmids):,})")
        
        # Early termination if we hit global limit
        if len(all_pmids) >= MAX_TOTAL_PAPERS:
            logger.warning(f"⚠️  Reached global limit. Stopping at {len(all_pmids):,} papers.")
            break
    
    logger.info(f"Multi-supplement search complete:")
    logger.info(f"  Total unique PMIDs: {len(all_pmids):,}")
    logger.info(f"  Supplements searched: {len(search_results)}/{len(SUPPLEMENT_QUERIES)}")
    logger.info(f"  Top supplements by paper count:")
    
    for supplement, count in sorted(search_results.items(), key=lambda x: x[1], reverse=True)[:10]:
        logger.info(f"    {supplement}: {count} papers")
    
    return list(all_pmids)

def pubmed_esearch(term: str, mindate: str|None=None, maxdate: str|None=None, retmax: int=200, retstart:int=0) -> dict:
    params = {"db":"pubmed","retmode":"json","term":term,"retmax":str(retmax),"retstart":str(retstart),"email":NCBI_EMAIL}
    if NCBI_API_KEY: params["api_key"]=NCBI_API_KEY
    if mindate or maxdate: 
        params["datetype"] = "pdat"
        if mindate: params["mindate"] = mindate  # YYYY/MM/DD
        if maxdate: params["maxdate"] = maxdate  # YYYY/MM/DD
    
    # Add rate limiting
    time.sleep(1.0)  # 1 second between requests
    
    with httpx.Client(timeout=60) as c:
        r = c.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params)
        r.raise_for_status()
        try:
            return r.json()
        except Exception as e:
            print(f"JSON decode error: {e}")
            print(f"Response content: {r.text[:500]}...")
            # Try to clean the response
            import re
            cleaned_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', r.text)
            return json.loads(cleaned_text)

def pubmed_efetch_xml(pmids: list[str]) -> dict:
    params = {"db":"pubmed","retmode":"xml","id":",".join(pmids),"email":NCBI_EMAIL}
    if NCBI_API_KEY: params["api_key"]=NCBI_API_KEY
    
    # Add rate limiting
    time.sleep(1.0)  # 1 second between requests
    
    # Retry logic for PubMed API
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=120) as c:
                r = c.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=params)
                r.raise_for_status()
                return xmltodict.parse(r.text)
        except Exception as e:
            if attempt < max_retries - 1:
                # Check if it's a 429 rate limit error
                if "429" in str(e) or "Too Many Requests" in str(e):
                    wait_time = (attempt + 1) * 10  # Longer wait for rate limits
                    print(f"PubMed rate limit hit (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Waiting {wait_time} seconds before retry...")
                else:
                    wait_time = (attempt + 1) * 5  # Standard exponential backoff
                    print(f"PubMed API error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"PubMed API failed after {max_retries} attempts: {e}")
                raise

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

def analyze_combination_distribution(existing_docs):
    """Analyze existing papers for factor combinations"""
    combinations = {
        "supplement_goal": {},      # creatine + muscle_gain
        "supplement_population": {}, # beta-alanine + athletes  
        "goal_population": {},      # muscle_gain + elderly
        "study_type_goal": {},      # meta-analysis + weight_loss
        "journal_supplement": {}    # J Appl Physiol + creatine
    }
    
    for doc in existing_docs:
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

def calculate_combination_weights(combinations, total_docs):
    """Calculate weights based on combination representation"""
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

def iterative_diversity_filtering(papers: list, target_count: int, elimination_per_round: int = 1000) -> list:
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
    
    print(f"Starting iterative diversity filtering:")
    print(f"  Initial papers: {len(current_papers):,}")
    print(f"  Target papers: {target_count:,}")
    print(f"  Elimination per round: {elimination_per_round:,}")
    print(f"  Estimated rounds: {(len(current_papers) - target_count) // elimination_per_round + 1}")
    
    while len(current_papers) > target_count:
        papers_to_eliminate = min(elimination_per_round, len(current_papers) - target_count)
        
        print(f"\nRound {round_num}: {len(current_papers):,} papers -> eliminating {papers_to_eliminate:,}")
        
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
            print(f"  Top combination weights: {dict(top_weights)}")
        
        round_num += 1
        
        # Safety check
        if round_num > 50:  # Prevent infinite loops
            print(f"⚠️  Safety limit reached at round {round_num}. Stopping.")
            break
    
    print(f"\nIterative filtering complete:")
    print(f"  Final papers: {len(current_papers):,}")
    print(f"  Rounds completed: {round_num - 1}")
    
    # Final sort by enhanced score
    current_papers.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
    
    return current_papers[:target_count]

def calculate_combination_score(paper, combination_weights):
    """Calculate score based on paper's factor combinations with quality safeguards"""
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

def analyze_existing_combinations():
    """Analyze existing index for factor combinations and adjust scoring"""
    try:
        from evidentfit_shared.search_client import search_docs
        
        # Search for all documents to analyze combination distribution
        results = search_docs("*", top=1000)  # Get a sample of existing docs
        existing_docs = results.get("value", [])
        total_docs = len(existing_docs)
        
        if total_docs == 0:
            print("No existing documents found")
            return {}, 0
        
        # Analyze combination distribution
        combinations = analyze_combination_distribution(existing_docs)
        
        # Calculate combination weights
        combination_weights = calculate_combination_weights(combinations, total_docs)
        
        print(f"Found {total_docs} existing documents")
        print(f"Supplement-goal combinations: {dict(sorted(combinations['supplement_goal'].items(), key=lambda x: x[1], reverse=True)[:10])}")
        print(f"Goal-population combinations: {dict(sorted(combinations['goal_population'].items(), key=lambda x: x[1], reverse=True)[:5])}")
        
        return combination_weights, total_docs
    except Exception as e:
        print(f"Could not analyze existing combinations: {e}")
        return {}, 0

def run_ingest(mode: str):
    ensure_index(vector_dim=1536)

    # For bootstrap mode, start with empty combination weights
    # We'll calculate them dynamically during the selection process
    combination_weights = {}
    total_docs = 0

    # Watermark → mindate
    mindate = None
    wm = get_doc(WATERMARK_KEY)
    if mode == "bootstrap":
        mindate = "1990/01/01"  # Comprehensive historical evaluation
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
        # Bootstrap: Use multi-supplement search for comprehensive coverage
        logger.info("Bootstrap mode: Using multi-supplement search for comprehensive coverage...")
        ids = multi_supplement_search(mindate=mindate)
        logger.info(f"Bootstrap: Found {len(ids)} PMIDs from multi-supplement search (will filter to best {INGEST_LIMIT} papers)")
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
            time.sleep(1.0)  # Rate limiting - 1 second between requests
        
        logger.info(f"Monthly: Found {len(ids)} new PMIDs since last run")

    if not ids:
        logger.warning("No new PubMed IDs."); return

    # Fetch → parse → score → filter → upsert
    all_docs = []
    total_processed = 0
    
    for i in range(0, len(ids), 50):  # Smaller batches to avoid API limits
        pid_batch = ids[i:i+50]
        xml = pubmed_efetch_xml(pid_batch)
        
        # Handle case where PubMed API returns string instead of XML
        if isinstance(xml, str):
            print(f"PubMed API returned string instead of XML for batch {i//50 + 1}, skipping...")
            continue
            
        arts = xml.get("PubmedArticleSet", {}).get("PubmedArticle", [])
        if isinstance(arts, dict): arts = [arts]

        for rec in arts:
            d = parse_pubmed_article(rec, combination_weights) # Pass combination weights
            if d is None: continue  # Skip irrelevant studies
            if not d["title"] and not d["content"]: continue
            
            # Calculate combination score for this paper
            combination_score = calculate_combination_score(d, combination_weights)
            d["combination_score"] = combination_score
            d["enhanced_score"] = d.get("reliability_score", 0) + combination_score
            
            all_docs.append(d)
            total_processed += 1
            
            if total_processed % 100 == 0:
                logger.info(f"Processed {total_processed} papers...")

    # Dynamic rolling window system: Maintain 10,000, temporarily go to 15,000
    logger.info(f"Processing {len(all_docs)} papers with dynamic rolling window system...")
    
    if mode == "bootstrap":
        # Bootstrap: Get best 10,000 from large batch
        logger.info("Bootstrap mode: Selecting best 10,000 papers from all available...")
        
        # Score all papers with combination-aware weighting
        all_docs.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
        
        # Enhanced quality threshold for 15K papers - balanced selectivity
        min_quality_threshold = 4.0  # Balanced: RCTs (10+), crossovers (7+), and cohorts (4+) pass, others (1) filtered
        quality_filtered_docs = [d for d in all_docs if d.get("reliability_score", 0) >= min_quality_threshold]
        logger.info(f"Quality filter: {len(all_docs)} -> {len(quality_filtered_docs)} papers (removed {len(all_docs) - len(quality_filtered_docs)} low-quality)")
        
        # Phase 1: Process all papers with reliability scores only
        logger.info(f"Phase 1: Processing {len(quality_filtered_docs)} papers with reliability scoring...")
        for doc in quality_filtered_docs:
            # Calculate combination score (will be 0.0 since no weights yet)
            combination_score = calculate_combination_score(doc, {})
            doc["combination_score"] = combination_score
            doc["enhanced_score"] = doc.get("reliability_score", 0) + combination_score
        
        # Phase 2: Iterative diversity filtering for optimal balance
        target_papers = INGEST_LIMIT  # Target full 10,000 papers
        logger.info(f"Phase 2: Iterative diversity filtering to select best {target_papers} papers...")
        top_docs = iterative_diversity_filtering(
            papers=quality_filtered_docs,
            target_count=target_papers,
            elimination_per_round=1000  # Fine-grained steps for optimal adaptation
        )
        
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
            
            logger.info(f"Found {len(existing_docs)} existing papers in index")
            
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
            
            # Sort by enhanced score (reliability + combination)
            unique_docs.sort(key=lambda x: x.get("enhanced_score", x.get("reliability_score", 0)), reverse=True)
            
            # Enhanced quality threshold for 15K papers - balanced selectivity  
            min_quality_threshold = 3.0  # Balanced minimum reliability score for comprehensive coverage
            quality_filtered_docs = [d for d in unique_docs if d.get("reliability_score", 0) >= min_quality_threshold]
            print(f"Quality filter: {len(unique_docs)} -> {len(quality_filtered_docs)} papers (removed {len(unique_docs) - len(quality_filtered_docs)} low-quality)")
            
            # If we have more than 15,000, temporarily keep top 15,000 for processing
            if len(quality_filtered_docs) > MAX_TEMP_LIMIT:
                print(f"Temporarily keeping top {MAX_TEMP_LIMIT} papers for processing...")
                temp_docs = quality_filtered_docs[:MAX_TEMP_LIMIT]
            else:
                temp_docs = quality_filtered_docs
            
            # Phase 1: Process all papers with reliability scores only
            print(f"Phase 1: Processing {len(temp_docs)} papers with reliability scoring...")
            for doc in temp_docs:
                # Calculate combination score (will be 0.0 since no weights yet)
                combination_score = calculate_combination_score(doc, {})
                doc["combination_score"] = combination_score
                doc["enhanced_score"] = doc.get("reliability_score", 0) + combination_score
            
            # Phase 2: Dynamic selection using combination-aware scoring
            target_papers = INGEST_LIMIT  # Target full 10,000 papers
            print(f"Phase 2: Selecting best {target_papers} papers using dynamic combination scoring...")
            
            # Calculate combination weights based on all processed papers
            combinations = analyze_combination_distribution(temp_docs)
            combination_weights = calculate_combination_weights(combinations, len(temp_docs))
            print(f"Calculated combination weights based on {len(temp_docs)} papers")
            
            # Re-score all papers with combination weights
            for doc in temp_docs:
                combination_score = calculate_combination_score(doc, combination_weights)
                doc["combination_score"] = combination_score
                doc["enhanced_score"] = doc.get("reliability_score", 0) + combination_score
            
            # Sort by enhanced score and select top papers
            temp_docs.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)
            selected_docs = temp_docs[:target_papers]
            
            # Fill remaining slots with highest scoring papers
            remaining_slots = target_papers - len(selected_docs)
            if remaining_slots > 0:
                used_ids = {doc["id"] for doc in selected_docs}
                for doc in temp_docs:
                    if doc["id"] not in used_ids and remaining_slots > 0:
                        selected_docs.append(doc)
                        remaining_slots -= 1
            
            top_docs = selected_docs
            print(f"Trimmed from {len(temp_docs)} to {len(top_docs)} papers")
            
        except Exception as e:
            logger.error(f"Could not merge with existing index: {e}")
            logger.warning("Falling back to bootstrap mode...")
            # Fallback to bootstrap logic
            target_papers = INGEST_LIMIT  # Target full 10,000 papers
            all_docs.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)
            top_docs = all_docs[:target_papers]
    
    # Final analysis
    final_supplement_counts = {}
    for doc in top_docs:
        supplements = doc.get("supplements", "").split(",") if doc.get("supplements") else []
        for supp in supplements:
            supp = supp.strip()
            if supp:
                final_supplement_counts[supp] = final_supplement_counts.get(supp, 0) + 1
    
    logger.info(f"Final selection: {len(top_docs)} papers")
    logger.info(f"Final supplement distribution: {dict(sorted(final_supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10])}")
    logger.info(f"Top enhanced scores: {[d.get('enhanced_score', 0) for d in top_docs[:5]]}")
    logger.info(f"Top combination scores: {[d.get('combination_score', 0) for d in top_docs[:5]]}")
    
    # Show combination distribution in final selection
    combo_analysis = {"supplement_goal": {}, "goal_population": {}}
    for doc in top_docs[:100]:  # Analyze top 100 papers
        supplements = doc.get("supplements", "").split(",")
        primary_goal = doc.get("primary_goal", "")
        population = doc.get("population", "")
        
        for supp in supplements:
            if supp.strip() and primary_goal:
                key = f"{supp.strip()}_{primary_goal}"
                combo_analysis["supplement_goal"][key] = combo_analysis["supplement_goal"].get(key, 0) + 1
        
        if primary_goal and population:
            key = f"{primary_goal}_{population}"
            combo_analysis["goal_population"][key] = combo_analysis["goal_population"].get(key, 0) + 1
    
    print(f"Top supplement-goal combinations: {dict(sorted(combo_analysis['supplement_goal'].items(), key=lambda x: x[1], reverse=True)[:10])}")
    print(f"Top goal-population combinations: {dict(sorted(combo_analysis['goal_population'].items(), key=lambda x: x[1], reverse=True)[:5])}")
    
    # Process in batches
    total = 0
    batch_size = 50  # Larger batches since we're not doing embeddings
    for i in range(0, len(top_docs), batch_size):
        batch_docs = top_docs[i:i+batch_size]
        
        try:
            upsert_docs(batch_docs)
            total += len(batch_docs)
            logger.info(f"Upserted {len(batch_docs)} docs (total {total})")
            
            # Small delay between batches
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error processing batch {i//batch_size + 1}: {e}")
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
    logger.info(f"Watermark updated to {now_iso}")
    logger.info("Ingest job completed successfully!")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bootstrap","monthly"], default="monthly")
    args = ap.parse_args()
    run_ingest(args.mode)
