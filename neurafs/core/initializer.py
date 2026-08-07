"""NeuraFS Zero-Touch System Initializer Module."""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

from neurafs.core.storage import StorageManager
from neurafs.core.preflight import PreFlightChecker
from neurafs.vfs.service_manager import VFSServiceManager


class NeuraFSInitializer:
    """Handles zero-touch setup of physical storage roots and global system configurations."""

    @classmethod
    def initialize_system(cls, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """Initializes NeuraFS storage directory and performs pre-flight environmental diagnostics."""
        # 1. Run Pre-Flight Environmental Diagnostics
        diagnostics = PreFlightChecker.run_diagnostics()

        # 2. Resolve storage path (~/.neurafs/storage or custom path)
        if custom_path:
            target_path = Path(custom_path).resolve()
        else:
            target_path = Path.home() / ".neurafs" / "storage"

        # 3. Ensure physical directory structure exists
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "documents").mkdir(exist_ok=True)
        (target_path / "media").mkdir(exist_ok=True)
        (target_path / ".temp").mkdir(exist_ok=True)

        # 4. Register global storage path in ~/.neurafs/config.json
        registered_path = StorageManager.set_path(str(target_path))
        
        # 5. Auto-mount VFS partition only if driver is installed AND not already mounted
        vfs_mounted = False
        if diagnostics["vfs_driver"]["installed"]:
            if not VFSServiceManager.is_mounted():
                VFSServiceManager.mount(
                    storage_path=registered_path,
                    enable_samba=diagnostics["samba"]["available"]
                )
                vfs_mounted = True
            else:
                print("\n[NeuraFS Init] Active VFS virtual partition already detected. Skipping new mount.")
                vfs_mounted = True

        return {
            "status": "success",
            "storage_path": registered_path,
            "config_file": str(Path.home() / ".neurafs" / "config.json"),
            "subfolders": ["documents", "media", ".temp"],
            "vfs_mounted": vfs_mounted,
            "diagnostics": diagnostics
        }