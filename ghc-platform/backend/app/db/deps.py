from collections.abc import Generator

from app.db.base import SessionLocal


def get_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
