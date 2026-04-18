"""
Push receipt split groups to wiebetaaltwat.nl (Splitser) via its REST API.

Usage:
  # One-time setup: discover group members and map them to local roommates by name
  python scripts/push_to_splitser.py --setup

  # Push all unpushed split groups for a receipt
  python scripts/push_to_splitser.py <receipt_id>

Requirements (host machine):
  uv add --dev httpx python-dotenv
  (playwright is NOT required — the Splitser API is used directly)
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SPLITSER_USERNAME = os.getenv("SPLITSER_USERNAME", "")
SPLITSER_PASSWORD = os.getenv("SPLITSER_PASSWORD", "")
SPLITSER_GROUP    = os.getenv("SPLITSER_GROUP", "")

SPLITSER_API = "https://app.wiebetaaltwat.nl/api"
SPLITSER_HEADERS = {
    "Accept":         "application/json",
    "Accept-Version": "11",
    "x-app-react":    "true",
    "Content-Type":   "application/json",
}

# Backend API — running in Docker on localhost:8000 by default
API_BASE = os.getenv("API_BASE", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Splitser API client
# ---------------------------------------------------------------------------

def splitser_login() -> httpx.Client:
    """Log in and return an authenticated httpx.Client."""
    client = httpx.Client(timeout=20, follow_redirects=True, headers=SPLITSER_HEADERS)
    r = client.post(
        f"{SPLITSER_API}/users/sign_in",
        json={"user": {"email": SPLITSER_USERNAME, "password": SPLITSER_PASSWORD}},
    )
    r.raise_for_status()
    session_cookie = r.cookies["_wbw_rails_session"]
    client.headers["Cookie"] = f"_wbw_rails_session={session_cookie}"
    return client


def splitser_members(client: httpx.Client) -> list[dict]:
    """Return all members of the configured group."""
    r = client.get(f"{SPLITSER_API}/lists/{SPLITSER_GROUP}/members")
    r.raise_for_status()
    return [item["member"] for item in r.json()["data"]]


def splitser_create_expense(
    client: httpx.Client,
    *,
    name: str,
    payed_by_member_id: str,
    payed_on: str,           # "YYYY-MM-DD"
    total_cents: int,
    shares: list[dict],      # [{"member_id": "...", "cents": 500}, ...]
) -> str:
    """Create an expense and return its Splitser ID."""
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
    r = client.post(f"{SPLITSER_API}/lists/{SPLITSER_GROUP}/expenses", json=payload)
    if not r.is_success:
        raise RuntimeError(f"Splitser API error {r.status_code}: {r.text}")
    return r.json()["expense"]["id"]


# ---------------------------------------------------------------------------
# Local backend API helpers
# ---------------------------------------------------------------------------

def api_get(path: str):
    r = httpx.get(f"{API_BASE}{path}", timeout=15)
    r.raise_for_status()
    return r.json()


def api_patch(path: str, body: dict):
    r = httpx.patch(f"{API_BASE}{path}", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict):
    r = httpx.post(f"{API_BASE}{path}", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# --setup: discover members and map them to local roommates
# ---------------------------------------------------------------------------

def run_setup():
    print("=== Splitser setup: discovering group members ===\n")

    roommates = api_get("/roommates")
    by_name = {r["name"].lower(): r for r in roommates}
    print(f"Local roommates: {[r['name'] for r in roommates]}\n")

    client = splitser_login()
    members = splitser_members(client)

    print(f"Splitser members ({len(members)}):")
    for m in members:
        print(f"  {m['nickname']:<20} id={m['id']}")

    print()
    matched = 0
    for m in members:
        key = m["nickname"].lower()
        roommate = by_name.get(key)
        if not roommate:
            for name_key, r in by_name.items():
                if key in name_key or name_key in key:
                    roommate = r
                    break

        if roommate:
            api_patch(f"/roommates/{roommate['id']}", {"splitser_member_id": m["id"]})
            print(f"  Mapped '{m['nickname']}' → roommate #{roommate['id']} ({roommate['name']})")
            matched += 1
        else:
            print(f"  No local match for '{m['nickname']}' (id={m['id']})")
            print(f"    → set manually: PATCH {API_BASE}/roommates/<id>  {{\"splitser_member_id\": \"{m['id']}\"}}")

    print(f"\nDone. {matched}/{len(members)} mapped.")


# ---------------------------------------------------------------------------
# Push: create Splitser expenses for a receipt's split groups
# ---------------------------------------------------------------------------

def run_push(receipt_id: str):
    print(f"=== Pushing receipt {receipt_id} to Splitser ===\n")

    receipt = api_get(f"/receipts/{receipt_id}")
    splits  = api_get(f"/receipts/{receipt_id}/splits")
    groups  = splits.get("splits", [])

    if not groups:
        print("No split groups configured for this receipt. Nothing to push.")
        return

    # Validate all roommates have splitser_member_id
    missing = {
        r["roommate_name"]
        for g in groups
        for r in g["roommates"]
        if not r.get("splitser_member_id")
    }
    if missing:
        print(f"ERROR: These roommates have no splitser_member_id: {sorted(missing)}")
        print("Run:  python scripts/push_to_splitser.py --setup")
        sys.exit(1)

    unpushed = [g for g in groups if not g.get("splitser_expense_id")]
    already  = [g for g in groups if g.get("splitser_expense_id")]

    if already:
        for g in already:
            print(f"  Already pushed: '{g['name']}' → {g['splitser_expense_id']}")
    if not unpushed:
        print("All split groups already pushed.")
        return

    # Build expense metadata
    store_number = receipt.get("store_info") or ""
    if receipt.get("date_time"):
        dt = datetime.fromisoformat(receipt["date_time"].replace("Z", "+00:00"))
        payed_on = dt.strftime("%Y-%m-%d")
    else:
        from datetime import date
        payed_on = date.today().isoformat()

    client = splitser_login()

    for group in unpushed:
        name = f"{group['name']} - AH {store_number}".strip(" -")
        total_cents = round(group["total"] * 100)

        # Build shares: one per roommate with their calculated amount in cents
        shares = []
        for rm in group["roommates"]:
            cents = round(rm["amount"] * 100)
            shares.append({"member_id": rm["splitser_member_id"], "cents": cents})

        # Payer = first roommate in the group (or pick the one with the largest share)
        payer_id = shares[0]["member_id"]

        # Rounding correction: cents must sum to total_cents exactly
        diff = total_cents - sum(s["cents"] for s in shares)
        if diff:
            shares[0]["cents"] += diff

        print(f"  Creating '{name}'  €{group['total']:.2f}  ({len(shares)} members) …")

        try:
            expense_id = splitser_create_expense(
                client,
                name=name,
                payed_by_member_id=payer_id,
                payed_on=payed_on,
                total_cents=total_cents,
                shares=shares,
            )
            api_post(
                f"/receipts/{receipt_id}/splits/{group['id']}/splitser-expense",
                {"expense_id": expense_id},
            )
            print(f"    ✓ Created and saved: {expense_id}")
        except Exception as e:
            print(f"    ✗ Failed: {e}")

    print("\nDone.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Push receipt splits to wiebetaaltwat.nl")
    parser.add_argument("receipt_id", nargs="?", help="Receipt ID to push")
    parser.add_argument("--setup", action="store_true", help="Map Splitser members to local roommates")
    args = parser.parse_args()

    if not SPLITSER_USERNAME or not SPLITSER_PASSWORD:
        print("ERROR: SPLITSER_USERNAME and SPLITSER_PASSWORD must be set in .env")
        sys.exit(1)
    if not SPLITSER_GROUP:
        print("ERROR: SPLITSER_GROUP must be set in .env")
        sys.exit(1)

    if args.setup:
        run_setup()
    elif args.receipt_id:
        run_push(args.receipt_id)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
