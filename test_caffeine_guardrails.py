#!/usr/bin/env python3
"""Test caffeine contraindication guardrails."""
import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io"
AUTH = HTTPBasicAuth("demo", "demo123")

test_cases = [
    {
        "name": "Caffeine Sensitive (should reduce dose)",
        "profile": {
            "goal": "performance",
            "weight_kg": 75,
            "caffeine_sensitive": True,
            "meds": []
        },
        "expected": "included_with_reduced_dose"
    },
    {
        "name": "Minor < 18 (should block)",
        "profile": {
            "goal": "strength",
            "weight_kg": 70,
            "age": 16,
            "caffeine_sensitive": False,
            "meds": []
        },
        "expected": "excluded"
    },
    {
        "name": "Anxiety condition (should block)",
        "profile": {
            "goal": "performance",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "conditions": ["anxiety"],
            "meds": []
        },
        "expected": "excluded"
    },
    {
        "name": "Insomnia condition (should block)",
        "profile": {
            "goal": "performance",
            "weight_kg": 75,
            "caffeine_sensitive": False,
            "conditions": ["insomnia"],
            "meds": []
        },
        "expected": "excluded"
    },
    {
        "name": "MAOI medication (should block)",
        "profile": {
            "goal": "performance",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "meds": ["phenelzine"],  # MAOI
            "conditions": []
        },
        "expected": "excluded"
    },
    {
        "name": "Pregnancy (should cap at 200mg)",
        "profile": {
            "goal": "performance",
            "weight_kg": 70,
            "pregnancy": True,
            "caffeine_sensitive": False,
            "meds": []
        },
        "expected": "included_with_cap"
    },
    {
        "name": "Hypertension (should cap at 200mg)",
        "profile": {
            "goal": "performance",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "conditions": ["hypertension"],
            "meds": []
        },
        "expected": "included_with_cap"
    },
    {
        "name": "Normal user (should include)",
        "profile": {
            "goal": "performance",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "meds": []
        },
        "expected": "included"
    }
]

print("Testing Caffeine Guardrails")
print("=" * 70)

for test in test_cases:
    print(f"\n{test['name']}")
    print("-" * 70)
    
    payload = {
        "thread_id": "test-guardrails",
        "messages": [{"role": "user", "content": "I want to improve performance"}],
        "profile": test["profile"]
    }
    
    try:
        response = requests.post(f"{API_BASE}/stack/conversational", json=payload, auth=AUTH, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            stack = data.get("stack_plan", {})
            items = stack.get("items", [])
            
            caffeine = next((item for item in items if item.get("supplement") == "caffeine"), None)
            
            if test["expected"] == "excluded":
                if not caffeine or not caffeine.get("included", True):
                    print(f"[PASS] Caffeine correctly excluded")
                    if caffeine:
                        print(f"  Reason: {caffeine.get('reason', 'N/A')}")
                else:
                    print(f"[FAIL] Caffeine should be excluded but was included")
                    
            elif test["expected"] == "included":
                if caffeine and caffeine.get("included", True):
                    doses = caffeine.get("doses", [])
                    if doses:
                        print(f"[PASS] Caffeine included with standard dose")
                        print(f"  Dose: {doses[0].get('value')} {doses[0].get('unit')}")
                else:
                    print(f"[FAIL] Caffeine should be included")
                    
            elif test["expected"] == "included_with_reduced_dose":
                if caffeine and caffeine.get("included", True):
                    doses = caffeine.get("doses", [])
                    if doses:
                        dose_value = doses[0].get("value", "")
                        print(f"[PASS] Caffeine included with dose: {dose_value} {doses[0].get('unit')}")
                        if "3-4" in str(dose_value):
                            print(f"  Correctly reduced for sensitivity (3-4 vs 4-6 mg/kg)")
                else:
                    print(f"[FAIL] Caffeine should be included with reduced dose")
                    
            elif test["expected"] == "included_with_cap":
                if caffeine and caffeine.get("included", True):
                    doses = caffeine.get("doses", [])
                    if doses and doses[0].get("notes"):
                        notes = doses[0].get("notes", [])
                        cap_note = next((n for n in notes if "200" in n or "cap" in n.lower()), None)
                        if cap_note:
                            print(f"[PASS] Caffeine included with cap")
                            print(f"  Cap note: {cap_note}")
                        else:
                            print(f"[WARN] Caffeine included but no cap note found")
                            print(f"  Notes: {notes}")
                else:
                    print(f"[FAIL] Caffeine should be included with cap")
        else:
            print(f"[ERROR] API returned {response.status_code}: {response.text[:200]}")
            
    except Exception as e:
        print(f"[ERROR] {e}")

print("\n" + "=" * 70)
print("Testing Complete!")

