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
    'dsm_lookback_hours': 2,  # Hours before DSM to include in task collection
}