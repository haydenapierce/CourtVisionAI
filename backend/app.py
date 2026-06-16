from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import create_videos_table
from routes.dashboard import router as dashboard_router
from routes.idea_lab import router as idea_lab_router

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

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "CourtVision AI running"
    }