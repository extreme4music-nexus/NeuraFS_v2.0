"""Portable setuptools compatibility entry point for NeuraFS."""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
UNINSTALL_COMMANDS = {"uninstall", "--uninstall", "-u"}


def uninstall() -> int:
    """Uninstall NeuraFS from the Python environment running this script.

    User configuration and storage under ``~/.neurafs`` are intentionally kept.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "--yes", "neurafs"],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    return result.returncode


def main() -> int:
    # Make ``python path/to/setup.py install`` independent of the caller's CWD.
    os.chdir(PROJECT_ROOT)
    if len(sys.argv) > 1 and sys.argv[1].lower() in UNINSTALL_COMMANDS:
        return uninstall()

    from setuptools import setup

    setup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
