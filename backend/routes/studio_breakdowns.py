from fastapi import APIRouter
from pydantic import BaseModel
from database.db import create_connection

router = APIRouter()


class StudioBreakdownEntry(BaseModel):
    breakdown_type: str
    scope: str = "channel"
    video_id: str = ""
    title: str = ""
    period_type: str = "30d"
    item_name: str = ""
    views: int = 0
    watch_time_hours: float = 0
    average_view_duration: str = ""
    impressions: int = 0
    ctr: float = 0
    estimated_revenue: float = 0
    rpm: float = 0
    cpm: float = 0
    subscribers: int = 0
    percentage: float = 0
    extra_metric_name: str = ""
    extra_metric_value: float = 0
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


def ensure_studio_breakdowns_table():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS studio_breakdowns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        breakdown_type TEXT DEFAULT '',
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        item_name TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        average_view_duration TEXT DEFAULT '',
        impressions INTEGER DEFAULT 0,
        ctr REAL DEFAULT 0,
        estimated_revenue REAL DEFAULT 0,
        rpm REAL DEFAULT 0,
        cpm REAL DEFAULT 0,
        subscribers INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        extra_metric_name TEXT DEFAULT '',
        extra_metric_value REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    connection.commit()
    connection.close()


def row_to_dict(row):
    return dict(row)


@router.get("/studio-breakdowns/types")
def studio_breakdown_types():
    return {
        "types": [
            "revenue_source",
            "ad_type",
            "transaction_type",
            "organic_paid_traffic",
            "country",
            "city",
            "viewer_age",
            "viewer_gender",
            "new_returning_viewers",
            "audience_watch_behavior",
            "subscription_status",
            "subscription_source",
            "youtube_product",
            "device_type",
            "operating_system",
            "subtitles_cc",
            "video_info_language",
            "translation_use",
            "end_screen_element",
            "end_screen_element_type",
            "card",
            "card_type",
            "playback_location",
            "player_type",
            "sharing_service",
            "playlist",
            "community_post"
        ]
    }


@router.get("/studio-breakdowns/summary")
def studio_breakdowns_summary():
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        COUNT(*) as total_entries,
        SUM(views) as total_views,
        SUM(watch_time_hours) as total_watch_time_hours,
        SUM(impressions) as total_impressions,
        SUM(estimated_revenue) as total_estimated_revenue,
        SUM(subscribers) as total_subscribers
    FROM studio_breakdowns
    """)

    totals = cursor.fetchone()

    cursor.execute("""
    SELECT
        breakdown_type,
        COUNT(*) as entries,
        SUM(views) as views,
        SUM(watch_time_hours) as watch_time_hours,
        SUM(estimated_revenue) as estimated_revenue
    FROM studio_breakdowns
    GROUP BY breakdown_type
    ORDER BY views DESC
    """)

    by_type = [row_to_dict(row) for row in cursor.fetchall()]

    connection.close()

    return {
        "summary": {
            "total_entries": totals["total_entries"] or 0,
            "total_views": totals["total_views"] or 0,
            "total_watch_time_hours": round(totals["total_watch_time_hours"] or 0, 2),
            "total_impressions": totals["total_impressions"] or 0,
            "total_estimated_revenue": round(totals["total_estimated_revenue"] or 0, 2),
            "total_subscribers": totals["total_subscribers"] or 0,
            "by_type": by_type
        }
    }


@router.get("/studio-breakdowns")
def get_studio_breakdowns():
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM studio_breakdowns
    ORDER BY created_at DESC, id DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    return {
        "studio_breakdowns": [row_to_dict(row) for row in rows]
    }


@router.get("/studio-breakdowns/{breakdown_type}")
def get_studio_breakdowns_by_type(breakdown_type: str):
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM studio_breakdowns
    WHERE breakdown_type=?
    ORDER BY views DESC, created_at DESC
    """, (breakdown_type,))

    rows = cursor.fetchall()
    connection.close()

    return {
        "breakdown_type": breakdown_type,
        "studio_breakdowns": [row_to_dict(row) for row in rows]
    }


@router.post("/studio-breakdowns")
def create_studio_breakdown(entry: StudioBreakdownEntry):
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO studio_breakdowns (
        breakdown_type,
        scope,
        video_id,
        title,
        period_type,
        item_name,
        views,
        watch_time_hours,
        average_view_duration,
        impressions,
        ctr,
        estimated_revenue,
        rpm,
        cpm,
        subscribers,
        percentage,
        extra_metric_name,
        extra_metric_value,
        start_date,
        end_date,
        notes,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.breakdown_type,
        entry.scope,
        entry.video_id,
        entry.title,
        entry.period_type,
        entry.item_name,
        int(entry.views or 0),
        float(entry.watch_time_hours or 0),
        entry.average_view_duration,
        int(entry.impressions or 0),
        float(entry.ctr or 0),
        float(entry.estimated_revenue or 0),
        float(entry.rpm or 0),
        float(entry.cpm or 0),
        int(entry.subscribers or 0),
        float(entry.percentage or 0),
        entry.extra_metric_name,
        float(entry.extra_metric_value or 0),
        entry.start_date,
        entry.end_date,
        entry.notes
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()

    return {
        "message": "Studio breakdown saved",
        "id": new_id
    }


@router.delete("/studio-breakdowns/{entry_id}")
def delete_studio_breakdown(entry_id: int):
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("DELETE FROM studio_breakdowns WHERE id=?", (entry_id,))

    connection.commit()
    connection.close()

    return {
        "message": "Studio breakdown deleted",
        "id": entry_id
    }