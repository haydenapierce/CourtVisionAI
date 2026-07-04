from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import create_videos_table

from routes.dashboard import router as dashboard_router
from routes.idea_lab import router as idea_lab_router

from routes.revenue import router as revenue_router
from routes.revenue_intelligence import router as revenue_intelligence_router
from routes.revenue_forecast import router as revenue_forecast_router

from routes.content_strategy import router as content_strategy_router
from routes.dead_video_recovery import router as dead_video_recovery_router

from routes.studio_breakdowns import router as studio_breakdowns_router
from routes.studio_intelligence import router as studio_intelligence_router

from routes.content_studio import router as content_studio_router
from routes.video_editor import router as video_editor_router

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

create_videos_table()

app.include_router(dashboard_router)
app.include_router(idea_lab_router)

app.include_router(revenue_router)
app.include_router(revenue_intelligence_router)
app.include_router(revenue_forecast_router)

app.include_router(content_strategy_router)
app.include_router(dead_video_recovery_router)

app.include_router(studio_breakdowns_router)
app.include_router(studio_intelligence_router)

app.include_router(content_studio_router)
app.include_router(video_editor_router)


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
            "Studio Breakdowns",
            "Studio Intelligence",
            "Content Studio",
            "Video Editor"
        ]
    }
