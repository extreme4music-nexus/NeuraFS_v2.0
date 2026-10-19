"""NeuraFS v2.3.0 - Installer Script with Fixed Unit-Test Bundling."""

import sys
import os
import shutil
import ctypes
import subprocess
from datetime import datetime

# Windows registry access is only needed by the native Windows installer.
if sys.platform == "win32":
    import winreg
else:
    winreg = None

NEURAFS_VERSION = "2.3.0"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Safe exclusions (Keeping heavy GUI/dev tools out, leaving core dependencies intact)
EXCLUDED_MODULES = [
    "tkinter",
    "matplotlib",
    "IPython",
    "notebook",
    "pytest",
    "PIL._tkinter_finder",
]


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin():
    script = os.path.abspath(sys.argv[0])
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}" {params}', None, 1
    )
    sys.exit(0)


def ensure_dependencies():
    print(f"[NeuraFS Build] Checking dependencies for NeuraFS v{NEURAFS_VERSION}...")
    source_dir = PROJECT_ROOT
    req_file = os.path.join(source_dir, "requirements.txt")

    if os.path.exists(req_file):
        print("[NeuraFS Build] Synchronizing dependencies from requirements.txt...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[NeuraFS Build] Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)


def build_and_install():
    if sys.platform != "win32":
        raise RuntimeError(
            "The custom PyInstaller installer currently supports Windows only. "
            "Install the Python package with 'python -m pip install .' on this host."
        )
    print(f"=== NeuraFS v{NEURAFS_VERSION} Installer ===")

    if not is_admin():
        print("[NeuraFS Build] Administrator privileges required. Requesting elevation...")
        run_as_admin()

    ensure_dependencies()

    source_dir = PROJECT_ROOT
    cli_entry = os.path.join(source_dir, "neurafs", "cli.py")
    web_dir = os.path.join(source_dir, "neurafs", "web")

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    install_target = os.path.join(program_files, "NeuraFS")
    dist_dir = os.path.join(source_dir, "dist")
    build_dir = os.path.join(source_dir, "build")

    print(f"[NeuraFS Build] Source Root: {source_dir}")
    print(f"[NeuraFS Build] Install Target: {install_target}")

    # Build using --onedir mode, forcing inclusion of unittest for PyTorch FX
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name=neurafs",
        "--hidden-import=unittest",
        "--collect-all",
        "unittest",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "watchdog",
        cli_entry,
    ]

    for mod in EXCLUDED_MODULES:
        pyinstaller_cmd.extend(["--exclude-module", mod])

    if os.path.exists(web_dir):
        pyinstaller_cmd.extend(["--add-data", f"{web_dir};neurafs/web"])

    print("[NeuraFS Build] Compiling NeuraFS binary distribution with unittest bundled...")
    subprocess.run(pyinstaller_cmd, check=True, cwd=source_dir)

    dist_neurafs_folder = os.path.join(dist_dir, "neurafs")
    if not os.path.exists(dist_neurafs_folder):
        raise FileNotFoundError("[NeuraFS Build Error] Compiled output directory not found.")

    # Clean existing installation directory in Program Files
    if os.path.exists(install_target):
        print("[NeuraFS Build] Removing previous installation directory...")
        shutil.rmtree(install_target, ignore_errors=True)

    # Deploy compiled binary assets directly to C:\Program Files\NeuraFS
    print(f"[NeuraFS Build] Deploying compiled binary to {install_target}...")
    shutil.copytree(dist_neurafs_folder, install_target, dirs_exist_ok=True)

    # Register C:\Program Files\NeuraFS in System PATH
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        ) as key:
            current_path, _ = winreg.QueryValueEx(key, "Path")
            path_list = [p.strip() for p in current_path.split(";") if p.strip()]
            if install_target not in path_list:
                new_path = f"{current_path};{install_target}"
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                print("[NeuraFS Build] Added C:\\Program Files\\NeuraFS to System PATH.")
    except Exception as e:
        print(f"[NeuraFS Build Warning] Could not update System PATH: {e}")

    # Clean local temporary build folders
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(build_dir, ignore_errors=True)
    spec_file = os.path.join(source_dir, "neurafs.spec")
    if os.path.exists(spec_file):
        os.remove(spec_file)

    print(f"\n NeuraFS v{NEURAFS_VERSION} successfully installed to C:\\Program Files\\NeuraFS\\")


def uninstall():
    if sys.platform != "win32":
        raise RuntimeError("The custom NeuraFS uninstaller currently supports Windows only.")
    print(f"=== NeuraFS v{NEURAFS_VERSION} Uninstaller ===")

    if not is_admin():
        run_as_admin()

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    install_target = os.path.join(program_files, "NeuraFS")
    log_file = os.path.join(PROJECT_ROOT, "neurafs_uninstall.log")

    log_entries = [
        f"==================================================\n",
        f" NeuraFS v{NEURAFS_VERSION} Uninstallation Log\n",
        f" Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"==================================================\n\n",
    ]

    if os.path.exists(install_target):
        for root, dirs, files in os.walk(install_target, topdown=False):
            for name in files:
                file_path = os.path.join(root, name)
                try:
                    os.remove(file_path)
                    log_entries.append(f"[REMOVED FILE] {file_path}\n")
                except Exception as e:
                    log_entries.append(f"[ERROR FILE]   {file_path} -> {e}\n")

            for name in dirs:
                dir_path = os.path.join(root, name)
                try:
                    os.rmdir(dir_path)
                    log_entries.append(f"[REMOVED DIR]  {dir_path}\n")
                except Exception as e:
                    log_entries.append(f"[ERROR DIR]    {dir_path} -> {e}\n")

        try:
            os.rmdir(install_target)
            log_entries.append(f"[REMOVED ROOT] {install_target}\n")
        except Exception as e:
            log_entries.append(f"[ERROR ROOT]   {install_target} -> {e}\n")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        ) as key:
            current_path, _ = winreg.QueryValueEx(key, "Path")
            paths = [p for p in current_path.split(";") if p.strip()]

            if install_target in paths:
                paths = [p for p in paths if p.lower() != install_target.lower()]
                new_path = ";".join(paths)
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                log_entries.append(f"[REGISTRY] Removed {install_target} from System PATH.\n")
    except Exception as e:
        log_entries.append(f"[REGISTRY ERROR] {e}\n")

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(log_entries)

    print(f"\n NeuraFS completely uninstalled. Log: {log_file}")


def main():
    os.chdir(PROJECT_ROOT)
    setuptools_cmds = {"install", "egg_info", "bdist_wheel", "build_wheel", "editable_wheel", "dist_info", "sdist", "develop"}
    if len(sys.argv) > 1 and any(cmd in sys.argv for cmd in setuptools_cmds):
        from setuptools import setup, find_packages
        setup(
            name="neurafs",
            version=NEURAFS_VERSION,
            packages=find_packages(),
            entry_points={
                "console_scripts": [
                    "neurafs=neurafs.cli:main",
                ],
            },
        )
        return

    if len(sys.argv) > 1 and sys.argv[1].lower() in ["uninstall", "--uninstall", "-u"]:
        uninstall()
    else:
        build_and_install()


if __name__ == "__main__":
    main()