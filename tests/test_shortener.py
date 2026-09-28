from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "url-shortener-ai-ops"}

def test_create_short_url():
    response = client.post("/api/v1/shorten", json={"original_url": "https://www.schwab.com"})
    assert response.status_code == 201
    data = response.json()
    assert "short_code" in data
    assert data["original_url"] == "https://www.schwab.com/"
