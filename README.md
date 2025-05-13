# Ekonsulta Internal Automations

A Discord bot for managing internal operations, task tracking, and daily standup meetings.

## Features

### Task Management
- Create, update, and track tasks with deadlines
- Task status tracking (pending, in progress, completed)
- Task categorization and priority levels
- Task history and statistics
- Task reminders and notifications

### Daily Standup Meeting (DSM)
- Automated daily standup threads
- Task statistics and progress tracking
- Participant tracking (updated/pending)
- Configurable standup times and deadlines
- Timezone support for all DSM operations
- Manual DSM triggering with previous session finalization

### Configuration
- Guild-specific settings
- Configurable channels and roles
- Timezone settings
- Thread management options
- Task tracking preferences

### Task Tracking
- Real-time task updates
- Task completion tracking
- Task statistics and analytics
- Task history and audit logs
- Task reminders and notifications

### Thread Management
- Automated thread creation and archiving
- Thread-based task discussions
- Thread statistics and analytics
- Thread cleanup and maintenance

## Commands

### Task Management
- `/task create` - Create a new task
- `/task update` - Update an existing task
- `/task complete` - Mark a task as complete
- `/task list` - List all tasks
- `/task stats` - View task statistics

### DSM Commands
- `/dsm` - Trigger a manual DSM
- `/config` - Configure DSM settings
  - `channel` - Set DSM channel
  - `time` - Set standup time
  - `timezone` - Set timezone (e.g., 'Asia/Manila')
  - `deadline` - Set task deadline
  - `thread_duration` - Set thread archive duration
  - `use_threads` - Toggle thread mode

### Configuration
- `/config` - View current configuration
- `/config update` - Update configuration
- `/config reset` - Reset configuration to defaults

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```env
DISCORD_TOKEN=your_discord_token
FIREBASE_CREDENTIALS=path_to_firebase_credentials
```

3. Run the bot:
```bash
python main.py
```

## Dependencies
- discord.py==2.3.2
- python-dotenv==1.0.0
- firebase_admin==6.2.0
- apscheduler==3.10.4
- PyPDF2==3.0.1
- pytesseract==0.3.10
- Pillow==10.1.0
- pdf2image==1.16.3
- loguru==0.7.2
- pytz==2024.1

## Best Practices

### Task Management
- Use clear and descriptive task names
- Set realistic deadlines
- Update task status regularly
- Use task categories for better organization
- Review task statistics periodically

### DSM Participation
- Update tasks before the deadline
- Use the ✅ reaction to mark completion
- Check task statistics regularly
- Participate in task discussions
- Follow the configured timezone

### Thread Management
- Keep discussions relevant to tasks
- Use threads for task-specific discussions
- Archive old threads when no longer needed
- Monitor thread activity and engagement

## Recent Updates
- Added timezone support for DSM operations
- Improved task statistics visualization
- Enhanced participant tracking
- Added manual DSM triggering with previous session finalization
- Improved thread management and archiving

## Future Plans
- Enhanced task analytics and reporting
- Improved thread management features
- Advanced participant tracking
- Better statistics visualization
- Integration with external task management tools

## Configuration

### Timezone Configuration
The bot uses the IANA Time Zone Database format for timezone configuration. This ensures accurate time handling across different regions and daylight saving time changes.

To set your server's timezone, use the `/set_config timezone` command with a valid timezone name. For example:
```
/set_config timezone:Asia/Manila
```

Common timezone formats:
- `Asia/Manila` (Philippines)
- `UTC` (Universal Coordinated Time)
- `America/New_York`
- `Europe/London`
- `Asia/Tokyo`
- `Australia/Sydney`

For a complete list of valid timezone names, visit: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

Common mistakes to avoid:
- Don't use abbreviations like "PHT" or "GMT+8"
- Don't use offsets like "UTC+8"
- Don't use spaces in the timezone name
- Use forward slashes (/) not backslashes

### Other Configuration Options
// ... existing code ...
