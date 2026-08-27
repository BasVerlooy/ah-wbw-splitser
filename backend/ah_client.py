from pathlib import Path
from typing import Optional

import httpx

QUERIES_DIR = Path(__file__).parent / "queries"

_RECEIPT_DETAIL = (QUERIES_DIR / "receiptDetail.gql").read_text()

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

_GQL_URL = "https://api.ah.nl/graphql"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)",
    "x-client-name": "appie-ios",
    "x-client-version": "9.28",
}


def _gql(client: httpx.Client, query: str, variables: Optional[dict] = None, access_token: str = "") -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    headers = {**_HEADERS, "Authorization": f"Bearer {access_token}"}
    resp = client.post(_GQL_URL, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise ValueError(f"GraphQL error: {data['errors']}")

    return data


_PAGE_SIZE = 50


def fetch_receipts_page(offset: int = 0, access_token: str = "") -> dict:
    with httpx.Client(timeout=30.0) as client:
        data = _gql(client, _RECEIPTS_PAGINATED, {"offset": offset, "limit": _PAGE_SIZE}, access_token=access_token)
        page = data["data"]["posReceiptsPage"]
        pagination = page["pagination"]

    return {
        "receipts": page["posReceipts"],
        "total": pagination.get("totalElements") or 0,
        "limit": pagination.get("limit") or _PAGE_SIZE,
        "offset": offset,
    }


def fetch_receipt_detail(receipt_id: str, access_token: str = "") -> dict:
    with httpx.Client(timeout=30.0) as client:
        data = _gql(client, _RECEIPT_DETAIL, {"posReceiptDetailsId": receipt_id}, access_token=access_token)
    return data["data"]["posReceiptDetails"]
