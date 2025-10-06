"""
Unified full-text fetcher for selected PubMed papers.

Strategy:
  1) Prefer PubMed Central (PMC) Open Access when linked from PubMed (via ELink).
  2) Save raw PMC XML (and a lightly stripped text) when available.
  3) Record DOI/publisher info for possible downstream retrieval (PDF/HTML),
     but do not aggressively crawl publisher sites here.

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
UNPAYWALL_API_BASE = "https://api.unpaywall.org/v2"

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
HEADERS = {
    "User-Agent": "EvidentFit-Fulltext-Fetcher/1.0 (+https://evidentfit.com; contact: research@evidentfit.com)"
}

# NCBI rate limiting: 3 req/sec without API key, 10 req/sec with key
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
RATE_LIMIT_DELAY = 0.34 if not NCBI_API_KEY else 0.11  # Conservative: ~3/sec or ~9/sec
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 5, 15]  # Exponential backoff for 429 errors

# Unpaywall configuration
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "research@evidentfit.com")  # Required
ENABLE_UNPAYWALL = os.getenv("ENABLE_UNPAYWALL", "true").lower() == "true"

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
    """
    Clean up common Unicode issues in scientific text.
    - Normalize Unicode to NFKD (compatibility decomposition)
    - Replace common problematic characters
    - Fix smart quotes, em dashes, etc.
    """
    # Normalize Unicode
    text = unicodedata.normalize('NFKD', text)
    
    # Replace common problematic characters
    replacements = {
        '\u2019': "'",  # Right single quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u2212': '-',  # Minus sign
        '\u00a0': ' ',  # Non-breaking space
        '\u2009': ' ',  # Thin space
        '\u200b': '',   # Zero-width space
        '\xa0': ' ',    # Non-breaking space (another code)
        '\u2032': "'",  # Prime (often misused as apostrophe)
        '\u2033': "''", # Double prime
        '\u00b0': ' degrees ',  # Degree symbol
        '\u00d7': 'x',  # Multiplication sign
        '\u2264': '<=', # Less than or equal
        '\u2265': '>=', # Greater than or equal
        '\u00b1': '+/-',# Plus-minus
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove any remaining non-ASCII characters that slipped through
    # (but keep basic Latin and common scientific symbols)
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    return text

def _extract_article_content(xml_text: str) -> str:
    """
    Extract comprehensive research content from PMC XML.
    
    KEEPS:
    - Title, abstract, full body text
    - Tables (simplified to text)
    - Figure captions
    - Statistical details, effect sizes, p-values
    - Dosing protocols, safety data
    - Population characteristics
    
    REMOVES:
    - Journal metadata, author affiliations
    - Reference lists (just the citations section)
    - Complex formatting, nested structures
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(xml_text, 'lxml-xml')
        
        parts = []
        
        # Title
        title_tag = soup.find('article-title')
        if title_tag:
            title = title_tag.get_text(' ', strip=True)
            parts.append(f"TITLE:\n{title}\n")
        
        # Abstract
        abstract_tag = soup.find('abstract')
        if abstract_tag:
            # Remove any nested title/label tags but keep content
            for tag in abstract_tag.find_all(['title', 'label']):
                tag.decompose()
            abstract_text = abstract_tag.get_text(' ', strip=True)
            if abstract_text:
                parts.append(f"ABSTRACT:\n{abstract_text}\n")
        
        # Main body content
        body_tag = soup.find('body')
        if body_tag:
            # Remove only the big non-content sections
            for tag in body_tag.find_all(['ref-list', 'fn-group', 'ack']):
                tag.decompose()
            
            # Extract section-by-section
            sections = body_tag.find_all('sec', recursive=False)  # Only top-level sections
            for sec in sections:
                # Get section title if present
                sec_title = sec.find('title')
                sec_name = sec_title.get_text(strip=True) if sec_title else ""
                
                if sec_name:
                    parts.append(f"\n{sec_name.upper()}:")
                
                # Extract paragraphs
                paragraphs = sec.find_all('p', recursive=True)
                for p in paragraphs:
                    p_text = p.get_text(' ', strip=True)
                    if p_text and len(p_text) > 15:  # Keep most paragraphs
                        # Clean up common XML artifacts
                        p_text = re.sub(r'\s+', ' ', p_text)  # Normalize whitespace
                        parts.append(p_text)
                
                # Extract table content (simplified to text)
                tables = sec.find_all('table-wrap')
                for table_wrap in tables:
                    # Get table caption/title
                    caption = table_wrap.find('caption')
                    if caption:
                        cap_text = caption.get_text(' ', strip=True)
                        if cap_text:
                            parts.append(f"TABLE: {cap_text}")
                    
                    # Get table body text (simplified)
                    table = table_wrap.find('table')
                    if table:
                        # Extract headers
                        headers = []
                        thead = table.find('thead')
                        if thead:
                            for th in thead.find_all(['th', 'td']):
                                h_text = th.get_text(' ', strip=True)
                                if h_text:
                                    headers.append(h_text)
                        
                        # Extract rows
                        rows = []
                        tbody = table.find('tbody')
                        if tbody:
                            for tr in tbody.find_all('tr')[:20]:  # Limit to 20 rows to avoid huge tables
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
                            parts.extend(rows[:15])  # Keep first 15 rows
                
                # Extract figure captions
                figs = sec.find_all('fig')
                for fig in figs:
                    caption = fig.find('caption')
                    if caption:
                        cap_text = caption.get_text(' ', strip=True)
                        if cap_text:
                            parts.append(f"FIGURE: {cap_text}")
        
        # If we got content, join it with proper paragraph breaks
        if parts:
            full_text = "\n\n".join(parts)
            # Clean Unicode issues
            full_text = _clean_unicode(full_text)
            # Remove citation brackets: [ ], [ , ], [ , , ], etc.
            full_text = re.sub(r'\[\s*(?:,\s*)*\]', '', full_text)
            # Remove empty parentheses from removed citations
            full_text = re.sub(r'\(\s*(?:,\s*)*\)', '', full_text)
            # Clean up extra spaces and punctuation from removed citations
            full_text = re.sub(r'\s+([.,;:)])', r'\1', full_text)  # Remove space before punctuation
            full_text = re.sub(r'([.,;:])\s*\1+', r'\1', full_text)  # Remove duplicate punctuation
            # Final cleanup: normalize whitespace within lines but preserve paragraph breaks
            lines = full_text.split('\n')
            lines = [re.sub(r'  +', ' ', line).strip() for line in lines]
            full_text = '\n'.join(line for line in lines if line)
            return full_text
    except Exception as e:
        logger.debug(f"Article content extraction failed, falling back to simple strip: {e}")
    
    # Fallback: simple tag removal
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
    """
    Returns PMCID like 'PMC123456' if PubMed -> PMC link exists, else None.
    Includes rate limiting and retry logic for 429 errors.
    """
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "retmode": "json",
        "id": pmid
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    
    for attempt in range(MAX_RETRIES):
        try:
            async with rate_limiter:
                r = await client.get(f"{EUTILS_BASE}/elink.fcgi", params=params)
                await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limit delay
                
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
    """
    Use PMC OA service to get XML/PDF links if available.
    Note: PMC OA service is separate from E-utilities and has more generous limits.
    """
    params = {"id": pmcid}
    try:
        async with rate_limiter:
            r = await client.get(NCBI_PMC_OA, params=params)
            await asyncio.sleep(RATE_LIMIT_DELAY * 0.5)  # Lighter rate limit for PMC OA
            r.raise_for_status()
        
        xml = xmltodict.parse(r.text)
        xml_url = None
        pdf_url = None
        # structure: <OA><records><record><link format="pdf" href="...">...</link>...</record></records></OA>
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
    """Fetch text content from URL, accepting various content types."""
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None
        
        content_type = r.headers.get("content-type", "").lower()
        # Accept XML, HTML, plain text
        if any(ct in content_type for ct in ["xml", "html", "text", "plain"]):
            return r.text
        
        # If no content-type hint but looks like text, try it
        if r.text and r.text.strip().startswith("<"):
            return r.text
            
        return None
    except Exception:
        return None

# ============================================================================
# Unpaywall Integration
# ============================================================================

def _extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 50) -> Optional[str]:
    """Extract text from PDF bytes. Returns None if extraction fails."""
    if not PdfReader:
        logger.warning("pypdf not available - cannot extract PDF text")
        return None
    
    try:
        import io
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        
        text_parts = []
        pages_to_read = min(len(reader.pages), max_pages)
        
        for i in range(pages_to_read):
            try:
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.debug(f"Failed to extract page {i}: {e}")
                continue
        
        if not text_parts:
            return None
        
        full_text = "\n\n".join(text_parts)
        
        # Basic cleanup for PDFs
        # Remove common PDF artifacts
        full_text = re.sub(r'\s+', ' ', full_text)  # Normalize whitespace
        full_text = re.sub(r'(\w)-\s+(\w)', r'\1\2', full_text)  # Fix hyphenation
        full_text = full_text.replace('\x00', '')  # Remove null bytes
        
        # Quality check: must have reasonable content
        if len(full_text) < 500:
            return None
        
        return full_text
        
    except Exception as e:
        logger.debug(f"PDF extraction failed: {e}")
        return None

async def _fetch_unpaywall(
    client: httpx.AsyncClient,
    doi: str,
) -> Optional[Tuple[str, bytes, str]]:
    """
    Query Unpaywall for DOI and fetch PDF if available.
    Returns (url, pdf_bytes, format) or None.
    format is 'pdf' or 'html'
    """
    if not doi or not ENABLE_UNPAYWALL:
        return None
    
    try:
        # Query Unpaywall API
        api_url = f"{UNPAYWALL_API_BASE}/{doi}"
        params = {"email": UNPAYWALL_EMAIL}
        
        r = await client.get(api_url, params=params)
        if r.status_code != 200:
            return None
        
        data = r.json()
        best_oa = data.get("best_oa_location")
        if not best_oa:
            return None
        
        # Prefer PDF, fallback to HTML
        pdf_url = best_oa.get("url_for_pdf")
        html_url = best_oa.get("url")
        
        if pdf_url:
            # Fetch PDF
            pdf_r = await client.get(pdf_url, follow_redirects=True)
            if pdf_r.status_code == 200 and len(pdf_r.content) > 10000:  # At least 10KB
                return (pdf_url, pdf_r.content, "pdf")
        
        if html_url:
            # Fetch HTML (basic, for future enhancement)
            html_r = await client.get(html_url, follow_redirects=True)
            if html_r.status_code == 200 and len(html_r.content) > 1000:
                return (html_url, html_r.content, "html")
        
        return None
        
    except Exception as e:
        logger.debug(f"Unpaywall fetch failed for {doi}: {e}")
        return None

async def _fetch_one_fulltext(
    client: httpx.AsyncClient,
    paper: Dict[str, Any],
    rate_limiter: asyncio.Semaphore
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (pmid_or_id, fulltext_record_dict)
    """
    pmid = str(paper.get("pmid") or "").strip()
    doi = (paper.get("doi") or "").strip()
    abstract = (paper.get("content") or "").strip()
    record: Dict[str, Any] = {
        "pmid": pmid or None,
        "doi": doi or None,
        "sources": {
            "pmc": {"pmcid": None, "xml_url": None, "pdf_url": None, "status": "none", "fulltext_bytes": None},
            "doi": {"url": f"https://doi.org/{doi}" if doi else None, "status": "hint_only"}
        },
        "fulltext_text": None,  # Extracted clean text only (no raw XML to save space)
        "abstract": abstract
    }

    # Try PMC route first if pmid present
    if pmid:
        try:
            pmcid = await _elink_pubmed_to_pmc(client, pmid, rate_limiter)
            if pmcid:
                record["sources"]["pmc"]["pmcid"] = pmcid
                links = await _pmc_oa_links(client, pmcid, rate_limiter)
                record["sources"]["pmc"].update(links)
                xml_url = links.get("xml_url")
                
                # If OA service provided XML URL, use it
                if xml_url:
                    xml_text = await _fetch_text(client, xml_url)
                    if xml_text:
                        # Extract content but don't store raw XML (saves ~200KB per paper)
                        fulltext = _extract_article_content(xml_text)
                        record["fulltext_text"] = fulltext
                        record["sources"]["pmc"]["fulltext_bytes"] = len(xml_text)
                        
                        # Quality check: actual body sections or just abstract?
                        has_body = bool(re.search(
                            r'(INTRODUCTION|METHODS|RESULTS|DISCUSSION|BACKGROUND|MATERIALS AND METHODS|STUDY DESIGN|PARTICIPANTS):',
                            fulltext
                        ))
                        
                        if has_body:
                            record["sources"]["pmc"]["status"] = "ok"
                            record["sources"]["pmc"]["has_body_sections"] = True
                        else:
                            record["sources"]["pmc"]["status"] = "abstract_only"
                            record["sources"]["pmc"]["has_body_sections"] = False
                        
                        return (pmid or doi or "unknown", record)
                
                # Fallback: Use EFetch to get PMC XML (works for all PMC articles, not just OA)
                # This endpoint doesn't require the OA service
                efetch_params = {
                    "db": "pmc",
                    "id": pmcid,
                    "rettype": "xml"
                }
                if NCBI_API_KEY:
                    efetch_params["api_key"] = NCBI_API_KEY
                
                fallback_xml_url = f"{EUTILS_BASE}/efetch.fcgi"
                try:
                    async with rate_limiter:
                        r = await client.get(fallback_xml_url, params=efetch_params)
                        await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limit delay
                        
                    if r.status_code == 200 and r.text and len(r.text) > 1000:
                        xml_text = r.text
                        # Extract content but don't store raw XML (saves ~200KB per paper)
                        fulltext = _extract_article_content(xml_text)
                        record["fulltext_text"] = fulltext
                        record["sources"]["pmc"]["xml_url"] = f"{fallback_xml_url}?db=pmc&id={pmcid}&rettype=xml"
                        record["sources"]["pmc"]["fulltext_bytes"] = len(xml_text)
                        
                        # Quality check: Do we have actual body sections or just title+abstract?
                        has_body = bool(re.search(
                            r'(INTRODUCTION|METHODS|RESULTS|DISCUSSION|BACKGROUND|MATERIALS AND METHODS|STUDY DESIGN|PARTICIPANTS):',
                            fulltext
                        ))
                        
                        if has_body:
                            record["sources"]["pmc"]["status"] = "ok_efetch"
                            record["sources"]["pmc"]["has_body_sections"] = True
                            logger.debug(f"Full text with body for {pmcid} ({len(xml_text)} bytes → {len(fulltext)} chars)")
                        else:
                            record["sources"]["pmc"]["status"] = "abstract_only"
                            record["sources"]["pmc"]["has_body_sections"] = False
                            logger.debug(f"Abstract only for {pmcid} ({len(xml_text)} bytes → {len(fulltext)} chars)")
                        
                        return (pmid or doi or "unknown", record)
                except Exception as e:
                    logger.debug(f"EFetch failed for {pmcid}: {e}")
                
                # Still no text? Keep pdf_url as hint; status stays "none"
        except Exception as e:
            record["sources"]["pmc"]["status"] = "error"
            record["sources"]["pmc"]["error"] = str(e)

    # Unpaywall fallback: Try if PMC failed OR returned abstract-only
    pmc_status = record["sources"]["pmc"]["status"]
    needs_unpaywall = pmc_status in ("none", "error", "abstract_only")
    
    if needs_unpaywall and doi and ENABLE_UNPAYWALL:
        try:
            unpaywall_result = await _fetch_unpaywall(client, doi)
            if unpaywall_result:
                url, content_bytes, format_type = unpaywall_result
                
                # Add unpaywall source to record
                record["sources"]["unpaywall"] = {
                    "url": url,
                    "format": format_type,
                    "status": "ok",
                    "content_bytes": len(content_bytes)
                }
                
                if format_type == "pdf":
                    # Extract text from PDF
                    pdf_text = _extract_text_from_pdf(content_bytes)
                    if pdf_text:
                        # Check if we got body sections
                        has_body = bool(re.search(
                            r'(Introduction|Methods|Results|Discussion|Background|Materials and Methods|Study Design|Participants)',
                            pdf_text,
                            re.IGNORECASE
                        ))
                        
                        record["fulltext_text"] = pdf_text
                        record["sources"]["unpaywall"]["has_body_sections"] = has_body
                        
                        if has_body:
                            record["sources"]["unpaywall"]["status"] = "ok_pdf"
                            logger.debug(f"Unpaywall PDF with body for {doi} ({len(content_bytes)} bytes → {len(pdf_text)} chars)")
                        else:
                            record["sources"]["unpaywall"]["status"] = "abstract_only"
                            logger.debug(f"Unpaywall PDF abstract-only for {doi}")
                        
                        # Override PMC abstract-only with Unpaywall full text
                        if pmc_status == "abstract_only" and has_body:
                            logger.info(f"✓ Unpaywall rescued abstract-only PMC: {pmid}")
                        
                        return (pmid or doi or "unknown", record)
                    else:
                        record["sources"]["unpaywall"]["status"] = "extraction_failed"
                
                elif format_type == "html":
                    # Basic HTML handling (future: improve with BeautifulSoup)
                    record["sources"]["unpaywall"]["status"] = "html_available"
                    # For now, don't extract HTML - keep PMC abstract or original abstract
        
        except Exception as e:
            logger.debug(f"Unpaywall fallback failed for {doi}: {e}")
            record["sources"]["unpaywall"] = {"status": "error", "error": str(e)}

    # Return what we have (PMC, Unpaywall, or just hints)
    return (pmid or doi or "unknown", record)

async def _bounded_worker(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    paper: Dict[str, Any],
    rate_limiter: asyncio.Semaphore
) -> Tuple[str, Dict[str, Any]]:
    async with sem:
        return await _fetch_one_fulltext(client, paper, rate_limiter)

def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _manifest_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate comprehensive stats tracking PMC and Unpaywall sources.
    """
    total = len(entries)
    
    # PMC stats
    pmc_full = sum(1 for e in entries if e.get("pmc_status") in ("ok", "ok_efetch") and e.get("pmc_has_body", False))
    pmc_abstract = sum(1 for e in entries if e.get("pmc_status") == "abstract_only")
    pmc_total = pmc_full + pmc_abstract
    
    # Unpaywall stats
    unpaywall_full = sum(1 for e in entries if e.get("unpaywall_status") == "ok_pdf" and e.get("unpaywall_has_body", False))
    unpaywall_abstract = sum(1 for e in entries if e.get("unpaywall_status") == "abstract_only")
    unpaywall_total = unpaywall_full + unpaywall_abstract
    
    # Combined full-text count (PMC OR Unpaywall with body)
    full_text_total = sum(1 for e in entries if e.get("pmc_has_body", False) or e.get("unpaywall_has_body", False))
    
    # Papers with no full text from either source
    no_fulltext = total - full_text_total
    
    return {
        "total": total,
        
        # PMC breakdown
        "pmc_total": pmc_total,
        "pmc_full_text": pmc_full,
        "pmc_abstract_only": pmc_abstract,
        "pmc_percent": round((pmc_total / total) * 100, 2) if total else 0.0,
        
        # Unpaywall breakdown
        "unpaywall_total": unpaywall_total,
        "unpaywall_full_text": unpaywall_full,
        "unpaywall_rescued": sum(1 for e in entries if e.get("pmc_status") == "abstract_only" and e.get("unpaywall_has_body", False)),
        "unpaywall_percent": round((unpaywall_total / total) * 100, 2) if total else 0.0,
        
        # Overall full-text coverage
        "full_text_with_body": full_text_total,
        "full_text_percent": round((full_text_total / total) * 100, 2) if total else 0.0,
        "abstract_only_final": no_fulltext,
        "abstract_only_percent": round((no_fulltext / total) * 100, 2) if total else 0.0,
        
        # Legacy compatibility
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
    """
    Read selected papers jsonl and fetch PMC full texts when available.
    Saves each full text ONCE into a centralized sharded store.
    Writes a per-run MANIFEST ONLY into `manifest_dir`.
    Returns a manifest dict with counts and entry list.
    """
    _ensure_dir(store_dir)
    _ensure_dir(manifest_dir)
    papers = list(_read_jsonl(jsonl_path))
    if limit:
        papers = papers[:limit]

    entries: List[Dict[str, Any]] = []
    saved_count = 0
    skipped_existing = 0
    processed = 0
    total_to_fetch = len(papers)

    async def _run() -> Dict[str, Any]:
        nonlocal saved_count, skipped_existing, processed
        sem = asyncio.Semaphore(max_concurrency)
        # Add a separate rate limiter for NCBI API calls
        rate_limiter = asyncio.Semaphore(1)  # Serialize NCBI calls with delays
        
        logger.info(f"Starting fulltext fetch for {total_to_fetch} papers")
        logger.info(f"Using {'API key' if NCBI_API_KEY else 'no API key'} - rate limit: ~{1/RATE_LIMIT_DELAY:.1f} req/sec")
        logger.info(f"Estimated time: ~{total_to_fetch * RATE_LIMIT_DELAY / 60:.1f} minutes")
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=HEADERS) as client:
            tasks = [ _bounded_worker(sem, client, p, rate_limiter) for p in papers ]
            for coro in asyncio.as_completed(tasks):
                processed += 1
                if processed % 50 == 0 or processed == total_to_fetch:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (total_to_fetch - processed) / rate if rate > 0 else 0
                    logger.info(f"Progress: {processed}/{total_to_fetch} ({processed/total_to_fetch*100:.1f}%) | "
                               f"Rate: {rate:.2f}/sec | ETA: {eta/60:.1f}min")
                try:
                    key, data = await coro
                except Exception as e:
                    logger.error(f"worker error: {e}")
                    continue
                pmid = data.get("pmid")
                doi = data.get("doi")
                pmc_status = (data.get("sources", {}).get("pmc", {}) or {}).get("status", "none")
                safe_key = _safe_key_from(pmid, doi)
                store_path = _sharded_store_path(store_dir, safe_key)
                if store_path.exists() and not overwrite:
                    skipped_existing += 1
                else:
                    _write_json_atomic(store_path, data)
                    saved_count += 1
                # Extract detailed status for manifest
                pmc_source = (data.get("sources", {}).get("pmc", {}) or {})
                unpaywall_source = (data.get("sources", {}).get("unpaywall", {}) or {})
                
                entries.append({
                    "pmid": pmid,
                    "doi": doi,
                    "stored_path": str(store_path.resolve()),
                    "pmc_status": pmc_source.get("status", "none"),
                    "pmc_has_body": pmc_source.get("has_body_sections", False),
                    "unpaywall_status": unpaywall_source.get("status", "none"),
                    "unpaywall_has_body": unpaywall_source.get("has_body_sections", False)
                })
        # Build detailed stats
        manifest_stats = _manifest_stats(entries)
        elapsed = time.time() - start_time
        
        # Breakdown by status
        status_counts = {}
        for e in entries:
            status = e.get("pmc_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Content type breakdown
        fulltext_count = status_counts.get("ok", 0) + status_counts.get("ok_efetch", 0)
        abstract_only = len(entries) - fulltext_count
        
        # Calculate storage metrics from saved papers
        total_bytes_saved = 0
        for e in entries:
            if e.get("pmc_status") in ("ok", "ok_efetch"):
                # Estimate: fulltext entries are ~30KB each
                total_bytes_saved += 30000
        
        manifest = {
            "store_dir": str(store_dir.resolve()),
            **manifest_stats,
            "saved": saved_count,
            "skipped_existing": skipped_existing,
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
        logger.info(f"Status breakdown: {status_counts}")
        logger.info(f"Saved: {saved_count} new, Skipped: {skipped_existing} existing")
        logger.info(f"Estimated storage: {manifest['storage_estimate_mb']} MB")
        
        return manifest

    return asyncio.run(_run())

if __name__ == "__main__":
    import argparse
    import datetime
    
    # Setup logging for CLI usage - both file and console
    log_dir = PROJECT_ROOT / "logs" / "fulltext_fetcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"fulltext_fetch_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also print to console
        ]
    )
    logger.info(f"Logging to: {log_file}")
    
    parser = argparse.ArgumentParser(
        description="Fetch PMC full texts for selected papers JSONL (centralized store)",
        epilog="""
Environment Variables:
  NCBI_API_KEY          NCBI E-utilities API key (increases rate limit from 3/sec to 10/sec)
  FULLTEXT_STORE_DIR    Override default store location (default: data/fulltext_store)
  
Examples:
  # Fetch for latest run (first 100 papers)
  python -m agents.ingest.get_papers.fulltext_fetcher \\
    --jsonl data/ingest/runs/latest/pm_papers.jsonl --limit 100
  
  # Full fetch with API key for faster processing
  export NCBI_API_KEY="your_key_here"
  python -m agents.ingest.get_papers.fulltext_fetcher \\
    --jsonl data/ingest/runs/latest/pm_papers.jsonl --concurrency 2
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
    print("PMC FULLTEXT FETCHER")
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
