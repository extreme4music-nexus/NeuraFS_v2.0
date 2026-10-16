"""NeuraFS Process Silencing & Subprocess Launcher Utilities (Zero-Ghost Window Policy)."""

from __future__ import annotations

import sys
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
DETACHED_PROCESS = 0x00000008


def get_silent_creation_flags(detached: bool = False) -> int:
    """Returns exact Windows process creation flags to guarantee zero console window popup."""
    if sys.platform != "win32":
        return 0
    flags = CREATE_NO_WINDOW
    if detached:
        flags |= CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
    return flags


def run_silent_subprocess(
    cmd: Union[List[str], str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Executes a subprocess silently without popping CMD or PowerShell windows."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", get_silent_creation_flags())

    if capture_output:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("text", text)

    return subprocess.run(cmd, cwd=cwd, env=env, check=check, **kwargs)


def spawn_silent_daemon(
    cmd: Union[List[str], str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    detached: bool = True,
    **kwargs: Any,
) -> subprocess.Popen:
    """Spawns a detached background daemon process with zero console window footprint."""
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    kwargs.setdefault("stdin", subprocess.DEVNULL)

    if sys.platform == "win32":
        if detached:
            try:
                flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
                kwargs_copy = kwargs.copy()
                kwargs_copy["creationflags"] = flags
                return subprocess.Popen(cmd, cwd=cwd, env=env, **kwargs_copy)
            except OSError:
                pass
        flags = CREATE_NO_WINDOW | (CREATE_NEW_PROCESS_GROUP if detached else 0)
        kwargs["creationflags"] = flags
        return subprocess.Popen(cmd, cwd=cwd, env=env, **kwargs)

    return subprocess.Popen(cmd, cwd=cwd, env=env, **kwargs)
