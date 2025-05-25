"""Default configuration for the bot."""
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    'timezone': 'UTC',
    'dsm_time': '09:00',
    'dsm_channel_id': None,
    'google_ai_api_key': None,  # Google AI Studio API key
    'skipped_dates': [],
    'admins': [],
    'dsm_messages': {},
    'updated_participants': [],
    'pending_participants': [],
    'standup_hour': 9,
    'standup_minute': 15,
    'thread_name_template': "Daily Stand-up {date}",
    'thread_auto_archive_duration': 10080,  # 7 days in minutes (maximum allowed by Discord)
    'deadline_hours': 12,  # Hours after DSM start time
    'use_threads': True
} 