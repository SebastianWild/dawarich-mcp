from dawarich_mcp.server import build_mcp


async def test_build_mcp_registers_expected_component_names():
    mcp = build_mcp(client=object())

    names = {tool.name for tool in await mcp.list_tools()}
    resource_uris = {str(resource.uri) for resource in await mcp.list_resources()}
    template_uris = {
        template.uri_template for template in await mcp.list_resource_templates()
    }

    assert "dawarich_get_stats" in names
    assert "dawarich_create_visit" in names
    assert "dawarich_create_trip" in names
    assert "dawarich_select_visit_place" in names
    assert "dawarich_merge_visits" in names
    assert "dawarich_bulk_update_visit_status" in names
    assert "dawarich_update_trip" in names
    assert "dawarich_delete_trip" in names
    assert "dawarich_add_points" in names
    assert "dawarich_recalculate" in names
    assert "dawarich://stats/summary" in resource_uris
    assert "dawarich://profile" in resource_uris
    assert "dawarich://places/{place_id}" in template_uris
    assert "dawarich://visits/{visit_id}" in template_uris
    assert "dawarich://stats/year/{year}" in template_uris


async def test_build_mcp_registers_workflow_prompts():
    mcp = build_mcp(client=object())

    prompt_names = {prompt.name for prompt in await mcp.list_prompts()}

    assert "review_suggested_visits" in prompt_names
    assert "create_trip_from_dates" in prompt_names
    assert "monthly_travel_summary" in prompt_names
