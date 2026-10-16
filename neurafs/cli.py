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
    """Interactive init: dependency/codec scan, auto or manual install, then storage setup."""
    result = NeuraFSInitializer.initialize_system(custom_path=args.path)
    if result.get("status") != "success":
        print("Initialization did not complete successfully.")
        sys.exit(1)


def handle_start(args):
    """Launches all NeuraFS ecosystem background services with step-by-step report."""
    # Use ASCII banner for Windows consoles (cp1252) to avoid encoding errors.
    print("\n[START] --- Starting NeuraFS Ecosystem Services ---")
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
    action = getattr(args, "action", None)
    if action == "mount":
        target_path = getattr(args, "storage_path", None) or getattr(args, "target", None)
        samba_flag = getattr(args, "samba", False)
        VFSServiceManager.mount(target=target_path, enable_samba=samba_flag)
    elif action in ("umount", "unmount"):
        target_path = getattr(args, "target", None)
        VFSServiceManager.umount(target=target_path)
    elif action == "status":
        VFSServiceManager.status()


def handle_mount(args):
    """Direct top-level handler for 'neurafs mount'."""
    target_path = getattr(args, "target", None)
    samba_flag = getattr(args, "samba", False)
    VFSServiceManager.mount(target=target_path, enable_samba=samba_flag)


def handle_umount(args):
    """Direct top-level handler for 'neurafs umount' / 'neurafs unmount'."""
    target_path = getattr(args, "target", None)
    VFSServiceManager.umount(target=target_path)


def handle_winfsp_driver(args):
    """Internal CLI handler for WinFSP background daemon process."""
    from neurafs.vfs.drivers.windows_winfsp import mount_windows_winfsp, NeuraFSWinFSP
    import signal
    storage_dir = getattr(args, "storage", None) or "storage"
    drive_letter = getattr(args, "drive", None) or "Z:"
    mount_windows_winfsp(storage_dir, drive_letter)
    driver = NeuraFSWinFSP(storage_dir)

    def _sig_handler(sig, frame):
        driver.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    try:
        while not driver._shutdown_event.is_set():
            driver._shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        driver.shutdown()


def handle_api_server(args):
    """Internal CLI handler for API server background daemon process."""
    import uvicorn
    host = getattr(args, "host", "127.0.0.1")
    port = int(getattr(args, "port", 8000))
    uvicorn.run("neurafs.api.server:app", host=host, port=port)


def handle_watcher_daemon(args):
    """Internal CLI handler for Watcher background daemon process."""
    from neurafs.core.modules.watcher import NeuraFSWatcher
    NeuraFSWatcher.run_forever()


def handle_samba(args):
    """Routes Samba / SMB network share management commands (enable, disable, status, config)."""
    from neurafs.vfs.samba_manager import SambaManager
    from neurafs.vfs.service_manager import load_vfs_state, save_vfs_state
    from neurafs.core.storage import StorageManager

    action = getattr(args, "action", None)

    if action in ("enable", "start", "on"):
        storage_path = getattr(args, "path", None) or StorageManager.get_path()
        share_name = getattr(args, "name", None) or "NeuraFS_Share"
        read_only = getattr(args, "read_only", False)
        guest_ok = not getattr(args, "no_guest", False)

        res = SambaManager.setup_share(
            physical_storage_path=storage_path,
            share_name=share_name,
            read_only=read_only,
            guest_ok=guest_ok
        )

        if res.get("status") == "success":
            vstate = load_vfs_state()
            if vstate:
                vstate["samba_enabled"] = True
                vstate["samba_share_name"] = share_name
                save_vfs_state(vstate)

            c_plugin_str = "ACTIVE ✅" if res.get("c_plugin_active") else "INACTIVE (smbd fallback)"
            print("\n✅ NeuraFS Samba Network Share Enabled & Configured!")
            print(f" • Share Name   : {res.get('share_name')}")
            print(f" • Physical Path: {res.get('path')}")
            print(f" • Access Mode  : {'Read-Only 🔒' if read_only else 'Read-Write 📝'}")
            print(f" • Guest Access : {'Enabled (No Password)' if guest_ok else 'Disabled (Authentication Required)'}")
            print(f" • C-VFS Plugin : {c_plugin_str}")
            print(f" • SMB Daemon   : Reloaded smbd\n")
        elif res.get("status") == "skipped":
            print(f"\n⚠️  Samba Share Skipped: {res.get('reason')}")
            print(" 👉 Hint: On Linux, install smbd (`sudo apt install samba`). On Windows, Samba is managed via host OS native network sharing.\n")
        else:
            print(f"\n❌ Failed to enable Samba share: {res.get('reason')}\n")

    elif action in ("disable", "stop", "off"):
        if not SambaManager.is_available():
            print("\n⚠️  Samba (smbd) is not installed on this host.\n")
            return

        ok = SambaManager.remove_share()
        if ok:
            vstate = load_vfs_state()
            if vstate:
                vstate["samba_enabled"] = False
                save_vfs_state(vstate)
            print("\n✅ NeuraFS Samba Network Share Disabled & Removed from smb.conf.\n")
        else:
            print("\n❌ Failed to disable Samba share or permission denied.\n")

    elif action == "status":
        avail = SambaManager.is_available()
        active = SambaManager.is_share_active()
        details = SambaManager.get_share_details() if avail else {}

        print("\n===================================================")
        print("      NeuraFS Samba (SMB) Network Share Status     ")
        print("===================================================")
        print(f" • Host Support  : {'AVAILABLE ✅' if avail else 'UNAVAILABLE ❌ (smbd missing or non-Linux)'}")
        print(f" • Share Status  : {'ACTIVE ✅' if active else 'INACTIVE ❌'}")
        if active:
            print(f" • Share Name    : {details.get('share_name', 'NeuraFS_Share')}")
            print(f" • Shared Path   : {details.get('path', StorageManager.get_path())}")
            ro = details.get('read_only')
            ro_str = 'Read-Only 🔒' if ro is True else ('Read-Write 📝' if ro is False else 'Unknown')
            print(f" • Access Mode   : {ro_str}")
            g = details.get('guest_ok')
            g_str = 'Enabled (Public)' if g is True else ('Disabled (Private)' if g is False else 'Unknown')
            print(f" • Guest Access  : {g_str}")
            print(f" • C-VFS Plugin  : {'INSTALLED ✅' if details.get('c_plugin_active') else 'NOT FOUND'}")
        print("===================================================\n")

    elif action in ("config", "configure"):
        if not SambaManager.is_available():
            print("\n⚠️  Samba (smbd) is not installed on this host.\n")
            return

        details = SambaManager.get_share_details()
        curr_path = details.get("path") or StorageManager.get_path()
        curr_name = details.get("share_name") or "NeuraFS_Share"
        curr_ro = details.get("read_only", False)
        curr_guest = details.get("guest_ok", True)

        new_path = getattr(args, "path", None) or curr_path
        new_name = getattr(args, "name", None) or curr_name

        ro_arg = getattr(args, "read_only", None)
        if ro_arg is not None:
            new_ro = (ro_arg.lower() in ("yes", "true", "1"))
        else:
            new_ro = curr_ro

        guest_arg = getattr(args, "guest_ok", None)
        if guest_arg is not None:
            new_guest = (guest_arg.lower() in ("yes", "true", "1"))
        else:
            new_guest = curr_guest

        res = SambaManager.setup_share(
            physical_storage_path=new_path,
            share_name=new_name,
            read_only=new_ro,
            guest_ok=new_guest
        )

        if res.get("status") == "success":
            print("\n✅ NeuraFS Samba Configuration Updated Successfully!")
            print(f" • Share Name   : {new_name}")
            print(f" • Physical Path: {new_path}")
            print(f" • Access Mode  : {'Read-Only 🔒' if new_ro else 'Read-Write 📝'}")
            print(f" • Guest Access : {'Enabled' if new_guest else 'Disabled'}")
            print(f" • Service State: smbd reloaded\n")
        else:
            print(f"\n❌ Failed to update Samba configuration: {res.get('reason')}\n")
    else:
        print("\n❌ Invalid Samba action. Available actions: enable, disable, status, config\n")

        
def handle_list_codecs(args):
    """Lists all registered neural codecs with detailed availability status."""
    from neurafs.core.codecs import list_codecs
    import json

    codecs_info = list_codecs()
    if getattr(args, "json", False):
        print(json.dumps(codecs_info, indent=2))
        return

    print("\n📦 --- NeuraFS Registered Neural Codecs ---")
    print(f" {'ID':<15} {'Architecture':<22} {'Kind':<18} {'Status':<15}")
    print(" " + "─" * 72)
    for codec_id, info in codecs_info.items():
        status_str = "AVAILABLE ✅" if info["available"] else "UNAVAILABLE ❌"
        print(f" {codec_id:<15} {info['architecture']:<22} {info['kind']:<18} {status_str:<15}")
        if not info["available"] and info.get("hint"):
            print(f"   └─ 💡 {info['hint']}")
    print()


def handle_codec(args):
    """Routes codec management commands (set, get, list)."""
    from neurafs.core.codecs import CODEC_REGISTRY, list_codecs
    from neurafs.core.config import config, EngineConfig

    action = getattr(args, "action", None)
    if action == "set":
        target = args.name.lower().strip()
        if target not in CODEC_REGISTRY:
            known = ", ".join(sorted(CODEC_REGISTRY.keys()))
            print(f"❌ Error: Codec '{args.name}' is not registered. Registered codecs: {known}")
            sys.exit(1)

        codecs_info = list_codecs()
        info = codecs_info.get(target, {})
        if not info.get("available", True):
            print(f"⚠️  Warning: Codec '{target}' is registered but currently unavailable on this system.")
            if info.get("hint"):
                print(f"💡 Hint: {info['hint']}")

        new_default = EngineConfig.set_default_codec(target)
        print(f"✅ Default neural codec successfully set to: '{new_default}' ({info.get('architecture', new_default)}) [{info.get('kind', 'inr_weights')}]")

    elif action == "get":
        curr = config.DEFAULT_CODEC
        codecs_info = list_codecs()
        info = codecs_info.get(curr, {})
        print(f"📌 Current Default Neural Codec: '{curr}' ({info.get('architecture', curr)}) [{info.get('kind', 'inr_weights')}]")

    elif action == "list":
        handle_list_codecs(args)
    else:
        curr = config.DEFAULT_CODEC
        codecs_info = list_codecs()
        info = codecs_info.get(curr, {})
        print(f"📌 Current Default Neural Codec: '{curr}' ({info.get('architecture', curr)}) [{info.get('kind', 'inr_weights')}]")


def handle_encode(args):
    """Routes encoding command to NeuraFSSDK with validation of neural codec selection."""
    from neurafs.core.codecs import CODEC_REGISTRY, list_codecs
    from neurafs.core.config import config

    selected_codec = getattr(args, "codec", None) or config.DEFAULT_CODEC
    codec_key = selected_codec.lower().strip()

    if codec_key not in CODEC_REGISTRY:
        known = ", ".join(sorted(CODEC_REGISTRY.keys()))
        print(f"❌ Error: Codec '{selected_codec}' is not registered. Registered codecs: {known}")
        sys.exit(1)

    codecs_info = list_codecs()
    info = codecs_info.get(codec_key, {})
    if not info.get("available", True):
        print(f"❌ Error: Codec '{selected_codec}' is registered but unavailable on this system.")
        if info.get("hint"):
            print(f"💡 Hint: {info['hint']}")
        sys.exit(1)

    print(f"⚡ Encoding '{args.input}' using codec: '{codec_key}' ({info.get('architecture', codec_key)}) [{info.get('kind', 'inr_weights')}]...")
    res = NeuraFSSDK.encode_file(args.input, args.output, precision=args.precision, codec=codec_key)
    print(f"✅ [Success] Encoded container saved to: {res['output_path']}")


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

    # --- Top-Level Mount / Umount Commands ---
    top_mount = subparsers.add_parser("mount", help="Mount persistent virtual drive")
    top_mount.add_argument("target", nargs="?", default=None, help="Target drive letter (e.g. Z:) or mount directory")
    top_mount.add_argument("--samba", action="store_true", help="Enable Samba share (Linux)")

    top_umount = subparsers.add_parser("umount", help="Unmount persistent virtual drive")
    top_umount.add_argument("target", nargs="?", default=None, help="Target drive letter or mount directory")

    top_unmount = subparsers.add_parser("unmount", help="Alias for umount")
    top_unmount.add_argument("target", nargs="?", default=None)

    winfsp_p = subparsers.add_parser("_run_winfsp_driver", help=argparse.SUPPRESS)
    winfsp_p.add_argument("storage", nargs="?", default="storage")
    winfsp_p.add_argument("drive", nargs="?", default="Z:")

    api_srv_p = subparsers.add_parser("_run_api_server", help=argparse.SUPPRESS)
    api_srv_p.add_argument("--host", type=str, default="127.0.0.1")
    api_srv_p.add_argument("--port", type=int, default=8000)

    subparsers.add_parser("_run_watcher_daemon", help=argparse.SUPPRESS)

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

    # --- Codec Subcommand ---
    codec_parser = subparsers.add_parser("codec", help="Manage neural audio codecs and configure default codec")
    codec_subparsers = codec_parser.add_subparsers(dest="action", required=True)

    set_codec_parser = codec_subparsers.add_parser("set", help="Set the default neural codec")
    set_codec_parser.add_argument("name", type=str, help="Codec ID to set as default (e.g. siren, dac, encodec)")

    codec_subparsers.add_parser("get", help="Display current default neural codec")

    list_codec_subparser = codec_subparsers.add_parser("list", help="List registered neural codecs and availability")
    list_codec_subparser.add_argument("--json", action="store_true", help="Output raw JSON format")

    # --- Processing & SDK Commands ---
    list_codecs_parser = subparsers.add_parser("list-codecs", help="List registered neural codecs and availability")
    list_codecs_parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    encode_parser = subparsers.add_parser("encode", help="Encode media file to .hcs container")
    encode_parser.add_argument("input", help="Path to input audio file")
    encode_parser.add_argument("output", help="Path to output .hcs container")
    encode_parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")
    encode_parser.add_argument("--codec", type=str, default=None,
                              help="Neural codec (e.g., siren, dac, encodec, future_codec). Default: siren")

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

    # --- Samba / Share Subcommand ---
    def _setup_samba_subparsers(sub_p):
        enable_p = sub_p.add_parser("enable", aliases=["start", "on"], help="Enable and configure NeuraFS Samba share")
        enable_p.add_argument("--path", type=str, default=None, help="Physical storage path to share")
        enable_p.add_argument("--name", type=str, default="NeuraFS_Share", help="Samba share name (default: NeuraFS_Share)")
        enable_p.add_argument("--read-only", action="store_true", help="Set share to read-only mode")
        enable_p.add_argument("--no-guest", action="store_true", help="Disable guest access (require auth)")

        sub_p.add_parser("disable", aliases=["stop", "off"], help="Disable and remove NeuraFS Samba share")
        sub_p.add_parser("status", help="Check Samba network share status")

        config_p = sub_p.add_parser("config", aliases=["configure"], help="Configure Samba share parameters")
        config_p.add_argument("--path", type=str, default=None, help="Update physical storage path")
        config_p.add_argument("--name", type=str, default=None, help="Update Samba share name")
        config_p.add_argument("--read-only", choices=["yes", "no"], default=None, help="Set read-only mode (yes/no)")
        config_p.add_argument("--guest-ok", choices=["yes", "no"], default=None, help="Set guest access mode (yes/no)")

    samba_parser = subparsers.add_parser("samba", help="Manage Samba (SMB) network sharing directly from terminal")
    _setup_samba_subparsers(samba_parser.add_subparsers(dest="action", required=True))

    share_parser = subparsers.add_parser("share", help="Alias for 'samba' network share management")
    _setup_samba_subparsers(share_parser.add_subparsers(dest="action", required=True))

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
        "mount": handle_mount,
        "umount": handle_umount,
        "unmount": handle_umount,
        "_run_winfsp_driver": handle_winfsp_driver,
        "_run_api_server": handle_api_server,
        "_run_watcher_daemon": handle_watcher_daemon,

        # Processing & SDK Operations
        "list-codecs": handle_list_codecs,
        "codec": handle_codec,
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
        "samba": handle_samba,
        "share": handle_samba,
    }

    # Route execution or print help
    handler = COMMAND_ROUTER.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()