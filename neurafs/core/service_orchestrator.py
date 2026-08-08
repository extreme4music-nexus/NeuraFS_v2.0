"""NeuraFS Master Service Orchestrator Module.

Synchronizes startup, shutdown, auto-healing, and boot persistence
across VFS Drivers, FastAPI Engine Gateway, Express Web Dashboard, and Samba.
"""

import os
import sys
import time
import ctypes
import subprocess
from pathlib import Path
from typing import Dict, Any

from neurafs.vfs.service_manager import VFSServiceManager
from neurafs.vfs.samba_manager import SambaManager
from neurafs.core.storage import StorageManager
from neurafs.api.manager import start_api, stop_api, status_api
from neurafs.web.manager import start_web, stop_web, status_web
from neurafs.core.modules.watcher import NeuraFSWatcher
from neurafs.core.modules.queue_manager import QueueManager


class ServiceOrchestrator:
    """Master orchestrator executing synchronized background ecosystem startups and persistence."""

    @classmethod
    def ensure_services_running(cls) -> bool:
        """Auto-healing guard: Checks ecosystem health and silently starts services if down."""
        vfs_ok = VFSServiceManager.is_mounted()

        api_ok = False
        try:
            import urllib.request
            req = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
            if req.getcode() == 200:
                api_ok = True
        except Exception:
            pass

        if not (vfs_ok and api_ok):
            print("[NeuraFS Auto-Healing] Background services offline. Auto-recovering...")
            cls.start_all()
            return True
        
        watcher_ok = NeuraFSWatcher.is_active()
        if not (vfs_ok and api_ok and watcher_ok):
            print("[NeuraFS Auto-Healing] Background services offline. Auto-recovering...")
            cls.start_all()
            return True
            
        return True
        
    @classmethod
    def is_admin(cls) -> bool:
        """Checks if the current process runs with Administrator (Windows) or Root (Linux) privileges."""
        try:
            if sys.platform == "win32":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except Exception:
            return False

    @classmethod
    def start_all(cls) -> Dict[str, Any]:
        """Executes strict sequential startup across VFS, API, Web UI, and Samba."""
        results = {}

        print("\n🚀 --- Starting NeuraFS Ecosystem Services ---")

        # 1. Start VFS Driver & Mount Virtual Drive
        print("[1/4] Mounting Virtual File System Partition...")
        try:
            if not VFSServiceManager.is_mounted():
                VFSServiceManager.mount()
            results["vfs"] = "MOUNTED ✅"
        except Exception as err:
            results["vfs"] = f"FAILED ❌ ({err})"
            print(f" ⚠️ VFS Mount Error: {err}")

        # 2. Start FastAPI Core Engine Gateway (Background Daemon)
        print("[2/4] Launching FastAPI Core Neural Engine (Port 8000)...")
        try:
            start_api(host="127.0.0.1", port=8000, daemon=True)
            time.sleep(1)
            results["api"] = "RUNNING ✅ (Port 8000)"
        except Exception as err:
            results["api"] = f"FAILED ❌ ({err})"
            print(f" ⚠️ API Server Error: {err}")

        # 3. Start Express.js Web Dashboard (Background Daemon)
        print("[3/4] Launching Express Web Explorer Dashboard (Port 3000)...")
        try:
            start_web(host="127.0.0.1", port=3000, daemon=True)
            time.sleep(1)
            results["web"] = "RUNNING ✅ (Port 3000)"
        except Exception as err:
            results["web"] = f"FAILED ❌ ({err})"
            print(f" ⚠️ Web Explorer Error: {err}")

        # 4. Manage Samba Network Sharing (If on Linux & available)
        print("[4/4] Synchronizing Samba Network VFS Sharing...")
        if SambaManager.is_available():
            storage_path = StorageManager.get_path()
            samba_res = SambaManager.setup_share(storage_path)
            if samba_res["status"] == "success":
                c_status = " (Native C-Plugin ACTIVE)" if samba_res.get("c_plugin_active") else ""
                results["samba"] = f"ACTIVE ✅{c_status}"
            else:
                results["samba"] = f"SKIPPED/WARNING ⚠️ ({samba_res.get('reason')})"
        else:
            results["samba"] = "N/A (Windows Native SMB / Samba not installed)"
        
        # 5. Start File System Watcher Daemon
        print("[NeuraFS Watcher] Launching Background File Watcher...")
        try:
            NeuraFSWatcher.start_daemon()
            results["watcher"] = "RUNNING ✅"
        except Exception as err:
            results["watcher"] = f"FAILED ❌ ({err})"
            print(f" ⚠️ Watcher Error: {err}")

        # Register unified boot persistence
        cls.enable_autostart()

        print("\n✨ All NeuraFS background services active & Master Boot Persistence registered!")
        return results

    @classmethod
    def stop_all(cls) -> Dict[str, Any]:
        """Executes clean shutdown of all background services and unregisters boot persistence."""
        print("\n🛑 --- Stopping NeuraFS Ecosystem Services ---")

        # 1. Disable OS Boot Persistence
        print("[1/5] Unregistering OS Boot Persistence...")
        try:
            cls.disable_autostart()
        except Exception:
            pass

        # 2. Disable Samba Share
        print("[2/5] Disabling Samba Network Share...")
        try:
            if SambaManager.is_available():
                SambaManager.remove_share()
        except Exception:
            pass

        # 3. Stop Watcher Daemon
        print("[3/5] Stopping Background File Watcher...")
        try:
            NeuraFSWatcher.stop_daemon()
        except Exception:
            pass

        # 4. Stop Express Web Dashboard
        print("[4/5] Stopping Express Web Dashboard...")
        try:
            stop_web()
        except Exception:
            pass

        # 5. Stop FastAPI Engine
        print("[5/5] Stopping FastAPI Engine Gateway...")
        try:
            stop_api()
        except Exception:
            pass

        # 6. Unmount VFS
        print("[6/6] Unmounting Virtual File System...")
        try:
            VFSServiceManager.umount()
        except Exception:
            pass
            
        # 7. Execute State Database Recovery & Self-Healing
        try:
            from neurafs.core.modules.state_db import StateManager
            recovered = StateManager.recover_interrupted_states()
            if recovered > 0:
                print(f"[NeuraFS State Recovery] Restored {recovered} interrupted jobs back to queue.")
        except Exception:
            pass

        print("✅ All NeuraFS background services and boot persistence stopped cleanly.\n")
        return {"status": "stopped"}
        
    @classmethod
    def restart_all(cls) -> Dict[str, Any]:
        """Executes full ecosystem shutdown followed by clean startup sequence."""
        print("\n🔄 --- Initiating Full NeuraFS Ecosystem Restart ---")
        cls.stop_all()
        time.sleep(1.5)
        cls.start_all()
        return {"status": "restarted"}
        
    @classmethod
    def status_all(cls) -> None:
        """Prints aggregated status report across all background services."""
        print("\n===================================================")
        print("        NeuraFS Global Ecosystem Status              ")
        print("=====================================================")

        # Check VFS
        vfs_mounted = VFSServiceManager.is_mounted()
        print(f" • VFS Partition   : {'MOUNTED ✅' if vfs_mounted else 'UNMOUNTED ❌'}")

        # Check API Status
        print(" • Api Gateway   : ", end="")
        try:
            status_api()
        except Exception:
            print("OFFLINE ❌")

        # Check Web UI Status
        print(" • Web Dashboard   : ", end="")
        try:
            status_web()
        except Exception:
            print("OFFLINE ❌")

        # Check Samba Network Share
        if SambaManager.is_available():
            samba_active = SambaManager.is_share_active()
            print(f" • Samba Share     : {'ACTIVE ✅' if samba_active else 'INACTIVE ℹ️'}")
        else:
            print(" • Samba Share     : N/A (Windows SMB Host)")
        
        # Check File Watcher
        watcher_active = NeuraFSWatcher.is_active()
        print(f" • File Watcher    : {'ACTIVE ✅' if watcher_active else 'INACTIVE ❌'}")
        
        # Check Que Manager
        try:
            from neurafs.core.modules.queue_manager import QueueManager
            q = QueueManager.get_status_summary()
            print(f" • Queue Metrics   : {q['pending']} Pending, {q['processing']} Processing")
        except Exception:
            pass
        
        # Check Autostart Status
        is_auto = cls.is_autostart_enabled()
        print(f" • Boot Persistence: {'ENABLED ✅' if is_auto else 'DISABLED ❌'}")

        print("===================================================\n")
        
    @classmethod
    def enable_autostart(cls) -> bool:
        """Registers Master Boot Service in OS Task Scheduler (Windows) or systemd (Linux)."""
        os_type = "windows" if sys.platform == "win32" else "linux"

        # Smart privilege verification
        if not cls.is_admin():
            print("\n⚠️  [NeuraFS Privilege Notice] Administrator / Root Privileges Required!")
            if os_type == "windows":
                print(" • Boot persistence registration requires Administrator rights to access Windows Task Scheduler.")
                print(" 👉 Guidance: Close CMD/PowerShell, right-click CMD or PowerShell icon -> select 'Run as Administrator', then run:\n   neurafs service autostart on\n")
            else:
                print(" • Boot persistence registration requires Root/Sudo rights on Linux.")
                print(" 👉 Guidance: Re-run the command with sudo privileges:\n   sudo neurafs service autostart on\n")
            return False

        cls.disable_autostart()  # Clean old tasks first

        python_exe = sys.executable
        cli_script = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli.py"))

        if os_type == "windows":
            task_name = "NeuraFS_Master_Daemon"
            action = f'"{python_exe}" "{cli_script}" service start'
            cmd = [
                "schtasks", "/create", "/tn", task_name,
                "/tr", action, "/sc", "onlogon", "/f"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return res.returncode == 0

        elif os_type == "linux":
            user_systemd_dir = Path.home() / ".config" / "systemd" / "user"
            user_systemd_dir.mkdir(parents=True, exist_ok=True)
            service_file = user_systemd_dir / "neurafs-master.service"

            unit_content = f"""[Unit]
Description=NeuraFS Master Service Daemon Orchestrator
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={sys.executable} "{cli_script}" service start
ExecStop={sys.executable} "{cli_script}" service stop

[Install]
WantedBy=default.target
"""
            service_file.write_text(unit_content, encoding="utf-8")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            res = subprocess.run(["systemctl", "--user", "enable", "neurafs-master.service"], check=False)
            return res.returncode == 0

        return False

    @classmethod
    def disable_autostart(cls) -> bool:
        """Unregisters Master Boot Service from OS."""
        os_type = "windows" if sys.platform == "win32" else "linux"

        if not cls.is_admin():
            print("\n⚠️  [NeuraFS Privilege Notice] Administrator / Root Privileges Required!")
            if os_type == "windows":
                print(" 👉 Guidance: Right-click CMD/PowerShell -> 'Run as Administrator', then run:\n   neurafs service autostart off\n")
            else:
                print(" 👉 Guidance: Re-run with sudo:\n   sudo neurafs service autostart off\n")
            return False

        if os_type == "windows":
            task_name = "NeuraFS_Master_Daemon"
            cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return res.returncode == 0
        elif os_type == "linux":
            subprocess.run(["systemctl", "--user", "disable", "neurafs-master.service"], check=False)
            service_file = Path.home() / ".config" / "systemd" / "user" / "neurafs-master.service"
            if service_file.exists():
                try:
                    os.remove(service_file)
                except OSError:
                    pass
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            return True
        return False

    @classmethod
    def is_autostart_enabled(cls) -> bool:
        """Checks if Master Boot Service is registered in Task Scheduler or systemd."""
        os_type = "windows" if sys.platform == "win32" else "linux"
        if os_type == "windows":
            task_name = "NeuraFS_Master_Daemon"
            res = subprocess.run(["schtasks", "/query", "/tn", task_name], capture_output=True, text=True, check=False)
            return res.returncode == 0
        elif os_type == "linux":
            service_file = Path.home() / ".config" / "systemd" / "user" / "neurafs-master.service"
            return service_file.exists()
        return False