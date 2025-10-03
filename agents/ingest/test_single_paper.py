#!/usr/bin/env python3
"""
Test single paper upload to estimate storage requirements.
"""

import os
import json
from evidentfit_shared.search_client import ensure_index, upsert_docs

def test_single_paper():
    """Upload a single test paper and measure storage"""
    
    # Ensure index exists with simplified schema
    print("Creating index with simplified schema...")
    ensure_index()
    
    # Create a test paper with all the simplified fields
    test_paper = {
        "id": "test_paper_001",
        "pmid": "12345678",
        "doi": "10.1000/test.doi",
        "url_pub": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "title": "Effects of Creatine Monohydrate Supplementation on Strength and Power in Resistance-Trained Athletes: A Randomized, Double-Blind, Placebo-Controlled Trial",
        "content": "Background: Creatine monohydrate is one of the most widely studied and effective ergogenic aids for increasing muscle mass and strength. Objective: To examine the effects of creatine monohydrate supplementation on strength and power in resistance-trained athletes. Methods: Twenty-four resistance-trained male athletes (age: 23.4 ± 2.1 years; body mass: 82.3 ± 8.7 kg) were randomly assigned to either a creatine monohydrate group (n=12) or placebo group (n=12). Participants supplemented with 5 g/day of creatine monohydrate or placebo for 8 weeks while maintaining their regular resistance training program. Strength was assessed using 1-repetition maximum (1RM) tests for bench press and squat. Power was measured using vertical jump height and peak power output during a 30-second Wingate test. Results: The creatine group showed significant improvements in bench press 1RM (pre: 125.3 ± 15.2 kg; post: 138.7 ± 16.8 kg; p<0.05), squat 1RM (pre: 165.4 ± 18.9 kg; post: 178.2 ± 19.4 kg; p<0.05), vertical jump height (pre: 65.2 ± 4.8 cm; post: 68.9 ± 5.1 cm; p<0.05), and peak power output (pre: 1250 ± 180 W; post: 1320 ± 195 W; p<0.05). No significant changes were observed in the placebo group. Conclusion: Creatine monohydrate supplementation significantly improves strength and power in resistance-trained athletes.",
        "summary": None,
        "journal": "Journal of Strength and Conditioning Research",
        "year": 2023,
        "study_type": "RCT",
        "supplements": "creatine",
        "outcomes": "strength,power,muscle mass",
        "primary_goal": "strength",
        "population": "resistance-trained male athletes",
        "sample_size": 24,
        "study_duration": "8 weeks",
        "safety_indicators": "no adverse events reported",
        "dosage_info": "5g/day creatine monohydrate",
        "has_loading_phase": False,
        "has_maintenance_phase": True,
        "has_side_effects": False,
        "has_contraindications": False,
        "reliability_score": 12.0,
        "study_design_score": 8.0,
        "combination_score": 2.0,
        "enhanced_score": 14.0,
        "index_version": "v1-2025-01-03"
    }
    
    print("Uploading test paper...")
    upsert_docs([test_paper])
    
    print("Test paper uploaded successfully!")
    print(f"Paper ID: {test_paper['id']}")
    print(f"Title: {test_paper['title'][:80]}...")
    
    # Calculate estimated size
    paper_json = json.dumps(test_paper)
    paper_size_bytes = len(paper_json.encode('utf-8'))
    paper_size_kb = paper_size_bytes / 1024
    paper_size_mb = paper_size_kb / 1024
    
    print(f"\nStorage Analysis:")
    print(f"Paper size: {paper_size_bytes} bytes ({paper_size_kb:.2f} KB, {paper_size_mb:.4f} MB)")
    
    # Estimate capacity
    storage_limit_mb = 50  # Free tier limit
    estimated_papers = int(storage_limit_mb / paper_size_mb)
    
    print(f"\nCapacity Estimates:")
    print(f"50 MB limit: ~{estimated_papers:,} papers")
    print(f"40 MB (80% of limit): ~{int(40 / paper_size_mb):,} papers")
    print(f"35 MB (70% of limit): ~{int(35 / paper_size_mb):,} papers")
    
    return paper_size_mb, estimated_papers

if __name__ == "__main__":
    test_single_paper()
