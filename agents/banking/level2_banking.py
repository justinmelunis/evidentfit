"""
Level 2 Banking: Profile-Specific Evidence Enhancement

This script pre-computes profile-specific reasoning for all profile combinations
using evidence from the research papers. It enhances the base Level 1 grades
with profile-specific evidence and citations.

Features:
- Profile-specific evidence enhancement (no scores, just reasoning)
- Citations for profile-specific findings
- Evidence for different weight bins, age groups, and sexes
- Integration with Level 1 base grades
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

from evidentfit_shared.search_client import search_docs
from clients.foundry_chat import chat as foundry_chat

# Banking configuration
GOALS = ["strength", "hypertrophy", "endurance", "weight_loss", "performance", "general"]
WEIGHT_BINS = ["xs", "small", "medium", "large", "xl"]  # <60, 60-70, 70-85, 85-100, 100+ kg
SEXES = ["male", "female", "other"]
AGE_BINS = ["minor", "young", "adult", "mature"]  # 13-17, 18-29, 30-49, 50+ years
SUPPLEMENTS = [
    "creatine", "protein", "caffeine", "beta-alanine", "citrulline", 
    "nitrate", "hmb", "bcaa", "taurine", "carnitine", "glutamine",
    "ashwagandha", "rhodiola", "omega-3", "vitamin-d", "magnesium",
    "collagen", "curcumin", "b12", "iron", "folate", "leucine", "betaine",
    "zma", "tribulus", "d-aspartic-acid", "tongkat-ali"
]

class Level2BankingInitializer:
    """Initialize Level 2 banking with profile-specific evidence enhancement"""
    
    def __init__(self):
        self.reasoning_bank = {}
        self.papers_cache = {}
        
        # Setup logging
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'level2_banking_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def initialize_level2_banking(self):
        """Initialize Level 2 banking for all profile combinations"""
        self.logger.info("Starting Level 2 Banking Initialization...")
        
        # Load Level 1 base grades
        level1_data = self.load_level1_bank()
        if not level1_data:
            self.logger.error("Level 1 bank not found. Please run level1_banking.py first.")
            return
        
        total_combinations = len(GOALS) * len(WEIGHT_BINS) * len(SEXES) * len(AGE_BINS)
        processed = 0
        
        for goal in GOALS:
            for weight_bin in WEIGHT_BINS:
                for sex in SEXES:
                    for age_bin in AGE_BINS:
                        processed += 1
                        profile_key = f"{goal}:{weight_bin}:{sex}:{age_bin}"
                        
                        self.logger.info(f"Processing profile: {profile_key} ({processed}/{total_combinations})")
                        
                        # Generate profile-specific reasoning for all supplements
                        profile_reasoning = {}
                        for supplement in SUPPLEMENTS:
                            reasoning = self.get_profile_specific_reasoning(
                                supplement, goal, weight_bin, sex, age_bin, level1_data
                            )
                            profile_reasoning[supplement] = reasoning
                        
                        self.reasoning_bank[profile_key] = profile_reasoning
                        
                        # Log progress every 50 profiles
                        if processed % 50 == 0:
                            self.logger.info(f"Progress: {processed}/{total_combinations} ({processed/total_combinations*100:.1f}%)")
        
        # Save Level 2 bank
        self.save_level2_bank()
        
        self.logger.info("SUCCESS: Level 2 banking initialization complete!")
        
    def load_level1_bank(self) -> Optional[Dict]:
        """Load Level 1 evidence bank"""
        level1_file = os.path.join(os.path.dirname(__file__), 'level1_evidence_bank.json')
        
        if not os.path.exists(level1_file):
            return None
        
        try:
            with open(level1_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load Level 1 bank: {e}")
            return None
    
    def get_profile_specific_reasoning(self, supplement: str, goal: str, weight_bin: str, 
                                     sex: str, age_bin: str, level1_data: Dict) -> Dict[str, Any]:
        """
        Get profile-specific reasoning for a supplement
        
        Returns:
            Dict with reasoning, supporting_evidence, and citations
        """
        # Get base grade from Level 1
        base_key = f"{supplement}:{goal}"
        base_evidence = level1_data.get("evidence_data", {}).get(base_key, {})
        base_grade = base_evidence.get("grade", "D")
        
        # Search for profile-specific evidence
        profile_evidence = self.search_profile_specific_evidence(supplement, goal, weight_bin, sex, age_bin)
        
        if not profile_evidence:
            return {
                "base_grade": base_grade,
                "reasoning": "No profile-specific evidence found. Using base evidence only.",
                "supporting_evidence": [],
                "citations": []
            }
        
        # Generate reasoning using LLM
        reasoning = self.generate_profile_reasoning_with_llm(
            supplement, goal, weight_bin, sex, age_bin, base_evidence, profile_evidence
        )
        
        return reasoning
    
    def search_profile_specific_evidence(self, supplement: str, goal: str, weight_bin: str, 
                                       sex: str, age_bin: str) -> List[Dict]:
        """Search for profile-specific evidence in the research papers"""
        
        # Build search query for profile-specific evidence
        query_parts = [f"supplements:{supplement}"]
        
        # Add weight-specific terms
        weight_terms = {
            "xs": ["<60kg", "lightweight", "small body", "low weight"],
            "small": ["60-70kg", "moderate weight", "average weight"],
            "medium": ["70-85kg", "standard weight", "normal weight"],
            "large": ["85-100kg", "heavyweight", "large body", "high weight"],
            "xl": [">100kg", "very heavy", "obese", "overweight"]
        }
        
        # Add sex-specific terms
        sex_terms = {
            "male": ["men", "male", "masculine"],
            "female": ["women", "female", "feminine"],
            "other": ["non-binary", "transgender"]
        }
        
        # Add age-specific terms
        age_terms = {
            "minor": ["adolescent", "teenager", "young", "pediatric"],
            "young": ["young adult", "college", "university", "18-29"],
            "adult": ["adult", "middle-aged", "30-49"],
            "mature": ["elderly", "senior", "older", "50+", "geriatric"]
        }
        
        # Search for papers with profile-specific information
        papers = search_docs(f"supplements:{supplement}", top=50)
        
        profile_specific_papers = []
        for paper in papers:
            content = (paper.get("content") or "").lower()
            population = (paper.get("population") or "").lower()
            title = (paper.get("title") or "").lower()
            
            # Check for profile-specific mentions
            has_weight_info = any(term in content or term in population for term in weight_terms[weight_bin])
            has_sex_info = any(term in content or term in population for term in sex_terms[sex])
            has_age_info = any(term in content or term in population for term in age_terms[age_bin])
            
            # Include paper if it has relevant profile information
            if has_weight_info or has_sex_info or has_age_info:
                profile_specific_papers.append(paper)
        
        return profile_specific_papers
    
    def generate_profile_reasoning_with_llm(self, supplement: str, goal: str, weight_bin: str, 
                                          sex: str, age_bin: str, base_evidence: Dict, 
                                          profile_evidence: List[Dict]) -> Dict[str, Any]:
        """Generate profile-specific reasoning using LLM"""
        
        # Prepare base evidence summary
        base_summary = f"""
Base Evidence (Grade {base_evidence.get('grade', 'D')}):
- Total papers: {base_evidence.get('quality_metrics', {}).get('total_papers', 0)}
- Meta-analyses: {base_evidence.get('quality_metrics', {}).get('meta_analyses', 0)}
- RCTs: {base_evidence.get('quality_metrics', {}).get('rcts', 0)}
- Consistency: {base_evidence.get('quality_metrics', {}).get('consistency_score', 0):.2f}
- Reasoning: {base_evidence.get('reasoning', 'No reasoning available')}
"""
        
        # Prepare profile-specific evidence
        profile_papers_text = ""
        citations = []
        
        for i, paper in enumerate(profile_evidence[:5]):  # Top 5 profile-specific papers
            title = paper.get('title', '')
            journal = paper.get('journal', '')
            year = paper.get('year', '')
            content = paper.get('content', '')[:1500]  # More content for profile analysis
            population = paper.get('population', '')
            
            profile_papers_text += f"""
=== PROFILE-SPECIFIC PAPER {i+1} ===
Title: {title}
Journal: {journal} ({year})
Population: {population}
Content: {content}...
"""
            
            # Build citation
            citation = {
                "title": title,
                "journal": journal,
                "year": year,
                "pmid": paper.get('pmid', ''),
                "doi": paper.get('doi', ''),
                "url": paper.get('url_pub', '')
            }
            citations.append(citation)
        
        # Map profile characteristics to human-readable terms
        weight_desc = {
            "xs": "under 60kg (lightweight)",
            "small": "60-70kg (small frame)",
            "medium": "70-85kg (average frame)",
            "large": "85-100kg (large frame)",
            "xl": "over 100kg (very large frame)"
        }
        
        age_desc = {
            "minor": "13-17 years (adolescent)",
            "young": "18-29 years (young adult)",
            "adult": "30-49 years (adult)",
            "mature": "50+ years (mature adult)"
        }
        
        prompt = f"""You are an expert in personalized supplement recommendations. Analyze the profile-specific evidence for {supplement} for {goal} goals.

PROFILE CHARACTERISTICS:
- Weight: {weight_desc[weight_bin]}
- Sex: {sex}
- Age: {age_desc[age_bin]}
- Goal: {goal}

BASE EVIDENCE:
{base_summary}

PROFILE-SPECIFIC EVIDENCE:
{profile_papers_text}

TASK:
Generate profile-specific reasoning that enhances the base evidence. Focus on:

1. **Profile-Specific Benefits**: Are there specific benefits for this weight/sex/age profile?
2. **Dosing Considerations**: Are there different dosing recommendations for this profile?
3. **Safety Considerations**: Are there any profile-specific safety concerns?
4. **Effectiveness**: Is the supplement more or less effective for this profile?
5. **Citations**: Reference specific papers that support your reasoning

RESPONSE FORMAT:
Provide a concise reasoning paragraph (2-3 sentences) that:
- References the base evidence grade
- Highlights any profile-specific findings
- Cites specific papers when available
- Maintains scientific accuracy

Example format:
"For [supplement] and [goal], the base evidence shows [grade] grade due to [reasoning]. However, for [profile characteristics], research suggests [profile-specific finding] (Citation: [paper title]). [Additional profile-specific considerations]."

Your reasoning:"""

        try:
            response = foundry_chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2
            )
            
            return {
                "base_grade": base_evidence.get('grade', 'D'),
                "reasoning": response.strip(),
                "supporting_evidence": profile_evidence[:5],
                "citations": citations
            }
            
        except Exception as e:
            self.logger.error(f"LLM reasoning generation failed: {e}")
            return {
                "base_grade": base_evidence.get('grade', 'D'),
                "reasoning": "Profile-specific analysis unavailable. Using base evidence only.",
                "supporting_evidence": [],
                "citations": []
            }
    
    def save_level2_bank(self):
        """Save Level 2 reasoning bank to JSON file"""
        output_file = os.path.join(os.path.dirname(__file__), 'level2_reasoning_bank.json')
        
        bank_data = {
            "initialization_date": datetime.now().isoformat(),
            "index_version": os.getenv("INDEX_VERSION", "v1"),
            "total_profiles": len(self.reasoning_bank),
            "goals": GOALS,
            "weight_bins": WEIGHT_BINS,
            "sexes": SEXES,
            "age_bins": AGE_BINS,
            "supplements": SUPPLEMENTS,
            "reasoning_data": self.reasoning_bank
        }
        
        with open(output_file, 'w') as f:
            json.dump(bank_data, f, indent=2)
        
        self.logger.info(f"Level 2 reasoning bank saved to {output_file}")
        self.logger.info(f"Total profiles: {len(self.reasoning_bank)}")

if __name__ == "__main__":
    initializer = Level2BankingInitializer()
    initializer.initialize_level2_banking()
