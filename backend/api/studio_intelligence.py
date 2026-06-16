from fastapi import APIRouter

router = APIRouter()

# =========================
# VIDEO DATABASE (SIMULATED STUDIO VIEW)
# =========================
@router.get("/studio/videos")
def videos():

    return {
        "videos": [
            {
                "title": "Top 10 LeBron Clutch Moments",
                "views": 120000,
                "revenue": 240,
                "thumbnail": "https://img.youtube.com/vi/demo/hqdefault.jpg"
            },
            {
                "title": "Top 10 Curry 3PT Runs",
                "views": 98000,
                "revenue": 180,
                "thumbnail": "https://img.youtube.com/vi/demo/hqdefault.jpg"
            }
        ]
    }


# =========================
# AI VIRAL IDEA ENGINE
# =========================
@router.get("/studio/ideas")
def ideas():

    return {
        "ideas": [
            {"idea": "Top 10 MJ clutch shots", "score": 99},
            {"idea": "Top 10 underrated NBA legends", "score": 94},
            {"idea": "Top 10 insane dunks ever", "score": 96},
            {"idea": "Top 10 rookie breakout seasons", "score": 91}
        ]
    }


# =========================
# NBA ALL-TIME DATABASE
# =========================
@router.get("/nba/alltime")
def nba():

    return {
        "players": [
            {"name": "Michael Jordan", "score": 100},
            {"name": "LeBron James", "score": 99},
            {"name": "Kobe Bryant", "score": 98},
            {"name": "Stephen Curry", "score": 97},
            {"name": "Shaq", "score": 95}
        ]
    }


# =========================
# AI STRATEGY ENGINE
# =========================
@router.get("/studio/strategy")
def strategy():

    return {
        "best_upload": "Top 10 LeBron Clutch Moments",
        "best_time": "6:00 PM EST",
        "reason": "High engagement window + trending player",
        "avoid": "Low view defensive highlights"
    }


# =========================
# REVENUE AI MODEL
# =========================
@router.get("/studio/revenue")
def revenue():

    return {
        "rpm_estimate": "$3.20 - $7.10",
        "top_earning": [
            "LeBron content",
            "MJ content",
            "Kobe content"
        ],
        "best_format": "Top 10 NBA Legends"
    }