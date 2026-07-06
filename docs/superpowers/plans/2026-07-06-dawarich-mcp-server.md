# Dawarich MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dawarich MCP server that exposes Maps, Trips, Places/Visits, and Stats as LLM-friendly resources and tools with read and write workflows, instead of mechanically mirroring Dawarich OpenAPI operations.

**Architecture:** Create a TypeScript MCP server with a small Dawarich HTTP client, typed domain adapters, MCP resources for stable contextual data, and MCP tools for bounded operations. The server should normalize Dawarich responses into compact, schema-validated objects with useful summaries and resource links, while keeping raw endpoint details inside adapters.

**Tech Stack:** Node.js, TypeScript, official MCP TypeScript SDK, Zod schemas, Vitest, undici/fetch, dotenv-compatible env loading, MCP Inspector for manual checks.

---

## Evidence Gathered

### MCP design constraints

Current MCP server features make a useful split:

- Tools are model-controlled operations with input schemas, optional output schemas, structured results, and explicit error results. MCP guidance calls out input validation, access controls, rate limiting, output sanitization, timeouts, and audit logging for tools.
- Resources are application-driven context objects identified by URIs, suitable for stable data such as summaries, schema notes, map snapshots, and entity details. Resource templates are the right shape for parameterized Dawarich context.
- Prompts can encode recurring workflows like "plan a trip", "review unconfirmed visits", or "summarize the month" without forcing the model to rediscover the correct tool order each time.
- The TypeScript SDK repository currently shows a v2 beta line and says v1.x remains the production-supported release until the 2026-07-28 spec stabilizes. For this project, start with the production-supported SDK line unless implementation begins after that release and v2 is stable.

### Dawarich source evidence

Local Dawarich source inspected at `/home/sebastian/projects/temp/dawarich`.

Relevant routing:

- `config/routes.rb` mounts Rswag API and UI at `/api-docs`.
- `/api/v1/points`, `/api/v1/places`, `/api/v1/visits`, `/api/v1/stats`, `/api/v1/timeline`, `/api/v1/maps/hexagons`, `/api/v1/tracks`, and related subroutes are present.
- Browser-side Trips CRUD exists at `/trips` through `TripsController`.
- There is no `/api/v1/trips` route in the current API routes or generated Swagger file. The generated Swagger paths include maps, places, points, stats, timeline, tracks, visits, but not trips.

Generated Swagger exists at `/home/sebastian/projects/temp/dawarich/swagger/v1/swagger.yaml`, but the MCP server should treat it as evidence for parameter names and edge cases, not as the MCP surface.

Important controllers and models:

- `app/controllers/api_controller.rb`: API key auth accepts query `api_key` or `Authorization: Bearer <token>`. Self-hosted bypasses cloud Pro/write restrictions. Non-self-hosted write APIs can require Pro.
- `app/controllers/api/v1/points_controller.rb`: list points by time, bbox, anomalies flags, pagination, order; create batch GeoJSON points; update/delete point coordinates; bulk delete; reapply anomaly filter.
- `app/controllers/api/v1/places_controller.rb`: list, show, create, update, destroy places; filters `all`, `manual`, `confirmed`, `tagged`; tag filtering; `nearby`; `search`.
- `app/controllers/api/v1/visits_controller.rb`: list by time or map bbox; show, create, update, destroy; possible places; select place route exists; merge; bulk status update.
- `app/controllers/api/v1/stats_controller.rb`: returns global and yearly aggregate stats through `StatsSerializer`.
- `app/controllers/api/v1/maps/hexagons_controller.rb`: hexagon feature collection, bounds, fog H3 indexes.
- `app/controllers/api/v1/timeline_controller.rb`: 31-day maximum timeline range returning day-by-day visits, tracks, and photos.
- `app/controllers/trips_controller.rb`: browser CRUD for trips; trips have name, started_at, ended_at, description; Trip model schedules calculation jobs after create/update.
- `app/models/trip.rb`: trip points derive from non-anomaly user points between trip start and end. Background jobs compute path, distance, and countries.
- `app/models/place.rb`: manual/photon places with lonlat, tags, visits, and suggested visits.
- `app/models/visit.rb`: statuses are `suggested`, `confirmed`, `declined`; validates name, start/end, duration, status; can link to place or area.

Deployment evidence from `/home/sebastian/projects/automated-setups`:

- `manifests/dawarich.yaml` routes `Host(timeline.<domain>) && PathPrefix(/api/v1)` directly to Dawarich without forward-auth. Dawarich native API auth remains required.
- Other browser routes are behind Traefik forward-auth, so an MCP server should not rely on scraping browser pages for normal operation.
- `charts/dawarich/values.yaml` currently pins image tag `1.9.1`, OIDC is enabled, email/password login is disabled, app protocol is HTTPS, timezone is `America/Los_Angeles`, distance unit is `km`, and Photon is in-cluster at `photon:2322`.
- No Dawarich user API key was found in repo config. Do not add a secret to the repo. Runtime config should read `DAWARICH_BASE_URL` and `DAWARICH_API_KEY`.

## Product Boundary

The MCP server should answer agent tasks like:

- "What places did I visit near this coordinate last month?"
- "Show my map bounds and a compact movement summary for July."
- "Create a visit for this cafe from 10:00 to 12:00 and mark it confirmed."
- "Find unconfirmed suggested visits in Seattle and confirm the ones at known places."
- "Create a trip named Oregon Coast from these dates."
- "Summarize yearly travel stats and link to supporting monthly resources."

It should not expose every Dawarich endpoint as a top-level tool. Raw endpoint wrappers create weak tool names, large schemas, inconsistent outputs, and too many choices for an LLM. Keep raw HTTP operations in adapters and expose a smaller domain vocabulary.

## MCP Surface

### Resource URI scheme

Use a custom URI scheme so resources are stable and self-describing:

- `dawarich://profile`
- `dawarich://stats/summary`
- `dawarich://stats/year/{year}`
- `dawarich://stats/month/{year}/{month}`
- `dawarich://map/bounds?start={iso}&end={iso}`
- `dawarich://map/hexagons?start={iso}&end={iso}`
- `dawarich://map/fog?start={iso}&end={iso}`
- `dawarich://timeline?start={iso}&end={iso}`
- `dawarich://places?filter={filter}&tag_ids={ids}&page={page}`
- `dawarich://places/{place_id}`
- `dawarich://visits?start={iso}&end={iso}&status={status}&page={page}`
- `dawarich://visits/{visit_id}`
- `dawarich://trips`
- `dawarich://trips/{trip_id}`
- `dawarich://tracks/{track_id}`

Resource outputs should be compact JSON plus a short text summary. Every resource should include:

- `generated_at`
- `source_endpoints`
- `filters`
- `truncated` boolean
- `next_page` or `next_resource_uri` when pagination applies
- `related_resources` for drill-down

### Resources

1. `profile`
   - Purpose: connection and account context.
   - Dawarich inputs: `/api/v1/health`, `/api/v1/users/me`, `/api/v1/settings`, `/api/v1/plan`.
   - LLM value: knows timezone, distance unit, available plan/write limits, and current server version.

2. `stats/summary`
   - Purpose: high-level travel history.
   - Dawarich inputs: `/api/v1/stats`.
   - LLM value: compact totals and yearly table, not raw serializer quirks.

3. `stats/year/{year}` and `stats/month/{year}/{month}`
   - Purpose: scoped stats for planning and review.
   - Dawarich inputs: `/api/v1/stats`, `/api/v1/timeline`, `/api/v1/maps/hexagons/bounds`.
   - LLM value: pre-aggregated summary with links to map and timeline resources.

4. `map/bounds`
   - Purpose: geographic extent for a period.
   - Dawarich inputs: `/api/v1/maps/hexagons/bounds`.
   - LLM value: small bbox object useful before calling point-heavy tools.

5. `map/hexagons`
   - Purpose: visited H3 or GeoJSON area context.
   - Dawarich inputs: `/api/v1/maps/hexagons`.
   - LLM value: summarizes coverage and links to full feature collection only when requested.

6. `map/fog`
   - Purpose: fog-of-war cell ids for visited locations.
   - Dawarich inputs: `/api/v1/maps/hexagons/fog`.
   - LLM value: count and cells, capped by default to prevent huge context.

7. `timeline`
   - Purpose: day-by-day movement context for up to 31 days.
   - Dawarich inputs: `/api/v1/timeline`.
   - LLM value: normalized days with visits, tracks, photos counts, distances, and related track/visit links.

8. `places` and `places/{id}`
   - Purpose: saved/suggested place context.
   - Dawarich inputs: `/api/v1/places`, `/api/v1/places/{id}`.
   - LLM value: visible place names, coordinates, tags, visit counts, source, notes, and links to matching visits.

9. `visits` and `visits/{id}`
   - Purpose: visit review and editing context.
   - Dawarich inputs: `/api/v1/visits`, `/api/v1/visits/{id}`, `/api/v1/visits/{id}/possible_places`.
   - LLM value: status, confidence, place/area identity, duration, and update affordances.

10. `trips` and `trips/{id}`
    - Purpose: trip planning and review.
    - Dawarich inputs: new `/api/v1/trips` endpoints should be added upstream or contributed before making this a first-class resource. Until then, expose a disabled capability with a clear error, not an HTML scraper.
    - LLM value: trip periods, distance/path/countries once Dawarich API support exists.

### Tools

Tool names should be domain verbs. All mutating tools should support `dry_run`, return `structuredContent`, and include related resource links.

#### Read/search tools

1. `dawarich_search_places`
   - Use for named or coordinate-adjacent place discovery.
   - Inputs:
     - `query`: string, optional, minimum 2 chars when present
     - `latitude`: number, optional
     - `longitude`: number, optional
     - `radius_km`: number, default 1.0, max 5.0
     - `limit`: integer, default 10, max 50
     - `include_saved`: boolean, default true
     - `include_photon`: boolean, default true
   - Adapter calls:
     - `/api/v1/places/search` when coordinate search is available.
     - `/api/v1/places` for saved place filtering.
   - Output: ranked places with `id`, `name`, `latitude`, `longitude`, `source`, `distance_km`, `tags`, `visits_count`, and `resource_uri`.

2. `dawarich_find_visits`
   - Use for time, status, and bbox visit lookup.
   - Inputs:
     - `start_at`, `end_at`: ISO datetime
     - `status`: enum `suggested`, `confirmed`, `declined`, `any`, default `any`
     - `bbox`: optional `{sw_lat, sw_lng, ne_lat, ne_lng}`
     - `page`, `per_page`
   - Adapter calls: `/api/v1/visits`.
   - Output: visit summaries with pagination and resource links.

3. `dawarich_get_timeline`
   - Use for a human-scale movement summary.
   - Inputs:
     - `start_at`, `end_at`: ISO datetime, max 31 days
     - `distance_unit`: enum `km`, `mi`, optional
   - Adapter calls: `/api/v1/timeline`.
   - Output: days array plus aggregate count/distance summaries and links to visit/track resources.

4. `dawarich_get_map_context`
   - Use before map-related reasoning.
   - Inputs:
     - `start_at`, `end_at`: ISO datetime
     - `include_hexagons`: boolean, default false
     - `include_fog`: boolean, default false
     - `max_features`: integer, default 500
   - Adapter calls: `/api/v1/maps/hexagons/bounds`, optionally `/api/v1/maps/hexagons`, `/api/v1/maps/hexagons/fog`.
   - Output: bbox, point count, hexagon metadata, capped features/cell ids, resource links for full data.

5. `dawarich_get_stats`
   - Use for aggregate stats.
   - Inputs:
     - `year`: integer optional
     - `include_monthly`: boolean default true
   - Adapter calls: `/api/v1/stats`.
   - Output: totals and filtered yearly/monthly stats.

6. `dawarich_find_points`
   - Use only when point-level evidence is necessary.
   - Inputs:
     - `start_at`, `end_at`: ISO datetime
     - `bbox`: optional
     - `include_anomalies`: boolean default false
     - `anomalies_only`: boolean default false
     - `slim`: boolean default true
     - `page`, `per_page`, `order`
   - Adapter calls: `/api/v1/points`.
   - Output: capped point list plus pagination headers.
   - Guardrail: default `per_page` should be 100, max 1000, and tool description should recommend timeline/map tools first.

#### Write tools

1. `dawarich_create_place`
   - Use to save a manual place.
   - Inputs:
     - `name`: string
     - `latitude`: number
     - `longitude`: number
     - `note`: string optional
     - `tag_ids`: integer array optional
     - `dry_run`: boolean default false
   - Adapter calls: `POST /api/v1/places`.
   - Output: created place plus resource URI, or dry-run validation result.

2. `dawarich_update_place`
   - Use to rename, move, annotate, or retag a place.
   - Inputs:
     - `place_id`: integer
     - `name`, `latitude`, `longitude`, `note`, `tag_ids`: optional update fields
     - `dry_run`: boolean default false
   - Adapter calls: `GET /api/v1/places/{id}` then `PATCH /api/v1/places/{id}`.
   - Output: before/after summary.

3. `dawarich_delete_place`
   - Use to remove a saved place.
   - Inputs:
     - `place_id`: integer
     - `dry_run`: boolean default true
   - Adapter calls: `GET /api/v1/places/{id}` then `DELETE /api/v1/places/{id}`.
   - Output: deleted place summary or dry-run impact. Default dry-run true because deleting a place nullifies visit associations in Dawarich.

4. `dawarich_create_visit`
   - Use to add a confirmed or suggested visit.
   - Inputs:
     - `name`: string
     - `latitude`: number
     - `longitude`: number
     - `started_at`: ISO datetime
     - `ended_at`: ISO datetime
     - `status`: enum `suggested`, `confirmed`, `declined`, default `confirmed`
     - `dry_run`: boolean default false
   - Adapter calls: `POST /api/v1/visits`.
   - Output: created visit, inferred/created place, resource links.
   - Validation: `ended_at` must be after `started_at`; coordinates must be valid; duration should be shown in minutes.

5. `dawarich_update_visit`
   - Use to rename, change status, link to a place/area, or adjust times.
   - Inputs:
     - `visit_id`: integer
     - `name`, `place_id`, `area_id`, `status`, `started_at`, `ended_at`: optional fields
     - `dry_run`: boolean default false
   - Adapter calls: `GET /api/v1/visits/{id}` then `PATCH /api/v1/visits/{id}`.
   - Output: before/after summary.

6. `dawarich_select_visit_place`
   - Use when Dawarich suggested possible places and the agent/user picks one.
   - Inputs:
     - `visit_id`: integer
     - `place_id`: integer
     - `dry_run`: boolean default false
   - Adapter calls: `GET /api/v1/visits/{id}/possible_places`; then `POST /api/v1/visits/{id}/select_place`.
   - Output: selected place and updated visit. This route exists in Rails routes but must be verified against controller behavior during implementation.

7. `dawarich_merge_visits`
   - Use to merge adjacent visits.
   - Inputs:
     - `visit_ids`: integer array, minimum 2
     - `dry_run`: boolean default true
   - Adapter calls: `GET /api/v1/visits/{id}` for each id; then `POST /api/v1/visits/merge`.
   - Output: dry-run merged interval or created merged visit.
   - Default dry-run true because merge is destructive.

8. `dawarich_bulk_update_visit_status`
   - Use for review workflows like confirming suggested visits.
   - Inputs:
     - `visit_ids`: integer array
     - `status`: enum `suggested`, `confirmed`, `declined`
     - `dry_run`: boolean default true
   - Adapter calls: `POST /api/v1/visits/bulk_update`.
   - Output: count and changed statuses.
   - Default dry-run true when more than one visit is affected.

9. `dawarich_create_trip`
   - Use to create a named trip from a date interval.
   - Inputs:
     - `name`: string
     - `started_at`: ISO datetime
     - `ended_at`: ISO datetime
     - `description`: string optional
     - `dry_run`: boolean default false
   - Adapter calls:
     - Preferred: new Dawarich `POST /api/v1/trips` endpoint.
     - Not acceptable as default: CSRF/browser HTML form scraping.
   - Output: created trip, expected background recalculation state, resource URI.
   - Current status: blocked on adding Dawarich API trip endpoints or accepting an explicit browser-session fallback.

10. `dawarich_update_trip`
    - Use to edit trip name, dates, or description.
    - Inputs:
      - `trip_id`: integer
      - `name`, `started_at`, `ended_at`, `description`: optional fields
      - `dry_run`: boolean default false
    - Adapter calls: preferred new `PATCH /api/v1/trips/{id}` endpoint.
    - Output: before/after summary and recalculation notice.

11. `dawarich_delete_trip`
    - Use to delete a trip.
    - Inputs:
      - `trip_id`: integer
      - `dry_run`: boolean default true
    - Adapter calls: preferred new `DELETE /api/v1/trips/{id}` endpoint.
    - Output: deleted trip summary.

12. `dawarich_add_points`
    - Use only when an agent needs to insert raw location samples.
    - Inputs:
      - `points`: array of `{latitude, longitude, timestamp, accuracy?, altitude?, speed?, device_id?, track_id?}`
      - `dry_run`: boolean default false
    - Adapter calls: `POST /api/v1/points`.
    - Output: inserted point count and IDs where Dawarich returns them.

13. `dawarich_recalculate`
    - Use to queue background recalculations.
    - Inputs:
      - `kind`: enum `stats`, `transportation`, `anomaly_filter`, `trip`
      - `year`, `month`, `trip_id`: optional depending on kind
      - `dry_run`: boolean default true
    - Adapter calls:
      - `/api/v1/recalculations` for global supported recalculations.
      - `/api/v1/points/reapply_anomaly_filter` for anomaly filter.
      - Preferred new `/api/v1/trips/{id}/recalculate` for trips.
   - Output: accepted job summary.

### Prompts

1. `review_suggested_visits`
   - Arguments: `start_at`, `end_at`, optional `city_or_bbox`.
   - Flow: get visits, get possible places for uncertain visits, present candidate updates, then use bulk or single update tools.

2. `create_trip_from_dates`
   - Arguments: `name`, `started_at`, `ended_at`, optional `description`.
   - Flow: get map bounds, stats/timeline context, create trip if API support is available.

3. `monthly_travel_summary`
   - Arguments: `year`, `month`.
   - Flow: stats summary, map bounds, timeline chunks, notable visits/places.

4. `clean_up_place_history`
   - Arguments: `place_query` or coordinate.
   - Flow: search places, list visits, propose rename/tag/link changes.

## Repository File Structure

Create these files in `/home/sebastian/projects/dawarich-mcp`:

- `package.json`: package metadata and scripts.
- `tsconfig.json`: strict TypeScript configuration.
- `vitest.config.ts`: unit test configuration.
- `.env.example`: documented runtime configuration without secrets.
- `README.md`: setup, capabilities, MCP client configuration, and safety notes.
- `src/index.ts`: stdio MCP server entrypoint.
- `src/server.ts`: MCP server construction and registration.
- `src/config.ts`: env parsing and validation.
- `src/dawarich/http.ts`: fetch wrapper, auth header/query handling, timeouts, error mapping.
- `src/dawarich/types.ts`: normalized Dawarich domain types.
- `src/dawarich/points.ts`: point API adapter.
- `src/dawarich/places.ts`: place API adapter.
- `src/dawarich/visits.ts`: visit API adapter.
- `src/dawarich/maps.ts`: maps API adapter.
- `src/dawarich/stats.ts`: stats API adapter.
- `src/dawarich/timeline.ts`: timeline API adapter.
- `src/dawarich/trips.ts`: trip adapter with current unsupported API behavior plus future interface.
- `src/mcp/schemas.ts`: Zod input and output schemas.
- `src/mcp/result.ts`: structuredContent/text compatibility helper.
- `src/mcp/resources.ts`: resource template registrations and resource readers.
- `src/mcp/tools/read.ts`: read/search tool registrations.
- `src/mcp/tools/write.ts`: write tool registrations.
- `src/mcp/prompts.ts`: workflow prompt registrations.
- `src/safety/dry-run.ts`: dry-run helpers and destructive-operation defaults.
- `src/safety/audit.ts`: local audit event writer.
- `src/utils/time.ts`: ISO/timezone/range helpers.
- `src/utils/pagination.ts`: pagination header parsing and cursors.
- `tests/fixtures/*.json`: representative Dawarich API responses copied from test-safe fixtures, not personal data.
- `tests/http.test.ts`: HTTP auth, timeout, and error tests.
- `tests/tools.*.test.ts`: tool schema and adapter behavior tests.
- `tests/resources.test.ts`: resource URI parsing and output shape tests.
- `tests/prompts.test.ts`: prompt registration tests.
- `tests/integration/live.test.ts`: optional live tests gated by `DAWARICH_LIVE_TESTS=1`.

## Implementation Tasks

### Task 1: Scaffold the TypeScript MCP project

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vitest.config.ts`
- Create: `.env.example`
- Create: `src/index.ts`
- Create: `src/server.ts`
- Test: `tests/server.test.ts`

- [ ] Create package scripts:
  - `build`: `tsc -p tsconfig.json`
  - `test`: `vitest run`
  - `test:watch`: `vitest`
  - `dev`: `tsx src/index.ts`
  - `inspect`: run MCP Inspector against the stdio entrypoint.
- [ ] Install the production-supported MCP TypeScript SDK line, Zod, Vitest, TypeScript, tsx, and undici if runtime fetch support needs it.
- [ ] Register a server named `dawarich-mcp` with version `0.1.0`.
- [ ] Write `tests/server.test.ts` asserting the server can be constructed and exposes tools, resources, and prompts capabilities.
- [ ] Run `npm test`.
- [ ] Commit with message `chore: scaffold dawarich mcp server`.

### Task 2: Add configuration and Dawarich HTTP client

**Files:**
- Create: `src/config.ts`
- Create: `src/dawarich/http.ts`
- Create: `src/dawarich/types.ts`
- Test: `tests/http.test.ts`

- [ ] Define config:
  - `DAWARICH_BASE_URL`, required, no trailing slash after normalization.
  - `DAWARICH_API_KEY`, required.
  - `DAWARICH_AUTH_MODE`, enum `bearer` or `query`, default `bearer`.
  - `DAWARICH_TIMEOUT_MS`, default `30000`.
  - `DAWARICH_MAX_PAGE_SIZE`, default `500`.
  - `DAWARICH_AUDIT_LOG`, optional path.
  - `DAWARICH_LIVE_TESTS`, optional boolean.
- [ ] Add HTTP auth:
  - Bearer mode sends `Authorization: Bearer <api_key>`.
  - Query mode appends `api_key=<api_key>`.
- [ ] Add typed error mapping:
  - 400 validation error
  - 401 auth error
  - 402 payment/plan error
  - 403 write restriction error
  - 404 not found
  - 409 conflict
  - 422 Dawarich validation error
  - 5xx upstream error
- [ ] Preserve pagination headers:
  - `X-Current-Page`
  - `X-Total-Pages`
  - `X-Total-Count`
  - rate-limit headers when present.
- [ ] Test URL normalization, bearer/query auth, JSON parse errors, Dawarich error bodies, and timeout aborts.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich http client`.

### Task 3: Implement read adapters

**Files:**
- Create: `src/dawarich/points.ts`
- Create: `src/dawarich/places.ts`
- Create: `src/dawarich/visits.ts`
- Create: `src/dawarich/maps.ts`
- Create: `src/dawarich/stats.ts`
- Create: `src/dawarich/timeline.ts`
- Create: `src/dawarich/trips.ts`
- Test: `tests/adapters.test.ts`

- [ ] Implement point list adapter for `/api/v1/points` with time, bbox, anomalies, slim, pagination, and order parameters.
- [ ] Implement place adapters for list/show/search/nearby using `/api/v1/places`, `/api/v1/places/{id}`, `/api/v1/places/search`, and `/api/v1/places/nearby`.
- [ ] Implement visit adapters for list/show/possible_places using `/api/v1/visits`, `/api/v1/visits/{id}`, and `/api/v1/visits/{id}/possible_places`.
- [ ] Implement map adapters for bounds, hexagons, and fog using `/api/v1/maps/hexagons/bounds`, `/api/v1/maps/hexagons`, and `/api/v1/maps/hexagons/fog`.
- [ ] Implement stats adapter for `/api/v1/stats`, including handling Dawarich's current serializer behavior if the response body is a JSON string.
- [ ] Implement timeline adapter for `/api/v1/timeline`, enforcing the 31-day maximum before making the request.
- [ ] Implement trips adapter with an explicit `UnsupportedDawarichCapabilityError` for create/update/delete/list until `/api/v1/trips` exists.
- [ ] Test every adapter with mocked HTTP requests and normalized output.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich read adapters`.

### Task 4: Implement write adapters and dry-run support

**Files:**
- Modify: `src/dawarich/points.ts`
- Modify: `src/dawarich/places.ts`
- Modify: `src/dawarich/visits.ts`
- Modify: `src/dawarich/trips.ts`
- Create: `src/safety/dry-run.ts`
- Create: `src/safety/audit.ts`
- Test: `tests/write-adapters.test.ts`

- [ ] Add create/update/delete place adapter methods.
- [ ] Add create/update/delete visit adapter methods.
- [ ] Add select-place, merge-visits, and bulk-update-status visit adapter methods.
- [ ] Add add-points adapter method.
- [ ] Keep trip write methods implemented as unsupported until Dawarich API trip routes exist.
- [ ] Implement dry-run helpers that return validation, target entity, intended endpoint, and body without making mutating requests.
- [ ] Implement audit logging for mutating operations, writing JSON Lines with timestamp, tool name, dry-run flag, target IDs, and status. Never log API keys.
- [ ] Test that destructive tools default to dry-run and that dry-run never calls POST/PATCH/DELETE.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich write adapters`.

### Task 5: Register LLM-friendly resources

**Files:**
- Create: `src/mcp/resources.ts`
- Create: `src/utils/time.ts`
- Create: `src/utils/pagination.ts`
- Test: `tests/resources.test.ts`

- [ ] Implement resource URI parser for the `dawarich://` scheme.
- [ ] Register fixed resources:
  - `dawarich://profile`
  - `dawarich://stats/summary`
- [ ] Register resource templates for stats, map, timeline, places, visits, trips, and tracks.
- [ ] Return JSON resources with compact summaries and related resource links.
- [ ] Cap large arrays and include `truncated`, `total_count`, and next-page URIs.
- [ ] Test every URI template and invalid URI error path.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich mcp resources`.

### Task 6: Register read/search tools

**Files:**
- Create: `src/mcp/schemas.ts`
- Create: `src/mcp/result.ts`
- Create: `src/mcp/tools/read.ts`
- Modify: `src/server.ts`
- Test: `tests/read-tools.test.ts`

- [ ] Define Zod schemas and output schemas for:
  - `dawarich_search_places`
  - `dawarich_find_visits`
  - `dawarich_get_timeline`
  - `dawarich_get_map_context`
  - `dawarich_get_stats`
  - `dawarich_find_points`
- [ ] Include tool descriptions that explain when to prefer higher-level tools over point-heavy calls.
- [ ] Return `structuredContent` and a short text block for compatibility.
- [ ] Return resource links for follow-up context.
- [ ] Test schema validation, happy paths, upstream errors, and truncation behavior.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich read tools`.

### Task 7: Register write tools

**Files:**
- Create: `src/mcp/tools/write.ts`
- Modify: `src/server.ts`
- Test: `tests/write-tools.test.ts`

- [ ] Define schemas and handlers for:
  - `dawarich_create_place`
  - `dawarich_update_place`
  - `dawarich_delete_place`
  - `dawarich_create_visit`
  - `dawarich_update_visit`
  - `dawarich_select_visit_place`
  - `dawarich_merge_visits`
  - `dawarich_bulk_update_visit_status`
  - `dawarich_create_trip`
  - `dawarich_update_trip`
  - `dawarich_delete_trip`
  - `dawarich_add_points`
  - `dawarich_recalculate`
- [ ] Default `dry_run` to true for delete, merge, bulk update, and recalculation tools.
- [ ] For unsupported trip tools, return `isError: true` with a precise message: Dawarich lacks `/api/v1/trips`; implement that API before enabling this tool.
- [ ] Test every mutating tool dry-run path and at least one real mocked mutation path per domain.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich write tools`.

### Task 8: Add prompts

**Files:**
- Create: `src/mcp/prompts.ts`
- Modify: `src/server.ts`
- Test: `tests/prompts.test.ts`

- [ ] Add `review_suggested_visits` prompt.
- [ ] Add `create_trip_from_dates` prompt.
- [ ] Add `monthly_travel_summary` prompt.
- [ ] Add `clean_up_place_history` prompt.
- [ ] Each prompt should name the expected tools/resources in order and require user confirmation before write tools that default to dry-run false.
- [ ] Test prompt listing and rendered messages for required arguments.
- [ ] Run `npm test`.
- [ ] Commit with message `feat: add dawarich workflow prompts`.

### Task 9: Document setup and live verification

**Files:**
- Create: `README.md`
- Modify: `.env.example`
- Create: `tests/integration/live.test.ts`

- [ ] Document MCP client config for stdio.
- [ ] Document required env vars without including secrets.
- [ ] Document self-hosted deployment note: `https://timeline.<domain>/api/v1` bypasses forward-auth but still needs Dawarich API key auth.
- [ ] Add optional live tests gated by `DAWARICH_LIVE_TESTS=1`.
- [ ] Live tests should only call:
  - health/profile
  - stats summary
  - map bounds for a small recent range
  - dry-run create visit
- [ ] Do not read or print personal detailed point/visit data in CI logs.
- [ ] Run `npm test`.
- [ ] Commit with message `docs: document dawarich mcp setup`.

### Task 10: Add trip API support upstream or local extension

**Files in Dawarich source if contributing upstream:**
- Modify: `/home/sebastian/projects/temp/dawarich/config/routes.rb`
- Create: `/home/sebastian/projects/temp/dawarich/app/controllers/api/v1/trips_controller.rb`
- Create: `/home/sebastian/projects/temp/dawarich/app/serializers/api/trip_serializer.rb`
- Create: `/home/sebastian/projects/temp/dawarich/spec/swagger/api/v1/trips_controller_spec.rb`
- Create: `/home/sebastian/projects/temp/dawarich/spec/requests/api/v1/trips_spec.rb` if the project uses non-swagger request specs for coverage.

API shape to propose:

- `GET /api/v1/trips`
  - filters: `start_at`, `end_at`, `page`, `per_page`
- `GET /api/v1/trips/{id}`
- `POST /api/v1/trips`
  - body: `{ "trip": { "name": "...", "started_at": "...", "ended_at": "...", "description": "..." } }`
- `PATCH /api/v1/trips/{id}`
- `DELETE /api/v1/trips/{id}`
- `POST /api/v1/trips/{id}/recalculate`

Serializer fields:

- `id`
- `name`
- `started_at`
- `ended_at`
- `description_text`
- `distance`
- `path`
- `visited_countries`
- `last_recalculated_at`
- `recalculating`
- `created_at`
- `updated_at`

Implementation notes:

- Reuse `Trip` validations and calculation jobs.
- Scope every query through `current_api_user.trips`.
- Call `require_write_api!` on mutating actions for cloud behavior.
- Return `202 Accepted` for recalculate.
- Keep description handling compatible with ActionText.

After this exists, update `src/dawarich/trips.ts` and enable trip MCP resources/tools.

### Task 11: Manual MCP verification

**Files:**
- No source file changes expected unless verification exposes defects.

- [ ] Run `npm run build`.
- [ ] Run `npm test`.
- [ ] Run MCP Inspector.
- [ ] Confirm tool list includes the planned read and write tools.
- [ ] Read `dawarich://stats/summary`.
- [ ] Call `dawarich_get_map_context` with a small range.
- [ ] Call `dawarich_create_visit` with `dry_run: true`.
- [ ] Call `dawarich_create_trip` and verify it returns the unsupported trip API message until Dawarich API routes exist.
- [ ] If a test API key is available, perform one create/update/delete cycle on a synthetic place whose name starts with `MCP Test`.
- [ ] Commit fixes, then commit verification docs if changed.

## Security and Privacy Requirements

- Never log `DAWARICH_API_KEY`.
- Prefer bearer auth to avoid API key leakage in URL logs. Keep query auth only for compatibility.
- Mutating and destructive tools must include dry-run behavior.
- Deletion, merge, bulk update, and recalculation default to dry-run.
- Use strict input validation for coordinates, dates, page sizes, enum values, and bbox ordering.
- Cap large point, hexagon, fog, and timeline outputs by default.
- Do not use the user's live Dawarich data in tests unless `DAWARICH_LIVE_TESTS=1` is explicitly set.
- Live tests should summarize counts and IDs only when necessary; avoid dumping detailed traces.
- MCP tool descriptions should not imply write tools are safe without user confirmation. MCP clients should still request human approval for mutations.

## Open Decisions

1. Trip API strategy:
   - Recommended: add narrow `/api/v1/trips` support to Dawarich.
   - Avoid: HTML scraping with session cookies and CSRF unless the user explicitly accepts a fragile local-only fallback.

2. SDK version:
   - Recommended for July 2026 start: production-supported TypeScript SDK line.
   - Re-check after the 2026-07-28 MCP spec release before committing to v2 package names.

3. Live instance access:
   - Recommended: configure `DAWARICH_BASE_URL=https://timeline.<domain>` and `DAWARICH_API_KEY` locally, then run gated live tests.
   - Do not store the key in git or derive it from the automated-setups repo.

## Completion Criteria

- MCP server builds with strict TypeScript.
- Unit tests cover config, HTTP client, adapters, tools, resources, prompts, and dry-run safety.
- MCP Inspector can list and call resources/tools over stdio.
- The server can read stats, map context, places, visits, timeline, and points from Dawarich.
- The server can create/update/delete places and visits through Dawarich API with dry-run support.
- Trip tools are either fully enabled through real `/api/v1/trips` routes or explicitly return a clear unsupported-capability error.
- Documentation explains self-hosted deployment routing, auth, privacy, and live-test gating.
- No OpenAPI-generated raw endpoint dump is exposed as the main MCP interface.

## Plan Self-Review

Spec coverage:

- Maps: covered by map resources and `dawarich_get_map_context`.
- Trips: covered as a first-class MCP concept, with current Dawarich API gap and concrete upstream implementation path.
- Places/Visits: covered with resources plus create/update/delete/select/merge/bulk tools.
- Stats: covered with summary/year/month resources and `dawarich_get_stats`.
- Read/write support: covered for places, visits, points, and trip plan once API gap is closed.
- Swagger UI/source code review: reflected in evidence and adapter endpoint mapping.
- Self-hosted deployment: reflected in route/auth/deployment notes without reading private live data.

Placeholder scan:

- No implementation step depends on unresolved placeholder behavior. Unsupported trip behavior is explicit and testable.

Type consistency:

- Tool names, resource URI names, adapter file names, and task references are consistent across the plan.
