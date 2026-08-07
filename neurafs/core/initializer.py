"""NeuraFS Zero-Touch System Initializer Module."""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from neurafs.core.storage import StorageManager


class NeuraFSInitializer:
    """Handles zero-touch setup of physical storage roots and global system configurations."""

    @classmethod
    def initialize_system(cls, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """Initializes NeuraFS storage directory and global configuration file."""
        # 1. Resolve storage path (~/.neurafs/storage or custom path)
        if custom_path:
            target_path = Path(custom_path).resolve()
        else:
            target_path = Path.home() / ".neurafs" / "storage"

        # 2. Ensure physical directory structure exists
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "documents").mkdir(exist_ok=True)
        (target_path / "media").mkdir(exist_ok=True)
        (target_path / ".temp").mkdir(exist_ok=True)

        # 3. Register global storage path in ~/.neurafs/config.json
        registered_path = StorageManager.set_path(str(target_path))

        return {
            "status": "success",
            "storage_path": registered_path,
            "config_file": str(Path.home() / ".neurafs" / "config.json"),
            "subfolders": ["documents", "media", ".temp"],
        }