import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Discord bot token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

<<<<<<< HEAD
# Firebase configuration - now using individual environment variables
# These are loaded from .env file:
# FIREBASE_TYPE, FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY_ID, 
# FIREBASE_PRIVATE_KEY, FIREBASE_CLIENT_EMAIL, FIREBASE_CLIENT_ID,
# FIREBASE_AUTH_URI, FIREBASE_TOKEN_URI, FIREBASE_AUTH_PROVIDER_X509_CERT_URL,
# FIREBASE_CLIENT_X509_CERT_URL, FIREBASE_UNIVERSE_DOMAIN
=======
# Firestore credentials file
FIRESTORE_CREDENTIALS = "internals-bot-firebase-adminsdk-fbsvc-279fc01645.json"
>>>>>>> recovered-commit-1

# Logging configuration
LOG_FILE = "discord.log"

# Scheduler settings (if needed)
SCHEDULER_TIMEZONE = "UTC"

# Default DSM time (used if no time is set in Firestore)
DEFAULT_DSM_TIME = "09:00"  # 9:00 AM

# DSM reminder time (15 minutes before DSM start)
DEFAULT_DSM_REMINDER_TIME = "08:45"  # 8:45 AM

# DSM deadline (12 hours and 15 minutes after DSM start - 9:15 PM for 9:00 AM start)
DSM_DEADLINE_HOURS = 12
DSM_DEADLINE_MINUTES = 15  # Total: 12 hours 15 minutes after DSM start
