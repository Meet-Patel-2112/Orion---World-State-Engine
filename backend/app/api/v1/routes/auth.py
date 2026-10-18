from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import UserLogin, UserRegister, Token, UserResponse
from app.services.profile_service import profile_with_stats, save_profile

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    existing = user_repo.get_by_email(user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
    user = user_repo.create({
        "email": user_in.email.lower().strip(),
        "password_hash": get_password_hash(user_in.password)
    })
    return user

@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(login_data.email)
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Successfully logged out."}


# ---- creator profile and preferences (app/services/profile_service.py)
class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, description="At least 8 characters, like registration.")


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_with_stats(db, current_user)


@router.put("/profile")
def update_profile(body: ProfileUpdate, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    try:
        save_profile(current_user.id, body.display_name, body.preferences)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return profile_with_stats(db, current_user)


@router.post("/password")
def change_password(body: PasswordChange, current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is not correct.")
    current_user.password_hash = get_password_hash(body.new_password)
    db.add(current_user)
    db.commit()
    return {"message": "Password changed."}

