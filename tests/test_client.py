import json

import httpx
import pytest

from dawarich_mcp.client import DawarichClient, DawarichClientError
from dawarich_mcp.config import DawarichMcpConfig


def make_client(handler, auth_mode="bearer", host_header=None, forwarded_proto=None):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    config = DawarichMcpConfig(
        base_url="https://dawarich.example.test",
        api_key="secret",
        auth_mode=auth_mode,
        timeout_seconds=30.0,
        max_page_size=500,
        audit_log=None,
        host_header=host_header,
        forwarded_proto=forwarded_proto,
    )
    return DawarichClient(config, http_client=http)


@pytest.mark.asyncio
async def test_client_uses_bearer_auth_and_parses_pagination_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json=[{"id": 1}],
            headers={"X-Current-Page": "2", "X-Total-Pages": "4", "X-Total-Count": "31"},
        )

    client = make_client(handler)
    page = await client.get_paginated("/api/v1/places", params={"page": 2})

    assert seen["authorization"] == "Bearer secret"
    assert seen["url"] == "https://dawarich.example.test/api/v1/places?page=2"
    assert page.data == [{"id": 1}]
    assert page.pagination.current_page == 2
    assert page.pagination.total_pages == 4
    assert page.pagination.total_count == 31


@pytest.mark.asyncio
async def test_client_can_use_query_auth_for_compatibility():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, auth_mode="query")
    data = await client.get("/api/v1/stats")

    assert data == {"ok": True}
    assert seen["url"] == "https://dawarich.example.test/api/v1/stats?api_key=secret"


@pytest.mark.asyncio
async def test_client_sends_configured_forwarded_request_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.headers.get("host")
        seen["forwarded_proto"] = request.headers.get("x-forwarded-proto")
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    client = make_client(
        handler,
        host_header="timeline.example.test",
        forwarded_proto="https",
    )
    data = await client.get("/api/v1/stats")

    assert data == {"ok": True}
    assert seen == {
        "host": "timeline.example.test",
        "forwarded_proto": "https",
        "authorization": "Bearer secret",
    }


@pytest.mark.asyncio
async def test_client_maps_dawarich_error_bodies():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "Invalid place"})

    client = make_client(handler)

    with pytest.raises(DawarichClientError) as exc_info:
        await client.patch("/api/v1/visits/123", json={"visit": {"place_id": 99}})

    assert exc_info.value.status_code == 422
    assert "Invalid place" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stats_endpoint_handles_json_string_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=json.dumps({"totalDistanceKm": 42, "yearlyStats": []}),
        )

    client = make_client(handler)
    stats = await client.stats()

    assert stats["totalDistanceKm"] == 42
    assert stats["yearlyStats"] == []
