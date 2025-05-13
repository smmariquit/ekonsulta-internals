"""Default configuration settings for the bot."""

DEFAULT_CONFIG = {
    'standup_hour': 9,
    'standup_minute': 15,
    'thread_name_template': "Daily Stand-up {date}",
    'thread_auto_archive_duration': 10080,  # 7 days in minutes (maximum allowed by Discord)
    'deadline_hours': 12,  # Hours after DSM start time
    'skipped_dates': [],  # List of dates to skip DSM (format: YYYY-MM-DD)
    'use_threads': True,  # Whether to use threads for DSMs
    'dsm_channel_id': None  # Channel ID where DSMs will be posted
} 