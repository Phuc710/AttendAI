"""api/auth.py - Admin authentication."""

from hmac import compare_digest

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import ADMIN_PASSWORD

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn):
    if not compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Mat khau khong chinh xac")
    return {"authenticated": True}
