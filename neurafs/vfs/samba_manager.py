"""NeuraFS Samba Network VFS Manager Module.

Manages Samba configuration (/etc/samba/smb.conf), handles C-driver integration,
and controls smbd daemon lifecycle safely.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any


class SambaManager:
    """Intelligent manager for Samba network sharing and C VFS plugin registration."""

    SMB_CONF_PATH = Path("/etc/samba/smb.conf")
    SHARE_NAME = "NeuraFS_Share"

    @classmethod
    def is_available(cls) -> bool:
        """Checks if system is Linux and Samba (smbd) executable exists."""
        if sys.platform.startswith("linux"):
            return shutil.which("smbd") is not None
        return False

    @classmethod
    def is_share_active(cls) -> bool:
        """Checks if NeuraFS share block exists inside smb.conf."""
        if cls.SMB_CONF_PATH.exists():
            try:
                content = cls.SMB_CONF_PATH.read_text(encoding="utf-8")
                return f"[{cls.SHARE_NAME}]" in content
            except Exception:
                pass
        return False

    @classmethod
    def setup_share(cls, physical_storage_path: str) -> Dict[str, Any]:
        """Safely injects NeuraFS share configuration into smb.conf and reloads smbd."""
        if not cls.is_available():
            return {"status": "skipped", "reason": "Samba (smbd) not installed on host."}

        if not os.access(cls.SMB_CONF_PATH, os.W_OK):
            return {"status": "error", "reason": "Permission denied: Root/sudo required to write /etc/samba/smb.conf"}

        abs_storage = os.path.abspath(physical_storage_path)

        # Remove previous share block if exists to prevent duplicates
        cls.remove_share(reload_service=False)

        # Check if native C-plugin (.so) exists in system VFS folder
        has_c_plugin = cls._check_c_plugin_exists()
        vfs_directive = "   vfs objects = neurafs\n" if has_c_plugin else ""

        share_config = f"""
# --- NeuraFS Managed Share Start ---
[{cls.SHARE_NAME}]
   comment = NeuraFS Virtual Neural Media Storage
   path = {abs_storage}
   read only = no
   guest ok = yes
   browseable = yes
   create mask = 0777
   directory mask = 0777
{vfs_directive}# --- NeuraFS Managed Share End ---
"""

        try:
            with open(cls.SMB_CONF_PATH, "a", encoding="utf-8") as f:
                f.write(share_config)

            cls.reload_smbd()
            return {
                "status": "success",
                "share_name": cls.SHARE_NAME,
                "path": abs_storage,
                "c_plugin_active": has_c_plugin
            }
        except Exception as err:
            return {"status": "error", "reason": str(err)}

    @classmethod
    def remove_share(cls, reload_service: bool = True) -> bool:
        """Cleanly removes NeuraFS share block from smb.conf without touching other shares."""
        if not cls.SMB_CONF_PATH.exists() or not os.access(cls.SMB_CONF_PATH, os.W_OK):
            return False

        try:
            content = cls.SMB_CONF_PATH.read_text(encoding="utf-8")
            if f"[{cls.SHARE_NAME}]" not in content:
                return True

            lines = content.splitlines()
            new_lines = []
            skipping = False

            for line in lines:
                if "# --- NeuraFS Managed Share Start ---" in line or f"[{cls.SHARE_NAME}]" in line:
                    skipping = True
                    continue
                if skipping and "# --- NeuraFS Managed Share End ---" in line:
                    skipping = False
                    continue
                if not skipping:
                    new_lines.append(line)

            cls.SMB_CONF_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

            if reload_service:
                cls.reload_smbd()
            return True
        except Exception:
            return False

    @classmethod
    def reload_smbd(cls) -> None:
        """Reloads smbd service configuration cleanly."""
        try:
            subprocess.run(["systemctl", "reload", "smbd"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    @classmethod
    def _check_c_plugin_exists(self) -> bool:
        """Checks if compiled vfs_neurafs.so C-plugin is installed in Samba VFS modules path."""
        possible_paths = [
            Path("/usr/lib/x86_64-linux-gnu/samba/vfs/neurafs.so"),
            Path("/usr/lib64/samba/vfs/neurafs.so"),
            Path("/usr/lib/samba/vfs/neurafs.so"),
        ]
        return any(p.exists() for p in possible_paths)