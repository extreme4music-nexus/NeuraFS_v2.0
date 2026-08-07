"""NeuraFS OS-Aware VFS Service Manager and Persistence Engine."""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from neurafs.core.storage import StorageManager


def get_vfs_state_file() -> Path:
    """Returns path to the active VFS state file."""
    run_dir = Path.home() / ".neurafs" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "vfs_state.json"


def load_vfs_state() -> Dict[str, Any]:
    """Loads active VFS state from disk."""
    state_file = get_vfs_state_file()
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_vfs_state(state: Dict[str, Any]) -> None:
    """Saves active VFS state to disk."""
    state_file = get_vfs_state_file()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


def clear_vfs_state() -> None:
    """Clears VFS state file."""
    state_file = get_vfs_state_file()
    if state_file.exists():
        try:
            os.remove(state_file)
        except OSError:
            pass


def detect_os() -> str:
    """Detects host operating system."""
    if sys.platform == "win32":
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def find_free_windows_drive() -> str:
    """Scans Windows logical drives and returns the first available drive letter from Z: down to D:."""
    import string
    from ctypes import windll

    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in reversed(string.ascii_uppercase[3:26]):  # D: to Z:
        if not (bitmask & (1 << (ord(letter) - ord("A")))):
            return f"{letter}:"
    return "Z:"


class VFSServiceManager:
    """Manages VFS driver lifecycle, OS persistence services, and StorageManager integration."""
    
    @classmethod
    def is_mounted(cls) -> bool:
        """Checks if a NeuraFS VFS virtual partition is currently mounted and accessible."""
        state = load_vfs_state()
        if state and state.get("status") == "mounted":
            target = state.get("virtual_target")
            if target and os.path.exists(target):
                return True
        return False
    
    @classmethod
    def mount(
        cls,
        storage_path: Optional[str] = None,
        target: Optional[str] = None,
        enable_samba: bool = False,
    ) -> None:
        """Mounts physical storage directory to an OS virtual drive/folder with startup persistence."""
        os_type = detect_os()

        raw_path = storage_path or target
        physical_storage = (
            os.path.abspath(raw_path)
            if raw_path
            else StorageManager.get_path()
        )
        if not os.path.exists(physical_storage):
            os.makedirs(physical_storage, exist_ok=True)

        print(f"\n[NeuraFS VFS] Detected OS           : {os_type.upper()}")
        print(f"[NeuraFS VFS] Physical Storage Path : {physical_storage}")

        if os_type == "windows":
            target_mount = find_free_windows_drive()
            print(f"[NeuraFS VFS] Selected Free Drive  : {target_mount}")

            cls._mount_windows(physical_storage, target_mount)
            cls._register_windows_autostart(physical_storage, target_mount)

            # Wait up to 3 seconds for Windows Kernel to make the drive visible
            for _ in range(10):
                if os.path.exists(target_mount):
                    break
                time.sleep(0.3)

        elif os_type == "linux":
            target_mount = str(Path.home() / "NeuraFS_Drive")
            os.makedirs(target_mount, exist_ok=True)
            print(f"[NeuraFS VFS] Selected Mount Point : {target_mount}")

            cls._mount_linux(physical_storage, target_mount)
            cls._register_linux_autostart(physical_storage, target_mount)

        else:
            raise RuntimeError(f"Unsupported operating system: {os_type}")

        if enable_samba and os_type == "linux":
            cls._enable_samba_share(physical_storage)

        # Redirect global StorageManager path to virtual partition
        StorageManager.set_path(target_mount)
        print(f"[NeuraFS VFS] Global Storage path redirected -> '{target_mount}'")

        save_vfs_state({
            "status": "mounted",
            "os": os_type,
            "physical_storage": physical_storage,
            "virtual_target": target_mount,
            "samba_enabled": enable_samba,
            "mode": "read_write"
        })

        print("[NeuraFS VFS] Status: MOUNTED (RW) & PERSISTED ACROSS REBOOTS ✅\n")

    @classmethod
    def umount(cls, target: Optional[str] = None) -> None:
        """Unmounts active virtual partition, removes boot startup services, and restores default storage."""
        state = load_vfs_state()
        os_type = state.get("os") or detect_os()
        target_mount = target or state.get("virtual_target")

        if not target_mount:
            target_mount = "Z:" if os_type == "windows" else str(Path.home() / "NeuraFS_Drive")

        print(f"\n[NeuraFS VFS] Unmounting Target: {target_mount}")

        if os_type == "windows":
            cls._remove_windows_autostart()
            cls._umount_windows(target_mount)
        elif os_type == "linux":
            cls._remove_linux_autostart()
            cls._umount_linux(target_mount)

        default_storage = os.path.join(os.path.expanduser("~"), ".neurafs", "storage")
        StorageManager.set_path(default_storage)
        print(f"[NeuraFS VFS] Global Storage path restored -> '{default_storage}'")

        clear_vfs_state()
        print(f"[NeuraFS VFS] Status: UNMOUNTED & PERSISTENCE REMOVED ✅\n")

    @classmethod
    def status(cls) -> None:
        """Displays status of the VFS virtual partition and persistence engine."""
        state = load_vfs_state()
        os_type = detect_os()

        print("\n===================================================")
        print("          NeuraFS Virtual File System Status       ")
        print("===================================================")
        print(f" • Host Operating System : {os_type.upper()}")
        print(f" • Active Driver Engine  : {'WinFSP / Windows VFS' if os_type == 'windows' else 'FUSE Kernel Module'}")

        if state and state.get("status") == "mounted":
            print(f" • Mount Status          : MOUNTED ✅ (Read/Write)")
            print(f" • Virtual Partition     : {state.get('virtual_target')}")
            print(f" • Physical Storage      : {state.get('physical_storage')}")
            print(f" • Boot Autostart        : ACTIVE (Persisted via {'Task Scheduler' if os_type == 'windows' else 'systemd'})")
            print(f" • Samba VFS Share       : {'ENABLED ✅' if state.get('samba_enabled') else 'DISABLED'}")
        else:
            print(f" • Mount Status          : UNMOUNTED ❌")
            print(f" • Current Storage Path  : {StorageManager.get_path()}")
        print("===================================================\n")

    # --- Windows Methods ---

    @staticmethod
    def _mount_windows(physical_storage: str, drive_letter: str) -> None:
        """Spawns background Python daemon process to mount drive permanently."""
        python_exe = sys.executable
        driver_script = os.path.join(os.path.dirname(__file__), "drivers", "windows_winfsp.py")

        # Launch detached background process so it survives terminal exit
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [python_exe, driver_script, physical_storage, drive_letter],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )

    @staticmethod
    def _umount_windows(drive_letter: str) -> None:
        cmd = ["subst", drive_letter, "/d"] if len(drive_letter) == 2 else ["net", "use", drive_letter, "/delete", "/y"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    @staticmethod
    def _mount_linux(physical_storage: str, mount_point: str) -> None:
        python_exe = sys.executable
        driver_script = os.path.join(os.path.dirname(__file__), "drivers", "linux_fuse.py")
        subprocess.Popen([python_exe, driver_script, physical_storage, mount_point])

    @staticmethod
    def _umount_linux(mount_point: str) -> None:
        subprocess.run(["fusermount", "-u", mount_point], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    @staticmethod
    def _register_windows_autostart(physical_storage: str, drive_letter: str) -> None:
        """Smart cleanup of old tasks before registering a clean, single Task Scheduler job."""
        task_name = "NeuraFS_VFS_AutoMount"

        # 1. Прво задолжително се бришат сите постоечки/застарени NeuraFS задачи
        VFSServiceManager._remove_windows_autostart()

        # 2. Се регистрира само најновата и свежа задача
        python_exe = sys.executable
        driver_script = os.path.join(os.path.dirname(__file__), "drivers", "windows_winfsp.py")
        action = f'"{python_exe}" "{driver_script}" "{physical_storage}" "{drive_letter}"'

        cmd = [
            "schtasks", "/create", "/tn", task_name,
            "/tr", action, "/sc", "onlogon", "/f"
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[NeuraFS Persistence] Cleaned old tasks and registered new Task Scheduler job '{task_name}'")

    @staticmethod
    def _remove_windows_autostart() -> None:
        """Forcibly removes any existing NeuraFS Task Scheduler jobs."""
        task_name = "NeuraFS_VFS_AutoMount"
        cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- Linux Methods ---
    
    @staticmethod
    def _register_linux_autostart(physical_storage: str, mount_point: str) -> None:
        """Smart cleanup of old systemd user units before creating a fresh unit."""
        # 1. Прво се оневозможува и чисти стариот сервис
        VFSServiceManager._remove_linux_autostart()

        # 2. Се запишува и активира само новиот сервис
        user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
        user_systemd_dir.mkdir(parents=True, exist_ok=True)
        service_file = user_systemd_dir / "neurafs-vfs.service"

        unit_content = f"""[Unit]
Description=NeuraFS Virtual File System Persistent Mount
After=default.target

[Service]
Type=simple
ExecStart={sys.executable} -m neurafs.vfs.drivers.linux_fuse "{physical_storage}" "{mount_point}"
Restart=on-failure

[Install]
WantedBy=default.target
"""
        service_file.write_text(unit_content, encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "neurafs-vfs.service"], check=False)
        print(f"[NeuraFS Persistence] Cleaned old services and registered new systemd unit '{service_file}'")

    @staticmethod
    def _remove_linux_autostart() -> None:
        """Disables and unlinks any existing NeuraFS systemd user services."""
        subprocess.run(["systemctl", "--user", "disable", "neurafs-vfs.service"], check=False)
        service_file = Path.home() / ".config" / "systemd" / "user" / "neurafs-vfs.service"
        if service_file.exists():
            try:
                os.remove(service_file)
            except OSError:
                pass
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

    @staticmethod
    def _enable_samba_share(physical_storage: str) -> None:
        smb_conf = Path("/etc/samba/smb.conf")
        if smb_conf.exists() and os.access(smb_conf, os.W_OK):
            share_block = f"\n[NeuraFS_Share]\n   path = {physical_storage}\n   read only = no\n   guest ok = yes\n   vfs objects = neurafs\n"
            with open(smb_conf, "a", encoding="utf-8") as f:
                f.write(share_block)
            subprocess.run(["systemctl", "restart", "smbd"], check=False)