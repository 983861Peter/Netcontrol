# auth/auth_utils.py
"""
Password hashing and JWT token utilities.
Move secret values into environment variables in production.
"""

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os

# Use environment variables for production; default values here for dev
SECRET_KEY = os.getenv("NC_SECRET_KEY", "replace-this-secret-with-env-value")
ALGORITHM = os.getenv("NC_JWT_ALG", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("NC_TOKEN_EXP_MIN", "360"))  # default 6 hours

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_ctx.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_ctx.verify(plain_password, hashed_password)

def create_access_token(subject: str, role: str, expires_delta: timedelta = None):
    to_encode = {"sub": subject, "role": role}
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
