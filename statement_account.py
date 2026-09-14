"""Репозиторий счетов для выписок (данные в БД, без Pydantic-схем для вставки)."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.statement_account import StatementAccount
from app.schemas.statement_fetch import BankAccountRef


class StatementAccountRepository:
    async def list_active_grouped_by_bank(
        self,
        db: AsyncSession,
    ) -> dict[str, list[BankAccountRef]]:
        """Все активные счета, сгруппированные по ``mkk_bank``."""
        stmt = (
            select(StatementAccount)
            .where(StatementAccount.is_active.is_(True))
            .order_by(StatementAccount.mkk_bank, StatementAccount.id)
        )
        rows = (await db.scalars(stmt)).all()
        grouped: dict[str, list[BankAccountRef]] = defaultdict(list)
        for row in rows:
            grouped[row.mkk_bank].append(
                BankAccountRef(
                    client_id=row.client_id,
                    account_number=row.account_number,
                )
            )
        return dict(grouped)


statement_account_repository = StatementAccountRepository()
