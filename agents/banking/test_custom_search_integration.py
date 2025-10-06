"""
Test script to validate Level 1 banking integration with custom search API.
Tests the enhanced structured summaries integration without requiring full environment setup.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any

# Add paper processor to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'paper_processor'))

# Import custom search API
from search_api import SearchAPI

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_custom_search_integration():
    """Test the custom search API integration with Level 1 banking logic."""
    
    print("=== Testing Custom Search API Integration ===")
    
    # Initialize custom search API
    try:
        # Use relative path to paper processor data
        data_path = os.path.join(os.path.dirname(__file__), '..', 'paper_processor', 'test_optimized_data')
        search_api = SearchAPI(data_path)
        print("+ Custom search API initialized successfully")
    except Exception as e:
        print(f"X Failed to initialize custom search API: {e}")
        return False
    
    # Test supplement evidence retrieval
    test_cases = [
        ("creatine", "strength"),
        ("protein", "hypertrophy"),
        ("caffeine", "endurance")
    ]
    
    results = {}
    
    for supplement, goal in test_cases:
        print(f"\n--- Testing {supplement} + {goal} ---")
        
        try:
            # Get papers using custom search API
            papers = search_api.get_supplement_evidence_by_goal(supplement, goal, limit=10)
            print(f"Found {len(papers)} papers")
            
            if papers:
                # Test quality score extraction
                paper = papers[0]
                quality_scores = paper.get("quality_scores", {})
                overall_score = quality_scores.get("overall", 0) if isinstance(quality_scores, dict) else 0
                print(f"Quality score: {overall_score}")
                
                # Test effect size extraction
                outcome_measures = paper.get("outcome_measures", {})
                effect_sizes = []
                if isinstance(outcome_measures, dict):
                    for goal_category, measures in outcome_measures.items():
                        if isinstance(measures, dict):
                            for measure_key, measure_data in measures.items():
                                if isinstance(measure_data, dict) and "effect_size" in measure_data:
                                    effect_sizes.append({
                                        "measure": measure_data.get("measure", "Unknown"),
                                        "effect_size": measure_data["effect_size"],
                                        "goal_category": goal_category
                                    })
                
                print(f"Effect sizes found: {len(effect_sizes)}")
                for effect in effect_sizes[:2]:  # Show first 2
                    print(f"  - {effect['measure']}: {effect['effect_size']} ({effect['goal_category']})")
                
                # Test evidence summary
                summary = search_api.get_evidence_summary(supplement, goal)
                print(f"Evidence grade: {summary['evidence_grade']}")
                print(f"Total papers: {summary['total_papers']}")
                
                results[f"{supplement}:{goal}"] = {
                    "papers_found": len(papers),
                    "quality_score": overall_score,
                    "effect_sizes": len(effect_sizes),
                    "evidence_grade": summary['evidence_grade'],
                    "total_papers": summary['total_papers']
                }
            else:
                print("No papers found")
                results[f"{supplement}:{goal}"] = {
                    "papers_found": 0,
                    "quality_score": 0,
                    "effect_sizes": 0,
                    "evidence_grade": "D",
                    "total_papers": 0
                }
                
        except Exception as e:
            print(f"X Error testing {supplement} + {goal}: {e}")
            results[f"{supplement}:{goal}"] = {"error": str(e)}
    
    # Summary
    print("\n=== Test Results Summary ===")
    for key, result in results.items():
        if "error" in result:
            print(f"{key}: ERROR - {result['error']}")
        else:
            print(f"{key}: Grade {result['evidence_grade']}, {result['papers_found']} papers, {result['effect_sizes']} effect sizes")
    
    # Check if we have good results
    successful_tests = sum(1 for r in results.values() if "error" not in r and r.get("papers_found", 0) > 0)
    total_tests = len(test_cases)
    
    print(f"\n=== Integration Test Results ===")
    print(f"Successful tests: {successful_tests}/{total_tests}")
    
    if successful_tests == total_tests:
        print("+ All tests passed! Custom search API integration working correctly.")
        return True
    else:
        print("X Some tests failed. Check the results above.")
        return False

def test_evidence_grading_logic():
    """Test the evidence grading logic with enhanced structured summaries."""
    
    print("\n=== Testing Evidence Grading Logic ===")
    
    try:
        # Use relative path to paper processor data
        data_path = os.path.join(os.path.dirname(__file__), '..', 'paper_processor', 'test_optimized_data')
        search_api = SearchAPI(data_path)
        
        # Test creatine + strength (should be Grade A)
        creatine_papers = search_api.get_supplement_evidence_by_goal("creatine", "strength")
        if creatine_papers:
            paper = creatine_papers[0]
            
            # Test quality score extraction
            quality_scores = paper.get("quality_scores", {})
            overall_score = quality_scores.get("overall", 0) if isinstance(quality_scores, dict) else 0
            print(f"Creatine paper quality score: {overall_score}")
            
            # Test study type
            study_type = paper.get("study_type", "")
            print(f"Study type: {study_type}")
            
            # Test outcome measures
            outcome_measures = paper.get("outcome_measures", {})
            if isinstance(outcome_measures, dict):
                for goal_category, measures in outcome_measures.items():
                    if isinstance(measures, dict):
                        for measure_key, measure_data in measures.items():
                            if isinstance(measure_data, dict):
                                effect_size = measure_data.get("effect_size", 0)
                                p_value = measure_data.get("p_value", 0)
                                clinical_significance = measure_data.get("clinical_significance", False)
                                print(f"  {measure_data.get('measure', 'Unknown')}: effect_size={effect_size}, p_value={p_value}, significant={clinical_significance}")
            
            # Test evidence summary
            summary = search_api.get_evidence_summary("creatine", "strength")
            print(f"Evidence grade: {summary['evidence_grade']}")
            print(f"Key findings: {summary['key_findings'][0] if summary['key_findings'] else 'None'}")
            
            return summary['evidence_grade'] == 'A'
        else:
            print("No creatine papers found")
            return False
            
    except Exception as e:
        print(f"Error in evidence grading test: {e}")
        return False

if __name__ == "__main__":
    # Run tests
    integration_success = test_custom_search_integration()
    grading_success = test_evidence_grading_logic()
    
    print(f"\n=== Final Results ===")
    print(f"Integration test: {'PASS' if integration_success else 'FAIL'}")
    print(f"Grading test: {'PASS' if grading_success else 'FAIL'}")
    
    if integration_success and grading_success:
        print("+ All tests passed! Level 1 banking integration with custom search API is working correctly.")
        print("+ Enhanced structured summaries are being used effectively.")
        print("+ Evidence grading is producing correct results (creatine + strength = Grade A).")
    else:
        print("X Some tests failed. Check the output above for details.")
