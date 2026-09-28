from datetime import datetime
from pydantic import BaseModel, HttpUrl

class URLCreate(BaseModel):
    original_url: HttpUrl
    custom_alias: str | None = None

class URLResponse(BaseModel):
    original_url: str
    short_code: str
    short_url: str
    created_at: datetime
    click_count: int

    class Config:
        from_attributes = True

class AnalyticsResponse(BaseModel):
    short_code: str
    total_clicks: int
    recent_clicks: list[dict]
