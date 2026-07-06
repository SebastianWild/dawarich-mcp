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
        host_header=None,
        forwarded_proto=None,
    )


def test_load_config_reads_forwarded_request_headers(monkeypatch):
    monkeypatch.setenv("DAWARICH_BASE_URL", "http://dawarich.dawarich.svc.cluster.local:3000")
    monkeypatch.setenv("DAWARICH_API_KEY", "secret")
    monkeypatch.setenv("DAWARICH_HOST_HEADER", "timeline.example.test")
    monkeypatch.setenv("DAWARICH_FORWARDED_PROTO", "https")

    config = load_config()

    assert config.host_header == "timeline.example.test"
    assert config.forwarded_proto == "https"


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
