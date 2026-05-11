import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import User
from redis_client import redis_client

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _stream_key_hash(stream_key: str) -> str:
    return hashlib.sha256(stream_key.encode("utf-8")).hexdigest()


@router.post("/stream-key/generate")
async def generate_stream_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    old_key_hash = user.stream_key_hash
    new_key = f"pk_live_{secrets.token_hex(12)}"
    new_key_hash = _stream_key_hash(new_key)
    user.stream_key_hash = new_key_hash

    db.commit()

    cache_keys = [f"cache:stream_key:{new_key_hash}"]
    if old_key_hash:
        cache_keys.append(f"cache:stream_key:{old_key_hash}")
    redis_client.delete(*cache_keys)

    return {"stream_key": new_key}
