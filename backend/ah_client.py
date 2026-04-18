import os
from pathlib import Path
from typing import Optional

import httpx

QUERIES_DIR = Path(__file__).parent / "queries"

_RECEIPT_DETAIL = (QUERIES_DIR / "receiptDetail.gql").read_text()

# Paginated variant — pagination input object with required offset and limit
_RECEIPTS_PAGINATED = """
query GetReceipts($offset: Int!, $limit: Int!) {
  posReceiptsPage(pagination: {offset: $offset, limit: $limit}) {
    posReceipts {
      id
      dateTime
      totalAmount {
        amount
      }
    }
    pagination {
      key
      totalElements
      offset
      limit
    }
  }
}
"""


def _headers(cookie: str = "") -> dict:
    return {
        "Cookie": cookie or os.getenv("COOKIE", ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }


def _gql(client: httpx.Client, query: str, variables: Optional[dict] = None, cookie: str = "") -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = client.post(
        os.getenv("AH_GQL_URL", "https://www.ah.nl/gql"),
        json=payload,
        headers=_headers(cookie),
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise ValueError(f"GraphQL error: {data['errors']}")

    return data


_PAGE_SIZE = 50


def fetch_receipts_page(offset: int = 0, cookie: str = "") -> dict:
    """Fetch one page of receipts from the given offset.

    Returns a dict with:
      - receipts: list of receipt dicts from this page
      - total: total number of receipts available on AH
      - limit: page size used
      - offset: offset that was used
    """
    with httpx.Client(timeout=30.0) as client:
        data = _gql(client, _RECEIPTS_PAGINATED, {"offset": offset, "limit": _PAGE_SIZE}, cookie=cookie)
        page = data["data"]["posReceiptsPage"]
        pagination = page["pagination"]

    return {
        "receipts": page["posReceipts"],
        "total": pagination.get("totalElements") or 0,
        "limit": pagination.get("limit") or _PAGE_SIZE,
        "offset": offset,
    }


def fetch_receipt_detail(receipt_id: str, cookie: str = "") -> dict:
    with httpx.Client(timeout=30.0) as client:
        data = _gql(client, _RECEIPT_DETAIL, {"posReceiptDetailsId": receipt_id}, cookie=cookie)
    return data["data"]["posReceiptDetails"]
