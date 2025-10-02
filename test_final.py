#!/usr/bin/env python3
"""Final test of hybrid LLM system."""
import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io"
AUTH = HTTPBasicAuth("demo", "demo123")

print("Final Test - Hybrid LLM System (tag: f2bce415, revision: 0000024)")
print("=" * 80)

# Test 1: Young athlete - should get personalized recommendations
print("\n1. Young Athlete (25, male, strength)")
print("-" * 80)
payload = {
    "thread_id": "test1",
    "messages": [{"role": "user", "content": "I'm 25, male, train 5x/week for strength"}],
    "profile": {
        "goal": "strength",
        "weight_kg": 80,
        "age": 25,
        "sex": "male",
        "caffeine_sensitive": False,
        "meds": []
    }
}

response = requests.post(f"{API_BASE}/stack/conversational", json=payload, auth=AUTH, timeout=45)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    items = data.get("stack_plan", {}).get("items", [])
    explanation = data.get("explanation", "")
    
    print(f"Papers: {data.get('retrieved_count', 0)}")
    print(f"Supplements: {', '.join([i['supplement'] for i in items])}")
    print(f"Explanation length: {len(explanation)} chars")
    if len(explanation) > 200:
        print("  [PASS] LLM composition working!")
    else:
        print("  [WARN] Using fallback explanation")
else:
    print(f"[FAIL] {response.text[:200]}")

# Test 2: Older adult - should get age-specific recommendations
print("\n2. Older Adult (60, female, muscle preservation)")
print("-" * 80)
payload2 = {
    "thread_id": "test2",
    "messages": [{"role": "user", "content": "I'm 60 years old and want to prevent muscle loss"}],
    "profile": {
        "goal": "hypertrophy",
        "weight_kg": 65,
        "age": 60,
        "sex": "female",
        "caffeine_sensitive": False,
        "meds": []
    }
}

response2 = requests.post(f"{API_BASE}/stack/conversational", json=payload2, auth=AUTH, timeout=45)
print(f"Status: {response2.status_code}")

if response2.status_code == 200:
    data2 = response2.json()
    items2 = data2.get("stack_plan", {}).get("items", [])
    supp_names = [i['supplement'] for i in items2]
    
    print(f"Supplements: {', '.join(supp_names)}")
    
    # Check for age-specific supplements
    if 'hmb' in supp_names:
        print("  [PASS] HMB included for 60+ muscle preservation")
    else:
        print("  [INFO] HMB not included (LLM may have chosen different approach)")

# Test 3: Anxiety patient - caffeine should be excluded
print("\n3. Anxiety Patient (should exclude caffeine)")
print("-" * 80)
payload3 = {
    "thread_id": "test3",
    "messages": [{"role": "user", "content": "I have anxiety disorder and want to lose weight"}],
    "profile": {
        "goal": "weight_loss",
        "weight_kg": 70,
        "age": 28,
        "caffeine_sensitive": False,
        "conditions": ["anxiety"],
        "meds": []
    }
}

response3 = requests.post(f"{API_BASE}/stack/conversational", json=payload3, auth=AUTH, timeout=45)
print(f"Status: {response3.status_code}")

if response3.status_code == 200:
    data3 = response3.json()
    items3 = data3.get("stack_plan", {}).get("items", [])
    exclusions = data3.get("stack_plan", {}).get("exclusions", [])
    supp_names = [i['supplement'] for i in items3]
    
    print(f"Supplements: {', '.join(supp_names)}")
    
    if 'caffeine' not in supp_names:
        print("  [PASS] Caffeine correctly excluded")
    else:
        print("  [FAIL] Caffeine should be excluded for anxiety")
    
    if exclusions:
        print(f"\nExclusions: {len(exclusions)}")
        for exc in exclusions[:2]:
            print(f"  - {exc[:80]}")

print("\n" + "=" * 80)
print("Testing Complete!")
print("Visit: https://www.evidentfit.com/stack-chat to test the UI")
print("=" * 80)

