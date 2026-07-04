from fastapi import APIRouter
from pydantic import BaseModel

from database.db import (
    save_manual_video_analytics,
    get_manual_video_analytics_entries,
    delete_manual_video_analytics,
    save_manual_audience_demographic,
    get_manual_audience_demographic_entries,
    delete_manual_audience_demographic,
    save_manual_traffic_source,
    get_manual_traffic_source_entries,
    delete_manual_traffic_source,
    save_manual_device_stat,
    get_manual_device_stat_entries,
    delete_manual_device_stat,
    get_manual_analytics_summary
)

router = APIRouter()


class ManualVideoAnalyticsEntry(BaseModel):
    video_id: str = ""
    title: str = ""
    period_type: str = "7d"
    impressions: int = 0
    ctr: float = 0
    watch_time_hours: float = 0
    average_view_duration: str = ""
    average_percentage_viewed: float = 0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    returning_viewers: int = 0
    new_viewers: int = 0
    end_screen_clicks: int = 0
    playlist_starts: int = 0
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class ManualAudienceDemographicEntry(BaseModel):
    scope: str = "channel"
    video_id: str = ""
    title: str = ""
    period_type: str = "30d"
    country: str = ""
    gender: str = ""
    age_range: str = ""
    percentage: float = 0
    views: int = 0
    watch_time_hours: float = 0
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class ManualTrafficSourceEntry(BaseModel):
    scope: str = "channel"
    video_id: str = ""
    title: str = ""
    period_type: str = "30d"
    source: str = ""
    views: int = 0
    percentage: float = 0
    watch_time_hours: float = 0
    average_view_duration: str = ""
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class ManualDeviceStatEntry(BaseModel):
    scope: str = "channel"
    video_id: str = ""
    title: str = ""
    period_type: str = "30d"
    device_type: str = ""
    views: int = 0
    percentage: float = 0
    watch_time_hours: float = 0
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


@router.get("/analytics/summary")
def analytics_summary():
    return {
        "summary": get_manual_analytics_summary()
    }


@router.get("/analytics/video")
def get_video_analytics():
    return {
        "video_analytics": get_manual_video_analytics_entries()
    }


@router.post("/analytics/video")
def create_video_analytics(entry: ManualVideoAnalyticsEntry):
    new_id = save_manual_video_analytics(entry.dict())

    return {
        "message": "Video analytics saved",
        "id": new_id
    }


@router.delete("/analytics/video/{entry_id}")
def remove_video_analytics(entry_id: int):
    delete_manual_video_analytics(entry_id)

    return {
        "message": "Video analytics deleted",
        "id": entry_id
    }


@router.get("/analytics/audience")
def get_audience_demographics():
    return {
        "audience": get_manual_audience_demographic_entries()
    }


@router.post("/analytics/audience")
def create_audience_demographic(entry: ManualAudienceDemographicEntry):
    new_id = save_manual_audience_demographic(entry.dict())

    return {
        "message": "Audience demographic saved",
        "id": new_id
    }


@router.delete("/analytics/audience/{entry_id}")
def remove_audience_demographic(entry_id: int):
    delete_manual_audience_demographic(entry_id)

    return {
        "message": "Audience demographic deleted",
        "id": entry_id
    }


@router.get("/analytics/traffic")
def get_traffic_sources():
    return {
        "traffic_sources": get_manual_traffic_source_entries()
    }


@router.post("/analytics/traffic")
def create_traffic_source(entry: ManualTrafficSourceEntry):
    new_id = save_manual_traffic_source(entry.dict())

    return {
        "message": "Traffic source saved",
        "id": new_id
    }


@router.delete("/analytics/traffic/{entry_id}")
def remove_traffic_source(entry_id: int):
    delete_manual_traffic_source(entry_id)

    return {
        "message": "Traffic source deleted",
        "id": entry_id
    }


@router.get("/analytics/devices")
def get_device_stats():
    return {
        "devices": get_manual_device_stat_entries()
    }


@router.post("/analytics/devices")
def create_device_stat(entry: ManualDeviceStatEntry):
    new_id = save_manual_device_stat(entry.dict())

    return {
        "message": "Device stat saved",
        "id": new_id
    }


@router.delete("/analytics/devices/{entry_id}")
def remove_device_stat(entry_id: int):
    delete_manual_device_stat(entry_id)

    return {
        "message": "Device stat deleted",
        "id": entry_id
    }