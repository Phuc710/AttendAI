"""api/auth.py - Admin authentication."""

from hmac import compare_digest

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import ADMIN_PASSWORD

from database import log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn):
    if not compare_digest(body.password, ADMIN_PASSWORD):
        log_event("auth", "Đăng nhập thất bại", "Mật khẩu không chính xác")
        raise HTTPException(status_code=401, detail="Mat khau khong chinh xac")
    log_event("auth", "Đăng nhập quản trị viên thành công", "Session bắt đầu")
    return {"authenticated": True}
