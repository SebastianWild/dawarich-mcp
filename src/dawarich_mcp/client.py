from __future__ import annotations

import json as json_module
from dataclasses import dataclass
from typing import Any

import httpx

from .config import DawarichMcpConfig


class DawarichClientError(RuntimeError):
    def __init__(self, status_code: int, message: str, payload: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class Pagination:
    current_page: int | None = None
    total_pages: int | None = None
    total_count: int | None = None

    @classmethod
    def from_headers(cls, headers: httpx.Headers) -> Pagination:
        return cls(
            current_page=_optional_int(headers.get("X-Current-Page")),
            total_pages=_optional_int(headers.get("X-Total-Pages")),
            total_count=_optional_int(headers.get("X-Total-Count")),
        )


@dataclass(frozen=True)
class PaginatedResponse:
    data: Any
    pagination: Pagination


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class DawarichClient:
    def __init__(
        self,
        config: DawarichMcpConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = http_client or httpx.AsyncClient(timeout=config.timeout_seconds)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._request("GET", path, params=params)
        return _decode_response(response)

    async def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> PaginatedResponse:
        response = await self._request("GET", path, params=params)
        return PaginatedResponse(
            data=_decode_response(response),
            pagination=Pagination.from_headers(response.headers),
        )

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._request("POST", path, params=params, json=json)
        return _decode_response(response)

    async def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._request("PATCH", path, params=params, json=json)
        return _decode_response(response)

    async def delete(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._request("DELETE", path, params=params, json=json)
        if response.status_code == 204:
            return None
        return _decode_response(response)

    async def stats(self) -> dict[str, Any]:
        data = await self.get("/api/v1/stats")
        if isinstance(data, str):
            return json_module.loads(data)
        return data

    async def health(self) -> dict[str, Any]:
        return await self.get("/api/v1/health")

    async def user(self) -> dict[str, Any]:
        return await self.get("/api/v1/users/me")

    async def settings(self) -> dict[str, Any]:
        return await self.get("/api/v1/settings")

    async def plan(self) -> dict[str, Any]:
        return await self.get("/api/v1/plan")

    async def search_places(
        self,
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 1.0,
        limit: int = 10,
    ) -> Any:
        if latitude is not None and longitude is not None:
            return await self.get(
                "/api/v1/places/search",
                params={
                    "q": query or "",
                    "lat": latitude,
                    "lon": longitude,
                    "radius": radius_km,
                    "limit": limit,
                },
            )
        return (
            await self.get_paginated(
                "/api/v1/places",
                params={"filter": "all", "page": 1, "per_page": min(limit, 500)},
            )
        ).data

    async def list_places(self, **params: Any) -> PaginatedResponse:
        return await self.get_paginated("/api/v1/places", params=_clean(params))

    async def get_place(self, place_id: int) -> dict[str, Any]:
        return await self.get(f"/api/v1/places/{place_id}")

    async def create_place(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post("/api/v1/places", json={"place": payload})

    async def update_place(self, place_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/api/v1/places/{place_id}", json={"place": payload})

    async def delete_place(self, place_id: int) -> None:
        await self.delete(f"/api/v1/places/{place_id}")

    async def list_visits(self, **params: Any) -> PaginatedResponse:
        return await self.get_paginated("/api/v1/visits", params=_clean(params))

    async def get_visit(self, visit_id: int) -> dict[str, Any]:
        return await self.get(f"/api/v1/visits/{visit_id}")

    async def possible_places(self, visit_id: int) -> list[dict[str, Any]]:
        return await self.get(f"/api/v1/visits/{visit_id}/possible_places")

    async def create_visit(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post("/api/v1/visits", json={"visit": payload})

    async def update_visit(self, visit_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.patch(f"/api/v1/visits/{visit_id}", json={"visit": payload})

    async def delete_visit(self, visit_id: int) -> None:
        await self.delete(f"/api/v1/visits/{visit_id}")

    async def select_visit_place(self, visit_id: int, place_id: int) -> dict[str, Any]:
        return await self.post(
            f"/api/v1/visits/{visit_id}/select_place",
            json={"place_id": place_id},
        )

    async def merge_visits(self, visit_ids: list[int]) -> dict[str, Any]:
        return await self.post("/api/v1/visits/merge", json={"visit_ids": visit_ids})

    async def bulk_update_visits(self, visit_ids: list[int], status: str) -> dict[str, Any]:
        return await self.post(
            "/api/v1/visits/bulk_update",
            json={"visit_ids": visit_ids, "status": status},
        )

    async def timeline(self, **params: Any) -> dict[str, Any]:
        return await self.get("/api/v1/timeline", params=_clean(params))

    async def points(self, **params: Any) -> PaginatedResponse:
        return await self.get_paginated("/api/v1/points", params=_clean(params))

    async def add_points(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        locations = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [point["longitude"], point["latitude"]],
                },
                "properties": {
                    key: value
                    for key, value in point.items()
                    if key not in {"latitude", "longitude"}
                },
            }
            for point in points
        ]
        return await self.post("/api/v1/points", json={"locations": locations})

    async def map_bounds(self, **params: Any) -> dict[str, Any]:
        return await self.get("/api/v1/maps/hexagons/bounds", params=_clean(params))

    async def map_hexagons(self, **params: Any) -> dict[str, Any]:
        return await self.get("/api/v1/maps/hexagons", params=_clean(params))

    async def map_fog(self, **params: Any) -> dict[str, Any]:
        return await self.get("/api/v1/maps/hexagons/fog", params=_clean(params))

    async def reapply_anomaly_filter(self) -> dict[str, Any]:
        return await self.post("/api/v1/points/reapply_anomaly_filter")

    async def recalculate(self) -> dict[str, Any]:
        return await self.post("/api/v1/recalculations")

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request_params = dict(params or {})
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.auth_mode == "query":
            request_params["api_key"] = self.config.api_key
        else:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        response = await self._client.request(
            method,
            f"{self.config.base_url}{path}",
            params=request_params,
            json=json,
            headers=headers,
        )
        if response.status_code >= 400:
            payload = _safe_json(response)
            raise DawarichClientError(
                response.status_code,
                _error_message(response.status_code, payload),
                payload=payload,
            )
        return response


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _decode_response(response: httpx.Response) -> Any:
    if not response.content:
        return None
    return response.json()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _error_message(status_code: int, payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("error"):
            return f"Dawarich API error {status_code}: {payload['error']}"
        if payload.get("errors"):
            return f"Dawarich API error {status_code}: {payload['errors']}"
        if payload.get("message"):
            return f"Dawarich API error {status_code}: {payload['message']}"
    return f"Dawarich API error {status_code}: {payload}"
