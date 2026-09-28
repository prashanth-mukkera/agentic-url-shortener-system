from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from .database import Base

class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, index=True)
    original_url = Column(Text, nullable=False)
    short_code = Column(String(10), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    click_count = Column(Integer, default=0)

class ClickAnalytics(Base):
    __tablename__ = "click_analytics"

    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(10), index=True, nullable=False)
    clicked_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
