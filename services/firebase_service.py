"""Firebase service for the bot."""
import firebase_admin
from firebase_admin import credentials, firestore
import asyncio
from typing import Dict, Any, Optional
from models.task import Task
from config.default_config import DEFAULT_CONFIG
from utils.logger import get_logger
import datetime

logger = get_logger("firebase_service")

class FirebaseService:
    """Service for handling Firebase operations."""
    
    def __init__(self, credentials_path: str):
        """Initialize Firebase service."""
        cred = credentials.Certificate(credentials_path)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        logger.info("Firebase service initialized")

    async def get_config(self, guild_id: int) -> Dict[str, Any]:
        """Get guild configuration."""
        config_ref = self.db.collection('config').document(str(guild_id))
        config_doc = await asyncio.to_thread(config_ref.get)
        
        if not config_doc.exists:
            logger.info(f"Creating default config for guild {guild_id}")
            await asyncio.to_thread(config_ref.set, DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        
        return config_doc.to_dict()

    async def save_user(self, user_data: Dict[str, Any]) -> None:
        """Save user information."""
        user_ref = self.db.collection('users').document(str(user_data['id']))
        await asyncio.to_thread(user_ref.set, {
            'username': user_data['name'],
            'discriminator': user_data['discriminator'],
            'avatar_url': user_data.get('avatar_url'),
            'joined_at': user_data['joined_at'],
            'last_active': user_data['last_active'],
            'message_id': user_data.get('message_id'),
            'last_updated': user_data['last_updated']
        })
        logger.debug(f"Saved user data for {user_data['name']}")

    async def update_user_activity(self, user_id: int) -> None:
        """Update user's last active timestamp."""
        user_ref = self.db.collection('users').document(str(user_id))
        await asyncio.to_thread(user_ref.update, {
            'last_active': datetime.datetime.now().isoformat()
        })
        logger.debug(f"Updated activity for user {user_id}")

    async def save_tasks(self, user_tasks: Dict[int, Dict]) -> None:
        """Save tasks to Firebase."""
        batch = self.db.batch()
        
        for user_id, user_data in user_tasks.items():
            user_ref = self.db.collection('users').document(str(user_id))
            
            # Update user document with message_id
            batch.update(user_ref, {
                'message_id': user_data["message_id"],
                'last_updated': datetime.datetime.now().isoformat()
            })
            
            # Update tasks subcollection
            tasks_ref = user_ref.collection('tasks')
            # Clear existing tasks
            existing_tasks = await asyncio.to_thread(tasks_ref.get)
            for task in existing_tasks:
                batch.delete(task.reference)
            
            # Add new tasks
            for task in user_data["tasks"]:
                task_doc = tasks_ref.document()
                batch.set(task_doc, task.to_dict())
        
        await asyncio.to_thread(batch.commit)
        logger.info("Saved tasks to Firebase")

    async def load_tasks(self) -> Dict[int, Dict]:
        """Load tasks from Firebase."""
        users_ref = self.db.collection('users')
        users = await asyncio.to_thread(users_ref.get)
        
        user_tasks = {}
        for user_doc in users:
            user_data = user_doc.to_dict()
            user_id = int(user_doc.id)
            
            # Get tasks from subcollection
            tasks_ref = user_doc.reference.collection('tasks')
            tasks = await asyncio.to_thread(tasks_ref.get)
            
            user_tasks[user_id] = {
                "tasks": [Task.from_dict(task.to_dict()) for task in tasks],
                "message_id": user_data.get('message_id')
            }
        
        logger.info("Loaded tasks from Firebase")
        return user_tasks

    async def update_config(self, guild_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update guild configuration."""
        config_ref = self.db.collection('config').document(str(guild_id))
        await asyncio.to_thread(config_ref.update, updates)
        logger.info(f"Updated config for guild {guild_id}")
        return await self.get_config(guild_id) 