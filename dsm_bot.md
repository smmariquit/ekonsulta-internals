# 🤖 DSM Bot Rules & Structure

> **Note for Cursor**: This document serves as a comprehensive guide to help you understand the DSM (Daily Standup Meeting) bot's codebase. It outlines the project structure, workflows, and implementation details to assist you in providing better code suggestions and modifications. Use this as a reference when working with the codebase.

## �� Project Structure
```
internal-automations/
├── cogs/
│   ├── __init__.py
│   └── dsm.py           # Main DSM cog implementation
├── models/
│   ├── __init__.py
│   ├── task.py          # Task model definition
│   └── dsm_session.py   # DSM session model
├── services/
│   ├── __init__.py
│   └── firebase_service.py  # Firebase integration
├── utils/
│   └── logger.py        # Logging utilities
├── config/
│   └── default_config.py    # Default configuration
├── bot.py               # Main bot file
└── requirements.txt     # Dependencies
```

## 🔄 Core Workflows

### 1. Task Management
- Tasks are stored in Firebase with unique IDs
- Each task has: description, status, remarks, timestamps
- Tasks are associated with users
- Tasks can be marked as done with completion timestamps
- Long task lists are split into multiple embeds to handle Discord's 1024 character limit
  - Completed tasks are split into multiple embeds if needed
  - Pending tasks are split into multiple embeds if needed
  - Message IDs are stored in arrays in Firebase
  - Latest tasks always appear in the first embed of each type

### 2. DSM Sessions
- Sessions are created automatically or manually
- Each session has:
  - Guild ID
  - Thread ID
  - Manual/Automatic flag
  - Task completion metrics
  - Participant tracking

### 3. User Interaction
- Users can:
  - Add tasks
  - Mark tasks as done
  - Add remarks
  - View their tasks
- Admins can:
  - Configure settings
  - Trigger manual DSMs
  - Manage other admins
  - Generate reports

## ⚙️ Configuration Rules

### 1. DSM Timing
- Configurable hour and minute
- Deadline hours setting
- Thread auto-archive duration
- Skip dates functionality

### 2. Access Control
- Admin-only commands require permissions
- User commands are available to all
- Firebase security rules apply

### 3. Task Management
- Unique task IDs are generated
- Tasks can have remarks
- Completion timestamps are tracked
- Task history is maintained

## 🔄 State Management

### 1. Firebase Collections
- `users`: User information and activity
- `tasks`: Task data and status
- `dsm_sessions`: DSM meeting records
- `config`: Guild-specific settings
- `dsm_messages`: Message IDs stored as arrays for split embeds
  ```json
  {
    "guild_id": {
      "user_id": {
        "completed_messages": [message_id1, message_id2, ...],
        "pending_messages": [message_id1, message_id2, ...],
        "last_updated": "timestamp"
      }
    }
  }
  ```

### 2. In-Memory State
- `user_tasks`: Current task state
- `message_ids`: Discord message references
- `active_sessions`: Current DSM sessions

## 🎯 Command Structure

### 1. User Commands
```python
@app_commands.command()
async def command_name(self, interaction: discord.Interaction, ...):
    # Command implementation
```

### 2. Admin Commands
```python
@app_commands.command()
@app_commands.default_permissions(administrator=True)
async def admin_command(self, interaction: discord.Interaction, ...):
    # Admin command implementation
```

## 🔄 Event Handlers

### 1. Scheduled Events
```python
@tasks.loop(hours=24)
async def daily_standup(self):
    # DSM creation logic
```

### 2. Discord Events
```python
@commands.Cog.listener()
async def on_ready(self):
    # Bot startup logic
```

## 📊 Data Models

### 1. Task Model
```python
class Task:
    def __init__(self, description, status="todo", remarks=None, task_id=None):
        self.description = description
        self.status = status
        self.remarks = remarks
        self.task_id = task_id
        self.created_at = datetime.now().isoformat()
```

### 2. DSM Session Model
```python
class DSMSession:
    def __init__(self, guild_id, thread_id, is_manual, ...):
        self.guild_id = guild_id
        self.thread_id = thread_id
        self.is_manual = is_manual
        # ... other properties
```

## 🔒 Security Rules

### 1. Command Access
- User commands: Available to all
- Admin commands: Require administrator permission
- Configuration: Requires admin role

### 2. Data Access
- User data: Accessible to the user and admins
- Task data: Accessible to the task owner and admins
- Session data: Accessible to all participants

## 🎨 UI Components

### 1. Embeds
- Task lists (split into multiple embeds if needed)
  - Each embed has a maximum of 1024 characters
  - Tasks are split chronologically
  - Latest tasks appear in the first embed
  - Each embed shows which part of the list it contains (e.g., "Part 1/3")
- DSM session information
  - Full date format (e.g., "Daily Standup Meeting for March 21, 2024")
  - Task statistics without emojis
  - Participant tracking (updated and pending)
  - Timeline with full date format
- User profiles
- Reports

### 2. Views
- Task management interface
- Admin controls
- Configuration panels

## 📝 Logging Rules

### 1. Log Levels
- INFO: Normal operations
- WARNING: Non-critical issues
- ERROR: Critical issues
- DEBUG: Detailed debugging
  - Message splitting operations
  - Embed character counts
  - Message ID array updates
  - Participant tracking updates
  - Statistics message updates

### 2. Log Categories
- Task operations
- DSM sessions
- User actions
- System events
- Message splitting
- Embed management
- Participant tracking
- Statistics updates

## 🔄 Error Handling

### 1. Command Errors
- User-friendly error messages
- Logging of errors
- Graceful fallbacks

### 2. System Errors
- Firebase connection issues
- Discord API errors
- Configuration problems
- Message tracking issues
- Participant tracking issues

## 🎯 Best Practices

### 1. Code Organization
- Modular design
- Clear separation of concerns
- Consistent naming conventions
- Comprehensive documentation

### 2. Performance
- Efficient database queries
- Optimized task updates
- Proper resource cleanup
- Efficient participant tracking
- Optimized statistics updates

### 3. User Experience
- Clear command feedback
- Intuitive interfaces
- Helpful error messages
- Responsive design
- Clear participant status
- Real-time statistics updates

## 🔄 Recent Updates

### Thread Management Improvements
- Consolidated thread finding logic into `get_current_dsm_thread`
- Improved thread tracking in Firebase config
- Added verification of message IDs on bot startup
- Enhanced thread selection to prioritize config-stored threads
- Added full date format to thread names and messages
- Added automatic finalization of previous DSM when triggering a new one
- Added explicit archiving of previous thread when creating a new DSM

### Message Management
- Improved message ID storage in guild config
- Added message verification on task updates
- Enhanced error handling for message operations
- Added support for multiple message embeds per user
- Added statistics message tracking and updates
- Added clearing of old message IDs when finalizing a DSM

### Task Management
- Added task statistics updates on task changes
- Improved task ID generation system
- Enhanced task display formatting
- Added support for task remarks
- Added participant tracking for task updates
- Added clearing of participant tracking when finalizing a DSM

### Configuration
- Moved all configuration to guild-specific subcollections
- Added support for skipping DSM dates
- Enhanced admin management system
- Improved configuration validation
- Added participant tracking configuration
- Added statistics message tracking
- Added automatic cleanup of old DSM data when creating a new one

### Future Plans
- Implement Unix timestamps for better timezone support
- Complete no-thread mode implementation
- Enhanced participant tracking features
- Improved statistics visualization
- Add confirmation prompt before finalizing previous DSM

---

*This document serves as a guide for understanding the DSM bot's structure and rules. It should be updated as the bot evolves.*
