# agents/ingest/get_papers/fulltext_fetcher.py
"""
Unified full-text fetcher for selected PubMed papers.

Order of attempts per paper:
  1) PMC fulltext (PMID→PMCID via ELink, then DOI→PMCID via PMC ID Converter), incl. EFetch fallback
  2) Europe PMC XML fallback
  3) Unpaywall (iterate ALL locations with smart ranking)
  4) Aggressive scrape (DOI resolver)
  5) PubMed abstract fallback

Storage model (de-coupled from runs):
  - Full texts are saved ONCE into a centralized store (default: PROJECT_ROOT/data/fulltext_store),
    sharded by a short hash to avoid giant folders.
  - Each run writes ONLY a manifest JSON listing per-paper status and the absolute stored path.

Manifest (written into the run dir you pass in):
  run_dir/fulltext_manifest.json
    {
      "store_dir": ".../data/fulltext_store",
      "total": N,
      "pmc_ok": M,
      "pmc_ok_percent": ...,
      "saved": S,
      "skipped_existing": K,
      "entries": [
         {"pmid":"...", "doi":"...", "stored_path":".../data/fulltext_store/aa/bb/pmid_1234.json", "pmc_status":"ok|none|error"}
      ]
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import hashlib
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
import xmltodict
import trafilatura
from evidentfit_shared.utils import PROJECT_ROOT

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # Will use fallback tag stripping

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # PDF extraction unavailable

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_PMC_OA = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
PMC_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_FETCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/{}/{}/fullTextXML"

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

# Browser-like headers for publisher compatibility
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# Separate headers for API calls (PubMed, Unpaywall) - keep bot identification
API_HEADERS = {
    "User-Agent": "EvidentFit-Research/1.0 (+https://evidentfit.com; research@evidentfit.com)",
    "Accept": "application/json",
}

# NCBI rate limiting: 3 req/sec without API key, 10 req/sec with key
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
RATE_LIMIT_DELAY = 0.34 if not NCBI_API_KEY else 0.11  # Conservative: ~3/sec or ~9/sec
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 5, 15]  # Exponential backoff for 429 errors

# Unpaywall configuration
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "research@evidentfit.com")  # Required
ENABLE_UNPAYWALL = os.getenv("ENABLE_UNPAYWALL", "true").lower() == "true"

# Availability pre-checking (for selection phase, not fetching)
ENABLE_AVAILABILITY_CHECKING = os.getenv("ENABLE_AVAILABILITY_CHECKING", "true").lower() == "true"

def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def _clean_unicode(text: str) -> str:
    # Normalize Unicode
    text = unicodedata.normalize('NFKD', text)
    replacements = {
        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '--', '\u2212': '-', '\u00a0': ' ',
        '\u2009': ' ', '\u200b': '', '\xa0': ' ', '\u2032': "'",
        '\u2033': "''", '\u00b0': ' degrees ', '\u00d7': 'x',
        '\u2264': '<=', '\u2265': '>=', '\u00b1': '+/-',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text

def _extract_article_content(xml_text: str) -> str:
    try:
        from bs4 import BeautifulSoup as _BS
        soup = _BS(xml_text, 'lxml-xml')
        parts = []
        title_tag = soup.find('article-title')
        if title_tag:
            title = title_tag.get_text(' ', strip=True)
            parts.append(f"TITLE:\n{title}\n")
        abstract_tag = soup.find('abstract')
        if abstract_tag:
            for tag in abstract_tag.find_all(['title', 'label']):
                tag.decompose()
            abstract_text = abstract_tag.get_text(' ', strip=True)
            if abstract_text:
                parts.append(f"ABSTRACT:\n{abstract_text}\n")
        body_tag = soup.find('body')
        if body_tag:
            for tag in body_tag.find_all(['ref-list', 'fn-group', 'ack']):
                tag.decompose()
            sections = body_tag.find_all('sec', recursive=False)
            for sec in sections:
                sec_title = sec.find('title')
                sec_name = sec_title.get_text(strip=True) if sec_title else ""
                if sec_name:
                    parts.append(f"\n{sec_name.upper()}:")
                paragraphs = sec.find_all('p', recursive=True)
                for p in paragraphs:
                    p_text = p.get_text(' ', strip=True)
                    if p_text and len(p_text) > 15:
                        p_text = re.sub(r'\s+', ' ', p_text)
                        parts.append(p_text)
                tables = sec.find_all('table-wrap')
                for table_wrap in tables:
                    caption = table_wrap.find('caption')
                    if caption:
                        cap_text = caption.get_text(' ', strip=True)
                        if cap_text:
                            parts.append(f"TABLE: {cap_text}")
                    table = table_wrap.find('table')
                    if table:
                        headers = []
                        thead = table.find('thead')
                        if thead:
                            for th in thead.find_all(['th', 'td']):
                                h_text = th.get_text(' ', strip=True)
                                if h_text:
                                    headers.append(h_text)
                        rows = []
                        tbody = table.find('tbody')
                        if tbody:
                            for tr in tbody.find_all('tr')[:20]:
                                row_cells = []
                                for td in tr.find_all(['td', 'th']):
                                    cell_text = td.get_text(' ', strip=True)
                                    if cell_text:
                                        row_cells.append(cell_text)
                                if row_cells:
                                    rows.append(' | '.join(row_cells))
                        if headers:
                            parts.append(' | '.join(headers))
                        if rows:
                            parts.extend(rows[:15])
                figs = sec.find_all('fig')
                for fig in figs:
                    caption = fig.find('caption')
                    if caption:
                        cap_text = caption.get_text(' ', strip=True)
                        if cap_text:
                            parts.append(f"FIGURE: {cap_text}")
        if parts:
            full_text = "\n\n".join(parts)
            full_text = _clean_unicode(full_text)
            full_text = re.sub(r'\[\s*(?:,\s*)*\]', '', full_text)
            full_text = re.sub(r'\(\s*(?:,\s*)*\)', '', full_text)
            full_text = re.sub(r'\s+([.,;:)])', r'\1', full_text)
            full_text = re.sub(r'([.,;:])\s*\1+', r'\1', full_text)
            lines = full_text.split('\n')
            lines = [re.sub(r'  +', ' ', line).strip() for line in lines]
            full_text = '\n'.join(line for line in lines if line)
            return full_text
    except Exception as e:
        logger.debug(f"Article content extraction failed, falling back to simple strip: {e}")
    text = re.sub(r"<[^>]+>", " ", xml_text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _safe_key_from(pmid: Optional[str], doi: Optional[str]) -> str:
    if pmid:
        return f"pmid_{pmid}"
    if doi:
        safe_doi = re.sub(r"[^A-Za-z0-9_.-]", "_", doi)
        return f"doi_{safe_doi}"
    return "unknown"

def _sharded_store_path(store_dir: Path, key: str) -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    shard1, shard2 = h[:2], h[2:4]
    return store_dir / shard1 / shard2 / f"{key}.json"

async def _elink_pubmed_to_pmc(client: httpx.AsyncClient, pmid: str, rate_limiter: asyncio.Semaphore) -> Optional[str]:
    params = {"dbfrom": "pubmed", "db": "pmc", "retmode": "json", "id": pmid}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    for attempt in range(MAX_RETRIES):
        try:
            async with rate_limiter:
                r = await client.get(f"{EUTILS_BASE}/elink.fcgi", params=params, headers=API_HEADERS)
                await asyncio.sleep(RATE_LIMIT_DELAY)
                if r.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        wait_time = RETRY_BACKOFF[attempt]
                        logger.warning(f"Rate limit hit for PMID {pmid}, waiting {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit hit for PMID {pmid}, max retries exceeded")
                        return None
                r.raise_for_status()
                data = r.json()
                linksets = data.get("linksets", [])
                if not linksets:
                    return None
                for ls in linksets:
                    for linksetdb in ls.get("linksetdbs", []) or []:
                        if linksetdb.get("dbto") == "pmc":
                            ids = linksetdb.get("links", []) or []
                            if ids:
                                pmcid_num = ids[0]
                                return f"PMC{pmcid_num}"
                return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF[attempt]
                logger.warning(f"Rate limit (429) for PMID {pmid}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                continue
            logger.error(f"HTTP error for PMID {pmid}: {e}")
            return None
        except Exception as e:
            logger.debug(f"elink error for PMID {pmid}: {e}")
            return None
    return None

async def _pmc_oa_links(client: httpx.AsyncClient, pmcid: str, rate_limiter: asyncio.Semaphore) -> Dict[str, Optional[str]]:
    params = {"id": pmcid}
    try:
        async with rate_limiter:
            r = await client.get(NCBI_PMC_OA, params=params, headers=API_HEADERS)
            await asyncio.sleep(RATE_LIMIT_DELAY * 0.5)
            r.raise_for_status()
        xml = xmltodict.parse(r.text)
        xml_url = None
        pdf_url = None
        records = xml.get("OA", {}).get("records", {}).get("record", [])
        if isinstance(records, dict):
            records = [records]
        for rec in records:
            links = rec.get("link", [])
            if isinstance(links, dict):
                links = [links]
            for lk in links or []:
                fmt = lk.get("@format")
                href = lk.get("@href")
                if fmt == "xml" and href:
                    xml_url = href
                if fmt == "pdf" and href:
                    pdf_url = href
        return {"xml_url": xml_url, "pdf_url": pdf_url}
    except Exception as e:
        logger.debug(f"PMC OA error for {pmcid}: {e}")
        return {"xml_url": None, "pdf_url": None}

async def _fetch_text(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, headers=HEADERS)
        if r.status_code != 200:
            return None
        content_type = r.headers.get("content-type", "").lower()
        if any(ct in content_type for ct in ["xml", "html", "text", "plain"]):
            return r.text
        if r.text and r.text.strip().startswith("<"):
            return r.text
        return None
    except Exception:
        return None

# ------------------------------
# NEW: PMC ID Converter (DOI→PMCID)
# ------------------------------
async def _pmcid_from_doi(client: httpx.AsyncClient, doi: str) -> Optional[str]:
    if not doi:
        return None
    try:
        params = {"ids": doi, "format": "json"}
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        r = await client.get(PMC_IDCONV, params=params, headers=API_HEADERS, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        recs = data.get("records", [])
        if recs and isinstance(recs, list):
            pmcid = recs[0].get("pmcid")
            if pmcid and pmcid.upper().startswith("PMC"):
                return pmcid
    except Exception as e:
        logger.debug(f"pmcid_from_doi failed for {doi}: {e}")
    return None

# ------------------------------
# NEW: Europe PMC XML fallback
# ------------------------------
async def _europe_pmc_fulltext(client: httpx.AsyncClient, doi: Optional[str]=None, pmid: Optional[str]=None) -> Optional[str]:
    """
    Returns full text XML as string if available, else None. Prefers DOI query.
    """
    try:
        if doi:
            q = f'EXT_ID:"{doi}"'
        elif pmid:
            q = f'EXT_ID:{pmid}'
        else:
            return None
        params = {"query": q, "resultType": "core", "format": "json", "pageSize": "1"}
        r = await client.get(EUROPE_PMC_SEARCH, params=params, headers=API_HEADERS, timeout=10.0)
        r.raise_for_status()
        hits = r.json().get("resultList", {}).get("result", []) or []
        if not hits:
            return None
        hit = hits[0]
        src = hit.get("source")  # "MED", "PMC", etc.
        ext_id = hit.get("id")
        if not src or not ext_id:
            return None
        ft_url = EUROPE_PMC_FETCH.format(src, ext_id)
        f = await client.get(ft_url, headers=API_HEADERS, timeout=10.0)
        if f.status_code == 200 and f.text and "<article" in f.text[:2000]:
            return f.text
    except Exception as e:
        logger.debug(f"Europe PMC fetch failed: {e}")
    return None

# ============================================================================
# Availability Pre-Checking (for selection phase, lightweight)
# ============================================================================
async def check_pmc_available(client: httpx.AsyncClient, pmid: str, rate_limiter: asyncio.Semaphore) -> bool:
    if not pmid:
        return False
    try:
        pmcid = await _elink_pubmed_to_pmc(client, pmid, rate_limiter)
        return pmcid is not None
    except Exception:
        return False

async def check_unpaywall_available(client: httpx.AsyncClient, doi: str) -> bool:
    if not doi or not ENABLE_UNPAYWALL:
        return False
    try:
        api_url = f"{UNPAYWALL_API_BASE}/{doi}"
        params = {"email": UNPAYWALL_EMAIL}
        r = await client.get(api_url, params=params, headers=API_HEADERS, timeout=5.0)
        if r.status_code != 200:
            return False
        data = r.json()
        if data.get("is_oa"):
            return True
        locs = data.get("oa_locations") or []
        return any(l.get("url_for_pdf") or l.get("url") for l in locs)
    except Exception:
        return False

async def check_fulltext_available(
    client: httpx.AsyncClient,
    pmid: Optional[str],
    doi: Optional[str],
    rate_limiter: asyncio.Semaphore
) -> bool:
    if pmid:
        if await check_pmc_available(client, pmid, rate_limiter):
            return True
    if doi:
        if await check_unpaywall_available(client, doi):
            return True
    return False

async def batch_check_availability(
    papers: List[Dict[str, Any]],
    max_concurrency: int = 10
) -> Dict[str, bool]:
    if not ENABLE_AVAILABILITY_CHECKING:
        return {}
    rate_limiter = asyncio.Semaphore(max_concurrency)
    results = {}
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=HEADERS) as client:
        tasks = []
        for p in papers:
            paper_id = p.get("id", "")
            pmid = str(p.get("pmid") or "").strip()
            doi = (p.get("doi") or "").strip()
            task = check_fulltext_available(client, pmid, doi, rate_limiter)
            tasks.append((paper_id, task))
        for paper_id, task in tasks:
            try:
                available = await task
                results[paper_id] = available
            except Exception:
                results[paper_id] = False
    return results

# ============================================================================
# Unpaywall Integration
# ============================================================================
def _extract_text_from_html(html_bytes: bytes) -> Optional[str]:
    if not html_bytes:
        return None
    try:
        html_text = html_bytes.decode('utf-8', errors='ignore')
        extracted = trafilatura.extract(
            html_text,
            include_tables=True,
            include_comments=False,
            favor_recall=True,          # more tolerant extraction
            no_fallback=False
        )
        if extracted and len(extracted.strip()) > 200:
            text = extracted.strip()
            # minimal signal that it's an article (≥1200 chars + 2 common section terms)
            if len(text) >= 1200:
                hits = sum(1 for s in ["introduction","methods","results","discussion","materials and methods"] if s in text.lower())
                if hits >= 2:
                    return text
        if BeautifulSoup:
            soup = BeautifulSoup(html_text, 'lxml')
            for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            if text and len(text) >= 1200:
                hits = sum(1 for s in ["introduction","methods","results","discussion","materials and methods"] if s in text.lower())
                if hits >= 2:
                    return text
        return None
    except Exception as e:
        logger.debug(f"HTML extraction failed: {e}")
        return None

def _extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 50) -> Optional[str]:
    if not PdfReader:
        logger.warning("pypdf not available - cannot extract PDF text")
        return None
    try:
        import io
        if not pdf_bytes.startswith(b'%PDF'):
            return None
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text_parts = []
        pages_to_read = min(len(reader.pages), max_pages)
        for i in range(pages_to_read):
            try:
                page_text = reader.pages[i].extract_text() or ""
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.debug(f"Failed to extract page {i}: {e}")
                continue
        full_text = "\n\n".join(text_parts)
        # Basic cleanup
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = re.sub(r'(\w)-\s+(\w)', r'\1\2', full_text)
        full_text = full_text.replace('\x00', '')
        if len(full_text) < 500:
            try:
                from pdfminer_high_level import extract_text as _bad  # sentinel to fail fast if not installed
            except Exception:
                _bad = None
            if _bad is None:
                try:
                    from pdfminer.high_level import extract_text as pdfminer_extract  # type: ignore
                    full_text = pdfminer_extract(io.BytesIO(pdf_bytes)) or ""
                except Exception as e:
                    logger.debug(f"pdfminer fallback failed: {e}")
        if not full_text or len(full_text) < 500:
            return None
        return full_text
    except Exception as e:
        logger.debug(f"PDF extraction failed: {e}")
        return None

def _rank_oa_locations(oa_locations: List[dict]) -> List[dict]:
    """
    Prefer repository > publisher; pdf > html; license present; version rank.
    """
    if not oa_locations:
        return []
    def key(loc: dict):
        host = 0 if loc.get("host_type") == "repository" else 1
        has_pdf = 0 if loc.get("url_for_pdf") else 1
        has_html = 0 if loc.get("url") else 1
        has_license = 0 if loc.get("license") else 1
        version_rank = {"publishedVersion": 0, "acceptedVersion": 1, "submittedVersion": 2}
        ver = version_rank.get((loc.get("version") or "").strip(), 3)
        return (host, has_pdf, has_html, has_license, ver)
    return sorted(oa_locations, key=key)

UNPAYWALL_CACHE: Dict[str, dict] = {}

async def _scrape_doi_aggressive(
    client: httpx.AsyncClient,
    doi: str
) -> Optional[Tuple[str, bytes, str]]:
    if not doi:
        return None
    browser_headers = {**HEADERS, "Referer": "https://scholar.google.com/", "Cache-Control": "no-cache"}
    urls_to_try = [f"https://doi.org/{doi}", f"https://dx.doi.org/{doi}"]
    for url in urls_to_try:
        try:
            r = await client.get(url, follow_redirects=True, headers=browser_headers, timeout=httpx.Timeout(15.0))
            if r.status_code == 200 and len(r.content) > 1000:
                content_type = r.headers.get("content-type", "").lower()
                if "html" in content_type or "text" in content_type:
                    logger.info(f"✓ Aggressive scrape succeeded for {doi}")
                    return (url, r.content, "html_aggressive_scrape")
                elif "pdf" in content_type or r.content.startswith(b'%PDF'):
                    return (url, r.content, "pdf")
        except Exception as e:
            logger.debug(f"Aggressive scrape failed for {url}: {e}")
            continue
    return None

async def _fetch_unpaywall(
    client: httpx.AsyncClient,
    doi: str,
) -> Optional[Tuple[str, bytes, str]]:
    """
    Query Unpaywall and try ALL ranked locations for PDF/HTML.
    Returns (url, bytes, format) or None. format is 'pdf' or 'html(_*)'
    """
    if not doi or not ENABLE_UNPAYWALL:
        return None
    try:
        data = UNPAYWALL_CACHE.get(doi)
        if not data:
            api_url = f"{UNPAYWALL_API_BASE}/{doi}"
            params = {"email": UNPAYWALL_EMAIL}
            r = await client.get(api_url, params=params, headers=API_HEADERS, timeout=10.0)
            if r.status_code != 200:
                return None
            data = r.json()
            UNPAYWALL_CACHE[doi] = data
        locations = data.get("oa_locations") or []
        if not locations and data.get("best_oa_location"):
            locations = [data["best_oa_location"]]
        for loc in _rank_oa_locations(locations):
            pdf_url = loc.get("url_for_pdf")
            html_url = loc.get("url")
            if pdf_url:
                try:
                    pdf_r = await client.get(pdf_url, follow_redirects=True, headers={**HEADERS, "Accept": "application/pdf"}, timeout=20.0)
                    ct = pdf_r.headers.get("content-type", "").lower()
                    if pdf_r.status_code == 200 and (("pdf" in ct) or pdf_r.content.startswith(b"%PDF")) and len(pdf_r.content) > 8000:
                        return (pdf_url, pdf_r.content, "pdf")
                except Exception as e:
                    logger.debug(f"Unpaywall PDF fetch failed ({pdf_url}): {e}")
            if html_url:
                try:
                    html_r = await client.get(html_url, follow_redirects=True, headers=HEADERS, timeout=20.0)
                    if html_r.status_code == 200 and len(html_r.content) > 1000:
                        return (html_url, html_r.content, "html")
                except Exception as e:
                    logger.debug(f"Unpaywall HTML fetch failed ({html_url}): {e}")
        doi_url = f"https://doi.org/{doi}"
        try:
            doi_r = await client.get(doi_url, follow_redirects=True, headers={**HEADERS, "Referer": "https://www.google.com/"}, timeout=15.0)
            if doi_r.status_code == 200 and len(doi_r.content) > 1000:
                ct = doi_r.headers.get("content-type","").lower()
                if "pdf" in ct or doi_r.content.startswith(b"%PDF"):
                    return (doi_url, doi_r.content, "pdf")
                if "html" in ct or "text" in ct:
                    return (doi_url, doi_r.content, "html_doi_fallback")
        except Exception as e:
            logger.debug(f"DOI landing fallback failed for {doi}: {e}")
    except Exception as e:
        logger.debug(f"Unpaywall fetch failed for {doi}: {e}")
        return None
    return None

# ============================================================================
# Main fetch path (ordered strategy)
# ============================================================================
async def _fetch_one_fulltext(
    client: httpx.AsyncClient,
    paper: Dict[str, Any],
    rate_limiter: asyncio.Semaphore
) -> Tuple[str, Dict[str, Any]]:
    pmid = str(paper.get("pmid") or "").strip()
    doi = (paper.get("doi") or "").strip()
    # normalize DOI (lowercase, strip leading resolver, decode common encodings)
    if doi:
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "").strip()
        doi = re.sub(r"%2F", "/", doi, flags=re.IGNORECASE)
        doi = doi.lower()
    abstract = (paper.get("content") or "").strip()
    record: Dict[str, Any] = {
        "pmid": pmid or None,
        "doi": doi or None,
        "sources": {
            "pmc": {"pmcid": None, "xml_url": None, "pdf_url": None, "status": "none", "fulltext_bytes": None},
            "doi": {"url": f"https://doi.org/{doi}" if doi else None, "status": "hint_only"}
        },
        "fulltext_text": None,
        "abstract": abstract
    }

    # 1) PMC fulltext (PMID→PMCID ; DOI→PMCID) + EFetch fallback
    pmcid: Optional[str] = None
    try:
        if pmid:
            pmcid = await _elink_pubmed_to_pmc(client, pmid, rate_limiter)
        if not pmcid and doi:
            pmcid = await _pmcid_from_doi(client, doi)
        if pmcid:
            record["sources"]["pmc"]["pmcid"] = pmcid
            links = await _pmc_oa_links(client, pmcid, rate_limiter)
            record["sources"]["pmc"].update(links)
            xml_url = links.get("xml_url")
            if xml_url:
                xml_text = await _fetch_text(client, xml_url)
                if xml_text:
                    fulltext = _extract_article_content(xml_text)
                    record["sources"]["pmc"]["fulltext_bytes"] = len(xml_text)
                    has_body = bool(re.search(
                        r'(INTRODUCTION|METHODS|RESULTS|DISCUSSION|BACKGROUND|MATERIALS AND METHODS|STUDY DESIGN|PARTICIPANTS):',
                        fulltext
                    ))
                    if has_body:
                        record["fulltext_text"] = fulltext
                        record["sources"]["pmc"]["status"] = "ok"
                        record["sources"]["pmc"]["has_body_sections"] = True
                        return (pmid or doi or "unknown", record)
                    else:
                        # Don't set fulltext_text for abstract-only; allow fallback sources to be tried
                        record["sources"]["pmc"]["status"] = "abstract_only"
                        record["sources"]["pmc"]["has_body_sections"] = False
            # EFetch fallback
            efetch_params = {"db": "pmc", "id": pmcid, "rettype": "xml"}
            if NCBI_API_KEY:
                efetch_params["api_key"] = NCBI_API_KEY
            fallback_xml_url = f"{EUTILS_BASE}/efetch.fcgi"
            try:
                async with rate_limiter:
                    r = await client.get(fallback_xml_url, params=efetch_params, headers=API_HEADERS)
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                if r.status_code == 200 and r.text and len(r.text) > 1000:
                    xml_text = r.text
                    fulltext = _extract_article_content(xml_text)
                    record["sources"]["pmc"]["xml_url"] = f"{fallback_xml_url}?db=pmc&id={pmcid}&rettype=xml"
                    record["sources"]["pmc"]["fulltext_bytes"] = len(xml_text)
                    has_body = bool(re.search(
                        r'(INTRODUCTION|METHODS|RESULTS|DISCUSSION|BACKGROUND|MATERIALS AND METHODS|STUDY DESIGN|PARTICIPANTS):',
                        fulltext
                    ))
                    if has_body:
                        record["fulltext_text"] = fulltext
                        record["sources"]["pmc"]["status"] = "ok_efetch"
                        record["sources"]["pmc"]["has_body_sections"] = True
                        return (pmid or doi or "unknown", record)
                    else:
                        # Don't set fulltext_text for abstract-only; allow fallback sources to be tried
                        record["sources"]["pmc"]["status"] = "abstract_only"
                        record["sources"]["pmc"]["has_body_sections"] = False
            except Exception as e:
                logger.debug(f"EFetch failed for {pmcid}: {e}")
    except Exception as e:
        record["sources"]["pmc"]["status"] = "error"
        record["sources"]["pmc"]["error"] = str(e)

    # 2) Europe PMC fallback
    if not record["fulltext_text"]:
        epmc_xml = await _europe_pmc_fulltext(client, doi=doi or None, pmid=pmid or None)
        if epmc_xml:
            ft = _extract_article_content(epmc_xml)
            if ft and len(ft) > 1000:
                record["fulltext_text"] = ft
                record.setdefault("sources", {}).setdefault("europe_pmc", {})["status"] = "ok_xml"
                record["sources"]["pmc"]["has_body_sections"] = True
                return (pmid or doi or "unknown", record)

    # 3) Unpaywall (iterate locations)
    pmc_status = record["sources"]["pmc"]["status"]
    needs_unpaywall = pmc_status in ("none", "error", "abstract_only")
    if needs_unpaywall and doi:
        try:
            unpaywall_result = None
            if ENABLE_UNPAYWALL:
                unpaywall_result = await _fetch_unpaywall(client, doi)
            if unpaywall_result:
                url, content_bytes, format_type = unpaywall_result
                record["sources"]["unpaywall"] = {"url": url, "format": format_type, "status": "ok", "content_bytes": len(content_bytes)}
                if format_type == "pdf":
                    pdf_text = _extract_text_from_pdf(content_bytes)
                    if pdf_text:
                        has_body = bool(re.search(r'(Introduction|Methods|Results|Discussion|Background|Materials and Methods|Study Design|Participants)', pdf_text, re.IGNORECASE))
                        record["sources"]["unpaywall"]["has_body_sections"] = has_body
                        if has_body:
                            # Only set fulltext_text if we have body sections
                            record["fulltext_text"] = pdf_text
                            record["sources"]["unpaywall"]["status"] = "ok_pdf"
                            return (pmid or doi or "unknown", record)
                        else:
                            # PDF extracted but no body sections - try other sources
                            record["sources"]["unpaywall"]["status"] = "pdf_abstract_only"
                    else:
                        record["sources"]["unpaywall"]["status"] = "pdf_extraction_failed"
                else:
                    html_text = _extract_text_from_html(content_bytes)
                    if html_text:
                        has_body = bool(re.search(r'(Introduction|Methods|Results|Discussion|Background|Materials and Methods|Study Design|Participants)', html_text, re.IGNORECASE))
                        record["sources"]["unpaywall"]["has_body_sections"] = has_body
                        if has_body:
                            # Only set fulltext_text if we have body sections
                            record["fulltext_text"] = html_text
                            if format_type == "html_aggressive_scrape":
                                record["sources"]["unpaywall"]["status"] = "ok_html_aggressive"
                            elif format_type == "html_doi_fallback":
                                record["sources"]["unpaywall"]["status"] = "ok_html_doi_fallback"
                            else:
                                record["sources"]["unpaywall"]["status"] = "ok_html"
                            return (pmid or doi or "unknown", record)
                        else:
                            # HTML extracted but no body sections - allow other sources to try
                            if format_type == "html_aggressive_scrape":
                                record["sources"]["unpaywall"]["status"] = "html_aggressive_abstract_only"
                            elif format_type == "html_doi_fallback":
                                record["sources"]["unpaywall"]["status"] = "html_doi_fallback_abstract_only"
                            else:
                                record["sources"]["unpaywall"]["status"] = "html_abstract_only"
                    else:
                        # Track failed extractions by format type
                        if format_type == "html_aggressive_scrape":
                            record["sources"]["unpaywall"]["status"] = "html_aggressive_extraction_failed"
                        elif format_type == "html_doi_fallback":
                            record["sources"]["unpaywall"]["status"] = "html_doi_fallback_extraction_failed"
                        else:
                            record["sources"]["unpaywall"]["status"] = "html_extraction_failed"
        except Exception as e:
            logger.debug(f"Unpaywall fallback failed for {doi}: {e}")
            record["sources"]["unpaywall"] = {"status": "error", "error": str(e)}

    # 4) Scrape (DOI landing / resolver)
    if not record["fulltext_text"] and doi:
        scraped = await _scrape_doi_aggressive(client, doi)
        if scraped:
            url, content_bytes, format_type = scraped
            record.setdefault("sources", {}).setdefault("unpaywall", {})
            record["sources"]["unpaywall"].update({"url": url, "format": format_type, "content_bytes": len(content_bytes)})
            if format_type == "pdf":
                pdf_text = _extract_text_from_pdf(content_bytes)
                if pdf_text:
                    has_body = bool(re.search(r'(Introduction|Methods|Results|Discussion|Background|Materials and Methods|Study Design|Participants)', pdf_text, re.IGNORECASE))
                    record["sources"]["unpaywall"]["has_body_sections"] = has_body
                    if has_body:
                        # Only set fulltext_text if we have body sections
                        record["fulltext_text"] = pdf_text
                        record["sources"]["unpaywall"]["status"] = "ok_pdf_aggressive"
                        return (pmid or doi or "unknown", record)
                    else:
                        # PDF extracted but no body sections - allow abstract fallback
                        record["sources"]["unpaywall"]["status"] = "pdf_aggressive_abstract_only"
                else:
                    # PDF fetch succeeded but extraction failed - still track it
                    record["sources"]["unpaywall"]["status"] = "pdf_aggressive_extraction_failed"
            else:
                html_text = _extract_text_from_html(content_bytes)
                if html_text:
                    has_body = bool(re.search(r'(Introduction|Methods|Results|Discussion|Background|Materials and Methods|Study Design|Participants)', html_text, re.IGNORECASE))
                    record["sources"]["unpaywall"]["has_body_sections"] = has_body
                    if has_body:
                        # Only set fulltext_text if we have body sections
                        record["fulltext_text"] = html_text
                        record["sources"]["unpaywall"]["status"] = "ok_html_aggressive"
                        return (pmid or doi or "unknown", record)
                    else:
                        # HTML extracted but no body sections - allow abstract fallback
                        record["sources"]["unpaywall"]["status"] = "html_aggressive_abstract_only"
                else:
                    # HTML fetch succeeded but extraction failed strict validation - still track it
                    record["sources"]["unpaywall"]["status"] = "html_aggressive_extraction_failed"

    # 5) Abstract fallback
    if not record["fulltext_text"] and record["abstract"]:
        record["fulltext_text"] = record["abstract"]
        logger.debug(f"Using PubMed abstract as fallback for {pmid or doi}")

    return (pmid or doi or "unknown", record)

# ============================================================================
# Pipeline + Manifest
# ============================================================================
def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _manifest_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(entries)
    pmc_full = sum(1 for e in entries if e.get("pmc_status") in ("ok", "ok_efetch") and e.get("pmc_has_body", False))
    pmc_abstract = sum(1 for e in entries if e.get("pmc_status") == "abstract_only")
    pmc_total = pmc_full + pmc_abstract
    unpaywall_full = sum(1 for e in entries if e.get("unpaywall_status") in ("ok_pdf", "ok_html", "ok_html_doi_fallback", "ok_html_aggressive") and e.get("unpaywall_has_body", False))
    unpaywall_abstract = sum(1 for e in entries if e.get("unpaywall_status") in ("abstract_only", "html_abstract_only"))
    unpaywall_total = unpaywall_full + unpaywall_abstract
    unpaywall_pdf = sum(1 for e in entries if e.get("unpaywall_status") == "ok_pdf")
    unpaywall_html = sum(1 for e in entries if e.get("unpaywall_status") == "ok_html")
    unpaywall_doi_fallback = sum(1 for e in entries if e.get("unpaywall_status") == "ok_html_doi_fallback")
    unpaywall_aggressive = sum(1 for e in entries if e.get("unpaywall_status") == "ok_html_aggressive")
    full_text_total = sum(1 for e in entries if e.get("pmc_has_body", False) or e.get("unpaywall_has_body", False))
    no_fulltext = total - full_text_total
    europe_pmc_ok = sum(1 for e in entries if e.get("europe_pmc_status") == "ok_xml")
    return {
        "total": total,
        "pmc_total": pmc_total,
        "pmc_full_text": pmc_full,
        "pmc_abstract_only": pmc_abstract,
        "pmc_percent": round((pmc_total / total) * 100, 2) if total else 0.0,
        "unpaywall_total": unpaywall_total,
        "unpaywall_full_text": unpaywall_full,
        "unpaywall_rescued": sum(1 for e in entries if e.get("pmc_status") == "abstract_only" and e.get("unpaywall_has_body", False)),
        "unpaywall_percent": round((unpaywall_total / total) * 100, 2) if total else 0.0,
        "unpaywall_pdf_count": unpaywall_pdf,
        "unpaywall_html_count": unpaywall_html,
        "unpaywall_doi_fallback_count": unpaywall_doi_fallback,
        "unpaywall_aggressive_count": unpaywall_aggressive,
        "europe_pmc_fulltext": europe_pmc_ok,
        "full_text_with_body": full_text_total,
        "full_text_percent": round((full_text_total / total) * 100, 2) if total else 0.0,
        "abstract_only_final": no_fulltext,
        "abstract_only_percent": round((no_fulltext / total) * 100, 2) if total else 0.0,
        "pmc_ok": pmc_total,
        "pmc_ok_percent": round((pmc_total / total) * 100, 2) if total else 0.0
    }

def fetch_fulltexts_for_jsonl(
    jsonl_path: Path,
    store_dir: Path,
    manifest_dir: Path,
    max_concurrency: int = 8,
    limit: Optional[int] = None,
    overwrite: bool = False
) -> Dict[str, Any]:
    _ensure_dir(store_dir)
    _ensure_dir(manifest_dir)
    papers = list(_read_jsonl(jsonl_path))
    if limit:
        papers = papers[:limit]
    entries: List[Dict[str, Any]] = []
    saved_count = 0
    skipped_existing = 0
    skipped_with_fulltext = 0
    processed = 0
    total_to_fetch = len(papers)

    async def _bounded_worker(
        sem: asyncio.Semaphore,
        client: httpx.AsyncClient,
        paper: Dict[str, Any],
        rate_limiter: asyncio.Semaphore,
        store_dir: Path,
        overwrite: bool
    ) -> Tuple[str, Dict[str, Any], bool]:
        async with sem:
            pmid = paper.get("pmid")
            doi = paper.get("doi")
            safe_key = _safe_key_from(pmid, doi)
            store_path = _sharded_store_path(store_dir, safe_key)
            if store_path.exists() and not overwrite:
                try:
                    with open(store_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    has_fulltext = (
                        existing.get("fulltext_text") and 
                        (existing.get("sources", {}).get("pmc", {}).get("has_body_sections") or
                         existing.get("sources", {}).get("unpaywall", {}).get("has_body_sections"))
                    )
                    if has_fulltext:
                        return (pmid or doi or "unknown", existing, True)
                except:
                    pass
            key, data = await _fetch_one_fulltext(client, paper, rate_limiter)
            return (key, data, False)

    async def _run() -> Dict[str, Any]:
        nonlocal saved_count, skipped_existing, skipped_with_fulltext, processed
        sem = asyncio.Semaphore(max_concurrency)
        rate_limiter = asyncio.Semaphore(1)  # serialize NCBI calls with delays
        # per-source lift counters
        lift = {
            "pmc": 0,
            "epmc": 0,
            "upw_pdf": 0,
            "upw_html": 0,
            "scrape_pdf": 0,
            "scrape_html": 0
        }
        logger.info(f"Starting fulltext fetch for {total_to_fetch} papers")
        logger.info(f"Using {'API key' if NCBI_API_KEY else 'no API key'} - rate limit: ~{1/RATE_LIMIT_DELAY:.1f} req/sec")
        logger.info(f"Smart skip enabled: Will check for existing fulltext in workers (no wasted API calls)")
        start_time = time.time()
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=HEADERS) as client:
            tasks = [ _bounded_worker(sem, client, p, rate_limiter, store_dir, overwrite) for p in papers ]
            for coro in asyncio.as_completed(tasks):
                processed += 1
                try:
                    key, data, was_skipped = await coro
                except Exception as e:
                    logger.error(f"worker error: {e}")
                    continue
                pmid = data.get("pmid")
                doi = data.get("doi")
                pmc_status = (data.get("sources", {}).get("pmc", {}) or {}).get("status", "none")
                unpaywall_status = (data.get("sources", {}).get("unpaywall", {}) or {}).get("status", "none")
                safe_key = _safe_key_from(pmid, doi)
                store_path = _sharded_store_path(store_dir, safe_key)
                if was_skipped:
                    skipped_existing += 1
                    skipped_with_fulltext += 1
                else:
                    _write_json_atomic(store_path, data)
                    saved_count += 1
                pmc_source = (data.get("sources", {}).get("pmc", {}) or {})
                unpaywall_source = (data.get("sources", {}).get("unpaywall", {}) or {})
                europe_pmc_source = (data.get("sources", {}).get("europe_pmc", {}) or {})
                
                # increment lift counters based on first winning source
                if data.get("fulltext_text") and not was_skipped:
                    if pmc_source.get("has_body_sections"):
                        lift["pmc"] += 1
                    elif europe_pmc_source.get("status") == "ok_xml":
                        lift["epmc"] += 1
                    elif unpaywall_source.get("status") == "ok_pdf":
                        lift["upw_pdf"] += 1
                    elif unpaywall_source.get("status") in ("ok_html", "ok_html_doi_fallback"):
                        lift["upw_html"] += 1
                    elif unpaywall_source.get("status") == "ok_html_aggressive":
                        lift["scrape_html"] += 1
                
                entries.append({
                    "pmid": pmid,
                    "doi": doi,
                    "stored_path": str(store_path.resolve()),
                    "pmc_status": pmc_source.get("status", "none"),
                    "pmc_has_body": pmc_source.get("has_body_sections", False),
                    "unpaywall_status": unpaywall_source.get("status", "none"),
                    "unpaywall_has_body": unpaywall_source.get("has_body_sections", False),
                    "europe_pmc_status": europe_pmc_source.get("status", "none")
                })
                if processed % 50 == 0 or processed == total_to_fetch:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (total_to_fetch - processed) / rate if rate > 0 else 0
                    logger.info(f"Progress: {processed}/{total_to_fetch} ({processed/total_to_fetch*100:.1f}%) | "
                               f"Rate: {rate:.2f}/sec | ETA: {eta/60:.1f}min | "
                               f"Skipped: {skipped_with_fulltext}")
        manifest_stats = _manifest_stats(entries)
        elapsed = time.time() - start_time
        status_counts = {}
        for e in entries:
            status = e.get("pmc_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        fulltext_count = manifest_stats["full_text_with_body"]
        abstract_only = manifest_stats["abstract_only_final"]
        total_bytes_saved = 0
        for e in entries:
            if e.get("pmc_status") in ("ok", "ok_efetch"):
                total_bytes_saved += 30000  # estimate
        new_fulltext = sum(1 for e in entries if e.get("pmc_has_body") or e.get("unpaywall_has_body")) - skipped_with_fulltext
        manifest = {
            "store_dir": str(store_dir.resolve()),
            **manifest_stats,
            "lift": lift,
            "saved": saved_count,
            "skipped_existing": skipped_existing,
            "skipped_with_fulltext": skipped_with_fulltext,
            "new_fulltext_fetched": new_fulltext,
            "attempted_upgrades": saved_count - new_fulltext,
            "status_breakdown": status_counts,
            "content_breakdown": {
                "fulltext_available": fulltext_count,
                "fulltext_percent": round(fulltext_count / len(entries) * 100, 2) if entries else 0,
                "abstract_only": abstract_only,
                "abstract_only_percent": round(abstract_only / len(entries) * 100, 2) if entries else 0
            },
            "storage_estimate_mb": round(total_bytes_saved / (1024 * 1024), 2),
            "elapsed_sec": round(elapsed, 2),
            "rate_per_sec": round(len(entries) / elapsed, 3) if elapsed > 0 else 0,
            "entries": entries,
        }
        manifest_path = manifest_dir / "fulltext_manifest.json"
        _write_json_atomic(manifest_path, manifest)
        logger.info(f"Fulltext fetch complete: {manifest_stats['pmc_ok']}/{manifest_stats['total']} successful ({manifest_stats['pmc_ok_percent']}%)")
        logger.info(f"Content breakdown: {fulltext_count} full-text, {abstract_only} abstract-only")
        logger.info(f"New fulltext fetched: {new_fulltext} papers")
        logger.info(f"Saved: {saved_count} new files, Skipped: {skipped_existing} existing (including {skipped_with_fulltext} with fulltext)")
        logger.info(f"Europe PMC contribution: {manifest_stats.get('europe_pmc_fulltext', 0)} papers")
        logger.info(f"Unpaywall contribution: {manifest_stats.get('unpaywall_full_text', 0)} papers ({manifest_stats.get('unpaywall_rescued', 0)} rescued from abstract-only)")
        logger.info(f"  - PDF extractions: {manifest_stats.get('unpaywall_pdf_count', 0)}")
        logger.info(f"  - HTML extractions: {manifest_stats.get('unpaywall_html_count', 0)}")
        logger.info(f"  - DOI landing page fallback: {manifest_stats.get('unpaywall_doi_fallback_count', 0)}")
        logger.info(f"  - Aggressive scraping: {manifest_stats.get('unpaywall_aggressive_count', 0)}")
        logger.info(f"Status breakdown: {status_counts}")
        logger.info(f"Lift → PMC:{lift['pmc']}  EPMC:{lift['epmc']}  UPW(pdf):{lift['upw_pdf']}  UPW(html):{lift['upw_html']}  SCRAPE(pdf):{lift['scrape_pdf']}  SCRAPE(html):{lift['scrape_html']}")
        logger.info(f"Estimated storage: {manifest['storage_estimate_mb']} MB")
        return manifest

    return asyncio.run(_run())

if __name__ == "__main__":
    import argparse
    import datetime
    log_dir = PROJECT_ROOT / "logs" / "fulltext_fetcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"fulltext_fetch_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger.info(f"Logging to: {log_file}")
    parser = argparse.ArgumentParser(
        description="Fetch PMC/EuropePMC/Unpaywall full texts for selected papers JSONL (centralized store)",
        epilog="""
Environment Variables:
  NCBI_API_KEY          NCBI E-utilities API key (increases rate limit from 3/sec to 10/sec)
  FULLTEXT_STORE_DIR    Override default store location (default: data/fulltext_store)
  UNPAYWALL_EMAIL       Email for Unpaywall API (required)
"""
    )
    parser.add_argument("--jsonl", required=True, help="Path to selected papers JSONL")
    parser.add_argument("--store", required=False, help="Central fulltext store dir (default: PROJECT_ROOT/data/fulltext_store)")
    parser.add_argument("--manifest", required=False, help="Run manifest output dir (default: selected jsonl parent)")
    parser.add_argument("--concurrency", type=int, default=8, help="Max concurrent requests (default: 8)")
    parser.add_argument("--limit", type=int, help="Optional limit of papers to process")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing stored fulltexts")
    args = parser.parse_args()
    default_store = PROJECT_ROOT / "data" / "fulltext_store"
    store_dir = Path(args.store).resolve() if args.store else default_store
    manifest_dir = Path(args.manifest).resolve() if args.manifest else Path(args.jsonl).resolve().parent
    print(f"\n{'='*60}")
    print("FULLTEXT FETCHER")
    print(f"{'='*60}")
    print(f"Input: {args.jsonl}")
    print(f"Store: {store_dir}")
    print(f"Manifest: {manifest_dir}")
    print(f"Concurrency: {args.concurrency}")
    if args.limit:
        print(f"Limit: {args.limit} papers")
    print(f"{'='*60}\n")
    manifest = fetch_fulltexts_for_jsonl(
        Path(args.jsonl),
        store_dir,
        manifest_dir,
        max_concurrency=args.concurrency,
        limit=args.limit,
        overwrite=args.overwrite
    )
    print(f"\n{'='*60}")
    print("FETCH COMPLETE")
    print(f"{'='*60}")
    print(json.dumps({k: v for k, v in manifest.items() if k != 'entries'}, indent=2))
    print(f"{'='*60}\n")
