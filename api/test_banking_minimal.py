#!/usr/bin/env python3
"""
Test banking system with minimal setup - no Azure dependencies
Creates mock banking files to test the system
"""

import json
import sys
from datetime import datetime

# Add shared directory to path
sys.path.append('../shared')

def create_mock_level1_bank():
    """Create mock Level 1 evidence bank"""
    from stack_builder import BANKING_BUCKETS, COMMON_SUPPLEMENTS, FALLBACK_BASE_GRADES
    
    level1_bank = {}
    
    for goal in BANKING_BUCKETS['goal']:
        fallback_grades = FALLBACK_BASE_GRADES.get(goal, {})
        
        for supplement in COMMON_SUPPLEMENTS:
            bank_key = f"{goal}:{supplement}"
            grade = fallback_grades.get(supplement, "D")
            
            level1_bank[bank_key] = {
                "grade": grade,
                "goal": goal,
                "supplement": supplement,
                "paper_count": 10 if grade == "A" else 5 if grade == "B" else 2,
                "last_updated": datetime.now().isoformat(),
                "index_version": "v1-2025-09-25"
            }
    
    return level1_bank

def create_mock_level2_bank():
    """Create mock Level 2 reasoning bank"""
    from stack_builder import BANKING_BUCKETS, COMMON_SUPPLEMENTS
    from evidentfit_shared.types import UserProfile
    
    level2_bank = {}
    
    # Weight bin to kg mapping
    weight_mapping = {
        "xs": 55, "small": 65, "medium": 77, "large": 92, "xl": 110
    }
    
    # Age bin to age mapping  
    age_mapping = {
        "minor": 16, "young": 25, "adult": 40, "mature": 60
    }
    
    for goal in BANKING_BUCKETS['goal']:
        for weight_bin in BANKING_BUCKETS['weight_bin']:
            for sex in BANKING_BUCKETS['sex']:
                for age_bin in BANKING_BUCKETS['age_bin']:
                    
                    # Generate bank key
                    bank_key = f"{goal}:{weight_bin}:{sex}:{age_bin}"
                    
                    # Create mock reasoning for each supplement
                    supplements_reasoning = {}
                    for supplement in COMMON_SUPPLEMENTS[:10]:  # Limit to first 10 for testing
                        reasoning = f"For your profile ({age_mapping[age_bin]}yo {sex}, {goal}), {supplement} may provide benefits based on research evidence."
                        
                        supplements_reasoning[supplement] = {
                            "reasoning": reasoning,
                            "evidence_grade": "B",  # Mock grade
                            "last_updated": datetime.now().isoformat()
                        }
                    
                    level2_bank[bank_key] = {
                        "profile_key": bank_key,
                        "goal": goal,
                        "weight_bin": weight_bin,
                        "sex": sex,
                        "age_bin": age_bin,
                        "supplements": supplements_reasoning,
                        "last_updated": datetime.now().isoformat(),
                        "index_version": "v1-2025-09-25"
                    }
    
    return level2_bank

def main():
    """Create mock banking files for testing"""
    print("Creating mock banking files for testing...")
    
    try:
        # Create Level 1 bank
        level1_bank = create_mock_level1_bank()
        with open("level1_evidence_bank.json", "w") as f:
            json.dump(level1_bank, f, indent=2)
        print(f"SUCCESS: Created level1_evidence_bank.json with {len(level1_bank)} entries")
        
        # Create Level 2 bank
        level2_bank = create_mock_level2_bank()
        with open("level2_reasoning_bank.json", "w") as f:
            json.dump(level2_bank, f, indent=2)
        print(f"SUCCESS: Created level2_reasoning_bank.json with {len(level2_bank)} entries")
        
        # Create summary
        summary = {
            "initialization_date": datetime.now().isoformat(),
            "index_version": "v1-2025-09-25",
            "level1_entries": len(level1_bank),
            "level2_entries": len(level2_bank),
            "mode": "mock_testing",
            "note": "Mock banking files for testing - not based on real research papers"
        }
        
        with open("banking_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        print("SUCCESS: Mock banking system initialized!")
        print("You can now test the API with cached banking data.")
        
    except Exception as e:
        print(f"ERROR: Failed to create mock banking files: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
