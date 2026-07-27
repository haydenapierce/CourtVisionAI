from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from fastapi.exceptions import RequestValidationError

from database.db import create_videos_table

from routes.dashboard import router as dashboard_router
from routes.idea_lab import router as idea_lab_router

from routes.revenue import router as revenue_router
from routes.revenue_intelligence import router as revenue_intelligence_router
from routes.revenue_forecast import router as revenue_forecast_router

from routes.content_strategy import router as content_strategy_router
from routes.dead_video_recovery import router as dead_video_recovery_router
from routes.end_screen_optimizer import router as end_screen_optimizer_router

from routes.studio_breakdowns import router as studio_breakdowns_router
from routes.studio_intelligence import router as studio_intelligence_router

from routes.content_studio import router as content_studio_router
from routes.video_editor import router as video_editor_router
from routes.community_automation import router as community_automation_router
from routes.thumbnail_builder import router as thumbnail_builder_router
from routes.clip_finder import router as clip_finder_router

# Initialize the database once before FastAPI begins accepting requests.
# This restores the reliable startup behavior and removes the background
# /health gate that caused the frontend to remain at 1%.
create_videos_table()

app = FastAPI(title="CourtVision AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dashboard_router)
app.include_router(idea_lab_router)

app.include_router(revenue_router)
app.include_router(revenue_intelligence_router)
app.include_router(revenue_forecast_router)

app.include_router(content_strategy_router)
app.include_router(dead_video_recovery_router)
app.include_router(end_screen_optimizer_router)

app.include_router(studio_breakdowns_router)
app.include_router(studio_intelligence_router)

app.include_router(content_studio_router)
app.include_router(video_editor_router)
app.include_router(community_automation_router)
app.include_router(thumbnail_builder_router)
app.include_router(clip_finder_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "ok": False,
        "code": "request_validation_failed",
        "message": "CourtVision could not understand one or more submitted fields.",
        "resolution": "Review the highlighted form fields and try again.",
        "technical_detail": str(exc)
    })


@app.exception_handler(Exception)
async def courtvision_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={
        "ok": False,
        "code": "backend_error",
        "message": "CourtVision encountered a backend error.",
        "resolution": "Check the backend terminal for the exact failing file, then retry the action.",
        "technical_detail": str(exc)
    })



@app.get("/startup/readiness")
def startup_readiness():
    """Lightweight readiness summary; never performs remote API refreshes."""
    base_dir = Path(__file__).resolve().parent
    clip_projects = base_dir / "data" / "clip_finder" / "projects"
    return {
        "ok": True,
        "data_source": "saved_database_and_local_project_state",
        "database_ready": True,
        "features": {
            "dashboard": True,
            "clip_finder": True,
            "courtvision_editor": True,
            "video_editor": True,
            "video_projects": True,
            "thumbnail_builder": True,
            "idea_lab": True,
            "decision_engine": True,
            "community_automation": True,
            "render_service": True,
            "upload_workflow": True,
        },
        "clip_finder": {
            "project_store_ready": clip_projects.exists(),
            "saved_project_count": len(list(clip_projects.glob("*.json"))) if clip_projects.exists() else 0,
        },
        "background_refresh_required": True,
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "CourtVision AI running",
        "data_source": "youtube_analytics_api_revenue_tracker",
        "manual_revenue_enabled": False,
        "modules": [
            "Dashboard",
            "Idea Lab",
            "Revenue Tracker",
            "Revenue Intelligence",
            "Revenue Forecast",
            "Strategy Center",
            "Dead Video Recovery",
            "End Screen Optimizer",
            "Studio Breakdowns",
            "Studio Intelligence",
            "Content Studio",
            "Video Editor",
            "Community Automation"
        ]
    }
