"""Unit + integration tests for the URL shortener service."""
import os
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TESTING", "1")

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_shorten_and_redirect():
    r = client.post("/api/shorten", json={"url": "https://example.com/very/long/path"})
    assert r.status_code == 201
    body = r.json()
    assert len(body["short_code"]) == 7

    r2 = client.get(f"/{body['short_code']}", follow_redirects=False)
    assert r2.status_code == 307
    assert r2.headers["location"] == "https://example.com/very/long/path"


def test_custom_alias():
    r = client.post("/api/shorten", json={"url": "https://example.com/x", "custom_alias": "mycustom"})
    assert r.status_code == 201
    assert r.json()["short_code"] == "mycustom"

    r_dup = client.post("/api/shorten", json={"url": "https://example.com/y", "custom_alias": "mycustom"})
    assert r_dup.status_code == 409


def test_unknown_code_404():
    r = client.get("/doesnotexist", follow_redirects=False)
    assert r.status_code == 404


def test_analytics_tracks_clicks():
    r = client.post("/api/shorten", json={"url": "https://example.com/tracked"})
    code = r.json()["short_code"]

    client.get(f"/{code}", follow_redirects=False)
    client.get(f"/{code}", follow_redirects=False)

    stats = client.get(f"/api/analytics/{code}")
    assert stats.status_code == 200
    assert stats.json()["total_clicks"] == 2
