"""NeuraFS Command Line Utility Interface."""

import argparse
import json
import sys
from neurafs.core.initializer import NeuraFSInitializer
from neurafs.core.storage import StorageManager
from neurafs.core.service_orchestrator import ServiceOrchestrator
from neurafs.utils.logger import BenchmarkLogger
from neurafs.api.manager import start_api, stop_api, restart_api, status_api
from neurafs.web.manager import start_web, stop_web, restart_web, status_web
from neurafs.benchmarks.manager import BenchmarkManager
from neurafs.sdk.python.sdk import NeuraFSSDK
from neurafs.vfs.service_manager import VFSServiceManager
from neurafs.core.modules.watcher import NeuraFSWatcher
from neurafs.core.modules.activity_logger import ActivityLogger
from neurafs.core.modules.queue_manager import QueueManager


def handle_init(args):
    """Executes environment diagnostic and dependency initialization with progress steps."""
    print("\n🔍 [1/3] Running Environmental & Pre-Flight Diagnostics...")
    result = NeuraFSInitializer.initialize_system(custom_path=args.path)
    diag = result['diagnostics']

    print("\n📂 [2/3] Verifying Physical Storage & System Directories...")
    print(f" • Storage Root : {result['storage_path']}")
    print(f" • Config File  : {result['config_file']}")
    print(f" • Subfolders   : {', '.join(result['subfolders'])}")

    print("\n🛡️ [3/3] Environmental Dependencies Check...")
    print(f" • Host OS      : {diag['os']}")

    # VFS Driver Check
    vfs = diag['vfs_driver']
    if vfs['installed']:
        print(f" • VFS Driver   : READY ✅ ({vfs.get('path') or 'Native System Library'})")
    else:
        print(" • VFS Driver   : MISSING ⚠️")
        print(f"   👉 Guidance  : {vfs['guide']}")

    # Samba Check
    samba = diag['samba']
    if diag['os'] == "LINUX":
        print(f" • Samba VFS    : {samba['status_str']}")
        if not samba['available']:
            print(f"   👉 Guidance  : {samba['guide']}")
    else:
        print(f" • Samba VFS    : {samba['status_str']}")

    print("\n🚀 --- NeuraFS System Environment Ready ---")
    print("👉 Execute 'neurafs start' to launch background ecosystem services.\n")


def handle_start(args):
    """Launches all NeuraFS ecosystem background services with step-by-step report."""
    print("\n🚀 --- Starting NeuraFS Ecosystem Services ---")
    print("[Step 1/5] Checking environment & mounting VFS virtual drive...")
    print("[Step 2/5] Initializing State Database & executing recovery...")
    print("[Step 3/5] Starting FastAPI Core Neural Engine...")
    print("[Step 4/5] Launching Express Web Dashboard...")
    print("[Step 5/5] Activating Watchdog Daemon & Queue Workers...")
    
    ServiceOrchestrator.start_all()
    print("✨ All NeuraFS background services are active & operational.\n")


def handle_stop(args):
    """Executes full NeuraFS ecosystem shutdown with detailed progress tracking."""
    print("\n🛑 --- Shutting Down NeuraFS Ecosystem ---")
    print("[1/5] Unregistering OS Boot Persistence tasks...")
    print("[2/5] Deactivating File Watcher Daemon & Queue Workers...")
    print("[3/5] Terminating Express Web Dashboard process...")
    print("[4/5] Terminating FastAPI Core Neural Engine process...")
    print("[5/5] Unmounting VFS Virtual Partition cleanly...")
    
    ServiceOrchestrator.stop_all()
    print("✅ System fully stopped. All resources and memory locks released.\n")


def handle_restart(args):
    """Executes clean global restart sequence for all NeuraFS processes."""
    print("\n🔄 --- Initiating Global NeuraFS Ecosystem Restart ---")
    handle_stop(args)
    import time
    time.sleep(1.5)
    handle_start(args)


def handle_status(args):
    """Displays global NeuraFS ecosystem status report."""
    ServiceOrchestrator.status_all()
    

def handle_log(args):
    """Prints user activity logs."""
    logs = ActivityLogger.get_recent_logs(lines=args.lines)
    print(f"\n📋 --- NeuraFS User Activity Log (Last {args.lines} entries) ---")
    for line in logs:
        print(f" {line}")
    print()


def handle_service(args):
    """Routes master service orchestration commands."""
    if args.action == "start":
        ServiceOrchestrator.start_all()
    elif args.action == "stop":
        ServiceOrchestrator.stop_all()
    elif args.action == "status":
        ServiceOrchestrator.status_all()
    elif args.action == "autostart":
        if args.state == "on":
            ok = ServiceOrchestrator.enable_autostart()
            if ok:
                print("✅ Master Boot Service registered for automatic OS startup.")
        elif args.state == "off":
            ok = ServiceOrchestrator.disable_autostart()
            if ok:
                print("🔄 Master Boot Service unregistered from automatic OS startup.")
        elif args.state == "status":
            enabled = ServiceOrchestrator.is_autostart_enabled()
            print(f" • Boot Persistence: {'ENABLED ✅' if enabled else 'DISABLED ❌'}")
    elif args.action == "watchdog":
        if args.state == "start":
            NeuraFSWatcher.start_daemon()
        elif args.state == "stop":
            NeuraFSWatcher.stop_daemon()
        elif args.state == "status":
            active = NeuraFSWatcher.is_active()
            print(f" • File Watcher    : {'ACTIVE ✅' if active else 'INACTIVE ❌'}")
        
        
def handle_inspect(args):
    """Routes inspect command to NeuraFSSDK."""
    manifest = NeuraFSSDK.inspect(args.input)
    print(json.dumps(manifest, indent=2))


def handle_api(args):
    """Routes API management commands."""
    if args.action == "start":
        start_api(host=args.host, port=args.port, reload=args.reload, daemon=args.daemon)
    elif args.action == "stop":
        stop_api()
    elif args.action == "restart":
        restart_api(host=args.host, port=args.port, reload=args.reload, daemon=args.daemon)
    elif args.action == "status":
        status_api()


def handle_web(args):
    """Routes Web UI management commands."""
    if args.action == "start":
        start_web(port=args.port, daemon=args.daemon)
    elif args.action == "stop":
        stop_web()
    elif args.action == "restart":
        restart_web(port=args.port, daemon=args.daemon)
    elif args.action == "status":
        status_web()


def handle_benchmark(args):
    """Routes benchmark commands."""
    BenchmarkManager.run(benchmark_type=args.type)


def handle_storage(args):
    """Routes storage configuration commands."""
    if args.action == "set":
        new_path = StorageManager.set_path(args.path)
        print(f"✅ Storage root path successfully set to: {new_path}")
    elif args.action == "check":
        info = StorageManager.check()
        print("\n📂 --- NeuraFS Universal Storage Report ---")
        print(f" • Location   : {info['path']}")
        print(f" • Status     : {'EXISTS ✅' if info['exists'] else 'MISSING ❌'}")
        print(f" • Readable   : {'YES ✅' if info['readable'] else 'NO ❌'}")
        print(f" • Writable   : {'YES ✅' if info['writable'] else 'NO ❌'}")
        print(f" • Free Space : {info['free_space_gb']} GB")
        print(" • Subfolders :")
        for sub, ok in info["subfolders"].items():
            print(f"    - {sub}/ : {'OK ✅' if ok else 'MISSING ❌'}")
        print()
    elif args.action == "remove":
        StorageManager.remove_config()
        print("🔄 Storage configuration reset to default project directory.")
    elif args.action == "move":
        try:
            curr = args.current_path if args.current_path else StorageManager.get_path()
            print(f"🚚 Moving storage from '{curr}' -> '{args.new_path}'...")
            StorageManager.move(curr, args.new_path)
            print(f"✅ Storage successfully moved and path updated to: {args.new_path}")
        except Exception as err:
            print(f"❌ Storage move failed: {err}")


def handle_vfs(args):
    """Routes VFS management commands."""
    if args.action == "mount":
        target_path = getattr(args, "storage_path", None) or getattr(args, "target", None)
        samba_flag = getattr(args, "samba", False)
        VFSServiceManager.mount(target=target_path, enable_samba=samba_flag)
    elif args.action == "umount":
        target_path = getattr(args, "target", None)
        VFSServiceManager.umount(target=target_path)
    elif args.action == "status":
        VFSServiceManager.status()
        
def handle_encode(args):
    """Routes encoding command to NeuraFSSDK."""
    res = NeuraFSSDK.encode_file(args.input, args.output, precision=args.precision)
    print(f"[Success] Encoded container saved to: {res['output_path']}")


def handle_decode(args):
    """Routes decoding command to NeuraFSSDK."""
    res = NeuraFSSDK.decode_to_wav(args.input, args.output)
    print(f"[Success] Reconstructed WAV saved to: {res['output_path']}")


def handle_inspect(args):
    """Routes inspect command to NeuraFSSDK."""
    manifest = NeuraFSSDK.inspect(args.input)
    print(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(
        prog="neurafs",
        description="NeuraFS Virtual File System & Neural Storage Ecosystem CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- Top-Level Lifecycle Commands ---
    init_parser = subparsers.add_parser("init", help="Check dependencies and initialize NeuraFS environment")
    init_parser.add_argument("--path", type=str, default=None, help="Custom physical storage path")

    subparsers.add_parser("start", help="Start all NeuraFS background services and mount VFS")
    subparsers.add_parser("stop", help="Stop all background services cleanly")
    subparsers.add_parser("restart", help="Restart all background services cleanly")
    subparsers.add_parser("status", help="Display global ecosystem status report")

    # --- Service Subcommand ---
    service_parser = subparsers.add_parser("service", help="Manage background NeuraFS ecosystem services")
    service_subparsers = service_parser.add_subparsers(dest="action", required=True)
    service_subparsers.add_parser("start", help="Start VFS, API, Web UI, and Samba ecosystem")
    service_subparsers.add_parser("stop", help="Stop all background services")
    service_subparsers.add_parser("status", help="Show status of all ecosystem services")

    watchdog_parser = service_subparsers.add_parser("watchdog", help="Manage background file watcher daemon (start/stop/status)")
    watchdog_parser.add_argument("state", choices=["start", "stop", "status"], help="Start, stop, or check file watcher daemon")

    autostart_parser = service_subparsers.add_parser("autostart", help="Manage OS boot persistence (on/off/status)")
    autostart_parser.add_argument("state", choices=["on", "off", "status"], help="Enable (on), disable (off), or check (status) boot persistence")

    # --- Processing & SDK Commands ---
    encode_parser = subparsers.add_parser("encode", help="Encode media file to .hcs container")
    encode_parser.add_argument("input", help="Path to input audio file")
    encode_parser.add_argument("output", help="Path to output .hcs container")
    encode_parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")

    decode_parser = subparsers.add_parser("decode", help="Decode .hcs container to .wav")
    decode_parser.add_argument("input", help="Path to input .hcs container")
    decode_parser.add_argument("output", help="Path to output .wav file")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect .hcs container metadata")
    inspect_parser.add_argument("input", help="Path to .hcs container")

    # --- API Subcommand ---
    api_parser = subparsers.add_parser("api", help="Manage NeuraFS FastAPI server")
    api_subparsers = api_parser.add_subparsers(dest="action", required=True)
    api_start = api_subparsers.add_parser("start", help="Start the API server")
    api_start.add_argument("--host", type=str, default="127.0.0.1")
    api_start.add_argument("--port", type=int, default=8000)
    api_start.add_argument("--reload", action="store_true")
    api_start.add_argument("-d", "--daemon", action="store_true")
    api_subparsers.add_parser("stop", help="Stop running API server")
    api_restart = api_subparsers.add_parser("restart", help="Restart API server")
    api_restart.add_argument("--host", type=str, default="127.0.0.1")
    api_restart.add_argument("--port", type=int, default=8000)
    api_restart.add_argument("--reload", action="store_true")
    api_restart.add_argument("-d", "--daemon", action="store_true")
    api_subparsers.add_parser("status", help="Check running API server status")

    # --- Web Subcommand ---
    web_parser = subparsers.add_parser("web", help="Manage NeuraFS Web UI server")
    web_subparsers = web_parser.add_subparsers(dest="action", required=True)
    web_start = web_subparsers.add_parser("start", help="Start Web UI server")
    web_start.add_argument("--port", type=int, default=3000)
    web_start.add_argument("-d", "--daemon", action="store_true")
    web_subparsers.add_parser("stop", help="Stop running Web UI server")
    web_restart = web_subparsers.add_parser("restart", help="Restart Web UI server")
    web_restart.add_argument("--port", type=int, default=3000)
    web_restart.add_argument("-d", "--daemon", action="store_true")
    web_subparsers.add_parser("status", help="Check running Web UI server status")

    # --- Benchmark Subcommand ---
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmarks")
    bench_parser.add_argument("--type", choices=["encode", "decode", "full"], default="decode")

    # --- Storage Subcommand ---
    storage_parser = subparsers.add_parser("storage", help="Manage universal storage location")
    storage_subparsers = storage_parser.add_subparsers(dest="action", required=True)
    set_parser = storage_subparsers.add_parser("set", help="Set universal storage path")
    set_parser.add_argument("path", type=str)
    storage_subparsers.add_parser("check", help="Verify storage integrity")
    storage_subparsers.add_parser("remove", help="Reset storage configuration")
    move_parser = storage_subparsers.add_parser("move", help="Relocate storage contents")
    move_parser.add_argument("new_path", type=str)
    move_parser.add_argument("current_path", type=str, nargs="?", default=None)

    # --- VFS Subcommand ---
    vfs_parser = subparsers.add_parser("vfs", help="Manage Persistent Virtual File System (VFS)")
    vfs_subparsers = vfs_parser.add_subparsers(dest="action", required=True)
    mount_parser = vfs_subparsers.add_parser("mount", help="Mount persistent virtual drive")
    mount_parser.add_argument("target", nargs="?", default=None)
    mount_parser.add_argument("--samba", action="store_true")
    umount_parser = vfs_subparsers.add_parser("umount", help="Unmount virtual drive")
    umount_parser.add_argument("target", nargs="?", default=None)
    vfs_subparsers.add_parser("status", help="Show current VFS status")

    # --- Activity Log Subcommand ---
    log_parser = subparsers.add_parser("log", help="Display recent user activity log entries")
    log_parser.add_argument("-n", "--lines", type=int, default=20, help="Number of log entries to display")

    args = parser.parse_args()

    # Automatic background service check for processing tasks
    AUTO_START_COMMANDS = {"encode", "decode", "inspect", "benchmark"}
    if args.command in AUTO_START_COMMANDS:
        ServiceOrchestrator.ensure_services_running()

    # Modular Command Dispatch Router
    COMMAND_ROUTER = {
        # Core Lifecycle Commands
        "init": handle_init,
        "start": handle_start,
        "stop": handle_stop,
        "restart": handle_restart,
        "status": handle_status,
        "log": handle_log,

        # Processing & SDK Operations
        "encode": handle_encode,
        "decode": handle_decode,
        "inspect": handle_inspect,
        "benchmark": handle_benchmark,

        # Sub-system Managers
        "service": handle_service,
        "api": handle_api,
        "web": handle_web,
        "vfs": handle_vfs,
        "storage": handle_storage,
    }

    # Route execution or print help
    handler = COMMAND_ROUTER.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()