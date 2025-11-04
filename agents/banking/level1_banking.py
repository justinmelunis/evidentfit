"""
Level 1 Banking: Goal × Supplement Evidence Grades

This script pre-computes evidence grades for all goal × supplement combinations
using a quality-first approach that prioritizes study quality over quantity.

Features:
- Quality-first approach: Prioritize study quality over quantity
- Use full abstracts (remove the 1000-character limit)
- Analyze all relevant papers in our index
- Use all metadata fields for quality assessment
- Consistency scoring: Better detection of contradictory findings
- Effect size detection and inclusion in details

LLM Model: GPT-4o-mini (Azure AI Foundry) - Long-term choice
- Cost: ~$3.75 per run (378 calls: 6 goals × 63 supplements)
- Runtime: 5-10 minutes (parallel execution)
- See docs/MODEL_SELECTION.md for detailed rationale and model comparison
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Tuple
from datetime import datetime

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'api'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'paper_processor'))

from evidentfit_shared.search_client import search_docs
from clients.foundry_chat import chat as foundry_chat

# Import custom search API for enhanced paper analysis
try:
    from search_api import SearchAPI
    CUSTOM_SEARCH_AVAILABLE = True
except ImportError:
    CUSTOM_SEARCH_AVAILABLE = False
    print("WARNING: Custom search API not available, using fallback search")

# Load environment variables
from dotenv import load_dotenv
load_dotenv('banking_init.env')

# Try to use Key Vault for credentials (same as API)
try:
    from keyvault_client import KeyVaultClient
    
    # Initialize Key Vault client
    kv_client = KeyVaultClient()
    
    # Get credentials from Key Vault
    foundation_endpoint = kv_client.get_secret("foundation-endpoint")
    foundation_key = kv_client.get_secret("foundation-key")
    
    if foundation_endpoint and foundation_key:
        os.environ["FOUNDATION_ENDPOINT"] = foundation_endpoint
        os.environ["FOUNDATION_KEY"] = foundation_key
        print("SUCCESS: Using Key Vault credentials for Foundry")
    else:
        print("WARNING: Key Vault credentials not available, using local env file")
        
except Exception as e:
    print(f"WARNING: Key Vault not available ({e}), using local env file")

# Banking configuration
GOALS = ["strength", "hypertrophy", "endurance", "weight_loss", "performance", "general"]
SUPPLEMENTS = [
    "creatine", "protein", "caffeine", "beta-alanine", "citrulline", 
    "nitrate", "hmb", "bcaa", "taurine", "carnitine", "glutamine",
    "ashwagandha", "rhodiola", "omega-3", "vitamin-d", "magnesium",
    "collagen", "curcumin", "b12", "iron", "folate", "leucine", "betaine",
    "zma", "tribulus", "d-aspartic-acid", "tongkat-ali"
]

class Level1BankingInitializer:
    """Initialize Level 1 banking with quality-first evidence grading"""
    
    def __init__(self):
        self.evidence_bank = {}
        self.papers_cache = {}
        
        # Initialize custom search API if available
        self.custom_search_api = None
        if CUSTOM_SEARCH_AVAILABLE:
            try:
                # Use the test data directory for now
                self.custom_search_api = SearchAPI("test_optimized_data")
                self.logger.info("SUCCESS: Custom search API initialized with enhanced structured summaries")
            except Exception as e:
                self.logger.warning(f"Failed to initialize custom search API: {e}")
                self.custom_search_api = None
        
        # Setup logging
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'level1_banking_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        
        # Configure file handler with immediate flushing
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Configure console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler],
            force=True  # Override any existing configuration
        )
        self.logger = logging.getLogger(__name__)
        
        # Force immediate flushing for real-time logging
        for handler in self.logger.handlers:
            handler.flush()
        
    def initialize_level1_banking(self):
        """Initialize Level 1 banking for all goal × supplement combinations"""
        self.logger.info("Starting Level 1 Banking Initialization...")
        self.logger.info(f"Will process: {len(GOALS)} goals × {len(SUPPLEMENTS)} supplements = {len(GOALS) * len(SUPPLEMENTS)} evidence grades")
        
        total_combinations = len(GOALS) * len(SUPPLEMENTS)
        processed = 0
        
        for goal in GOALS:
            for supplement in SUPPLEMENTS:
                processed += 1
                self.logger.info(f"Processing {supplement} for {goal} ({processed}/{total_combinations})")
                
                # Get evidence grade with detailed analysis
                evidence_data = self.get_evidence_grade_with_details(supplement, goal)
                self.evidence_bank[f"{supplement}:{goal}"] = evidence_data
                
                self.logger.info(f"  {supplement} for {goal}: Grade {evidence_data['grade']}")
                
                # Force flush to ensure real-time logging
                for handler in self.logger.handlers:
                    handler.flush()
        
        # Save Level 1 bank
        self.save_level1_bank()
        
        self.logger.info("SUCCESS: Level 1 banking initialization complete!")
        
    def get_evidence_grade_with_details(self, supplement: str, goal: str) -> Dict[str, Any]:
        """
        Get evidence grade with detailed analysis using quality-first approach
        
        Returns:
            Dict with grade, reasoning, supporting_papers, contradictory_papers, 
            effect_sizes, and quality_metrics
        """
        # Get all relevant papers for this supplement and goal
        papers = self.get_relevant_papers(supplement, goal)
        
        if not papers:
            self.logger.info(f"    No papers found for {supplement} and {goal} - assigning Grade D")
            return {
                "grade": "D",
                "reasoning": "No relevant papers found in database",
                "supporting_papers": [],
                "contradictory_papers": [],
                "effect_sizes": [],
                "quality_metrics": {
                    "total_papers": 0,
                    "meta_analyses": 0,
                    "rcts": 0,
                    "consistency_score": 0.0
                }
            }
        
        # Analyze papers for quality, consistency, and effect sizes
        self.logger.info(f"    Analyzing {len(papers)} papers for quality and consistency")
        analysis = self.analyze_papers_quality_first(papers, supplement, goal)
        
        # Use LLM to assign final grade based on comprehensive analysis
        self.logger.info(f"    Calling LLM for evidence grading")
        grade = self.assign_evidence_grade_with_llm(supplement, goal, analysis)
        
        return {
            "grade": grade,
            "reasoning": analysis["reasoning"],
            "supporting_papers": analysis["supporting_papers"],
            "contradictory_papers": analysis["contradictory_papers"],
            "effect_sizes": analysis["effect_sizes"],
            "quality_metrics": analysis["quality_metrics"]
        }
    
    def get_relevant_papers(self, supplement: str, goal: str) -> List[Dict]:
        """Get all relevant papers for supplement and goal from the index"""
        
        # Try custom search API first (enhanced with structured summaries)
        if self.custom_search_api:
            try:
                self.logger.info(f"    Using custom search API for {supplement} and {goal}")
                papers = self.custom_search_api.get_supplement_evidence_by_goal(supplement, goal, limit=100)
                
                if papers:
                    self.logger.info(f"    Found {len(papers)} papers via custom search with enhanced structured summaries")
                    return papers
                else:
                    self.logger.info(f"    No papers found via custom search, falling back to standard search")
            except Exception as e:
                self.logger.warning(f"    Custom search failed: {e}, falling back to standard search")
        
        # Fallback to standard search
        self.logger.info(f"    Using standard search for {supplement} and {goal}")
        query = supplement
        search_results = search_docs(query, top=100)  # Get more papers for comprehensive analysis
        papers = search_results.get('value', [])  # Extract documents from search results
        
        self.logger.info(f"    Found {len(papers)} papers for {supplement} in index")
        
        # Filter for goal relevance
        goal_keywords = {
            "strength": ["strength", "1rm", "power", "force", "muscle strength"],
            "hypertrophy": ["hypertrophy", "muscle mass", "lean mass", "muscle growth", "muscle size"],
            "endurance": ["endurance", "vo2", "aerobic", "cardio", "fatigue", "time to exhaustion"],
            "weight_loss": ["weight loss", "fat loss", "body composition", "metabolism", "body fat"],
            "performance": ["performance", "athletic", "exercise", "training", "sport"],
            "general": ["health", "wellness", "general", "overall", "quality of life"]
        }
        
        relevant_papers = []
        keywords = goal_keywords.get(goal, [])
        
        for paper in papers:
            # First check if the supplement is actually in the supplements field
            supplements_field = (paper.get("supplements") or "").lower()
            if supplement.lower() not in supplements_field:
                continue  # Skip papers that don't actually contain this supplement
            
            # Check if paper is relevant to the goal
            title = (paper.get("title") or "").lower()
            content = (paper.get("content") or "").lower()
            outcomes = (paper.get("outcomes") or "").lower()
            primary_goal = (paper.get("primary_goal") or "").lower()
            
            # Check for goal relevance
            text_to_check = f"{title} {content} {outcomes} {primary_goal}"
            if any(keyword in text_to_check for keyword in keywords):
                relevant_papers.append(paper)
        
        self.logger.info(f"    Filtered to {len(relevant_papers)} papers relevant to {goal} goals")
        return relevant_papers
    
    def analyze_papers_quality_first(self, papers: List[Dict], supplement: str, goal: str) -> Dict[str, Any]:
        """
        Analyze papers using quality-first approach with full abstracts and metadata
        """
        # Sort papers by quality using existing ingest scores
        quality_scores = []
        for paper in papers:
            score = self.get_paper_quality_score(paper)
            quality_scores.append((score, paper))
        
        quality_scores.sort(key=lambda x: x[0], reverse=True)
        sorted_papers = [paper for _, paper in quality_scores]
        
        # Analyze consistency and effect sizes
        consistency_analysis = self.analyze_consistency(sorted_papers)
        effect_sizes = self.extract_effect_sizes(sorted_papers)
        
        # Separate supporting vs contradictory papers
        supporting_papers = []
        contradictory_papers = []
        
        for paper in sorted_papers:
            if self.is_supporting_evidence(paper, supplement, goal):
                supporting_papers.append(paper)
            elif self.is_contradictory_evidence(paper, supplement, goal):
                contradictory_papers.append(paper)
        
        # Calculate quality metrics using existing scores
        meta_analyses = sum(1 for p in papers if "meta" in (p.get("study_type") or "").lower())
        rcts = sum(1 for p in papers if "rct" in (p.get("study_type") or "").lower() or "randomized" in (p.get("study_type") or "").lower())
        
        # Calculate average quality scores
        avg_enhanced_score = sum(self.get_paper_quality_score(p) for p in papers) / len(papers) if papers else 0
        avg_reliability_score = sum(p.get("reliability_score", 0) for p in papers) / len(papers) if papers else 0
        
        return {
            "reasoning": f"Analyzed {len(papers)} papers with {meta_analyses} meta-analyses and {rcts} RCTs",
            "supporting_papers": supporting_papers[:10],  # Top 10 supporting papers
            "contradictory_papers": contradictory_papers[:5],  # Top 5 contradictory papers
            "effect_sizes": effect_sizes,
            "quality_metrics": {
                "total_papers": len(papers),
                "meta_analyses": meta_analyses,
                "rcts": rcts,
                "consistency_score": consistency_analysis["score"],
                "supporting_count": len(supporting_papers),
                "contradictory_count": len(contradictory_papers),
                "avg_enhanced_score": avg_enhanced_score,
                "avg_reliability_score": avg_reliability_score
            }
        }
    
    def get_paper_quality_score(self, paper: Dict) -> float:
        """Get quality score from enhanced structured summaries or existing ingest scoring system"""
        # First try to get quality score from enhanced structured summaries
        quality_scores = paper.get("quality_scores", {})
        if isinstance(quality_scores, dict):
            overall_score = quality_scores.get("overall", 0)
            if overall_score > 0:
                return overall_score
        
        # Use the enhanced_score from ingest, which combines reliability_score + combination_score
        enhanced_score = paper.get("enhanced_score", 0)
        if enhanced_score > 0:
            return enhanced_score
        
        # Fallback to reliability_score if enhanced_score not available
        reliability_score = paper.get("reliability_score", 0)
        if reliability_score > 0:
            return reliability_score
        
        # Final fallback to study_design_score
        study_design_score = paper.get("study_design_score", 0)
        return study_design_score
    
    def analyze_consistency(self, papers: List[Dict]) -> Dict[str, Any]:
        """Analyze consistency across papers"""
        if len(papers) < 2:
            return {"score": 1.0, "description": "Insufficient papers for consistency analysis"}
        
        # Simple consistency scoring based on study outcomes
        positive_outcomes = 0
        negative_outcomes = 0
        neutral_outcomes = 0
        
        for paper in papers:
            outcomes = (paper.get("outcomes") or "").lower()
            if any(word in outcomes for word in ["improved", "increased", "enhanced", "beneficial", "positive"]):
                positive_outcomes += 1
            elif any(word in outcomes for word in ["decreased", "worsened", "negative", "harmful", "adverse"]):
                negative_outcomes += 1
            else:
                neutral_outcomes += 1
        
        total = len(papers)
        if total == 0:
            return {"score": 0.0, "description": "No papers to analyze"}
        
        # Calculate consistency score (higher = more consistent)
        if positive_outcomes > negative_outcomes:
            consistency_score = positive_outcomes / total
        elif negative_outcomes > positive_outcomes:
            consistency_score = negative_outcomes / total
        else:
            consistency_score = 0.5  # Mixed results
        
        return {
            "score": consistency_score,
            "description": f"{positive_outcomes} positive, {negative_outcomes} negative, {neutral_outcomes} neutral outcomes"
        }
    
    def extract_effect_sizes(self, papers: List[Dict]) -> List[Dict]:
        """Extract effect sizes from enhanced structured summaries or paper content"""
        effect_sizes = []
        
        for paper in papers:
            # First try to extract from enhanced structured summaries
            outcome_measures = paper.get("outcome_measures", {})
            if isinstance(outcome_measures, dict):
                for goal_category, measures in outcome_measures.items():
                    if isinstance(measures, dict):
                        for measure_key, measure_data in measures.items():
                            if isinstance(measure_data, dict) and "effect_size" in measure_data:
                                effect_sizes.append({
                                    "type": "structured_effect_size",
                                    "value": measure_data["effect_size"],
                                    "unit": "cohen_d",
                                    "measure": measure_data.get("measure", "Unknown"),
                                    "paper_title": paper.get("title", ""),
                                    "paper_id": paper.get("id", ""),
                                    "goal_category": goal_category
                                })
            
            # Fallback to text-based extraction
            content = paper.get("content", "")
            outcomes = paper.get("outcomes", "")
            summary = paper.get("summary", "")
            
            # Look for effect size indicators
            text_to_analyze = f"{content} {outcomes} {summary}"
            
            # Simple effect size extraction (can be enhanced)
            if "%" in text_to_analyze:
                # Look for percentage improvements
                import re
                percentages = re.findall(r'(\d+(?:\.\d+)?%)', text_to_analyze)
                for pct in percentages:
                    try:
                        value = float(pct.replace('%', ''))
                        if 1 <= value <= 100:  # Reasonable range
                            effect_sizes.append({
                                "type": "percentage_improvement",
                                "value": value,
                                "unit": "%",
                                "paper_title": paper.get("title", ""),
                                "paper_id": paper.get("id", "")
                            })
                    except ValueError:
                        continue
        
        return effect_sizes[:10]  # Top 10 effect sizes
    
    def is_supporting_evidence(self, paper: Dict, supplement: str, goal: str) -> bool:
        """Determine if paper provides supporting evidence"""
        outcomes = (paper.get("outcomes") or "").lower()
        content = (paper.get("content") or "").lower()
        
        positive_indicators = ["improved", "increased", "enhanced", "beneficial", "positive", "significant improvement"]
        return any(indicator in outcomes or indicator in content for indicator in positive_indicators)
    
    def is_contradictory_evidence(self, paper: Dict, supplement: str, goal: str) -> bool:
        """Determine if paper provides contradictory evidence"""
        outcomes = (paper.get("outcomes") or "").lower()
        content = (paper.get("content") or "").lower()
        
        negative_indicators = ["decreased", "worsened", "negative", "harmful", "adverse", "no effect", "no significant"]
        return any(indicator in outcomes or indicator in content for indicator in negative_indicators)
    
    def assign_evidence_grade_with_llm(self, supplement: str, goal: str, analysis: Dict) -> str:
        """Use LLM to assign evidence grade based on comprehensive analysis"""
        
        # Prepare detailed analysis for LLM
        supporting_papers_text = ""
        for i, paper in enumerate(analysis["supporting_papers"][:5]):
            supporting_papers_text += f"""
=== SUPPORTING PAPER {i+1} ===
Title: {paper.get('title', '')}
Journal: {paper.get('journal', '')} ({paper.get('year', '')})
Study Type: {paper.get('study_type', '')}
Sample Size: {paper.get('sample_size', 'N/A')}
Outcomes: {paper.get('outcomes', '')}
Content: {paper.get('content', '')[:2000]}...
"""
        
        contradictory_papers_text = ""
        for i, paper in enumerate(analysis["contradictory_papers"][:3]):
            contradictory_papers_text += f"""
=== CONTRADICTORY PAPER {i+1} ===
Title: {paper.get('title', '')}
Journal: {paper.get('journal', '')} ({paper.get('year', '')})
Study Type: {paper.get('study_type', '')}
Outcomes: {paper.get('outcomes', '')}
Content: {paper.get('content', '')[:2000]}...
"""
        
        effect_sizes_text = ""
        for i, effect in enumerate(analysis["effect_sizes"][:5]):
            effect_sizes_text += f"""
Effect {i+1}: {effect['value']}{effect['unit']} {effect['type']} (from {effect['paper_title']})
"""
        
        prompt = f"""You are an expert research evidence grader evaluating {supplement} for {goal} goals.

COMPREHENSIVE ANALYSIS:
{analysis['reasoning']}

QUALITY METRICS:
- Total papers: {analysis['quality_metrics']['total_papers']}
- Meta-analyses: {analysis['quality_metrics']['meta_analyses']}
- RCTs: {analysis['quality_metrics']['rcts']}
- Consistency score: {analysis['quality_metrics']['consistency_score']:.2f}
- Supporting papers: {analysis['quality_metrics']['supporting_count']}
- Contradictory papers: {analysis['quality_metrics']['contradictory_count']}
- Average enhanced score: {analysis['quality_metrics']['avg_enhanced_score']:.1f}
- Average reliability score: {analysis['quality_metrics']['avg_reliability_score']:.1f}

SUPPORTING EVIDENCE:
{supporting_papers_text}

CONTRADICTORY EVIDENCE:
{contradictory_papers_text}

EFFECT SIZES:
{effect_sizes_text}

GRADING CRITERIA:

**Grade A - Strong Evidence:**
- Multiple high-quality RCTs or systematic reviews/meta-analyses showing consistent benefits
- Clear positive effects with clinically meaningful effect sizes
- Well-established supplements with decades of research
- Meta-analyses from reputable journals showing significant improvements
- Strong biological plausibility and mechanism of action
- Effects directly relevant to {goal}

**Grade B - Moderate Evidence:**
- Some quality RCTs or one good meta-analysis showing benefits
- Generally positive effects but may have some inconsistency
- Moderate effect sizes or limited by study quality/size
- Most studies show benefit but evidence base could be stronger
- Effects reasonably relevant to {goal}

**Grade C - Limited Evidence:**
- Few studies, mostly observational or small RCTs
- Mixed or inconsistent results across studies
- Small effect sizes or studies with methodological limitations
- Some suggestion of benefit but evidence is preliminary
- Indirect relevance to {goal} or limited population studied

**Grade D - Insufficient/Negative Evidence:**
- No quality studies showing benefits for {goal}
- Studies consistently show no effect or potential harm
- Very poor study quality or extremely limited evidence base
- No plausible mechanism or theoretical basis for benefits

Based on your comprehensive analysis of study quality, consistency, effect sizes, and relevance to {goal}, what evidence grade would you assign?

Respond with ONLY the single letter grade: A, B, C, or D

Your grade:"""

        try:
            response = foundry_chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.1
            )
            
            grade = response.strip().upper()
            if grade in ['A', 'B', 'C', 'D']:
                return grade
            else:
                self.logger.warning(f"Invalid grade response: '{response}', defaulting to C")
                return "C"
                
        except Exception as e:
            self.logger.error(f"LLM grading failed: {e}")
            return "C"  # Conservative default
    
    def save_level1_bank(self):
        """Save Level 1 evidence bank to JSON file"""
        output_file = os.path.join(os.path.dirname(__file__), 'level1_evidence_bank.json')
        
        bank_data = {
            "initialization_date": datetime.now().isoformat(),
            "index_version": os.getenv("INDEX_VERSION", "v1"),
            "total_entries": len(self.evidence_bank),
            "goals": GOALS,
            "supplements": SUPPLEMENTS,
            "evidence_data": self.evidence_bank
        }
        
        with open(output_file, 'w') as f:
            json.dump(bank_data, f, indent=2)
        
        self.logger.info(f"Level 1 evidence bank saved to {output_file}")
        self.logger.info(f"Total entries: {len(self.evidence_bank)}")

if __name__ == "__main__":
    initializer = Level1BankingInitializer()
    initializer.initialize_level1_banking()
