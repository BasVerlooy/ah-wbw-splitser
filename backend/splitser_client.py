"""Splitser (wiebetaaltwat.nl) REST API client."""

import os
import pathlib

import httpx

API = "https://app.wiebetaaltwat.nl/api"
_HEADERS = {
    "Accept":         "application/json",
    "Accept-Version": "11",
    "x-app-react":    "true",
    "Content-Type":   "application/json",
}

_SESSION_FILE = pathlib.Path(__file__).parent.parent / ".splitser_session"
_cached_cookie: "str | None" = None


def _load_cached_cookie() -> "str | None":
    """Return cached session cookie from memory or file, or None."""
    global _cached_cookie
    if _cached_cookie:
        return _cached_cookie
    if _SESSION_FILE.exists():
        cookie = _SESSION_FILE.read_text().strip()
        if cookie:
            _cached_cookie = cookie
            return cookie
    return None


def _save_cookie(cookie: str) -> None:
    global _cached_cookie
    _cached_cookie = cookie
    try:
        _SESSION_FILE.write_text(cookie)
    except OSError:
        pass  # non-fatal


def _clear_cookie() -> None:
    global _cached_cookie
    _cached_cookie = None
    try:
        _SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _login() -> str:
    """Perform sign-in and return the session cookie value."""
    username = os.getenv("SPLITSER_USERNAME", "")
    password = os.getenv("SPLITSER_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("SPLITSER_USERNAME and SPLITSER_PASSWORD must be set in .env")

    with httpx.Client(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
        r = client.post(
            f"{API}/users/sign_in",
            json={"user": {"email": username, "password": password}},
        )
        r.raise_for_status()
        cookie = r.cookies["_wbw_rails_session"]

    _save_cookie(cookie)
    return cookie


def _client(cookie: str) -> httpx.Client:
    """Return an authenticated client using the given session cookie."""
    client = httpx.Client(timeout=20, follow_redirects=True, headers=_HEADERS)
    client.headers["Cookie"] = f"_wbw_rails_session={cookie}"
    return client


def _authenticated_request(method: str, url: str, **kwargs):
    """
    Make an authenticated request, re-logging in once on 401/403.
    Returns the httpx.Response.
    """
    cookie = _load_cached_cookie() or _login()

    client = _client(cookie)
    try:
        r = getattr(client, method)(url, **kwargs)
    finally:
        client.close()

    if r.status_code in (401, 403):
        # Session expired — clear and retry once with fresh login
        _clear_cookie()
        cookie = _login()
        client = _client(cookie)
        try:
            r = getattr(client, method)(url, **kwargs)
        finally:
            client.close()

    return r


def create_expense(
    *,
    name: str,
    payed_by_member_id: str,
    payed_on: str,
    total_cents: int,
    shares: list[dict],   # [{"member_id": str, "cents": int}, ...]
    group: str = "",
) -> str:
    """Create an expense in the configured Splitser group and return its ID."""
    group = group or os.getenv("SPLITSER_GROUP", "")
    if not group:
        raise RuntimeError("SPLITSER_GROUP must be set in settings or .env")

    # Rounding correction: cents must sum exactly to total_cents
    diff = total_cents - sum(s["cents"] for s in shares)
    if diff and shares:
        shares = [*shares]
        shares[0] = {**shares[0], "cents": shares[0]["cents"] + diff}

    payload = {
        "expense": {
            "name": name,
            "payed_by_id": payed_by_member_id,
            "payed_on": payed_on,
            "amount": {"currency": "EUR", "fractional": total_cents},
            "shares_attributes": [
                {
                    "member_id": s["member_id"],
                    "meta": {"type": "factor", "multiplier": 1.0},
                    "source_amount": {"currency": "EUR", "fractional": s["cents"]},
                }
                for s in shares
            ],
        }
    }

    r = _authenticated_request("post", f"{API}/lists/{group}/expenses", json=payload)

    if not r.is_success:
        raise RuntimeError(f"Splitser API {r.status_code}: {r.text}")

    return r.json()["expense"]["id"]


def update_expense(
    expense_id: str,
    *,
    name: str,
    payed_by_member_id: str,
    payed_on: str,
    total_cents: int,
    shares: list[dict],
) -> None:
    """Update an existing Splitser expense."""
    diff = total_cents - sum(s["cents"] for s in shares)
    if diff and shares:
        shares = [*shares]
        shares[0] = {**shares[0], "cents": shares[0]["cents"] + diff}

    payload = {
        "expense": {
            "name": name,
            "payed_by_id": payed_by_member_id,
            "payed_on": payed_on,
            "amount": {"currency": "EUR", "fractional": total_cents},
            "shares_attributes": [
                {
                    "member_id": s["member_id"],
                    "meta": {"type": "factor", "multiplier": 1.0},
                    "source_amount": {"currency": "EUR", "fractional": s["cents"]},
                }
                for s in shares
            ],
        }
    }

    r = _authenticated_request("patch", f"{API}/expenses/{expense_id}", json=payload)

    if not r.is_success:
        raise RuntimeError(f"Splitser API {r.status_code}: {r.text}")


def delete_expense(expense_id: str) -> None:
    """Delete a Splitser expense."""
    r = _authenticated_request("delete", f"{API}/expenses/{expense_id}")

    if not r.is_success:
        raise RuntimeError(f"Splitser API {r.status_code}: {r.text}")
