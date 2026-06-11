"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Dict, Any, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(..., min_length=5, max_length=280)
    expires_at: str
    starts_at: Optional[str] = None


def _validate_dates(starts_at: Optional[str], expires_at: str) -> None:
    try:
        expires_date = date.fromisoformat(expires_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Expiration date must use YYYY-MM-DD format") from exc

    if starts_at:
        try:
            starts_date = date.fromisoformat(starts_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Start date must use YYYY-MM-DD format") from exc

        if starts_date > expires_date:
            raise HTTPException(status_code=400, detail="Start date must be on or before expiration date")


def _authenticate_user(username: str) -> Dict[str, Any]:
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher


def _normalize_message(message: str) -> str:
    normalized = message.strip()
    if len(normalized) < 5:
        raise HTTPException(status_code=400, detail="Announcement message must contain at least 5 characters")
    return normalized


def _serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "message": document.get("message", ""),
        "starts_at": document.get("starts_at"),
        "expires_at": document.get("expires_at"),
        "created_by": document.get("created_by")
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements for public display."""
    today = date.today().isoformat()
    query = {
        "expires_at": {"$gte": today},
        "$or": [
            {"starts_at": None},
            {"starts_at": {"$exists": False}},
            {"starts_at": {"$lte": today}}
        ]
    }

    announcements = announcements_collection.find(query).sort("expires_at", 1)
    return [_serialize_announcement(item) for item in announcements]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(username: str = Query(...)) -> List[Dict[str, Any]]:
    """Get all announcements for announcement management UI."""
    _authenticate_user(username)
    announcements = announcements_collection.find({}).sort("expires_at", 1)
    return [_serialize_announcement(item) for item in announcements]


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, username: str = Query(...)) -> Dict[str, Any]:
    """Create an announcement. Authentication is required."""
    teacher = _authenticate_user(username)
    _validate_dates(payload.starts_at, payload.expires_at)
    message = _normalize_message(payload.message)

    created = {
        "message": message,
        "starts_at": payload.starts_at,
        "expires_at": payload.expires_at,
        "created_by": teacher.get("display_name", teacher.get("_id"))
    }

    result = announcements_collection.insert_one(created)
    created["_id"] = result.inserted_id
    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    username: str = Query(...)
) -> Dict[str, Any]:
    """Update an existing announcement. Authentication is required."""
    _authenticate_user(username)
    _validate_dates(payload.starts_at, payload.expires_at)
    message = _normalize_message(payload.message)

    try:
        object_id = ObjectId(announcement_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    updates = {
        "message": message,
        "starts_at": payload.starts_at,
        "expires_at": payload.expires_at
    }

    result = announcements_collection.update_one({"_id": object_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    announcement = announcements_collection.find_one({"_id": object_id})
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return _serialize_announcement(announcement)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(announcement_id: str, username: str = Query(...)) -> Dict[str, str]:
    """Delete an announcement. Authentication is required."""
    _authenticate_user(username)

    try:
        object_id = ObjectId(announcement_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
