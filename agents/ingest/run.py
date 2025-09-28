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
INGEST_LIMIT = int(os.getenv("INGEST_LIMIT","2000"))

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
        "supplements": supplements,
        "outcomes": outcomes,
        "population": None,
        "summary": None,
        "content": content.strip(),
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

    # Search PubMed
    ids, retstart = [], 0
    while len(ids) < INGEST_LIMIT:
        batch = pubmed_esearch(PM_SEARCH_QUERY, mindate=mindate, retmax=200, retstart=retstart)
        idlist = batch.get("esearchresult", {}).get("idlist", [])
        if not idlist: break
        ids.extend(idlist)
        retstart += len(idlist)
        if retstart >= int(batch["esearchresult"].get("count","0")): break
        time.sleep(0.34)

    if not ids:
        print("No new PubMed IDs."); return

    print(f"Found {len(ids)} PMIDs (capped to INGEST_LIMIT={INGEST_LIMIT})")

    # Fetch → parse → embed → upsert
    total = 0
    for i in range(0, min(len(ids), INGEST_LIMIT), 200):
        pid_batch = ids[i:i+200]
        xml = pubmed_efetch_xml(pid_batch)
        arts = xml.get("PubmedArticleSet", {}).get("PubmedArticle", [])
        if isinstance(arts, dict): arts = [arts]

        docs, texts = [], []
        for rec in arts:
            d = parse_pubmed_article(rec)
            if not d["title"] and not d["content"]: continue
            texts.append(d["content"] or d["title"])
            docs.append(d)

        if not docs: continue

        # Process embeddings in smaller batches to avoid rate limits
        batch_size = 10  # Smaller batch size for embeddings
        for j in range(0, len(texts), batch_size):
            batch_texts = texts[j:j+batch_size]
            batch_docs = docs[j:j+batch_size]
            
            try:
                # Skip embeddings for free tier - just use content as searchable text
                # vecs = embed_texts(batch_texts)
                # for d, v in zip(batch_docs, vecs): d["content_vector"] = v
                
                upsert_docs(batch_docs)
                total += len(batch_docs)
                print(f"Upserted {len(batch_docs)} docs (total {total})")
                
                # Rate limiting: wait between embedding calls
                time.sleep(2.0)  # 2 seconds between batches
                
            except Exception as e:
                print(f"Error processing batch {j//batch_size + 1}: {e}")
                # Continue with next batch instead of failing completely
                continue

    # Update watermark
    now_iso = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00","Z")
    wm_doc = {
        "id": WATERMARK_KEY,
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
