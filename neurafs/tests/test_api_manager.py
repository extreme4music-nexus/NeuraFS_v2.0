"""Tests for API daemon readiness and failure cleanup."""

import subprocess
from pathlib import Path

import pytest

from neurafs.api import manager
from neurafs.api.manager import APIManager
from neurafs.utils import process as process_module


class FakeProcess:
    pid = 43210

    def __init__(self):
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated else 1

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 1

    def kill(self):
        self.killed = True
        self.terminated = True


def test_api_health_url_handles_wildcard_and_ipv6_hosts():
    assert manager._health_url("0.0.0.0", 8000) == "http://127.0.0.1:8000/health"
    assert manager._health_url("::", 8000) == "http://127.0.0.1:8000/health"
    assert manager._health_url("::1", 8000) == "http://[::1]:8000/health"


def test_api_endpoint_requires_expected_health_response(monkeypatch):
    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.payload

    monkeypatch.setattr(manager, "urlopen", lambda *_args, **_kwargs: Response(b'{"status":"ok"}'))
    assert manager._api_endpoint_is_ready("127.0.0.1", 8000)
    monkeypatch.setattr(manager, "urlopen", lambda *_args, **_kwargs: Response(b'{"status":"wrong"}'))
    assert not manager._api_endpoint_is_ready("127.0.0.1", 8000)


def test_daemon_pid_is_written_only_after_readiness(monkeypatch, tmp_path, capsys):
    process = FakeProcess()
    pid_file = tmp_path / "run" / "api.pid"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(APIManager, "get_running_pid", lambda: None)
    monkeypatch.setattr(process_module, "spawn_silent_daemon", lambda *a, **k: process)

    def ready(proc, host, port, log_file):
        assert proc is process
        assert host == "127.0.0.1" and port == 8123
        assert not pid_file.exists()
        assert log_file == tmp_path / ".neurafs" / "logs" / "api.log"

    monkeypatch.setattr(manager, "_wait_for_api_ready", ready)
    monkeypatch.setattr(APIManager, "get_pid_file", lambda: pid_file)

    manager.start_api(port=8123, daemon=True)

    assert pid_file.read_text(encoding="utf-8") == str(process.pid)
    assert "Background server ready" in capsys.readouterr().out


def test_daemon_start_failure_terminates_child_and_clears_pid(monkeypatch, tmp_path):
    process = FakeProcess()
    pid_file = tmp_path / "run" / "api.pid"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(APIManager, "get_running_pid", lambda: None)
    monkeypatch.setattr(process_module, "spawn_silent_daemon", lambda *a, **k: process)
    monkeypatch.setattr(APIManager, "get_pid_file", lambda: pid_file)

    def fail_ready(*_args):
        assert not pid_file.exists()
        raise RuntimeError("controlled readiness failure")

    monkeypatch.setattr(manager, "_wait_for_api_ready", fail_ready)

    with pytest.raises(RuntimeError, match="controlled readiness failure"):
        manager.start_api(port=8123, daemon=True)

    assert process.terminated
    assert not pid_file.exists()
