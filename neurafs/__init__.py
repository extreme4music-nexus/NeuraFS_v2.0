"""NeuraFS Virtual Neural Media File System Package."""

import sys

__version__ = "2.3.0"
__author__ = "NeuraFS Team"

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(errors="replace")
        except Exception:
            pass