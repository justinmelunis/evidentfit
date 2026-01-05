"""
PICO-based paper relevance evaluation using LLM.

Extracts PICO components (Patient/Population, Intervention, Comparison, Outcome)
and scores relevance for supplement research context.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import sys

# Add api directory to path to import foundry_chat
project_root = Path(__file__).parent.parent.parent.parent
api_path = project_root / "api"
if str(api_path) not in sys.path:
    sys.path.insert(0, str(api_path))

try:
    from clients.foundry_chat import chat as foundry_chat
except ImportError:
    # Fallback if api not available
    foundry_chat = None

logger = logging.getLogger(__name__)

# Configuration
PICO_ENABLED = os.getenv("PICO_ENABLED", "true").lower() == "true"
PICO_RELEVANCE_THRESHOLD = float(os.getenv("PICO_RELEVANCE_THRESHOLD", "0.4"))  # Lower threshold - only filter out clear non-fits
PICO_PENALTY_FACTOR = float(os.getenv("PICO_PENALTY_FACTOR", "0.3"))  # Not used with filtering approach
PICO_BATCH_SIZE = int(os.getenv("PICO_BATCH_SIZE", "15"))


def evaluate_pico_single(
    title: str,
    abstract: str,
    supplements: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate a single paper's PICO components and relevance score.
    
    Args:
        title: Paper title
        abstract: Paper abstract (or full text for full-text stage)
        supplements: Comma-separated list of supplements mentioned
        
    Returns:
        Dictionary with:
        - pico: Dict with P, I, C, O components
        - relevance_score: float 0-1
        - relevance_reasoning: str explanation
    """
    if not PICO_ENABLED or not foundry_chat:
        # Return default if disabled or LLM not available
        return {
            "pico": {
                "patient_population": "",
                "intervention": "",
                "comparison": "",
                "outcome": ""
            },
            "relevance_score": 0.8,  # Default to high relevance if disabled
            "relevance_reasoning": "PICO evaluation disabled"
        }
    
    # Build context for LLM
    text_content = f"Title: {title}\n\nAbstract: {abstract}"
    if supplements:
        text_content += f"\n\nSupplements: {supplements}"
    
    system_prompt = """You are a medical research analyst evaluating research papers for supplement and fitness research.

Extract PICO components from the paper:
- P (Patient/Population): Who is the study population? (e.g., "healthy adults", "athletes", "elderly")
- I (Intervention): What supplement, treatment, or intervention is being studied?
- C (Comparison): What is the comparison? (placebo, control, other intervention)
- O (Outcome): What outcomes are measured? (e.g., strength, muscle mass, performance, endurance)

Then score relevance (0-1) for supplement/fitness research:
- 0.9-1.0: Highly relevant (human studies on supplements/exercise, clear outcomes)
- 0.7-0.8: Relevant (related populations, applicable interventions)
- 0.5-0.6: Moderately relevant (some overlap, may have limitations)
- 0.4-0.5: Borderline (some connection, may have limitations but not clearly irrelevant)
- 0.0-0.4: Clearly irrelevant (wrong population, non-supplement interventions, irrelevant outcomes, clearly off-topic)

Only filter out papers scoring 0.0-0.4 (clearly don't fit). Keep everything else for downstream evaluation.

Respond with JSON only:
{
  "pico": {
    "patient_population": "...",
    "intervention": "...",
    "comparison": "...",
    "outcome": "..."
  },
  "relevance_score": 0.85,
  "relevance_reasoning": "Brief explanation of score"
}"""

    user_prompt = f"Evaluate this research paper:\n\n{text_content}"
    
    try:
        response = foundry_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500,
            temperature=0.2
        )
        
        # Extract JSON from response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        result = json.loads(response)
        
        # Validate and normalize
        if "relevance_score" not in result:
            result["relevance_score"] = 0.5
        else:
            result["relevance_score"] = float(result["relevance_score"])
            # Clamp to 0-1
            result["relevance_score"] = max(0.0, min(1.0, result["relevance_score"]))
        
        if "pico" not in result:
            result["pico"] = {
                "patient_population": "",
                "intervention": "",
                "comparison": "",
                "outcome": ""
            }
        
        if "relevance_reasoning" not in result:
            result["relevance_reasoning"] = ""
        
        return result
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse PICO JSON: {e}, response: {response[:200]}")
        return {
            "pico": {
                "patient_population": "",
                "intervention": "",
                "comparison": "",
                "outcome": ""
            },
            "relevance_score": 0.5,  # Default moderate score on error
            "relevance_reasoning": "Failed to parse LLM response"
        }
    except Exception as e:
        logger.error(f"PICO evaluation failed: {e}")
        return {
            "pico": {
                "patient_population": "",
                "intervention": "",
                "comparison": "",
                "outcome": ""
            },
            "relevance_score": 0.5,
            "relevance_reasoning": f"Evaluation error: {str(e)}"
        }


def evaluate_pico_batch(
    papers: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Evaluate PICO for a batch of papers.
    
    Args:
        papers: List of paper dicts with at least 'title' and 'content' keys
        
    Returns:
        List of PICO evaluation results (same order as input)
    """
    if not PICO_ENABLED:
        # Return default results
        return [{
            "pico": {
                "patient_population": "",
                "intervention": "",
                "comparison": "",
                "outcome": ""
            },
            "relevance_score": 0.8,
            "relevance_reasoning": "PICO evaluation disabled"
        } for _ in papers]
    
    results = []
    for paper in papers:
        title = paper.get("title", "")
        content = paper.get("content", "") or paper.get("abstract", "")
        supplements = paper.get("supplements", "")
        
        result = evaluate_pico_single(title, content, supplements)
        results.append(result)
    
    return results


def is_pico_relevant(
    pico_result: Dict[str, Any]
) -> bool:
    """
    Check if paper meets PICO relevance threshold.
    
    Args:
        pico_result: Result from evaluate_pico_single
        
    Returns:
        True if paper should be kept, False if it should be filtered out
    """
    if not PICO_ENABLED:
        return True  # Keep all papers if PICO is disabled
    
    relevance_score = pico_result.get("relevance_score", 0.8)
    return relevance_score >= PICO_RELEVANCE_THRESHOLD


def apply_pico_metadata(
    paper: Dict[str, Any],
    pico_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Store PICO metadata in paper dict.
    
    Args:
        paper: Paper dictionary
        pico_result: Result from evaluate_pico_single
        
    Returns:
        Modified paper dict with PICO metadata
    """
    # Store PICO metadata
    paper["_pico"] = pico_result.get("pico", {})
    paper["_pico_relevance_score"] = pico_result.get("relevance_score", 0.8)
    paper["_pico_relevance_reasoning"] = pico_result.get("relevance_reasoning", "")
    
    return paper
