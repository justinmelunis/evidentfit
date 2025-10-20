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
            # Determine banking directory - try agents/banking first, then current directory
            banking_dir = None
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '..', '..', 'agents', 'banking'),
                os.path.dirname(__file__),
                os.getcwd()
            ]
            
            for path in possible_paths:
                if os.path.exists(os.path.join(path, "level1_evidence_bank.json")):
                    banking_dir = path
                    break
            
            if not banking_dir:
                print("WARNING: Banking files not found in any expected location")
                return False
            
            # Load Level 1 bank (accept both flat and nested schemas)
            level1_path = os.path.join(banking_dir, "level1_evidence_bank.json")
            if os.path.exists(level1_path):
                with open(level1_path, "r", encoding="utf-8") as f:
                    l1_raw = json.load(f)
                self.level1_bank = self._normalize_level1(l1_raw)
                print(f"SUCCESS: Level 1 bank loaded: {len(self.level1_bank)} evidence grades")
            
            # Load Level 2 bank (expect mapping of profile_key -> {supplements:{...}})
            level2_path = os.path.join(banking_dir, "level2_reasoning_bank.json")
            if os.path.exists(level2_path):
                with open(level2_path, "r", encoding="utf-8") as f:
                    l2_raw = json.load(f)
                # If file saved as a flat mapping already, keep; else unwrap known container
                if isinstance(l2_raw, dict) and "reasoning_data" in l2_raw:
                    self.level2_bank = l2_raw.get("reasoning_data", {})
                else:
                    self.level2_bank = l2_raw if isinstance(l2_raw, dict) else {}
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
        return entry.get("grade") if isinstance(entry, dict) else (entry if isinstance(entry, str) else None)
    
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
            "goals_covered": len(set((entry.get("goal") if isinstance(entry, dict) else None) for entry in self.level1_bank.values() if isinstance(entry, dict))),
            "supplements_covered": len(set((entry.get("supplement") if isinstance(entry, dict) else None) for entry in self.level1_bank.values() if isinstance(entry, dict))),
            "profiles_covered": len(self.level2_bank)
        }

    def _normalize_level1(self, l1_raw: Dict) -> Dict:
        """
        Accept both schemas:
        - Flat: {"goal:supp": {grade,...}}
        - Nested container with evidence_data: {goals:[], supplements:[], evidence_data: {...}}
        Returns a flat dict mapping "goal:supplement" -> {grade, ...}
        """
        if not isinstance(l1_raw, dict):
            return {}
        # Flat already
        if all(isinstance(v, (dict, str)) for v in l1_raw.values()) and not {"evidence_data","goals","supplements"}.intersection(set(l1_raw.keys())):
            return l1_raw
        evidence = l1_raw.get("evidence_data")
        if isinstance(evidence, dict):
            out = {}
            for k, v in evidence.items():
                # if nested under supplement or goal, try to flatten
                if isinstance(v, dict) and "grade" in v:
                    out[k] = v
                elif isinstance(v, dict):
                    # attempt to detect goal->supp or supp->goal mapping
                    for subk, subv in v.items():
                        if isinstance(subv, dict) and "grade" in subv:
                            out[subk] = subv
                # else ignore
            return out
        # Fallback: try to synthesize from list entries if present
        out = {}
        for k, v in l1_raw.items():
            if isinstance(v, dict) and "grade" in v:
                out[k] = v
        return out


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
