import sqlite3
import os

DB_FOLDER = "database"
DATABASE_NAME = os.path.join(DB_FOLDER, "courtvision.db")

_SAVED_VIDEOS_CACHE = None
_SAVED_VIDEOS_CACHE_COUNT = None


def clear_runtime_caches():
    global _SAVED_VIDEOS_CACHE, _SAVED_VIDEOS_CACHE_COUNT
    _SAVED_VIDEOS_CACHE = None
    _SAVED_VIDEOS_CACHE_COUNT = None


def create_connection():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    connection = sqlite3.connect(DATABASE_NAME, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=60000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("PRAGMA cache_size=-20000")
    return connection


def add_column_if_missing(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def create_revenue_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_type TEXT,
        amount REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT,
        amount REAL DEFAULT 0,
        views INTEGER DEFAULT 0,
        rpm REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)



def create_youtube_analytics_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        analytics_date TEXT NOT NULL,
        views INTEGER DEFAULT 0,
        estimated_revenue REAL DEFAULT 0,
        estimated_minutes_watched REAL DEFAULT 0,
        rpm REAL DEFAULT 0,
        source TEXT DEFAULT 'youtube_analytics_api',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, analytics_date)
    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_period (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT 'lifetime',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        estimated_revenue REAL DEFAULT 0,
        estimated_minutes_watched REAL DEFAULT 0,
        rpm REAL DEFAULT 0,
        source TEXT DEFAULT 'youtube_analytics_api',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, period_type)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_type TEXT DEFAULT 'manual',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        channel_rows INTEGER DEFAULT 0,
        video_rows INTEGER DEFAULT 0,
        status TEXT DEFAULT '',
        message TEXT DEFAULT '',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)


def create_manual_analytics_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_video_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '7d',
        impressions INTEGER DEFAULT 0,
        ctr REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        average_view_duration TEXT DEFAULT '',
        average_percentage_viewed REAL DEFAULT 0,
        subscribers_gained INTEGER DEFAULT 0,
        subscribers_lost INTEGER DEFAULT 0,
        returning_viewers INTEGER DEFAULT 0,
        new_viewers INTEGER DEFAULT 0,
        end_screen_clicks INTEGER DEFAULT 0,
        playlist_starts INTEGER DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_audience_demographics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        country TEXT DEFAULT '',
        gender TEXT DEFAULT '',
        age_range TEXT DEFAULT '',
        percentage REAL DEFAULT 0,
        views INTEGER DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_traffic_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        source TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        average_view_duration TEXT DEFAULT '',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_device_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        device_type TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)



def create_performance_indexes(cursor):
    """
    Indexes for startup/dashboard/revenue reads.

    These do not change any program output. They only make the same queries
    faster and reduce how long SQLite stays busy during app startup.
    """
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_videos_video_id ON videos(video_id)",
        "CREATE INDEX IF NOT EXISTS idx_videos_views ON videos(views DESC)",
        "CREATE INDEX IF NOT EXISTS idx_videos_player ON videos(player_name)",
        "CREATE INDEX IF NOT EXISTS idx_videos_content_type ON videos(content_type)",
        "CREATE INDEX IF NOT EXISTS idx_videos_synced_at ON videos(synced_at)",

        "CREATE INDEX IF NOT EXISTS idx_ytr_period_video_period ON youtube_revenue_period(video_id, period_type)",
        "CREATE INDEX IF NOT EXISTS idx_ytr_period_period ON youtube_revenue_period(period_type)",
        "CREATE INDEX IF NOT EXISTS idx_ytr_period_revenue ON youtube_revenue_period(estimated_revenue DESC)",
        "CREATE INDEX IF NOT EXISTS idx_ytr_period_synced ON youtube_revenue_period(synced_at)",

        "CREATE INDEX IF NOT EXISTS idx_ytr_daily_video_date ON youtube_revenue_daily(video_id, analytics_date)",
        "CREATE INDEX IF NOT EXISTS idx_ytr_sync_log_synced ON youtube_revenue_sync_log(synced_at DESC)",

        "CREATE INDEX IF NOT EXISTS idx_channel_revenue_period ON channel_revenue(period_type)",
        "CREATE INDEX IF NOT EXISTS idx_video_revenue_video_period ON video_revenue(video_id, period_type)",
        "CREATE INDEX IF NOT EXISTS idx_video_revenue_period ON video_revenue(period_type)"
    ]

    for statement in indexes:
        try:
            cursor.execute(statement)
        except Exception:
            pass


SCHEMA_VERSION = "2026_06_fast_startup_v3"


def schema_is_initialized():
    """
    Fast startup guard.

    Once the database has all CourtVision tables/columns/indexes, future backend
    restarts do not need to run dozens of PRAGMA table_info / ALTER checks.
    """
    if not os.path.exists(DATABASE_NAME):
        return False

    connection = create_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
        """)

        cursor.execute("SELECT value FROM app_meta WHERE key='schema_version'")
        row = cursor.fetchone()
        connection.close()

        return bool(row and row["value"] == SCHEMA_VERSION)
    except Exception:
        connection.close()
        return False


def mark_schema_initialized(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT DEFAULT ''
    )
    """)
    cursor.execute("""
    INSERT INTO app_meta (key, value)
    VALUES ('schema_version', ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (SCHEMA_VERSION,))

def create_videos_table():
    if schema_is_initialized():
        return

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        video_id TEXT UNIQUE,
        published TEXT
    )
    """)

    add_column_if_missing(cursor, "videos", "views", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "likes", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "comments", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "thumbnail", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "estimated_revenue", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "estimated_rpm", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_estimated_revenue", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_estimated_rpm", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_revenue_synced_at", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "content_type", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "player_name", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "title_length", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "upload_year", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "ai_score", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "synced_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

    create_revenue_tables(cursor)
    create_youtube_analytics_tables(cursor)
    create_manual_analytics_tables(cursor)

    connection.commit()
    connection.close()


def save_video(
    title,
    video_id,
    published,
    views=0,
    likes=0,
    comments=0,
    thumbnail="",
    estimated_revenue=0,
    estimated_rpm=0,
    content_type="",
    player_name="",
    title_length=0,
    upload_year=0,
    ai_score=0
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO videos (
        title, video_id, published, views, likes, comments, thumbnail,
        estimated_revenue, estimated_rpm, content_type, player_name,
        title_length, upload_year, ai_score, synced_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(video_id) DO UPDATE SET
        title=excluded.title,
        published=excluded.published,
        views=excluded.views,
        likes=excluded.likes,
        comments=excluded.comments,
        thumbnail=excluded.thumbnail,
        estimated_revenue=excluded.estimated_revenue,
        estimated_rpm=excluded.estimated_rpm,
        content_type=excluded.content_type,
        player_name=excluded.player_name,
        title_length=excluded.title_length,
        upload_year=excluded.upload_year,
        ai_score=excluded.ai_score,
        synced_at=CURRENT_TIMESTAMP
    """, (
        title, video_id, published, views, likes, comments, thumbnail,
        estimated_revenue, estimated_rpm, content_type, player_name,
        title_length, upload_year, ai_score
    ))

    connection.commit()
    connection.close()



def save_videos_bulk(video_rows):
    """
    Saves synced YouTube video rows in one transaction.

    This replaces hundreds of open/commit/close cycles during startup sync with
    one SQLite transaction. Output data is identical to save_video().
    """
    rows = list(video_rows or [])

    if not rows:
        return 0

    connection = create_connection()
    cursor = connection.cursor()

    payload = []

    for row in rows:
        payload.append((
            row.get("title", ""),
            row.get("video_id", ""),
            row.get("published", ""),
            int(row.get("views") or 0),
            int(row.get("likes") or 0),
            int(row.get("comments") or 0),
            row.get("thumbnail", ""),
            float(row.get("estimated_revenue") or 0),
            float(row.get("estimated_rpm") or 0),
            row.get("content_type", ""),
            row.get("player_name", ""),
            int(row.get("title_length") or 0),
            int(row.get("upload_year") or 0),
            float(row.get("ai_score") or 0)
        ))

    cursor.executemany("""
    INSERT INTO videos (
        title, video_id, published, views, likes, comments, thumbnail,
        estimated_revenue, estimated_rpm, content_type, player_name,
        title_length, upload_year, ai_score, synced_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(video_id) DO UPDATE SET
        title=excluded.title,
        published=excluded.published,
        views=excluded.views,
        likes=excluded.likes,
        comments=excluded.comments,
        thumbnail=excluded.thumbnail,
        estimated_revenue=excluded.estimated_revenue,
        estimated_rpm=excluded.estimated_rpm,
        content_type=excluded.content_type,
        player_name=excluded.player_name,
        title_length=excluded.title_length,
        upload_year=excluded.upload_year,
        ai_score=excluded.ai_score,
        synced_at=CURRENT_TIMESTAMP
    """, payload)

    connection.commit()
    connection.close()
    clear_runtime_caches()

    return len(payload)

def get_saved_videos():
    global _SAVED_VIDEOS_CACHE, _SAVED_VIDEOS_CACHE_COUNT

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) as total_count, MAX(synced_at) as latest_sync FROM videos")
    info = cursor.fetchone()
    cache_key = (
        int(info["total_count"] or 0) if info else 0,
        info["latest_sync"] if info else ""
    )

    if _SAVED_VIDEOS_CACHE is not None and _SAVED_VIDEOS_CACHE_COUNT == cache_key:
        connection.close()
        return [dict(row) for row in _SAVED_VIDEOS_CACHE]

    cursor.execute("SELECT * FROM videos ORDER BY views DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    _SAVED_VIDEOS_CACHE = rows
    _SAVED_VIDEOS_CACHE_COUNT = cache_key

    return [dict(row) for row in rows]


def get_latest_video_sync_info():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        COUNT(*) as video_count,
        MAX(synced_at) as latest_video_sync,
        SUM(views) as total_views
    FROM videos
    """)

    row = cursor.fetchone()
    connection.close()

    return {
        "video_count": int(row["video_count"] or 0) if row else 0,
        "latest_video_sync": row["latest_video_sync"] if row else "",
        "total_views": int(row["total_views"] or 0) if row else 0
    }


def clear_videos():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM videos")
    connection.commit()
    connection.close()


def get_channel_totals():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        COUNT(*) as total_videos,
        SUM(views) as total_views,
        SUM(likes) as total_likes,
        SUM(comments) as total_comments,
        AVG(views) as average_views
    FROM videos
    """)

    row = cursor.fetchone()
    connection.close()

    api_revenue = get_youtube_channel_period("lifetime").get("estimated_revenue", 0) if youtube_rows_exist() else 0

    return {
        "total_videos": row["total_videos"] or 0,
        "total_views": row["total_views"] or 0,
        "total_likes": row["total_likes"] or 0,
        "total_comments": row["total_comments"] or 0,
        "average_views": int(row["average_views"] or 0),
        "estimated_revenue": api_revenue
    }


def get_top_videos(limit=10):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM videos
    ORDER BY views DESC
    LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]


def save_channel_revenue(period_type, amount, start_date="", end_date="", notes=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO channel_revenue (
        period_type, amount, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (period_type, float(amount or 0), start_date, end_date, notes))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_channel_revenue(entry_id, period_type, amount, start_date="", end_date="", notes=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    UPDATE channel_revenue
    SET period_type=?, amount=?, start_date=?, end_date=?, notes=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, (period_type, float(amount or 0), start_date, end_date, notes, entry_id))

    connection.commit()
    connection.close()


def delete_channel_revenue(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM channel_revenue WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_channel_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM channel_revenue ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def save_video_revenue(
    video_id="",
    title="",
    period_type="lifetime",
    amount=0,
    views=0,
    rpm=0,
    start_date="",
    end_date="",
    notes=""
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO video_revenue (
        video_id, title, period_type, amount, views, rpm,
        start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        video_id, title, period_type, float(amount or 0), int(views or 0),
        float(rpm or 0), start_date, end_date, notes
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_video_revenue(
    entry_id,
    video_id="",
    title="",
    period_type="lifetime",
    amount=0,
    views=0,
    rpm=0,
    start_date="",
    end_date="",
    notes=""
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    UPDATE video_revenue
    SET video_id=?, title=?, period_type=?, amount=?, views=?, rpm=?,
        start_date=?, end_date=?, notes=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, (
        video_id, title, period_type, float(amount or 0), int(views or 0),
        float(rpm or 0), start_date, end_date, notes, entry_id
    ))

    connection.commit()
    connection.close()


def delete_video_revenue(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM video_revenue WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_video_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM video_revenue ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def normalize_period_type(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


def best_revenue_total(entries):
    """
    Prevents double counting.
    Lifetime is the true total.
    If lifetime does not exist, use the biggest available period.
    """
    priority = ["lifetime", "365d", "90d", "28d", "7d"]

    by_period = {}

    for entry in entries:
        period = normalize_period_type(entry.get("period_type"))
        by_period[period] = by_period.get(period, 0) + float(entry.get("amount") or 0)

    for period in priority:
        if period in by_period:
            return round(by_period[period], 2)

    return 0


def get_manual_revenue_summary():
    """
    API-only compatibility wrapper.

    Older route files may still call this function name, but it no longer reads
    hand-entered revenue. It returns synced YouTube Analytics / Revenue Tracker
    data only. If there are no synced API rows yet, it returns empty zero values.
    """
    if youtube_rows_exist():
        return get_youtube_revenue_summary()

    return {
        "channel_revenue_entries": 0,
        "video_revenue_entries": 0,
        "total_channel_manual_revenue": 0,
        "total_video_manual_revenue": 0,
        "total_channel_youtube_revenue": 0,
        "total_video_youtube_revenue": 0,
        "channel_by_period": {},
        "video_by_period": {},
        "channel_views_by_period": {},
        "video_views_by_period": {},
        "channel_rpm_by_period": {},
        "video_rpm_by_period": {},
        "data_source": "youtube_analytics_api_only_no_rows_yet"
    }


def save_manual_video_analytics(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_video_analytics (
        video_id, title, period_type, impressions, ctr, watch_time_hours,
        average_view_duration, average_percentage_viewed, subscribers_gained,
        subscribers_lost, returning_viewers, new_viewers, end_screen_clicks,
        playlist_starts, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "7d"),
        int(entry.get("impressions") or 0),
        float(entry.get("ctr") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("average_view_duration", ""),
        float(entry.get("average_percentage_viewed") or 0),
        int(entry.get("subscribers_gained") or 0),
        int(entry.get("subscribers_lost") or 0),
        int(entry.get("returning_viewers") or 0),
        int(entry.get("new_viewers") or 0),
        int(entry.get("end_screen_clicks") or 0),
        int(entry.get("playlist_starts") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_video_analytics_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_video_analytics ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_video_analytics(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_video_analytics WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_audience_demographic(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_audience_demographics (
        scope, video_id, title, period_type, country, gender, age_range,
        percentage, views, watch_time_hours, start_date, end_date, notes,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("country", ""),
        entry.get("gender", ""),
        entry.get("age_range", ""),
        float(entry.get("percentage") or 0),
        int(entry.get("views") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_audience_demographic_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_audience_demographics ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_audience_demographic(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_audience_demographics WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_traffic_source(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_traffic_sources (
        scope, video_id, title, period_type, source, views, percentage,
        watch_time_hours, average_view_duration, start_date, end_date, notes,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("source", ""),
        int(entry.get("views") or 0),
        float(entry.get("percentage") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("average_view_duration", ""),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_traffic_source_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_traffic_sources ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_traffic_source(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_traffic_sources WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_device_stat(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_device_stats (
        scope, video_id, title, period_type, device_type, views, percentage,
        watch_time_hours, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("device_type", ""),
        int(entry.get("views") or 0),
        float(entry.get("percentage") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_device_stat_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_device_stats ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_device_stat(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_device_stats WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_manual_analytics_summary():
    video_entries = get_manual_video_analytics_entries()
    audience_entries = get_manual_audience_demographic_entries()
    traffic_entries = get_manual_traffic_source_entries()
    device_entries = get_manual_device_stat_entries()

    total_impressions = sum(int(e.get("impressions") or 0) for e in video_entries)
    total_watch_time = sum(float(e.get("watch_time_hours") or 0) for e in video_entries)
    total_subs_gained = sum(int(e.get("subscribers_gained") or 0) for e in video_entries)
    total_end_screen_clicks = sum(int(e.get("end_screen_clicks") or 0) for e in video_entries)

    ctr_values = [
        float(e.get("ctr") or 0)
        for e in video_entries
        if float(e.get("ctr") or 0) > 0
    ]

    average_ctr = round(sum(ctr_values) / len(ctr_values), 2) if ctr_values else 0

    return {
        "video_analytics_entries": len(video_entries),
        "audience_entries": len(audience_entries),
        "traffic_source_entries": len(traffic_entries),
        "device_entries": len(device_entries),
        "total_impressions": total_impressions,
        "average_ctr": average_ctr,
        "total_watch_time_hours": round(total_watch_time, 2),
        "total_subscribers_gained": total_subs_gained,
        "total_end_screen_clicks": total_end_screen_clicks
    }


def normalize_money_title(value):
    return str(value or "").strip().lower()


def get_manual_video_revenue_map():
    video_entries = get_video_revenue_entries()
    revenue_map = {}

    priority = ["lifetime", "365d", "90d", "28d", "7d"]

    grouped = {}

    for entry in video_entries:
        video_id = str(entry.get("video_id") or "").strip()
        title = normalize_money_title(entry.get("title", ""))

        key = None

        if video_id:
            key = f"id:{video_id}"
        elif title:
            key = f"title:{title}"

        if not key:
            continue

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(entry)

    for key, entries in grouped.items():

        best_revenue = 0

        for period in priority:
            matching = [
                float(e.get("amount") or 0)
                for e in entries
                if normalize_period_type(e.get("period_type")) == period
            ]

            if matching:
                best_revenue = max(matching)
                break

        total_views = sum(int(e.get("views") or 0) for e in entries)

        rpm_values = [
            float(e.get("rpm") or 0)
            for e in entries
            if float(e.get("rpm") or 0) > 0
        ]

        average_rpm = (
            round(sum(rpm_values) / len(rpm_values), 2)
            if rpm_values
            else 0
        )

        revenue_map[key] = {
            "total_revenue": round(best_revenue, 2),
            "total_views": total_views,
            "average_rpm": average_rpm,
            "entries": len(entries),
            "periods": {}
        }

    return revenue_map


def get_manual_revenue_for_video(video):
    """
    API-only compatibility wrapper.

    This name is kept so older features do not crash, but it now returns only
    synced YouTube Analytics revenue for the video. No hand-entered revenue is
    used as fallback.
    """
    video_id = str(video.get("video_id") or "").strip()

    if youtube_rows_exist() and video_id:
        auto_item = get_youtube_video_period(video_id, "lifetime")
        return {
            "total_revenue": auto_item.get("amount", 0),
            "total_views": auto_item.get("views", 0),
            "average_rpm": auto_item.get("rpm", 0),
            "entries": 5 if auto_item.get("amount", 0) or auto_item.get("views", 0) else 0,
            "periods": {
                "lifetime": auto_item.get("amount", 0),
                "365d": get_youtube_video_period(video_id, "365d").get("amount", 0),
                "90d": get_youtube_video_period(video_id, "90d").get("amount", 0),
                "28d": get_youtube_video_period(video_id, "28d").get("amount", 0),
                "7d": get_youtube_video_period(video_id, "7d").get("amount", 0),
            },
            "source": "youtube_analytics_api_revenue_tracker"
        }

    return {
        "total_revenue": 0,
        "total_views": 0,
        "average_rpm": 0,
        "entries": 0,
        "periods": {},
        "source": "youtube_analytics_api_only_no_rows_yet"
    }


def get_manual_channel_revenue_total():
    """
    API-only compatibility wrapper. Does not read hand-entered channel revenue.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period("lifetime").get("estimated_revenue", 0)

    return 0


def get_manual_channel_rpm():
    """
    API-only compatibility wrapper. Does not read hand-entered video revenue.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period("lifetime").get("rpm", 0)

    return 0


def get_manual_player_revenue_summary(videos):
    """
    API-only compatibility wrapper. Does not read hand-entered player revenue.
    """
    if youtube_rows_exist():
        return get_youtube_player_revenue_summary(videos, "lifetime")

    player_map = {}

    for video in videos:
        player = video.get("player_name") or "Unknown"

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "average_revenue": 0,
                "average_rpm": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0
            }

        player_map[player]["total_videos"] += 1
        player_map[player]["total_views"] += int(video.get("views") or 0)

    return sorted(player_map.values(), key=lambda x: x["total_views"], reverse=True)


# =========================================================
# YOUTUBE ANALYTICS API REVENUE STORE
# =========================================================

REVENUE_PERIOD_WINDOWS = {
    "7d": 7,
    "28d": 28,
    "90d": 90,
    "365d": 365,
    "lifetime": None
}

REVENUE_PERIOD_ORDER = ["lifetime", "365d", "90d", "28d", "7d"]

# Permanent correction for private/hidden videos that are not included in the public
# video list but should still count toward all-time channel revenue.
PRIVATE_HIDDEN_LIFETIME_REVENUE_ADJUSTMENT = 0


def get_private_hidden_lifetime_adjustment():
    return PRIVATE_HIDDEN_LIFETIME_REVENUE_ADJUSTMENT


def apply_private_hidden_adjustment(period_key, revenue):
    revenue = round(float(revenue or 0), 2)

    # YouTube Analytics channel totals already include private/unlisted revenue for the authenticated owner.
    # Keep this function for future manual corrections, but default adjustment is 0 to avoid double counting.
    if normalize_period_type(period_key) == "lifetime":
        return round(revenue + get_private_hidden_lifetime_adjustment(), 2)

    return revenue


def normalize_analytics_date(value):
    return str(value or "").strip()[:10]


def calculate_rpm(revenue, views):
    revenue = float(revenue or 0)
    views = int(views or 0)

    if views <= 0:
        return 0

    return round((revenue / views) * 1000, 2)


def save_youtube_revenue_daily_rows(rows):
    """
    Legacy daily row storage.
    Kept so old synced daily data does not break anything.
    New Revenue Tracker totals use youtube_revenue_period.
    """
    connection = create_connection()
    cursor = connection.cursor()

    saved = 0

    for row in rows:
        analytics_date = normalize_analytics_date(row.get("date"))

        if not analytics_date:
            continue

        video_id = str(row.get("video_id") or "").strip() or "__CHANNEL__"
        title = str(row.get("title") or "").strip()
        views = int(float(row.get("views") or 0))
        revenue = round(float(row.get("estimated_revenue") or 0), 6)
        minutes = round(float(row.get("estimated_minutes_watched") or 0), 4)
        rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 4)

        cursor.execute("""
        INSERT INTO youtube_revenue_daily (
            video_id, title, analytics_date, views, estimated_revenue,
            estimated_minutes_watched, rpm, source, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'youtube_analytics_api', CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, analytics_date) DO UPDATE SET
            title=excluded.title,
            views=excluded.views,
            estimated_revenue=excluded.estimated_revenue,
            estimated_minutes_watched=excluded.estimated_minutes_watched,
            rpm=excluded.rpm,
            source='youtube_analytics_api',
            synced_at=CURRENT_TIMESTAMP
        """, (
            video_id,
            title,
            analytics_date,
            views,
            revenue,
            minutes,
            rpm
        ))

        saved += 1

    connection.commit()
    connection.close()

    update_videos_with_youtube_revenue()

    return saved


def save_youtube_revenue_period_rows(rows):
    """
    Saves exact YouTube Analytics totals by period.
    This is the source of truth for Revenue Tracker:
    lifetime, 365d, 90d, 28d, 7d.
    """
    connection = create_connection()
    cursor = connection.cursor()

    saved = 0

    for row in rows:
        video_id = str(row.get("video_id") or "").strip() or "__CHANNEL__"
        title = str(row.get("title") or "").strip()
        period_type = normalize_period_type(row.get("period_type") or row.get("period") or "lifetime")
        start_date = normalize_analytics_date(row.get("start_date"))
        end_date = normalize_analytics_date(row.get("end_date"))
        views = int(float(row.get("views") or 0))
        revenue = round(float(row.get("estimated_revenue") or row.get("amount") or 0), 6)
        minutes = round(float(row.get("estimated_minutes_watched") or 0), 4)
        rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 4)

        cursor.execute("""
        INSERT INTO youtube_revenue_period (
            video_id, title, period_type, start_date, end_date, views,
            estimated_revenue, estimated_minutes_watched, rpm, source, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'youtube_analytics_api', CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, period_type) DO UPDATE SET
            title=excluded.title,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            views=excluded.views,
            estimated_revenue=excluded.estimated_revenue,
            estimated_minutes_watched=excluded.estimated_minutes_watched,
            rpm=excluded.rpm,
            source='youtube_analytics_api',
            synced_at=CURRENT_TIMESTAMP
        """, (
            video_id,
            title,
            period_type,
            start_date,
            end_date,
            views,
            revenue,
            minutes,
            rpm
        ))

        saved += 1

    connection.commit()
    connection.close()

    update_videos_with_youtube_revenue()

    return saved


def log_youtube_revenue_sync(sync_type, start_date, end_date, channel_rows, video_rows, status, message=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO youtube_revenue_sync_log (
        sync_type, start_date, end_date, channel_rows, video_rows, status, message, synced_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        sync_type,
        start_date,
        end_date,
        int(channel_rows or 0),
        int(video_rows or 0),
        status,
        message
    ))

    connection.commit()
    connection.close()


def get_latest_youtube_revenue_sync():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM youtube_revenue_sync_log
    ORDER BY synced_at DESC, id DESC
    LIMIT 1
    """)

    row = cursor.fetchone()
    connection.close()

    return dict(row) if row else None


def get_youtube_revenue_date_range():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        MIN(start_date) as first_date,
        MAX(end_date) as last_date,
        COUNT(*) as total_rows
    FROM youtube_revenue_period
    """)

    row = cursor.fetchone()

    if row and int(row["total_rows"] or 0) > 0:
        connection.close()
        return {
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "total_rows": row["total_rows"] or 0
        }

    cursor.execute("""
    SELECT
        MIN(analytics_date) as first_date,
        MAX(analytics_date) as last_date,
        COUNT(*) as total_rows
    FROM youtube_revenue_daily
    """)

    row = cursor.fetchone()
    connection.close()

    return {
        "first_date": row["first_date"] if row else None,
        "last_date": row["last_date"] if row else None,
        "total_rows": row["total_rows"] if row else 0
    }


def get_youtube_period_row(video_id, period_key):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM youtube_revenue_period
    WHERE video_id=?
    AND period_type=?
    LIMIT 1
    """, (video_id, normalize_period_type(period_key)))

    row = cursor.fetchone()
    connection.close()

    return dict(row) if row else None


def period_start_date(period_key):
    from datetime import date, timedelta

    period_key = normalize_period_type(period_key)

    if period_key == "lifetime":
        return None

    days = REVENUE_PERIOD_WINDOWS.get(period_key)

    if not days:
        return None

    return (date.today() - timedelta(days=days - 1)).isoformat()


def get_youtube_channel_period(period_key):
    period_key = normalize_period_type(period_key)
    period_row = get_youtube_period_row("__CHANNEL__", period_key)

    if period_row:
        views = int(period_row.get("views") or 0)
        raw_revenue = round(float(period_row.get("estimated_revenue") or 0), 2)
        revenue = apply_private_hidden_adjustment(period_key, raw_revenue)
        private_adjustment = get_private_hidden_lifetime_adjustment() if period_key == "lifetime" else 0
        minutes = round(float(period_row.get("estimated_minutes_watched") or 0), 2)

        return {
            "period": period_key,
            "views": views,
            "estimated_revenue": revenue,
            "amount": revenue,
            "estimated_minutes_watched": minutes,
            "rpm": calculate_rpm(revenue, views),
            "start_date": period_row.get("start_date") or "",
            "end_date": period_row.get("end_date") or "",
            "source": "youtube_analytics_api",
            "raw_estimated_revenue": raw_revenue,
            "private_hidden_adjustment": private_adjustment
        }

    # Fallback to old daily rows if period snapshots have not been synced yet.
    start_date = period_start_date(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    if start_date:
        cursor.execute("""
        SELECT
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id='__CHANNEL__'
        AND analytics_date >= ?
        """, (start_date,))
    else:
        cursor.execute("""
        SELECT
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id='__CHANNEL__'
        """)

    row = cursor.fetchone()
    connection.close()

    views = int(row["views"] or 0) if row else 0
    raw_revenue = round(float(row["revenue"] or 0), 2) if row else 0
    revenue = apply_private_hidden_adjustment(period_key, raw_revenue)
    private_adjustment = get_private_hidden_lifetime_adjustment() if period_key == "lifetime" else 0
    minutes = round(float(row["minutes"] or 0), 2) if row else 0

    return {
        "period": period_key,
        "views": views,
        "estimated_revenue": revenue,
        "amount": revenue,
        "estimated_minutes_watched": minutes,
        "rpm": calculate_rpm(revenue, views),
        "start_date": start_date or "",
        "end_date": "",
        "source": "youtube_analytics_api_daily_fallback",
        "raw_estimated_revenue": raw_revenue,
        "private_hidden_adjustment": private_adjustment
    }


def get_youtube_video_period(video_id, period_key):
    period_key = normalize_period_type(period_key)
    period_row = get_youtube_period_row(video_id, period_key)

    if period_row:
        views = int(period_row.get("views") or 0)
        revenue = round(float(period_row.get("estimated_revenue") or 0), 2)
        minutes = round(float(period_row.get("estimated_minutes_watched") or 0), 2)

        return {
            "video_id": video_id,
            "title": period_row.get("title") or "",
            "period_type": period_key,
            "amount": revenue,
            "estimated_revenue": revenue,
            "views": views,
            "estimated_minutes_watched": minutes,
            "rpm": calculate_rpm(revenue, views),
            "start_date": period_row.get("start_date") or "",
            "end_date": period_row.get("end_date") or "",
            "notes": "YouTube Analytics API",
            "source": "youtube_analytics_api"
        }

    start_date = period_start_date(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    if start_date:
        cursor.execute("""
        SELECT
            video_id,
            MAX(title) as title,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id=?
        AND analytics_date >= ?
        GROUP BY video_id
        """, (video_id, start_date))
    else:
        cursor.execute("""
        SELECT
            video_id,
            MAX(title) as title,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id=?
        GROUP BY video_id
        """, (video_id,))

    row = cursor.fetchone()
    connection.close()

    if not row:
        return {
            "video_id": video_id,
            "title": "",
            "period_type": period_key,
            "amount": 0,
            "estimated_revenue": 0,
            "views": 0,
            "rpm": 0,
            "start_date": start_date or "",
            "end_date": "",
            "notes": "YouTube Analytics API"
        }

    views = int(row["views"] or 0)
    revenue = round(float(row["revenue"] or 0), 2)
    minutes = round(float(row["minutes"] or 0), 2)

    return {
        "video_id": row["video_id"],
        "title": row["title"] or "",
        "period_type": period_key,
        "amount": revenue,
        "estimated_revenue": revenue,
        "views": views,
        "estimated_minutes_watched": minutes,
        "rpm": calculate_rpm(revenue, views),
        "start_date": start_date or "",
        "end_date": "",
        "notes": "YouTube Analytics API",
        "source": "youtube_analytics_api_daily_fallback"
    }


def get_youtube_channel_revenue_entries():
    entries = []

    for period in REVENUE_PERIOD_ORDER:
        item = get_youtube_channel_period(period)

        entries.append({
            "id": f"youtube-channel-{period}",
            "period_type": period,
            "amount": item["estimated_revenue"],
            "views": item["views"],
            "rpm": item["rpm"],
            "start_date": item["start_date"],
            "end_date": item["end_date"],
            "notes": "Auto synced from YouTube Analytics API",
            "source": "youtube_analytics_api"
        })

    return entries


def get_youtube_video_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        title,
        period_type,
        start_date,
        end_date,
        views,
        estimated_revenue,
        estimated_minutes_watched,
        rpm,
        synced_at
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    ORDER BY estimated_revenue DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    if rows:
        return [
            {
                "id": f"youtube-video-{row['video_id']}-{row['period_type']}",
                "video_id": row["video_id"],
                "title": row["title"] or "",
                "period_type": row["period_type"],
                "amount": round(float(row["estimated_revenue"] or 0), 2),
                "estimated_revenue": round(float(row["estimated_revenue"] or 0), 2),
                "views": int(row["views"] or 0),
                "estimated_minutes_watched": round(float(row["estimated_minutes_watched"] or 0), 2),
                "rpm": round(float(row["rpm"] or 0), 2),
                "start_date": row["start_date"] or "",
                "end_date": row["end_date"] or "",
                "notes": "YouTube Analytics API",
                "source": "youtube_analytics_api",
                "synced_at": row["synced_at"]
            }
            for row in rows
        ]

    # Fallback for old daily data.
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT DISTINCT video_id
    FROM youtube_revenue_daily
    WHERE video_id != '__CHANNEL__'
    ORDER BY video_id
    """)

    video_ids = [row["video_id"] for row in cursor.fetchall()]
    connection.close()

    entries = []

    for video_id in video_ids:
        for period in REVENUE_PERIOD_ORDER:
            item = get_youtube_video_period(video_id, period)
            item["id"] = f"youtube-video-{video_id}-{period}"
            item["source"] = "youtube_analytics_api"
            entries.append(item)

    return entries


def get_top_youtube_video_revenue(period_key="lifetime", limit=50):
    period_key = normalize_period_type(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        title,
        period_type,
        start_date,
        end_date,
        views,
        estimated_revenue,
        estimated_minutes_watched,
        rpm,
        synced_at
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    AND period_type=?
    ORDER BY estimated_revenue DESC
    LIMIT ?
    """, (period_key, int(limit or 50)))

    rows = cursor.fetchall()
    connection.close()

    return [
        {
            "rank": index + 1,
            "video_id": row["video_id"],
            "title": row["title"] or "",
            "period_type": row["period_type"],
            "amount": round(float(row["estimated_revenue"] or 0), 2),
            "estimated_revenue": round(float(row["estimated_revenue"] or 0), 2),
            "views": int(row["views"] or 0),
            "rpm": round(float(row["rpm"] or 0), 2),
            "start_date": row["start_date"] or "",
            "end_date": row["end_date"] or "",
            "synced_at": row["synced_at"]
        }
        for index, row in enumerate(rows)
    ]


def get_youtube_revenue_summary():
    channel_by_period = {}
    channel_views_by_period = {}
    channel_rpm_by_period = {}
    channel_date_ranges = {}
    video_by_period = {}
    video_views_by_period = {}
    video_rpm_by_period = {}

    video_entries = get_youtube_video_revenue_entries()
    channel_entries = get_youtube_channel_revenue_entries()

    for period in REVENUE_PERIOD_ORDER:
        channel_item = get_youtube_channel_period(period)
        channel_by_period[period] = channel_item["estimated_revenue"]
        channel_views_by_period[period] = channel_item["views"]
        channel_rpm_by_period[period] = channel_item["rpm"]
        channel_date_ranges[period] = {
            "start_date": channel_item.get("start_date", ""),
            "end_date": channel_item.get("end_date", "")
        }

        period_video_entries = [
            item for item in video_entries
            if item.get("period_type") == period
        ]

        period_revenue = round(sum(float(item.get("amount") or 0) for item in period_video_entries), 2)
        period_views = sum(int(item.get("views") or 0) for item in period_video_entries)

        video_by_period[period] = period_revenue
        video_views_by_period[period] = period_views
        video_rpm_by_period[period] = calculate_rpm(period_revenue, period_views)

    date_range = get_youtube_revenue_date_range()

    return {
        "source": "youtube_analytics_api",
        "is_auto_synced": True,
        "periods": REVENUE_PERIOD_ORDER,
        "total_channel_manual_revenue": channel_by_period.get("lifetime", 0),
        "total_video_manual_revenue": video_by_period.get("lifetime", 0),
        "total_channel_youtube_revenue": channel_by_period.get("lifetime", 0),
        "total_video_youtube_revenue": video_by_period.get("lifetime", 0),
        "channel_revenue_entries": len(channel_entries),
        "video_revenue_entries": len(video_entries),
        "channel_by_period": channel_by_period,
        "channel_views_by_period": channel_views_by_period,
        "channel_rpm_by_period": channel_rpm_by_period,
        "channel_date_ranges": channel_date_ranges,
        "private_hidden_lifetime_adjustment": get_private_hidden_lifetime_adjustment(),
        "private_hidden_adjustment_note": "No manual private-video adjustment is currently added. YouTube Analytics channel totals should already include private/unlisted video revenue for the owner account.",
        "video_by_period": video_by_period,
        "video_views_by_period": video_views_by_period,
        "video_rpm_by_period": video_rpm_by_period,
        "first_analytics_date": date_range.get("first_date"),
        "last_analytics_date": date_range.get("last_date"),
        "total_daily_rows": date_range.get("total_rows"),
        "latest_sync": get_latest_youtube_revenue_sync()
    }


def get_youtube_revenue_status():
    summary = get_youtube_revenue_summary()
    latest_sync = get_latest_youtube_revenue_sync()

    return {
        "enabled": True,
        "source": "youtube_analytics_api",
        "message": "Revenue Tracker is using exact YouTube Analytics API period totals when synced. Default sync uses YouTube Studio-style completed-day windows.",
        "latest_sync": latest_sync,
        "first_analytics_date": summary.get("first_analytics_date"),
        "last_analytics_date": summary.get("last_analytics_date"),
        "total_daily_rows": summary.get("total_daily_rows"),
        "channel_lifetime_revenue": summary.get("total_channel_youtube_revenue"),
        "video_lifetime_revenue": summary.get("total_video_youtube_revenue"),
        "channel_by_period": summary.get("channel_by_period"),
        "video_by_period": summary.get("video_by_period"),
        "channel_date_ranges": summary.get("channel_date_ranges"),
        "private_hidden_lifetime_adjustment": summary.get("private_hidden_lifetime_adjustment"),
        "private_hidden_adjustment_note": summary.get("private_hidden_adjustment_note")
    }



def youtube_period_rows_count():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) as total_rows FROM youtube_revenue_period")
    row = cursor.fetchone()
    connection.close()

    return int(row["total_rows"] or 0) if row else 0


def update_videos_with_youtube_revenue():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        views,
        estimated_revenue
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    AND period_type='lifetime'
    """)

    rows = cursor.fetchall()

    if not rows:
        cursor.execute("""
        SELECT
            video_id,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue
        FROM youtube_revenue_daily
        WHERE video_id != '__CHANNEL__'
        GROUP BY video_id
        """)

        rows = cursor.fetchall()

        for row in rows:
            views = int(row["views"] or 0)
            revenue = round(float(row["revenue"] or 0), 2)
            rpm = calculate_rpm(revenue, views)

            cursor.execute("""
            UPDATE videos
            SET
                estimated_revenue=?,
                estimated_rpm=?,
                yt_estimated_revenue=?,
                yt_estimated_rpm=?,
                yt_revenue_synced_at=CURRENT_TIMESTAMP
            WHERE video_id=?
            """, (
                revenue,
                rpm,
                revenue,
                rpm,
                row["video_id"]
            ))

        connection.commit()
        connection.close()
        return

    for row in rows:
        views = int(row["views"] or 0)
        revenue = round(float(row["estimated_revenue"] or 0), 2)
        rpm = calculate_rpm(revenue, views)

        cursor.execute("""
        UPDATE videos
        SET
            estimated_revenue=?,
            estimated_rpm=?,
            yt_estimated_revenue=?,
            yt_estimated_rpm=?,
            yt_revenue_synced_at=CURRENT_TIMESTAMP
        WHERE video_id=?
        """, (
            revenue,
            rpm,
            revenue,
            rpm,
            row["video_id"]
        ))

    connection.commit()
    connection.close()



def get_youtube_player_revenue_summary(videos, period_type="lifetime"):
    """
    Groups YouTube Analytics API video period revenue by detected player.
    This replaces manual revenue grouping when API revenue rows exist.
    """
    period_type = normalize_period_type(period_type)

    player_map = {}

    for video in videos:
        player = video.get("player_name") or "Unknown"

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "manual_revenue": 0,
                "youtube_revenue": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0,
                "rpm_values": []
            }

        player_map[player]["total_videos"] += 1
        player_map[player]["total_views"] += int(video.get("views") or 0)

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT video_id, title, views, estimated_revenue, rpm
    FROM youtube_revenue_period
    WHERE period_type=?
    AND video_id != '__CHANNEL__'
    """, (period_type,))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    video_to_player = {
        str(video.get("video_id") or ""): video.get("player_name") or "Unknown"
        for video in videos
    }

    for row in rows:
        video_id = str(row.get("video_id") or "")
        player = video_to_player.get(video_id, "Unknown")

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "manual_revenue": 0,
                "youtube_revenue": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0,
                "rpm_values": []
            }

        revenue = round(float(row.get("estimated_revenue") or 0), 2)
        views = int(row.get("views") or 0)
        rpm = float(row.get("rpm") or 0)

        if revenue > 0:
            player_map[player]["total_revenue"] += revenue
            player_map[player]["youtube_revenue"] += revenue
            player_map[player]["youtube_revenue_videos"] += 1
            player_map[player]["manual_revenue_videos"] += 1

        if views > 0 and player_map[player]["total_views"] <= 0:
            player_map[player]["total_views"] += views

        if rpm > 0:
            player_map[player]["rpm_values"].append(rpm)

    results = []

    for player, item in player_map.items():
        revenue_videos = int(item["youtube_revenue_videos"] or 0)

        average_rpm = (
            round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2)
            if item["rpm_values"]
            else 0
        )

        average_revenue = (
            round(item["total_revenue"] / revenue_videos, 2)
            if revenue_videos > 0
            else 0
        )

        results.append({
            "player": player,
            "total_revenue": round(item["total_revenue"], 2),
            "manual_revenue": round(item["total_revenue"], 2),
            "youtube_revenue": round(item["youtube_revenue"], 2),
            "average_revenue": average_revenue,
            "average_rpm": average_rpm,
            "manual_revenue_videos": revenue_videos,
            "youtube_revenue_videos": revenue_videos,
            "total_videos": item["total_videos"],
            "total_views": item["total_views"]
        })

    return sorted(results, key=lambda x: (x["total_revenue"], x["total_views"]), reverse=True)



def get_best_revenue_for_video(video, period_type="lifetime"):
    """
    Single video money helper for all recommendation tools.
    Source order:
    1. synced YouTube Analytics / Revenue Tracker period row
    2. synced values stored on the videos table
    3. zero if no synced API data exists

    Manual revenue is intentionally not used for predictions.
    """
    period_type = normalize_period_type(period_type)
    video_id = str(video.get("video_id") or "").strip()

    if video_id and youtube_rows_exist():
        row = get_youtube_period_row(video_id, period_type)
        if row:
            views = int(row.get("views") or 0)
            revenue = round(float(row.get("estimated_revenue") or 0), 2)
            rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 2)
            return {
                "video_id": video_id,
                "period_type": period_type,
                "total_revenue": revenue,
                "estimated_revenue": revenue,
                "average_rpm": rpm,
                "rpm": rpm,
                "views": views,
                "entries": 1 if revenue > 0 or views > 0 or rpm > 0 else 0,
                "source": "youtube_analytics_api_revenue_tracker",
                "periods": {
                    period_type: revenue,
                    "lifetime": get_youtube_video_period(video_id, "lifetime").get("amount", 0),
                    "365d": get_youtube_video_period(video_id, "365d").get("amount", 0),
                    "90d": get_youtube_video_period(video_id, "90d").get("amount", 0),
                    "28d": get_youtube_video_period(video_id, "28d").get("amount", 0),
                    "7d": get_youtube_video_period(video_id, "7d").get("amount", 0),
                }
            }

    views = int(video.get("views") or 0)
    revenue = round(float(video.get("yt_estimated_revenue") or video.get("estimated_revenue") or 0), 2)
    rpm = round(float(video.get("yt_estimated_rpm") or video.get("estimated_rpm") or calculate_rpm(revenue, views)), 2)

    return {
        "video_id": video_id,
        "period_type": period_type,
        "total_revenue": revenue,
        "estimated_revenue": revenue,
        "average_rpm": rpm,
        "rpm": rpm,
        "views": views,
        "entries": 1 if revenue > 0 or rpm > 0 else 0,
        "source": "synced_video_row" if revenue > 0 or rpm > 0 else "no_synced_revenue"
    }


def get_best_player_revenue_summary(videos, period_type="lifetime"):
    """
    Returns synced YouTube Analytics player revenue only.
    """
    if youtube_rows_exist():
        return get_youtube_player_revenue_summary(videos, period_type)

    return []


def get_best_channel_rpm(period_type="lifetime"):
    """
    Returns synced YouTube Analytics channel RPM only.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period(period_type).get("rpm", 0)

    return 0


def youtube_rows_exist():
    status = get_youtube_revenue_date_range()
    return int(status.get("total_rows") or 0) > 0


def get_best_revenue_summary():
    """
    Single source of truth: synced YouTube Analytics / Revenue Tracker rows only.
    Manual revenue is intentionally ignored.
    """
    if youtube_rows_exist():
        summary = get_youtube_revenue_summary()
        summary["data_source"] = "youtube_analytics_api_revenue_tracker"
        return summary

    return {
        "channel_revenue_entries": 0,
        "video_revenue_entries": 0,
        "total_channel_youtube_revenue": 0,
        "total_video_youtube_revenue": 0,
        "total_channel_manual_revenue": 0,
        "total_video_manual_revenue": 0,
        "channel_by_period": {},
        "video_by_period": {},
        "channel_views_by_period": {},
        "video_views_by_period": {},
        "channel_rpm_by_period": {},
        "video_rpm_by_period": {},
        "private_hidden_lifetime_adjustment": get_private_hidden_lifetime_adjustment(),
        "data_source": "youtube_analytics_api_only_no_rows_yet"
    }


def get_best_channel_revenue_entries():
    """
    Returns channel revenue rows from synced YouTube Analytics only.
    """
    if youtube_rows_exist():
        return get_youtube_channel_revenue_entries()

    return []


def get_best_video_revenue_entries():
    """
    Returns video revenue rows from synced YouTube Analytics only.
    """
    if youtube_rows_exist():
        return get_youtube_video_revenue_entries()
import sqlite3
import os

DB_FOLDER = "database"
DATABASE_NAME = os.path.join(DB_FOLDER, "courtvision.db")


def create_connection():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    connection = sqlite3.connect(DATABASE_NAME, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def add_column_if_missing(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def create_revenue_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period_type TEXT,
        amount REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT,
        amount REAL DEFAULT 0,
        views INTEGER DEFAULT 0,
        rpm REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)



def create_youtube_analytics_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        analytics_date TEXT NOT NULL,
        views INTEGER DEFAULT 0,
        estimated_revenue REAL DEFAULT 0,
        estimated_minutes_watched REAL DEFAULT 0,
        rpm REAL DEFAULT 0,
        source TEXT DEFAULT 'youtube_analytics_api',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, analytics_date)
    )
    """)



    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_period (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT 'lifetime',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        estimated_revenue REAL DEFAULT 0,
        estimated_minutes_watched REAL DEFAULT 0,
        rpm REAL DEFAULT 0,
        source TEXT DEFAULT 'youtube_analytics_api',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(video_id, period_type)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS youtube_revenue_sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_type TEXT DEFAULT 'manual',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        channel_rows INTEGER DEFAULT 0,
        video_rows INTEGER DEFAULT 0,
        status TEXT DEFAULT '',
        message TEXT DEFAULT '',
        synced_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)


def create_manual_analytics_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_video_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '7d',
        impressions INTEGER DEFAULT 0,
        ctr REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        average_view_duration TEXT DEFAULT '',
        average_percentage_viewed REAL DEFAULT 0,
        subscribers_gained INTEGER DEFAULT 0,
        subscribers_lost INTEGER DEFAULT 0,
        returning_viewers INTEGER DEFAULT 0,
        new_viewers INTEGER DEFAULT 0,
        end_screen_clicks INTEGER DEFAULT 0,
        playlist_starts INTEGER DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_audience_demographics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        country TEXT DEFAULT '',
        gender TEXT DEFAULT '',
        age_range TEXT DEFAULT '',
        percentage REAL DEFAULT 0,
        views INTEGER DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_traffic_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        source TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        average_view_duration TEXT DEFAULT '',
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manual_device_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT DEFAULT 'channel',
        video_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        period_type TEXT DEFAULT '30d',
        device_type TEXT DEFAULT '',
        views INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        start_date TEXT DEFAULT '',
        end_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)


def create_videos_table():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        video_id TEXT UNIQUE,
        published TEXT
    )
    """)

    add_column_if_missing(cursor, "videos", "views", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "likes", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "comments", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "thumbnail", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "estimated_revenue", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "estimated_rpm", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_estimated_revenue", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_estimated_rpm", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "yt_revenue_synced_at", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "content_type", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "player_name", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "title_length", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "upload_year", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "ai_score", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "synced_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

    create_revenue_tables(cursor)
    create_youtube_analytics_tables(cursor)
    create_manual_analytics_tables(cursor)

    connection.commit()
    connection.close()


def save_video(
    title,
    video_id,
    published,
    views=0,
    likes=0,
    comments=0,
    thumbnail="",
    estimated_revenue=0,
    estimated_rpm=0,
    content_type="",
    player_name="",
    title_length=0,
    upload_year=0,
    ai_score=0
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO videos (
        title, video_id, published, views, likes, comments, thumbnail,
        estimated_revenue, estimated_rpm, content_type, player_name,
        title_length, upload_year, ai_score, synced_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(video_id) DO UPDATE SET
        title=excluded.title,
        published=excluded.published,
        views=excluded.views,
        likes=excluded.likes,
        comments=excluded.comments,
        thumbnail=excluded.thumbnail,
        estimated_revenue=excluded.estimated_revenue,
        estimated_rpm=excluded.estimated_rpm,
        content_type=excluded.content_type,
        player_name=excluded.player_name,
        title_length=excluded.title_length,
        upload_year=excluded.upload_year,
        ai_score=excluded.ai_score,
        synced_at=CURRENT_TIMESTAMP
    """, (
        title, video_id, published, views, likes, comments, thumbnail,
        estimated_revenue, estimated_rpm, content_type, player_name,
        title_length, upload_year, ai_score
    ))

    connection.commit()
    connection.close()


def get_saved_videos():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM videos ORDER BY views DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def clear_videos():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM videos")
    connection.commit()
    connection.close()


def get_channel_totals():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        COUNT(*) as total_videos,
        SUM(views) as total_views,
        SUM(likes) as total_likes,
        SUM(comments) as total_comments,
        AVG(views) as average_views
    FROM videos
    """)

    row = cursor.fetchone()
    connection.close()

    api_revenue = get_youtube_channel_period("lifetime").get("estimated_revenue", 0) if youtube_rows_exist() else 0

    return {
        "total_videos": row["total_videos"] or 0,
        "total_views": row["total_views"] or 0,
        "total_likes": row["total_likes"] or 0,
        "total_comments": row["total_comments"] or 0,
        "average_views": int(row["average_views"] or 0),
        "estimated_revenue": api_revenue
    }


def get_top_videos(limit=10):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM videos
    ORDER BY views DESC
    LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]


def save_channel_revenue(period_type, amount, start_date="", end_date="", notes=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO channel_revenue (
        period_type, amount, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (period_type, float(amount or 0), start_date, end_date, notes))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_channel_revenue(entry_id, period_type, amount, start_date="", end_date="", notes=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    UPDATE channel_revenue
    SET period_type=?, amount=?, start_date=?, end_date=?, notes=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, (period_type, float(amount or 0), start_date, end_date, notes, entry_id))

    connection.commit()
    connection.close()


def delete_channel_revenue(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM channel_revenue WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_channel_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM channel_revenue ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def save_video_revenue(
    video_id="",
    title="",
    period_type="lifetime",
    amount=0,
    views=0,
    rpm=0,
    start_date="",
    end_date="",
    notes=""
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO video_revenue (
        video_id, title, period_type, amount, views, rpm,
        start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        video_id, title, period_type, float(amount or 0), int(views or 0),
        float(rpm or 0), start_date, end_date, notes
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_video_revenue(
    entry_id,
    video_id="",
    title="",
    period_type="lifetime",
    amount=0,
    views=0,
    rpm=0,
    start_date="",
    end_date="",
    notes=""
):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    UPDATE video_revenue
    SET video_id=?, title=?, period_type=?, amount=?, views=?, rpm=?,
        start_date=?, end_date=?, notes=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, (
        video_id, title, period_type, float(amount or 0), int(views or 0),
        float(rpm or 0), start_date, end_date, notes, entry_id
    ))

    connection.commit()
    connection.close()


def delete_video_revenue(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM video_revenue WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_video_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM video_revenue ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def normalize_period_type(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


def best_revenue_total(entries):
    """
    Prevents double counting.
    Lifetime is the true total.
    If lifetime does not exist, use the biggest available period.
    """
    priority = ["lifetime", "365d", "90d", "28d", "7d"]

    by_period = {}

    for entry in entries:
        period = normalize_period_type(entry.get("period_type"))
        by_period[period] = by_period.get(period, 0) + float(entry.get("amount") or 0)

    for period in priority:
        if period in by_period:
            return round(by_period[period], 2)

    return 0


def get_manual_revenue_summary():
    """
    API-only compatibility wrapper.

    Older route files may still call this function name, but it no longer reads
    hand-entered revenue. It returns synced YouTube Analytics / Revenue Tracker
    data only. If there are no synced API rows yet, it returns empty zero values.
    """
    if youtube_rows_exist():
        return get_youtube_revenue_summary()

    return {
        "channel_revenue_entries": 0,
        "video_revenue_entries": 0,
        "total_channel_manual_revenue": 0,
        "total_video_manual_revenue": 0,
        "total_channel_youtube_revenue": 0,
        "total_video_youtube_revenue": 0,
        "channel_by_period": {},
        "video_by_period": {},
        "channel_views_by_period": {},
        "video_views_by_period": {},
        "channel_rpm_by_period": {},
        "video_rpm_by_period": {},
        "data_source": "youtube_analytics_api_only_no_rows_yet"
    }


def save_manual_video_analytics(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_video_analytics (
        video_id, title, period_type, impressions, ctr, watch_time_hours,
        average_view_duration, average_percentage_viewed, subscribers_gained,
        subscribers_lost, returning_viewers, new_viewers, end_screen_clicks,
        playlist_starts, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "7d"),
        int(entry.get("impressions") or 0),
        float(entry.get("ctr") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("average_view_duration", ""),
        float(entry.get("average_percentage_viewed") or 0),
        int(entry.get("subscribers_gained") or 0),
        int(entry.get("subscribers_lost") or 0),
        int(entry.get("returning_viewers") or 0),
        int(entry.get("new_viewers") or 0),
        int(entry.get("end_screen_clicks") or 0),
        int(entry.get("playlist_starts") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_video_analytics_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_video_analytics ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_video_analytics(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_video_analytics WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_audience_demographic(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_audience_demographics (
        scope, video_id, title, period_type, country, gender, age_range,
        percentage, views, watch_time_hours, start_date, end_date, notes,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("country", ""),
        entry.get("gender", ""),
        entry.get("age_range", ""),
        float(entry.get("percentage") or 0),
        int(entry.get("views") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_audience_demographic_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_audience_demographics ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_audience_demographic(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_audience_demographics WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_traffic_source(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_traffic_sources (
        scope, video_id, title, period_type, source, views, percentage,
        watch_time_hours, average_view_duration, start_date, end_date, notes,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("source", ""),
        int(entry.get("views") or 0),
        float(entry.get("percentage") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("average_view_duration", ""),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_traffic_source_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_traffic_sources ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_traffic_source(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_traffic_sources WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def save_manual_device_stat(entry):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO manual_device_stats (
        scope, video_id, title, period_type, device_type, views, percentage,
        watch_time_hours, start_date, end_date, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        entry.get("scope", "channel"),
        entry.get("video_id", ""),
        entry.get("title", ""),
        entry.get("period_type", "30d"),
        entry.get("device_type", ""),
        int(entry.get("views") or 0),
        float(entry.get("percentage") or 0),
        float(entry.get("watch_time_hours") or 0),
        entry.get("start_date", ""),
        entry.get("end_date", ""),
        entry.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_manual_device_stat_entries():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM manual_device_stats ORDER BY created_at DESC, id DESC")
    rows = cursor.fetchall()
    connection.close()
    return [dict(row) for row in rows]


def delete_manual_device_stat(entry_id):
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM manual_device_stats WHERE id=?", (entry_id,))
    connection.commit()
    connection.close()


def get_manual_analytics_summary():
    video_entries = get_manual_video_analytics_entries()
    audience_entries = get_manual_audience_demographic_entries()
    traffic_entries = get_manual_traffic_source_entries()
    device_entries = get_manual_device_stat_entries()

    total_impressions = sum(int(e.get("impressions") or 0) for e in video_entries)
    total_watch_time = sum(float(e.get("watch_time_hours") or 0) for e in video_entries)
    total_subs_gained = sum(int(e.get("subscribers_gained") or 0) for e in video_entries)
    total_end_screen_clicks = sum(int(e.get("end_screen_clicks") or 0) for e in video_entries)

    ctr_values = [
        float(e.get("ctr") or 0)
        for e in video_entries
        if float(e.get("ctr") or 0) > 0
    ]

    average_ctr = round(sum(ctr_values) / len(ctr_values), 2) if ctr_values else 0

    return {
        "video_analytics_entries": len(video_entries),
        "audience_entries": len(audience_entries),
        "traffic_source_entries": len(traffic_entries),
        "device_entries": len(device_entries),
        "total_impressions": total_impressions,
        "average_ctr": average_ctr,
        "total_watch_time_hours": round(total_watch_time, 2),
        "total_subscribers_gained": total_subs_gained,
        "total_end_screen_clicks": total_end_screen_clicks
    }


def normalize_money_title(value):
    return str(value or "").strip().lower()


def get_manual_video_revenue_map():
    video_entries = get_video_revenue_entries()
    revenue_map = {}

    priority = ["lifetime", "365d", "90d", "28d", "7d"]

    grouped = {}

    for entry in video_entries:
        video_id = str(entry.get("video_id") or "").strip()
        title = normalize_money_title(entry.get("title", ""))

        key = None

        if video_id:
            key = f"id:{video_id}"
        elif title:
            key = f"title:{title}"

        if not key:
            continue

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(entry)

    for key, entries in grouped.items():

        best_revenue = 0

        for period in priority:
            matching = [
                float(e.get("amount") or 0)
                for e in entries
                if normalize_period_type(e.get("period_type")) == period
            ]

            if matching:
                best_revenue = max(matching)
                break

        total_views = sum(int(e.get("views") or 0) for e in entries)

        rpm_values = [
            float(e.get("rpm") or 0)
            for e in entries
            if float(e.get("rpm") or 0) > 0
        ]

        average_rpm = (
            round(sum(rpm_values) / len(rpm_values), 2)
            if rpm_values
            else 0
        )

        revenue_map[key] = {
            "total_revenue": round(best_revenue, 2),
            "total_views": total_views,
            "average_rpm": average_rpm,
            "entries": len(entries),
            "periods": {}
        }

    return revenue_map


def get_manual_revenue_for_video(video):
    """
    API-only compatibility wrapper.

    This name is kept so older features do not crash, but it now returns only
    synced YouTube Analytics revenue for the video. No hand-entered revenue is
    used as fallback.
    """
    video_id = str(video.get("video_id") or "").strip()

    if youtube_rows_exist() and video_id:
        auto_item = get_youtube_video_period(video_id, "lifetime")
        return {
            "total_revenue": auto_item.get("amount", 0),
            "total_views": auto_item.get("views", 0),
            "average_rpm": auto_item.get("rpm", 0),
            "entries": 5 if auto_item.get("amount", 0) or auto_item.get("views", 0) else 0,
            "periods": {
                "lifetime": auto_item.get("amount", 0),
                "365d": get_youtube_video_period(video_id, "365d").get("amount", 0),
                "90d": get_youtube_video_period(video_id, "90d").get("amount", 0),
                "28d": get_youtube_video_period(video_id, "28d").get("amount", 0),
                "7d": get_youtube_video_period(video_id, "7d").get("amount", 0),
            },
            "source": "youtube_analytics_api_revenue_tracker"
        }

    return {
        "total_revenue": 0,
        "total_views": 0,
        "average_rpm": 0,
        "entries": 0,
        "periods": {},
        "source": "youtube_analytics_api_only_no_rows_yet"
    }


def get_manual_channel_revenue_total():
    """
    API-only compatibility wrapper. Does not read hand-entered channel revenue.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period("lifetime").get("estimated_revenue", 0)

    return 0


def get_manual_channel_rpm():
    """
    API-only compatibility wrapper. Does not read hand-entered video revenue.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period("lifetime").get("rpm", 0)

    return 0


def get_manual_player_revenue_summary(videos):
    """
    API-only compatibility wrapper. Does not read hand-entered player revenue.
    """
    if youtube_rows_exist():
        return get_youtube_player_revenue_summary(videos, "lifetime")

    player_map = {}

    for video in videos:
        player = video.get("player_name") or "Unknown"

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "average_revenue": 0,
                "average_rpm": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0
            }

        player_map[player]["total_videos"] += 1
        player_map[player]["total_views"] += int(video.get("views") or 0)

    return sorted(player_map.values(), key=lambda x: x["total_views"], reverse=True)


# =========================================================
# YOUTUBE ANALYTICS API REVENUE STORE
# =========================================================

REVENUE_PERIOD_WINDOWS = {
    "7d": 7,
    "28d": 28,
    "90d": 90,
    "365d": 365,
    "lifetime": None
}

REVENUE_PERIOD_ORDER = ["lifetime", "365d", "90d", "28d", "7d"]

# Permanent correction for private/hidden videos that are not included in the public
# video list but should still count toward all-time channel revenue.
PRIVATE_HIDDEN_LIFETIME_REVENUE_ADJUSTMENT = 0


def get_private_hidden_lifetime_adjustment():
    return PRIVATE_HIDDEN_LIFETIME_REVENUE_ADJUSTMENT


def apply_private_hidden_adjustment(period_key, revenue):
    revenue = round(float(revenue or 0), 2)

    # YouTube Analytics channel totals already include private/unlisted revenue for the authenticated owner.
    # Keep this function for future manual corrections, but default adjustment is 0 to avoid double counting.
    if normalize_period_type(period_key) == "lifetime":
        return round(revenue + get_private_hidden_lifetime_adjustment(), 2)

    return revenue


def normalize_analytics_date(value):
    return str(value or "").strip()[:10]


def calculate_rpm(revenue, views):
    revenue = float(revenue or 0)
    views = int(views or 0)

    if views <= 0:
        return 0

    return round((revenue / views) * 1000, 2)


def save_youtube_revenue_daily_rows(rows):
    """
    Legacy daily row storage.
    Kept so old synced daily data does not break anything.
    New Revenue Tracker totals use youtube_revenue_period.
    """
    connection = create_connection()
    cursor = connection.cursor()

    saved = 0

    for row in rows:
        analytics_date = normalize_analytics_date(row.get("date"))

        if not analytics_date:
            continue

        video_id = str(row.get("video_id") or "").strip() or "__CHANNEL__"
        title = str(row.get("title") or "").strip()
        views = int(float(row.get("views") or 0))
        revenue = round(float(row.get("estimated_revenue") or 0), 6)
        minutes = round(float(row.get("estimated_minutes_watched") or 0), 4)
        rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 4)

        cursor.execute("""
        INSERT INTO youtube_revenue_daily (
            video_id, title, analytics_date, views, estimated_revenue,
            estimated_minutes_watched, rpm, source, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'youtube_analytics_api', CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, analytics_date) DO UPDATE SET
            title=excluded.title,
            views=excluded.views,
            estimated_revenue=excluded.estimated_revenue,
            estimated_minutes_watched=excluded.estimated_minutes_watched,
            rpm=excluded.rpm,
            source='youtube_analytics_api',
            synced_at=CURRENT_TIMESTAMP
        """, (
            video_id,
            title,
            analytics_date,
            views,
            revenue,
            minutes,
            rpm
        ))

        saved += 1

    connection.commit()
    connection.close()

    update_videos_with_youtube_revenue()

    return saved


def save_youtube_revenue_period_rows(rows):
    """
    Saves exact YouTube Analytics totals by period.
    This is the source of truth for Revenue Tracker:
    lifetime, 365d, 90d, 28d, 7d.
    """
    connection = create_connection()
    cursor = connection.cursor()

    saved = 0

    for row in rows:
        video_id = str(row.get("video_id") or "").strip() or "__CHANNEL__"
        title = str(row.get("title") or "").strip()
        period_type = normalize_period_type(row.get("period_type") or row.get("period") or "lifetime")
        start_date = normalize_analytics_date(row.get("start_date"))
        end_date = normalize_analytics_date(row.get("end_date"))
        views = int(float(row.get("views") or 0))
        revenue = round(float(row.get("estimated_revenue") or row.get("amount") or 0), 6)
        minutes = round(float(row.get("estimated_minutes_watched") or 0), 4)
        rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 4)

        cursor.execute("""
        INSERT INTO youtube_revenue_period (
            video_id, title, period_type, start_date, end_date, views,
            estimated_revenue, estimated_minutes_watched, rpm, source, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'youtube_analytics_api', CURRENT_TIMESTAMP)
        ON CONFLICT(video_id, period_type) DO UPDATE SET
            title=excluded.title,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            views=excluded.views,
            estimated_revenue=excluded.estimated_revenue,
            estimated_minutes_watched=excluded.estimated_minutes_watched,
            rpm=excluded.rpm,
            source='youtube_analytics_api',
            synced_at=CURRENT_TIMESTAMP
        """, (
            video_id,
            title,
            period_type,
            start_date,
            end_date,
            views,
            revenue,
            minutes,
            rpm
        ))

        saved += 1

    connection.commit()
    connection.close()

    update_videos_with_youtube_revenue()

    return saved


def log_youtube_revenue_sync(sync_type, start_date, end_date, channel_rows, video_rows, status, message=""):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO youtube_revenue_sync_log (
        sync_type, start_date, end_date, channel_rows, video_rows, status, message, synced_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        sync_type,
        start_date,
        end_date,
        int(channel_rows or 0),
        int(video_rows or 0),
        status,
        message
    ))

    connection.commit()
    connection.close()


def get_latest_youtube_revenue_sync():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM youtube_revenue_sync_log
    ORDER BY synced_at DESC, id DESC
    LIMIT 1
    """)

    row = cursor.fetchone()
    connection.close()

    return dict(row) if row else None


def get_youtube_revenue_date_range():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        MIN(start_date) as first_date,
        MAX(end_date) as last_date,
        COUNT(*) as total_rows
    FROM youtube_revenue_period
    """)

    row = cursor.fetchone()

    if row and int(row["total_rows"] or 0) > 0:
        connection.close()
        return {
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "total_rows": row["total_rows"] or 0
        }

    cursor.execute("""
    SELECT
        MIN(analytics_date) as first_date,
        MAX(analytics_date) as last_date,
        COUNT(*) as total_rows
    FROM youtube_revenue_daily
    """)

    row = cursor.fetchone()
    connection.close()

    return {
        "first_date": row["first_date"] if row else None,
        "last_date": row["last_date"] if row else None,
        "total_rows": row["total_rows"] if row else 0
    }


def get_youtube_period_row(video_id, period_key):
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM youtube_revenue_period
    WHERE video_id=?
    AND period_type=?
    LIMIT 1
    """, (video_id, normalize_period_type(period_key)))

    row = cursor.fetchone()
    connection.close()

    return dict(row) if row else None


def period_start_date(period_key):
    from datetime import date, timedelta

    period_key = normalize_period_type(period_key)

    if period_key == "lifetime":
        return None

    days = REVENUE_PERIOD_WINDOWS.get(period_key)

    if not days:
        return None

    return (date.today() - timedelta(days=days - 1)).isoformat()


def get_youtube_channel_period(period_key):
    period_key = normalize_period_type(period_key)
    period_row = get_youtube_period_row("__CHANNEL__", period_key)

    if period_row:
        views = int(period_row.get("views") or 0)
        raw_revenue = round(float(period_row.get("estimated_revenue") or 0), 2)
        revenue = apply_private_hidden_adjustment(period_key, raw_revenue)
        private_adjustment = get_private_hidden_lifetime_adjustment() if period_key == "lifetime" else 0
        minutes = round(float(period_row.get("estimated_minutes_watched") or 0), 2)

        return {
            "period": period_key,
            "views": views,
            "estimated_revenue": revenue,
            "amount": revenue,
            "estimated_minutes_watched": minutes,
            "rpm": calculate_rpm(revenue, views),
            "start_date": period_row.get("start_date") or "",
            "end_date": period_row.get("end_date") or "",
            "source": "youtube_analytics_api",
            "raw_estimated_revenue": raw_revenue,
            "private_hidden_adjustment": private_adjustment
        }

    # Fallback to old daily rows if period snapshots have not been synced yet.
    start_date = period_start_date(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    if start_date:
        cursor.execute("""
        SELECT
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id='__CHANNEL__'
        AND analytics_date >= ?
        """, (start_date,))
    else:
        cursor.execute("""
        SELECT
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id='__CHANNEL__'
        """)

    row = cursor.fetchone()
    connection.close()

    views = int(row["views"] or 0) if row else 0
    raw_revenue = round(float(row["revenue"] or 0), 2) if row else 0
    revenue = apply_private_hidden_adjustment(period_key, raw_revenue)
    private_adjustment = get_private_hidden_lifetime_adjustment() if period_key == "lifetime" else 0
    minutes = round(float(row["minutes"] or 0), 2) if row else 0

    return {
        "period": period_key,
        "views": views,
        "estimated_revenue": revenue,
        "amount": revenue,
        "estimated_minutes_watched": minutes,
        "rpm": calculate_rpm(revenue, views),
        "start_date": start_date or "",
        "end_date": "",
        "source": "youtube_analytics_api_daily_fallback",
        "raw_estimated_revenue": raw_revenue,
        "private_hidden_adjustment": private_adjustment
    }


def get_youtube_video_period(video_id, period_key):
    period_key = normalize_period_type(period_key)
    period_row = get_youtube_period_row(video_id, period_key)

    if period_row:
        views = int(period_row.get("views") or 0)
        revenue = round(float(period_row.get("estimated_revenue") or 0), 2)
        minutes = round(float(period_row.get("estimated_minutes_watched") or 0), 2)

        return {
            "video_id": video_id,
            "title": period_row.get("title") or "",
            "period_type": period_key,
            "amount": revenue,
            "estimated_revenue": revenue,
            "views": views,
            "estimated_minutes_watched": minutes,
            "rpm": calculate_rpm(revenue, views),
            "start_date": period_row.get("start_date") or "",
            "end_date": period_row.get("end_date") or "",
            "notes": "YouTube Analytics API",
            "source": "youtube_analytics_api"
        }

    start_date = period_start_date(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    if start_date:
        cursor.execute("""
        SELECT
            video_id,
            MAX(title) as title,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id=?
        AND analytics_date >= ?
        GROUP BY video_id
        """, (video_id, start_date))
    else:
        cursor.execute("""
        SELECT
            video_id,
            MAX(title) as title,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue,
            SUM(estimated_minutes_watched) as minutes
        FROM youtube_revenue_daily
        WHERE video_id=?
        GROUP BY video_id
        """, (video_id,))

    row = cursor.fetchone()
    connection.close()

    if not row:
        return {
            "video_id": video_id,
            "title": "",
            "period_type": period_key,
            "amount": 0,
            "estimated_revenue": 0,
            "views": 0,
            "rpm": 0,
            "start_date": start_date or "",
            "end_date": "",
            "notes": "YouTube Analytics API"
        }

    views = int(row["views"] or 0)
    revenue = round(float(row["revenue"] or 0), 2)
    minutes = round(float(row["minutes"] or 0), 2)

    return {
        "video_id": row["video_id"],
        "title": row["title"] or "",
        "period_type": period_key,
        "amount": revenue,
        "estimated_revenue": revenue,
        "views": views,
        "estimated_minutes_watched": minutes,
        "rpm": calculate_rpm(revenue, views),
        "start_date": start_date or "",
        "end_date": "",
        "notes": "YouTube Analytics API",
        "source": "youtube_analytics_api_daily_fallback"
    }


def get_youtube_channel_revenue_entries():
    entries = []

    for period in REVENUE_PERIOD_ORDER:
        item = get_youtube_channel_period(period)

        entries.append({
            "id": f"youtube-channel-{period}",
            "period_type": period,
            "amount": item["estimated_revenue"],
            "views": item["views"],
            "rpm": item["rpm"],
            "start_date": item["start_date"],
            "end_date": item["end_date"],
            "notes": "Auto synced from YouTube Analytics API",
            "source": "youtube_analytics_api"
        })

    return entries


def get_youtube_video_revenue_entries():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        title,
        period_type,
        start_date,
        end_date,
        views,
        estimated_revenue,
        estimated_minutes_watched,
        rpm,
        synced_at
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    ORDER BY estimated_revenue DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    if rows:
        return [
            {
                "id": f"youtube-video-{row['video_id']}-{row['period_type']}",
                "video_id": row["video_id"],
                "title": row["title"] or "",
                "period_type": row["period_type"],
                "amount": round(float(row["estimated_revenue"] or 0), 2),
                "estimated_revenue": round(float(row["estimated_revenue"] or 0), 2),
                "views": int(row["views"] or 0),
                "estimated_minutes_watched": round(float(row["estimated_minutes_watched"] or 0), 2),
                "rpm": round(float(row["rpm"] or 0), 2),
                "start_date": row["start_date"] or "",
                "end_date": row["end_date"] or "",
                "notes": "YouTube Analytics API",
                "source": "youtube_analytics_api",
                "synced_at": row["synced_at"]
            }
            for row in rows
        ]

    # Fallback for old daily data.
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT DISTINCT video_id
    FROM youtube_revenue_daily
    WHERE video_id != '__CHANNEL__'
    ORDER BY video_id
    """)

    video_ids = [row["video_id"] for row in cursor.fetchall()]
    connection.close()

    entries = []

    for video_id in video_ids:
        for period in REVENUE_PERIOD_ORDER:
            item = get_youtube_video_period(video_id, period)
            item["id"] = f"youtube-video-{video_id}-{period}"
            item["source"] = "youtube_analytics_api"
            entries.append(item)

    return entries


def get_top_youtube_video_revenue(period_key="lifetime", limit=50):
    period_key = normalize_period_type(period_key)

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        title,
        period_type,
        start_date,
        end_date,
        views,
        estimated_revenue,
        estimated_minutes_watched,
        rpm,
        synced_at
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    AND period_type=?
    ORDER BY estimated_revenue DESC
    LIMIT ?
    """, (period_key, int(limit or 50)))

    rows = cursor.fetchall()
    connection.close()

    return [
        {
            "rank": index + 1,
            "video_id": row["video_id"],
            "title": row["title"] or "",
            "period_type": row["period_type"],
            "amount": round(float(row["estimated_revenue"] or 0), 2),
            "estimated_revenue": round(float(row["estimated_revenue"] or 0), 2),
            "views": int(row["views"] or 0),
            "rpm": round(float(row["rpm"] or 0), 2),
            "start_date": row["start_date"] or "",
            "end_date": row["end_date"] or "",
            "synced_at": row["synced_at"]
        }
        for index, row in enumerate(rows)
    ]


def get_youtube_revenue_summary():
    channel_by_period = {}
    channel_views_by_period = {}
    channel_rpm_by_period = {}
    channel_date_ranges = {}
    video_by_period = {}
    video_views_by_period = {}
    video_rpm_by_period = {}

    video_entries = get_youtube_video_revenue_entries()
    channel_entries = get_youtube_channel_revenue_entries()

    for period in REVENUE_PERIOD_ORDER:
        channel_item = get_youtube_channel_period(period)
        channel_by_period[period] = channel_item["estimated_revenue"]
        channel_views_by_period[period] = channel_item["views"]
        channel_rpm_by_period[period] = channel_item["rpm"]
        channel_date_ranges[period] = {
            "start_date": channel_item.get("start_date", ""),
            "end_date": channel_item.get("end_date", "")
        }

        period_video_entries = [
            item for item in video_entries
            if item.get("period_type") == period
        ]

        period_revenue = round(sum(float(item.get("amount") or 0) for item in period_video_entries), 2)
        period_views = sum(int(item.get("views") or 0) for item in period_video_entries)

        video_by_period[period] = period_revenue
        video_views_by_period[period] = period_views
        video_rpm_by_period[period] = calculate_rpm(period_revenue, period_views)

    date_range = get_youtube_revenue_date_range()

    return {
        "source": "youtube_analytics_api",
        "is_auto_synced": True,
        "periods": REVENUE_PERIOD_ORDER,
        "total_channel_manual_revenue": channel_by_period.get("lifetime", 0),
        "total_video_manual_revenue": video_by_period.get("lifetime", 0),
        "total_channel_youtube_revenue": channel_by_period.get("lifetime", 0),
        "total_video_youtube_revenue": video_by_period.get("lifetime", 0),
        "channel_revenue_entries": len(channel_entries),
        "video_revenue_entries": len(video_entries),
        "channel_by_period": channel_by_period,
        "channel_views_by_period": channel_views_by_period,
        "channel_rpm_by_period": channel_rpm_by_period,
        "channel_date_ranges": channel_date_ranges,
        "private_hidden_lifetime_adjustment": get_private_hidden_lifetime_adjustment(),
        "private_hidden_adjustment_note": "No manual private-video adjustment is currently added. YouTube Analytics channel totals should already include private/unlisted video revenue for the owner account.",
        "video_by_period": video_by_period,
        "video_views_by_period": video_views_by_period,
        "video_rpm_by_period": video_rpm_by_period,
        "first_analytics_date": date_range.get("first_date"),
        "last_analytics_date": date_range.get("last_date"),
        "total_daily_rows": date_range.get("total_rows"),
        "latest_sync": get_latest_youtube_revenue_sync()
    }


def get_youtube_revenue_status():
    summary = get_youtube_revenue_summary()
    latest_sync = get_latest_youtube_revenue_sync()

    return {
        "enabled": True,
        "source": "youtube_analytics_api",
        "message": "Revenue Tracker is using exact YouTube Analytics API period totals when synced. Default sync uses YouTube Studio-style completed-day windows.",
        "latest_sync": latest_sync,
        "first_analytics_date": summary.get("first_analytics_date"),
        "last_analytics_date": summary.get("last_analytics_date"),
        "total_daily_rows": summary.get("total_daily_rows"),
        "channel_lifetime_revenue": summary.get("total_channel_youtube_revenue"),
        "video_lifetime_revenue": summary.get("total_video_youtube_revenue"),
        "channel_by_period": summary.get("channel_by_period"),
        "video_by_period": summary.get("video_by_period"),
        "channel_date_ranges": summary.get("channel_date_ranges"),
        "private_hidden_lifetime_adjustment": summary.get("private_hidden_lifetime_adjustment"),
        "private_hidden_adjustment_note": summary.get("private_hidden_adjustment_note")
    }


def update_videos_with_youtube_revenue():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        video_id,
        views,
        estimated_revenue
    FROM youtube_revenue_period
    WHERE video_id != '__CHANNEL__'
    AND period_type='lifetime'
    """)

    rows = cursor.fetchall()

    if not rows:
        cursor.execute("""
        SELECT
            video_id,
            SUM(views) as views,
            SUM(estimated_revenue) as revenue
        FROM youtube_revenue_daily
        WHERE video_id != '__CHANNEL__'
        GROUP BY video_id
        """)

        rows = cursor.fetchall()

        for row in rows:
            views = int(row["views"] or 0)
            revenue = round(float(row["revenue"] or 0), 2)
            rpm = calculate_rpm(revenue, views)

            cursor.execute("""
            UPDATE videos
            SET
                estimated_revenue=?,
                estimated_rpm=?,
                yt_estimated_revenue=?,
                yt_estimated_rpm=?,
                yt_revenue_synced_at=CURRENT_TIMESTAMP
            WHERE video_id=?
            """, (
                revenue,
                rpm,
                revenue,
                rpm,
                row["video_id"]
            ))

        connection.commit()
        connection.close()
        return

    for row in rows:
        views = int(row["views"] or 0)
        revenue = round(float(row["estimated_revenue"] or 0), 2)
        rpm = calculate_rpm(revenue, views)

        cursor.execute("""
        UPDATE videos
        SET
            estimated_revenue=?,
            estimated_rpm=?,
            yt_estimated_revenue=?,
            yt_estimated_rpm=?,
            yt_revenue_synced_at=CURRENT_TIMESTAMP
        WHERE video_id=?
        """, (
            revenue,
            rpm,
            revenue,
            rpm,
            row["video_id"]
        ))

    connection.commit()
    connection.close()



def get_youtube_player_revenue_summary(videos, period_type="lifetime"):
    """
    Groups YouTube Analytics API video period revenue by detected player.
    This replaces manual revenue grouping when API revenue rows exist.
    """
    period_type = normalize_period_type(period_type)

    player_map = {}

    for video in videos:
        player = video.get("player_name") or "Unknown"

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "manual_revenue": 0,
                "youtube_revenue": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0,
                "rpm_values": []
            }

        player_map[player]["total_videos"] += 1
        player_map[player]["total_views"] += int(video.get("views") or 0)

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT video_id, title, views, estimated_revenue, rpm
    FROM youtube_revenue_period
    WHERE period_type=?
    AND video_id != '__CHANNEL__'
    """, (period_type,))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    video_to_player = {
        str(video.get("video_id") or ""): video.get("player_name") or "Unknown"
        for video in videos
    }

    for row in rows:
        video_id = str(row.get("video_id") or "")
        player = video_to_player.get(video_id, "Unknown")

        if player not in player_map:
            player_map[player] = {
                "player": player,
                "total_revenue": 0,
                "manual_revenue": 0,
                "youtube_revenue": 0,
                "manual_revenue_videos": 0,
                "youtube_revenue_videos": 0,
                "total_videos": 0,
                "total_views": 0,
                "rpm_values": []
            }

        revenue = round(float(row.get("estimated_revenue") or 0), 2)
        views = int(row.get("views") or 0)
        rpm = float(row.get("rpm") or 0)

        if revenue > 0:
            player_map[player]["total_revenue"] += revenue
            player_map[player]["youtube_revenue"] += revenue
            player_map[player]["youtube_revenue_videos"] += 1
            player_map[player]["manual_revenue_videos"] += 1

        if views > 0 and player_map[player]["total_views"] <= 0:
            player_map[player]["total_views"] += views

        if rpm > 0:
            player_map[player]["rpm_values"].append(rpm)

    results = []

    for player, item in player_map.items():
        revenue_videos = int(item["youtube_revenue_videos"] or 0)

        average_rpm = (
            round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2)
            if item["rpm_values"]
            else 0
        )

        average_revenue = (
            round(item["total_revenue"] / revenue_videos, 2)
            if revenue_videos > 0
            else 0
        )

        results.append({
            "player": player,
            "total_revenue": round(item["total_revenue"], 2),
            "manual_revenue": round(item["total_revenue"], 2),
            "youtube_revenue": round(item["youtube_revenue"], 2),
            "average_revenue": average_revenue,
            "average_rpm": average_rpm,
            "manual_revenue_videos": revenue_videos,
            "youtube_revenue_videos": revenue_videos,
            "total_videos": item["total_videos"],
            "total_views": item["total_views"]
        })

    return sorted(results, key=lambda x: (x["total_revenue"], x["total_views"]), reverse=True)



def get_best_revenue_for_video(video, period_type="lifetime"):
    """
    Single video money helper for all recommendation tools.
    Source order:
    1. synced YouTube Analytics / Revenue Tracker period row
    2. synced values stored on the videos table
    3. zero if no synced API data exists

    Manual revenue is intentionally not used for predictions.
    """
    period_type = normalize_period_type(period_type)
    video_id = str(video.get("video_id") or "").strip()

    if video_id and youtube_rows_exist():
        row = get_youtube_period_row(video_id, period_type)
        if row:
            views = int(row.get("views") or 0)
            revenue = round(float(row.get("estimated_revenue") or 0), 2)
            rpm = round(float(row.get("rpm") or calculate_rpm(revenue, views)), 2)
            return {
                "video_id": video_id,
                "period_type": period_type,
                "total_revenue": revenue,
                "estimated_revenue": revenue,
                "average_rpm": rpm,
                "rpm": rpm,
                "views": views,
                "entries": 1 if revenue > 0 or views > 0 or rpm > 0 else 0,
                "source": "youtube_analytics_api_revenue_tracker",
                "periods": {
                    period_type: revenue,
                    "lifetime": get_youtube_video_period(video_id, "lifetime").get("amount", 0),
                    "365d": get_youtube_video_period(video_id, "365d").get("amount", 0),
                    "90d": get_youtube_video_period(video_id, "90d").get("amount", 0),
                    "28d": get_youtube_video_period(video_id, "28d").get("amount", 0),
                    "7d": get_youtube_video_period(video_id, "7d").get("amount", 0),
                }
            }

    views = int(video.get("views") or 0)
    revenue = round(float(video.get("yt_estimated_revenue") or video.get("estimated_revenue") or 0), 2)
    rpm = round(float(video.get("yt_estimated_rpm") or video.get("estimated_rpm") or calculate_rpm(revenue, views)), 2)

    return {
        "video_id": video_id,
        "period_type": period_type,
        "total_revenue": revenue,
        "estimated_revenue": revenue,
        "average_rpm": rpm,
        "rpm": rpm,
        "views": views,
        "entries": 1 if revenue > 0 or rpm > 0 else 0,
        "source": "synced_video_row" if revenue > 0 or rpm > 0 else "no_synced_revenue"
    }


def get_best_player_revenue_summary(videos, period_type="lifetime"):
    """
    Returns synced YouTube Analytics player revenue only.
    """
    if youtube_rows_exist():
        return get_youtube_player_revenue_summary(videos, period_type)

    return []


def get_best_channel_rpm(period_type="lifetime"):
    """
    Returns synced YouTube Analytics channel RPM only.
    """
    if youtube_rows_exist():
        return get_youtube_channel_period(period_type).get("rpm", 0)

    return 0


def youtube_rows_exist():
    status = get_youtube_revenue_date_range()
    return int(status.get("total_rows") or 0) > 0


def get_best_revenue_summary():
    """
    Single source of truth: synced YouTube Analytics / Revenue Tracker rows only.
    Manual revenue is intentionally ignored.
    """
    if youtube_rows_exist():
        summary = get_youtube_revenue_summary()
        summary["data_source"] = "youtube_analytics_api_revenue_tracker"
        return summary

    return {
        "channel_revenue_entries": 0,
        "video_revenue_entries": 0,
        "total_channel_youtube_revenue": 0,
        "total_video_youtube_revenue": 0,
        "total_channel_manual_revenue": 0,
        "total_video_manual_revenue": 0,
        "channel_by_period": {},
        "video_by_period": {},
        "channel_views_by_period": {},
        "video_views_by_period": {},
        "channel_rpm_by_period": {},
        "video_rpm_by_period": {},
        "private_hidden_lifetime_adjustment": get_private_hidden_lifetime_adjustment(),
        "data_source": "youtube_analytics_api_only_no_rows_yet"
    }


def get_best_channel_revenue_entries():
    """
    Returns channel revenue rows from synced YouTube Analytics only.
    """
    if youtube_rows_exist():
        return get_youtube_channel_revenue_entries()

    return []


def get_best_video_revenue_entries():
    """
    Returns video revenue rows from synced YouTube Analytics only.
    """
    if youtube_rows_exist():
        return get_youtube_video_revenue_entries()

    return []


    return []

