from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base


def _engine_connect_args() -> dict:
    if settings.SHOPIFY_APP_DB_URL.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine: Engine = create_engine(
    settings.SHOPIFY_APP_DB_URL,
    future=True,
    connect_args=_engine_connect_args(),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _ensure_nullable_text_column(
    *,
    table_name: str,
    column_name: str,
) -> None:
    with engine.begin() as connection:
        existing_columns = {
            str(column.get("name", "")).strip().lower()
            for column in inspect(connection).get_columns(table_name)
        }
        if column_name.lower() in existing_columns:
            return
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT")
        )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_nullable_text_column(
        table_name="shop_installations",
        column_name="app_api_key",
    )
    _ensure_nullable_text_column(
        table_name="shop_installations",
        column_name="app_api_secret",
    )
    _ensure_nullable_text_column(
        table_name="oauth_states",
        column_name="app_api_key",
    )
    _ensure_nullable_text_column(
        table_name="oauth_states",
        column_name="app_api_secret",
    )


def get_session():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
