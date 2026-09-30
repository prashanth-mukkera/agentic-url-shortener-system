"""Persistence schema for the URL shortener."""
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
