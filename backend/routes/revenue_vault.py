from fastapi import APIRouter
from pydantic import BaseModel
from database.db import (
    create_connection,
    get_best_revenue_summary,
    get_best_channel_revenue_entries,
    get_best_video_revenue_entries,
)

router = APIRouter()

REVENUE_PERIODS = ["lifetime", "365d", "90d", "28d", "7d"]


class RevenueVaultSnapshot(BaseModel):
    snapshot_name: str = ""
    notes: str = ""


def safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def safe_int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def normalize_period(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


def ensure_revenue_vault_table():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS revenue_vault (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_name TEXT DEFAULT '',
        total_channel_revenue REAL DEFAULT 0,
        total_video_revenue REAL DEFAULT 0,
        channel_lifetime REAL DEFAULT 0,
        channel_365d REAL DEFAULT 0,
        channel_90d REAL DEFAULT 0,
        channel_28d REAL DEFAULT 0,
        channel_7d REAL DEFAULT 0,
        video_lifetime REAL DEFAULT 0,
        video_365d REAL DEFAULT 0,
        video_90d REAL DEFAULT 0,
        video_28d REAL DEFAULT 0,
        video_7d REAL DEFAULT 0,
        channel_entries INTEGER DEFAULT 0,
        video_entries INTEGER DEFAULT 0,
        revenue_source TEXT DEFAULT 'revenue_tracker',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("PRAGMA table_info(revenue_vault)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    if "revenue_source" not in existing_columns:
        cursor.execute("ALTER TABLE revenue_vault ADD COLUMN revenue_source TEXT DEFAULT 'revenue_tracker'")

    connection.commit()
    connection.close()


def sum_by_period(entries):
    output = {period: 0 for period in REVENUE_PERIODS}

    for entry in entries:
        period = normalize_period(entry.get("period_type") or entry.get("period"))
        amount = safe_float(
            entry.get("amount")
            if entry.get("amount") is not None
            else entry.get("estimated_revenue")
        )

        if period in output:
            output[period] += amount

    return {key: round(value, 2) for key, value in output.items()}


def get_summary_total(summary, key_primary, key_fallback):
    value = summary.get(key_primary)
    if value is None:
        value = summary.get(key_fallback)
    return safe_float(value)


@router.post("/revenue-vault/snapshot")
def create_revenue_vault_snapshot(snapshot: RevenueVaultSnapshot):
    ensure_revenue_vault_table()

    summary = get_best_revenue_summary()
    channel_entries = get_best_channel_revenue_entries()
    video_entries = get_best_video_revenue_entries()

    channel_periods = summary.get("channel_by_period") or sum_by_period(channel_entries)
    video_periods = summary.get("video_by_period") or sum_by_period(video_entries)

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO revenue_vault (
        snapshot_name,
        total_channel_revenue,
        total_video_revenue,
        channel_lifetime,
        channel_365d,
        channel_90d,
        channel_28d,
        channel_7d,
        video_lifetime,
        video_365d,
        video_90d,
        video_28d,
        video_7d,
        channel_entries,
        video_entries,
        revenue_source,
        notes,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        snapshot.snapshot_name or "Revenue Tracker Snapshot",
        get_summary_total(summary, "total_channel_youtube_revenue", "total_channel_manual_revenue"),
        get_summary_total(summary, "total_video_youtube_revenue", "total_video_manual_revenue"),
        safe_float(channel_periods.get("lifetime")),
        safe_float(channel_periods.get("365d")),
        safe_float(channel_periods.get("90d")),
        safe_float(channel_periods.get("28d")),
        safe_float(channel_periods.get("7d")),
        safe_float(video_periods.get("lifetime")),
        safe_float(video_periods.get("365d")),
        safe_float(video_periods.get("90d")),
        safe_float(video_periods.get("28d")),
        safe_float(video_periods.get("7d")),
        safe_int(summary.get("channel_revenue_entries") or len(channel_entries)),
        safe_int(summary.get("video_revenue_entries") or len(video_entries)),
        summary.get("source") or "revenue_tracker",
        snapshot.notes or ""
    ))

    connection.commit()
    new_id = cursor.lastrowid
    connection.close()

    return {
        "message": "Revenue Vault snapshot saved",
        "id": new_id,
        "source": summary.get("source") or "revenue_tracker"
    }


@router.get("/revenue-vault")
def get_revenue_vault():
    ensure_revenue_vault_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM revenue_vault
    ORDER BY created_at DESC, id DESC
    """)

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    return {
        "snapshots": rows,
        "snapshot_count": len(rows)
    }


@router.get("/revenue-vault/latest")
def get_latest_revenue_vault_snapshot():
    ensure_revenue_vault_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT *
    FROM revenue_vault
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """)

    row = cursor.fetchone()
    connection.close()

    return {
        "latest_snapshot": dict(row) if row else None
    }


@router.delete("/revenue-vault/{snapshot_id}")
def delete_revenue_vault_snapshot(snapshot_id: int):
    ensure_revenue_vault_table()

    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM revenue_vault WHERE id=?", (snapshot_id,))

    connection.commit()
    connection.close()

    return {
        "message": "Revenue Vault snapshot deleted",
        "id": snapshot_id
    }
