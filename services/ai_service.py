"""AI service for the bot."""
import os
from dotenv import load_dotenv
import json # For JSON operations
import aiohttp # Async HTTP client
from typing import Optional, Dict, Any

from utils.logging_util import get_logger
load_dotenv()

logger = get_logger("ai_service")

class AIService:
    """Service for handling AI-related functionality."""
    def __init__(self):
        """Initialize the AI service."""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.model = "gemini-2.5-flash"
        self.api_key = None
    
    def set_api_key(self, api_key: str):
        """Set the API key for Google AI Studio."""
        self.api_key = os.getenv("GEMINI_API_KEY")
    
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a response using Google AI Studio."""
        if not self.api_key:
            raise ValueError("API key not set. Please set the API key first.")
        
        try:
            url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
            
            # Prepare the request payload
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            # Add context if provided
            if context:
                payload["contents"][0]["parts"][0]["text"] = f"Context: {json.dumps(context)}\n\nPrompt: {prompt}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        error_data = await response.json()
                        raise Exception(f"API Error: {error_data.get('error', {}).get('message', 'Unknown error')}")
        
        except Exception as e:
            logger.error(f"Error generating AI response: {str(e)}")
            raise
    
    async def analyze_tasks(self, tasks: list) -> Dict[str, Any]:
        """Analyze tasks using AI to provide insights."""
        try:
            # Prepare the prompt
            prompt = f"""Analyze the following tasks and provide insights:
            Tasks: {json.dumps(tasks, indent=2)}
            
            Please provide:
            1. Task completion rate
            2. Common patterns or themes
            3. Potential blockers or challenges
            4. Suggestions for improvement
            """
            
            response = await self.generate_response(prompt)
            return json.loads(response)
        
        except Exception as e:
            logger.error(f"Error analyzing tasks: {str(e)}")
            raise
    
    async def generate_task_summary(self, tasks: list) -> str:
        """Generate a summary of tasks using AI."""
        try:
            # Prepare the prompt
            prompt = f"""Generate a concise summary of the following tasks:
            Tasks: {json.dumps(tasks, indent=2)}
            
            Please provide:
            1. Overall progress
            2. Key achievements
            3. Main challenges
            4. Next steps
            """
            
            return await self.generate_response(prompt)
        
        except Exception as e:
            logger.error(f"Error generating task summary: {str(e)}")
            raise
    
    async def suggest_task_improvements(self, task: Dict[str, Any]) -> str:
        """Suggest improvements for a specific task using AI."""
        try:
            # Prepare the prompt
            prompt = f"""Analyze this task and suggest improvements:
            Task: {json.dumps(task, indent=2)}
            
            Please provide:
            1. Task clarity assessment
            2. Potential improvements
            3. Best practices
            4. Risk mitigation suggestions
            """
            
            return await self.generate_response(prompt)
        
        except Exception as e:
            logger.error(f"Error suggesting task improvements: {str(e)}")
            raise 