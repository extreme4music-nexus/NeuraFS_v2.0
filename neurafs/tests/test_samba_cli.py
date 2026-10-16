"""Unit tests for NeuraFS Samba CLI commands and SambaManager."""

import sys
import argparse
import pytest
from unittest.mock import MagicMock, patch

from neurafs.vfs.samba_manager import SambaManager
from neurafs.cli import handle_samba


def test_samba_manager_details():
    details = SambaManager.get_share_details()
    assert isinstance(details, dict)
    assert "active" in details
    assert "share_name" in details
    assert "c_plugin_active" in details


def test_handle_samba_status(capsys):
    args = argparse.Namespace(action="status")
    handle_samba(args)
    captured = capsys.readouterr()
    assert "NeuraFS Samba (SMB) Network Share Status" in captured.out
    assert "Host Support" in captured.out
    assert "Share Status" in captured.out


@patch.object(SambaManager, "is_available", return_value=True)
@patch.object(SambaManager, "setup_share")
def test_handle_samba_enable(mock_setup, mock_avail, capsys):
    mock_setup.return_value = {
        "status": "success",
        "share_name": "NeuraFS_Share",
        "path": "/tmp/test",
        "c_plugin_active": False
    }
    args = argparse.Namespace(action="enable", path="/tmp/test", name="NeuraFS_Share", read_only=False, no_guest=False)
    handle_samba(args)
    captured = capsys.readouterr()
    assert "Enabled & Configured" in captured.out
    assert mock_setup.called


@patch.object(SambaManager, "is_available", return_value=True)
@patch.object(SambaManager, "remove_share", return_value=True)
def test_handle_samba_disable(mock_remove, mock_avail, capsys):
    args = argparse.Namespace(action="disable")
    handle_samba(args)
    captured = capsys.readouterr()
    assert "Disabled & Removed" in captured.out
    assert mock_remove.called

def test_windows_samba_status_avoids_unix_config_path(monkeypatch, capsys):
    class ForbiddenPath:
        def exists(self):
            raise AssertionError("unsupported smb.conf path was accessed")

        def read_text(self, **kwargs):
            raise AssertionError("unsupported smb.conf path was read")

    monkeypatch.setattr(SambaManager, "is_available", classmethod(lambda cls: False))
    monkeypatch.setattr(SambaManager, "SMB_CONF_PATH", ForbiddenPath())

    assert SambaManager.is_share_active() is False
    details = SambaManager.get_share_details()
    assert details["active"] is False
    assert details["c_plugin_active"] is False

    handle_samba(argparse.Namespace(action="status"))
    output = capsys.readouterr().out
    assert "UNAVAILABLE" in output
    assert "Share Status  : INACTIVE" in output
