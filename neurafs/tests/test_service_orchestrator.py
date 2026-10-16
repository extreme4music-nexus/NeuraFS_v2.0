from neurafs.core import service_orchestrator as module
from neurafs.core.service_orchestrator import ServiceOrchestrator
from neurafs import cli


def test_cli_start_does_not_claim_success_when_a_service_failed(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.ServiceOrchestrator,
        "start_all",
        lambda: {"api": "FAILED ❌ (did not start)", "autostart": "NOT REGISTERED"},
    )

    try:
        cli.handle_start(None)
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("start must return a failure exit code when a service failed")

    output = capsys.readouterr().out
    assert "startup is incomplete" in output
    assert "All NeuraFS background services are active" not in output


def test_start_reports_service_and_autostart_failures(monkeypatch, capsys):
    monkeypatch.setattr(module.VFSServiceManager, "is_mounted", lambda: True)
    monkeypatch.setattr(module, "start_api", lambda **kwargs: None)
    monkeypatch.setattr(
        module,
        "start_web",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("web did not start")),
    )
    monkeypatch.setattr(module.SambaManager, "is_available", lambda: False)
    monkeypatch.setattr(module.NeuraFSWatcher, "start_daemon", lambda: None)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ServiceOrchestrator,
        "enable_autostart",
        classmethod(lambda cls: False),
    )

    results = ServiceOrchestrator.start_all()
    output = capsys.readouterr().out

    assert results["web"].startswith("FAILED")
    assert results["autostart"] == "NOT REGISTERED"
    assert "Startup completed with failures: web" in output
    assert "All NeuraFS services active" not in output
    assert "Master Boot Persistence registered" not in output

