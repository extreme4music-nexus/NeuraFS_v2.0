import json

import pytest

from neurafs.vfs import service_manager as module
from neurafs.vfs.service_manager import VFSServiceManager


def test_windows_mount_failure_is_persisted_as_unmounted(tmp_path, monkeypatch, capsys):
    physical_storage = tmp_path / "physical"
    state_file = tmp_path / "vfs_state.json"
    storage_paths = []

    monkeypatch.setattr(module, "detect_os", lambda: "windows")
    monkeypatch.setattr(module, "load_vfs_state", lambda: {})
    monkeypatch.setattr(module, "get_vfs_state_file", lambda: state_file)

    def save_state(state):
        state_file.write_text(json.dumps(state), encoding="utf-8")

    monkeypatch.setattr(module, "save_vfs_state", save_state)
    monkeypatch.setattr(module, "find_free_windows_drive", lambda requested: "Z:")
    monkeypatch.setattr(VFSServiceManager, "_mount_windows", lambda *args: None)
    registrations = []
    monkeypatch.setattr(VFSServiceManager, "_register_windows_autostart", lambda *args: registrations.append(args))
    monkeypatch.setattr(VFSServiceManager, "_wait_for_mount", lambda *args: False)
    monkeypatch.setattr(VFSServiceManager, "_kill_vfs_process", lambda: None)
    monkeypatch.setattr(module.StorageManager, "get_path", lambda: str(physical_storage))
    monkeypatch.setattr(module.StorageManager, "set_path", lambda path: storage_paths.append(path))

    with pytest.raises(RuntimeError, match="did not become visible"):
        VFSServiceManager.mount(storage_path=str(physical_storage), target="Z:")

    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    output = capsys.readouterr().out
    assert saved_state["status"] == "unmounted"
    assert saved_state["virtual_target"] == "Z:"
    assert storage_paths == []
    assert registrations == []
    assert "MOUNT IN PROGRESS" not in output
    assert "Status: MOUNTED" not in output

def test_windows_mount_is_persisted_only_after_visibility(tmp_path, monkeypatch, capsys):
    physical_storage = tmp_path / "physical"
    state_file = tmp_path / "vfs_state.json"
    storage_paths = []
    registrations = []

    monkeypatch.setattr(module, "detect_os", lambda: "windows")
    monkeypatch.setattr(module, "load_vfs_state", lambda: {})
    monkeypatch.setattr(module, "get_vfs_state_file", lambda: state_file)
    monkeypatch.setattr(
        module,
        "save_vfs_state",
        lambda state: state_file.write_text(json.dumps(state), encoding="utf-8"),
    )
    monkeypatch.setattr(module, "find_free_windows_drive", lambda requested: "Z:")
    monkeypatch.setattr(VFSServiceManager, "_mount_windows", lambda *args: None)
    monkeypatch.setattr(VFSServiceManager, "_wait_for_mount", lambda *args: True)
    monkeypatch.setattr(
        VFSServiceManager,
        "_register_windows_autostart",
        lambda *args: registrations.append(args),
    )
    monkeypatch.setattr(module.StorageManager, "get_path", lambda: str(physical_storage))
    monkeypatch.setattr(module.StorageManager, "set_path", lambda path: storage_paths.append(path))

    VFSServiceManager.mount(storage_path=str(physical_storage), target="Z:")

    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    output = capsys.readouterr().out
    assert saved_state["status"] == "mounted"
    assert saved_state["virtual_target"] == "Z:"
    assert storage_paths == ["Z:"]
    assert len(registrations) == 1
    assert "Status: MOUNTED (Z:)" in output
