"""Core short-code generation & resolution logic."""
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
