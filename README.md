# E-Konsulta Discord Bot Internals

Discord bot for managing daily standup meetings and team coordination.

## Features

- **Daily Standup Meetings (DSM)**: Automated daily standup creation at 9:00 AM
- **Task Tracking**: TODO task extraction and tracking from team messages  
- **Reminders**: Pre-DSM reminders at 8:45 AM
- **Deadline Management**: 9:15 PM deadline for daily task submissions
- **Admin Commands**: Configuration, user management, and debugging tools

## Deployment to Railway

### 1. Firebase Credentials Setup

The bot requires Firebase credentials to function. Since credentials files can't be committed to git, Railway deployment needs environment variables.

#### Get Firebase Credentials for Railway:
```bash
python3 setup_railway_env.py
```

This will output a JSON string that you need to add to Railway as an environment variable.

#### Add to Railway:
1. Go to your Railway project dashboard
2. Navigate to **Variables** tab  
3. Add environment variable:
   - **Name**: `FIREBASE_CREDENTIALS`
   - **Value**: (paste the JSON output from the script above)

### 2. Other Required Environment Variables

Make sure these are also set in Railway:
- `DISCORD_BOT_TOKEN`: Your Discord bot token
- `GEMINI_API_KEY`: Your Gemini API key (required for translator features)

## Running in a VM: Required Credentials

To run this project in a VM, set these environment variables (for example in a `.env` file copied from `.env.example`):

### Required
- `DISCORD_BOT_TOKEN`
- `GEMINI_API_KEY`
- `FIREBASE_TYPE`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_PRIVATE_KEY_ID`
- `FIREBASE_PRIVATE_KEY`
- `FIREBASE_CLIENT_EMAIL`

### Recommended (include from your Firebase service account JSON)
- `FIREBASE_CLIENT_ID`
- `FIREBASE_AUTH_URI`
- `FIREBASE_TOKEN_URI`
- `FIREBASE_AUTH_PROVIDER_X509_CERT_URL`
- `FIREBASE_CLIENT_X509_CERT_URL`
- `FIREBASE_UNIVERSE_DOMAIN`

### 3. Deploy

Railway will automatically deploy when you push to the connected branch.

## Local Development

1. Copy `.env.example` to `.env` and fill in all required values.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```bash
   python3 bot.py
   ```

## Configuration

The bot supports per-server configuration via slash commands:

- `/configure timezone:<timezone> dsm_time:<HH:MM> dsm_channel:<channel>`
- `/simulate_dsm` - Manually trigger a DSM
- `/skip_dsm date:<YYYY-MM-DD>` - Skip DSM on specific date
- `/show_lookback` - Show current task collection settings

## Schedule

- **8:45 AM**: Pre-DSM reminder sent to all team members
- **9:00 AM**: Daily standup meeting starts automatically  
- **9:15 PM**: Deadline for task submissions (12 hours 15 minutes later)
- **9:16 PM**: Final status update with completion summary
