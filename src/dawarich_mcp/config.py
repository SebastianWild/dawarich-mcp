from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DawarichMcpConfig:
    base_url: str
    api_key: str
    auth_mode: str = "bearer"
    timeout_seconds: float = 30.0
    max_page_size: int = 500
    audit_log: str | None = None
    host_header: str | None = None
    forwarded_proto: str | None = None


def load_config() -> DawarichMcpConfig:
    missing = [
        name
        for name in ("DAWARICH_BASE_URL", "DAWARICH_API_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    auth_mode = os.environ.get("DAWARICH_AUTH_MODE", "bearer").lower()
    if auth_mode not in {"bearer", "query"}:
        raise ValueError("DAWARICH_AUTH_MODE must be 'bearer' or 'query'")

    return DawarichMcpConfig(
        base_url=os.environ["DAWARICH_BASE_URL"].rstrip("/"),
        api_key=os.environ["DAWARICH_API_KEY"],
        auth_mode=auth_mode,
        timeout_seconds=float(os.environ.get("DAWARICH_TIMEOUT_SECONDS", "30")),
        max_page_size=int(os.environ.get("DAWARICH_MAX_PAGE_SIZE", "500")),
        audit_log=os.environ.get("DAWARICH_AUDIT_LOG") or None,
        host_header=os.environ.get("DAWARICH_HOST_HEADER") or None,
        forwarded_proto=os.environ.get("DAWARICH_FORWARDED_PROTO") or None,
    )
