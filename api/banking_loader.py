"""
Banking Loader for EvidentFit

Loads pre-computed evidence grades and reasoning from banking files.
Used by the stack builder to provide fast, cached responses.
"""

import os
import json
from typing import Dict, Optional
from datetime import datetime


class BankingLoader:
    """Loads and manages cached banking data"""
    
    def __init__(self):
        self.level1_bank = {}  # Goal × Supplement evidence grades
        self.level2_bank = {}  # Profile-specific reasoning
        self.loaded = False
        
    def load_banks(self) -> bool:
        """Load banking data from files"""
        try:
            # Load Level 1 bank
            if os.path.exists("level1_evidence_bank.json"):
                with open("level1_evidence_bank.json", "r") as f:
                    self.level1_bank = json.load(f)
                print(f"SUCCESS: Level 1 bank loaded: {len(self.level1_bank)} evidence grades")
            
            # Load Level 2 bank
            if os.path.exists("level2_reasoning_bank.json"):
                with open("level2_reasoning_bank.json", "r") as f:
                    self.level2_bank = json.load(f)
                print(f"SUCCESS: Level 2 bank loaded: {len(self.level2_bank)} profile reasoning sets")
            
            self.loaded = True
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to load banking data: {e}")
            return False
    
    def get_evidence_grade(self, supplement: str, goal: str) -> Optional[str]:
        """Get cached evidence grade for supplement × goal"""
        if not self.loaded:
            return None
            
        bank_key = f"{goal}:{supplement}"
        entry = self.level1_bank.get(bank_key)
        return entry.get("grade") if entry else None
    
    def get_profile_reasoning(self, supplement: str, profile_bank_key: str) -> Optional[dict]:
        """Get cached reasoning for supplement × profile with publications"""
        if not self.loaded:
            return None
            
        profile_entry = self.level2_bank.get(profile_bank_key)
        if not profile_entry:
            return None
            
        supplement_data = profile_entry.get("supplements", {}).get(supplement)
        if not supplement_data:
            return None
            
        # Return both reasoning and publications
        return {
            "reasoning": supplement_data.get("reasoning", ""),
            "publications": supplement_data.get("publications", [])
        }
    
    def get_banking_stats(self) -> Dict:
        """Get statistics about loaded banking data"""
        if not self.loaded:
            return {"loaded": False}
            
        return {
            "loaded": True,
            "level1_entries": len(self.level1_bank),
            "level2_entries": len(self.level2_bank),
            "goals_covered": len(set(entry["goal"] for entry in self.level1_bank.values())),
            "supplements_covered": len(set(entry["supplement"] for entry in self.level1_bank.values())),
            "profiles_covered": len(self.level2_bank)
        }


# Global banking loader instance
banking_loader = BankingLoader()


def get_cached_evidence_grade(supplement: str, goal: str) -> Optional[str]:
    """Get cached evidence grade (Level 1)"""
    return banking_loader.get_evidence_grade(supplement, goal)


def get_cached_reasoning(supplement: str, profile_bank_key: str) -> Optional[dict]:
    """Get cached profile reasoning (Level 2) with publications"""
    return banking_loader.get_profile_reasoning(supplement, profile_bank_key)


def initialize_banking_loader():
    """Initialize the banking loader (call on startup)"""
    return banking_loader.load_banks()


def get_banking_status() -> Dict:
    """Get current banking system status"""
    return banking_loader.get_banking_stats()
