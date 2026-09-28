import base64
import hashlib
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from . import models, schemas, database

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="Enterprise Scalable URL Shortener & Agentic Core",
    description="Scalable URL shortener service with analytics, persistence, and SRE guardrails.",
    version="1.0.0"
)

def generate_short_code(url: str) -> str:
    hash_object = hashlib.sha256(url.encode())
    return base64.urlsafe_b64encode(hash_object.digest()).decode('utf-8')[:6]

@app.post("/api/v1/shorten", response_model=schemas.URLResponse, status_code=status.HTTP_201_CREATED)
def create_short_url(payload: schemas.URLCreate, request: Request, db: Session = Depends(database.get_db)):
    long_url_str = str(payload.original_url)
    
    if payload.custom_alias:
        short_code = payload.custom_alias
        existing = db.query(models.URL).filter(models.URL.short_code == short_code).first()
        if existing:
            raise HTTPException(status_code=400, detail="Custom alias already taken.")
    else:
        short_code = generate_short_code(long_url_str)
        existing = db.query(models.URL).filter(models.URL.short_code == short_code).first()
        if existing and existing.original_url != long_url_str:
            short_code = base64.urlsafe_b64encode(hashlib.sha256((long_url_str + datetime.now().isoformat()).encode()).digest()).decode('utf-8')[:6]

    db_url = db.query(models.URL).filter(models.URL.original_url == long_url_str, models.URL.short_code == short_code).first()
    if not db_url:
        db_url = models.URL(original_url=long_url_str, short_code=short_code)
        db.add(db_url)
        db.commit()
        db.refresh(db_url)

    base_url = str(request.base_url).rstrip("/")
    return {
        "original_url": db_url.original_url,
        "short_code": db_url.short_code,
        "short_url": f"{base_url}/{db_url.short_code}",
        "created_at": db_url.created_at,
        "click_count": db_url.click_count
    }

@app.get("/{short_code}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def redirect_to_url(short_code: str, request: Request, db: Session = Depends(database.get_db)):
    db_url = db.query(models.URL).filter(models.URL.short_code == short_code).first()
    if not db_url:
        raise HTTPException(status_code=404, detail="Short URL not found.")
    
    db_url.click_count += 1
    click_log = models.ClickAnalytics(
        short_code=short_code,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(click_log)
    db.commit()

    return RedirectResponse(url=db_url.original_url, status_code=307)

@app.get("/api/v1/analytics/{short_code}", response_model=schemas.AnalyticsResponse)
def get_analytics(short_code: str, db: Session = Depends(database.get_db)):
    db_url = db.query(models.URL).filter(models.URL.short_code == short_code).first()
    if not db_url:
        raise HTTPException(status_code=404, detail="Short URL not found.")
    
    clicks = db.query(models.ClickAnalytics).filter(models.ClickAnalytics.short_code == short_code).order_by(models.ClickAnalytics.clicked_at.desc()).limit(10).all()
    recent = [{"clicked_at": c.clicked_at, "ip": c.ip_address, "user_agent": c.user_agent} for c in clicks]
    
    return {
        "short_code": short_code,
        "total_clicks": db_url.click_count,
        "recent_clicks": recent
    }

@app.get("/healthz", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "healthy", "service": "url-shortener-ai-ops"}
