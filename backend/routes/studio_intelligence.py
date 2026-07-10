from fastapi import APIRouter
from database.db import create_connection
from datetime import datetime, timedelta

router = APIRouter()

STUDIO_INTELLIGENCE_CACHE = {
    "created_at": None,
    "payload": None,
}
STUDIO_INTELLIGENCE_CACHE_SECONDS = 300


def safe_number(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def normalize_period(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


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
        period_type TEXT DEFAULT '28d',
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


def get_breakdown_rankings(breakdown_type, limit=25):
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        item_name,
        breakdown_type,
        period_type,
        SUM(views) as total_views,
        SUM(watch_time_hours) as total_watch_time_hours,
        SUM(impressions) as total_impressions,
        SUM(estimated_revenue) as total_revenue,
        SUM(subscribers) as total_subscribers,
        AVG(ctr) as average_ctr,
        AVG(rpm) as average_rpm,
        AVG(cpm) as average_cpm,
        AVG(percentage) as average_percentage,
        COUNT(*) as entries
    FROM studio_breakdowns
    WHERE breakdown_type=?
    GROUP BY item_name, breakdown_type, period_type
    ORDER BY total_views DESC
    LIMIT ?
    """, (breakdown_type, limit))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    cleaned = []

    for row in rows:
        cleaned.append({
            "item_name": row.get("item_name") or "Unknown",
            "breakdown_type": row.get("breakdown_type") or breakdown_type,
            "period_type": normalize_period(row.get("period_type")),
            "total_views": int(row.get("total_views") or 0),
            "total_watch_time_hours": round(safe_number(row.get("total_watch_time_hours")), 2),
            "total_impressions": int(row.get("total_impressions") or 0),
            "total_revenue": round(safe_number(row.get("total_revenue")), 2),
            "total_subscribers": int(row.get("total_subscribers") or 0),
            "average_ctr": round(safe_number(row.get("average_ctr")), 2),
            "average_rpm": round(safe_number(row.get("average_rpm")), 2),
            "average_cpm": round(safe_number(row.get("average_cpm")), 2),
            "average_percentage": round(safe_number(row.get("average_percentage")), 2),
            "entries": int(row.get("entries") or 0)
        })

    return cleaned


def get_all_breakdown_rankings(limit_per_type=25):
    """
    Reads every Studio breakdown category in one SQLite query rather than
    opening the database once for each of roughly 27 categories.
    """
    ensure_studio_breakdowns_table()

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        item_name,
        breakdown_type,
        period_type,
        SUM(views) as total_views,
        SUM(watch_time_hours) as total_watch_time_hours,
        SUM(impressions) as total_impressions,
        SUM(estimated_revenue) as total_revenue,
        SUM(subscribers) as total_subscribers,
        AVG(ctr) as average_ctr,
        AVG(rpm) as average_rpm,
        AVG(cpm) as average_cpm,
        AVG(percentage) as average_percentage,
        COUNT(*) as entries
    FROM studio_breakdowns
    GROUP BY item_name, breakdown_type, period_type
    ORDER BY breakdown_type ASC, total_views DESC
    """)

    grouped = {}

    for raw_row in cursor.fetchall():
        row = dict(raw_row)
        breakdown_type = row.get("breakdown_type") or "unknown"
        rows = grouped.setdefault(breakdown_type, [])

        if len(rows) >= limit_per_type:
            continue

        rows.append({
            "item_name": row.get("item_name") or "Unknown",
            "breakdown_type": breakdown_type,
            "period_type": normalize_period(row.get("period_type")),
            "total_views": int(row.get("total_views") or 0),
            "total_watch_time_hours": round(safe_number(row.get("total_watch_time_hours")), 2),
            "total_impressions": int(row.get("total_impressions") or 0),
            "total_revenue": round(safe_number(row.get("total_revenue")), 2),
            "total_subscribers": int(row.get("total_subscribers") or 0),
            "average_ctr": round(safe_number(row.get("average_ctr")), 2),
            "average_rpm": round(safe_number(row.get("average_rpm")), 2),
            "average_cpm": round(safe_number(row.get("average_cpm")), 2),
            "average_percentage": round(safe_number(row.get("average_percentage")), 2),
            "entries": int(row.get("entries") or 0),
        })

    connection.close()
    return grouped


def top_item(rankings):
    if rankings:
        return rankings[0]
    return None


def build_summary(data):
    total_breakdown_groups = 0
    total_entries = 0
    total_views = 0
    total_revenue = 0
    total_subscribers = 0

    for rows in data.values():
        if rows:
            total_breakdown_groups += 1

        for item in rows:
            total_entries += int(item.get("entries") or 0)
            total_views += int(item.get("total_views") or 0)
            total_revenue += safe_number(item.get("total_revenue"))
            total_subscribers += int(item.get("total_subscribers") or 0)

    return {
        "breakdown_groups_with_data": total_breakdown_groups,
        "total_entries": total_entries,
        "total_views": total_views,
        "total_revenue": round(total_revenue, 2),
        "total_subscribers": total_subscribers
    }


def build_insights(data):
    insights = []

    if data["countries"]:
        item = data["countries"][0]
        insights.append(
            f"Top country is {item['item_name']} with {item['total_views']:,} views."
        )

    if data["cities"]:
        item = data["cities"][0]
        insights.append(
            f"Top city is {item['item_name']} with {item['total_views']:,} views."
        )

    if data["traffic_sources"]:
        item = data["traffic_sources"][0]
        insights.append(
            f"Best traffic source is {item['item_name']} with {item['total_views']:,} views."
        )

    if data["playlists"]:
        item = data["playlists"][0]
        insights.append(
            f"Best playlist is {item['item_name']} with {item['total_views']:,} views."
        )

    if data["devices"]:
        item = data["devices"][0]
        insights.append(
            f"Most viewers use {item['item_name']}."
        )

    if data["revenue_sources"]:
        item = data["revenue_sources"][0]
        insights.append(
            f"Best revenue source is {item['item_name']} with ${item['total_revenue']:,} tracked revenue."
        )

    if data["ad_types"]:
        item = data["ad_types"][0]
        insights.append(
            f"Top ad type is {item['item_name']}."
        )

    if data["viewer_ages"]:
        item = data["viewer_ages"][0]
        insights.append(
            f"Top viewer age group is {item['item_name']}."
        )

    if data["viewer_genders"]:
        item = data["viewer_genders"][0]
        insights.append(
            f"Top viewer gender category is {item['item_name']}."
        )

    if data["subscription_sources"]:
        item = data["subscription_sources"][0]
        insights.append(
            f"Best subscriber source is {item['item_name']} with {item['total_subscribers']:,} subscribers."
        )

    if data["end_screen_elements"]:
        item = data["end_screen_elements"][0]
        insights.append(
            f"Best end screen element is {item['item_name']}."
        )

    if data["community_posts"]:
        item = data["community_posts"][0]
        insights.append(
            f"Best community post is {item['item_name']}."
        )

    if not insights:
        insights.append(
            "No Studio Breakdown data entered yet. Add YouTube Studio breakdown snapshots to unlock analytics intelligence."
        )

    return insights


def build_recommendations(data):
    recommendations = []

    if data["traffic_sources"]:
        item = data["traffic_sources"][0]
        recommendations.append(
            f"Optimize future uploads for {item['item_name']} traffic because it is currently your strongest source."
        )

    if data["playlists"]:
        item = data["playlists"][0]
        recommendations.append(
            f"Use end screens and pinned comments to push viewers toward the playlist '{item['item_name']}'."
        )

    if data["countries"]:
        item = data["countries"][0]
        recommendations.append(
            f"Consider upload timing and title wording for viewers in {item['item_name']}."
        )

    if data["cities"]:
        item = data["cities"][0]
        recommendations.append(
            f"City-level interest is strongest in {item['item_name']}; this may help with upload timing and topic selection."
        )

    if data["devices"]:
        item = data["devices"][0]
        recommendations.append(
            f"Since {item['item_name']} is your top device type, make thumbnails and titles easy to read on that screen size."
        )

    if data["viewer_ages"]:
        item = data["viewer_ages"][0]
        recommendations.append(
            f"Shape titles and player choices around your strongest age group: {item['item_name']}."
        )

    if data["subscription_sources"]:
        item = data["subscription_sources"][0]
        recommendations.append(
            f"Your strongest subscriber source is {item['item_name']}; use that source more intentionally in future uploads."
        )

    if data["community_posts"]:
        item = data["community_posts"][0]
        recommendations.append(
            f"Study the community post '{item['item_name']}' because it has the strongest recorded signal."
        )

    if data["end_screen_elements"]:
        item = data["end_screen_elements"][0]
        recommendations.append(
            f"Use more end screens like '{item['item_name']}' because it has the strongest recorded signal."
        )

    if not recommendations:
        recommendations.append(
            "Add Studio Breakdown entries first. Once data exists, CourtVision will recommend upload timing, playlist strategy, traffic strategy, device strategy, audience strategy, and end screen choices."
        )

    return recommendations


def build_leak_warnings(data):
    warnings = []

    if data["traffic_sources"]:
        top = data["traffic_sources"][0]
        if top["average_percentage"] >= 60:
            warnings.append(
                f"Traffic may be too dependent on {top['item_name']} because it represents about {top['average_percentage']}% of tracked traffic."
            )

    if data["devices"]:
        top = data["devices"][0]
        if top["average_percentage"] >= 65:
            warnings.append(
                f"Device audience may be concentrated on {top['item_name']}. Check thumbnails on other device sizes."
            )

    if data["countries"]:
        top = data["countries"][0]
        if top["average_percentage"] >= 70:
            warnings.append(
                f"Audience may be heavily concentrated in {top['item_name']}. Consider topics with wider international reach."
            )

    if data["playlists"]:
        weak_playlists = [
            item for item in data["playlists"]
            if item["total_views"] <= 100 and item["entries"] > 0
        ]

        if weak_playlists:
            warnings.append(
                "Some playlists have very low tracked views. These may need better end screens, pinned comments, or homepage placement."
            )

    if not warnings:
        warnings.append("No major analytics leak warnings detected yet.")

    return warnings


def build_growth_opportunities(data):
    opportunities = []

    if data["traffic_sources"]:
        for item in data["traffic_sources"][:3]:
            opportunities.append(
                f"Double down on {item['item_name']} because it is one of your top traffic sources."
            )

    if data["playlists"]:
        item = data["playlists"][0]
        opportunities.append(
            f"Build more watch sessions around '{item['item_name']}' because it is your strongest playlist signal."
        )

    if data["end_screen_elements"]:
        item = data["end_screen_elements"][0]
        opportunities.append(
            f"Use '{item['item_name']}' as a model for future end screen choices."
        )

    if data["viewer_ages"]:
        item = data["viewer_ages"][0]
        opportunities.append(
            f"Prioritize players and eras that match your strongest age group: {item['item_name']}."
        )

    if data["countries"]:
        item = data["countries"][0]
        opportunities.append(
            f"Schedule and title uploads with {item['item_name']} viewers in mind."
        )

    if not opportunities:
        opportunities.append(
            "Add more Studio Breakdown entries to unlock growth opportunities."
        )

    return opportunities


@router.get("/studio-intelligence")
def studio_intelligence():
    cached_at = STUDIO_INTELLIGENCE_CACHE.get("created_at")
    cached_payload = STUDIO_INTELLIGENCE_CACHE.get("payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=STUDIO_INTELLIGENCE_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    grouped = get_all_breakdown_rankings()

    data = {
        "countries": grouped.get("country", []),
        "cities": grouped.get("city", []),
        "traffic_sources": grouped.get("traffic_source", []),
        "playlists": grouped.get("playlist", []),
        "devices": grouped.get("device_type", []),
        "operating_systems": grouped.get("operating_system", []),
        "revenue_sources": grouped.get("revenue_source", []),
        "ad_types": grouped.get("ad_type", []),
        "viewer_ages": grouped.get("viewer_age", []),
        "viewer_genders": grouped.get("viewer_gender", []),
        "new_returning_viewers": grouped.get("new_returning_viewers", []),
        "subscription_sources": grouped.get("subscription_source", []),
        "subscription_statuses": grouped.get("subscription_status", []),
        "youtube_products": grouped.get("youtube_product", []),
        "end_screen_elements": grouped.get("end_screen_element", []),
        "end_screen_element_types": grouped.get("end_screen_element_type", []),
        "cards": grouped.get("card", []),
        "card_types": grouped.get("card_type", []),
        "playback_locations": grouped.get("playback_location", []),
        "player_types": grouped.get("player_type", []),
        "sharing_services": grouped.get("sharing_service", []),
        "community_posts": grouped.get("community_post", []),
        "subtitles_cc": grouped.get("subtitles_cc", []),
        "video_info_languages": grouped.get("video_info_language", []),
        "translation_uses": grouped.get("translation_use", []),
        "organic_paid_traffic": grouped.get("organic_paid_traffic", []),
        "transaction_types": grouped.get("transaction_type", []),
    }

    payload = {
        "summary": build_summary(data),
        "top_country": top_item(data["countries"]),
        "top_city": top_item(data["cities"]),
        "top_traffic_source": top_item(data["traffic_sources"]),
        "top_playlist": top_item(data["playlists"]),
        "top_device": top_item(data["devices"]),
        "top_operating_system": top_item(data["operating_systems"]),
        "top_revenue_source": top_item(data["revenue_sources"]),
        "top_ad_type": top_item(data["ad_types"]),
        "top_viewer_age": top_item(data["viewer_ages"]),
        "top_viewer_gender": top_item(data["viewer_genders"]),
        "top_community_post": top_item(data["community_posts"]),
        "top_end_screen": top_item(data["end_screen_elements"]),
        "rankings": data,
        "insights": build_insights(data),
        "recommendations": build_recommendations(data),
        "leak_warnings": build_leak_warnings(data),
        "growth_opportunities": build_growth_opportunities(data),
    }

    STUDIO_INTELLIGENCE_CACHE["created_at"] = datetime.now()
    STUDIO_INTELLIGENCE_CACHE["payload"] = payload
    return payload
