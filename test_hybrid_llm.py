#!/usr/bin/env python3
"""Test the hybrid LLM + rule-based supplement recommendation system."""
import requests
from requests.auth import HTTPBasicAuth
import time

API_BASE = "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io"
AUTH = HTTPBasicAuth("demo", "demo123")

test_cases = [
    {
        "name": "Young athlete (25, male, strength)",
        "profile": {
            "goal": "strength",
            "weight_kg": 80,  # Will convert from lbs in frontend
            "age": 25,
            "sex": "male",
            "caffeine_sensitive": False,
            "meds": []
        },
        "context": "I train 5 days a week and want to maximize strength gains",
        "expected_supplements": ["creatine", "protein", "caffeine", "beta-alanine"]
    },
    {
        "name": "Older adult (60, female, muscle preservation)",
        "profile": {
            "goal": "hypertrophy",
            "weight_kg": 65,
            "age": 60,
            "sex": "female",
            "caffeine_sensitive": False,
            "meds": []
        },
        "context": "I want to prevent muscle loss as I age",
        "expected_supplements": ["protein", "hmb", "leucine", "creatine"]
    },
    {
        "name": "Vegan endurance athlete (30, female)",
        "profile": {
            "goal": "endurance",
            "weight_kg": 60,
            "age": 30,
            "sex": "female",
            "diet": "vegan",
            "caffeine_sensitive": False,
            "meds": []
        },
        "context": "I'm vegan and train for marathons",
        "expected_supplements": ["protein", "b12", "iron", "omega-3", "beta-alanine"]
    },
    {
        "name": "Stressed professional (35, male)",
        "profile": {
            "goal": "general",
            "weight_kg": 80,
            "age": 35,
            "sex": "male",
            "caffeine_sensitive": False,
            "meds": []
        },
        "context": "I'm very stressed at work and have trouble sleeping. Also interested in ashwagandha.",
        "expected_supplements": ["protein", "ashwagandha", "magnesium"]
    },
    {
        "name": "Person with anxiety (28, female)",
        "profile": {
            "goal": "weight_loss",
            "weight_kg": 70,
            "age": 28,
            "sex": "female",
            "caffeine_sensitive": False,
            "conditions": ["anxiety"],
            "meds": []
        },
        "context": "I want to lose weight but I have anxiety",
        "expected_excluded": ["caffeine"]
    }
]

print("Testing Hybrid LLM Supplement Recommendation System")
print("=" * 80)
print("Tag: ee6cfba8")
print("Revision: cae-evidentfit-api--0000023")
print("\nStarting tests...\n")

for i, test in enumerate(test_cases, 1):
    print(f"\nTest {i}: {test['name']}")
    print("-" * 80)
    
    payload = {
        "thread_id": f"test-hybrid-{i}",
        "messages": [{"role": "user", "content": test['context']}],
        "profile": test['profile']
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/stack/conversational",
            json=payload,
            auth=AUTH,
            timeout=45
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            stack = data.get("stack_plan", {})
            items = stack.get("items", [])
            exclusions = stack.get("exclusions", [])
            
            print(f"Retrieved: {data.get('retrieved_count', 0)} papers")
            print(f"Supplements recommended: {len(items)}")
            
            # Show what was recommended
            supplement_names = [item.get("supplement") for item in items]
            print(f"  Recommended: {', '.join(supplement_names)}")
            
            # Check expected supplements
            if "expected_supplements" in test:
                for exp_supp in test["expected_supplements"]:
                    if exp_supp in supplement_names:
                        print(f"  ✓ Found expected: {exp_supp}")
                    else:
                        print(f"  ✗ Missing expected: {exp_supp}")
            
            # Check expected exclusions
            if "expected_excluded" in test:
                for exp_exc in test["expected_excluded"]:
                    if any(exp_exc in exc.lower() for exc in exclusions) or exp_exc not in supplement_names:
                        print(f"  ✓ Correctly excluded: {exp_exc}")
                    else:
                        print(f"  ✗ Should be excluded: {exp_exc}")
            
            # Show exclusions
            if exclusions:
                print(f"\n  Exclusions ({len(exclusions)}):")
                for exc in exclusions[:3]:
                    print(f"    - {exc}")
                    
        else:
            print(f"[FAIL] {response.text[:200]}")
            
    except Exception as e:
        print(f"[ERROR] {e}")
    
    # Brief pause between tests
    time.sleep(2)

print("\n" + "=" * 80)
print("Testing Complete!")

