from fastapi import APIRouter
from . import users, groups, enrollments, sessions, attendance, camera, configs, auth, system

router = APIRouter()
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(groups.router)
router.include_router(enrollments.router)
router.include_router(sessions.router)
router.include_router(attendance.router)
router.include_router(camera.router)
router.include_router(configs.router)
router.include_router(system.router)
