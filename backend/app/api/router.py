from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.graph import router as graph_router
from app.api.v1.projects import router as projects_router
from app.api.v1.profiles import router as profiles_router
from app.api.v1.plans import router as plans_router
from app.api.v1.tracking import router as tracking_router
from app.api.v1.replans import router as replans_router
from app.api.v1.search import router as search_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(graph_router, tags=["graph"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(profiles_router, tags=["profiles"])
api_router.include_router(plans_router, tags=["plans"])
api_router.include_router(tracking_router, tags=["tracking"])
api_router.include_router(replans_router, tags=["replans"])
api_router.include_router(search_router, tags=["search"])
