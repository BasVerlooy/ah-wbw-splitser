import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, object_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("backend")

from sqlalchemy import text

from . import ah_auth, ah_client, splitser_client
from .db import (
    Base, KoopzegelBuyer, Receipt, ReceiptDiscount, ReceiptProduct,
    Roommate, Setting, SplitGroup, SplitGroupProduct, SplitGroupRoommate,
    engine, get_db,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Migrate existing databases to add new columns
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE roommates ADD COLUMN splitser_member_id TEXT",
            "ALTER TABLE split_groups ADD COLUMN splitser_expense_id TEXT",
            "ALTER TABLE split_groups ADD COLUMN override_amount REAL",
            "ALTER TABLE split_group_products ADD COLUMN quantity REAL",
            "ALTER TABLE receipt_products ADD COLUMN ah_product_id TEXT",
            "ALTER TABLE receipt_products ADD COLUMN indicator_name TEXT",
            "ALTER TABLE receipt_products ADD COLUMN indicator_discount TEXT",
            "ALTER TABLE receipt_products ADD COLUMN indicator_percentage REAL",
            "ALTER TABLE receipt_products ADD COLUMN weight_amount REAL",
            "ALTER TABLE receipt_products ADD COLUMN weight_unit TEXT",
            "ALTER TABLE split_groups ADD COLUMN payed_by_roommate_id INTEGER REFERENCES roommates(id)",
            "ALTER TABLE roommates ADD COLUMN is_default_payer INTEGER",
            "ALTER TABLE receipts ADD COLUMN stamps_quantity INTEGER",
            "ALTER TABLE receipts ADD COLUMN stamps_amount REAL",
            "ALTER TABLE receipts ADD COLUMN stamps_fetched_at TEXT",
            "ALTER TABLE receipts ADD COLUMN koopzegel_buyer_id INTEGER REFERENCES koopzegel_buyers(id)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        ))
        conn.commit()
    yield


app = FastAPI(title="AH WBW Splitser", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("%s %s -> %s %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("%s %s -> 500 %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RoommateCreate(BaseModel):
    name: str


class RoommateUpdate(BaseModel):
    splitser_member_id: Optional[str] = None
    is_default_payer: Optional[bool] = None


class KoopzegelBuyerCreate(BaseModel):
    name: str


class KoopzegelBuyerUpdate(BaseModel):
    buyer_id: Optional[int] = None


class SplitserExpenseIn(BaseModel):
    expense_id: str


class SplitRoommateIn(BaseModel):
    roommate_id: int
    share: Optional[float] = None  # percentage (0-100), None = equal


class SplitProductIn(BaseModel):
    product_id: int
    quantity: Optional[float] = None  # None = use full product quantity


class SplitGroupIn(BaseModel):
    name: str
    products: list[SplitProductIn]
    roommates: list[SplitRoommateIn]
    override_amount: Optional[float] = None
    payed_by_roommate_id: Optional[int] = None


class SplitsUpdate(BaseModel):
    splits: list[SplitGroupIn]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Lowercase, strip common AH prefix, keep only alphanumeric chars."""
    name = name.lower()
    name = re.sub(r'^ah\s+', '', name)
    return re.sub(r'[^a-z0-9]', '', name)


def _koopzegel_buyer_dict(buyer: KoopzegelBuyer) -> dict:
    return {"id": buyer.id, "name": buyer.name}


def _receipt_koopzegel_buyer_dict(receipt: Receipt) -> Optional[dict]:
    return (
        _koopzegel_buyer_dict(receipt.koopzegel_buyer)
        if receipt.koopzegel_buyer
        else None
    )


def _match_discounts_to_products(products, discounts) -> dict[int, dict]:
    """Return mapping of product DB id → {"names": [str], "amount": float}.

    Two-pass strategy:
    1. Name-based: look for a shared substring of 5+ chars between normalized
       product name and normalized discount name. When one discount matches
       multiple products (e.g. a 2-for-1 deal), the discount amount is split
       evenly across all matched products.
    2. Positional fallback: remaining unmatched discounts are assigned to
       products that carry an `indicator_discount` code of the same type, in
       receipt order (by DB id). AH uses "B" for BONUS discounts.
    """
    # discount.id → list of matched products (name-based)
    discount_to_products: dict[int, list] = {}
    name_matched_product_ids: set[int] = set()

    for d in discounts:
        if not d.name:
            continue
        dn = _normalize_name(d.name)
        matched = []
        for p in products:
            if not p.name:
                continue
            pn = _normalize_name(p.name)
            min_len = min(len(dn), len(pn))
            found = False
            for length in range(min_len, 4, -1):
                for i in range(len(dn) - length + 1):
                    if dn[i:i + length] in pn:
                        found = True
                        break
                if found:
                    break
            if found:
                matched.append(p)
        if matched:
            discount_to_products[d.id] = matched
            for p in matched:
                name_matched_product_ids.add(p.id)

    # Positional fallback: indicator "B" → discount_type "BONUS", etc.
    INDICATOR_TO_TYPE = {"B": "BONUS", "S": "STAFF"}
    unmatched_discounts = [d for d in discounts if d.id not in discount_to_products]

    for indicator_code, discount_type in INDICATOR_TO_TYPE.items():
        indicator_products = sorted(
            [p for p in products
             if p.indicator_discount
             and indicator_code in p.indicator_discount.split(",")
             and p.id not in name_matched_product_ids],
            key=lambda p: p.id,
        )
        type_discounts = [d for d in unmatched_discounts if d.discount_type == discount_type]
        for p, d in zip(indicator_products, type_discounts):
            discount_to_products[d.id] = [p]
            name_matched_product_ids.add(p.id)
            unmatched_discounts.remove(d)

    # Build result: per-product totals and names
    result: dict[int, dict] = {}
    for d in discounts:
        matched_prods = discount_to_products.get(d.id, [])
        if not matched_prods:
            continue
        per_product_amount = float(d.amount or 0) / len(matched_prods)
        for p in matched_prods:
            entry = result.setdefault(p.id, {"names": [], "amount": 0.0})
            entry["names"].append(d.name)
            entry["amount"] += per_product_amount

    return result


def _product_cost(sgp, discount: float = 0.0) -> float:
    """Cost attributed to a SplitGroupProduct entry, including any discount.

    `discount` is the total discount amount for the full product quantity
    (negative value). When only a partial quantity is split, the discount is
    prorated accordingly.
    """
    product = sgp.product
    full_cost = float(product.amount or product.price or 0) + discount
    if sgp.quantity is None:
        return full_cost
    product_qty = float(product.quantity or 1)
    return (full_cost / product_qty) * float(sgp.quantity)


def _calc_group(group: SplitGroup) -> dict:
    """Return serialised split group with calculated per-roommate amounts."""
    receipt = group.receipt
    discount_map = _match_discounts_to_products(receipt.products, receipt.discounts)

    calculated_total = sum(
        _product_cost(sgp, discount=discount_map.get(sgp.receipt_product_id, {}).get("amount", 0.0))
        for sgp in group.products
    )
    total = group.override_amount if group.override_amount is not None else calculated_total

    equal_members = [r for r in group.roommates if r.share is None]
    custom = [r for r in group.roommates if r.share is not None]
    custom_pct = sum(r.share for r in custom)
    remaining = total * (1 - custom_pct / 100)
    equal_per = remaining / len(equal_members) if equal_members else 0.0

    return {
        "id": group.id,
        "name": group.name,
        "splitser_expense_id": group.splitser_expense_id,
        "override_amount": group.override_amount,
        "payed_by_roommate_id": group.payed_by_roommate_id,
        "calculated_total": round(float(calculated_total), 2),
        "total": round(float(total), 2),
        "products": [
            {
                "product_id": p.receipt_product_id,
                "quantity": p.quantity,
                "discount_amount": round(discount_map.get(p.receipt_product_id, {}).get("amount", 0.0), 4),
            }
            for p in group.products
        ],
        "roommates": [
            {
                "roommate_id": r.roommate_id,
                "roommate_name": r.roommate.name,
                "splitser_member_id": r.roommate.splitser_member_id,
                "is_default_payer": bool(r.roommate.is_default_payer),
                "share_pct": r.share,
                "amount": round(
                    float(equal_per) if r.share is None else round(float(r.share) / 100 * float(total), 2), 2
                ),
            }
            for r in group.roommates
        ],
    }


def _friendly_ah_error(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code
    if status_code == 403:
        return HTTPException(
            status_code=403,
            detail="Albert Heijn rejected the request. Check your AH cookie and try syncing again.",
        )
    if status_code == 401:
        return HTTPException(
            status_code=401,
            detail="Albert Heijn authentication failed. Check your AH cookie and try again.",
        )
    return HTTPException(
        status_code=502,
        detail=f"Albert Heijn request failed with status {status_code}. Please try again later.",
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@app.post("/sync")
def sync_receipts(offset: int = 0, db: Session = Depends(get_db)):
    """Fetch one page of receipts from Albert Heijn (starting at `offset`) and store new ones.

    Pass offset=0 (default) for the latest receipts. Use the returned
    `next_offset` and `total_available` to determine whether earlier receipts
    exist and what offset to pass next.
    """
    ah_token = _get_setting(db, "ah_access_token") or ""
    try:
        page = ah_client.fetch_receipts_page(offset=offset, access_token=ah_token)
    except httpx.HTTPStatusError as exc:
        raise _friendly_ah_error(exc) from exc
    receipts = page["receipts"]
    total_available = page["total"]

    new_count = 0
    skipped = 0

    for r in receipts:
        existing_receipt = db.get(Receipt, r["id"])
        if existing_receipt and existing_receipt.stamps_fetched_at:
            skipped += 1
            continue

        try:
            detail = ah_client.fetch_receipt_detail(r["id"], access_token=ah_token)
        except httpx.HTTPStatusError as exc:
            raise _friendly_ah_error(exc) from exc

        stamps = detail.get("stamps")
        stamps_quantity = stamps.get("quantity") if stamps else None
        stamps_amount = (stamps.get("amount") or {}).get("amount") if stamps else None

        if existing_receipt:
            existing_receipt.stamps_quantity = stamps_quantity
            existing_receipt.stamps_amount = stamps_amount
            existing_receipt.stamps_fetched_at = datetime.now(timezone.utc).isoformat()
            db.commit()
            skipped += 1
            continue

        address = detail.get("address") or {}

        receipt = Receipt(
            id=r["id"],
            date_time=r.get("dateTime"),
            total_amount=(r.get("totalAmount") or {}).get("amount"),
            store_info=", ".join(str(x) for x in v) if isinstance(v := detail.get("storeInfo"), list) else v,
            address_city=address.get("city"),
            address_postal_code=address.get("postalCode"),
            address_street=address.get("street"),
            address_house_number=address.get("houseNumber"),
            stamps_quantity=stamps_quantity,
            stamps_amount=stamps_amount,
            stamps_fetched_at=datetime.now(timezone.utc).isoformat(),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(receipt)

        for p in detail.get("products") or []:
            indicators = p.get("indicators") or []
            db.add(
                ReceiptProduct(
                    receipt_id=receipt.id,
                    name=p.get("name"),
                    quantity=p.get("quantity"),
                    price=(p.get("price") or {}).get("amount"),
                    amount=(p.get("amount") or {}).get("amount"),
                    deposit=(p.get("deposit") or {}).get("amount"),
                    ah_product_id=p.get("id"),
                    indicator_name=",".join(i["name"] for i in indicators if i.get("name")) or None,
                    indicator_discount=",".join(i["discount"] for i in indicators if i.get("discount")) or None,
                    indicator_percentage=indicators[0].get("percentage") if indicators else None,
                    weight_amount=(p.get("weight") or {}).get("amount"),
                    weight_unit=(p.get("weight") or {}).get("unit"),
                )
            )

        for d in detail.get("discounts") or []:
            db.add(
                ReceiptDiscount(
                    receipt_id=receipt.id,
                    name=d.get("name"),
                    discount_type=d.get("type"),
                    amount=(d.get("amount") or {}).get("amount"),
                )
            )

        db.commit()
        new_count += 1

    next_offset = offset + len(receipts)
    return {
        "synced": new_count,
        "skipped": skipped,
        "total": len(receipts),
        "total_available": total_available,
        "next_offset": next_offset,
        "has_more": next_offset < total_available,
    }


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


@app.get("/receipts")
def list_receipts(db: Session = Depends(get_db)):
    rows = db.query(Receipt).order_by(Receipt.date_time.desc()).all()
    return [
        {
            "id": r.id,
            "date_time": r.date_time,
            "total_amount": r.total_amount,
            "product_count": len(r.products),
            "split_product_count": len({
                p.receipt_product_id
                for g in r.split_groups
                for p in g.products
            }),
            "has_splits": bool(r.split_groups),
            "store_info": r.store_info,
            "stamps": {
                "quantity": r.stamps_quantity,
                "amount": r.stamps_amount,
            } if r.stamps_fetched_at else None,
            "koopzegel_buyer": _receipt_koopzegel_buyer_dict(r),
            "address": {
                "city": r.address_city,
                "postal_code": r.address_postal_code,
                "street": r.address_street,
                "house_number": r.address_house_number,
            },
        }
        for r in rows
    ]


@app.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    discount_matches = _match_discounts_to_products(receipt.products, receipt.discounts)

    return {
        "id": receipt.id,
        "date_time": receipt.date_time,
        "total_amount": receipt.total_amount,
        "store_info": receipt.store_info,
        "stamps": {
            "quantity": receipt.stamps_quantity,
            "amount": receipt.stamps_amount,
        } if receipt.stamps_fetched_at else None,
        "koopzegel_buyer": _receipt_koopzegel_buyer_dict(receipt),
        "address": {
            "city": receipt.address_city,
            "postal_code": receipt.address_postal_code,
            "street": receipt.address_street,
            "house_number": receipt.address_house_number,
        },
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "quantity": p.quantity,
                "price": p.price,
                "amount": p.amount,
                "deposit": p.deposit,
                "indicator_name": p.indicator_name,
                "indicator_discount": p.indicator_discount,
                "matched_discounts": discount_matches.get(p.id, {}).get("names", []),
                "discount_amount": round(discount_matches.get(p.id, {}).get("amount", 0.0), 4),
            }
            for p in receipt.products
        ],
        "discounts": [
            {
                "name": d.name,
                "type": d.discount_type,
                "amount": d.amount,
            }
            for d in receipt.discounts
        ],
    }


# ---------------------------------------------------------------------------
# Koopzegel buyers
# ---------------------------------------------------------------------------


@app.get("/koopzegel-buyers")
def list_koopzegel_buyers(db: Session = Depends(get_db)):
    return [
        _koopzegel_buyer_dict(buyer)
        for buyer in db.query(KoopzegelBuyer).order_by(KoopzegelBuyer.name).all()
    ]


@app.post("/koopzegel-buyers", status_code=201)
def create_koopzegel_buyer(body: KoopzegelBuyerCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Buyer name is required")
    if db.query(KoopzegelBuyer).filter(KoopzegelBuyer.name == name).first():
        raise HTTPException(status_code=409, detail="Koopzegel buyer already exists")
    buyer = KoopzegelBuyer(name=name)
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    return _koopzegel_buyer_dict(buyer)


@app.delete("/koopzegel-buyers/{buyer_id}", status_code=204)
def delete_koopzegel_buyer(buyer_id: int, db: Session = Depends(get_db)):
    buyer = db.get(KoopzegelBuyer, buyer_id)
    if not buyer:
        raise HTTPException(status_code=404, detail="Koopzegel buyer not found")
    if buyer.receipts:
        raise HTTPException(
            status_code=409,
            detail="Cannot remove a Koopzegel buyer assigned to receipts",
        )
    db.delete(buyer)
    db.commit()


@app.patch("/receipts/{receipt_id}/koopzegel-buyer")
def update_receipt_koopzegel_buyer(
    receipt_id: str,
    body: KoopzegelBuyerUpdate,
    db: Session = Depends(get_db),
):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.stamps_quantity is None:
        raise HTTPException(status_code=400, detail="Receipt has no Koopzegels")

    buyer = None
    if body.buyer_id is not None:
        buyer = db.get(KoopzegelBuyer, body.buyer_id)
        if not buyer:
            raise HTTPException(status_code=404, detail="Koopzegel buyer not found")

    receipt.koopzegel_buyer = buyer
    db.commit()
    db.refresh(receipt)
    return {"koopzegel_buyer": _receipt_koopzegel_buyer_dict(receipt)}


# ---------------------------------------------------------------------------
# Roommates
# ---------------------------------------------------------------------------


def _roommate_dict(r: Roommate) -> dict:
    return {"id": r.id, "name": r.name, "splitser_member_id": r.splitser_member_id, "is_default_payer": bool(r.is_default_payer)}


@app.get("/roommates")
def list_roommates(db: Session = Depends(get_db)):
    return [_roommate_dict(r) for r in db.query(Roommate).all()]


@app.post("/roommates", status_code=201)
def create_roommate(body: RoommateCreate, db: Session = Depends(get_db)):
    if db.query(Roommate).filter(Roommate.name == body.name).first():
        raise HTTPException(status_code=409, detail="Roommate already exists")
    roommate = Roommate(name=body.name)
    db.add(roommate)
    db.commit()
    db.refresh(roommate)
    return _roommate_dict(roommate)


@app.patch("/roommates/{roommate_id}")
def update_roommate(roommate_id: int, body: RoommateUpdate, db: Session = Depends(get_db)):
    roommate = db.get(Roommate, roommate_id)
    if not roommate:
        raise HTTPException(status_code=404, detail="Roommate not found")
    if body.splitser_member_id is not None:
        roommate.splitser_member_id = body.splitser_member_id
    if body.is_default_payer is not None:
        if body.is_default_payer:
            # Clear any existing default payer first
            for other in db.query(Roommate).filter(Roommate.id != roommate_id).all():
                other.is_default_payer = None
            roommate.is_default_payer = 1
        else:
            roommate.is_default_payer = None
    db.commit()
    return _roommate_dict(roommate)


@app.delete("/roommates/{roommate_id}", status_code=204)
def delete_roommate(roommate_id: int, db: Session = Depends(get_db)):
    roommate = db.get(Roommate, roommate_id)
    if not roommate:
        raise HTTPException(status_code=404, detail="Roommate not found")
    db.delete(roommate)
    db.commit()


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


@app.get("/receipts/{receipt_id}/splits")
def get_splits(receipt_id: str, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return {
        "receipt_id": receipt_id,
        "splits": [_calc_group(g) for g in receipt.split_groups],
    }


@app.put("/receipts/{receipt_id}/splits")
def set_splits(receipt_id: str, body: SplitsUpdate, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    valid_product_ids = {p.id for p in receipt.products}

    for group in body.splits:
        for sp in group.products:
            if sp.product_id not in valid_product_ids:
                raise HTTPException(status_code=400, detail=f"Product {sp.product_id} does not belong to this receipt")
        for r in group.roommates:
            if not db.get(Roommate, r.roommate_id):
                raise HTTPException(status_code=404, detail=f"Roommate {r.roommate_id} not found")

    # Delete existing split groups (cascades to products/roommates via ORM)
    for g in list(receipt.split_groups):
        db.delete(g)
    db.flush()

    for group_data in body.splits:
        group = SplitGroup(
            receipt_id=receipt_id,
            name=group_data.name,
            override_amount=group_data.override_amount,
            payed_by_roommate_id=group_data.payed_by_roommate_id,
        )
        db.add(group)
        db.flush()  # get group.id

        for sp in group_data.products:
            db.add(SplitGroupProduct(
                split_group_id=group.id,
                receipt_product_id=sp.product_id,
                quantity=sp.quantity,
            ))

        for r in group_data.roommates:
            db.add(SplitGroupRoommate(
                split_group_id=group.id,
                roommate_id=r.roommate_id,
                share=r.share,
            ))

    db.commit()
    db.refresh(receipt)

    return {
        "receipt_id": receipt_id,
        "splits": [_calc_group(g) for g in receipt.split_groups],
    }


@app.delete("/receipts/{receipt_id}/splits", status_code=204)
def delete_splits(receipt_id: str, db: Session = Depends(get_db)):
    receipt = db.get(Receipt, receipt_id)
    if receipt:
        for g in list(receipt.split_groups):
            db.delete(g)
        db.commit()


@app.post("/receipts/{receipt_id}/splits/{group_id}/splitser-expense")
def save_splitser_expense(
    receipt_id: str, group_id: int, body: SplitserExpenseIn, db: Session = Depends(get_db)
):
    """Store the Splitser expense ID on a split group after it has been pushed."""
    group = db.get(SplitGroup, group_id)
    if not group or group.receipt_id != receipt_id:
        raise HTTPException(status_code=404, detail="Split group not found")
    group.splitser_expense_id = body.expense_id
    db.commit()
    return {"group_id": group_id, "splitser_expense_id": group.splitser_expense_id}


@app.post("/receipts/{receipt_id}/splits/{group_id}/push-to-splitser")
def push_to_splitser(receipt_id: str, group_id: int, db: Session = Depends(get_db)):
    """Create a Splitser expense for a split group and save the returned ID."""
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    group = db.get(SplitGroup, group_id)
    if not group or group.receipt_id != receipt_id:
        raise HTTPException(status_code=404, detail="Split group not found")

    if group.splitser_expense_id:
        raise HTTPException(status_code=409, detail="Already pushed to Splitser")

    splitser_group = _get_setting(db, "splitser_group") or ""
    try:
        expense_id = splitser_client.create_expense(**_build_expense_args(receipt, group, splitser_group))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    group.splitser_expense_id = expense_id
    db.commit()
    return {"group_id": group_id, "splitser_expense_id": expense_id}


def _build_expense_args(receipt, group, splitser_group: str = "") -> dict:
    """Build keyword args for splitser_client.create/update_expense."""
    data = _calc_group(group)

    missing = [r["roommate_name"] for r in data["roommates"] if not r.get("splitser_member_id")]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing splitser_member_id for: {', '.join(missing)}",
        )

    store_number = receipt.store_info or ""
    if receipt.date_time:
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(receipt.date_time.replace("Z", "+00:00"))
        payed_on = dt.strftime("%Y-%m-%d")
    else:
        from datetime import date as _date
        payed_on = _date.today().isoformat()

    name = f"{data['name']} - AH {store_number}".strip(" -")
    total_cents = round(data["total"] * 100)
    shares = [
        {"member_id": r["splitser_member_id"], "cents": round(r["amount"] * 100)}
        for r in data["roommates"]
    ]

    if group.payed_by_roommate_id:
        payer_entry = next(
            (r for r in data["roommates"] if r["roommate_id"] == group.payed_by_roommate_id), None
        )
    else:
        payer_entry = next((r for r in data["roommates"] if r.get("is_default_payer")), None)

    if not payer_entry:
        # Default payer may exist but not be a member of this split group — query all roommates.
        db = object_session(group)
        default_payer = db.query(Roommate).filter(Roommate.is_default_payer == 1).first()
        if not default_payer:
            raise HTTPException(
                status_code=422,
                detail="No payer set for this split and no default payer configured. Set a default payer on a roommate first.",
            )
        if not default_payer.splitser_member_id:
            raise HTTPException(
                status_code=422,
                detail=f"Default payer '{default_payer.name}' has no Splitser member ID configured.",
            )
        payer_id = default_payer.splitser_member_id
    else:
        payer_id = payer_entry["splitser_member_id"]

    return dict(name=name, payed_by_member_id=payer_id, payed_on=payed_on, total_cents=total_cents, shares=shares, group=splitser_group)


@app.patch("/receipts/{receipt_id}/splits/{group_id}/splitser-expense")
def update_splitser_expense(receipt_id: str, group_id: int, db: Session = Depends(get_db)):
    """Push updated name/amount to Splitser for an already-pushed split group."""
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    group = db.get(SplitGroup, group_id)
    if not group or group.receipt_id != receipt_id:
        raise HTTPException(status_code=404, detail="Split group not found")
    if not group.splitser_expense_id:
        raise HTTPException(status_code=409, detail="Not yet pushed to Splitser")

    splitser_group = _get_setting(db, "splitser_group") or ""
    try:
        splitser_client.update_expense(group.splitser_expense_id, **_build_expense_args(receipt, group, splitser_group))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"group_id": group_id, "splitser_expense_id": group.splitser_expense_id}


@app.delete("/receipts/{receipt_id}/splits/{group_id}/splitser-expense", status_code=204)
def delete_splitser_expense(receipt_id: str, group_id: int, db: Session = Depends(get_db)):
    """Delete the Splitser expense and clear the stored ID."""
    group = db.get(SplitGroup, group_id)
    if not group or group.receipt_id != receipt_id:
        raise HTTPException(status_code=404, detail="Split group not found")
    if not group.splitser_expense_id:
        raise HTTPException(status_code=409, detail="No Splitser expense linked")

    try:
        splitser_client.delete_expense(group.splitser_expense_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    group.splitser_expense_id = None
    db.commit()


# ---------------------------------------------------------------------------
# Summary — who owes what across all split receipts
# ---------------------------------------------------------------------------


@app.post("/push-all-to-splitser")
def push_all_to_splitser(db: Session = Depends(get_db)):
    """Push every unpushed split group to Splitser. Returns counts of pushed and failed."""
    pushed = 0
    failed = []

    splitser_group = _get_setting(db, "splitser_group") or ""
    for receipt in db.query(Receipt).all():
        for group in receipt.split_groups:
            if group.splitser_expense_id:
                continue
            try:
                expense_id = splitser_client.create_expense(**_build_expense_args(receipt, group, splitser_group))
                group.splitser_expense_id = expense_id
                db.commit()
                pushed += 1
            except HTTPException as exc:
                failed.append({"group_id": group.id, "name": group.name, "error": exc.detail})
            except RuntimeError as exc:
                failed.append({"group_id": group.id, "name": group.name, "error": str(exc)})

    return {"pushed": pushed, "failed": failed}


# ---------------------------------------------------------------------------
# Settings

_SETTING_KEYS = {"splitser_group"}


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.get(Setting, key)
    return row.value if row else None


def _set_setting(db: Session, key: str, value: Optional[str]) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


class SettingsIn(BaseModel):
    splitser_group: Optional[str] = None


@app.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {key: _get_setting(db, key) for key in _SETTING_KEYS}


@app.patch("/settings")
def patch_settings(body: SettingsIn, db: Session = Depends(get_db)):
    if body.splitser_group is not None:
        _set_setting(db, "splitser_group", body.splitser_group or None)
    return {key: _get_setting(db, key) for key in _SETTING_KEYS}


class AhLoginIn(BaseModel):
    email: str
    password: str


class AhMfaIn(BaseModel):
    code: str


@app.post("/auth/ah/login")
async def ah_login(body: AhLoginIn, db: Session = Depends(get_db)):
    try:
        result = await ah_auth.start_login(body.email, body.password)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result["status"] == "success":
        tokens = result["tokens"]
        _set_setting(db, "ah_access_token", tokens.get("access_token"))
        _set_setting(db, "ah_refresh_token", tokens.get("refresh_token"))
    return result


@app.post("/auth/ah/mfa")
async def ah_mfa(body: AhMfaIn, db: Session = Depends(get_db)):
    try:
        result = await ah_auth.submit_mfa(body.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    tokens = result["tokens"]
    _set_setting(db, "ah_access_token", tokens.get("access_token"))
    _set_setting(db, "ah_refresh_token", tokens.get("refresh_token"))
    return {"status": "success"}


@app.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Aggregate split counts and pushed/unpushed breakdown."""
    total_splits = 0
    unpushed_splits = 0

    for receipt in db.query(Receipt).all():
        for group in receipt.split_groups:
            total_splits += 1
            if not group.splitser_expense_id:
                unpushed_splits += 1

    return {
        "total_splits": total_splits,
        "unpushed_splits": unpushed_splits,
        "pushed_splits": total_splits - unpushed_splits,
    }
