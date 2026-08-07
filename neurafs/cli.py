"""NeuraFS Command Line Utility Interface."""

import argparse
import json
import sys
from neurafs.core.initializer import NeuraFSInitializer
from neurafs.core.storage import StorageManager
from neurafs.utils.logger import BenchmarkLogger
from neurafs.api.manager import start_api, stop_api, restart_api, status_api
from neurafs.web.manager import start_web, stop_web, restart_web, status_web
from neurafs.benchmarks.manager import BenchmarkManager
from neurafs.sdk.python.sdk import NeuraFSSDK
from neurafs.vfs.service_manager import VFSServiceManager


def handle_init(args):
    """Routes initialization commands to NeuraFSInitializer."""
    result = NeuraFSInitializer.initialize_system(custom_path=args.path)
    print("\n🚀 --- NeuraFS System Initialized ---")
    print(f" • Status       : {result['status'].upper()} ✅")
    print(f" • Storage Root : {result['storage_path']}")
    print(f" • Config File  : {result['config_file']}")
    print(f" • Subfolders   : {', '.join(result['subfolders'])}\n")


def handle_api(args):
    """Routes API management commands to APIManager."""
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
    """Routes storage configuration and maintenance commands."""
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
    """Routes VFS management commands to VFSServiceManager."""
    if args.action == "mount":
        target_path = getattr(args, "storage_path", None) or getattr(args, "target", None)
        samba_flag = getattr(args, "samba", False)
        VFSServiceManager.mount(target=target_path, enable_samba=samba_flag)
    elif args.action == "umount":
        target_path = getattr(args, "target", None)
        VFSServiceManager.umount(target=target_path)
    elif args.action == "status":
        VFSServiceManager.status()


def main():
    parser = argparse.ArgumentParser(description="NeuraFS Neural Media Storage CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    init_parser = subparsers.add_parser("init", help="Zero-touch initialization of NeuraFS storage and config")
    init_parser.add_argument("--path", type=str, default=None, help="Optional custom physical storage path")

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Encode media file to .hcs container")
    encode_parser.add_argument("input", help="Path to input audio file")
    encode_parser.add_argument("output", help="Path to output .hcs container")
    encode_parser.add_argument("--precision", choices=["fp16", "fp32"], default="fp16")

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode .hcs container to .wav")
    decode_parser.add_argument("input", help="Path to input .hcs container")
    decode_parser.add_argument("output", help="Path to output .wav file")

    # API Subcommand
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

    # Web Subcommand
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

    # Benchmark Subcommand
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmarks")
    bench_parser.add_argument("--type", choices=["encode", "decode", "full"], default="decode")

    # Storage Subcommand
    storage_parser = subparsers.add_parser("storage", help="Manage universal storage location")
    storage_subparsers = storage_parser.add_subparsers(dest="action", required=True)
    set_parser = storage_subparsers.add_parser("set", help="Set universal storage path")
    set_parser.add_argument("path", type=str)
    storage_subparsers.add_parser("check", help="Verify storage integrity")
    storage_subparsers.add_parser("remove", help="Reset storage configuration")
    move_parser = storage_subparsers.add_parser("move", help="Relocate storage contents")
    move_parser.add_argument("new_path", type=str)
    move_parser.add_argument("current_path", type=str, nargs="?", default=None)

    # Inspect Command
    inspect_parser = subparsers.add_parser("inspect", help="Inspect .hcs container metadata")
    inspect_parser.add_argument("input", help="Path to .hcs container")

    # VFS Subcommand
    vfs_parser = subparsers.add_parser("vfs", help="Manage Persistent Virtual File System (VFS)")
    vfs_subparsers = vfs_parser.add_subparsers(dest="action", required=True)
    mount_parser = vfs_subparsers.add_parser("mount", help="Mount persistent virtual drive")
    mount_parser.add_argument("target", nargs="?", default=None)
    mount_parser.add_argument("--samba", action="store_true")
    umount_parser = vfs_subparsers.add_parser("umount", help="Unmount virtual drive")
    umount_parser.add_argument("target", nargs="?", default=None)
    vfs_subparsers.add_parser("status", help="Show current VFS status")

    args = parser.parse_args()

    if args.command == "init":
        handle_init(args)
    elif args.command == "encode":
        res = NeuraFSSDK.encode_file(args.input, args.output, precision=args.precision)
        print(f"[Success] Encoded container saved to: {res['output_path']}")
    elif args.command == "decode":
        res = NeuraFSSDK.decode_to_wav(args.input, args.output)
        print(f"[Success] Reconstructed WAV saved to: {res['output_path']}")
    elif args.command == "storage":
        handle_storage(args)
    elif args.command == "inspect":
        manifest = NeuraFSSDK.inspect(args.input)
        print(json.dumps(manifest, indent=2))
    elif args.command == "benchmark":
        handle_benchmark(args)
    elif args.command == "api":
        handle_api(args)
    elif args.command == "web":
        handle_web(args)
    elif args.command == "vfs":
        handle_vfs(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()