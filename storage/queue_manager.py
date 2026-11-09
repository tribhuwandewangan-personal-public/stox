"""Queue manager stub - for backtesting, uses simple in-memory queue."""

import queue
from typing import Dict, Any, List, Optional


class ValkeyQueueManager:
    """Fallback queue manager using Python's queue module."""

    def __init__(self):
        self.queue = queue.Queue()
        self.tasks = {}

    def enqueue(self, symbol: str, task_data: Dict[str, Any]) -> str:
        """Add task to queue."""
        task_id = f"{symbol}_{len(self.tasks)}"
        self.tasks[task_id] = task_data
        self.queue.put(task_id)
        return task_id

    def dequeue(self) -> Optional[str]:
        """Get next task from queue."""
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def mark_complete(self, task_id: str) -> None:
        """Mark task as complete."""
        if task_id in self.tasks:
            self.tasks[task_id]["completed"] = True

    def get_status(self) -> Dict[str, int]:
        """Get queue status."""
        pending = self.queue.qsize()
        completed = sum(1 for t in self.tasks.values() if t.get("completed"))
        return {
            "pending_count": pending,
            "completed_count": completed,
            "in_progress_count": 0
        }
