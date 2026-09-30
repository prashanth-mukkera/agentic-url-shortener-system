"""
Agent 4 — Engineering Output Generation (code).

Design decision: code for the mandatory deliverable is produced via
*validated deterministic templates* rather than free-form LLM generation.
This is a guardrail — see src/llm/client.py docstring — so the prototype is
100% reproducible and the generated service is guaranteed syntactically valid
before it ever reaches the validation/test stage.

For the brownfield scenario, this module deliberately ships a first patch
with a realistic latent bug (a NameError only triggered once the rate
limiter's window resets), then exposes `repair_brownfield_patch` which the
validation agent calls if tests fail — this is the system's demonstrated
error-recovery path (see agents/validation_agent.py).
"""
from __future__ import annotations
import os
import shutil


# ---------------------------------------------------------------- greenfield

def _f(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


DATABASE_PY = '''"""SQLAlchemy engine/session setup (SQLite for the demo; swap the URL for Postgres in prod)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./shortener.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

MODELS_PY = '''"""Persistence schema for the URL shortener."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class URLMapping(Base):
    __tablename__ = "url_mappings"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(16), unique=True, index=True, nullable=False)
    original_url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    clicks = relationship("ClickEvent", back_populates="mapping", cascade="all, delete-orphan")


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(16), ForeignKey("url_mappings.short_code"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    referrer = Column(String(512), nullable=True)

    mapping = relationship("URLMapping", back_populates="clicks")
'''

SHORTENER_PY = '''"""Core short-code generation & resolution logic."""
import string
import random
from sqlalchemy.orm import Session
from .models import URLMapping

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7


def _generate_code() -> str:
    return "".join(random.choices(ALPHABET, k=CODE_LENGTH))


def create_short_url(db: Session, original_url: str, custom_alias: str | None = None) -> URLMapping:
    if custom_alias:
        existing = db.query(URLMapping).filter(URLMapping.short_code == custom_alias).first()
        if existing:
            raise ValueError(f"Alias '{custom_alias}' is already taken.")
        code = custom_alias
    else:
        # collision-avoidance loop: regenerate on the (rare) hash collision
        for _ in range(5):
            code = _generate_code()
            if not db.query(URLMapping).filter(URLMapping.short_code == code).first():
                break
        else:
            raise RuntimeError("Failed to generate a unique short code after 5 attempts.")

    mapping = URLMapping(short_code=code, original_url=original_url)
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


def resolve_short_code(db: Session, short_code: str) -> URLMapping | None:
    return db.query(URLMapping).filter(URLMapping.short_code == short_code).first()
'''

ANALYTICS_PY = '''"""Click tracking & analytics aggregation."""
from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import ClickEvent


def record_click(db: Session, short_code: str, referrer: str | None = None) -> ClickEvent:
    event = ClickEvent(short_code=short_code, referrer=referrer)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_analytics(db: Session, short_code: str) -> dict:
    total = db.query(func.count(ClickEvent.id)).filter(ClickEvent.short_code == short_code).scalar()
    recent = (
        db.query(ClickEvent)
        .filter(ClickEvent.short_code == short_code)
        .order_by(ClickEvent.timestamp.desc())
        .limit(20)
        .all()
    )
    return {
        "short_code": short_code,
        "total_clicks": total or 0,
        "recent_clicks": [
            {"timestamp": e.timestamp.isoformat(), "referrer": e.referrer} for e in recent
        ],
    }
'''

MAIN_PY = '''"""
FastAPI entrypoint for the URL shortener service.

Endpoints:
  POST /api/shorten            -> create a short URL
  GET  /{short_code}           -> redirect to the original URL (records a click)
  GET  /api/analytics/{code}   -> usage analytics for a short code
  GET  /api/health             -> liveness probe
"""
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from . import shortener, analytics

Base.metadata.create_all(bind=engine)

app = FastAPI(title="URL Shortener Service", version="1.0.0")


class ShortenRequest(BaseModel):
    url: HttpUrl
    custom_alias: str | None = None


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/shorten", response_model=ShortenResponse, status_code=201)
def shorten(req: ShortenRequest, db: Session = Depends(get_db)):
    try:
        mapping = shortener.create_short_url(db, str(req.url), req.custom_alias)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ShortenResponse(
        short_code=mapping.short_code,
        short_url=f"/{mapping.short_code}",
        original_url=mapping.original_url,
    )


@app.get("/api/analytics/{short_code}")
def get_analytics(short_code: str, db: Session = Depends(get_db)):
    mapping = shortener.resolve_short_code(db, short_code)
    if not mapping:
        raise HTTPException(status_code=404, detail="Short code not found")
    return analytics.get_analytics(db, short_code)


@app.get("/{short_code}")
def redirect(short_code: str, request: Request, db: Session = Depends(get_db)):
    mapping = shortener.resolve_short_code(db, short_code)
    if not mapping:
        raise HTTPException(status_code=404, detail="Short code not found")
    analytics.record_click(db, short_code, referrer=request.headers.get("referer"))
    return RedirectResponse(url=mapping.original_url, status_code=307)
'''

TEST_SHORTENER_PY = '''"""Unit + integration tests for the URL shortener service."""
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
'''

REQUIREMENTS_TXT = "fastapi>=0.110\nuvicorn>=0.29\nsqlalchemy>=2.0\npydantic>=2.6\nhttpx>=0.27\npytest>=8.0\n"

APP_README = """# URL Shortener Service (generated artifact)

Run locally:

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:

```
pytest -q
```

## Endpoints
- `POST /api/shorten` `{"url": "...", "custom_alias": "optional"}`
- `GET /{short_code}` -> 307 redirect (records a click)
- `GET /api/analytics/{short_code}` -> click stats
- `GET /api/health`
"""


def write_greenfield_project(project_dir: str) -> list[str]:
    """
    Wipe any prior generated project first. This makes a greenfield run
    idempotent and order-independent — e.g. running `brownfield` and then
    re-running `greenfield` in the same session must not leave brownfield
    artifacts (like tests/test_rate_limit.py, tests/conftest.py, or the
    rate-limiter block previously spliced into app/main.py) lying around to
    fail against the freshly generated, unpatched service.
    """
    if os.path.isdir(project_dir):
        shutil.rmtree(project_dir)

    files = {
        os.path.join(project_dir, "app", "__init__.py"): "",
        os.path.join(project_dir, "app", "database.py"): DATABASE_PY,
        os.path.join(project_dir, "app", "models.py"): MODELS_PY,
        os.path.join(project_dir, "app", "shortener.py"): SHORTENER_PY,
        os.path.join(project_dir, "app", "analytics.py"): ANALYTICS_PY,
        os.path.join(project_dir, "app", "main.py"): MAIN_PY,
        os.path.join(project_dir, "tests", "test_shortener.py"): TEST_SHORTENER_PY,
        os.path.join(project_dir, "requirements.txt"): REQUIREMENTS_TXT,
        os.path.join(project_dir, "README.md"): APP_README,
    }
    for path, content in files.items():
        _f(path, content)
    return list(files.keys())


# ---------------------------------------------------------------- brownfield
#
# Requirement demoed: "Add basic rate limiting to /api/shorten to prevent
# abuse, and capture the referrer header in click analytics."
# (analytics/referrer capture already exists in the greenfield build above —
#  the realistic incremental delta here is the rate limiter.)

RATE_LIMIT_BUGGY = '''
# --- brownfield patch: basic in-memory rate limiting on /api/shorten -------
import time
from collections import defaultdict
from fastapi import Request

RATE_LIMIT_MAX = 5          # requests
RATE_LIMIT_WINDOW = 60      # seconds
_hits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str):
    now = time.time()
    window = _hits[client_ip]
    # NOTE: bug — typo'd constant name means this raises NameError once a
    # client's request list needs pruning (i.e. on their 2nd request), which
    # is exactly the kind of latent bug static analysis alone won't catch
    # but a test exercising the endpoint twice will.
    window[:] = [t for t in window if now - t < RATE_LIMIT_WINDW]
    if len(window) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    window.append(now)
'''

RATE_LIMIT_FIXED = '''
# --- brownfield patch: basic in-memory rate limiting on /api/shorten -------
import time
from collections import defaultdict
from fastapi import Request

RATE_LIMIT_MAX = 5          # requests
RATE_LIMIT_WINDOW = 60      # seconds
_hits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str):
    now = time.time()
    window = _hits[client_ip]
    window[:] = [t for t in window if now - t < RATE_LIMIT_WINDOW]
    if len(window) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    window.append(now)
'''

SHORTEN_ROUTE_OLD = '''@app.post("/api/shorten", response_model=ShortenResponse, status_code=201)
def shorten(req: ShortenRequest, db: Session = Depends(get_db)):
    try:'''

SHORTEN_ROUTE_NEW = '''@app.post("/api/shorten", response_model=ShortenResponse, status_code=201)
def shorten(req: ShortenRequest, request: Request, db: Session = Depends(get_db)):
    _check_rate_limit(request.client.host if request.client else "unknown")
    try:'''


def _patch_main(project_dir: str, rate_limit_block: str):
    main_path = os.path.join(project_dir, "app", "main.py")
    with open(main_path) as f:
        content = f.read()

    if "_check_rate_limit" in content:
        # already patched once (retry path) — replace just the helper block
        start = content.index("# --- brownfield patch")
        end = content.index("app = FastAPI")
        content = content[:start] + rate_limit_block.strip("\n") + "\n\n\n" + content[end:]
    else:
        insert_at = content.index("app = FastAPI")
        content = content[:insert_at] + rate_limit_block.strip("\n") + "\n\n\n" + content[insert_at:]
        content = content.replace(SHORTEN_ROUTE_OLD, SHORTEN_ROUTE_NEW)

    with open(main_path, "w") as f:
        f.write(content)


def apply_brownfield_patch(project_dir: str) -> list[str]:
    """First attempt — ships with the latent bug described above."""
    _patch_main(project_dir, RATE_LIMIT_BUGGY)
    return [os.path.join(project_dir, "app", "main.py")]


def repair_brownfield_patch(project_dir: str) -> list[str]:
    """Called by the validation agent when the first patch fails tests."""
    _patch_main(project_dir, RATE_LIMIT_FIXED)
    return [os.path.join(project_dir, "app", "main.py")]


def write_conftest(project_dir: str):
    """
    Regression-test hygiene: the in-memory rate limiter is process-global
    state, so without a reset it leaks quota usage across test functions
    (a second, independent bug the validation run surfaced beyond the
    injected NameError — left in deliberately and documented here rather
    than quietly special-cased away, because it's a realistic thing a real
    review would catch).
    """
    path = os.path.join(project_dir, "tests", "conftest.py")
    content = '''import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """Rate limiter state is process-global; reset it between tests so test
    order/count doesn't leak quota usage across unrelated test functions."""
    try:
        from app.main import _hits
        _hits.clear()
    except ImportError:
        pass
    yield
'''
    _f(path, content)
    return path


def add_rate_limit_test(project_dir: str):
    test_path = os.path.join(project_dir, "tests", "test_rate_limit.py")
    content = '''import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

client = TestClient(app)


def test_rate_limit_kicks_in():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    last = None
    for i in range(7):
        last = client.post("/api/shorten", json={"url": f"https://example.com/{i}"})
    assert last.status_code == 429
'''
    _f(test_path, content)
    return test_path


# ---------------------------------------------------------------- task hooks

def run_greenfield(task, context):
    project_dir = os.path.join(context.workspace_dir, "url_shortener")
    files = write_greenfield_project(project_dir)
    context.set("project_dir", project_dir)
    context.set("generated_files", files)
    context.log(f"Generated {len(files)} files for URL shortener service at {project_dir}")
    return {"project_dir": project_dir, "files": files}


def run_brownfield(task, context):
    project_dir = context.get("project_dir")
    if not project_dir:
        raise RuntimeError("Brownfield codegen requires an existing project_dir in context.")
    changed = apply_brownfield_patch(project_dir)
    test_path = add_rate_limit_test(project_dir)
    conftest_path = write_conftest(project_dir)
    context.set("brownfield_patch_files", changed + [test_path, conftest_path])
    context.set("brownfield_attempt", 1)
    context.log(f"Applied brownfield patch to {changed} and added {test_path}")
    return {"changed_files": changed, "new_test": test_path}
