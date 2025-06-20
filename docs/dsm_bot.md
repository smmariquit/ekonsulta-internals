# DSM Bot Implementation Notes

## Important Implementation Details

### Message IDs
- Discord message IDs are NOT incremental or sequential
- Each message ID is a unique snowflake that contains timestamp and other metadata
- Never assume message IDs are sequential (e.g., msg.id + 1)
- Always search for messages by their content or other unique identifiers

### Thread Management
- Each DSM session creates a new thread with format: "DAILY STANDUP MEETING - {date}"
- Thread IDs are unique and should be stored for reference
- Messages within threads need to be tracked separately from the thread ID

### Task Management
- Tasks are stored with unique IDs generated using alphanumeric characters
- Each user's tasks are stored separately in Firebase
- Tasks can be in two states: pending or completed
- Each task can have remarks added to it

### Message Storage
- Each user has two messages in the DSM thread:
  1. Completed Tasks message
  2. Pending Tasks message
- Message IDs are stored in Firebase for each user
- Message IDs are stored in a dictionary format:
  ```json
  {
    "completed_msg_id": "message_id_here",
    "pending_msg_id": "message_id_here"
  }
  ```

### DSM Lookback Feature
- **Purpose**: Include messages from a configurable time period before DSM in task collection
- **Default**: 2 hours before DSM time
- **Configuration**: Set via `dsm_lookback_hours` in bot configuration
- **Range**: 0-24 hours
- **Usage**: 
  - Messages sent within the lookback period are included in the current DSM's task collection
  - This allows for early task planning and updates before the official DSM time
  - Useful for teams that start planning their day before the scheduled DSM

#### Commands for Lookback Configuration
- `/configure dsm_lookback_hours:<hours>` - Set the lookback period (0-24 hours)
- `/show_lookback` - Display current lookback configuration and time windows

#### Implementation Details
- Lookback time is calculated as: `last_dsm_time - timedelta(hours=lookback_hours)`
- Affects `get_user_tasks()`, `update_todo_tasks_for_today()`, `update_todo_tasks_embed()`, and `create_dsm()` methods
- Messages outside the lookback window are ignored for task collection
- Logging includes lookback time calculations for debugging

## Common Issues and Solutions

### Message Finding
- Problem: Messages not being found in threads
- Solution: Search by message content and author instead of relying on message IDs
- Implementation: Use message history search with filters for bot author and embed titles

### Thread Context
- Problem: Wrong thread being used for updates
- Solution: Always verify current thread and update message IDs accordingly
- Implementation: Use get_current_dsm_thread() to find the correct thread

### Message Updates
- Problem: Messages not updating correctly
- Solution: Ensure both completed and pending messages are found and updated
- Implementation: Search for both message types independently and update together

### Lookback Configuration
- Problem: Tasks not being collected from expected time period
- Solution: Check lookback configuration with `/show_lookback` command
- Implementation: Verify `dsm_lookback_hours` setting and recalculate time windows 