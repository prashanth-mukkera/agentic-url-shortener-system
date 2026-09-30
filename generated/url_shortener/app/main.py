"""
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
