"""NeuraFS User Activity Logger Module."""

import time
from pathlib import Path
from typing import List

LOG_FILE = Path.home() / ".neurafs" / "activity.log"


class ActivityLogger:
    """Logs user-relevant file lifecycle events in a clean, readable format."""

    @classmethod
    def log(cls, event_type: str, message: str) -> None:
        """Appends a new event entry to activity.log."""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{event_type.upper()}] {message}\n"
        
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass

    @classmethod
    def get_recent_logs(cls, lines: int = 20) -> List[str]:
        """Returns the most recent user activity log entries."""
        if not LOG_FILE.exists():
            return ["No activity logged yet."]
        
        try:
            content = LOG_FILE.read_text(encoding="utf-8").splitlines()
            return content[-lines:] if content else ["Log file is empty."]
        except Exception as err:
            return [f"Error reading log file: {err}"]