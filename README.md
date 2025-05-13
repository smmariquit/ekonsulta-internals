# 🤖 Ekonsulta DSM Bot

> *"Because your daily standups deserve to be as smooth as your morning coffee"* ☕

## ✨ Features

### 🎯 Task Management
- **Add Tasks** ➕ - Create new tasks with unique IDs
- **Mark Tasks Done** ✅ - Track your progress
- **Add Remarks** 📝 - Add context and notes to your tasks
- **Task History** 📊 - View your task completion history

### 🌅 Daily Standup Meetings
- **Automated DSMs** 🤖 - Scheduled daily standup meetings
- **Manual DSMs** 🎮 - Trigger standups whenever needed
- **Task Tracking** 📈 - Monitor completed vs. pending tasks
- **Deadline Management** ⏰ - Set and track DSM deadlines
- **Thread Mode** 🧵 - Currently only thread mode is fully implemented (no-thread mode coming soon)
- **Timezone Support** 🌍 - Future plans to implement Unix timestamps for better timezone handling

### 👥 User Management
- **User Profiles** 👤 - Track user activity and participation
- **Admin Controls** 👑 - Manage bot administrators
- **Activity Tracking** 📱 - Monitor user engagement

### 🔧 Configuration
- **Customizable Settings** ⚙️ - Configure DSM timing and behavior
- **Skip Dates** 🏖️ - Schedule DSM-free days
- **Thread Management** 🧵 - Control thread archiving and naming

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Discord Bot Token
- Firebase Project with credentials

### Installation
1. Clone the repository:
```bash
git clone https://github.com/yourusername/ekonsulta-internals.git
cd ekonsulta-internals
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Add your Firebase credentials:
```bash
# Place your firebase-credentials.json in the project root
```

### Running the Bot
```bash
python bot.py
```

## 🎮 Commands

### User Commands
- `/dsm` - Open the DSM task management interface
- `/add <task>` - Add a new task
- `/done <task_id>` - Mark a task as complete
- `/remark <task_id> <remark>` - Add a remark to a task
- `/refresh_tasks` - Refresh your task view

### Admin Commands
- `/config` - Configure DSM settings
- `/simulate_dsm` - Manually trigger a DSM
- `/resend_dsm` - Resend the opening message
- `/skip_dsm <date>` - Skip DSM on a specific date
- `/unskip_dsm <date>` - Remove a date from skip list
- `/list_skipped_dsm` - View skipped DSM dates
- `/generate_report <days>` - Generate task report
- `/add_admin <user>` - Add a bot administrator
- `/remove_admin <user>` - Remove a bot administrator
- `/list_admins` - View bot administrators

## 📊 DSM Features

### Automatic DSMs
- Scheduled daily at configured time
- Creates dedicated threads with full date format (e.g., "Daily Standup Meeting for March 21, 2024")
- Tracks task completion and participant status
- Monitors participation with real-time updates
- Stores message IDs in Firebase for reliable updates
- Maintains lists of updated and pending participants

### Manual DSMs
- Triggered by administrators
- Same features as automatic DSMs
- Flexible timing

### Task Management
- Unique task IDs
- Status tracking
- Remark system
- Completion timestamps

## 🔒 Security

- Role-based access control
- Admin-only commands
- Secure Firebase integration
- Environment variable protection

## 🤝 Contributing

We welcome contributions! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with ❤️ for the Ekonsulta team
- Powered by Discord.py and Firebase
- Inspired by agile methodologies

---

*Made with ☕ and 🎵 by the Ekonsulta team*

## Task ID System

- 4-character alphanumeric codes (lowercase letters + numbers)
- Total possible combinations: 1,679,616 (36^4)
- Format examples: `a1b2`, `x7y9`, `1234`, `abcd`
- Automatic fallback system if ID collision occurs

## Discord Embed Limitations

Discord embeds have the following limitations:
1. Title: 256 characters
2. Description: 4096 characters
3. Field name: 256 characters
4. Field value: 1024 characters
5. Footer text: 2048 characters
6. Total embed size: 6000 characters
7. Maximum 25 fields per embed
8. Maximum 10 embeds per message

Due to these limitations, the bot:
- Separates completed and pending tasks into different embeds
- Groups tasks by date to stay within field limits
- Truncates long task descriptions if necessary
- Uses pagination for task selection menus (max 25 options)

## Task Display Format

Tasks are displayed in the following format:
```
HH:MM [`task_id`] Task description
   📝 **Remark:** Remark text (if any)
```

Completed tasks show completion time:
```
HH:MM [`task_id`] Task description (HH:MM)
```

Tasks are grouped by date and sorted by time within each group.

## Configuration

The bot can be configured using the `/config` command (Admin only):
- Standup hour and minute
- Thread name template
- Auto-archive duration
- Thread/Channel mode

# Internal Automations

This repository contains various automation tools and bots for internal use.

## Projects

### 1. DSM Bot (Daily Standup Meeting Bot)
A Discord bot that helps manage daily standup meetings by tracking tasks and their status.

#### Features
- Creates daily standup meeting threads
- Tracks pending and completed tasks
- Allows adding remarks to tasks
- Supports task completion marking
- Maintains task history

#### Implementation Notes
- Uses Firebase for data storage
- Implements Discord.py for bot functionality
- Handles both thread and message management
- Supports multiple users and their tasks

#### Important Considerations
- Discord message IDs are not sequential (see `docs/dsm_bot.md` for details)
- Each user has two messages in the DSM thread (completed and pending tasks)
- Thread context must be maintained for proper message updates
- Task IDs are unique and generated using alphanumeric characters

#### Recent Updates
- Fixed message finding logic to not rely on sequential IDs
- Improved thread context handling
- Enhanced error handling and logging
- Added support for task remarks
- Implemented proper message storage format

### 2. [Other Projects]
[Add other projects as they are developed]

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- Firebase account and credentials
- Discord bot token

### Installation
1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   - `DISCORD_TOKEN`: Your Discord bot token
   - `FIREBASE_CREDENTIALS`: Path to your Firebase credentials file

### Running the Bot
```bash
python main.py
```

## Documentation
- See `docs/dsm_bot.md` for detailed implementation notes
- Check individual project directories for specific documentation

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
[Add appropriate license information]

## ✨ Recent Updates

### 🎯 Task Management Improvements
- Enhanced task tracking with real-time statistics
- Improved task ID generation system
- Better task display formatting
- Added support for task remarks

### 🔄 Thread Management
- Consolidated thread finding logic
- Improved thread tracking in Firebase
- Added message verification on startup
- Enhanced thread selection system

### 📊 Message Handling
- Improved message ID storage
- Added support for multiple embeds
- Enhanced error handling
- Better message verification

### ⚙️ Configuration
- Moved to guild-specific subcollections
- Added DSM skip date support
- Enhanced admin management
- Improved configuration validation

