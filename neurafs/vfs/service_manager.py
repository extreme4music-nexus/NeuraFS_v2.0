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


def find_free_windows_drive(requested_drive: Optional[str] = None) -> str:
    """Scans Windows logical drives and returns an available drive letter.
    
    If requested_drive is specified and free, uses it; otherwise scans from Z: down to D:.
    Checks both GetLogicalDrives bitmask and filesystem path accessibility.
    """
    import string
    from ctypes import windll

    bitmask = 0
    try:
        bitmask = windll.kernel32.GetLogicalDrives()
    except Exception:
        pass

    def is_drive_free(letter: str) -> bool:
        shift = ord(letter.upper()) - ord("A")
        if 0 <= shift <= 25 and bitmask:
            if bitmask & (1 << shift):
                return False
        drive_path = f"{letter.upper()}:\\"
        try:
            if os.path.exists(drive_path) or os.path.isdir(drive_path):
                return False
        except Exception:
            pass
        return True

    if requested_drive:
        clean = requested_drive.strip().upper().rstrip(":\\")
        if len(clean) == 1 and clean.isalpha():
            if is_drive_free(clean):
                return f"{clean}:"

    for letter in reversed(string.ascii_uppercase[3:26]):  # Z: down to D:
        if is_drive_free(letter):
            return f"{letter}:"

    return "Z:"


class VFSServiceManager:
    """Manages VFS driver lifecycle, OS persistence services, and StorageManager integration."""

    @staticmethod
    def _mount_target_is_visible(os_type: str, target: str) -> bool:
        if os_type == "windows":
            drive_path = f"{target.rstrip(':\\')}:\\"
            return os.path.exists(drive_path) or os.path.isdir(drive_path)
        return os.path.ismount(target)

    @classmethod
    def _wait_for_mount(cls, os_type: str, target: str, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if cls._mount_target_is_visible(os_type, target):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.3)
    
    @classmethod
    def is_mounted(cls) -> bool:
        """Checks if a NeuraFS VFS virtual partition is currently mounted and accessible."""
        state = load_vfs_state()
        if state and state.get("status") == "mounted":
            target = state.get("virtual_target")
            if target:
                target_check = f"{target}\\" if len(target) == 2 and target.endswith(":") else target
                if os.path.exists(target_check) or os.path.isdir(target_check):
                    return True
        # Fallback dynamic check: if current StorageManager path is an active Windows drive letter, consider mounted
        sm_path = StorageManager.get_path()
        if sys.platform == "win32" and len(sm_path.rstrip("\\/")) <= 2:
            drive_check = f"{sm_path.rstrip('\\/')}\\"
            if os.path.exists(drive_check) or os.path.isdir(drive_check):
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
        state = load_vfs_state()

        # 1. Resolve actual physical disk directory (preventing virtual drive letters like "X:\")
        raw_path = storage_path or target
        if raw_path and not (os_type == "windows" and len(raw_path.rstrip("\\/")) <= 2):
            physical_storage = os.path.abspath(raw_path)
        elif state.get("physical_storage"):
            physical_storage = state.get("physical_storage")
        else:
            sm_path = StorageManager.get_path()
            if os_type == "windows" and len(sm_path.rstrip("\\/")) <= 2:
                physical_storage = str(Path.home() / ".neurafs" / "storage")
            else:
                physical_storage = sm_path

        # 2. Ensure real physical storage folder exists
        os.makedirs(physical_storage, exist_ok=True)

        print(f"\n[NeuraFS VFS] Detected OS           : {os_type.upper()}")
        print(f"[NeuraFS VFS] Physical Storage Path : {physical_storage}")

        if os_type == "windows":
            req_letter = target if (target and len(target.rstrip(":\\")) == 1) else None
            target_mount = find_free_windows_drive(req_letter)
            print(f"[NeuraFS VFS] Selected Free Drive  : {target_mount}")

            cls._mount_windows(physical_storage, target_mount)
            mounted_ok = cls._wait_for_mount(os_type, target_mount)
            if mounted_ok:
                cls._register_windows_autostart(physical_storage, target_mount)

        elif os_type == "linux":
            target_mount = str(Path.home() / "NeuraFS_Drive")
            os.makedirs(target_mount, exist_ok=True)
            print(f"[NeuraFS VFS] Selected Mount Point : {target_mount}")

            cls._mount_linux(physical_storage, target_mount)
            mounted_ok = cls._wait_for_mount(os_type, target_mount)
            if mounted_ok:
                cls._register_linux_autostart(physical_storage, target_mount)

        else:
            raise RuntimeError(f"Unsupported operating system: {os_type}")

        if enable_samba and os_type == "linux" and mounted_ok:
            cls._enable_samba_share(physical_storage)

        # Redirect global StorageManager path to virtual partition if mounted successfully
        if mounted_ok:
            StorageManager.set_path(target_mount)
            print(f"[NeuraFS VFS] Global Storage path redirected -> '{target_mount}'")

        save_vfs_state({
            "status": "mounted" if mounted_ok else "unmounted",
            "os": os_type,
            "physical_storage": physical_storage,
            "virtual_target": target_mount,
            "samba_enabled": enable_samba,
            "mode": "read_write"
        })

        if not mounted_ok:
            cls._kill_vfs_process()
            raise RuntimeError(
                f"VFS mount did not become visible at {target_mount} within the startup timeout."
            )

        print(f"[NeuraFS VFS] Status: MOUNTED ({target_mount}) (RW) [OK]\n")

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
        print(f"[NeuraFS VFS] Status: UNMOUNTED & PERSISTENCE REMOVED [OK]\n")

    @classmethod
    def status(cls) -> None:
        """Displays status of the VFS virtual partition and persistence engine."""
        state = load_vfs_state()
        os_type = detect_os()
        mounted = cls.is_mounted()

        print("\n===================================================")
        print("          NeuraFS Virtual File System Status       ")
        print("===================================================")
        print(f" • Host Operating System : {os_type.upper()}")
        print(f" • Active Driver Engine  : {'WinFSP / Windows VFS' if os_type == 'windows' else 'FUSE Kernel Module'}")

        if mounted:
            v_target = state.get("virtual_target") or StorageManager.get_path()
            p_storage = state.get("physical_storage") or str(Path.home() / ".neurafs" / "storage")
            print(f" • Mount Status          : MOUNTED [OK] (Read/Write)")
            print(f" • Virtual Partition     : {v_target}")
            print(f" • Physical Storage      : {p_storage}")
            print(f" • Boot Autostart        : ACTIVE (Persisted via {'Task Scheduler' if os_type == 'windows' else 'systemd'})")
            print(f" • Samba VFS Share       : {'ENABLED [OK]' if state.get('samba_enabled') else 'DISABLED'}")
        else:
            print(f" • Mount Status          : UNMOUNTED [OFFLINE]")
            print(f" • Current Storage Path  : {StorageManager.get_path()}")
        print("===================================================\n")

    # --- Windows Methods ---

    @staticmethod
    def _mount_windows(physical_storage: str, drive_letter: str) -> None:
        """Spawns background Python daemon process to mount drive permanently without CMD window."""
        from neurafs.utils.process import spawn_silent_daemon

        python_exe = sys.executable
        driver_script = os.path.join(os.path.dirname(__file__), "drivers", "windows_winfsp.py")

        if getattr(sys, "frozen", False):
            cmd = [python_exe, "_run_winfsp_driver", physical_storage, drive_letter]
        else:
            cmd = [python_exe, driver_script, physical_storage, drive_letter]

        proc = spawn_silent_daemon(cmd, detached=True)
        
        # Track VFS process PID for clean unmounting
        if proc and hasattr(proc, "pid"):
            pid_file = Path.home() / ".neurafs" / "run" / "vfs.pid"
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(proc.pid), encoding="utf-8")

    @staticmethod
    def _umount_windows(drive_letter: str) -> None:
        from neurafs.utils.process import run_silent_subprocess

        VFSServiceManager._kill_vfs_process()
        cmd = ["subst", drive_letter, "/d"] if len(drive_letter) == 2 else ["net", "use", drive_letter, "/delete", "/y"]
        run_silent_subprocess(cmd)
    
    @staticmethod
    def _mount_linux(physical_storage: str, mount_point: str) -> None:
        from neurafs.utils.process import spawn_silent_daemon

        python_exe = sys.executable
        driver_script = os.path.join(os.path.dirname(__file__), "drivers", "linux_fuse.py")
        proc = spawn_silent_daemon([python_exe, driver_script, physical_storage, mount_point])
        
        # Track Linux FUSE process PID
        pid_file = Path.home() / ".neurafs" / "run" / "vfs.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid), encoding="utf-8")

    @staticmethod
    def _umount_linux(mount_point: str) -> None:
        from neurafs.utils.process import run_silent_subprocess

        VFSServiceManager._kill_vfs_process()
        run_silent_subprocess(["fusermount", "-u", mount_point])
        
    @staticmethod
    def _kill_vfs_process() -> None:
        """Terminates active VFS background daemon process via tracked PID."""
        from neurafs.utils.process import run_silent_subprocess

        pid_file = Path.home() / ".neurafs" / "run" / "vfs.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if sys.platform == "win32":
                    run_silent_subprocess(["taskkill", "/F", "/PID", str(pid)])
                else:
                    import signal
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                os.remove(pid_file)
            except OSError:
                pass
    
    @staticmethod
    def _register_windows_autostart(physical_storage: str, drive_letter: str) -> None:
        """Smart cleanup of old tasks before registering a clean, single Task Scheduler job."""
        from neurafs.utils.process import run_silent_subprocess

        task_name = "NeuraFS_VFS_AutoMount"

        VFSServiceManager._remove_windows_autostart()

        if getattr(sys, "frozen", False):
            action = f'"{sys.executable}" _run_winfsp_driver "{physical_storage}" "{drive_letter}"'
        else:
            python_exe = sys.executable
            driver_script = os.path.join(os.path.dirname(__file__), "drivers", "windows_winfsp.py")
            action = f'"{python_exe}" "{driver_script}" "{physical_storage}" "{drive_letter}"'

        cmd = [
            "schtasks", "/create", "/tn", task_name,
            "/tr", action, "/sc", "onlogon", "/f"
        ]
        run_silent_subprocess(cmd)
        print(f"[NeuraFS Persistence] Cleaned old tasks and registered new Task Scheduler job '{task_name}'")

    @staticmethod
    def _remove_windows_autostart() -> None:
        """Forcibly removes any existing NeuraFS Task Scheduler jobs."""
        from neurafs.utils.process import run_silent_subprocess

        task_name = "NeuraFS_VFS_AutoMount"
        cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
        run_silent_subprocess(cmd)

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