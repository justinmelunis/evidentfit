"""
PubMed E-utilities client for paper fetching

Handles PubMed API calls with rate limiting, retry logic, and chunking
to bypass the 10K result limit. No LLM calls - pure data fetching.
"""

import os
import time
import math
import json
import logging
import httpx
import xmltodict
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Environment variables
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "you@example.com")
NCBI_API_KEY = os.getenv("NCBI_API_KEY")  # optional
MAX_TOTAL_PAPERS = int(os.getenv("MAX_TOTAL_PAPERS", "200000"))

# Multi-Query Strategy - Supplement-specific PubMed queries for comprehensive coverage
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
    "sodium-phosphate": '"sodium phosphate" AND (exercise OR training OR performance OR endurance) AND humans[MeSH]',
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
    "ecdysteroids": '(ecdysterone OR ecdysteroid* OR "20-hydroxyecdysone" OR "20-HE" OR turkesterone) AND (exercise OR training OR performance OR muscle OR strength OR hypertrophy) AND humans[MeSH]',
    "sodium-citrate": '"sodium citrate" AND (exercise OR training OR performance OR endurance) AND humans[MeSH]',
    "alpha-gpc": '("alpha-GPC" OR glycerylphosphorylcholine OR "alpha glycerylphosphorylcholine") AND (exercise OR performance OR strength OR power) AND humans[MeSH]',
    "theacrine": 'theacrine AND (exercise OR training OR performance OR fatigue OR vigilance) AND humans[MeSH]',
    "yohimbine": 'yohimbine AND (exercise OR "weight loss" OR "body composition" OR fat) AND humans[MeSH]',
    "green-tea-extract": '("green tea extract" OR EGCG OR catechin*) AND (exercise OR training OR performance OR "weight loss" OR fat) AND humans[MeSH]',
    "ketone-esters": '("ketone ester" OR "ketone esters" OR "beta-hydroxybutyrate" OR BHB OR "ketone salt*") AND (exercise OR endurance OR performance OR fatigue) AND humans[MeSH]',
    "collagen": '(collagen OR "collagen peptides" OR gelatin) AND (tendon OR ligament OR joint OR recovery OR "muscle" OR "body composition") AND humans[MeSH]',
    "blackcurrant": '("blackcurrant" OR "ribes nigrum") AND (exercise OR performance OR endurance) AND humans[MeSH]',
    "tart-cherry": '("tart cherry" OR Montmorency OR "Prunus cerasus") AND (exercise OR recovery OR performance OR soreness OR DOMS) AND humans[MeSH]',
    "pomegranate": '(pomegranate OR "punica granatum") AND (exercise OR performance OR endurance OR recovery) AND humans[MeSH]',
    "pycnogenol": '(pycnogenol OR "French maritime pine" OR "pine bark extract") AND (exercise OR performance OR endurance OR recovery) AND humans[MeSH]',
    "resveratrol": 'resveratrol AND (exercise OR performance OR endurance OR mitochondrial) AND humans[MeSH]',
    "nac": '("N-acetylcysteine" OR NAC) AND (exercise OR performance OR fatigue OR recovery) AND humans[MeSH]',
    "coq10": '("coenzyme Q10" OR ubiquinone OR ubiquinol) AND (exercise OR performance OR fatigue) AND humans[MeSH]',
    "fenugreek": '(fenugreek OR "Trigonella foenum-graecum") AND (exercise OR strength OR testosterone OR "body composition") AND humans[MeSH]',
    "tongkat-ali": '("tongkat ali" OR "Eurycoma longifolia") AND (exercise OR strength OR testosterone OR fatigue) AND humans[MeSH]',
    "maca": '(maca OR "Lepidium meyenii") AND (exercise OR performance OR fatigue) AND humans[MeSH]',
    "boron": 'boron AND (testosterone OR "body composition" OR strength) AND humans[MeSH]',
    "shilajit": 'shilajit AND (exercise OR performance OR testosterone OR fatigue) AND humans[MeSH]',
    "d-ribose": '("D-ribose" OR ribose) AND (exercise OR performance OR fatigue) AND humans[MeSH]',
    "phosphatidic-acid": '("phosphatidic acid") AND (exercise OR strength OR hypertrophy OR muscle) AND humans[MeSH]',
    "phosphatidylserine": 'phosphatidylserine AND (exercise OR performance OR cortisol OR stress) AND humans[MeSH]',
    "epicatechin": 'epicatechin AND (exercise OR muscle OR strength OR performance) AND humans[MeSH]',
    "red-spinach": '("red spinach" OR amaranthus) AND (nitrate OR exercise OR performance OR endurance) AND humans[MeSH]',
    "synephrine": '("synephrine" OR "bitter orange" OR "citrus aurantium") AND ("weight loss" OR fat OR exercise OR performance) AND humans[MeSH]',
    "garcinia-cambogia": '("garcinia cambogia" OR "hydroxycitric acid" OR HCA) AND ("weight loss" OR "body composition") AND humans[MeSH]',
    "raspberry-ketone": '("raspberry ketone" OR "raspberry ketones") AND ("weight loss" OR "body composition") AND humans[MeSH]',
    "chromium-picolinate": '("chromium picolinate") AND ("weight loss" OR "body composition" OR glucose OR insulin) AND humans[MeSH]',
    "alpha-lipoic-acid": '("alpha-lipoic acid" OR "thioctic acid") AND (exercise OR performance OR insulin OR glucose) AND humans[MeSH]',
    "theanine": '("L-theanine" OR theanine) AND (caffeine OR attention OR reaction OR stress OR exercise) AND humans[MeSH]',
    "hica": '("alpha-hydroxy-isocaproic acid" OR HICA) AND (muscle OR hypertrophy OR strength OR recovery OR soreness) AND humans[MeSH]',
}

# Consolidated query for monthly updates
PM_SEARCH_QUERY = os.getenv("PM_SEARCH_QUERY") or \
    '(creatine OR "beta-alanine" OR caffeine OR citrulline OR nitrate OR "nitric oxide" OR HMB OR "branched chain amino acids" OR BCAA OR tribulus OR "d-aspartic acid" OR betaine OR taurine OR carnitine OR ZMA OR glutamine OR CLA OR ecdysterone OR "deer antler" OR "whey protein" OR "protein supplementation") AND (resistance OR "strength training" OR "1RM" OR hypertrophy OR "lean mass" OR "muscle mass" OR "exercise" OR "athletic performance") AND (humans[MeSH] OR adult OR adults OR participants OR subjects OR volunteers OR athletes) NOT ("nitrogen dioxide" OR NO2 OR pollution OR "cardiac hypertrophy" OR "ventricular hypertrophy" OR "fish" OR "rat" OR "mice" OR "mouse" OR "in vitro" OR "cell culture" OR animals[MeSH])'


def pubmed_esearch(term: str, mindate: Optional[str] = None, maxdate: Optional[str] = None, 
                   retmax: int = 200, retstart: int = 0) -> Dict:
    """
    Search PubMed using ESearch API with retry logic
    
    Args:
        term: Search query
        mindate: Minimum publication date (YYYY/MM/DD format)
        maxdate: Maximum publication date (YYYY/MM/DD format)
        retmax: Maximum number of results to return
        retstart: Starting position for results
        
    Returns:
        Dictionary with search results
    """
    params = {
        "db": "pubmed",
        "retmode": "json",
        "term": term,
        "retmax": str(retmax),
        "retstart": str(retstart),
        "email": NCBI_EMAIL
    }
    
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
        
    if mindate or maxdate:
        params["datetype"] = "pdat"
        if mindate:
            params["mindate"] = mindate
        if maxdate:
            params["maxdate"] = maxdate
    
    # Retry logic for timeouts and transient errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Rate limiting - 1 second between requests
            time.sleep(1.0)
            
            with httpx.Client(timeout=60) as client:
                response = client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params)
                response.raise_for_status()
                
                try:
                    return response.json()
                except Exception as e:
                    logger.error(f"JSON decode error: {e}")
                    logger.error(f"Response content: {response.text[:500]}...")
                    # Try to clean the response
                    import re
                    cleaned_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', response.text)
                    return json.loads(cleaned_text)
                    
        except Exception as e:
            if attempt < max_retries - 1:
                # Check if it's a 429 rate limit error or timeout
                if "429" in str(e) or "Too Many Requests" in str(e):
                    wait_time = (attempt + 1) * 10  # Longer wait for rate limits
                    logger.warning(f"PubMed rate limit hit (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.warning(f"Waiting {wait_time} seconds before retry...")
                elif "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    wait_time = (attempt + 1) * 5  # Standard backoff for timeouts
                    logger.warning(f"PubMed timeout (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.warning(f"Retrying in {wait_time} seconds...")
                else:
                    wait_time = (attempt + 1) * 5  # Standard exponential backoff
                    logger.warning(f"PubMed API error (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.warning(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"PubMed ESearch failed after {max_retries} attempts: {e}")
                raise


def pubmed_efetch_xml(pmids: List[str]) -> Dict:
    """
    Fetch PubMed articles using EFetch API
    
    Args:
        pmids: List of PubMed IDs
        
    Returns:
        Dictionary with article data in XML format
    """
    params = {
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(pmids),
        "email": NCBI_EMAIL
    }
    
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    
    # Rate limiting - 1 second between requests
    time.sleep(1.0)
    
    # Retry logic for PubMed API
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=120) as client:
                response = client.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params=params)
                response.raise_for_status()
                return xmltodict.parse(response.text)
        except Exception as e:
            if attempt < max_retries - 1:
                # Check if it's a 429 rate limit error
                if "429" in str(e) or "Too Many Requests" in str(e):
                    wait_time = (attempt + 1) * 10  # Longer wait for rate limits
                    logger.warning(f"PubMed rate limit hit (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.warning(f"Waiting {wait_time} seconds before retry...")
                else:
                    wait_time = (attempt + 1) * 5  # Standard exponential backoff
                    logger.warning(f"PubMed API error (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.warning(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"PubMed API failed after {max_retries} attempts: {e}")
                raise


def search_supplement_simple(query: str, mindate: Optional[str] = None) -> List[str]:
    """
    Simple search for supplements with <10K results
    
    Args:
        query: PubMed search query
        mindate: Minimum publication date
        
    Returns:
        List of PMIDs
    """
    pmids = []
    retstart = 0
    failed_batches = []
    
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
                logger.warning(f"DYNAMIC CHUNKING DETECTED - Hit 9,999 paper limit during simple search")
                logger.warning(f"Returning {len(pmids):,} papers so far, caller will switch to chunking")
                return pmids
                
        except Exception as e:
            # With retry logic in pubmed_esearch, this should be rare
            # But if it happens after 3 retries, log and continue to next batch
            logger.error(f"Error in simple search at retstart={retstart}: {e}")
            failed_batches.append(retstart)
            
            # Try to continue with next batch
            retstart += 200
            
            # Safety: if too many failures, give up
            if len(failed_batches) >= 5:
                logger.error(f"Too many failed batches ({len(failed_batches)}), stopping simple search")
                break
                
            continue
    
    # Report any paper loss
    if failed_batches:
        logger.warning(f"Simple search WARNING: {len(failed_batches)} batch(es) failed (approximately {len(failed_batches) * 200} papers lost)")
        logger.warning(f"Failed retstart positions: {failed_batches}")
    
    return pmids


def search_supplement_chunked(query: str, start_date: str, total_count: int, 
                             recursion_depth: int = 0) -> List[str]:
    """
    Search using date-based chunks to bypass 10K limit
    
    Args:
        query: PubMed search query
        start_date: Start date for chunking (YYYY/MM/DD format)
        total_count: Total number of results expected
        recursion_depth: Current recursion depth (max 3)
        
    Returns:
        List of PMIDs
    """
    # Prevent infinite recursion
    if recursion_depth >= 3:
        logger.warning(f"Maximum recursion depth reached ({recursion_depth}), stopping chunking")
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
    
    logger.info(f"DYNAMIC CHUNKING: Splitting into ~{estimated_chunks} date ranges ({years_per_chunk:.1f} years each)")
    logger.info(f"Target: {target_per_chunk:,} papers per chunk (staying under 10K limit)")
    if recursion_depth > 0:
        logger.info(f"RECURSIVE CHUNKING: Depth {recursion_depth} (max 3)")
    
    current_dt = start_dt
    chunk_num = 1
    
    while current_dt < end_dt:
        # Calculate end of this chunk
        chunk_end_dt = min(current_dt + timedelta(days=years_per_chunk * 365.25), end_dt)
        
        # Format dates for PubMed
        chunk_start = current_dt.strftime("%Y/%m/%d")
        chunk_end = chunk_end_dt.strftime("%Y/%m/%d")
        
        logger.info(f"CHUNK {chunk_num}: {chunk_start} to {chunk_end}")
        
        # OPTIMIZATION: Check count for this date range FIRST before pulling any papers
        # This lets us decide if we need to sub-chunk BEFORE pulling data
        try:
            count_check = pubmed_esearch(query, mindate=chunk_start, maxdate=chunk_end, retmax=1, retstart=0)
            chunk_total = int(count_check.get("esearchresult", {}).get("count", "0"))
            
            # If this chunk itself exceeds 9,999, recursively chunk it BEFORE pulling papers
            if chunk_total >= 9999:
                logger.warning(f"CHUNK {chunk_num} NEEDS SUB-CHUNKING: {chunk_total:,} papers in this date range (exceeds 9,999 limit)")
                logger.warning(f"Recursively sub-chunking this date range BEFORE pulling papers: {chunk_start} to {chunk_end}")
                
                # Recursively chunk this date range
                chunk_pmids = search_supplement_chunked(
                    query, 
                    chunk_start, 
                    chunk_total,
                    recursion_depth + 1
                )
                logger.info(f"Recursive sub-chunking complete: {len(chunk_pmids):,} papers retrieved")
                
                # Skip to next chunk since we already got all papers via recursion
                logger.info(f"CHUNK {chunk_num} COMPLETE: {len(chunk_pmids):,} papers retrieved (via sub-chunking)")
                all_pmids.extend(chunk_pmids)
                current_dt = chunk_end_dt + timedelta(days=1)
                chunk_num += 1
                continue
                
        except Exception as e:
            logger.error(f"Error checking count for chunk {chunk_num}: {e}")
            logger.warning(f"Proceeding with normal pull despite count check failure")
            chunk_total = 0  # Will be set on first batch
        
        # Normal case: chunk has < 9,999 papers, pull them all
        logger.info(f"CHUNK {chunk_num}: Pulling {chunk_total:,} papers (no sub-chunking needed)")
        chunk_pmids = []
        retstart = 0
        failed_batches = []
        
        while True:
            try:
                # Add date range to query
                batch = pubmed_esearch(query, mindate=chunk_start, maxdate=chunk_end, 
                                     retmax=200, retstart=retstart)
                idlist = batch.get("esearchresult", {}).get("idlist", [])
                
                if not idlist:
                    break
                    
                chunk_pmids.extend(idlist)
                retstart += len(idlist)
                
                # Check if we've reached the end of this chunk
                chunk_total = int(batch.get("esearchresult", {}).get("count", "0"))
                if retstart >= chunk_total:
                    break
                    
            except Exception as e:
                # Log error but track which batch failed - don't break immediately
                logger.error(f"Error in chunk {chunk_num} at retstart={retstart}: {e}")
                logger.error(f"This batch of ~200 papers will be LOST unless we retry")
                failed_batches.append(retstart)
                
                # Try to continue with next batch instead of giving up on entire chunk
                # This prevents losing ALL remaining papers if one batch fails
                retstart += 200
                
                # Safety: if we have too many consecutive failures, give up
                if len(failed_batches) >= 5:
                    logger.error(f"Too many failed batches ({len(failed_batches)}), stopping this chunk")
                    break
                    
                # Otherwise continue to next batch
                continue
        
        # Report any paper loss
        if failed_batches:
            logger.warning(f"CHUNK {chunk_num} WARNING: {len(failed_batches)} batch(es) failed (approximately {len(failed_batches) * 200} papers lost)")
            logger.warning(f"Failed retstart positions: {failed_batches}")
        
        logger.info(f"CHUNK {chunk_num} COMPLETE: {len(chunk_pmids):,} papers retrieved")
        all_pmids.extend(chunk_pmids)
        
        # Move to next chunk
        current_dt = chunk_end_dt + timedelta(days=1)
        chunk_num += 1
        
        # Safety limit
        if chunk_num > 20:  # Don't create too many chunks
            logger.warning(f"Reached chunk limit, stopping")
            break
    
    # Remove duplicates while preserving order
    unique_pmids = []
    seen = set()
    for pmid in all_pmids:
        if pmid not in seen:
            unique_pmids.append(pmid)
            seen.add(pmid)
    
    logger.info(f"DYNAMIC CHUNKING COMPLETE: {len(unique_pmids):,} unique PMIDs (deduplicated across chunks)")
    return unique_pmids


def search_supplement_with_chunking(supplement: str, query: str, mindate: Optional[str] = None) -> List[str]:
    """
    Search for a supplement using dynamic chunking to bypass PubMed's 10K limit
    
    Args:
        supplement: Supplement name for logging
        query: PubMed search query
        mindate: Minimum publication date
        
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


def multi_supplement_search(mindate: Optional[str] = None) -> List[str]:
    """
    Run multiple supplement-specific searches to get comprehensive coverage
    
    Args:
        mindate: Minimum publication date
        
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
