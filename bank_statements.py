import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, config
from app.db.pg_async_session import pg_async_session
from app.repository.sql.bank_operation import bank_operation_repository
from app.repository.sql.statement_account import statement_account_repository
from app.repository.pg.fact_arrival import fact_arrival_repository
from app.repository.pg.loan_core import loan_core_repository

from app.schemas.bank_operation import BankOperationCreate
from app.schemas.loan_from_pg import LoanFieldsFromPg
from app.schemas.statement_fetch import BankAccountRef, StatementFetchResult, StatementProxyPayload
from app.utils.bank_operation_from_proxy import payload_to_creates
from app.utils.datetime_tz import (
    today_and_yesterday_calendar_day_bounds,
    today_calendar_day_bounds,
)

logger = logging.getLogger(__name__)


class BankStatementsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings if settings is not None else config

    def _bearer_token(self) -> str:
        return (self._cfg.proxy_cfg.API_KEY or "").strip()

    def _statement_url(self, bank: str) -> str:
        base = (self._cfg.proxy_cfg.BASE_URL or "").strip().rstrip("/")
        path = (self._cfg.proxy_cfg.STATEMENT_PATH or "").strip()
        if not base:
            raise ValueError("PROXY_BASE_URL is not set")
        path_filled = path.format(bank=bank)
        if not path_filled.startswith("/"):
            path_filled = f"/{path_filled}"
        return f"{base}{path_filled}"

    async def _fetch_statements(
        self,
        accounts: dict[str, list[BankAccountRef]],
        from_dt: datetime,
        to_dt: datetime,
        session: aiohttp.ClientSession | None = None,
    ) -> list[StatementFetchResult]:
        if not accounts:
            return []

        token = self._bearer_token()
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        timeout = aiohttp.ClientTimeout(total=self._cfg.proxy_cfg.REQUEST_TIMEOUT)

        async def run(sess: aiohttp.ClientSession) -> list[StatementFetchResult]:
            results: list[StatementFetchResult] = []
            for mkk_bank, rows in accounts.items():
                url = self._statement_url(mkk_bank)
                for ref in rows:
                    body = StatementProxyPayload(
                        client_id=ref.client_id,
                        account_number=ref.account_number,
                        from_dt=from_dt,
                        to_dt=to_dt,
                    )
                    payload_dict: dict[str, Any] = {
                        "client_id": body.client_id,
                        "account_number": body.account_number,
                        "from_dt": body.from_dt.isoformat(),
                        "to_dt": body.to_dt.isoformat(),
                    }
                    logger.info(
                        "Выполняется запрос операций для банка %s client_id=%s account_number=%s "
                        "from_dt=%s to_dt=%s",
                        mkk_bank,
                        ref.client_id,
                        ref.account_number,
                        from_dt.date(),
                        to_dt.date(),
                    )
                    async with sess.post(
                        url, params=payload_dict, headers=headers
                    ) as response:
                        if response.status >= 400:
                            err_text = await response.text()
                            logger.warning(
                                "Прокси вернул ошибку, пропуск выписки: status=%s bank=%s "
                                "client_id=%s account_number=%s body=%s",
                                response.status,
                                mkk_bank,
                                ref.client_id,
                                ref.account_number,
                                err_text[:2000] if err_text else "",
                            )
                            continue
                        data = await response.json()
                        if not isinstance(data, list):
                            logger.warning(
                                "Прокси вернул не список операций, пропуск: bank=%s "
                                "client_id=%s account_number=%s type=%s",
                                mkk_bank,
                                ref.client_id,
                                ref.account_number,
                                type(data).__name__,
                            )
                            continue
                    results.append(
                        StatementFetchResult(
                            mkk_bank=mkk_bank,
                            client_id=ref.client_id,
                            account_number=ref.account_number,
                            from_dt=from_dt,
                            to_dt=to_dt,
                            payload=data,
                        )
                    )
            return results

        if session is None:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                return await run(sess)
        return await run(session)

    async def _loan_fields_by_order_ids(
        self, order_ids: Iterable[str]
    ) -> dict[str, LoanFieldsFromPg]:
        """``operation_id`` → ``loan_fact`` и ``mkk`` (fact_arrival → loan_core)."""
        op_ids = {str(oid).strip() for oid in order_ids if oid and str(oid).strip()}
        if not op_ids:
            return {}
        async with pg_async_session() as pg_db:
            inner_loan_by_order = (
                await fact_arrival_repository.get_inner_loan_ids_by_order_ids(
                    pg_db, op_ids
                )
            )
            inner_loan_ids = set(inner_loan_by_order.values())
            loan_by_inner_id: dict[int, tuple[str, str | None]] = {}
            if inner_loan_ids:
                loan_by_inner_id = (
                    await loan_core_repository.get_loan_fields_by_inner_loan_ids(
                        pg_db, inner_loan_ids
                    )
                )
        out: dict[str, LoanFieldsFromPg] = {}
        for order_id in op_ids:
            inner_loan_id = inner_loan_by_order.get(order_id)
            if not inner_loan_id:
                continue
            fields = loan_by_inner_id.get(inner_loan_id)
            if not fields:
                continue
            loan_num, mkk = fields
            out[order_id] = LoanFieldsFromPg(loan_fact=loan_num, mkk=mkk)
        return out

    async def update_null_loan_fact_for_today_and_yesterday(
        self, db: AsyncSession
    ) -> dict[str, int]:
        """Обновить ``loan_fact`` (``IS NULL``) за вчера и сегодня по ``operation_id``."""
        from_dt, to_dt = today_and_yesterday_calendar_day_bounds(self._cfg.app_cfg.TZ)
        rows = await bank_operation_repository.list_with_null_loan_fact_in_range(
            db, from_dt, to_dt
        )
        if not rows:
            logger.info(
                "Нет операций за вчера/сегодня с loan_fact IS NULL (%s — %s)",
                from_dt.date(),
                to_dt.date(),
            )
            return {
                "candidates": 0,
                "updated": 0,
                "no_match": 0,
            }

        loan_by_order = await self._loan_fields_by_order_ids(
            r.operation_id for r in rows if r.operation_id
        )
        updated = 0
        no_match = 0
        for row in rows:
            oid = (row.operation_id or "").strip()
            fields = loan_by_order.get(oid) if oid else None
            if not fields:
                no_match += 1
                continue
            mkk = fields.mkk if fields.mkk and not (row.mkk or "").strip() else None
            await bank_operation_repository.set_loan_fields(
                db,
                row.id,
                loan_fact=fields.loan_fact,
                mkk=mkk,
            )
            updated += 1

        await db.commit()
        stats = {
            "candidates": len(rows),
            "updated": updated,
            "no_match": no_match,
        }
        logger.info(
            "Обновление loan_fact за вчера/сегодня (%s — %s): %s",
            from_dt.date(),
            to_dt.date(),
            stats,
        )
        return stats

    async def fetch_all(
        self,
        db: AsyncSession,
        session: aiohttp.ClientSession | None = None,
    ) -> list[StatementFetchResult]:
        accounts = await statement_account_repository.list_active_grouped_by_bank(db)
        if not accounts:
            logger.warning(
                "Таблица statement_accounts пуста или нет активных записей; нечего запрашивать",
            )
            return []

        tz = self._cfg.app_cfg.TZ
        from_dt, to_dt = today_calendar_day_bounds(tz)
        return await self._fetch_statements(accounts, from_dt, to_dt, session=session)

    async def _save_statement_results(
        self,
        db: AsyncSession,
        results: list[StatementFetchResult],
    ) -> dict[str, int]:
        creates: list[BankOperationCreate | dict[str, Any]] = []
        for res in results:
            creates.extend(payload_to_creates(res.mkk_bank, res.payload))

        after_credit = len(creates)
        seen_in_batch: set[tuple[str, str]] = set()
        deduped: list[BankOperationCreate | dict[str, Any]] = []
        for c in creates:
            if isinstance(c, BankOperationCreate) and c.operation_id:
                k = (str(c.mkk_bank), c.operation_id)
                if k in seen_in_batch:
                    continue
                seen_in_batch.add(k)
            deduped.append(c)
        creates = deduped
        skipped_in_batch = after_credit - len(creates)

        pair_keys: list[tuple[str, str]] = []
        for c in creates:
            if isinstance(c, BankOperationCreate) and c.operation_id:
                pair_keys.append((str(c.mkk_bank), c.operation_id))
        skipped_already_in_db = 0
        if pair_keys:
            already = await bank_operation_repository.pairs_that_exist(db, pair_keys)
            if already:
                before = len(creates)
                creates = [
                    c
                    for c in creates
                    if not isinstance(c, BankOperationCreate)
                    or (str(c.mkk_bank), c.operation_id) not in already
                ]
                skipped_already_in_db = before - len(creates)
                logger.info(
                    "Сверка с БД: пропущено операций, уже есть (банк+operation_id): %s из %s",
                    skipped_already_in_db,
                    before,
                )

        rows_inserted = len(creates)
        updated = 0
        if creates:
            op_ids = [
                c.operation_id
                for c in creates
                if isinstance(c, BankOperationCreate) and c.operation_id
            ]
            loan_by_order = await self._loan_fields_by_order_ids(op_ids)
            for create in creates:
                if not isinstance(create, BankOperationCreate):
                    continue
                oid = (create.operation_id or "").strip()
                fields = loan_by_order.get(oid) if oid else None
                if not fields:
                    continue
                create.loan_fact = fields.loan_fact
                if not (create.loan or "").strip():
                    create.loan = fields.loan_fact
                if fields.mkk:
                    create.mkk = fields.mkk
                updated += 1

        if creates:
            await bank_operation_repository.bulk_create(db, creates)
        logger.info(
            "Сохранение: вставлено %s; loan_fact/mkk из Postgres: %s",
            rows_inserted,
            updated,
        )
        return {
            "after_credit": after_credit,
            "skipped_in_batch": skipped_in_batch,
            "skipped_already_in_db": skipped_already_in_db,
            "rows_inserted": rows_inserted,
            "loan_fact_from_pg": updated,
        }

    async def fetch_all_and_save(
        self,
        db: AsyncSession,
        session: aiohttp.ClientSession | None = None,
    ) -> list[StatementFetchResult]:
        results = await self.fetch_all(db, session=session)
        await self._save_statement_results(db, results)
        return results


bank_statements_service = BankStatementsService()
