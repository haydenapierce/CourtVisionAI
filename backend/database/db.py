import sqlite3
import os

DB_FOLDER = "database"
DATABASE_NAME = os.path.join(DB_FOLDER, "courtvision.db")


def create_connection():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def add_column_if_missing(cursor, table, column, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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
    add_column_if_missing(cursor, "videos", "content_type", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "player_name", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "videos", "title_length", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "upload_year", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "videos", "ai_score", "REAL DEFAULT 0")
    add_column_if_missing(cursor, "videos", "synced_at", "TEXT DEFAULT CURRENT_TIMESTAMP")

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
        title,
        video_id,
        published,
        views,
        likes,
        comments,
        thumbnail,
        estimated_revenue,
        estimated_rpm,
        content_type,
        player_name,
        title_length,
        upload_year,
        ai_score,
        synced_at
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
        title,
        video_id,
        published,
        views,
        likes,
        comments,
        thumbnail,
        estimated_revenue,
        estimated_rpm,
        content_type,
        player_name,
        title_length,
        upload_year,
        ai_score
    ))

    connection.commit()
    connection.close()


def get_saved_videos():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM videos
    ORDER BY views DESC
    """)

    rows = cursor.fetchall()
    connection.close()

    videos = []

    for row in rows:
        videos.append(dict(row))

    return videos


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
        AVG(views) as average_views,
        SUM(estimated_revenue) as estimated_revenue
    FROM videos
    """)

    row = cursor.fetchone()
    connection.close()

    return {
        "total_videos": row["total_videos"] or 0,
        "total_views": row["total_views"] or 0,
        "total_likes": row["total_likes"] or 0,
        "total_comments": row["total_comments"] or 0,
        "average_views": int(row["average_views"] or 0),
        "estimated_revenue": round(row["estimated_revenue"] or 0, 2)
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