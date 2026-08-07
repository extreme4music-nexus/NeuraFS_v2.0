"""NeuraFS Zero-Touch System Initializer & Dependency Guard Module."""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from neurafs.core.storage import StorageManager
from neurafs.core.preflight import PreFlightChecker


class NeuraFSInitializer:
    """Handles environmental pre-flight checks, dependency management, and storage setup."""

    @classmethod
    def initialize_system(cls, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """Runs diagnostics, checks/installs missing software dependencies, and sets up directories."""
        print("\n🔍 --- Running Pre-Flight Environmental Diagnostics ---")
        diagnostics = PreFlightChecker.run_diagnostics()

        # 1. Dependency Guard Check
        missing_deps = cls._check_and_prompt_dependencies(diagnostics)
        if missing_deps:
            print("\n❌ Initialization aborted: Missing required system dependencies.")
            print("👉 Please install the required software above and rerun 'neurafs init'.\n")
            sys.exit(1)

        # 2. Resolve storage path
        if custom_path:
            target_path = Path(custom_path).resolve()
        else:
            target_path = Path.home() / ".neurafs" / "storage"

        # 3. Create physical folder structure
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "documents").mkdir(exist_ok=True)
        (target_path / "media").mkdir(exist_ok=True)
        (target_path / ".temp").mkdir(exist_ok=True)

        # 4. Register path in config.json
        registered_path = StorageManager.set_path(str(target_path))

        print("\n✅ Environment fully verified and initialized successfully!")
        print("👉 You can now launch NeuraFS services using command: neurafs start\n")

        return {
            "status": "success",
            "storage_path": registered_path,
            "config_file": str(Path.home() / ".neurafs" / "config.json"),
            "subfolders": ["documents", "media", ".temp"],
            "diagnostics": diagnostics
        }

    @classmethod
    def _check_and_prompt_dependencies(cls, diagnostics: Dict[str, Any]) -> bool:
        """Prompts user to auto-install missing packages or gives manual installation steps."""
        has_missing = False

        # Check VFS Drivers
        if not diagnostics["vfs_driver"]["installed"]:
            has_missing = True
            print("\n⚠️  [MISSING DEPENDENCY] Virtual File System Driver (WinFSP / FUSE) is not detected.")
            
            if sys.platform == "win32":
                print("   NeuraFS requires WinFSP driver to mount virtual drives on Windows.")
                user_input = input("   Would you like NeuraFS to attempt auto-installation via Winget? [y/N]: ").strip().lower()
                if user_input == 'y':
                    if cls._run_install_cmd(["winget", "install", "WinFsp.WinFsp", "--accept-source-agreements", "--accept-package-agreements"]):
                        has_missing = False
                        print("   ✅ WinFSP driver installed successfully!")
                    else:
                        print("   ❌ Auto-installation failed. Download manually from: https://winfsp.dev/")
                else:
                    print("   👉 Manual Install: Download WinFSP installer from https://winfsp.dev/")
            else:
                print("   👉 Manual Install: Run 'sudo apt install fuse3' (Debian/Ubuntu) or 'sudo dnf install fuse' (Fedora)")

        # Check FFmpeg (Used in DSP Engine)
        if not cls._is_tool_available("ffmpeg"):
            has_missing = True
            print("\n⚠️  [MISSING DEPENDENCY] FFmpeg audio processor is not installed or not in PATH.")
            if sys.platform == "win32":
                user_input = input("   Would you like NeuraFS to attempt installing FFmpeg via Winget? [y/N]: ").strip().lower()
                if user_input == 'y':
                    if cls._run_install_cmd(["winget", "install", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"]):
                        has_missing = False
                        print("   ✅ FFmpeg installed successfully!")
                    else:
                        print("   ❌ Auto-installation failed. Download manually from: https://ffmpeg.org/")
                else:
                    print("   👉 Manual Install: Run 'winget install Gyan.FFmpeg' or download from https://ffmpeg.org/")

        return has_missing

    @classmethod
    def _is_tool_available(cls, name: str) -> bool:
        """Checks if a command-line tool is executable in current PATH."""
        from shutil import which
        return which(name) is not None

    @classmethod
    def _run_install_cmd(cls, cmd_list: list) -> bool:
        """Executes installation command."""
        try:
            res = subprocess.run(cmd_list, check=True)
            return res.returncode == 0
        except Exception:
            return False