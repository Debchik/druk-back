from datetime import date, datetime
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class BankOperation(Base):
    __tablename__ = "bank_operations"
    __table_args__ = (
        UniqueConstraint(
            "bank",
            "operation_id",
            name="uq_bank_operations_bank_operation_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    operation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bank: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    loan_mkk: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mkk_pa: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    operation_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    transaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    pay_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_kind: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    loan: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    loan_fact: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    inner_client_temp_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    loan_core: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    loan_core_dt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loan_core_comment: Mapped[str | None] = mapped_column(Text, nullable=True) 
    loan_core_mkk: Mapped[str | None] = mapped_column(String(32), nullable=True)

    paygate_operation_id: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    
    payer_acct: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payer_bank_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    payer_inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payer_kpp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payer_bank_bik: Mapped[str | None] = mapped_column(String(16), nullable=True)

    receiver_acct: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receiver_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    receiver_bank_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    receiver_inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    receiver_kpp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    receiver_bank_bik: Mapped[str | None] = mapped_column(String(16), nullable=True)

    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payvo: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True, default="643")
    priority: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vat: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vat_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_duplicate: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=None, index=True)
    create_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    update_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
