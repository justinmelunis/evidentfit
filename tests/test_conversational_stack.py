"""
Test script for conversational stack API endpoint.

Tests the new /stack/conversational endpoint locally.
"""

import requests
import json
import sys

# Test configuration
# API_BASE = "http://localhost:8000"  # Local development
API_BASE = "https://cae-evidentfit-api.whiteocean-6d9daede.eastus2.azurecontainerapps.io"  # Production

# Basic auth for preview (if needed)
AUTH = ("demo", "demo123")

def test_conversational_stack():
    """Test the conversational stack endpoint with a sample request."""
    
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-12345",
        "messages": [
            {
                "role": "user",
                "content": "What supplements should I take for building muscle and strength?"
            }
        ],
        "profile": {
            "goal": "strength",
            "weight_kg": 80,
            "caffeine_sensitive": False,
            "meds": [],
            "diet": "any",
            "training_freq": "high",
            "diet_protein_g_per_day": 120,
            "creatine_form": "monohydrate"
        }
    }
    
    print("Testing: POST /stack/conversational")
    print(f"URL: {url}")
    print(f"\nRequest payload:")
    print(json.dumps(payload, indent=2))
    print("\n" + "="*80 + "\n")
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"\nResponse:")
        
        if response.status_code == 200:
            data = response.json()
            print(json.dumps(data, indent=2))
            
            # Pretty print key sections
            print("\n" + "="*80)
            print("EXPLANATION:")
            print("="*80)
            print(data.get("explanation", "No explanation"))
            
            print("\n" + "="*80)
            print("STACK ITEMS:")
            print("="*80)
            stack_plan = data.get("stack_plan", {})
            items = stack_plan.get("items", [])
            for item in items:
                print(f"\n{item['supplement'].upper()} (Grade {item['evidence_grade']})")
                print(f"  Why: {item['why']}")
                for dose in item.get('doses', []):
                    print(f"  Dose: {dose['value']} {dose['unit']}")
                    if dose.get('timing'):
                        print(f"  Timing: {dose['timing']}")
                    if dose.get('notes'):
                        for note in dose['notes']:
                            print(f"    • {note}")
            
            print("\n" + "="*80)
            print("WARNINGS & EXCLUSIONS:")
            print("="*80)
            warnings = stack_plan.get("warnings", [])
            if warnings:
                for warning in warnings:
                        print(f"  WARNING: {warning}")
            else:
                print("  No warnings")
            
            exclusions = stack_plan.get("exclusions", [])
            if exclusions:
                print("\nExcluded:")
                for ex in exclusions:
                    print(f"  EXCLUDED: {ex}")
            else:
                print("\nNo exclusions")
            
            print("\n" + "="*80)
            print(f"Retrieved {data.get('retrieved_count', 0)} research papers")
            print("="*80)
            
        else:
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("Connection Error: Is the API server running?")
        print("   Try: cd api && python main.py")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def test_creatine_forms():
    """Test the creatine forms comparison endpoint."""
    
    url = f"{API_BASE}/stack/creatine-forms"
    
    print("\n\n" + "="*80)
    print("Testing: GET /stack/creatine-forms")
    print(f"URL: {url}")
    print("="*80 + "\n")
    
    try:
        response = requests.get(url, auth=AUTH, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\nCreatine Form Comparison:")
            for form, info in data.items():
                print(f"\n{form.upper()}")
                print(f"  Evidence Grade: {info.get('evidence_grade', 'N/A')}")
                print(f"  Creatine Content: {info.get('creatine_content_percent', 'N/A')}%")
                print(f"  Research Support: {info.get('research_support', 'N/A')}")
                print(f"  Cost: {info.get('cost', 'N/A')}")
                print(f"  Recommended for: {info.get('recommended_for', 'N/A')}")
        else:
            print(response.text)
            
    except Exception as e:
        print(f"Error: {e}")

def test_caffeine_sensitive():
    """Test with a caffeine-sensitive user."""
    
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-caffeine-sensitive",
        "messages": [
            {
                "role": "user",
                "content": "I'm sensitive to caffeine. What can I take?"
            }
        ],
        "profile": {
            "goal": "hypertrophy",
            "weight_kg": 70,
            "caffeine_sensitive": True,
            "meds": [],
            "diet_protein_g_per_day": 100
        }
    }
    
    print("\n\n" + "="*80)
    print("Testing: Caffeine-sensitive user")
    print("="*80 + "\n")
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            stack_plan = data.get("stack_plan", {})
            
            # Check if caffeine is capped or excluded
            items = stack_plan.get("items", [])
            caffeine_item = next((i for i in items if i['supplement'] == 'caffeine'), None)
            
            if caffeine_item:
                print("CHECK: Caffeine included with sensitivity caps:")
                for dose in caffeine_item.get('doses', []):
                    print(f"  Dose: {dose['value']} {dose['unit']}")
                    if dose.get('cap_reason'):
                        print(f"  Cap Reason: {dose['cap_reason']}")
            else:
                print("CHECK: Caffeine excluded (as expected for sensitive user)")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Error: {e}")

def test_creatine_hcl():
    """Test asking about creatine HCl."""
    
    url = f"{API_BASE}/stack/conversational"
    
    payload = {
        "thread_id": "test-creatine-hcl",
        "messages": [
            {
                "role": "user",
                "content": "Should I take creatine HCl instead of monohydrate?"
            }
        ],
        "profile": {
            "goal": "strength",
            "weight_kg": 85,
            "caffeine_sensitive": False,
            "meds": [],
            "creatine_form": "hcl"
        }
    }
    
    print("\n\n" + "="*80)
    print("Testing: Creatine HCl question")
    print("="*80 + "\n")
    
    try:
        response = requests.post(url, json=payload, auth=AUTH, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print("EXPLANATION:")
            print(data.get("explanation", "No explanation"))
            
            stack_plan = data.get("stack_plan", {})
            items = stack_plan.get("items", [])
            creatine_item = next((i for i in items if i['supplement'] == 'creatine'), None)
            
            if creatine_item:
                print("\n\nCREATINE DETAILS:")
                for dose in creatine_item.get('doses', []):
                    print(f"  Dose: {dose['value']} {dose['unit']}")
                    if dose.get('notes'):
                        print("  Notes:")
                        for note in dose['notes']:
                            print(f"    • {note}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("="*80)
    print("CONVERSATIONAL STACK API TESTS")
    print("="*80)
    
    # Run tests
    test_conversational_stack()
    test_creatine_forms()
    test_caffeine_sensitive()
    test_creatine_hcl()
    
    print("\n\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)

