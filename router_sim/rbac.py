# /rbac.py

from fastapi import Depends, HTTPException, Header
from .auth_utils import decode_access_token
from .db import get_db
from .models import User
from typing import Optional
from sqlalchemy.orm import Session

def get_current_user(authorization: str = Header(None), db=Depends(get_db)):
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing auth header")

    try:
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ValueError("Invalid header format")
        token = parts[1]
        
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            raise ValueError("Invalid token payload")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_role(*allowed_roles):
    def wrapper(user=Depends(get_current_user)):
        if not hasattr(user, "role") or user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Not permitted")
        return user
    return wrapper
