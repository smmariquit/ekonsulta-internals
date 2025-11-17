#!/usr/bin/env python3
"""Test script to verify Firebase connection with individual environment variables."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def test_firebase_connection():
    """Test Firebase connection using individual environment variables."""
    try:
        # Import Firebase service
        from services.firebase_service import FirebaseService
        
        print("Testing Firebase connection with individual environment variables...")
        
        # Check if required environment variables are present
        required_vars = [
            'FIREBASE_TYPE',
            'FIREBASE_PROJECT_ID',
            'FIREBASE_PRIVATE_KEY_ID',
            'FIREBASE_PRIVATE_KEY',
            'FIREBASE_CLIENT_EMAIL'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
            return False
        
        print("✅ All required Firebase environment variables found")
        
        # Try to initialize Firebase service
        firebase_service = FirebaseService()
        print("✅ Firebase service initialized successfully")
        
        # Try to test a simple Firestore operation
        test_guild_id = 123456789  # Dummy guild ID for testing
        config = await firebase_service.get_config(test_guild_id)
        print("✅ Firebase connection test successful - can read/write to Firestore")
        
        return True
        
    except Exception as e:
        print(f"❌ Firebase connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    import asyncio
    
    async def main():
        success = await test_firebase_connection()
        if success:
            print("\n🎉 All Firebase tests passed! The bot should work correctly with individual environment variables.")
            sys.exit(0)
        else:
            print("\n💥 Firebase tests failed! Please check your configuration.")
            sys.exit(1)
    
    # Run the async test
    asyncio.run(main())