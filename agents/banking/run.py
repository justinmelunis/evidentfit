"""
Banking Initialization Script for EvidentFit

This script pre-computes and caches all evidence grades and reasoning for the 3-level banking system:

Level 1: Goal × Supplement Evidence Grades (216 combinations)
Level 2: Profile-Specific Reasoning (360 combinations) 
Level 3: Real-time adjustments (never cached)

Run this after major research updates to refresh all cached evidence.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'api'))

from stack_builder import (
    COMMON_SUPPLEMENTS,
    BANKING_BUCKETS,
    generate_profile_specific_reasoning,
    generate_bank_key,
    get_weight_bin,
    get_age_bin,
)
from evidentfit_shared.types import UserProfile
from clients.search_read import search_docs
from evidentfit_shared.banking.aggregate import BankingConfig, load_cards_for, pool_and_grade
from evidentfit_shared.utils import read_index_version


class BankingInitializer:
    """Initialize and populate all banking caches"""
    
    def __init__(self):
        self.level1_bank = {}  # Goal × Supplement evidence grades
        self.level2_bank = {}  # Profile-specific reasoning
        self.papers_cache = {}  # Cache retrieved papers to avoid repeated searches
        self.cfg = None
        
        # Setup logging
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'banking_init_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        # Load banking config and index version
        try:
            self.cfg = BankingConfig.load(Path("config/banking.yml"))
        except Exception as e:
            self.logger.warning(f"Failed to load banking config: {e}")
            self.cfg = None
        try:
            self.index_version = read_index_version()
        except Exception:
            self.index_version = os.getenv("INDEX_VERSION", "v1")
        
    def initialize_all_banks(self):
        """Initialize both Level 1 and Level 2 banking"""
        self.logger.info("Starting Banking Initialization...")
        self.logger.info(f"Will process:")
        self.logger.info(f"   - Level 1: {len(BANKING_BUCKETS['goal'])} goals × {len(COMMON_SUPPLEMENTS)} supplements = {len(BANKING_BUCKETS['goal']) * len(COMMON_SUPPLEMENTS)} evidence grades")
        self.logger.info(f"   - Level 2: {6 * 5 * 3 * 4} profile combinations × {len(COMMON_SUPPLEMENTS)} supplements = {6 * 5 * 3 * 4 * len(COMMON_SUPPLEMENTS)} reasoning entries")
        
        # Step 1: Initialize Level 1 (Goal × Supplement Evidence)
        self.initialize_level1_banking()
        
        # Step 2: Initialize Level 2 (Profile-Specific Reasoning)  
        self.initialize_level2_banking()
        
        # Step 3: Save banks to storage
        self.save_banks()
        
        self.logger.info("SUCCESS: Banking initialization complete!")
        
    def initialize_level1_banking(self):
        """Pre-compute evidence grades for all goal × supplement combinations using shared aggregator over cards"""
        self.logger.info("=== Level 1: Computing Goal × Supplement Evidence Grades (cards + shared aggregator) ===")

        goals = BANKING_BUCKETS["goal"]
        total_combinations = len(goals) * len(COMMON_SUPPLEMENTS)
        processed = 0
        cards_dir = Path("data/cards")
        if not cards_dir.exists():
            self.logger.warning(f"Cards directory not found: {cards_dir}. Level 1 may be incomplete.")

        for goal in goals:
            self.logger.info(f"Processing {goal} goal...")
            for supplement in COMMON_SUPPLEMENTS:
                try:
                    cards = load_cards_for(supplement, goal, cards_dir)
                    if not cards:
                        # No cards for this combination; default to D
                        agg = {"grade": "D", "pooled_effect": 0.0, "consistency": 0.0, "confidence": 0.0, "weight": 0.0}
                        publications = []
                        paper_count = 0
                    else:
                        agg = pool_and_grade(cards, self.cfg) if self.cfg else {"grade": "D"}
                        # Build top refs into minimal publication list from cards meta
                        pmids = set(agg.get("top_refs", []))
                        publications = []
                        for c in cards:
                            pmid = str((c.get("meta") or {}).get("pmid") or "")
                            if pmid and (not pmids or pmid in pmids):
                                publications.append({
                                    "title": (c.get("meta") or {}).get("title", ""),
                                    "doi": (c.get("meta") or {}).get("doi", ""),
                                    "pmid": pmid,
                                    "journal": (c.get("meta") or {}).get("journal", ""),
                                    "year": (c.get("meta") or {}).get("year", ""),
                                    "url_pub": (c.get("meta") or {}).get("url_pub", ""),
                                    "study_type": (c.get("meta") or {}).get("study_type", ""),
                                })
                                if len(publications) >= 3:
                                    break
                        paper_count = len(cards)

                    bank_key = f"{goal}:{supplement}"
                    self.level1_bank[bank_key] = {
                        "grade": agg.get("grade", "D"),
                        "goal": goal,
                        "supplement": supplement,
                        "paper_count": paper_count,
                        "publications": publications,
                        "pooled_effect": agg.get("pooled_effect"),
                        "consistency": agg.get("consistency"),
                        "confidence": agg.get("confidence"),
                        "last_updated": datetime.now().isoformat(),
                        "index_version": self.index_version,
                    }
                except Exception as e:
                    self.logger.warning(f"Failed L1 for {supplement}+{goal}: {e}")
                    self.level1_bank[f"{goal}:{supplement}"] = {
                        "grade": "D",
                        "goal": goal,
                        "supplement": supplement,
                        "paper_count": 0,
                        "publications": [],
                        "last_updated": datetime.now().isoformat(),
                        "index_version": self.index_version,
                    }

                processed += 1
                if processed % 20 == 0:
                    self.logger.info(f"Progress: {processed}/{total_combinations} ({processed/total_combinations*100:.1f}%)")

        self.logger.info(f"SUCCESS: Level 1 complete: {len(self.level1_bank)} evidence grades computed")
    
    def initialize_level2_banking(self):
        """Pre-compute profile-specific reasoning for all profile combinations"""
        self.logger.info("=== Level 2: Computing Profile-Specific Reasoning ===")
        
        # Generate all profile combinations
        profiles = self.generate_all_profiles()
        total_combinations = len(profiles) * len(COMMON_SUPPLEMENTS)
        processed = 0
        
        for profile in profiles:
            bank_key = generate_bank_key(profile)
            self.logger.info(f"Processing profile: {bank_key}")
            
            # Get papers for this profile's goal
            goal_papers = self.get_papers_for_goal(profile.goal)
            
            profile_reasoning = {}
            
            for supplement in COMMON_SUPPLEMENTS:
                # Get Level 1 evidence grade
                l1_key = f"{profile.goal}:{supplement}"
                evidence_grade = self.level1_bank.get(l1_key, {}).get("grade", "D")
                
                # Generate profile-specific reasoning
                try:
                    reasoning_result = generate_profile_specific_reasoning(
                        supplement, profile, evidence_grade, goal_papers, bank_key
                    )
                    profile_reasoning[supplement] = {
                        "reasoning": reasoning_result.get("reasoning", f"May provide benefits for {profile.goal} goals (Grade {evidence_grade})"),
                        "publications": reasoning_result.get("publications", []),
                        "evidence_grade": evidence_grade,
                        "last_updated": datetime.now().isoformat()
                    }
                except Exception as e:
                    self.logger.warning(f"Failed to generate reasoning for {supplement}: {e}")
                    profile_reasoning[supplement] = {
                        "reasoning": f"May provide benefits for {profile.goal} goals (Grade {evidence_grade})",
                        "publications": [],
                        "evidence_grade": evidence_grade,
                        "last_updated": datetime.now().isoformat()
                    }
                
                processed += 1
                self.logger.info(f"  {supplement} for {bank_key}: Grade {evidence_grade}")
                
                if processed % 50 == 0:
                    self.logger.info(f"Progress: {processed}/{total_combinations} ({processed/total_combinations*100:.1f}%)")
            
            # Store profile reasoning
            self.level2_bank[bank_key] = {
                "profile_key": bank_key,
                "goal": profile.goal,
                "weight_bin": get_weight_bin(profile.weight_kg),
                "sex": getattr(profile, 'sex', 'other'),
                "age_bin": get_age_bin(profile.age),
                "supplements": profile_reasoning,
                "last_updated": datetime.now().isoformat(),
                "index_version": self.index_version
            }
        
        self.logger.info(f"SUCCESS: Level 2 complete: {len(self.level2_bank)} profile reasoning sets computed")
    
    def generate_all_profiles(self) -> List[UserProfile]:
        """Generate all possible profile combinations for banking"""
        profiles = []
        
        goals = BANKING_BUCKETS['goal']
        weight_bins = BANKING_BUCKETS['weight_bin'] 
        sexes = BANKING_BUCKETS['sex']
        age_bins = BANKING_BUCKETS['age_bin']
        
        # Weight bin to kg mapping
        weight_mapping = {
            "xs": 55,     # <60kg
            "small": 65,  # 60-70kg  
            "medium": 77, # 70-85kg
            "large": 92,  # 85-100kg
            "xl": 110     # 100kg+
        }
        
        # Age bin to age mapping
        age_mapping = {
            "minor": 16,   # 13-17
            "young": 25,   # 18-29
            "adult": 40,   # 30-49  
            "mature": 60   # 50+
        }
        
        for goal in goals:
            for weight_bin in weight_bins:
                for sex in sexes:
                    for age_bin in age_bins:
                        weight_kg = weight_mapping[weight_bin]
                        age = age_mapping[age_bin]
                        
                        profile = UserProfile(
                            goal=goal,
                            weight_kg=weight_kg,
                            age=age,
                            sex=sex if sex != "other" else None,
                            caffeine_sensitive=False,
                            pregnancy=False
                        )
                        profiles.append(profile)
        
        return profiles
    
    def get_papers_for_goal(self, goal: str) -> List[Dict]:
        """Get papers relevant to a specific goal (with caching)"""
        if goal in self.papers_cache:
            return self.papers_cache[goal]
        
        # Search for papers relevant to this goal
        goal_queries = {
            "strength": "strength power 1RM force",
            "hypertrophy": "hypertrophy muscle mass lean mass muscle growth", 
            "endurance": "endurance VO2 aerobic cardio fatigue",
            "weight_loss": "weight loss fat loss body composition metabolism",
            "performance": "performance athletic exercise training",
            "general": "health wellness general overall"
        }
        
        query = goal_queries.get(goal, goal)
        
        try:
            # Get papers from search index (search_docs already returns the 'value' array)
            papers = search_docs(query=query, top=50)
            
            # Cache the results
            self.papers_cache[goal] = papers
            self.logger.info(f"Retrieved {len(papers)} papers for {goal} goal")
            
            return papers
            
        except Exception as e:
            self.logger.warning(f"Failed to retrieve papers for {goal}: {e}")
            self.papers_cache[goal] = []
            return []
    
    def save_banks(self):
        """Save banking data to files"""
        self.logger.info("Saving banking data...")
        
        # Save Level 1 bank
        with open("level1_evidence_bank.json", "w") as f:
            json.dump(self.level1_bank, f, indent=2)
        self.logger.info(f"Level 1 bank saved: {len(self.level1_bank)} entries")
        
        # Save Level 2 bank  
        with open("level2_reasoning_bank.json", "w") as f:
            json.dump(self.level2_bank, f, indent=2)
        self.logger.info(f"Level 2 bank saved: {len(self.level2_bank)} entries")
        
        # Save summary
        summary = {
            "initialization_date": datetime.now().isoformat(),
            "index_version": os.getenv("INDEX_VERSION", "v1"),
            "level1_entries": len(self.level1_bank),
            "level2_entries": len(self.level2_bank),
            "goals": BANKING_BUCKETS['goal'],
            "supplements": COMMON_SUPPLEMENTS,
            "profile_combinations": len(self.level2_bank)
        }
        
        with open("banking_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        self.logger.info("SUCCESS: All banking data saved successfully!")


def main():
    """Main initialization function"""
    print("=== EvidentFit Banking Initialization ===")
    print("=" * 50)
    
    # Initialize banking system
    initializer = BankingInitializer()
    initializer.initialize_all_banks()
    
    print("\n🎉 Banking initialization complete!")
    print("The system is now ready with pre-computed evidence grades and reasoning.")


if __name__ == "__main__":
    main()
