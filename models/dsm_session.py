"""DSM Session model for the stand-up bot."""
from datetime import datetime
from typing import Dict, Any, List

class DSMSession:
    """Model for representing DSM sessions."""
    
    def __init__(self, 
                 guild_id: int,
                 thread_id: int,
                 is_manual: bool,
                 created_at: str = None,
                 completed_tasks: int = 0,
                 new_tasks: int = 0,
                 participants: List[int] = None):
        """Initialize a new DSM session.
        
        Args:
            guild_id: The Discord guild ID
            thread_id: The Discord thread ID
            is_manual: Whether the DSM was manually triggered
            created_at: When the DSM was created (default: current time)
            completed_tasks: Number of tasks completed since last DSM
            new_tasks: Number of new tasks added
            participants: List of user IDs who participated
        """
        self.guild_id = guild_id
        self.thread_id = thread_id
        self.is_manual = is_manual
        self.created_at = created_at or datetime.now().isoformat()
        self.completed_tasks = completed_tasks
        self.new_tasks = new_tasks
        self.participants = participants or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert the DSM session to a dictionary for storage."""
        return {
            'guild_id': self.guild_id,
            'thread_id': self.thread_id,
            'is_manual': self.is_manual,
            'created_at': self.created_at,
            'completed_tasks': self.completed_tasks,
            'new_tasks': self.new_tasks,
            'participants': self.participants
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DSMSession':
        """Create a DSM session instance from a dictionary."""
        return cls(
            guild_id=data['guild_id'],
            thread_id=data['thread_id'],
            is_manual=data['is_manual'],
            created_at=data.get('created_at'),
            completed_tasks=data.get('completed_tasks', 0),
            new_tasks=data.get('new_tasks', 0),
            participants=data.get('participants', [])
        ) 