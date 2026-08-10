"""NeuraFS Zero-Touch System Initializer & Interactive Dependency Guard."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from neurafs.core.preflight import DependencyItem, PreFlightChecker
from neurafs.core.storage import StorageManager


class NeuraFSInitializer:
    """Handles pre-flight checks, interactive install, and storage setup."""

    @classmethod
    def initialize_system(cls, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """Interactive init: check → resolve missing → re-check → create storage."""
        print("\n=== NeuraFS Initialization ===")
        print("Scanning codecs, Python packages, and system dependencies...\n")

        while True:
            diagnostics = PreFlightChecker.collect_all()
            cls._print_inventory(diagnostics)

            missing_required: List[DependencyItem] = list(diagnostics["missing_required"])
            missing_codecs: List[DependencyItem] = list(diagnostics["missing_codecs"])
            missing_optional: List[DependencyItem] = list(diagnostics["missing_optional"])
            actionable = missing_required + missing_codecs + missing_optional

            if not actionable:
                break

            print("\n--- Missing components ---")
            for item in actionable:
                print(f"  [{item.category.upper()}] {item.name}")
                print(f"         {item.detail}")

            # Required deps must be resolved; codecs/optional are offered too.
            choice = cls._prompt_yes_no(
                "\nInstall missing components automatically now?",
                default_yes=True,
            )

            if choice is True:
                cls._auto_install_all(actionable)
                print("\nRe-checking environment after automatic install...")
                post = PreFlightChecker.collect_all()
                if not post["missing_required"] and not (
                    post["missing_codecs"] or post["missing_optional"]
                ):
                    diagnostics = post
                    break
                if not post["missing_required"]:
                    # Only non-blocking leftovers remain → leave loop for proceed prompt
                    diagnostics = post
                    break
                # Required still missing — show and loop again (auto / manual / stop)
                print("\nSome REQUIRED components are still missing.")
                continue

            # Manual installation path
            print("\n--- Manual installation instructions ---")
            for item in actionable:
                print(f"\n• {item.name} [{item.category}]")
                print(cls._indent(item.manual_guide, "  "))

            print(
                "\nInitialization paused."
                "\nInstall the software listed above, then type CONTINUE to re-check,"
                "\nor STOP to abort initialization."
            )
            action = cls._prompt_continue_or_stop()
            if action == "stop":
                print("\nInitialization stopped by user. Storage was not finalized.")
                sys.exit(1)

            print("\nRe-checking environment...")
            cls._refresh_path()
            post = PreFlightChecker.collect_all()
            if post["missing_required"]:
                print("\nRequired components are still missing after re-check.")
                continue
            # Required OK — exit loop (may still have codec/optional leftovers)
            diagnostics = post
            break

        # Final gate for required
        diagnostics = PreFlightChecker.collect_all()
        if diagnostics["missing_required"]:
            print("\nRequired dependencies are still missing:")
            for item in diagnostics["missing_required"]:
                print(f"  - {item.name}: {item.detail}")
                print(cls._indent(item.manual_guide, "    "))
            print("\nFix them, then run: neurafs init")
            sys.exit(1)

        leftover = list(diagnostics["missing_codecs"]) + list(diagnostics["missing_optional"])
        if leftover:
            print("\nStill missing (non-blocking for basic operation):")
            for item in leftover:
                first_line = item.manual_guide.splitlines()[0] if item.manual_guide else item.detail
                print(f"  - [{item.category}] {item.name}: {first_line}")
            proceed = cls._prompt_yes_no(
                "Continue initialization with SIREN / currently available components only?",
                default_yes=True,
            )
            if not proceed:
                print(
                    "\nInitialization paused."
                    "\nInstall remaining components, then re-run: neurafs init"
                )
                sys.exit(1)

        return cls._finalize_storage(custom_path, diagnostics)

    @classmethod
    def _finalize_storage(
        cls, custom_path: Optional[str], diagnostics: Dict[str, Any]
    ) -> Dict[str, Any]:
        print("\n--- Creating storage layout ---")
        if custom_path:
            target_path = Path(custom_path).resolve()
        else:
            target_path = Path.home() / ".neurafs" / "storage"

        target_path.mkdir(parents=True, exist_ok=True)
        for sub in ("documents", "media", ".temp"):
            (target_path / sub).mkdir(exist_ok=True)

        (Path.home() / ".neurafs" / "run").mkdir(parents=True, exist_ok=True)

        registered_path = StorageManager.set_path(str(target_path))
        print(f"  Storage root : {registered_path}")
        print(f"  Config file  : {Path.home() / '.neurafs' / 'config.json'}")
        print("  Subfolders   : documents, media, .temp")

        # Codec summary after init
        codec_items = [i for i in diagnostics["items"] if i.id.startswith("codec:")]
        print("\n--- Codecs ---")
        for item in codec_items:
            print(f"  [{'READY' if item.installed else 'SKIPPED'}] {item.name}")

        print("\nNeuraFS environment fully initialized.")
        print("Next: run  neurafs start\n")

        return {
            "status": "success",
            "storage_path": registered_path,
            "config_file": str(Path.home() / ".neurafs" / "config.json"),
            "subfolders": ["documents", "media", ".temp"],
            "diagnostics": diagnostics,
        }

    @classmethod
    def _print_inventory(cls, diagnostics: Dict[str, Any]) -> None:
        print(f"Host OS: {diagnostics['os']}")
        print("\nStatus:")
        for item in diagnostics["items"]:
            mark = "OK" if item.installed else "MISSING"
            print(f"  [{mark:7}] ({item.category:8}) {item.name}")

    @classmethod
    def _refresh_path(cls) -> None:
        """Reload PATH from the machine/user environment (Windows winget installs)."""
        if sys.platform != "win32":
            return
        try:
            import winreg

            def _read(root, sub):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "Path")
                        return val
                except OSError:
                    return ""

            machine = _read(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
            user = _read(winreg.HKEY_CURRENT_USER, "Environment")
            parts = [p for p in (machine.split(";") + user.split(";")) if p]
            # Keep current process extras, put registry paths first
            current = os.environ.get("PATH", "").split(";")
            merged = []
            for part in parts + current:
                if part and part not in merged:
                    merged.append(part)
            os.environ["PATH"] = ";".join(merged)
        except Exception:
            pass

    @classmethod
    def _auto_install_all(cls, items: List[DependencyItem]) -> None:
        print("\n--- Automatic installation ---")
        for item in items:
            if item.installed:
                continue
            print(f"\nInstalling: {item.name} ...")
            ok = cls._install_item(item)
            if ok:
                print(f"  OK: {item.name}")
            else:
                print(f"  FAILED: {item.name}")
                print(cls._indent(item.manual_guide, "  "))
        cls._refresh_path()

    @classmethod
    def _install_item(cls, item: DependencyItem) -> bool:
        if item.pip_packages:
            return cls._run_install_cmd(
                [sys.executable, "-m", "pip", "install", *item.pip_packages]
            )

        if sys.platform == "win32" and item.auto_cmd:
            return cls._run_install_cmd(item.auto_cmd)

        if sys.platform.startswith("linux") and item.auto_cmd_linux:
            return cls._run_install_cmd(item.auto_cmd_linux)

        if item.auto_cmd:
            return cls._run_install_cmd(item.auto_cmd)

        print("  No automatic installer available for this component.")
        return False

    @classmethod
    def _run_install_cmd(cls, cmd_list: List[str]) -> bool:
        print(f"  > {' '.join(cmd_list)}")
        try:
            res = subprocess.run(cmd_list, check=False)
            return res.returncode == 0
        except FileNotFoundError:
            print(f"  Command not found: {cmd_list[0]}")
            return False
        except Exception as err:
            print(f"  Install error: {err}")
            return False

    @classmethod
    def _prompt_yes_no(cls, message: str, default_yes: bool = True) -> bool:
        suffix = " [Y/n]: " if default_yes else " [y/N]: "
        while True:
            try:
                raw = input(message + suffix).strip().lower()
            except EOFError:
                return default_yes
            if raw == "":
                return default_yes
            if raw in ("y", "yes"):
                return True
            if raw in ("n", "no"):
                return False
            print("  Please answer YES or NO.")

    @classmethod
    def _prompt_continue_or_stop(cls) -> str:
        while True:
            try:
                raw = input("\nType CONTINUE or STOP: ").strip().lower()
            except EOFError:
                return "stop"
            if raw in ("continue", "c"):
                return "continue"
            if raw in ("stop", "s", "abort", "quit", "q"):
                return "stop"
            print("  Enter CONTINUE (re-check) or STOP (abort).")

    @staticmethod
    def _indent(text: str, prefix: str = "  ") -> str:
        return "\n".join(prefix + line if line else line for line in text.splitlines())
