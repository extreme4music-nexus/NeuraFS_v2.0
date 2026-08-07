"""NeuraFS Pre-Flight Environmental Diagnostic Module."""

import sys
import shutil
import ctypes
import subprocess
from pathlib import Path
from typing import Dict, Any


class PreFlightChecker:
    """Scans host system environment for OS type, kernel drivers (WinFSP/FUSE), and Samba accessibility."""

    @classmethod
    def check_winfsp(cls) -> Dict[str, Any]:
        """Checks for native WinFSP installation on Windows."""
        candidates = [
            "winfsp-x64.dll",
            r"C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll",
            r"C:\Program Files\WinFsp\bin\winfsp-x64.dll",
        ]
        installed = False
        loaded_path = None

        for path in candidates:
            try:
                _ = ctypes.CDLL(path)
                installed = True
                loaded_path = path
                break
            except OSError:
                continue

        return {
            "installed": installed,
            "path": loaded_path,
            "guide": (
                "Download and install WinFsp runtime executable (WinFsp.msi) from:\n"
                "   https://winfsp.dev/\n"
                "   (No reboot required after installation)"
            ) if not installed else "WinFSP Native DLL loaded successfully."
        }

    @classmethod
    def check_fuse(cls) -> Dict[str, Any]:
        """Checks for FUSE and fusepy availability on Linux."""
        fuse_bin = shutil.which("fusermount") or shutil.which("fusermount3")
        fusepy_available = False

        try:
            import fuse  # noqa: F401
            fusepy_available = True
        except ImportError:
            pass

        installed = bool(fuse_bin and fusepy_available)
        
        guide_msgs = []
        if not fuse_bin:
            guide_msgs.append("Install FUSE runtime via package manager: 'sudo apt install fuse3'")
        if not fusepy_available:
            guide_msgs.append("Install python bindings: 'pip install fusepy'")

        return {
            "installed": installed,
            "path": fuse_bin,
            "fusepy": fusepy_available,
            "guide": "\n   ".join(guide_msgs) if not installed else "FUSE kernel interface ready."
        }

    @classmethod
    def check_samba(cls, os_type: str) -> Dict[str, Any]:
        """Deep checks Samba (smbd) binary and daemon state on Linux, or provides Windows SMB instructions."""
        if os_type == "linux":
            smb_bin = shutil.which("smbd")
            if not smb_bin:
                return {
                    "available": False,
                    "status_str": "NOT INSTALLED ❌",
                    "guide": "Install Samba server via: 'sudo apt update && sudo apt install samba'"
                }

            # Check if smbd daemon service is currently running
            is_active = False
            try:
                res = subprocess.run(["systemctl", "is-active", "smbd"], capture_output=True, text=True, check=False)
                if res.stdout.strip() == "active":
                    is_active = True
            except Exception:
                pass

            if not is_active:
                return {
                    "available": False,
                    "status_str": "INSTALLED BUT INACTIVE ⚠️",
                    "guide": "Start & enable Samba daemon via: 'sudo systemctl enable --now smbd'"
                }

            return {
                "available": True,
                "status_str": "READY & ACTIVE ✅",
                "guide": "Samba background service is running natively."
            }
        else:
            # Windows SMB Environment Setup Guidance
            return {
                "available": True,
                "status_str": "NATIVE WINDOWS SMB READY ✅",
                "guide_gui": "Right-click Virtual Drive (X:) -> Properties -> Sharing -> Advanced Sharing -> Check 'Share this folder'",
                "guide_cli": "Or execute in Admin PowerShell/CMD: net share NeuraFS_Drive=X:\\ /GRANT:Everyone,FULL"
            }

    @classmethod
    def run_diagnostics(cls) -> Dict[str, Any]:
        """Runs complete pre-flight check across OS, Drivers, and Samba capabilities."""
        os_type = "windows" if sys.platform == "win32" else ("linux" if sys.platform.startswith("linux") else sys.platform)

        if os_type == "windows":
            vfs_report = cls.check_winfsp()
        elif os_type == "linux":
            vfs_report = cls.check_fuse()
        else:
            vfs_report = {"installed": False, "guide": f"Unsupported platform: {os_type}"}

        samba_report = cls.check_samba(os_type)

        return {
            "os": os_type.upper(),
            "vfs_driver": vfs_report,
            "samba": samba_report,
            "system_ready": vfs_report["installed"]
        }