import hashlib

import psycopg2
from app.core.config import settings


def _stream_key_hash(stream_key: str) -> str:
    return hashlib.sha256(stream_key.encode("utf-8")).hexdigest()


def get_conn():
    if settings.POSTGRES_URL:
        return psycopg2.connect(settings.POSTGRES_URL)

    return psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
    )


def get_user_by_stream_key(stream_key: str) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE stream_key_hash = %s",
                (_stream_key_hash(stream_key),),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("invalid stream key")
            return row[0]
    finally:
        conn.close()
