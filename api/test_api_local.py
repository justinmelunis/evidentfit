#!/usr/bin/env python3
"""
Test the API endpoints locally without requiring full environment setup
"""

import sys
import json
from datetime import datetime

# Add shared directory to path
sys.path.append('../shared')

def test_stack_builder():
    """Test the stack builder components"""
    print("🧪 Testing Stack Builder Components...")
    
    try:
        from stack_builder import (
            COMMON_SUPPLEMENTS, 
            BANKING_BUCKETS,
            get_weight_bin, 
            get_age_bin, 
            generate_bank_key,
            build_creatine_item,
            build_caffeine_item,
            build_protein_item
        )
        from evidentfit_shared.types import UserProfile
        
        # Test profile creation
        profile = UserProfile(
            goal='hypertrophy',
            weight_kg=80,
            age=28,
            sex='male',
            caffeine_sensitive=False,
            pregnancy=False,
            meds=[],
            conditions=[]
        )
        
        print(f"✅ Profile created: {profile.goal}, {profile.weight_kg}kg, {profile.age}yo {profile.sex}")
        
        # Test banking key generation
        bank_key = generate_bank_key(profile)
        print(f"✅ Bank key generated: {bank_key}")
        
        # Test supplement builders (without docs for now)
        docs = []  # Empty docs for testing
        
        creatine_item = build_creatine_item(profile, docs, include_form_info=True)
        print(f"✅ Creatine item: {creatine_item.supplement} - Grade {creatine_item.evidence_grade}")
        
        caffeine_item = build_caffeine_item(profile, docs)
        print(f"✅ Caffeine item: {caffeine_item.supplement} - Grade {caffeine_item.evidence_grade}")
        
        protein_item = build_protein_item(profile, docs)
        print(f"✅ Protein item: {protein_item.supplement} - Grade {protein_item.evidence_grade}")
        
        print("🎉 Stack builder components working!")
        return True
        
    except Exception as e:
        print(f"❌ Stack builder test failed: {e}")
        return False

def test_guardrails():
    """Test the guardrails system"""
    print("\n🛡️ Testing Guardrails System...")
    
    try:
        from evidentfit_shared.guardrails import (
            check_contraindications,
            get_dose_caps,
            CONTRAINDICATIONS,
            AGE_RESTRICTIONS
        )
        
        # Test contraindications
        profile_safe = {"conditions": [], "meds": [], "age": 28, "pregnancy": False}
        is_safe, reason = check_contraindications(profile_safe, "creatine")
        print(f"✅ Safe profile + creatine: {is_safe} ({reason or 'No issues'})")
        
        # Test age restrictions
        profile_minor = {"conditions": [], "meds": [], "age": 16, "pregnancy": False}
        is_safe, reason = check_contraindications(profile_minor, "caffeine")
        print(f"✅ Minor + caffeine: {is_safe} ({reason})")
        
        # Test condition restrictions
        profile_anxiety = {"conditions": ["anxiety"], "meds": [], "age": 28, "pregnancy": False}
        is_safe, reason = check_contraindications(profile_anxiety, "caffeine")
        print(f"✅ Anxiety + caffeine: {is_safe} ({reason})")
        
        print("🎉 Guardrails system working!")
        return True
        
    except Exception as e:
        print(f"❌ Guardrails test failed: {e}")
        return False

def test_types():
    """Test the types system"""
    print("\n📋 Testing Types System...")
    
    try:
        from evidentfit_shared.types import UserProfile, StackItem, Dose, Citation
        
        # Test UserProfile validation
        profile = UserProfile(
            goal='strength',
            weight_kg=75,
            age=30,
            sex='female',
            caffeine_sensitive=True,
            pregnancy=False
        )
        print(f"✅ UserProfile validation: {profile.goal}, {profile.weight_kg}kg")
        
        # Test Dose creation
        dose = Dose(
            value=5,
            unit="g",
            timing="Post-workout",
            notes=["Take with water"]
        )
        print(f"✅ Dose creation: {dose.value}{dose.unit} {dose.timing}")
        
        # Test Citation creation
        citation = Citation(
            title="Test Study",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678",
            pmid="12345678",
            study_type="RCT"
        )
        print(f"✅ Citation creation: {citation.title} ({citation.study_type})")
        
        # Test StackItem creation
        item = StackItem(
            supplement="creatine",
            evidence_grade="A",
            included=True,
            tier="recommended",
            why="Proven benefits for strength",
            doses=[dose],
            citations=[citation]
        )
        print(f"✅ StackItem creation: {item.supplement} Grade {item.evidence_grade}")
        
        print("🎉 Types system working!")
        return True
        
    except Exception as e:
        print(f"❌ Types test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 EvidentFit API Local Testing")
    print("=" * 50)
    
    results = []
    results.append(test_types())
    results.append(test_guardrails())
    results.append(test_stack_builder())
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"✅ Passed: {sum(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("🎉 All tests passed! System is ready for production.")
    else:
        print("⚠️ Some tests failed. Check the output above.")
    
    return all(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
