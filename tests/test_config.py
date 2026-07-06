from dawarich_mcp.config import DawarichMcpConfig, load_config


def test_load_config_normalizes_base_url_and_defaults(monkeypatch):
    monkeypatch.setenv("DAWARICH_BASE_URL", "https://timeline.example.test/")
    monkeypatch.setenv("DAWARICH_API_KEY", "secret")

    config = load_config()

    assert config == DawarichMcpConfig(
        base_url="https://timeline.example.test",
        api_key="secret",
        auth_mode="bearer",
        timeout_seconds=30.0,
        max_page_size=500,
        audit_log=None,
    )


def test_load_config_rejects_missing_required_values(monkeypatch):
    monkeypatch.delenv("DAWARICH_BASE_URL", raising=False)
    monkeypatch.delenv("DAWARICH_API_KEY", raising=False)

    try:
        load_config()
    except ValueError as exc:
        assert "DAWARICH_BASE_URL" in str(exc)
        assert "DAWARICH_API_KEY" in str(exc)
    else:
        raise AssertionError("expected missing config to fail")
