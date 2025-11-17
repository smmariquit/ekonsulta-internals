#!/usr/bin/env python3
"""
Script to help set up Railway environment variables for Firebase credentials.
Run this locally to get the properly formatted environment variable value.
"""

import json
import os

def main():
    """Read Firebase credentials and output environment variable format."""
    
    # Try to read the Firebase credentials file
    creds_file = 'firebase-credentials.json'
    
    if not os.path.exists(creds_file):
        print(f"❌ Error: {creds_file} not found!")
        print("Make sure you have the Firebase credentials file in the project root.")
        return
    
    try:
        # Read and parse the credentials file
        with open(creds_file, 'r') as f:
            creds = json.load(f)
        
        # Convert back to compact JSON string
        creds_json = json.dumps(creds, separators=(',', ':'))
        
        print("🚀 Railway Environment Variable Setup")
        print("=" * 50)
        print("1. Go to your Railway project dashboard")
        print("2. Navigate to Variables tab")
        print("3. Add a new environment variable:")
        print("   Name: FIREBASE_CREDENTIALS")
        print("   Value: (copy the JSON below)")
        print("=" * 50)
        print("Firebase Credentials JSON (copy this entire line):")
        print()
        print(creds_json)
        print()
        print("=" * 50)
        print("✅ After setting this environment variable, redeploy your Railway app!")
        
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {creds_file}: {e}")
    except Exception as e:
        print(f"❌ Error reading {creds_file}: {e}")

if __name__ == "__main__":
    main()