"""NeuraFS Pre-Flight Environmental & Dependency Diagnostic Module."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import ctypes
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DependencyItem:
    """Single dependency / codec / tool check result."""

    id: str
    name: str
    category: str  # required | codec | optional
    installed: bool
    detail: str = ""
    manual_guide: str = ""
    # Prefer pip packages when set; otherwise shell auto_cmd
    pip_packages: List[str] = field(default_factory=list)
    auto_cmd: List[str] = field(default_factory=list)
    auto_cmd_linux: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PreFlightChecker:
    """Scans OS drivers, core Python packages, codecs, and system tools."""

    CORE_PIP = [
        ("torch", "torch", "PyTorch", "required"),
        ("numpy", "numpy", "NumPy", "required"),
        ("scipy", "scipy", "SciPy", "required"),
        ("fastapi", "fastapi", "FastAPI", "required"),
        ("uvicorn", "uvicorn", "Uvicorn", "required"),
        ("pydantic", "pydantic", "Pydantic", "required"),
        ("psutil", "psutil", "psutil", "required"),
        ("multipart", "python-multipart", "python-multipart", "required"),
        ("watchdog", "watchdog", "watchdog", "required"),
    ]

    @classmethod
    def detect_os(cls) -> str:
        if sys.platform == "win32":
            return "windows"
        if sys.platform.startswith("linux"):
            return "linux"
        return sys.platform

    @classmethod
    def _module_available(cls, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    @classmethod
    def _tool_available(cls, name: str) -> bool:
        return shutil.which(name) is not None

    @classmethod
    def check_winfsp(cls) -> DependencyItem:
        candidates = [
            "winfsp-x64.dll",
            r"C:\Program Files (x86)\WinFsp\bin\winfsp-x64.dll",
            r"C:\Program Files\WinFsp\bin\winfsp-x64.dll",
        ]
        loaded_path = None
        for path in candidates:
            try:
                ctypes.CDLL(path)
                loaded_path = path
                break
            except OSError:
                continue
        ok = loaded_path is not None
        return DependencyItem(
            id="winfsp",
            name="WinFsp (Windows VFS driver)",
            category="required",
            installed=ok,
            detail=loaded_path or "Not found",
            manual_guide=(
                "1) Download WinFsp from https://winfsp.dev/\n"
                "2) Run the installer (WinFsp.msi)\n"
                "3) Or: winget install WinFsp.WinFsp\n"
                "4) Return here and type continue"
            ),
            auto_cmd=[
                "winget",
                "install",
                "WinFsp.WinFsp",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
        )

    @classmethod
    def check_fuse(cls) -> List[DependencyItem]:
        fuse_bin = shutil.which("fusermount") or shutil.which("fusermount3")
        fusepy_ok = cls._module_available("fuse")
        items = [
            DependencyItem(
                id="fuse",
                name="FUSE userspace (fusermount)",
                category="required",
                installed=bool(fuse_bin),
                detail=fuse_bin or "Not found",
                manual_guide=(
                    "Debian/Ubuntu: sudo apt update && sudo apt install -y fuse3\n"
                    "Fedora: sudo dnf install -y fuse\n"
                    "Then return here and type continue"
                ),
                auto_cmd_linux=["sudo", "apt", "update"],
            ),
            DependencyItem(
                id="fusepy",
                name="Python FUSE bindings (fusepy)",
                category="required",
                installed=fusepy_ok,
                detail="import fuse OK" if fusepy_ok else "fusepy missing",
                manual_guide="pip install fusepy",
                pip_packages=["fusepy"],
            ),
        ]
        # Prefer a combined apt install for fuse when missing
        if not fuse_bin:
            items[0].auto_cmd_linux = ["sudo", "apt", "install", "-y", "fuse3"]
        return items

    @classmethod
    def check_samba(cls, os_type: str) -> DependencyItem:
        if os_type == "linux":
            smb_bin = shutil.which("smbd")
            is_active = False
            if smb_bin:
                try:
                    res = subprocess.run(
                        ["systemctl", "is-active", "smbd"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    is_active = res.stdout.strip() == "active"
                except Exception:
                    pass
            if not smb_bin:
                return DependencyItem(
                    id="samba",
                    name="Samba (smbd)",
                    category="optional",
                    installed=False,
                    detail="smbd not installed",
                    manual_guide="sudo apt update && sudo apt install -y samba && sudo systemctl enable --now smbd",
                    auto_cmd_linux=["sudo", "apt", "install", "-y", "samba"],
                )
            return DependencyItem(
                id="samba",
                name="Samba (smbd)",
                category="optional",
                installed=is_active,
                detail="active" if is_active else "installed but inactive",
                manual_guide="sudo systemctl enable --now smbd",
                auto_cmd_linux=["sudo", "systemctl", "enable", "--now", "smbd"],
            )
        return DependencyItem(
            id="samba",
            name="Windows SMB sharing",
            category="optional",
            installed=True,
            detail="Native Windows SMB available",
            manual_guide=(
                "GUI: Right-click Virtual Drive -> Properties -> Sharing\n"
                "CLI: net share NeuraFS_Drive=X:\\ /GRANT:Everyone,FULL"
            ),
        )

    @classmethod
    def check_ffmpeg(cls) -> DependencyItem:
        ok = cls._tool_available("ffmpeg")
        return DependencyItem(
            id="ffmpeg",
            name="FFmpeg",
            category="required",
            installed=ok,
            detail=shutil.which("ffmpeg") or "Not in PATH",
            manual_guide=(
                "Windows: winget install Gyan.FFmpeg   (or https://ffmpeg.org/download.html)\n"
                "Linux:   sudo apt install -y ffmpeg\n"
                "Ensure ffmpeg is on PATH, then type continue"
            ),
            auto_cmd=[
                "winget",
                "install",
                "Gyan.FFmpeg",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            auto_cmd_linux=["sudo", "apt", "install", "-y", "ffmpeg"],
        )

    @classmethod
    def check_node(cls) -> DependencyItem:
        ok = cls._tool_available("node")
        return DependencyItem(
            id="node",
            name="Node.js (Web UI)",
            category="optional",
            installed=ok,
            detail=shutil.which("node") or "Not in PATH",
            manual_guide=(
                "Windows: winget install OpenJS.NodeJS.LTS\n"
                "Linux:   sudo apt install -y nodejs npm\n"
                "Then type continue"
            ),
            auto_cmd=[
                "winget",
                "install",
                "OpenJS.NodeJS.LTS",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            auto_cmd_linux=["sudo", "apt", "install", "-y", "nodejs", "npm"],
        )

    @classmethod
    def check_node_packages(cls) -> DependencyItem:
        """Check the locked Node packages required by the web service."""
        package_root = Path(__file__).resolve().parents[1]
        required = ("express", "multer", "lzma-native")
        missing = [
            name for name in required
            if not (package_root / "node_modules" / name / "package.json").is_file()
        ]
        npm_available = cls._tool_available("npm")
        installed = not missing
        command = ["npm", "ci", "--prefix", str(package_root)] if npm_available else []
        return DependencyItem(
            id="node:packages",
            name="NeuraFS Web dependencies (Express, Multer, LZMA)",
            category="optional",
            installed=installed,
            detail="all locked packages available" if installed else "Missing: " + ", ".join(missing),
            manual_guide=(
                f'npm ci --prefix "{package_root}"'
                if npm_available
                else "Install Node.js LTS (which includes npm), then run npm ci in the NeuraFS package directory."
            ),
            auto_cmd=command,
        )

    @classmethod
    def check_core_python_packages(cls) -> List[DependencyItem]:
        items: List[DependencyItem] = []
        for mod, package, name, category in cls.CORE_PIP:
            ok = cls._module_available(mod)
            items.append(
                DependencyItem(
                    id=f"pip:{mod}",
                    name=name,
                    category=category,
                    installed=ok,
                    detail=f"import {mod}" if ok else f"Missing Python package '{mod}'",
                    manual_guide=f"pip install {package}",
                    pip_packages=[package],
                )
            )
        # Platform VFS python binding
        if sys.platform == "win32":
            ok = cls._module_available("winfspy")
            items.append(
                DependencyItem(
                    id="pip:winfspy",
                    name="winfspy (Python WinFsp bindings)",
                    category="required",
                    installed=ok,
                    detail="import winfspy" if ok else "Missing winfspy",
                    manual_guide="pip install winfspy",
                    pip_packages=["winfspy"],
                )
            )
        return items

    @classmethod
    def check_codecs(cls) -> List[DependencyItem]:
        """Check registered codecs; SIREN is core, DAC/EnCodec are optional extras."""
        items: List[DependencyItem] = []
        try:
            from neurafs.core.codecs import list_codecs

            snapshot = list_codecs()
        except Exception as err:
            return [
                DependencyItem(
                    id="codec:registry",
                    name="Codec registry",
                    category="required",
                    installed=False,
                    detail=str(err),
                    manual_guide="Reinstall NeuraFS package: pip install -e .",
                )
            ]

        # SIREN — required alternative/default (needs torch only)
        siren = snapshot.get("siren", {})
        siren_ok = bool(siren.get("available", False)) and cls._module_available("torch")
        items.append(
            DependencyItem(
                id="codec:siren",
                name="SIREN codec (default / alternative INR)",
                category="required",
                installed=siren_ok,
                detail="available" if siren_ok else (siren.get("hint") or "SIREN unavailable (needs torch)"),
                manual_guide="pip install torch",
                pip_packages=["torch"],
            )
        )

        dac = snapshot.get("dac", {})
        dac_ok = bool(dac.get("available", False))
        items.append(
            DependencyItem(
                id="codec:dac",
                name="DAC codec (Descript Audio Codec)",
                category="codec",
                installed=dac_ok,
                detail="available" if dac_ok else (dac.get("hint") or "descript-audio-codec not installed"),
                manual_guide="pip install descript-audio-codec",
                pip_packages=["descript-audio-codec"],
            )
        )

        enc = snapshot.get("encodec", {})
        enc_ok = bool(enc.get("available", False))
        items.append(
            DependencyItem(
                id="codec:encodec",
                name="EnCodec codec (Meta)",
                category="codec",
                installed=enc_ok,
                detail="available" if enc_ok else (enc.get("hint") or "encodec not installed"),
                manual_guide="pip install encodec",
                pip_packages=["encodec"],
            )
        )
        return items

    @classmethod
    def collect_all(cls) -> Dict[str, Any]:
        """Full inventory used by init."""
        os_type = cls.detect_os()
        items: List[DependencyItem] = []
        items.extend(cls.check_core_python_packages())
        items.append(cls.check_ffmpeg())
        items.append(cls.check_node())
        items.append(cls.check_node_packages())
        items.append(cls.check_samba(os_type))

        if os_type == "windows":
            items.append(cls.check_winfsp())
            # keep legacy shape for older callers
            vfs_report = cls.check_winfsp()
            vfs_legacy = {
                "installed": vfs_report.installed,
                "path": vfs_report.detail if vfs_report.installed else None,
                "guide": vfs_report.manual_guide,
            }
        elif os_type == "linux":
            fuse_items = cls.check_fuse()
            items.extend(fuse_items)
            vfs_legacy = {
                "installed": all(i.installed for i in fuse_items if i.category == "required"),
                "path": next((i.detail for i in fuse_items if i.id == "fuse"), None),
                "guide": "\n".join(i.manual_guide for i in fuse_items if not i.installed),
            }
        else:
            vfs_legacy = {"installed": False, "guide": f"Unsupported platform: {os_type}"}
            items.append(
                DependencyItem(
                    id="platform",
                    name=f"Platform support ({os_type})",
                    category="required",
                    installed=False,
                    detail="Unsupported OS",
                    manual_guide="NeuraFS currently supports Windows (WinFsp) and Linux (FUSE).",
                )
            )

        items.extend(cls.check_codecs())

        missing = [i for i in items if not i.installed]
        missing_required = [i for i in missing if i.category == "required"]
        missing_codecs = [i for i in missing if i.category == "codec"]
        missing_optional = [i for i in missing if i.category == "optional"]

        samba = cls.check_samba(os_type)
        return {
            "os": os_type.upper(),
            "items": items,
            "missing": missing,
            "missing_required": missing_required,
            "missing_codecs": missing_codecs,
            "missing_optional": missing_optional,
            "system_ready": len(missing_required) == 0,
            "vfs_driver": vfs_legacy,
            "samba": {
                "available": samba.installed,
                "status_str": ("READY ✅" if samba.installed else f"MISSING/INACTIVE ⚠️ ({samba.detail})"),
                "guide": samba.manual_guide,
            },
        }

    @classmethod
    def run_diagnostics(cls) -> Dict[str, Any]:
        """Backward-compatible entry used by initializer / CLI."""
        return cls.collect_all()
