import asyncio
import os
from services.ai_service import AIService

async def main():
    """Tests the AIService by generating a simple response."""
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("🔴 GEMINI_API_KEY environment variable not found or not set.")
        print("Please ensure your API key is correctly set as an environment variable.")
        return

    print("🟢 GEMINI_API_KEY found. Initializing AI Service...")
    ai_service = AIService()
    ai_service.set_api_key(api_key)
    
    prompt = "Say 'Hello, World!' in a friendly tone."
    
    try:
        print("⏳ Generating response from AI service...")
        response = await ai_service.generate_response(prompt)
        print("\n✅ AI Service Verification Successful!")
        print(f"   Response: {response}")
    except Exception as e:
        print("\n❌ AI Service Verification Failed!")
        print(f"   An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 