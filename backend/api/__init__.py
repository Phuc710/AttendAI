from fastapi import APIRouter
from . import users, classes, enrollments, sessions, attendance, camera, configs, auth

router = APIRouter()
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(classes.router)
router.include_router(enrollments.router)
router.include_router(sessions.router)
router.include_router(attendance.router)
router.include_router(camera.router)
router.include_router(configs.router)
