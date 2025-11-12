"""
Test script to verify JD ID generation uses form job_title, not document job_title
"""
import json
import tempfile
import os
from backend.database.mongodb_jd import JDDataInserter

def test_jd_id_priority():
    """Test that form job_title takes precedence over document job_title"""
    
    # Simulate the wrapper created in workflow.py during JD upload
    # User entered "Mobile Application Developer" in the form
    # But the JD document contains "Senior Mobile Developer"
    test_data = {
        "company_name": "google",
        "job_title": "Mobile Application Developer",  # From form (what user typed)
        "company_name_sanitized": "google",
        "job_title_sanitized": "mobile_application_developer",
        "structured_data": {
            "job_title": "Senior Mobile Developer",  # From document content (different!)
            "description": "We are looking for a talented developer...",
            "responsibilities": ["Develop mobile apps", "Write clean code"],
            "requirements": ["5+ years experience", "Flutter/React Native"]
        }
    }
    
    # Create temporary JSON file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(test_data, f, indent=2)
        temp_path = f.name
    
    try:
        # Test the loader
        inserter = JDDataInserter()
        loaded_data = inserter.load_json_file(temp_path)
        
        print("="*70)
        print("TEST: JD ID Generation Priority")
        print("="*70)
        print(f"\n📝 Form Input (User Typed): 'Mobile Application Developer'")
        print(f"📄 Document Content: 'Senior Mobile Developer'")
        print(f"\n✅ Loaded job_title: '{loaded_data.get('job_title')}'")
        
        # Generate ID
        jd_id = inserter.generate_jd_id(loaded_data.get('job_title'), loaded_data.get('company_name'))
        print(f"🔑 Generated JD ID: '{jd_id}'")
        
        # Verify it matches the form input (sanitized)
        expected_id = "mobile_application_developer"
        if jd_id == expected_id:
            print(f"\n✅ SUCCESS: JD ID matches form input!")
            print(f"   Expected: '{expected_id}'")
            print(f"   Got:      '{jd_id}'")
            print(f"\n💡 This means the JD can be found during search using the form job title.")
            return True
        else:
            print(f"\n❌ FAILURE: JD ID doesn't match!")
            print(f"   Expected: '{expected_id}'")
            print(f"   Got:      '{jd_id}'")
            return False
            
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    success = test_jd_id_priority()
    print("="*70)
    if success:
        print("✅ All tests passed! The fix is working correctly.")
    else:
        print("❌ Tests failed! There's still an issue.")
    print("="*70)
