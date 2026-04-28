"""
Quick test to verify agent endpoint works

This creates a test agent session to verify the integration is working.
"""

import requests
import json

API_BASE = "http://localhost:8000"

def test_agent_endpoint():
    """Test the agent session creation endpoint."""
    print("Testing agent endpoint...")
    
    # You'll need to replace these with actual values from your database
    test_payload = {
        "cv_id": "your_cv_id_here",  # Replace with actual CV ID
        "jd_id": "your_jd_id_here",  # Replace with actual JD ID
        "company_name": "your_company",  # Replace with actual company
        "job_title": "your_job_title",  # Replace with actual job title
        "scoring_result": {
            "combined_score": 0.85,
            "skill_mandatory_coverage": 0.90,
            "skill_optional_coverage": 0.70
        }
    }
    
    # Note: You'll need authentication token
    # Get token by logging in first
    
    print("\n⚠️  This is a template test script.")
    print("To use it:")
    print("1. Log in to get authentication token")
    print("2. Upload a CV and JD")
    print("3. Run a search to get cv_id and jd_id")
    print("4. Update the test_payload above with real IDs")
    print("5. Add authentication header with your token")
    print("\nExample:")
    print("""
    headers = {
        'Authorization': 'Bearer YOUR_TOKEN_HERE',
        'Content-Type': 'application/json'
    }
    response = requests.post(
        f'{API_BASE}/agent/session',
        json=test_payload,
        headers=headers
    )
    print(response.json())
    """)

if __name__ == "__main__":
    test_agent_endpoint()
