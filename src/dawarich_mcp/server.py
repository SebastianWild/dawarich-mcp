from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from . import __version__
from .client import DawarichClient
from .config import load_config
from .tools import DawarichTools


def build_mcp(client: Any | None = None) -> FastMCP:
    if client is None:
        client = DawarichClient(load_config())
    tools = DawarichTools(client)

    mcp = FastMCP(
        name="dawarich-mcp",
        instructions=(
            "Use Dawarich tools and resources for location history. Prefer stats, timeline, "
            "places, visits, and map context tools before requesting raw points. Destructive "
            "operations default to dry-run where possible."
        ),
        version=__version__,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    @mcp.resource("dawarich://stats/summary", mime_type="application/json")
    async def stats_summary() -> dict[str, Any]:
        return await tools.get_stats()

    @mcp.resource("dawarich://stats/year/{year}", mime_type="application/json")
    async def stats_year(year: int) -> dict[str, Any]:
        return await tools.get_stats(year=year)

    @mcp.resource("dawarich://profile", mime_type="application/json")
    async def profile() -> dict[str, Any]:
        return {
            "health": await client.health(),
            "user": await client.user(),
            "settings": await client.settings(),
            "plan": await client.plan(),
        }

    @mcp.resource("dawarich://places/{place_id}", mime_type="application/json")
    async def place_resource(place_id: int) -> dict[str, Any]:
        return await client.get_place(place_id)

    @mcp.resource("dawarich://visits/{visit_id}", mime_type="application/json")
    async def visit_resource(visit_id: int) -> dict[str, Any]:
        return await client.get_visit(visit_id)

    @mcp.tool
    async def dawarich_get_stats(
        year: int | None = None,
        include_monthly: bool = True,
    ) -> dict[str, Any]:
        """Get aggregate Dawarich travel stats, optionally filtered to one year."""
        return await tools.get_stats(year=year, include_monthly=include_monthly)

    @mcp.tool
    async def dawarich_search_places(
        query: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 1.0,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search saved and nearby Dawarich places."""
        return await tools.search_places(query, latitude, longitude, radius_km, limit)

    @mcp.tool
    async def dawarich_find_visits(
        start_at: str | None = None,
        end_at: str | None = None,
        status: str = "any",
        page: int = 1,
        per_page: int = 100,
    ) -> dict[str, Any]:
        """Find Dawarich visits by time and status."""
        return await tools.find_visits(start_at, end_at, status, page, per_page)

    @mcp.tool
    async def dawarich_get_timeline(
        start_at: str,
        end_at: str,
        distance_unit: str | None = None,
    ) -> dict[str, Any]:
        """Get day-by-day Dawarich timeline context for a date range."""
        return await tools.get_timeline(start_at, end_at, distance_unit)

    @mcp.tool
    async def dawarich_get_map_context(
        start_at: str,
        end_at: str,
        include_hexagons: bool = False,
        include_fog: bool = False,
        max_features: int = 500,
    ) -> dict[str, Any]:
        """Get map bounds and optional capped hexagon/fog context."""
        return await tools.get_map_context(
            start_at,
            end_at,
            include_hexagons,
            include_fog,
            max_features,
        )

    @mcp.tool
    async def dawarich_find_points(
        start_at: str | None = None,
        end_at: str | None = None,
        page: int = 1,
        per_page: int = 100,
        order: str = "desc",
        include_anomalies: bool = False,
        anomalies_only: bool = False,
        slim: bool = True,
    ) -> dict[str, Any]:
        """Find raw Dawarich points. Prefer timeline/map context unless point evidence is needed."""
        return await tools.find_points(
            start_at,
            end_at,
            page,
            per_page,
            order,
            include_anomalies,
            anomalies_only,
            slim,
        )

    @mcp.tool
    async def dawarich_create_place(
        name: str,
        latitude: float,
        longitude: float,
        note: str | None = None,
        tag_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Create a manual Dawarich place."""
        return await tools.create_place(name, latitude, longitude, note, tag_ids, dry_run)

    @mcp.tool
    async def dawarich_update_place(
        place_id: int,
        name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        note: str | None = None,
        tag_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update a Dawarich place after reading its current value."""
        return await tools.update_place(place_id, name, latitude, longitude, note, tag_ids, dry_run)

    @mcp.tool
    async def dawarich_delete_place(place_id: int, dry_run: bool = True) -> dict[str, Any]:
        """Delete a Dawarich place. Defaults to dry-run."""
        return await tools.delete_place(place_id, dry_run)

    @mcp.tool
    async def dawarich_create_visit(
        name: str,
        latitude: float,
        longitude: float,
        started_at: str,
        ended_at: str,
        status: str = "confirmed",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Create a Dawarich visit and matching/manual place if needed."""
        return await tools.create_visit(
            name,
            latitude,
            longitude,
            started_at,
            ended_at,
            status,
            dry_run,
        )

    @mcp.tool
    async def dawarich_update_visit(
        visit_id: int,
        name: str | None = None,
        place_id: int | None = None,
        area_id: int | None = None,
        status: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update a Dawarich visit after reading its current value."""
        return await tools.update_visit(
            visit_id,
            name,
            place_id,
            area_id,
            status,
            started_at,
            ended_at,
            dry_run,
        )

    @mcp.tool
    async def dawarich_select_visit_place(
        visit_id: int,
        place_id: int,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Select one of Dawarich's possible places for a visit."""
        return await tools.select_visit_place(visit_id, place_id, dry_run)

    @mcp.tool
    async def dawarich_merge_visits(visit_ids: list[int], dry_run: bool = True) -> dict[str, Any]:
        """Merge Dawarich visits. Defaults to dry-run because merge is destructive."""
        return await tools.merge_visits(visit_ids, dry_run)

    @mcp.tool
    async def dawarich_bulk_update_visit_status(
        visit_ids: list[int],
        status: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Bulk update Dawarich visit status. Defaults to dry-run."""
        return await tools.bulk_update_visit_status(visit_ids, status, dry_run)

    @mcp.tool
    async def dawarich_create_trip(
        name: str,
        started_at: str,
        ended_at: str,
        description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Create a Dawarich trip when /api/v1/trips exists; currently reports that API gap."""
        return await tools.create_trip(name, started_at, ended_at, description, dry_run)

    @mcp.tool
    async def dawarich_update_trip(
        trip_id: int,
        name: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        description: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update a Dawarich trip when /api/v1/trips exists; currently reports that API gap."""
        return await tools.update_trip(
            trip_id=trip_id,
            name=name,
            started_at=started_at,
            ended_at=ended_at,
            description=description,
            dry_run=dry_run,
        )

    @mcp.tool
    async def dawarich_delete_trip(trip_id: int, dry_run: bool = True) -> dict[str, Any]:
        """Delete a Dawarich trip when /api/v1/trips exists; currently reports that API gap."""
        return await tools.delete_trip(trip_id, dry_run)

    @mcp.tool
    async def dawarich_add_points(
        points: list[dict[str, Any]],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add raw Dawarich points. Prefer visit/timeline tools unless raw samples are needed."""
        return await tools.add_points(points, dry_run)

    @mcp.tool
    async def dawarich_recalculate(kind: str, dry_run: bool = True) -> dict[str, Any]:
        """Queue supported Dawarich recalculations. Defaults to dry-run."""
        return await tools.recalculate(kind, dry_run)

    @mcp.prompt
    def review_suggested_visits(start_at: str, end_at: str) -> str:
        return (
            "Review suggested Dawarich visits between "
            f"{start_at} and {end_at}. First call dawarich_find_visits with "
            "status='suggested', then inspect possible places before proposing updates. "
            "Use dry-run for bulk status changes until the user confirms."
        )

    @mcp.prompt
    def create_trip_from_dates(name: str, started_at: str, ended_at: str) -> str:
        return (
            f"Create a Dawarich trip named {name!r} from {started_at} to {ended_at}. "
            "First call dawarich_get_map_context and dawarich_get_timeline for context. "
            "Then call dawarich_create_trip; if it reports that /api/v1/trips is unsupported, "
            "explain that Dawarich needs trip API routes before MCP can mutate trips."
        )

    @mcp.prompt
    def monthly_travel_summary(year: int, month: int) -> str:
        return (
            f"Summarize Dawarich travel for {year:04d}-{month:02d}. Use "
            "dawarich_get_stats, dawarich_get_map_context, and dawarich_get_timeline. "
            "Prefer compact totals and notable places/visits over raw point dumps."
        )

    return mcp
