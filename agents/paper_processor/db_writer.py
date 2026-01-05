"""
Database writer for paper cards.
Writes validated cards to PostgreSQL database.
"""
import os
import logging
from typing import Dict, Any, Optional
import psycopg
from psycopg.rows import dict_row

LOG = logging.getLogger("paper_processor.db_writer")


def get_db_connection(dsn: Optional[str] = None) -> psycopg.Connection:
    """
    Get database connection using DSN from environment or provided parameter.
    """
    if dsn is None:
        dsn = os.environ.get('EVIDENTFIT_DB_DSN')
        if not dsn:
            raise ValueError("EVIDENTFIT_DB_DSN environment variable not set")
    
    try:
        conn = psycopg.connect(dsn, row_factory=dict_row)
        return conn
    except Exception as e:
        LOG.error(f"Failed to connect to database: {e}")
        raise


def write_card_to_db(card: Dict[str, Any], dsn: Optional[str] = None) -> bool:
    """
    Write a validated card to the database.
    
    Args:
        card: The card data to write
        dsn: Database connection string (optional, uses env var if not provided)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with get_db_connection(dsn) as conn:
            with conn.cursor() as cur:
                # Extract fields for the database
                paper_id = card.get("paper_id") or card.get("id", "unknown")
                pmid = card.get("pmid") or card.get("meta", {}).get("pmid")
                doi = card.get("doi") or card.get("meta", {}).get("doi")
                
                meta = card.get("meta", {})
                title = meta.get("title")
                journal = meta.get("journal")
                year = meta.get("year")
                study_type = meta.get("study_type")
                
                # Population information
                population_size = card.get("population_size")
                population_characteristics = json.dumps(card.get("population_characteristics", {}))
                
                # Intervention details
                intervention_details = json.dumps(card.get("intervention_details", {}))
                
                # Outcomes and effect sizes
                outcome_measures = json.dumps(card.get("outcome_measures", {}))
                effect_sizes = json.dumps(card.get("effect_sizes", []))
                
                # Safety information
                safety_details = json.dumps(card.get("safety_details", {}))
                
                # Quality metrics
                extraction_confidence = card.get("extraction_confidence")
                study_quality_score = card.get("study_quality_score")
                
                # Insert or update the card
                cur.execute("""
                    INSERT INTO paper_cards (
                        paper_id, pmid, doi, title, journal, year, study_type,
                        population_size, population_characteristics,
                        intervention_details, outcome_measures, effect_sizes,
                        safety_details, extraction_confidence, study_quality_score,
                        full_card
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s
                    )
                    ON CONFLICT (paper_id) DO UPDATE SET
                        pmid = EXCLUDED.pmid,
                        doi = EXCLUDED.doi,
                        title = EXCLUDED.title,
                        journal = EXCLUDED.journal,
                        year = EXCLUDED.year,
                        study_type = EXCLUDED.study_type,
                        population_size = EXCLUDED.population_size,
                        population_characteristics = EXCLUDED.population_characteristics,
                        intervention_details = EXCLUDED.intervention_details,
                        outcome_measures = EXCLUDED.outcome_measures,
                        effect_sizes = EXCLUDED.effect_sizes,
                        safety_details = EXCLUDED.safety_details,
                        extraction_confidence = EXCLUDED.extraction_confidence,
                        study_quality_score = EXCLUDED.study_quality_score,
                        full_card = EXCLUDED.full_card,
                        updated_at = NOW()
                """, (
                    paper_id, pmid, doi, title, journal, year, study_type,
                    population_size, population_characteristics,
                    intervention_details, outcome_measures, effect_sizes,
                    safety_details, extraction_confidence, study_quality_score,
                    card  # Store the full card as JSONB
                ))
                
                conn.commit()
                LOG.debug(f"Successfully wrote card to database: {paper_id}")
                return True
                
    except Exception as e:
        LOG.error(f"Failed to write card to database: {e}")
        return False


def write_cards_batch(cards: list[Dict[str, Any]], dsn: Optional[str] = None) -> Dict[str, int]:
    """
    Write multiple cards to the database in a batch.
    
    Args:
        cards: List of card data to write
        dsn: Database connection string (optional, uses env var if not provided)
    
    Returns:
        Dict with success and failure counts
    """
    results = {"success": 0, "failed": 0}
    
    try:
        with get_db_connection(dsn) as conn:
            with conn.cursor() as cur:
                for card in cards:
                    try:
                        # Extract fields for the database
                        paper_id = card.get("paper_id") or card.get("id", "unknown")
                        pmid = card.get("pmid") or card.get("meta", {}).get("pmid")
                        doi = card.get("doi") or card.get("meta", {}).get("doi")
                        
                        meta = card.get("meta", {})
                        title = meta.get("title")
                        journal = meta.get("journal")
                        year = meta.get("year")
                        study_type = meta.get("study_type")
                        
                        # Population information
                        population_size = card.get("population_size")
                        population_characteristics = json.dumps(card.get("population_characteristics", {}))
                        
                        # Intervention details
                        intervention_details = json.dumps(card.get("intervention_details", {}))
                        
                        # Outcomes and effect sizes
                        outcome_measures = json.dumps(card.get("outcome_measures", {}))
                        effect_sizes = json.dumps(card.get("effect_sizes", []))
                        
                        # Safety information
                        safety_details = json.dumps(card.get("safety_details", {}))
                        
                        # Quality metrics
                        extraction_confidence = card.get("extraction_confidence")
                        study_quality_score = card.get("study_quality_score")
                        
                        # Insert or update the card
                        cur.execute("""
                            INSERT INTO paper_cards (
                                paper_id, pmid, doi, title, journal, year, study_type,
                                population_size, population_characteristics,
                                intervention_details, outcome_measures, effect_sizes,
                                safety_details, extraction_confidence, study_quality_score,
                                full_card
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s,
                                %s, %s,
                                %s, %s, %s,
                                %s, %s, %s,
                                %s
                            )
                            ON CONFLICT (paper_id) DO UPDATE SET
                                pmid = EXCLUDED.pmid,
                                doi = EXCLUDED.doi,
                                title = EXCLUDED.title,
                                journal = EXCLUDED.journal,
                                year = EXCLUDED.year,
                                study_type = EXCLUDED.study_type,
                                population_size = EXCLUDED.population_size,
                                population_characteristics = EXCLUDED.population_characteristics,
                                intervention_details = EXCLUDED.intervention_details,
                                outcome_measures = EXCLUDED.outcome_measures,
                                effect_sizes = EXCLUDED.effect_sizes,
                                safety_details = EXCLUDED.safety_details,
                                extraction_confidence = EXCLUDED.extraction_confidence,
                                study_quality_score = EXCLUDED.study_quality_score,
                                full_card = EXCLUDED.full_card,
                                updated_at = NOW()
                        """, (
                            paper_id, pmid, doi, title, journal, year, study_type,
                            population_size, population_characteristics,
                            intervention_details, outcome_measures, effect_sizes,
                            safety_details, extraction_confidence, study_quality_score,
                            card  # Store the full card as JSONB
                        ))
                        
                        results["success"] += 1
                        
                    except Exception as e:
                        LOG.error(f"Failed to write card {card.get('paper_id', 'unknown')}: {e}")
                        results["failed"] += 1
                
                conn.commit()
                LOG.info(f"Batch write complete: {results['success']} success, {results['failed']} failed")
                
    except Exception as e:
        LOG.error(f"Failed to write batch to database: {e}")
        results["failed"] += len(cards)
        results["success"] = 0
    
    return results


def get_card_from_db(paper_id: str, dsn: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve a card from the database by paper_id.
    
    Args:
        paper_id: The paper ID to retrieve
        dsn: Database connection string (optional, uses env var if not provided)
    
    Returns:
        Card data if found, None otherwise
    """
    try:
        with get_db_connection(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM paper_cards WHERE paper_id = %s", (paper_id,))
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
                
    except Exception as e:
        LOG.error(f"Failed to retrieve card from database: {e}")
        return None


def get_cards_by_quality(confidence_threshold: float = 0.8, dsn: Optional[str] = None) -> list[Dict[str, Any]]:
    """
    Retrieve cards above a certain quality threshold.
    
    Args:
        confidence_threshold: Minimum extraction confidence score
        dsn: Database connection string (optional, uses env var if not provided)
    
    Returns:
        List of high-quality cards
    """
    try:
        with get_db_connection(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM paper_cards 
                    WHERE extraction_confidence >= %s 
                    ORDER BY extraction_confidence DESC
                """, (confidence_threshold,))
                rows = cur.fetchall()
                return [dict(row) for row in rows]
                
    except Exception as e:
        LOG.error(f"Failed to retrieve cards by quality: {e}")
        return []


def get_quality_stats(dsn: Optional[str] = None) -> Dict[str, Any]:
    """
    Get quality statistics from the database.
    
    Args:
        dsn: Database connection string (optional, uses env var if not provided)
    
    Returns:
        Dictionary with quality statistics
    """
    try:
        with get_db_connection(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_cards,
                        AVG(extraction_confidence) as avg_confidence,
                        MIN(extraction_confidence) as min_confidence,
                        MAX(extraction_confidence) as max_confidence,
                        COUNT(CASE WHEN extraction_confidence >= 0.8 THEN 1 END) as high_quality_count,
                        COUNT(CASE WHEN extraction_confidence < 0.6 THEN 1 END) as low_quality_count
                    FROM paper_cards
                """)
                row = cur.fetchone()
                if row:
                    return dict(row)
                return {}
                
    except Exception as e:
        LOG.error(f"Failed to get quality stats: {e}")
        return {}


if __name__ == "__main__":
    # Test the database writer
    test_card = {
        "paper_id": "test_123",
        "pmid": "12345678",
        "title": "Test Study",
        "journal": "Test Journal",
        "year": 2020,
        "population_size": 45,
        "intervention_details": {"dose_g_per_day": 5.0, "duration_weeks": 8},
        "effect_sizes": [{"outcome": "1RM", "value": 0.45, "p_value": 0.02}],
        "extraction_confidence": 0.85,
        "meta": {"title": "Test Study", "journal": "Test Journal", "year": 2020}
    }
    
    print("Testing database writer...")
    success = write_card_to_db(test_card)
    print(f"Write test: {'SUCCESS' if success else 'FAILED'}")
    
    retrieved = get_card_from_db("test_123")
    print(f"Retrieve test: {'SUCCESS' if retrieved else 'FAILED'}")
    
    stats = get_quality_stats()
    print(f"Quality stats: {stats}")
