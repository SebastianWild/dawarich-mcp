from __future__ import annotations

from dawarich_mcp import __main__


class RecordingMcp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_http_transport_allows_kubernetes_service_hosts_by_default(monkeypatch):
    mcp = RecordingMcp()
    monkeypatch.setattr(__main__, "build_mcp", lambda: mcp)
    monkeypatch.setattr(
        "sys.argv",
        ["dawarich-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"],
    )
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)

    __main__.main()

    assert mcp.calls == [
        {
            "transport": "http",
            "host": "0.0.0.0",
            "port": 8000,
            "allowed_hosts": [
                "127.0.0.1",
                "localhost",
                "dawarich-mcp",
                "dawarich-mcp.dawarich",
                "dawarich-mcp.dawarich.svc",
                "dawarich-mcp.dawarich.svc.cluster.local",
            ],
        }
    ]


def test_http_transport_allows_hosts_from_env(monkeypatch):
    mcp = RecordingMcp()
    monkeypatch.setattr(__main__, "build_mcp", lambda: mcp)
    monkeypatch.setattr("sys.argv", ["dawarich-mcp", "--transport", "http"])
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "example.internal, other.internal ,,")

    __main__.main()

    assert mcp.calls[0]["allowed_hosts"] == ["example.internal", "other.internal"]
