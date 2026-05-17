# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

### Backend
```bash
# Run dev server (from project root)
uv run granian --interface asgi backend.main:app --host 0.0.0.0 --port 8000 --reload

# Install dependencies
uv sync
```

### Frontend
```bash
cd frontend
bun install
bun run dev      # Vite dev server on :5173
bun run build
```

### Docker (full stack)
```bash
docker compose up --build          # production-like
docker compose watch               # with hot-reload
```

## Architecture

### Backend (`backend/`)
FastAPI app served by Granian (ASGI). SQLite via SQLAlchemy 2 (sync ORM). Run as a package (`backend.main:app`) so relative imports work.

**Key modules:**
- `main.py` — all FastAPI routes, Pydantic schemas, and business logic helpers
- `db.py` — SQLAlchemy models and `get_db` dependency
- `ah_client.py` — AH GraphQL API (`https://www.ah.nl/gql`). Authenticates via a session `Cookie` header (stored in DB settings or `COOKIE` env var)
- `splitser_client.py` — wiebetaaltwat.nl REST API. Caches the `_wbw_rails_session` cookie in memory and on disk (`.splitser_session`) to avoid rate-limiting the sign-in endpoint. Credentials come from `SPLITSER_USERNAME` / `SPLITSER_PASSWORD` env vars.
- `queries/receipts.gql` + `queries/receiptDetail.gql` — GraphQL queries for the AH API

**Database schema** (SQLite, `receipts.db` at project root):
- `receipts` + `receipt_products` + `receipt_discounts` — raw AH receipt data
  - `receipt_products` includes: `name`, `quantity`, `price`, `amount`, `deposit`, `ah_product_id`, `indicator_name`, `indicator_discount`, `indicator_percentage`, `weight_amount`, `weight_unit`
- `roommates` — people in the household; `is_default_payer` (INTEGER, only one row can be 1), `splitser_member_id`
- `split_groups` — how a receipt is divided; `override_amount` (manual total override), `payed_by_roommate_id` (FK → roommates)
- `split_group_products` — products in a split; `quantity` (partial quantity override, NULL = full product quantity)
- `split_group_roommates` — roommates in a split; `share` (percentage, NULL = equal split)
- `settings` — key/value store for `ah_cookie` and `splitser_group` UUID

**Schema migrations** run at startup in the lifespan handler — `ALTER TABLE ADD COLUMN` statements are swallowed if the column already exists. New columns must be added there.

**Important helpers in `main.py`:**
- `_normalize_name(name)` — lowercase, strips "AH " prefix, removes non-alphanumeric chars; used for discount-product matching
- `_match_discounts_to_products(products, discounts)` — two-pass matching: (1) name substring ≥5 chars, splitting amount across multiple matches; (2) positional fallback using `indicator_discount` codes
- `_product_cost(sgp, discount=0.0)` — cost for a `SplitGroupProduct`, prorating discount if quantity is partial
- `_calc_group(group)` — calculates per-roommate amounts for a split group; result is the source of truth for Splitser pushes
- `_build_expense_args(receipt, group, splitser_group)` — builds the payload for `create_expense` / `update_expense`. Payer priority: explicit `payed_by_roommate_id` → roommate with `is_default_payer` → raises 422 (no silent fallback)
- `_get_setting(db, key)` / `_set_setting(db, key, value)` — reads/writes the `settings` table

**API routes (summary):**
- `POST /sync` — fetch one page of AH receipts (query param: `offset`)
- `GET /receipts`, `GET /receipts/{id}` — list/detail
- `GET|POST|DELETE /roommates`, `PATCH /roommates/{id}`
- `GET|PUT|DELETE /receipts/{id}/splits` — replace all splits atomically
- `POST /receipts/{id}/splits/{group_id}/push-to-splitser` — create Splitser expense
- `PATCH|DELETE /receipts/{id}/splits/{group_id}/splitser-expense` — update/remove
- `POST /push-all-to-splitser` — bulk push all unpushed splits
- `GET|PATCH /settings`, `GET /summary`

### Frontend (`frontend/`)
React 19 + Vite + React Router v7. No UI component library — plain HTML + `src/index.css`.

**Vite proxy:** all `/api/*` requests are proxied to `http://localhost:8000` (or `API_URL` env var, used in Docker compose to point at the `backend` service). Strips the `/api` prefix, so the frontend fetches `/api/receipts` → backend `/receipts`.

**`src/api.js`** — thin fetch wrapper (`get`, `post`, `put`, `patch`, `del`) that prepends `/api`.

**`src/App.jsx`** — top-level router with navbar and route definitions.

**Pages:** Dashboard (sync + bulk push), Receipts (paginated + filtered), ReceiptDetail (split editor), Roommates, Settings.

**Components:** `ReceiptsTable` — reusable receipt list used by both Dashboard and Receipts pages. Passes `state={{ from: location.pathname + location.search }}` on receipt links so `ReceiptDetail` can restore the correct back URL including search params.

## Environment variables

Stored in `.env` at project root (never committed).

| Variable | Purpose |
|---|---|
| `COOKIE` | AH session cookie (fallback if not set in DB settings) |
| `SPLITSER_USERNAME` | wiebetaaltwat.nl login email |
| `SPLITSER_PASSWORD` | wiebetaaltwat.nl login password |
| `SPLITSER_GROUP` | Splitser group UUID (fallback if not set in DB settings) |
| `AH_GQL_URL` | AH GraphQL endpoint (default: `https://www.ah.nl/gql`) |

`COOKIE` and `SPLITSER_GROUP` can also be configured via the Settings page (stored in the `settings` DB table), which takes precedence over env vars.
