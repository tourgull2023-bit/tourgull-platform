from fastapi.testclient import TestClient
from app.main import app


def test_api_v1_metadata():
    response = TestClient(app).get('/api/v1/meta')
    assert response.status_code == 200
    assert response.json() == {'platform': 'tourgull', 'api_version': 'v1'}


def test_health_still_works():
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
