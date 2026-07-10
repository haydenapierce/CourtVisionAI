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




def create_community_automation_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS community_post_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_date TEXT DEFAULT '',
        post_time TEXT DEFAULT '',
        post_type TEXT DEFAULT 'poll',
        topic TEXT DEFAULT '',
        post_text TEXT DEFAULT '',
        option_a TEXT DEFAULT '',
        option_b TEXT DEFAULT '',
        option_c TEXT DEFAULT '',
        option_d TEXT DEFAULT '',
        linked_video_id TEXT DEFAULT '',
        linked_video_title TEXT DEFAULT '',
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        votes INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        subscribers_gained INTEGER DEFAULT 0,
        views_generated INTEGER DEFAULT 0,
        revenue_lift REAL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_date ON community_post_results(post_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_type ON community_post_results(post_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_topic ON community_post_results(topic)")


def ensure_community_automation_tables():
    connection = create_connection()
    cursor = connection.cursor()
    create_community_automation_tables(cursor)
    connection.commit()
    connection.close()


def save_community_post_result(data):
    ensure_community_automation_tables()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO community_post_results (
        post_date, post_time, post_type, topic, post_text,
        option_a, option_b, option_c, option_d,
        linked_video_id, linked_video_title,
        likes, comments, votes, shares, subscribers_gained,
        views_generated, revenue_lift, notes, created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        data.get("post_date", ""),
        data.get("post_time", ""),
        data.get("post_type", "poll"),
        data.get("topic", ""),
        data.get("post_text", ""),
        data.get("option_a", ""),
        data.get("option_b", ""),
        data.get("option_c", ""),
        data.get("option_d", ""),
        data.get("linked_video_id", ""),
        data.get("linked_video_title", ""),
        int(data.get("likes") or 0),
        int(data.get("comments") or 0),
        int(data.get("votes") or 0),
        int(data.get("shares") or 0),
        int(data.get("subscribers_gained") or 0),
        int(data.get("views_generated") or 0),
        float(data.get("revenue_lift") or 0),
        data.get("notes", "")
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def get_community_post_results(limit=50):
    ensure_community_automation_tables()

    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("""
    SELECT *
    FROM community_post_results
    ORDER BY post_date DESC, created_at DESC, id DESC
    LIMIT ?
    """, (int(limit or 50),))
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def get_community_performance_summary():
    ensure_community_automation_tables()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        COUNT(*) as total_posts,
        COALESCE(SUM(likes), 0) as total_likes,
        COALESCE(SUM(comments), 0) as total_comments,
        COALESCE(SUM(votes), 0) as total_votes,
        COALESCE(SUM(subscribers_gained), 0) as total_subscribers,
        COALESCE(SUM(views_generated), 0) as total_views_generated,
        COALESCE(SUM(revenue_lift), 0) as total_revenue_lift,
        COALESCE(AVG(votes), 0) as average_votes,
        COALESCE(AVG(likes), 0) as average_likes,
        COALESCE(AVG(comments), 0) as average_comments
    FROM community_post_results
    """)
    overall = dict(cursor.fetchone() or {})

    cursor.execute("""
    SELECT
        post_type,
        COUNT(*) as posts,
        COALESCE(AVG(votes + likes + comments + shares), 0) as engagement_score,
        COALESCE(AVG(votes), 0) as average_votes,
        COALESCE(AVG(likes), 0) as average_likes,
        COALESCE(AVG(comments), 0) as average_comments
    FROM community_post_results
    GROUP BY post_type
    ORDER BY engagement_score DESC
    """)
    type_stats = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
    SELECT
        post_time,
        COUNT(*) as posts,
        COALESCE(AVG(votes + likes + comments + shares), 0) as engagement_score
    FROM community_post_results
    WHERE post_time != ''
    GROUP BY post_time
    ORDER BY engagement_score DESC
    LIMIT 1
    """)
    best_time_row = cursor.fetchone()

    cursor.execute("""
    SELECT
        topic,
        COUNT(*) as posts,
        COALESCE(AVG(votes + likes + comments + shares), 0) as engagement_score
    FROM community_post_results
    WHERE topic != ''
    GROUP BY topic
    ORDER BY engagement_score DESC
    LIMIT 1
    """)
    best_topic_row = cursor.fetchone()

    connection.close()

    best_type = type_stats[0]["post_type"] if type_stats else "poll"

    return {
        **overall,
        "post_type_stats": type_stats,
        "best_type": best_type,
        "best_time": best_time_row["post_time"] if best_time_row else "7:00 PM",
        "best_topic": best_topic_row["topic"] if best_topic_row else "player debates",
        "engagement_score": round(float(overall.get("average_votes") or 0) + float(overall.get("average_likes") or 0) + float(overall.get("average_comments") or 0), 2)
    }

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
    create_community_automation_tables(cursor)
    create_performance_indexes(cursor)
    mark_schema_initialized(cursor)

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
    create_community_automation_tables(cursor)

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


# =========================================================
# COMMUNITY AUTOMATION V2 PERSISTENCE OVERRIDES
# Keeps old columns for compatibility, adds editable poll percentages
# and update support without removing any existing database data.
# =========================================================

def create_community_automation_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS community_post_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_date TEXT DEFAULT '',
        post_time TEXT DEFAULT '',
        post_type TEXT DEFAULT 'Next Upload Poll',
        topic TEXT DEFAULT '',
        post_text TEXT DEFAULT '',
        option_a TEXT DEFAULT '',
        option_b TEXT DEFAULT '',
        option_c TEXT DEFAULT '',
        option_d TEXT DEFAULT '',
        option_a_percent REAL DEFAULT 0,
        option_b_percent REAL DEFAULT 0,
        option_c_percent REAL DEFAULT 0,
        option_d_percent REAL DEFAULT 0,
        poll_winner TEXT DEFAULT '',
        trivia_answer TEXT DEFAULT '',
        linked_video_id TEXT DEFAULT '',
        linked_video_title TEXT DEFAULT '',
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        votes INTEGER DEFAULT 0,
        impressions INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        subscribers_gained INTEGER DEFAULT 0,
        views_generated INTEGER DEFAULT 0,
        revenue_lift REAL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    for column, column_type in [
        ("option_a_percent", "REAL DEFAULT 0"),
        ("option_b_percent", "REAL DEFAULT 0"),
        ("option_c_percent", "REAL DEFAULT 0"),
        ("option_d_percent", "REAL DEFAULT 0"),
        ("poll_winner", "TEXT DEFAULT ''"),
        ("trivia_answer", "TEXT DEFAULT ''"),
        ("impressions", "INTEGER DEFAULT 0"),
    ]:
        try:
            add_column_if_missing(cursor, "community_post_results", column, column_type)
        except Exception:
            pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_date ON community_post_results(post_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_type ON community_post_results(post_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_topic ON community_post_results(topic)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_poll_winner ON community_post_results(poll_winner)")


def ensure_community_automation_tables():
    connection = create_connection()
    cursor = connection.cursor()
    create_community_automation_tables(cursor)
    connection.commit()
    connection.close()


def _community_clean_number(value, default=0, cast=float):
    try:
        return cast(value or default)
    except Exception:
        return default


def _community_payload(data):
    return {
        "post_date": data.get("post_date", ""),
        "post_time": data.get("post_time", ""),
        "post_type": data.get("post_type", "Next Upload Poll"),
        "topic": data.get("topic", "") or data.get("poll_winner", ""),
        "post_text": data.get("post_text", ""),
        "option_a": data.get("option_a", "") or data.get("poll_option_1", ""),
        "option_b": data.get("option_b", "") or data.get("poll_option_2", ""),
        "option_c": data.get("option_c", "") or data.get("poll_option_3", ""),
        "option_d": data.get("option_d", "") or data.get("poll_option_4", ""),
        "option_a_percent": _community_clean_number(data.get("option_a_percent"), 0, float),
        "option_b_percent": _community_clean_number(data.get("option_b_percent"), 0, float),
        "option_c_percent": _community_clean_number(data.get("option_c_percent"), 0, float),
        "option_d_percent": _community_clean_number(data.get("option_d_percent"), 0, float),
        "poll_winner": data.get("poll_winner", ""),
        "trivia_answer": data.get("trivia_answer", ""),
        "linked_video_id": data.get("linked_video_id", ""),
        "linked_video_title": data.get("linked_video_title", ""),
        "likes": _community_clean_number(data.get("likes"), 0, int),
        "comments": _community_clean_number(data.get("comments"), 0, int),
        "votes": _community_clean_number(data.get("votes"), 0, int),
        "impressions": 0,
        "views_generated": 0,
    }


def save_community_post_result(data):
    ensure_community_automation_tables()
    payload = _community_payload(data or {})
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO community_post_results (
        post_date, post_time, post_type, topic, post_text,
        option_a, option_b, option_c, option_d,
        option_a_percent, option_b_percent, option_c_percent, option_d_percent,
        poll_winner, trivia_answer,
        linked_video_id, linked_video_title,
        likes, comments, votes, impressions, views_generated,
        created_at, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        payload["post_date"], payload["post_time"], payload["post_type"], payload["topic"], payload["post_text"],
        payload["option_a"], payload["option_b"], payload["option_c"], payload["option_d"],
        payload["option_a_percent"], payload["option_b_percent"], payload["option_c_percent"], payload["option_d_percent"],
        payload["poll_winner"], payload["trivia_answer"],
        payload["linked_video_id"], payload["linked_video_title"],
        payload["likes"], payload["comments"], payload["votes"], payload["impressions"], payload["views_generated"]
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_community_post_result(row_id, data):
    ensure_community_automation_tables()
    payload = _community_payload(data or {})
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("""
    UPDATE community_post_results
    SET post_date=?, post_time=?, post_type=?, topic=?, post_text=?,
        option_a=?, option_b=?, option_c=?, option_d=?,
        option_a_percent=?, option_b_percent=?, option_c_percent=?, option_d_percent=?,
        poll_winner=?, trivia_answer=?,
        linked_video_id=?, linked_video_title=?,
        likes=?, comments=?, votes=?, impressions=?, views_generated=?,
        updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, (
        payload["post_date"], payload["post_time"], payload["post_type"], payload["topic"], payload["post_text"],
        payload["option_a"], payload["option_b"], payload["option_c"], payload["option_d"],
        payload["option_a_percent"], payload["option_b_percent"], payload["option_c_percent"], payload["option_d_percent"],
        payload["poll_winner"], payload["trivia_answer"],
        payload["linked_video_id"], payload["linked_video_title"],
        payload["likes"], payload["comments"], payload["votes"], payload["impressions"], payload["views_generated"],
        int(row_id or 0)
    ))
    connection.commit()
    connection.close()
    return int(row_id or 0)


def get_community_post_results(limit=50):
    ensure_community_automation_tables()
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("""
    SELECT *
    FROM community_post_results
    ORDER BY COALESCE(NULLIF(post_date, ''), created_at) DESC, created_at DESC, id DESC
    LIMIT ?
    """, (int(limit or 50),))
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def get_community_post_history(limit=50):
    return get_community_post_results(limit)


def get_community_post_learning():
    rows = get_community_post_results(500)
    if not rows:
        return {
            "best_post_type": "Next Upload Poll",
            "best_type_score": 0,
            "best_time": "7:00 PM",
            "average_likes": 0,
            "average_comments": 0,
            "average_votes": 0,
            "top_topics": []
        }

    by_type = {}
    by_time = {}
    by_topic = {}
    total_likes = total_comments = total_votes = 0

    for row in rows:
        score = int(row.get("likes") or 0) + int(row.get("comments") or 0) * 3 + int(row.get("votes") or 0) * 0.35
        post_type = row.get("post_type") or "Next Upload Poll"
        by_type.setdefault(post_type, [0, 0])
        by_type[post_type][0] += score
        by_type[post_type][1] += 1
        if row.get("post_time"):
            by_time.setdefault(row.get("post_time"), [0, 0])
            by_time[row.get("post_time")][0] += score
            by_time[row.get("post_time")][1] += 1
        topic = row.get("poll_winner") or row.get("topic") or ""
        if topic:
            by_topic[topic] = by_topic.get(topic, 0) + score
        total_likes += int(row.get("likes") or 0)
        total_comments += int(row.get("comments") or 0)
        total_votes += int(row.get("votes") or 0)

    best_type, best_type_score = "Next Upload Poll", 0
    for key, value in by_type.items():
        avg = value[0] / max(1, value[1])
        if avg > best_type_score:
            best_type, best_type_score = key, avg

    best_time, best_time_score = "7:00 PM", 0
    for key, value in by_time.items():
        avg = value[0] / max(1, value[1])
        if avg > best_time_score:
            best_time, best_time_score = key, avg

    return {
        "best_post_type": best_type,
        "best_type_score": round(best_type_score, 2),
        "best_time": best_time,
        "average_likes": round(total_likes / max(1, len(rows)), 1),
        "average_comments": round(total_comments / max(1, len(rows)), 1),
        "average_votes": round(total_votes / max(1, len(rows)), 1),
        "top_topics": [{"topic": k, "score": round(v, 2)} for k, v in sorted(by_topic.items(), key=lambda item: item[1], reverse=True)[:8]]
    }

# =========================================================
# COMMUNITY AUTOMATION AI HISTORY SEED + DEEP LEARNING OVERRIDE
# Added for all-time Community tab learning. Keeps old data safe.
# =========================================================

COMMUNITY_HISTORY_SEED_VERSION = "community_history_seed_2026_07_08_v1"

COMMUNITY_HISTORY_SEED_POSTS = [
    {"post_date":"2026-06-10","post_type":"Player Debate","post_text":"Who’s winning the NBA Finals?","option_a":"San Antonio Spurs","option_b":"New York Knicks","option_a_percent":44,"option_b_percent":56,"poll_winner":"New York Knicks","votes":632,"likes":13,"comments":2},
    {"post_date":"2026-06-10","post_type":"Next Upload Poll","post_text":"Which player deserves a Top 10 Career Dunks video next?","option_a":"Shawn Kemp","option_b":"Vince Carter","option_c":"Dominique Wilkins","option_d":"Clyde Drexler","option_a_percent":22,"option_b_percent":46,"option_c_percent":20,"option_d_percent":13,"poll_winner":"Vince Carter","votes":102,"likes":5,"comments":2},
    {"post_date":"2025-07-01","post_type":"Upload Teaser","post_text":"New video is out, go check it out!","linked_video_title":"Julius Randle Top 10 Plays of Career","likes":1},
    {"post_date":"2025-06-24","post_type":"Next Upload Poll","post_text":"Which Top 10 video do you guys want next?","option_a":"Julius Randle","option_b":"Jalen Brunson","option_c":"Donte DiVincenzo","option_d":"Naz Reid","option_e":"Rudy Gobert","option_a_percent":15,"option_b_percent":53,"option_c_percent":3,"option_d_percent":9,"option_e_percent":20,"poll_winner":"Jalen Brunson","votes":92,"likes":6,"comments":4},
    {"post_date":"2025-06-17","post_type":"Upload Teaser","post_text":"New video is up, go check it out!","linked_video_title":"Gordon Hayward Top 10 Plays of Career","likes":3},
    {"post_date":"2024-07-01","post_type":"Upload Teaser","post_text":"New Top 10 video is up, go check it out! Thanks for watching!","linked_video_title":"Victor Wembanyama Top 10 Plays of Rookie Season","likes":5},
    {"post_date":"2024-06-24","post_type":"Player Debate","post_text":"Who will win the NBA Finals this year?","option_a":"Celtics","option_b":"Nuggets","option_c":"Thunder","option_d":"Wolves","option_a_percent":40,"option_b_percent":45,"option_c_percent":6,"option_d_percent":8,"poll_winner":"Nuggets","votes":836,"likes":16,"comments":7},
    {"post_date":"2024-06-17","post_type":"Player Debate","post_text":"Could Caitlin Clark play in the NBA?","option_a":"Yes","option_b":"No","option_a_percent":23,"option_b_percent":77,"poll_winner":"No","votes":532,"likes":8,"comments":7},
    {"post_date":"2024-06-10","post_type":"Upload Teaser","post_text":"New Top 10 video is uploaded, go show support!","linked_video_title":"Pete Maravich Top 10 Plays of Career","likes":3},
    {"post_date":"2024-06-03","post_type":"Community Question","post_text":"Thank you to everyone for 4,000 subscribers! What Top 10 video do you want to see next?","likes":3,"comments":9},
    {"post_date":"2024-05-27","post_type":"Upload Teaser","post_text":"New video is up, go check it out!","linked_video_title":"De'Aaron Fox Top 10 Plays of Career","likes":1},
    {"post_date":"2024-05-20","post_type":"Upload Teaser","post_text":"Another new video, check it out!","linked_video_title":"Hassan Whiteside Top 10 Plays of Career","likes":1},
    {"post_date":"2024-05-13","post_type":"Upload Teaser","post_text":"New Top 10 video is up! Go check it out!","linked_video_title":"Tyrese Haliburton Top 10 Plays of Career","likes":1},
    {"post_date":"2024-05-06","post_type":"Next Upload Poll","post_text":"Which Top 10 should I make next?","option_a":"Tyrese Haliburton","option_b":"Domantas Sabonis","option_c":"Jalen Brunson","option_d":"Jamal Murray","option_e":"De'Aaron Fox","option_a_percent":44,"option_b_percent":8,"option_c_percent":14,"option_d_percent":17,"option_e_percent":17,"poll_winner":"Tyrese Haliburton","votes":112,"likes":3,"comments":1},
    {"post_date":"2024-04-29","post_type":"Upload Teaser","post_text":"New video is up! Go leave a like and comment which player you want next!","linked_video_title":"Jerry West Top 10 Plays of Career","likes":2},
    {"post_date":"2024-04-22","post_type":"Upload Teaser","post_text":"New Terrence Ross video is up after he announced his retirement!","linked_video_title":"Terrence Ross Top 10 Plays of Career","likes":1},
    {"post_date":"2024-04-15","post_type":"Upload Teaser","post_text":"New video is up! Suggested by viewer.","linked_video_title":"Shai Gilgeous-Alexander Top 10 Plays of Career","likes":1},
    {"post_date":"2024-04-08","post_type":"Upload Teaser","post_text":"New Top 10 video is up! Go check it out!","linked_video_title":"Al Horford Top 10 Plays of Career","likes":1},
    {"post_date":"2024-04-01","post_type":"Next Upload Poll","post_text":"Which Top 10 next? Sorry for the lack of uploads.","option_a":"Michael Redd","option_b":"Muggsy Bogues","option_c":"Dikembe Mutombo","option_d":"Giannis Antetokounmpo","option_e":"Luka Doncic","option_a_percent":13,"option_b_percent":19,"option_c_percent":13,"option_d_percent":41,"option_e_percent":14,"poll_winner":"Giannis Antetokounmpo","votes":69,"likes":2},
    {"post_date":"2024-03-25","post_type":"Community Question","post_text":"Which Top 10 do you guys want to see next? Leave a comment and I'll get back to everyone!","likes":10,"comments":5},
    {"post_date":"2023-07-05","post_type":"Next Upload Poll","post_text":"Which upcoming video are you most excited for?","option_a":"Joel Embiid","option_b":"Reggie Miller","option_c":"Jermaine O'Neal","option_d":"Jamal Crawford","option_a_percent":17,"option_b_percent":50,"option_c_percent":12,"option_d_percent":21,"poll_winner":"Reggie Miller","votes":435,"likes":10,"comments":5},
    {"post_date":"2023-06-28","post_type":"Upload Teaser","post_text":"Welcome to Phoenix! New Bradley Beal Top 10 video is up.","linked_video_title":"Bradley Beal Top 10 Plays of Career","likes":4},
    {"post_date":"2023-06-21","post_type":"Upload Teaser","post_text":"Check out the latest video showcasing Wilt Chamberlain.","linked_video_title":"Wilt Chamberlain Top 10 Plays of Career","likes":3},
    {"post_date":"2023-06-13","post_type":"Upload Teaser","post_text":"Wilt Chamberlain Top 10 scheduled upload at 10:00 AM CST on June 13th.","linked_video_title":"Wilt Chamberlain upcoming","likes":25,"comments":1},
    {"post_date":"2023-06-08","post_type":"Upload Teaser","post_text":"New Richard Jefferson Top 10 video is out!","linked_video_title":"Richard Jefferson Top 10 Plays of Career","likes":3},
    {"post_date":"2023-06-02","post_type":"Upload Teaser","post_text":"Grant Hill Top 10 moments video just dropped.","linked_video_title":"Grant Hill Top 10 Plays of Career","likes":1},
    {"post_date":"2023-05-28","post_type":"Next Upload Poll","post_text":"Are you guys interested in a video featuring Wilt Chamberlain?","option_a":"Yes","option_b":"YES!!","option_a_percent":56,"option_b_percent":44,"poll_winner":"Yes","votes":530,"likes":9,"comments":1},
    {"post_date":"2023-05-24","post_type":"Upload Teaser","post_text":"Paul George Top 10 moments video is out.","linked_video_title":"Paul George Top 10 Plays of Career","likes":1},
    {"post_date":"2023-05-21","post_type":"Upload Teaser","post_text":"Jordan Clarkson Top 10 moments is now out.","linked_video_title":"Jordan Clarkson Top 10 Plays of Career","likes":1},
    {"post_date":"2023-05-18","post_type":"Upload Teaser","post_text":"New Jaylen Brown Top 10 video is up.","linked_video_title":"Jaylen Brown Top 10 Plays of Career","likes":2},
    {"post_date":"2023-05-15","post_type":"Player Debate","post_text":"Who will win the NBA Finals?","option_a":"Miami Heat","option_b":"Denver Nuggets","option_a_percent":27,"option_b_percent":73,"poll_winner":"Denver Nuggets","votes":952,"likes":8},
    {"post_date":"2023-05-12","post_type":"Community Question","post_text":"Donations available to support the channel.","likes":3},
    {"post_date":"2023-05-09","post_type":"Upload Teaser","post_text":"Made a Caleb Martin Top 10 video after Game 7.","linked_video_title":"Caleb Martin Top 10 Plays of Career","likes":1},
    {"post_date":"2023-05-05","post_type":"Community Question","post_text":"Thank you for 1,000 subscribers. Comment players for my next Top 10 video.","likes":8},
    {"post_date":"2023-05-01","post_type":"Upload Teaser","post_text":"New Karl Malone video is up.","linked_video_title":"Karl Malone Top 10 Plays of Career","likes":3},
    {"post_date":"2023-04-28","post_type":"Next Upload Poll","post_text":"Which Top 10 video do you guys want next? Fan suggestions added.","option_a":"Karl Malone","option_b":"Grant Hill","option_c":"Jaylen Brown","option_d":"Gordon Hayward","option_e":"Nate Robinson","option_a_percent":43,"option_b_percent":19,"option_c_percent":15,"option_d_percent":8,"option_e_percent":15,"poll_winner":"Karl Malone","votes":237,"likes":3,"comments":3},
    {"post_date":"2023-04-24","post_type":"Upload Teaser","post_text":"Derrick White Top 10 video is up.","linked_video_title":"Derrick White Top 10 Plays of Career","likes":1},
    {"post_date":"2023-04-21","post_type":"Next Upload Poll","post_text":"Which Top 10 next?","option_a":"Gordon Hayward","option_b":"Nate Robinson","option_c":"Karl Malone","option_d":"Mason Plumlee","option_e":"Jeff Teague","option_a_percent":16,"option_b_percent":18,"option_c_percent":58,"option_d_percent":5,"option_e_percent":3,"poll_winner":"Karl Malone","votes":289,"likes":2,"comments":6},
    {"post_date":"2023-04-18","post_type":"Upload Teaser","post_text":"Darius Garland Top 10 video is up.","linked_video_title":"Darius Garland Top 10 Plays of Career","likes":2},
    {"post_date":"2023-04-18","post_type":"Upload Teaser","post_text":"New Kareem Top 10 video is up.","linked_video_title":"Kareem Abdul-Jabbar Top 10 Plays of Career","likes":1},
    {"post_date":"2023-04-15","post_type":"Upload Teaser","post_text":"Kareem video will be up hopefully soon.","linked_video_title":"Kareem upcoming","likes":3},
    {"post_date":"2023-04-12","post_type":"Next Upload Poll","post_text":"Which Top 10 should I do next?","option_a":"Al Horford","option_b":"Ricky Rubio","option_c":"Kareem Abdul-Jabbar","option_d":"Clyde Drexler","option_e":"Patrick Ewing","option_a_percent":17,"option_b_percent":9,"option_c_percent":53,"option_d_percent":11,"option_e_percent":11,"poll_winner":"Kareem Abdul-Jabbar","votes":139,"likes":5},
    {"post_date":"2023-04-09","post_type":"Upload Teaser","post_text":"Dominique Wilkins Top 10 video is up.","linked_video_title":"Dominique Wilkins Top 10 Plays of Career","likes":1},
    {"post_date":"2023-04-08","post_type":"Upload Teaser","post_text":"Dominique Wilkins Top 10 will be up later tonight.","linked_video_title":"Dominique upcoming","likes":4},
    {"post_date":"2023-04-05","post_type":"Next Upload Poll","post_text":"Which Top 10 next?","option_a":"Dominique Wilkins","option_b":"Ricky Rubio","option_c":"Lonzo Ball","option_d":"Al Horford","option_e":"Ben Simmons","option_a_percent":63,"option_b_percent":5,"option_c_percent":12,"option_d_percent":9,"option_e_percent":11,"poll_winner":"Dominique Wilkins","votes":130,"likes":3,"comments":1},
    {"post_date":"2023-04-02","post_type":"Upload Teaser","post_text":"Dennis Schroder Top 10 video is up.","linked_video_title":"Dennis Schroder Top 10 Plays of Career","likes":2},
    {"post_date":"2023-03-30","post_type":"Next Upload Poll","post_text":"Which Top 10 next?","option_a":"Ricky Rubio","option_b":"Dennis Schröder","option_c":"Ben Simmons","option_d":"Lonzo Ball","option_e":"Al Horford","option_a_percent":11,"option_b_percent":38,"option_c_percent":15,"option_d_percent":20,"option_e_percent":16,"poll_winner":"Dennis Schröder","votes":88,"likes":1,"comments":1},
    {"post_date":"2023-03-27","post_type":"Upload Teaser","post_text":"Dennis Rodman Top 10 video is uploaded.","linked_video_title":"Dennis Rodman Top 10 Plays of Career","likes":1},
    {"post_date":"2023-03-26","post_type":"Community Question","post_text":"Thank you everyone for 500 subscribers!","likes":5},
    {"post_date":"2023-03-23","post_type":"Next Upload Poll","post_text":"Which Top 10 do you want next?","option_a":"Dennis Schröder","option_b":"Lonzo Ball","option_c":"Ricky Rubio","option_d":"Dennis Rodman","option_e":"Ben Simmons","option_a_percent":10,"option_b_percent":9,"option_c_percent":10,"option_d_percent":64,"option_e_percent":6,"poll_winner":"Dennis Rodman","votes":87,"likes":1},
    {"post_date":"2023-03-20","post_type":"Upload Teaser","post_text":"New video is up!","linked_video_title":"Nikola Jokic Top 10 Plays of Career","likes":1},
    {"post_date":"2023-03-18","post_type":"Community Question","post_text":"Channel is back near 500 subscribers after old channel was hacked.","likes":5},
    {"post_date":"2023-03-15","post_type":"Next Upload Poll","post_text":"What Top 10 should I make next?","option_a":"Al Horford","option_b":"Nikola Jokic","option_c":"Lonzo Ball","option_d":"Dennis Schröder","option_e":"Ben Simmons","option_a_percent":8,"option_b_percent":59,"option_c_percent":13,"option_d_percent":11,"option_e_percent":9,"poll_winner":"Nikola Jokic","votes":75,"likes":3,"comments":1},
    {"post_date":"2023-03-12","post_type":"Next Upload Poll","post_text":"Which Top 10 next?","option_a":"Al Horford","option_b":"Lonzo Ball","option_c":"Ben Simmons","option_d":"Dennis Schröder","option_e":"Brandon Ingram","option_a_percent":14,"option_b_percent":14,"option_c_percent":12,"option_d_percent":22,"option_e_percent":38,"poll_winner":"Brandon Ingram","votes":58,"likes":1},
    {"post_date":"2023-03-09","post_type":"Upload Teaser","post_text":"Donovan Mitchell Top 10 video is up.","linked_video_title":"Donovan Mitchell Top 10 Plays of Career","likes":1},
    {"post_date":"2023-03-06","post_type":"Player Debate","post_text":"Were you subscribed to the last channel before it was hacked?","option_a":"I was subscribed to the last channel","option_b":"I just found out about this channel","option_a_percent":43,"option_b_percent":57,"poll_winner":"I just found out about this channel","votes":14,"likes":1},
    {"post_date":"2023-03-03","post_type":"Next Upload Poll","post_text":"What Top 10 should I make next?","option_a":"Brandon Ingram","option_b":"Al Horford","option_c":"Donovan Mitchell","option_d":"Ben Simmons","option_e":"Lonzo Ball","option_a_percent":11,"option_b_percent":15,"option_c_percent":61,"option_d_percent":9,"option_e_percent":4,"poll_winner":"Donovan Mitchell","votes":46,"likes":2},
    {"post_date":"2023-02-28","post_type":"Upload Teaser","post_text":"J.R. Smith Top 10 video is uploaded.","linked_video_title":"J.R. Smith Top 10 Plays of Career","likes":1},
    {"post_date":"2023-02-25","post_type":"Upload Teaser","post_text":"CJ McCollum Top 10 video is up.","linked_video_title":"CJ McCollum Top 10 Plays of Career","likes":1},
    {"post_date":"2023-02-22","post_type":"Upload Teaser","post_text":"Updated Michael Jordan Top 10 video is up.","linked_video_title":"Michael Jordan Top 10 Plays of Career","likes":1},
    {"post_date":"2023-02-19","post_type":"Upload Teaser","post_text":"Third video of the day!","linked_video_title":"Karl-Anthony Towns Top 10 Plays of Career","likes":1},
    {"post_date":"2023-02-16","post_type":"Upload Teaser","post_text":"Top 10 Buzzer Beaters of All Time is up.","linked_video_title":"Top 10 Buzzer Beaters of All Time","likes":1},
    {"post_date":"2023-02-13","post_type":"Upload Teaser","post_text":"David Robinson Top 10 video is up.","linked_video_title":"David Robinson Top 10 Plays of Career","likes":1},
    {"post_date":"2023-02-10","post_type":"Upload Teaser","post_text":"Updated David Robinson video is almost finished.","linked_video_title":"David Robinson upcoming","likes":3},
    {"post_date":"2023-02-07","post_type":"Community Question","post_text":"Original NBATop10 account was terminated due to hacker spam videos.","likes":3},
    {"post_date":"2023-02-04","post_type":"Community Question","post_text":"Hello everyone, this is my new channel after the old one was hacked.","likes":4,"comments":1},
]

def _community_canonical_type(value):
    text = str(value or '').lower()
    if 'trivia' in text or 'guess' in text:
        return 'Trivia / Guess Who'
    if 'teaser' in text or ('upload' in text and 'poll' not in text):
        return 'Upload Teaser'
    if 'throwback' in text or 'history' in text or 'on this day' in text:
        return 'Throwback / History Post'
    if 'question' in text or 'community' in text:
        return 'Community Question'
    if 'debate' in text or 'finals' in text or 'win' in text or 'could' in text:
        return 'Player Debate'
    return 'Next Upload Poll'

def _community_season_from_date(date_text):
    try:
        month = int(str(date_text or '').split('-')[1])
    except Exception:
        return 'Unknown'
    if month in (4,5,6):
        return 'Playoffs / Finals'
    if month in (7,8,9):
        return 'Offseason'
    if month in (10,11,12,1,2,3):
        return 'Regular Season'
    return 'Unknown'

def _community_year_from_date(date_text):
    try:
        return int(str(date_text or '').split('-')[0])
    except Exception:
        return 0

def _community_option_count(payload):
    return sum(1 for key in ['option_a','option_b','option_c','option_d','option_e'] if str(payload.get(key) or '').strip())

def _community_score(payload):
    return round(int(payload.get('likes') or 0) + int(payload.get('comments') or 0) * 3 + int(payload.get('votes') or 0) * 0.35, 2)

def create_community_automation_tables(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS community_post_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_date TEXT DEFAULT '', post_time TEXT DEFAULT '', post_type TEXT DEFAULT 'Next Upload Poll',
        poll_subtype TEXT DEFAULT '', season TEXT DEFAULT '', nba_year INTEGER DEFAULT 0,
        topic TEXT DEFAULT '', post_text TEXT DEFAULT '',
        option_a TEXT DEFAULT '', option_b TEXT DEFAULT '', option_c TEXT DEFAULT '', option_d TEXT DEFAULT '', option_e TEXT DEFAULT '',
        option_a_percent REAL DEFAULT 0, option_b_percent REAL DEFAULT 0, option_c_percent REAL DEFAULT 0, option_d_percent REAL DEFAULT 0, option_e_percent REAL DEFAULT 0,
        poll_winner TEXT DEFAULT '', trivia_answer TEXT DEFAULT '',
        linked_video_id TEXT DEFAULT '', linked_video_title TEXT DEFAULT '', linked_player TEXT DEFAULT '', linked_format TEXT DEFAULT '',
        likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, votes INTEGER DEFAULT 0,
        ai_engagement_score REAL DEFAULT 0, poll_option_count INTEGER DEFAULT 0,
        poll_uploaded_status TEXT DEFAULT '', upload_date_after_poll TEXT DEFAULT '', days_between_poll_and_upload INTEGER DEFAULT 0,
        historical_seed_version TEXT DEFAULT '', notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    for column, column_type in [
        ('poll_subtype','TEXT DEFAULT ""'), ('season','TEXT DEFAULT ""'), ('nba_year','INTEGER DEFAULT 0'),
        ('option_e','TEXT DEFAULT ""'), ('option_e_percent','REAL DEFAULT 0'), ('linked_player','TEXT DEFAULT ""'),
        ('linked_format','TEXT DEFAULT ""'), ('ai_engagement_score','REAL DEFAULT 0'), ('poll_option_count','INTEGER DEFAULT 0'),
        ('poll_uploaded_status','TEXT DEFAULT ""'), ('upload_date_after_poll','TEXT DEFAULT ""'), ('days_between_poll_and_upload','INTEGER DEFAULT 0'),
        ('historical_seed_version','TEXT DEFAULT ""'), ('option_a_percent','REAL DEFAULT 0'), ('option_b_percent','REAL DEFAULT 0'),
        ('option_c_percent','REAL DEFAULT 0'), ('option_d_percent','REAL DEFAULT 0'), ('poll_winner','TEXT DEFAULT ""'), ('trivia_answer','TEXT DEFAULT ""')
    ]:
        try:
            add_column_if_missing(cursor, 'community_post_results', column, column_type)
        except Exception:
            pass
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_community_post_date ON community_post_results(post_date DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_community_post_type ON community_post_results(post_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_community_poll_winner ON community_post_results(poll_winner)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_community_seed ON community_post_results(historical_seed_version)')

def ensure_community_automation_tables():
    connection = create_connection(); cursor = connection.cursor(); create_community_automation_tables(cursor); connection.commit(); connection.close()

def _community_payload(data):
    data = data or {}
    payload = {
        'post_date': data.get('post_date',''), 'post_time': data.get('post_time',''),
        'post_type': _community_canonical_type(data.get('post_type','Next Upload Poll')),
        'topic': data.get('topic','') or data.get('poll_winner','') or data.get('trivia_answer',''),
        'post_text': data.get('post_text',''),
        'option_a': data.get('option_a','') or data.get('poll_option_1',''),
        'option_b': data.get('option_b','') or data.get('poll_option_2',''),
        'option_c': data.get('option_c','') or data.get('poll_option_3',''),
        'option_d': data.get('option_d','') or data.get('poll_option_4',''),
        'option_e': data.get('option_e','') or data.get('poll_option_5',''),
        'option_a_percent': _community_clean_number(data.get('option_a_percent'),0,float),
        'option_b_percent': _community_clean_number(data.get('option_b_percent'),0,float),
        'option_c_percent': _community_clean_number(data.get('option_c_percent'),0,float),
        'option_d_percent': _community_clean_number(data.get('option_d_percent'),0,float),
        'option_e_percent': _community_clean_number(data.get('option_e_percent'),0,float),
        'poll_winner': data.get('poll_winner',''), 'trivia_answer': data.get('trivia_answer',''),
        'linked_video_id': data.get('linked_video_id',''), 'linked_video_title': data.get('linked_video_title',''),
        'linked_player': data.get('linked_player',''), 'linked_format': data.get('linked_format',''),
        'likes': _community_clean_number(data.get('likes'),0,int), 'comments': _community_clean_number(data.get('comments'),0,int), 'votes': _community_clean_number(data.get('votes'),0,int),
        'poll_uploaded_status': data.get('poll_uploaded_status',''), 'upload_date_after_poll': data.get('upload_date_after_poll',''),
        'days_between_poll_and_upload': _community_clean_number(data.get('days_between_poll_and_upload'),0,int),
        'historical_seed_version': data.get('historical_seed_version',''), 'notes': data.get('notes','')
    }
    payload['season'] = data.get('season') or _community_season_from_date(payload['post_date'])
    payload['nba_year'] = _community_year_from_date(payload['post_date'])
    payload['poll_option_count'] = _community_option_count(payload)
    payload['ai_engagement_score'] = _community_score(payload)
    payload['poll_subtype'] = data.get('poll_subtype','') or payload['post_type']
    return payload

def save_community_post_result(data):
    ensure_community_automation_tables(); payload = _community_payload(data)
    connection = create_connection(); cursor = connection.cursor()
    cursor.execute('''
    INSERT INTO community_post_results (
        post_date, post_time, post_type, poll_subtype, season, nba_year, topic, post_text,
        option_a, option_b, option_c, option_d, option_e,
        option_a_percent, option_b_percent, option_c_percent, option_d_percent, option_e_percent,
        poll_winner, trivia_answer, linked_video_id, linked_video_title, linked_player, linked_format,
        likes, comments, votes, ai_engagement_score, poll_option_count, poll_uploaded_status,
        upload_date_after_poll, days_between_poll_and_upload, historical_seed_version, notes,
        created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    ''', tuple(payload[k] for k in ['post_date','post_time','post_type','poll_subtype','season','nba_year','topic','post_text','option_a','option_b','option_c','option_d','option_e','option_a_percent','option_b_percent','option_c_percent','option_d_percent','option_e_percent','poll_winner','trivia_answer','linked_video_id','linked_video_title','linked_player','linked_format','likes','comments','votes','ai_engagement_score','poll_option_count','poll_uploaded_status','upload_date_after_poll','days_between_poll_and_upload','historical_seed_version','notes']))
    connection.commit(); new_id = cursor.lastrowid; connection.close(); return new_id

def update_community_post_result(row_id, data):
    ensure_community_automation_tables(); payload = _community_payload(data)
    connection = create_connection(); cursor = connection.cursor()
    cursor.execute('''
    UPDATE community_post_results SET
        post_date=?, post_time=?, post_type=?, poll_subtype=?, season=?, nba_year=?, topic=?, post_text=?,
        option_a=?, option_b=?, option_c=?, option_d=?, option_e=?,
        option_a_percent=?, option_b_percent=?, option_c_percent=?, option_d_percent=?, option_e_percent=?,
        poll_winner=?, trivia_answer=?, linked_video_id=?, linked_video_title=?, linked_player=?, linked_format=?,
        likes=?, comments=?, votes=?, ai_engagement_score=?, poll_option_count=?, poll_uploaded_status=?,
        upload_date_after_poll=?, days_between_poll_and_upload=?, historical_seed_version=?, notes=?, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    ''', tuple(payload[k] for k in ['post_date','post_time','post_type','poll_subtype','season','nba_year','topic','post_text','option_a','option_b','option_c','option_d','option_e','option_a_percent','option_b_percent','option_c_percent','option_d_percent','option_e_percent','poll_winner','trivia_answer','linked_video_id','linked_video_title','linked_player','linked_format','likes','comments','votes','ai_engagement_score','poll_option_count','poll_uploaded_status','upload_date_after_poll','days_between_poll_and_upload','historical_seed_version','notes']) + (int(row_id or 0),))
    connection.commit(); connection.close(); return int(row_id or 0)

def seed_community_post_history_if_needed():
    ensure_community_automation_tables()
    connection = create_connection(); cursor = connection.cursor()
    inserted = 0
    for row in COMMUNITY_HISTORY_SEED_POSTS:
        payload = dict(row); payload['historical_seed_version'] = COMMUNITY_HISTORY_SEED_VERSION; payload['notes'] = 'Imported from all-time YouTube Community tab history.'
        cursor.execute('SELECT id FROM community_post_results WHERE post_date=? AND post_text=? LIMIT 1', (payload.get('post_date',''), payload.get('post_text','')))
        if cursor.fetchone():
            continue
        p = _community_payload(payload)
        cursor.execute('''
        INSERT INTO community_post_results (
            post_date, post_time, post_type, poll_subtype, season, nba_year, topic, post_text,
            option_a, option_b, option_c, option_d, option_e,
            option_a_percent, option_b_percent, option_c_percent, option_d_percent, option_e_percent,
            poll_winner, trivia_answer, linked_video_id, linked_video_title, linked_player, linked_format,
            likes, comments, votes, ai_engagement_score, poll_option_count, poll_uploaded_status,
            upload_date_after_poll, days_between_poll_and_upload, historical_seed_version, notes,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        ''', tuple(p[k] for k in ['post_date','post_time','post_type','poll_subtype','season','nba_year','topic','post_text','option_a','option_b','option_c','option_d','option_e','option_a_percent','option_b_percent','option_c_percent','option_d_percent','option_e_percent','poll_winner','trivia_answer','linked_video_id','linked_video_title','linked_player','linked_format','likes','comments','votes','ai_engagement_score','poll_option_count','poll_uploaded_status','upload_date_after_poll','days_between_poll_and_upload','historical_seed_version','notes']))
        inserted += 1
    connection.commit(); connection.close(); return inserted

def get_community_post_results(limit=500):
    ensure_community_automation_tables(); connection = create_connection(); cursor = connection.cursor()
    cursor.execute('SELECT * FROM community_post_results ORDER BY COALESCE(NULLIF(post_date, ""), created_at) DESC, created_at DESC, id DESC LIMIT ?', (int(limit or 500),))
    rows = [dict(row) for row in cursor.fetchall()]; connection.close(); return rows

def get_community_post_history(limit=500):
    return get_community_post_results(limit)

def get_community_post_learning():
    rows = get_community_post_results(1000)
    if not rows:
        return {'best_post_type':'Next Upload Poll','best_type_score':0,'best_time':'7:00 PM','average_likes':0,'average_comments':0,'average_votes':0,'top_topics':[],'insights':[]}
    by_type = {}; by_season = {}; by_options = {}; winners = {}; total_likes=total_comments=total_votes=0
    for r in rows:
        score = float(r.get('ai_engagement_score') or (int(r.get('likes') or 0)+int(r.get('comments') or 0)*3+int(r.get('votes') or 0)*0.35))
        typ = r.get('post_type') or 'Next Upload Poll'; by_type.setdefault(typ, [0,0]); by_type[typ][0]+=score; by_type[typ][1]+=1
        season = r.get('season') or 'Unknown'; by_season.setdefault(season,[0,0]); by_season[season][0]+=score; by_season[season][1]+=1
        opt_count = int(r.get('poll_option_count') or 0)
        if opt_count: by_options.setdefault(opt_count,[0,0]); by_options[opt_count][0]+=score; by_options[opt_count][1]+=1
        if r.get('poll_winner'): winners[r['poll_winner']] = winners.get(r['poll_winner'],0)+1
        total_likes += int(r.get('likes') or 0); total_comments += int(r.get('comments') or 0); total_votes += int(r.get('votes') or 0)
    def best(bucket, default=''):
        if not bucket: return default, 0
        key, stats = max(bucket.items(), key=lambda kv: kv[1][0]/max(1,kv[1][1]))
        return key, round(stats[0]/max(1,stats[1]),2)
    best_type, best_type_score = best(by_type,'Next Upload Poll')
    best_season, best_season_score = best(by_season,'Unknown')
    best_option_count, best_option_score = best(by_options,'')
    top_winners = sorted(winners.items(), key=lambda x:x[1], reverse=True)[:8]
    insights = [
        f'{best_type} is currently the strongest post type by historical engagement.',
        f'{best_season} is the strongest season/window in your logged data.',
    ]
    if best_option_count:
        insights.append(f'{best_option_count}-option polls are performing best so far.')
    if top_winners:
        insights.append(f'Top recurring poll winner: {top_winners[0][0]}.')
    return {
        'best_post_type': best_type, 'best_type_score': best_type_score, 'best_time':'7:00 PM',
        'average_likes': round(total_likes/max(1,len(rows)),1), 'average_comments': round(total_comments/max(1,len(rows)),1),
        'average_votes': round(total_votes/max(1,len(rows)),1), 'total_votes': total_votes,
        'best_season': best_season, 'best_season_score': best_season_score, 'best_option_count': best_option_count,
        'top_poll_winners': [{'topic':k,'wins':v} for k,v in top_winners],
        'top_topics': [{'topic':k,'score':v} for k,v in top_winners], 'insights': insights,
        'post_type_stats': [{'post_type':k,'score':round(v[0]/max(1,v[1]),2),'posts':v[1]} for k,v in sorted(by_type.items(), key=lambda kv: kv[1][0]/max(1,kv[1][1]), reverse=True)]
    }


# =========================================================
# COMMUNITY AUTOMATION OPTIMAL AI OVERRIDE
# Added: all-time seed import, option E, prediction fields, 3/week learning.
# Safe to keep at bottom: these function names override earlier versions.
# =========================================================

COMMUNITY_HISTORY_SEED_VERSION = "community_history_seed_2026_07_08_v2_optimal"

COMMUNITY_HISTORY_SEED_POSTS = [{'post_date': '2026-06-10', 'post_type': 'Player Debate', 'post_text': 'Who’s winning the NBA Finals?', 'option_a': 'San Antonio Spurs', 'option_b': 'New York Knicks', 'option_a_percent': 44, 'option_b_percent': 56, 'poll_winner': 'New York Knicks', 'votes': 632, 'likes': 13, 'comments': 2}, {'post_date': '2026-06-10', 'post_type': 'Next Upload Poll', 'post_text': 'Which player deserves a Top 10 Career Dunks video next?', 'option_a': 'Shawn Kemp', 'option_b': 'Vince Carter', 'option_c': 'Dominique Wilkins', 'option_d': 'Clyde Drexler', 'option_a_percent': 22, 'option_b_percent': 46, 'option_c_percent': 20, 'option_d_percent': 13, 'poll_winner': 'Vince Carter', 'votes': 102, 'likes': 5, 'comments': 2, 'linked_format': 'Top 10 Career Dunks'}, {'post_date': '2025-07-01', 'post_type': 'Upload Teaser', 'post_text': 'New video is out, go check it out!', 'linked_video_title': 'Julius Randle Top 10 Plays of Career', 'linked_player': 'Julius Randle', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2025-06-24', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 video do you guys wants next?', 'option_a': 'Julius Randle', 'option_b': 'Jalen Brunson', 'option_c': 'Donte DiVincenzo', 'option_d': 'Naz Reid', 'option_e': 'Rudy Gobert', 'option_a_percent': 15, 'option_b_percent': 53, 'option_c_percent': 3, 'option_d_percent': 9, 'option_e_percent': 20, 'poll_winner': 'Jalen Brunson', 'votes': 92, 'likes': 6, 'comments': 4}, {'post_date': '2025-06-17', 'post_type': 'Upload Teaser', 'post_text': 'New video is up, go check it out!', 'linked_video_title': 'Gordon Hayward Top 10 Plays of Career', 'linked_player': 'Gordon Hayward', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2024-07-01', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up, go check it out! Thanks for watching!', 'linked_video_title': 'Victor Wembanyama Top 10 Plays of Rookie Season', 'linked_player': 'Victor Wembanyama', 'linked_format': 'Top 10 Plays', 'likes': 5, 'comments': 0}, {'post_date': '2024-06-24', 'post_type': 'Player Debate', 'post_text': 'Who will win the NBA Finals this year? (Comment any others)', 'option_a': 'Celtics', 'option_b': 'Nuggets', 'option_c': 'Thunder', 'option_d': 'Wolves', 'option_a_percent': 40, 'option_b_percent': 45, 'option_c_percent': 6, 'option_d_percent': 8, 'poll_winner': 'Nuggets', 'votes': 836, 'likes': 16, 'comments': 7}, {'post_date': '2024-06-17', 'post_type': 'Player Debate', 'post_text': 'Could Caitlin Clark play in the NBA?', 'option_a': 'Yes', 'option_b': 'No', 'option_a_percent': 23, 'option_b_percent': 77, 'poll_winner': 'No', 'votes': 532, 'likes': 8, 'comments': 7}, {'post_date': '2024-06-10', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is uploaded, go show support!', 'linked_video_title': 'Pete Maravich Top 10 Plays of Career', 'linked_player': 'Pete Maravich', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2024-06-03', 'post_type': 'Community Question', 'post_text': 'Thank you to everyone for 4,000 subscribers! What top 10 video do you want to see next? Comment below!', 'likes': 3, 'comments': 9}, {'post_date': '2024-05-27', 'post_type': 'Upload Teaser', 'post_text': 'New video is up, go check it out!', 'linked_video_title': "De'Aaron Fox Top 10 Plays of Career", 'linked_player': "De'Aaron Fox", 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-05-20', 'post_type': 'Upload Teaser', 'post_text': 'Another new video, check it out!', 'linked_video_title': 'Hassan Whiteside Top 10 Plays of Career', 'linked_player': 'Hassan Whiteside', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-05-13', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up! Go check it out!', 'linked_video_title': 'Tyrese Haliburton Top 10 Plays of Career', 'linked_player': 'Tyrese Haliburton', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-05-06', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 should I make next?', 'option_a': 'Tyrese Haliburton', 'option_b': 'Domantas Sabonis', 'option_c': 'Jalen Brunson', 'option_d': 'Jamal Murray', 'option_e': "De'Aaron Fox", 'option_a_percent': 44, 'option_b_percent': 8, 'option_c_percent': 14, 'option_d_percent': 17, 'option_e_percent': 17, 'poll_winner': 'Tyrese Haliburton', 'votes': 112, 'likes': 3, 'comments': 1}, {'post_date': '2024-04-29', 'post_type': 'Upload Teaser', 'post_text': 'New video is up! Go leave a like and comment which player you want next!', 'linked_video_title': 'Jerry West Top 10 Plays of Career', 'linked_player': 'Jerry West', 'linked_format': 'Top 10 Plays', 'likes': 2, 'comments': 0}, {'post_date': '2024-04-22', 'post_type': 'Upload Teaser', 'post_text': 'New Terrence Ross video is up after he announced his retirement! Go check it out!', 'linked_video_title': 'Terrence Ross Top 10 Plays of Career', 'linked_player': 'Terrence Ross', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-04-15', 'post_type': 'Upload Teaser', 'post_text': 'New video is up! Suggested by a viewer. Go check it out!', 'linked_video_title': 'Shai Gilgeous-Alexander Top 10 Plays of Career', 'linked_player': 'Shai Gilgeous-Alexander', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-04-08', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up! Go check it out!', 'linked_video_title': 'Al Horford Top 10 Plays of Career', 'linked_player': 'Al Horford', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2024-04-01', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 next? Sorry for the lack of uploads, been very busy recently with college and football.', 'option_a': 'Michael Redd', 'option_b': 'Muggsy Bogues', 'option_c': 'Dikembe Mutombo', 'option_d': 'Giannis Antetokounmpo', 'option_e': 'Luka Doncic', 'option_a_percent': 13, 'option_b_percent': 19, 'option_c_percent': 13, 'option_d_percent': 41, 'option_e_percent': 14, 'poll_winner': 'Giannis Antetokounmpo', 'votes': 69, 'likes': 2, 'comments': 0}, {'post_date': '2024-03-25', 'post_type': 'Community Question', 'post_text': "Which top 10 do you guys want to see next? Leave a comment and I'll get back to everyone!", 'likes': 10, 'comments': 5}, {'post_date': '2023-07-05', 'post_type': 'Next Upload Poll', 'post_text': 'Which upcoming video are you most excited for? (Chris Paul coming soon as well)', 'option_a': 'Joel Embiid', 'option_b': 'Reggie Miller', 'option_c': "Jermaine O'Neal", 'option_d': 'Jamal Crawford', 'option_a_percent': 17, 'option_b_percent': 50, 'option_c_percent': 12, 'option_d_percent': 21, 'poll_winner': 'Reggie Miller', 'votes': 435, 'likes': 10, 'comments': 5}, {'post_date': '2023-06-28', 'post_type': 'Upload Teaser', 'post_text': 'Welcome to Phoenix! New Bradley Beal top 10 plays video is up.', 'linked_video_title': 'Bradley Beal Top 10 Plays of Career', 'linked_player': 'Bradley Beal', 'linked_format': 'Top 10 Plays', 'likes': 4, 'comments': 0}, {'post_date': '2023-06-21', 'post_type': 'Upload Teaser', 'post_text': 'Check out the latest video showcasing the top 10 plays of the legendary Wilt Chamberlain!', 'linked_video_title': 'Wilt Chamberlain Top 10 Plays of Career', 'linked_player': 'Wilt Chamberlain', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2023-06-13', 'post_type': 'Upload Teaser', 'post_text': "Are you excited for the scheduled upload of Wilt Chamberlain's top 10 plays at 10:00 AM CST on June 13th?", 'linked_video_title': 'Wilt Chamberlain upcoming', 'linked_player': 'Wilt Chamberlain', 'linked_format': 'Top 10 Plays', 'likes': 25, 'comments': 1}, {'post_date': '2023-06-08', 'post_type': 'Upload Teaser', 'post_text': 'New Richard Jefferson top 10 video is out!', 'linked_video_title': 'Richard Jefferson Top 10 Plays of Career', 'linked_player': 'Richard Jefferson', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2023-06-02', 'post_type': 'Upload Teaser', 'post_text': "Check out the new video that just dropped featuring Grant Hill's top 10 moments!", 'linked_video_title': 'Grant Hill Top 10 Plays of Career', 'linked_player': 'Grant Hill', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-05-28', 'post_type': 'Next Upload Poll', 'post_text': "Are you guys interested in a video featuring the top 10 plays of Wilt Chamberlain's career?", 'option_a': 'Yes', 'option_b': 'YES!!', 'option_a_percent': 56, 'option_b_percent': 44, 'poll_winner': 'Yes', 'votes': 530, 'likes': 9, 'comments': 1, 'linked_player': 'Wilt Chamberlain'}, {'post_date': '2023-05-24', 'post_type': 'Upload Teaser', 'post_text': "Check out the recently released video showcasing Paul George's best 10 moments!", 'linked_video_title': 'Paul George Top 10 Plays of Career', 'linked_player': 'Paul George', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-05-21', 'post_type': 'Upload Teaser', 'post_text': "The new video featuring Jordan Clarkson's top 10 moments is now out!", 'linked_video_title': 'Jordan Clarkson Top 10 Plays of Career', 'linked_player': 'Jordan Clarkson', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-05-18', 'post_type': 'Upload Teaser', 'post_text': 'New Jaylen Brown top 10 video is up, go check it out!', 'linked_video_title': 'Jaylen Brown Top 10 Plays of Career', 'linked_player': 'Jaylen Brown', 'linked_format': 'Top 10 Plays', 'likes': 2, 'comments': 0}, {'post_date': '2023-05-15', 'post_type': 'Player Debate', 'post_text': 'Who will win the NBA Finals?', 'option_a': 'Miami Heat', 'option_b': 'Denver Nuggets', 'option_a_percent': 27, 'option_b_percent': 73, 'poll_winner': 'Denver Nuggets', 'votes': 952, 'likes': 8, 'comments': 0}, {'post_date': '2023-05-12', 'post_type': 'Community Question', 'post_text': "I've made donations available for those who wish to contribute to support the growth and sustainability of this channel.", 'likes': 3, 'comments': 0}, {'post_date': '2023-05-09', 'post_type': 'Upload Teaser', 'post_text': 'Made a Caleb Martin top 10 video after his performance in game 7 last night.', 'linked_video_title': 'Caleb Martin Top 10 Plays of Career', 'linked_player': 'Caleb Martin', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-05-05', 'post_type': 'Community Question', 'post_text': 'Thank you to everyone for helping me reach 1,000 subscribers once again! Comment below with players for my next top 10 video.', 'likes': 8, 'comments': 0}, {'post_date': '2023-05-01', 'post_type': 'Upload Teaser', 'post_text': 'New Karl Malone video is up, go show support!', 'linked_video_title': 'Karl Malone Top 10 Plays of Career', 'linked_player': 'Karl Malone', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2023-04-28', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 video do you guys want next? (Fan suggestions added)', 'option_a': 'Karl Malone', 'option_b': 'Grant Hill', 'option_c': 'Jaylen Brown', 'option_d': 'Gordon Hayward', 'option_e': 'Nate Robinson', 'option_a_percent': 43, 'option_b_percent': 19, 'option_c_percent': 15, 'option_d_percent': 8, 'option_e_percent': 15, 'poll_winner': 'Karl Malone', 'votes': 237, 'likes': 3, 'comments': 3}, {'post_date': '2023-04-24', 'post_type': 'Upload Teaser', 'post_text': 'New video is up, had to make a top 10 for him after that crazy shot he hit in game 6 last night!', 'linked_video_title': 'Derrick White Top 10 Plays of Career', 'linked_player': 'Derrick White', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-04-21', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 next?', 'option_a': 'Gordon Hayward', 'option_b': 'Nate Robinson', 'option_c': 'Karl Malone', 'option_d': 'Mason Plumlee', 'option_e': 'Jeff Teague', 'option_a_percent': 16, 'option_b_percent': 18, 'option_c_percent': 58, 'option_d_percent': 5, 'option_e_percent': 3, 'poll_winner': 'Karl Malone', 'votes': 289, 'likes': 2, 'comments': 6}, {'post_date': '2023-04-18', 'post_type': 'Upload Teaser', 'post_text': 'Two videos in one day! Go show support on this video, as well as the Kareem top 10.', 'linked_video_title': 'Darius Garland Top 10 Plays of Career', 'linked_player': 'Darius Garland', 'linked_format': 'Top 10 Plays', 'likes': 2, 'comments': 0}, {'post_date': '2023-04-18', 'post_type': 'Upload Teaser', 'post_text': 'New Kareem top 10 video is up!', 'linked_video_title': 'Kareem Abdul-Jabbar Top 10 Plays of Career', 'linked_player': 'Kareem Abdul-Jabbar', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-04-15', 'post_type': 'Upload Teaser', 'post_text': 'Kareem video will be up hopefully soon!', 'linked_video_title': 'Kareem upcoming', 'linked_player': 'Kareem Abdul-Jabbar', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2023-04-12', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 should I do next?', 'option_a': 'Al Horford', 'option_b': 'Ricky Rubio', 'option_c': 'Kareem Abdul-Jabbar', 'option_d': 'Clyde Drexler', 'option_e': 'Patrick Ewing', 'option_a_percent': 17, 'option_b_percent': 9, 'option_c_percent': 53, 'option_d_percent': 11, 'option_e_percent': 11, 'poll_winner': 'Kareem Abdul-Jabbar', 'votes': 139, 'likes': 5, 'comments': 0}, {'post_date': '2023-04-09', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up! Go leave a like and show support!', 'linked_video_title': 'Dominique Wilkins Top 10 Plays of Career', 'linked_player': 'Dominique Wilkins', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-04-08', 'post_type': 'Upload Teaser', 'post_text': 'Dominique Wilkins top 10 will be up later tonight.', 'linked_video_title': 'Dominique upcoming', 'linked_player': 'Dominique Wilkins', 'linked_format': 'Top 10 Plays', 'likes': 4, 'comments': 0}, {'post_date': '2023-04-05', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 next?', 'option_a': 'Dominique Wilkins', 'option_b': 'Ricky Rubio', 'option_c': 'Lonzo Ball', 'option_d': 'Al Horford', 'option_e': 'Ben Simmons', 'option_a_percent': 63, 'option_b_percent': 5, 'option_c_percent': 12, 'option_d_percent': 9, 'option_e_percent': 11, 'poll_winner': 'Dominique Wilkins', 'votes': 130, 'likes': 3, 'comments': 1}, {'post_date': '2023-04-02', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up! Go comment who you want next.', 'linked_video_title': 'Dennis Schroder Top 10 Plays of Career', 'linked_player': 'Dennis Schroder', 'linked_format': 'Top 10 Plays', 'likes': 2, 'comments': 0}, {'post_date': '2023-03-30', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 next?', 'option_a': 'Ricky Rubio', 'option_b': 'Dennis Schroder', 'option_c': 'Ben Simmons', 'option_d': 'Lonzo Ball', 'option_e': 'Al Horford', 'option_a_percent': 11, 'option_b_percent': 38, 'option_c_percent': 15, 'option_d_percent': 20, 'option_e_percent': 16, 'poll_winner': 'Dennis Schroder', 'votes': 88, 'likes': 1, 'comments': 1}, {'post_date': '2023-03-27', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is uploaded!', 'linked_video_title': 'Dennis Rodman Top 10 Plays of Career', 'linked_player': 'Dennis Rodman', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-03-26', 'post_type': 'Community Question', 'post_text': 'Thank you everyone for 500 subscribers!! The Dennis Rodman top 10 will be up later today!', 'likes': 5, 'comments': 0}, {'post_date': '2023-03-23', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 do you want next?', 'option_a': 'Dennis Schroder', 'option_b': 'Lonzo Ball', 'option_c': 'Ricky Rubio', 'option_d': 'Dennis Rodman', 'option_e': 'Ben Simmons', 'option_a_percent': 10, 'option_b_percent': 9, 'option_c_percent': 10, 'option_d_percent': 64, 'option_e_percent': 6, 'poll_winner': 'Dennis Rodman', 'votes': 87, 'likes': 1, 'comments': 0}, {'post_date': '2023-03-20', 'post_type': 'Upload Teaser', 'post_text': 'New video is up!', 'linked_video_title': 'Nikola Jokic Top 10 Plays of Career', 'linked_player': 'Nikola Jokic', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-03-18', 'post_type': 'Community Question', 'post_text': 'Thank you to everyone who has been subscribing recently! The Nikola Jokic top 10 video is almost finished!', 'likes': 5, 'comments': 0}, {'post_date': '2023-03-15', 'post_type': 'Next Upload Poll', 'post_text': 'What top 10 should I make next?', 'option_a': 'Al Horford', 'option_b': 'Nikola Jokic', 'option_c': 'Lonzo Ball', 'option_d': 'Dennis Schroder', 'option_e': 'Ben Simmons', 'option_a_percent': 8, 'option_b_percent': 59, 'option_c_percent': 13, 'option_d_percent': 11, 'option_e_percent': 9, 'poll_winner': 'Nikola Jokic', 'votes': 75, 'likes': 3, 'comments': 1}, {'post_date': '2023-03-12', 'post_type': 'Next Upload Poll', 'post_text': 'Which top 10 next?', 'option_a': 'Al Horford', 'option_b': 'Lonzo Ball', 'option_c': 'Ben Simmons', 'option_d': 'Dennis Schroder', 'option_e': 'Brandon Ingram', 'option_a_percent': 14, 'option_b_percent': 14, 'option_c_percent': 12, 'option_d_percent': 22, 'option_e_percent': 38, 'poll_winner': 'Brandon Ingram', 'votes': 58, 'likes': 1, 'comments': 0}, {'post_date': '2023-03-09', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up!', 'linked_video_title': 'Donovan Mitchell Top 10 Plays of Career', 'linked_player': 'Donovan Mitchell', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-03-06', 'post_type': 'Player Debate', 'post_text': 'How many of you were subscribed to the last channel back when it had over 50,000 subscribers before it was hacked?', 'option_a': 'I was subscribed to the last channel', 'option_b': 'I just found out about this channel', 'option_a_percent': 43, 'option_b_percent': 57, 'poll_winner': 'I just found out about this channel', 'votes': 14, 'likes': 1, 'comments': 0}, {'post_date': '2023-03-03', 'post_type': 'Next Upload Poll', 'post_text': 'What top 10 should I make next?', 'option_a': 'Brandon Ingram', 'option_b': 'Al Horford', 'option_c': 'Donovan Mitchell', 'option_d': 'Ben Simmons', 'option_e': 'Lonzo Ball', 'option_a_percent': 11, 'option_b_percent': 15, 'option_c_percent': 61, 'option_d_percent': 9, 'option_e_percent': 4, 'poll_winner': 'Donovan Mitchell', 'votes': 46, 'likes': 2, 'comments': 0}, {'post_date': '2023-02-28', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is uploaded!', 'linked_video_title': 'J.R. Smith Top 10 Plays of Career', 'linked_player': 'J.R. Smith', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-25', 'post_type': 'Upload Teaser', 'post_text': 'New top 10 video is up! Go check it out!!', 'linked_video_title': 'CJ McCollum Top 10 Plays of Career', 'linked_player': 'CJ McCollum', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-22', 'post_type': 'Upload Teaser', 'post_text': 'Updated Michael Jordan Top 10 video is up!', 'linked_video_title': 'Michael Jordan Top 10 Plays of Career', 'linked_player': 'Michael Jordan', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-19', 'post_type': 'Upload Teaser', 'post_text': 'Third video of the day! Go check it out!', 'linked_video_title': 'Karl-Anthony Towns Top 10 Plays of Career', 'linked_player': 'Karl-Anthony Towns', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-16', 'post_type': 'Upload Teaser', 'post_text': 'New video! Go leave a like!', 'linked_video_title': 'Top 10 Buzzer Beaters of All Time', 'linked_format': 'Top 10 Buzzer Beaters', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-13', 'post_type': 'Upload Teaser', 'post_text': 'New video is up! Go check it out!', 'linked_video_title': 'David Robinson Top 10 Plays of Career', 'linked_player': 'David Robinson', 'linked_format': 'Top 10 Plays', 'likes': 1, 'comments': 0}, {'post_date': '2023-02-10', 'post_type': 'Upload Teaser', 'post_text': "An updated top 10 video of David Robinson's career plays is almost finished!", 'linked_video_title': 'David Robinson upcoming', 'linked_player': 'David Robinson', 'linked_format': 'Top 10 Plays', 'likes': 3, 'comments': 0}, {'post_date': '2023-02-07', 'post_type': 'Community Question', 'post_text': 'Update on the situation: The original NBATop10 account was terminated due to the hacker posting spam videos.', 'likes': 3, 'comments': 0}, {'post_date': '2023-02-04', 'post_type': 'Community Question', 'post_text': 'Hello everyone, this is my new channel. I’m doing my best to get the old one back after it being hacked.', 'likes': 4, 'comments': 1}]


def _community_safe_int(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _community_safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _community_season_from_date(date_text):
    try:
        month = int(str(date_text or "").split("-")[1])
    except Exception:
        return "Unknown"
    if month in (4, 5, 6):
        return "Playoffs / Finals"
    if month in (7, 8, 9):
        return "Offseason"
    return "Regular Season"


def _community_nba_year(date_text):
    try:
        year = int(str(date_text or "").split("-")[0])
        month = int(str(date_text or "").split("-")[1])
    except Exception:
        return ""
    return f"{year - 1}-{str(year)[-2:]}" if month <= 6 else f"{year}-{str(year + 1)[-2:]}"


def _community_option_count(data):
    return sum(1 for key in ["option_a", "option_b", "option_c", "option_d", "option_e"] if str(data.get(key) or "").strip())


def _community_score(data):
    return round(_community_safe_int(data.get("votes")) * 0.35 + _community_safe_int(data.get("comments")) * 3 + _community_safe_int(data.get("likes")), 2)


def create_community_automation_tables(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS community_post_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_date TEXT DEFAULT '',
        post_time TEXT DEFAULT '',
        post_type TEXT DEFAULT 'Next Upload Poll',
        poll_subtype TEXT DEFAULT '',
        season TEXT DEFAULT '',
        nba_year TEXT DEFAULT '',
        topic TEXT DEFAULT '',
        post_text TEXT DEFAULT '',
        option_a TEXT DEFAULT '',
        option_b TEXT DEFAULT '',
        option_c TEXT DEFAULT '',
        option_d TEXT DEFAULT '',
        option_e TEXT DEFAULT '',
        option_a_percent REAL DEFAULT 0,
        option_b_percent REAL DEFAULT 0,
        option_c_percent REAL DEFAULT 0,
        option_d_percent REAL DEFAULT 0,
        option_e_percent REAL DEFAULT 0,
        poll_winner TEXT DEFAULT '',
        trivia_answer TEXT DEFAULT '',
        linked_video_id TEXT DEFAULT '',
        linked_video_title TEXT DEFAULT '',
        linked_player TEXT DEFAULT '',
        linked_format TEXT DEFAULT '',
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        votes INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        subscribers_gained INTEGER DEFAULT 0,
        views_generated INTEGER DEFAULT 0,
        revenue_lift REAL DEFAULT 0,
        ai_engagement_score REAL DEFAULT 0,
        poll_option_count INTEGER DEFAULT 0,
        poll_uploaded_status TEXT DEFAULT '',
        upload_date_after_poll TEXT DEFAULT '',
        days_between_poll_and_upload INTEGER DEFAULT 0,
        historical_seed_version TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    for column, column_type in [
        ("poll_subtype", "TEXT DEFAULT ''"),
        ("season", "TEXT DEFAULT ''"),
        ("nba_year", "TEXT DEFAULT ''"),
        ("option_e", "TEXT DEFAULT ''"),
        ("option_a_percent", "REAL DEFAULT 0"),
        ("option_b_percent", "REAL DEFAULT 0"),
        ("option_c_percent", "REAL DEFAULT 0"),
        ("option_d_percent", "REAL DEFAULT 0"),
        ("option_e_percent", "REAL DEFAULT 0"),
        ("poll_winner", "TEXT DEFAULT ''"),
        ("trivia_answer", "TEXT DEFAULT ''"),
        ("linked_player", "TEXT DEFAULT ''"),
        ("linked_format", "TEXT DEFAULT ''"),
        ("ai_engagement_score", "REAL DEFAULT 0"),
        ("poll_option_count", "INTEGER DEFAULT 0"),
        ("poll_uploaded_status", "TEXT DEFAULT ''"),
        ("upload_date_after_poll", "TEXT DEFAULT ''"),
        ("days_between_poll_and_upload", "INTEGER DEFAULT 0"),
        ("historical_seed_version", "TEXT DEFAULT ''"),
    ]:
        try:
            add_column_if_missing(cursor, "community_post_results", column, column_type)
        except Exception:
            pass
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_date ON community_post_results(post_date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_type ON community_post_results(post_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_post_topic ON community_post_results(topic)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_poll_winner ON community_post_results(poll_winner)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_seed_version ON community_post_results(historical_seed_version)")


def ensure_community_automation_tables():
    connection = create_connection()
    cursor = connection.cursor()
    create_community_automation_tables(cursor)
    connection.commit()
    connection.close()


def _community_payload(data):
    data = dict(data or {})
    option_a = data.get("option_a", "") or data.get("poll_option_1", "")
    option_b = data.get("option_b", "") or data.get("poll_option_2", "")
    option_c = data.get("option_c", "") or data.get("poll_option_3", "")
    option_d = data.get("option_d", "") or data.get("poll_option_4", "")
    option_e = data.get("option_e", "") or data.get("poll_option_5", "")
    payload = {
        "post_date": data.get("post_date", ""),
        "post_time": data.get("post_time", ""),
        "post_type": data.get("post_type", "Next Upload Poll"),
        "poll_subtype": data.get("poll_subtype", ""),
        "topic": data.get("topic", "") or data.get("poll_winner", "") or data.get("linked_player", ""),
        "post_text": data.get("post_text", ""),
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "option_e": option_e,
        "option_a_percent": _community_safe_float(data.get("option_a_percent")),
        "option_b_percent": _community_safe_float(data.get("option_b_percent")),
        "option_c_percent": _community_safe_float(data.get("option_c_percent")),
        "option_d_percent": _community_safe_float(data.get("option_d_percent")),
        "option_e_percent": _community_safe_float(data.get("option_e_percent")),
        "poll_winner": data.get("poll_winner", ""),
        "trivia_answer": data.get("trivia_answer", ""),
        "linked_video_id": data.get("linked_video_id", ""),
        "linked_video_title": data.get("linked_video_title", ""),
        "linked_player": data.get("linked_player", "") or data.get("poll_winner", ""),
        "linked_format": data.get("linked_format", ""),
        "likes": _community_safe_int(data.get("likes")),
        "comments": _community_safe_int(data.get("comments")),
        "votes": _community_safe_int(data.get("votes")),
        "poll_uploaded_status": data.get("poll_uploaded_status", ""),
        "upload_date_after_poll": data.get("upload_date_after_poll", ""),
        "days_between_poll_and_upload": _community_safe_int(data.get("days_between_poll_and_upload")),
        "historical_seed_version": data.get("historical_seed_version", ""),
        "notes": data.get("notes", ""),
    }
    payload["season"] = data.get("season", "") or _community_season_from_date(payload["post_date"])
    payload["nba_year"] = data.get("nba_year", "") or _community_nba_year(payload["post_date"])
    payload["poll_option_count"] = _community_option_count(payload)
    payload["ai_engagement_score"] = _community_score(payload)
    return payload


_COMMUNITY_COLUMNS = [
    "post_date", "post_time", "post_type", "poll_subtype", "season", "nba_year", "topic", "post_text",
    "option_a", "option_b", "option_c", "option_d", "option_e",
    "option_a_percent", "option_b_percent", "option_c_percent", "option_d_percent", "option_e_percent",
    "poll_winner", "trivia_answer", "linked_video_id", "linked_video_title", "linked_player", "linked_format",
    "likes", "comments", "votes", "ai_engagement_score", "poll_option_count", "poll_uploaded_status",
    "upload_date_after_poll", "days_between_poll_and_upload", "historical_seed_version", "notes"
]


def save_community_post_result(data):
    ensure_community_automation_tables()
    payload = _community_payload(data or {})
    connection = create_connection()
    cursor = connection.cursor()
    columns = ", ".join(_COMMUNITY_COLUMNS)
    placeholders = ", ".join(["?"] * len(_COMMUNITY_COLUMNS))
    cursor.execute(f"""
    INSERT INTO community_post_results ({columns}, created_at, updated_at)
    VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, tuple(payload.get(column, "") for column in _COMMUNITY_COLUMNS))
    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def update_community_post_result(row_id, data):
    ensure_community_automation_tables()
    payload = _community_payload(data or {})
    connection = create_connection()
    cursor = connection.cursor()
    set_clause = ", ".join([f"{column}=?" for column in _COMMUNITY_COLUMNS])
    cursor.execute(f"""
    UPDATE community_post_results
    SET {set_clause}, updated_at=CURRENT_TIMESTAMP
    WHERE id=?
    """, tuple(payload.get(column, "") for column in _COMMUNITY_COLUMNS) + (int(row_id or 0),))
    connection.commit()
    connection.close()
    return int(row_id or 0)


def seed_community_post_history_if_needed():
    ensure_community_automation_tables()
    connection = create_connection()
    cursor = connection.cursor()
    inserted = 0
    for row in COMMUNITY_HISTORY_SEED_POSTS:
        payload = dict(row)
        payload["historical_seed_version"] = COMMUNITY_HISTORY_SEED_VERSION
        payload["notes"] = "Imported from all-time YouTube Community tab history."
        cursor.execute(
            "SELECT id FROM community_post_results WHERE post_date=? AND post_text=? LIMIT 1",
            (payload.get("post_date", ""), payload.get("post_text", ""))
        )
        if cursor.fetchone():
            continue
        p = _community_payload(payload)
        columns = ", ".join(_COMMUNITY_COLUMNS)
        placeholders = ", ".join(["?"] * len(_COMMUNITY_COLUMNS))
        cursor.execute(f"""
        INSERT INTO community_post_results ({columns}, created_at, updated_at)
        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, tuple(p.get(column, "") for column in _COMMUNITY_COLUMNS))
        inserted += 1
    connection.commit()
    connection.close()
    return inserted


def get_community_post_results(limit=500):
    ensure_community_automation_tables()
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("""
    SELECT *
    FROM community_post_results
    ORDER BY COALESCE(NULLIF(post_date, ''), created_at) DESC, created_at DESC, id DESC
    LIMIT ?
    """, (int(limit or 500),))
    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()
    return rows


def get_community_post_history(limit=500):
    return get_community_post_results(limit)


def get_community_post_learning():
    rows = get_community_post_results(1000)
    if not rows:
        return {
            "best_post_type": "Next Upload Poll",
            "best_type_score": 0,
            "best_time": "7:00 PM",
            "average_likes": 0,
            "average_comments": 0,
            "average_votes": 0,
            "top_topics": [],
            "insights": []
        }
    by_type = {}
    by_season = {}
    by_options = {}
    winners = {}
    total_likes = total_comments = total_votes = 0
    poll_rows = 0
    for row in rows:
        score = float(row.get("ai_engagement_score") or _community_score(row))
        typ = row.get("post_type") or "Next Upload Poll"
        by_type.setdefault(typ, [0, 0])
        by_type[typ][0] += score
        by_type[typ][1] += 1
        season = row.get("season") or "Unknown"
        by_season.setdefault(season, [0, 0])
        by_season[season][0] += score
        by_season[season][1] += 1
        opt_count = int(row.get("poll_option_count") or 0)
        if opt_count:
            by_options.setdefault(opt_count, [0, 0])
            by_options[opt_count][0] += score
            by_options[opt_count][1] += 1
        if row.get("poll_winner"):
            winners[row["poll_winner"]] = winners.get(row["poll_winner"], 0) + 1
        total_likes += int(row.get("likes") or 0)
        total_comments += int(row.get("comments") or 0)
        total_votes += int(row.get("votes") or 0)
        if int(row.get("votes") or 0) > 0:
            poll_rows += 1
    def best(bucket, default=""):
        if not bucket:
            return default, 0
        key, stats = max(bucket.items(), key=lambda kv: kv[1][0] / max(1, kv[1][1]))
        return key, round(stats[0] / max(1, stats[1]), 2)
    best_type, best_type_score = best(by_type, "Next Upload Poll")
    best_season, best_season_score = best(by_season, "Unknown")
    best_option_count, best_option_score = best(by_options, 4)
    type_stats = [
        {"post_type": key, "posts": stats[1], "score": round(stats[0] / max(1, stats[1]), 2)}
        for key, stats in sorted(by_type.items(), key=lambda kv: kv[1][0] / max(1, kv[1][1]), reverse=True)
    ]
    return {
        "best_post_type": best_type,
        "best_type_score": best_type_score,
        "best_time": "7:00 PM",
        "average_likes": round(total_likes / max(1, len(rows)), 1),
        "average_comments": round(total_comments / max(1, len(rows)), 1),
        "average_votes": round(total_votes / max(1, poll_rows), 1),
        "total_votes": total_votes,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "best_season": best_season,
        "best_season_score": best_season_score,
        "best_option_count": best_option_count,
        "best_option_score": best_option_score,
        "post_type_stats": type_stats,
        "top_topics": [{"topic": k, "score": v} for k, v in sorted(winners.items(), key=lambda item: item[1], reverse=True)[:10]],
        "top_poll_winners": [{"topic": k, "wins": v} for k, v in sorted(winners.items(), key=lambda item: item[1], reverse=True)[:10]],
        "insights": [
            "3 posts per week is the recommended cadence.",
            f"Best learned post type: {best_type}.",
            f"Best season window: {best_season}.",
            f"Best poll size: {best_option_count} options."
        ],
    }
