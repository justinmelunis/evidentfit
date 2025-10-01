#!/usr/bin/env python3
"""
Test the conversational stack API endpoints.
"""
import requests
from requests.auth import HTTPBasicAuth
import json

API_BASE = "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io"
AUTH = HTTPBasicAuth("demo", "demo123")

def test_creatine_forms():
    """Test GET /stack/creatine-forms"""
    print("\n=== Testing GET /stack/creatine-forms ===")
    url = f"{API_BASE}/stack/creatine-forms"
    
    try:
        response = requests.get(url, auth=AUTH, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            print(f"Number of forms: {len(data.get('forms', []))}")
            
            # Show first form details
            if data.get('forms'):
                first_form = data['forms'][0]
                print(f"\nFirst form: {first_form.get('form')}")
                print(f"  - CME factor: {first_form.get('cme_factor')}")
                print(f"  - Evidence: {first_form.get('evidence_grade')}")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

def test_conversational_stack():
    """Test POST /stack/conversational"""
    print("\n=== Testing POST /stack/conversational ===")
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-123",
        "messages": [
            {"role": "user", "content": "I want to build muscle and need a supplement stack"}
        ],
        "profile": {
            "goal": "hypertrophy",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "meds": [],
            "diet": "any",
            "training_freq": "high"
        }
    }
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            if "stack_plan" in data:
                stack = data["stack_plan"]
                print(f"\nStack tiers: {list(stack.get('tiers', {}).keys())}")
                
                # Show core tier items
                core = stack.get("tiers", {}).get("core", [])
                print(f"Core supplements ({len(core)}):")
                for item in core:
                    print(f"  - {item.get('supplement')}: {item.get('evidence_grade')}")
            
            print(f"\nRetrieved docs: {data.get('retrieved_count')}")
            
            if "explanation" in data:
                print(f"\nExplanation length: {len(data['explanation'])} chars")
                print(f"First 200 chars: {data['explanation'][:200]}...")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

def test_caffeine_sensitive():
    """Test with caffeine sensitive profile"""
    print("\n=== Testing POST /stack/conversational (caffeine sensitive) ===")
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-caffeine",
        "messages": [
            {"role": "user", "content": "I'm sensitive to caffeine but want to improve performance"}
        ],
        "profile": {
            "goal": "performance",
            "weight_kg": 75,
            "caffeine_sensitive": True,
            "meds": [],
            "diet": "any",
            "training_freq": "med"
        }
    }
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            stack = data.get("stack_plan", {})
            
            # Check if caffeine is included
            all_items = []
            for tier_items in stack.get("tiers", {}).values():
                all_items.extend(tier_items)
            
            caffeine_items = [item for item in all_items if "caffeine" in item.get("supplement", "").lower()]
            
            if caffeine_items:
                print(f"Caffeine found: {len(caffeine_items)} items")
                for item in caffeine_items:
                    print(f"  - {item.get('supplement')}: included={item.get('included')}")
                    if not item.get('included'):
                        print(f"    Reason: {item.get('reason')}")
            else:
                print("No caffeine items in stack (correctly excluded)")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

def test_minor_restrictions():
    """Test with minor age profile"""
    print("\n=== Testing POST /stack/conversational (minor) ===")
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-minor",
        "messages": [
            {"role": "user", "content": "I'm 16 and want to get stronger"}
        ],
        "profile": {
            "goal": "strength",
            "weight_kg": 70,
            "age": 16,
            "caffeine_sensitive": False,
            "meds": [],
            "diet": "any",
            "training_freq": "med"
        }
    }
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            stack = data.get("stack_plan", {})
            
            # Check for age-restricted supplements
            all_items = []
            for tier_items in stack.get("tiers", {}).values():
                all_items.extend(tier_items)
            
            restricted = ["tribulus", "tongkat-ali", "daa"]
            restricted_items = [item for item in all_items if any(r in item.get("supplement", "").lower() for r in restricted)]
            
            print(f"Age-restricted supplements found: {len(restricted_items)}")
            for item in restricted_items:
                print(f"  - {item.get('supplement')}: included={item.get('included')}")
                if not item.get('included'):
                    print(f"    Reason: {item.get('reason')}")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    print("Testing Conversational Stack API Endpoints")
    print("=" * 60)
    
    # Run all tests
    test_creatine_forms()
    test_conversational_stack()
    test_caffeine_sensitive()
    test_minor_restrictions()
    
    print("\n" + "=" * 60)
    print("All tests completed!")

