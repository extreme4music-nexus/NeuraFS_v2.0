from fastapi.testclient import TestClient

from neurafs.api.server import app


def test_health_endpoint_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
