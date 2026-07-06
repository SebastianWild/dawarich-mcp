from __future__ import annotations

from datetime import datetime
from typing import Any

SUPPORTED_VISIT_STATUSES = {"suggested", "confirmed", "declined"}


class DawarichTools:
    def __init__(self, client: Any):
        self.client = client

    async def get_stats(
        self,
        year: int | None = None,
        include_monthly: bool = True,
    ) -> dict[str, Any]:
        stats = await self.client.stats()
        if year is not None:
            stats = {
                **stats,
                "yearlyStats": [
                    entry for entry in stats.get("yearlyStats", []) if entry.get("year") == year
                ],
            }
        if not include_monthly:
            for entry in stats.get("yearlyStats", []):
                entry.pop("monthlyDistanceKm", None)
        return {"summary": stats, "resource_uri": "dawarich://stats/summary"}

    async def search_places(
        self,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 1.0,
        limit: int = 10,
    ) -> dict[str, Any]:
        data = await self.client.search_places(query, latitude, longitude, radius_km, limit)
        return {"places": data, "count": len(data) if isinstance(data, list) else None}

    async def find_visits(
        self,
        start_at: str | None = None,
        end_at: str | None = None,
        status: str = "any",
        page: int | None = 1,
        per_page: int = 100,
        sw_lat: float | None = None,
        sw_lng: float | None = None,
        ne_lat: float | None = None,
        ne_lng: float | None = None,
    ) -> dict[str, Any]:
        if status != "any" and status not in SUPPORTED_VISIT_STATUSES:
            raise ValueError("status must be suggested, confirmed, declined, or any")
        bbox_selected = all(value is not None for value in (sw_lat, sw_lng, ne_lat, ne_lng))
        page_data = await self.client.list_visits(
            start_at=start_at,
            end_at=end_at,
            status=None if status == "any" else status,
            page=page,
            per_page=per_page,
            selection="true" if bbox_selected else None,
            sw_lat=sw_lat,
            sw_lng=sw_lng,
            ne_lat=ne_lat,
            ne_lng=ne_lng,
        )
        return {
            "visits": page_data.data,
            "pagination": page_data.pagination.__dict__,
            "resource_uri": "dawarich://visits",
        }

    async def get_timeline(
        self,
        start_at: str,
        end_at: str,
        distance_unit: str | None = None,
    ) -> dict[str, Any]:
        _validate_range_order(start_at, end_at)
        data = await self.client.timeline(
            start_at=start_at,
            end_at=end_at,
            distance_unit=distance_unit,
        )
        days = data.get("days", []) if isinstance(data, dict) else []
        return {"days": days, "day_count": len(days), "resource_uri": "dawarich://timeline"}

    async def get_map_context(
        self,
        start_at: str,
        end_at: str,
        include_hexagons: bool = False,
        include_fog: bool = False,
        max_features: int = 500,
    ) -> dict[str, Any]:
        _validate_range_order(start_at, end_at)
        bounds = await self.client.map_bounds(start_date=start_at, end_date=end_at)
        result: dict[str, Any] = {"bounds": bounds}
        if include_hexagons:
            hexagons = await self.client.map_hexagons(start_date=start_at, end_date=end_at)
            result["hexagons"] = _cap_feature_collection(hexagons, max_features)
        if include_fog:
            fog = await self.client.map_fog(start_date=start_at, end_date=end_at)
            indexes = fog.get("h3_indexes", []) if isinstance(fog, dict) else []
            result["fog"] = {
                **fog,
                "h3_indexes": indexes[:max_features],
                "truncated": len(indexes) > max_features,
            }
        return result

    async def find_points(
        self,
        start_at: str | None = None,
        end_at: str | None = None,
        page: int = 1,
        per_page: int = 100,
        order: str = "desc",
        include_anomalies: bool = False,
        anomalies_only: bool = False,
        slim: bool = True,
    ) -> dict[str, Any]:
        page_data = await self.client.points(
            start_at=start_at,
            end_at=end_at,
            page=page,
            per_page=per_page,
            order=order,
            include_anomalies=str(include_anomalies).lower(),
            anomalies_only=str(anomalies_only).lower(),
            slim=str(slim).lower(),
        )
        return {"points": page_data.data, "pagination": page_data.pagination.__dict__}

    async def create_place(
        self,
        name: str,
        latitude: float,
        longitude: float,
        note: str | None = None,
        tag_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        payload = _clean(
            {
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "note": note,
                "tag_ids": tag_ids,
            }
        )
        if dry_run:
            return {"dry_run": True, "would_create": payload}
        place = await self.client.create_place(payload)
        return {"dry_run": False, "place": place, "resource_uri": f"dawarich://places/{place.get('id')}"}

    async def update_place(
        self,
        place_id: int,
        name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        note: str | None = None,
        tag_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        before = await self.client.get_place(place_id)
        payload = _clean(
            {
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "note": note,
                "tag_ids": tag_ids,
            }
        )
        if dry_run:
            return {"dry_run": True, "before": before, "would_update": payload}
        place = await self.client.update_place(place_id, payload)
        return {"dry_run": False, "before": before, "place": place}

    async def delete_place(self, place_id: int, dry_run: bool = True) -> dict[str, Any]:
        place = await self.client.get_place(place_id)
        if dry_run:
            return {"dry_run": True, "would_delete": place}
        await self.client.delete_place(place_id)
        return {"dry_run": False, "deleted": place}

    async def create_visit(
        self,
        name: str,
        latitude: float,
        longitude: float,
        started_at: str,
        ended_at: str,
        status: str = "confirmed",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        _validate_range_order(started_at, ended_at)
        if status not in SUPPORTED_VISIT_STATUSES:
            raise ValueError("status must be suggested, confirmed, or declined")
        payload = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
        }
        if dry_run:
            return {"dry_run": True, "would_create": payload}
        visit = await self.client.create_visit(payload)
        return {"dry_run": False, "visit": visit, "resource_uri": f"dawarich://visits/{visit.get('id')}"}

    async def update_visit(
        self,
        visit_id: int,
        name: str | None = None,
        place_id: int | None = None,
        area_id: int | None = None,
        status: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        before = await self.client.get_visit(visit_id)
        if started_at and ended_at:
            _validate_range_order(started_at, ended_at)
        if status is not None and status not in SUPPORTED_VISIT_STATUSES:
            raise ValueError("status must be suggested, confirmed, or declined")
        payload = _clean(
            {
                "name": name,
                "place_id": place_id,
                "area_id": area_id,
                "status": status,
                "started_at": started_at,
                "ended_at": ended_at,
            }
        )
        if dry_run:
            return {"dry_run": True, "before": before, "would_update": payload}
        visit = await self.client.update_visit(visit_id, payload)
        return {"dry_run": False, "before": before, "visit": visit}

    async def select_visit_place(
        self,
        visit_id: int,
        place_id: int,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        possible_places = await self.client.possible_places(visit_id)
        if dry_run:
            return {"dry_run": True, "possible_places": possible_places, "would_select": place_id}
        visit = await self.client.select_visit_place(visit_id, place_id)
        return {"dry_run": False, "visit": visit}

    async def merge_visits(self, visit_ids: list[int], dry_run: bool = True) -> dict[str, Any]:
        if len(visit_ids) < 2:
            raise ValueError("visit_ids must contain at least two ids")
        visits = [await self.client.get_visit(visit_id) for visit_id in visit_ids]
        if dry_run:
            return {"dry_run": True, "would_merge": visits}
        merged = await self.client.merge_visits(visit_ids)
        return {"dry_run": False, "visit": merged}

    async def bulk_update_visit_status(
        self,
        visit_ids: list[int],
        status: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        if status not in SUPPORTED_VISIT_STATUSES:
            raise ValueError("status must be suggested, confirmed, or declined")
        if dry_run:
            return {"dry_run": True, "would_update": {"visit_ids": visit_ids, "status": status}}
        result = await self.client.bulk_update_visits(visit_ids, status)
        return {"dry_run": False, "result": result}

    async def create_trip(
        self,
        name: str,
        started_at: str,
        ended_at: str,
        description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        _validate_range_order(started_at, ended_at)
        return _unsupported_trip_api(
            "create",
            name=name,
            started_at=started_at,
            ended_at=ended_at,
            description=description,
            dry_run=dry_run,
        )

    async def update_trip(
        self,
        trip_id: int,
        dry_run: bool = False,
        **updates: Any,
    ) -> dict[str, Any]:
        return _unsupported_trip_api(
            "update",
            trip_id=trip_id,
            updates=_clean(updates),
            dry_run=dry_run,
        )

    async def delete_trip(self, trip_id: int, dry_run: bool = True) -> dict[str, Any]:
        return _unsupported_trip_api("delete", trip_id=trip_id, dry_run=dry_run)

    async def add_points(
        self,
        points: list[dict[str, Any]],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if dry_run:
            return {"dry_run": True, "would_create_count": len(points), "points": points}
        result = await self.client.add_points(points)
        return {"dry_run": False, "result": result}

    async def recalculate(
        self,
        kind: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        if dry_run:
            return {"dry_run": True, "would_recalculate": kind}
        if kind == "anomaly_filter":
            return {"dry_run": False, "result": await self.client.reapply_anomaly_filter()}
        if kind == "stats":
            return {"dry_run": False, "result": await self.client.recalculate()}
        if kind == "trip":
            return _unsupported_trip_api("recalculate", dry_run=dry_run)
        raise ValueError("kind must be stats, anomaly_filter, or trip")


def _unsupported_trip_api(action: str, **details: Any) -> dict[str, Any]:
    return {
        "supported": False,
        "action": action,
        "details": details,
        "message": (
            "Dawarich does not currently expose /api/v1/trips. Add Dawarich trip API "
            "routes before enabling MCP trip mutations."
        ),
    }


def _validate_range_order(start_at: str, end_at: str) -> None:
    if _parse_iso(end_at) <= _parse_iso(start_at):
        raise ValueError("ended_at must be after started_at")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _cap_feature_collection(data: dict[str, Any], max_features: int) -> dict[str, Any]:
    features = data.get("features", []) if isinstance(data, dict) else []
    return {
        **data,
        "features": features[:max_features],
        "truncated": len(features) > max_features,
    }


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
