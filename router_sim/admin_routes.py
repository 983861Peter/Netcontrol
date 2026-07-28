from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from .models import AuthUser
from .schemas import UserCreate, UserResponse, UserPermissionUpdate
from .auth_utils import hash_password, verify_password
from .db import get_db
from .routes import get_current_user

# ✅ Define the router properly here
user_router = APIRouter(
    prefix="/users",
    tags=["Users"]
)
@user_router.get("/", response_model=List[UserResponse])
def get_all_users(current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fetch all users (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    users = db.query(AuthUser).all()
    return users

@user_router.post("/create", response_model=UserResponse)
def create_user(user_data: UserCreate, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create new user (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    existing = db.query(AuthUser).filter(AuthUser.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_pw = hash_password(user_data.password)
    new_user = AuthUser(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_pw,
        role=user_data.role,
        is_active=True,
        can_add_device=user_data.role == "admin",
        can_delete_device=user_data.role == "admin",
        can_restart_device=user_data.role == "admin",
        can_configure_device=user_data.role == "admin",
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@user_router.put("/{user_id}/permissions", response_model=UserResponse)
def update_permissions(user_id: int, perms: UserPermissionUpdate,
                       current_user: AuthUser = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Update user permissions (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for key, value in perms.dict(exclude_unset=True).items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

#Delete user
@user_router.delete("/{user_id}")
def delete_user(user_id: int, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete user account (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return {"message": f"User '{user.username}' deleted successfully"}

user_router = APIRouter(prefix="/users", tags=["Users"])
