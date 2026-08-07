"""NeuraFS Universal Storage Location & Lifecycle Manager."""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any

CONFIG_DIR = Path.home() / ".neurafs"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_STORAGE = Path(__file__).resolve().parents[2] / "storage"


class StorageManager:
    """Universal Storage Manager for NeuraFS (API, Web, FUSE/WinFSP, Samba, Benchmarks)."""

    @classmethod
    def _ensure_config_dir(cls) -> None:
        """Ensures that the ~/.neurafs directory exists."""
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_path(cls) -> str:
        """Returns the configured absolute storage root path."""
        cls._ensure_config_dir()
        if not CONFIG_FILE.exists():
            cls.set_path(str(DEFAULT_STORAGE))

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                path = data.get("storage_path", str(DEFAULT_STORAGE))
                cls.init_structure(path)
                return os.path.abspath(path)
        except Exception:
            return os.path.abspath(str(DEFAULT_STORAGE))

    @classmethod
    def init_structure(cls, target_path: str) -> None:
        """Ensures documents, media, and .temp directories exist safely."""
        try:
            os.makedirs(os.path.join(target_path, "documents"), exist_ok=True)
            os.makedirs(os.path.join(target_path, "media"), exist_ok=True)
            os.makedirs(os.path.join(target_path, ".temp"), exist_ok=True)
        except Exception:
            # Handles read-only VFS drives and pending Windows mount points gracefully
            pass

    @classmethod
    def set_path(cls, new_path: str) -> str:
        """Sets a new global storage path."""
        abs_path = os.path.abspath(new_path)
        cls.init_structure(abs_path)
        
        cls._ensure_config_dir()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"storage_path": abs_path}, f, indent=4)
        return abs_path

    @classmethod
    def check(cls) -> Dict[str, Any]:
        """Checks storage integrity, permissions, and disk space."""
        path = cls.get_path()
        exists = os.path.exists(path)
        
        stats = {
            "path": path,
            "exists": exists,
            "writable": os.access(path, os.W_OK) if exists else False,
            "readable": os.access(path, os.R_OK) if exists else False,
            "subfolders": {
                "documents": os.path.exists(os.path.join(path, "documents")),
                "media": os.path.exists(os.path.join(path, "media")),
                ".temp": os.path.exists(os.path.join(path, ".temp")),
            },
            "free_space_gb": 0.0
        }

        if exists:
            try:
                usage = shutil.disk_usage(path)
                stats["free_space_gb"] = round(usage.free / (1024 ** 3), 2)
            except Exception:
                pass

        return stats

    @classmethod
    def remove_config(cls) -> None:
        """Resets storage configuration back to default project directory."""
        if CONFIG_FILE.exists():
            os.remove(CONFIG_FILE)
        cls.set_path(str(DEFAULT_STORAGE))

    @classmethod
    def move(cls, current_path: str, new_path: str) -> bool:
        """Moves data from current storage to a new location and updates configuration."""
        src = os.path.abspath(current_path)
        dst = os.path.abspath(new_path)

        if not os.path.exists(src):
            raise FileNotFoundError(f"Source storage path does not exist: {src}")

        os.makedirs(dst, exist_ok=True)

        for item in os.listdir(src):
            s_item = os.path.join(src, item)
            d_item = os.path.join(dst, item)
            if os.path.isdir(s_item):
                if os.path.exists(d_item):
                    shutil.copytree(s_item, d_item, dirs_exist_ok=True)
                    shutil.rmtree(s_item)
                else:
                    shutil.move(s_item, d_item)
            else:
                shutil.move(s_item, d_item)

        cls.set_path(dst)
        return True