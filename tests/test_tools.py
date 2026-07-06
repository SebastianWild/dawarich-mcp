import pytest

from dawarich_mcp.tools import DawarichTools


class RecordingClient:
    def __init__(self):
        self.calls = []

    async def get_place(self, place_id):
        self.calls.append(("get_place", place_id))
        return {"id": place_id, "name": "Cafe", "visits_count": 2}

    async def delete_place(self, place_id):
        self.calls.append(("delete_place", place_id))
        return None

    async def create_visit(self, payload):
        self.calls.append(("create_visit", payload))
        return {"id": 7, "name": payload["name"], "status": payload["status"]}


@pytest.mark.asyncio
async def test_delete_place_defaults_to_dry_run_and_does_not_mutate():
    client = RecordingClient()
    tools = DawarichTools(client)

    result = await tools.delete_place(place_id=42)

    assert result["dry_run"] is True
    assert result["would_delete"]["id"] == 42
    assert client.calls == [("get_place", 42)]


@pytest.mark.asyncio
async def test_create_visit_validates_time_order_before_mutating():
    client = RecordingClient()
    tools = DawarichTools(client)

    with pytest.raises(ValueError, match="ended_at must be after started_at"):
        await tools.create_visit(
            name="Bad Visit",
            latitude=45.0,
            longitude=-122.0,
            started_at="2026-01-02T12:00:00Z",
            ended_at="2026-01-02T11:00:00Z",
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_trip_tools_report_api_gap():
    tools = DawarichTools(RecordingClient())

    result = await tools.create_trip(
        name="Oregon Coast",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-03T00:00:00Z",
    )

    assert result["supported"] is False
    assert "/api/v1/trips" in result["message"]
