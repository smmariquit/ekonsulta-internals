import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Discord bot token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Firestore credentials file
FIRESTORE_CREDENTIALS = "internals-bot-firebase-adminsdk-fbsvc-04121b2125.json"

# Logging configuration
LOG_FILE = "discord.log"

# Bot settings
COMMAND_PREFIX = "!"
INTENTS = {
    "messages": True,
    "guilds": True,
    "message_content": True,
}

# Scheduler settings (if needed)
SCHEDULER_TIMEZONE = "UTC"

# Default DSM time (used if no time is set in Firestore)
DEFAULT_DSM_TIME = "09:00"  # 9:00 AM
