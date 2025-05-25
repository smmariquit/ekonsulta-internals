"""DSM Session model for the stand-up bot."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class DSMSession:
    """DSM session data class."""
    guild_id: int
    channel_id: int
    created_at: datetime
    is_manual: bool = False
    completed_tasks: int = 0
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert session to dictionary."""
        return {
            'guild_id': self.guild_id,
            'channel_id': self.channel_id,
            'created_at': self.created_at.isoformat(),
            'is_manual': self.is_manual,
            'completed_tasks': self.completed_tasks,
            'session_id': self.session_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DSMSession':
        """Create session from dictionary."""
        return cls(
            guild_id=data['guild_id'],
            channel_id=data['channel_id'],
            created_at=datetime.fromisoformat(data['created_at']),
            is_manual=data.get('is_manual', False),
            completed_tasks=data.get('completed_tasks', 0),
            session_id=data.get('session_id')
        ) 