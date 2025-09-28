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
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT","5000"))

# --- Simple maps/heuristics ---
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

def calculate_reliability_score(rec: dict) -> float:
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
    
    # Supplement diversity bonus - boost less common supplements
    text_for_diversity = f"{title}\n{content}".lower()
    diversity_bonus = 0.0
    
    # Less researched supplements get higher scores
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

def parse_pubmed_article(rec: dict) -> dict:
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

    # Calculate reliability score
    reliability_score = calculate_reliability_score(rec)

    text_for_tags = f"{title}\n{content}"
    supplements = extract_supplements(text_for_tags)
    outcomes = extract_outcomes(text_for_tags)

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
        "population": None,
        "summary": None,
        "content": content.strip(),  # Only store abstract, not full text
        "reliability_score": reliability_score,
        "index_version": INDEX_VERSION
    }

def run_ingest(mode: str):
    ensure_index(vector_dim=1536)

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

    # Search PubMed with higher limit to allow for filtering
    ids, retstart = [], 0
    search_limit = INGEST_LIMIT * 3  # Get 3x more to filter down
    while len(ids) < search_limit:
        batch = pubmed_esearch(PM_SEARCH_QUERY, mindate=mindate, retmax=200, retstart=retstart)
        idlist = batch.get("esearchresult", {}).get("idlist", [])
        if not idlist: break
        ids.extend(idlist)
        retstart += len(idlist)
        if retstart >= int(batch["esearchresult"].get("count","0")): break
        time.sleep(0.34)

    if not ids:
        print("No new PubMed IDs."); return

    print(f"Found {len(ids)} PMIDs (will filter to top {INGEST_LIMIT})")

    # Fetch → parse → score → filter → upsert
    all_docs = []
    total_processed = 0
    
    for i in range(0, len(ids), 200):
        pid_batch = ids[i:i+200]
        xml = pubmed_efetch_xml(pid_batch)
        arts = xml.get("PubmedArticleSet", {}).get("PubmedArticle", [])
        if isinstance(arts, dict): arts = [arts]

        for rec in arts:
            d = parse_pubmed_article(rec)
            if not d["title"] and not d["content"]: continue
            all_docs.append(d)
            total_processed += 1
            
            if total_processed % 100 == 0:
                print(f"Processed {total_processed} papers...")

    # Sort by reliability score and apply diversity filtering
    print(f"Sorting {len(all_docs)} papers by reliability score...")
    all_docs.sort(key=lambda x: x.get("reliability_score", 0), reverse=True)
    
    # Apply diversity filtering to ensure balanced supplement representation
    selected_docs = []
    supplement_counts = {}
    max_per_supplement = INGEST_LIMIT // 20  # Max 5% per supplement
    
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
    
    print(f"Selected {len(top_docs)} papers with diversity filtering")
    print(f"Supplement distribution: {dict(sorted(supplement_counts.items(), key=lambda x: x[1], reverse=True)[:10])}")
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
