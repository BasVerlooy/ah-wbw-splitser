import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_FILE = BASE_DIR / "receipts.db"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_FILE.as_posix()}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(String, primary_key=True)
    date_time = Column(String, nullable=True)
    total_amount = Column(Float, nullable=True)
    store_info = Column(String, nullable=True)
    address_city = Column(String, nullable=True)
    address_postal_code = Column(String, nullable=True)
    address_street = Column(String, nullable=True)
    address_house_number = Column(String, nullable=True)
    fetched_at = Column(String, nullable=True)

    products = relationship("ReceiptProduct", back_populates="receipt", cascade="all, delete-orphan")
    discounts = relationship("ReceiptDiscount", back_populates="receipt", cascade="all, delete-orphan")
    split_groups = relationship("SplitGroup", back_populates="receipt", cascade="all, delete-orphan")


class ReceiptProduct(Base):
    __tablename__ = "receipt_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String, ForeignKey("receipts.id"), nullable=False)
    name = Column(String, nullable=True)
    quantity = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    amount = Column(Float, nullable=True)
    deposit = Column(Float, nullable=True)
    ah_product_id = Column(String, nullable=True)
    indicator_name = Column(String, nullable=True)   # comma-separated indicator display names
    indicator_discount = Column(String, nullable=True)  # comma-separated discount type keys
    indicator_percentage = Column(Float, nullable=True)
    weight_amount = Column(Float, nullable=True)
    weight_unit = Column(String, nullable=True)

    receipt = relationship("Receipt", back_populates="products")


class ReceiptDiscount(Base):
    __tablename__ = "receipt_discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String, ForeignKey("receipts.id"), nullable=False)
    name = Column(String, nullable=True)
    discount_type = Column(String, nullable=True)
    amount = Column(Float, nullable=True)

    receipt = relationship("Receipt", back_populates="discounts")


class Roommate(Base):
    __tablename__ = "roommates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    splitser_member_id = Column(String, nullable=True)
    is_default_payer = Column(Integer, nullable=True)  # 1 = yes, NULL = no (only one row can be 1)

    split_group_roommates = relationship("SplitGroupRoommate", back_populates="roommate")


class SplitGroup(Base):
    __tablename__ = "split_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receipt_id = Column(String, ForeignKey("receipts.id"), nullable=False)
    name = Column(String, nullable=False)
    splitser_expense_id = Column(String, nullable=True)
    override_amount = Column(Float, nullable=True)
    payed_by_roommate_id = Column(Integer, ForeignKey("roommates.id"), nullable=True)

    receipt = relationship("Receipt", back_populates="split_groups")
    products = relationship("SplitGroupProduct", back_populates="split_group", cascade="all, delete-orphan")
    roommates = relationship("SplitGroupRoommate", back_populates="split_group", cascade="all, delete-orphan")


class SplitGroupProduct(Base):
    __tablename__ = "split_group_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    split_group_id = Column(Integer, ForeignKey("split_groups.id"), nullable=False)
    receipt_product_id = Column(Integer, ForeignKey("receipt_products.id"), nullable=False)
    quantity = Column(Float, nullable=True)  # None = use full product quantity

    split_group = relationship("SplitGroup", back_populates="products")
    product = relationship("ReceiptProduct")


class SplitGroupRoommate(Base):
    __tablename__ = "split_group_roommates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    split_group_id = Column(Integer, ForeignKey("split_groups.id"), nullable=False)
    roommate_id = Column(Integer, ForeignKey("roommates.id"), nullable=False)
    share = Column(Float, nullable=True)  # percentage (0-100), None = equal

    split_group = relationship("SplitGroup", back_populates="roommates")
    roommate = relationship("Roommate", back_populates="split_group_roommates")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
