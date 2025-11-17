"""Firebase service for the bot."""
import firebase_admin
from firebase_admin import credentials, firestore
import asyncio
import os
import json
from typing import Dict, Any, Optional, List
from models.task import Task
from config.default_config import DEFAULT_CONFIG
from utils.logging_util import get_logger
import datetime
from models.dsm_session import DSMSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = get_logger("firebase_service")

class FirebaseService:
    """Service for handling Firebase operations."""
    
    def __init__(self):
        """Initialize Firebase service."""
        self.db = None
        self.initialize()
        logger.info("Firebase service initialized")

    def initialize(self):
        """Initialize Firebase connection using environment variables only."""
        try:
            # Get Firebase credentials from individual environment variables
            firebase_type = os.getenv('FIREBASE_TYPE')
            firebase_project_id = os.getenv('FIREBASE_PROJECT_ID')
            firebase_private_key_id = os.getenv('FIREBASE_PRIVATE_KEY_ID')
            firebase_private_key = os.getenv('FIREBASE_PRIVATE_KEY')
            firebase_client_email = os.getenv('FIREBASE_CLIENT_EMAIL')
            firebase_client_id = os.getenv('FIREBASE_CLIENT_ID')
            firebase_auth_uri = os.getenv('FIREBASE_AUTH_URI')
            firebase_token_uri = os.getenv('FIREBASE_TOKEN_URI')
            firebase_auth_provider_x509_cert_url = os.getenv('FIREBASE_AUTH_PROVIDER_X509_CERT_URL')
            firebase_client_x509_cert_url = os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
            firebase_universe_domain = os.getenv('FIREBASE_UNIVERSE_DOMAIN')

            # Validate that all required environment variables are present
            if not all([firebase_type, firebase_project_id, firebase_private_key_id, firebase_private_key, firebase_client_email]):
                missing_vars = []
                if not firebase_type: missing_vars.append('FIREBASE_TYPE')
                if not firebase_project_id: missing_vars.append('FIREBASE_PROJECT_ID')
                if not firebase_private_key_id: missing_vars.append('FIREBASE_PRIVATE_KEY_ID')
                if not firebase_private_key: missing_vars.append('FIREBASE_PRIVATE_KEY')
                if not firebase_client_email: missing_vars.append('FIREBASE_CLIENT_EMAIL')
                
                raise ValueError(f"Missing required Firebase environment variables: {', '.join(missing_vars)}")

            # Clean up the private key (replace \\n with actual newlines)
            if firebase_private_key:
                firebase_private_key = firebase_private_key.replace('\\n', '\n')
            
            # Build Firebase credentials dictionary
            firebase_credentials = {
                "type": firebase_type,
                "project_id": firebase_project_id,
                "private_key_id": firebase_private_key_id,
                "private_key": firebase_private_key,
                "client_email": firebase_client_email,
                "client_id": firebase_client_id,
                "auth_uri": firebase_auth_uri,
                "token_uri": firebase_token_uri,
                "auth_provider_x509_cert_url": firebase_auth_provider_x509_cert_url,
                "client_x509_cert_url": firebase_client_x509_cert_url,
                "universe_domain": firebase_universe_domain
            }
            
            # Initialize Firebase
            cred = credentials.Certificate(firebase_credentials)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            logger.info("Firebase connection established using environment variables only")
        except Exception as e:
            logger.error(f"Error initializing Firebase: {str(e)}")
            raise

    async def get_config(self, guild_id: int) -> Dict[str, Any]:
        """Get guild configuration from the guild's config subcollection."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        guild_ref = self.db.collection('guilds').document(str(guild_id))
        config_ref = guild_ref.collection('config').document('settings')
        config_doc = await asyncio.to_thread(config_ref.get)
        
        logger.info(f"[DEBUG] Getting config for guild {guild_id}")
        logger.info(f"[DEBUG] Config document exists: {config_doc.exists}")
        
        if not config_doc.exists:
            logger.info(f"Creating default config for guild {guild_id}")
            default_config = DEFAULT_CONFIG.copy()
            default_config.update({
                'dsm_messages': {},  # Store DSM message IDs here
                'latest_dsm_thread': None,  # Store latest DSM thread info here
                'last_updated': datetime.datetime.now().isoformat()
            })
            await asyncio.to_thread(config_ref.set, default_config)
            return default_config
        
        config_data = config_doc.to_dict()
        logger.info(f"[DEBUG] Retrieved config data: {config_data}")
        return config_data

    async def save_user(self, user_data: Dict[str, Any]) -> None:
        """Save user information."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
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
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        user_ref = self.db.collection('users').document(str(user_id))
        await asyncio.to_thread(user_ref.update, {
            'last_active': datetime.datetime.now().isoformat()
        })
        logger.debug(f"Updated activity for user {user_id}")

    async def save_tasks(self, user_tasks: Dict[int, Dict]) -> None:
        """Save tasks to Firebase."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
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
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
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
        """Update guild configuration in the guild's config subcollection."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        guild_ref = self.db.collection('guilds').document(str(guild_id))
        config_ref = guild_ref.collection('config').document('settings')
        
        # Get current config
        current_config = await self.get_config(guild_id)
        logger.info(f"[DEBUG] Current config before update: {current_config}")
        
        # Update the config
        current_config.update(updates)
        current_config['last_updated'] = datetime.datetime.now().isoformat()
        logger.info(f"[DEBUG] Updated config: {current_config}")
        
        # Save the updated config
        await asyncio.to_thread(config_ref.set, current_config)
        logger.info(f"Updated config for guild {guild_id}")
        return current_config

    async def save_dsm_session(self, session: DSMSession) -> None:
        """Save a DSM session to Firebase."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        session_ref = self.db.collection('dsm_sessions').document()
        await asyncio.to_thread(session_ref.set, session.to_dict())
        logger.info(f"Saved DSM session for guild {session.guild_id}")

    async def get_last_dsm_session(self, guild_id: int) -> Optional[DSMSession]:
        """Get the last DSM session for a guild."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        sessions_ref = self.db.collection('dsm_sessions')
        query = sessions_ref.where('guild_id', '==', guild_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(1)
        sessions = await asyncio.to_thread(query.get)
        
        if not sessions:
            return None
            
        return DSMSession.from_dict(sessions[0].to_dict())

    async def get_dsm_sessions(self, guild_id: int, limit: int = 10) -> List[DSMSession]:
        """Get recent DSM sessions for a guild."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        sessions_ref = self.db.collection('dsm_sessions')
        query = sessions_ref.where('guild_id', '==', guild_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        sessions = await asyncio.to_thread(query.get)
        
        return [DSMSession.from_dict(session.to_dict()) for session in sessions]

    async def update_dsm_session(self, thread_id: int, updates: Dict[str, Any]) -> None:
        """Update a DSM session."""
        if not self.db:
            raise RuntimeError("Firebase database not initialized")
            
        sessions_ref = self.db.collection('dsm_sessions')
        query = sessions_ref.where('thread_id', '==', thread_id).limit(1)
        sessions = await asyncio.to_thread(query.get)
        
        if sessions:
            await asyncio.to_thread(sessions[0].reference.update, updates)
            logger.info(f"Updated DSM session for thread {thread_id}")

    async def save_dsm_message(self, guild_id: int, user_id: str, message_data: dict):
        """Save DSM message IDs to guild's config."""
        try:
            # Get current config
            config = await self.get_config(guild_id)
            
            # Initialize dsm_messages if it doesn't exist
            if 'dsm_messages' not in config:
                config['dsm_messages'] = {}
            
            # Update the message data with timestamp
            message_data['last_updated'] = datetime.datetime.now().isoformat()
            
            # Update the message data in config
            config['dsm_messages'][str(user_id)] = message_data
            
            # Save updated config
            await self.update_config(guild_id, {
                'dsm_messages': config['dsm_messages']
            })
            
            logger.info(f"[DEBUG] Saved DSM message IDs for user {user_id} in guild {guild_id}: {message_data}")
            
        except Exception as e:
            logger.error(f"[DEBUG] Error saving DSM message IDs to Firebase: {str(e)}")
            raise

    async def get_latest_dsm_message(self, guild_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest DSM message IDs for a user from guild's config."""
        try:
            # Get the config
            config = await self.get_config(guild_id)
            
            # Get the message data from config
            dsm_messages = config.get('dsm_messages', {})
            user_messages = dsm_messages.get(str(user_id))
            
            if user_messages:
                logger.info(f"[DEBUG] Retrieved DSM message IDs for user {user_id}: {user_messages}")
                return user_messages
            else:
                logger.info(f"[DEBUG] No DSM message IDs found for user {user_id}")
                return None
            
        except Exception as e:
            logger.error(f"[DEBUG] Error retrieving DSM message IDs from Firebase: {str(e)}")
            return None

    async def load_dsm_messages(self) -> Dict[int, Dict[int, int]]:
        """Load DSM message IDs from guild configs."""
        try:
            if not self.db:
                raise RuntimeError("Firebase database not initialized")
                
            # Get all guild documents
            guilds = await asyncio.to_thread(self.db.collection('guilds').get)
            
            messages = {}
            for guild_doc in guilds:
                guild_id = int(guild_doc.id)
                config_ref = guild_doc.reference.collection('config').document('settings')
                config_doc = await asyncio.to_thread(config_ref.get)
                
                if config_doc.exists:
                    config_data = config_doc.to_dict()
                    # Get DSM messages from config
                    dsm_messages = config_data.get('dsm_messages', {})
                    messages[guild_id] = {
                        int(user_id): message_data 
                        for user_id, message_data in dsm_messages.items()
                    }
            
            logger.info("Loaded DSM messages from guild configs")
            return messages
        except Exception as e:
            logger.error(f"Error loading DSM messages: {str(e)}")
            return {} 