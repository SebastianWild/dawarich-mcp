# Dawarich MCP

> **Disclaimer:** This project is a work in progress and was vibe-coded without
> much of a plan. Treat it as experimental until the API surface and behavior
> have been reviewed more deliberately.

FastMCP server for Dawarich location history.

The server exposes LLM-friendly tools and resources for maps, stats, places, visits, points, and trip workflows. Dawarich currently does not expose `/api/v1/trips`, so trip mutation tools return a clear unsupported-capability response until those routes exist.

## Configuration

Required:

- `DAWARICH_BASE_URL`: Dawarich base URL, for example `http://dawarich.dawarich.svc.cluster.local:3000`
- `DAWARICH_API_KEY`: Dawarich user API key

Optional:

- `DAWARICH_AUTH_MODE`: `bearer` or `query`, default `bearer`
- `DAWARICH_HOST_HEADER`: optional HTTP `Host` header for deployments that call an internal service URL while Dawarich only allows the public app host
- `DAWARICH_FORWARDED_PROTO`: optional `X-Forwarded-Proto` header, for example `https` when Dawarich forces HTTPS behind a proxy
- `DAWARICH_TIMEOUT_SECONDS`: default `30`
- `DAWARICH_MAX_PAGE_SIZE`: default `500`
- `MCP_TRANSPORT`: `stdio` or `http`, default `stdio` outside the container
- `MCP_HOST`: default `127.0.0.1`
- `MCP_PORT`: default `8000`

## Local Development

```bash
uv --cache-dir /tmp/uv-cache-dawarich-mcp run --extra dev pytest
uv --cache-dir /tmp/uv-cache-dawarich-mcp run --extra dev ruff check .
```

Run over stdio:

```bash
DAWARICH_BASE_URL=https://timeline.example.test \
DAWARICH_API_KEY=... \
uv run dawarich-mcp --transport stdio
```

Run over HTTP:

```bash
DAWARICH_BASE_URL=https://timeline.example.test \
DAWARICH_API_KEY=... \
uv run dawarich-mcp --transport http --host 127.0.0.1 --port 8000
```

HTTP MCP endpoint: `http://127.0.0.1:8000/mcp`

Health endpoint: `http://127.0.0.1:8000/health`

## Kubernetes Shape

The intended cluster deployment is internal only:

- Namespace: `dawarich`
- Service: `dawarich-mcp`
- URL: `http://dawarich-mcp.dawarich.svc.cluster.local:8000/mcp`
- No IngressRoute
- Dawarich API URL: `http://dawarich.dawarich.svc.cluster.local:3000`

Store the API key in a Kubernetes Secret. Do not commit it.

`automated-setups` expects the secret at:

```text
namespace: dawarich
name: dawarich-mcp-secret
key: api-key
```

The image build and deployment can be run separately:

```bash
# Build the configured localhost/dawarich-mcp image into Spark's k8s.io containerd namespace.
direnv exec . env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local TMPDIR=/tmp \
  venv/bin/ansible-playbook -i inventory/k8s_cluster/inventory.ini \
  playbooks/cluster/applications.yml --tags dawarich-mcp-build

# Apply the internal-only Deployment and ClusterIP Service.
direnv exec . env ANSIBLE_LOCAL_TEMP=/tmp/ansible-local TMPDIR=/tmp \
  venv/bin/ansible-playbook -i inventory/k8s_cluster/inventory.ini \
  playbooks/cluster/applications.yml --tags dawarich-mcp-deploy
```

The deploy tag refuses to apply the Deployment unless either
`dawarich_mcp_api_key` is set from Ansible Vault or the `dawarich-mcp-secret`
already exists in the `dawarich` namespace.

## Safety

- Bearer auth is preferred so the Dawarich API key is not placed in URLs.
- Delete, merge, bulk update, and recalculation tools default to dry-run.
- Raw point reads are available but described as lower-level tools; prefer timeline, stats, and map context first.
- Trip tools intentionally do not scrape Dawarich HTML forms. They report the missing `/api/v1/trips` API instead.
