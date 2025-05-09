"""Task model for the stand-up bot."""
from datetime import datetime
from typing import Dict, Any

class Task:
    """Task model for representing tasks in the standup system."""
    
    def __init__(self, description: str, status: str = "todo", remarks: str = None, task_id: str = None):
        """Initialize a new task.
        
        Args:
            description: The task description
            status: The task status (default: "todo")
            remarks: Any remarks about the task (default: None)
            task_id: A unique identifier for the task (default: None)
        """
        self.description = description
        self.status = status
        self.remarks = remarks
        self.task_id = task_id
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary for storage.
        
        Returns:
            dict: The task data as a dictionary
        """
        return {
            'description': self.description,
            'status': self.status,
            'remarks': self.remarks,
            'task_id': self.task_id,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create a task instance from a dictionary.
        
        Args:
            data: The task data as a dictionary
            
        Returns:
            Task: A new task instance
        """
        task = cls(
            description=data['description'],
            status=data.get('status', 'todo'),
            remarks=data.get('remarks'),
            task_id=data.get('task_id')
        )
        task.created_at = data.get('created_at', datetime.now().isoformat())
        return task 