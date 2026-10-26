"""
Centralized in-memory ring-buffer logging service for terminal dashboard and auditing.
"""

from collections import deque
from datetime import datetime, timezone
from typing import List, Dict, Any
import logging

logger = logging.getLogger("LoggingService")


class RingBufferLogHandler(logging.Handler):
    """Stores the last N logs in memory for fast UI inspection."""
    def __init__(self, capacity: int = 200):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record)
            }
            self.buffer.append(log_entry)
        except Exception:
            self.handleError(record)

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.buffer)[-limit:]


# Create singleton log handler and attach to root logger
ring_buffer_handler = RingBufferLogHandler(capacity=300)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%H:%M:%S")
ring_buffer_handler.setFormatter(formatter)
logging.getLogger().addHandler(ring_buffer_handler)
logging.getLogger().setLevel(logging.INFO)
