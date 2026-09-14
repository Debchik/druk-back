import logging
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.bank_operation import BankOperationCreate, BankOperationProxyItem
from app.utils.loan_contract import normalize_contract_number

logger = logging.getLogger(__name__)
_CREDIT_OPERATION_TYPES = {"Credit", "CREDIT"}
# Договор «как номер телефона + дефис»: 9+ цифр, дефис, цифры суффикса.
# Допускаем пробелы вокруг дефиса и любой не-цифровой символ перед номером
# (включая кириллические/латинские буквы и знаки № N #).
_PHONE_CONTRACT_RE = re.compile(r"(?<!\d)#?\s*(\d{9,})\s*-\s*(\d+)(?!\d)")
# Договор «как номер телефона» без дефиса: 11 цифр, начинаются с 7 или 8.
# Лукэхеды по цифрам отсекают банковские счета, ИНН и прочие более длинные
# числовые идентификаторы — матч возможен только если 11 цифр обособлены.
_BARE_PHONE_RE = re.compile(r"(?<!\d)([78]\d{10})(?!\d)")
# Короткий «старый» договор: любые обособленные 6 цифр подряд.
# Защиты от ложных матчей:
#   (?<![\d_]) — не часть более длинного числа и не комиссионный «C_NNNNNN»;
#   (?!\d)     — после 6 цифр не идёт ещё одна цифра (отсекает хвосты);
#   (?![.,]\d) — не дробная часть суммы (110508.21);
#   (?!\s*(?:руб|коп|%)) — после числа нет признака денежного значения.
_SHORT_CONTRACT_RE = re.compile(
    r"(?<![\d_])(\d{6})(?!\d|[.,]\d|\s*(?:руб|коп|%))",
    re.IGNORECASE,
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _extract_loan_from_pay_purpose(pay_purpose: str | None) -> str | None:
    if not pay_purpose:
        return None
    match = _PHONE_CONTRACT_RE.search(pay_purpose)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = _BARE_PHONE_RE.search(pay_purpose)
    if match:
        return match.group(1)
    match = _SHORT_CONTRACT_RE.search(pay_purpose)
    if match:
        return normalize_contract_number(match.group(1))
    return None


def _counterparty_to_flat(
    item: BankOperationProxyItem,
) -> BankOperationCreate:
    payer = item.payer
    receiver = item.receiver
    pay_purpose = _normalize_text(item.pay_purpose)
    loan = normalize_contract_number(
        _normalize_text(item.loan) or _extract_loan_from_pay_purpose(pay_purpose)
    )
    loan_fact = normalize_contract_number(_normalize_text(item.loan_fact))
    return BankOperationCreate(
        operation_id=item.operation_id,
        mkk_bank=item.mkk_bank,
        amount=item.amount,
        operation_at=item.operation_at,
        transaction_at=item.transaction_at,
        pay_purpose=pay_purpose,
        payer_acct=payer.acct if payer else None,
        payer_name=payer.name if payer else None,
        payer_bank_name=payer.bank_name if payer else None,
        payer_inn=payer.inn if payer else None,
        payer_kpp=payer.kpp if payer else None,
        payer_bank_bik=payer.bank_bik if payer else None,
        payer_bank_corr_acct=payer.bank_corr_acct if payer else None,
        receiver_acct=receiver.acct if receiver else None,
        receiver_name=receiver.name if receiver else None,
        receiver_bank_name=receiver.bank_name if receiver else None,
        receiver_inn=receiver.inn if receiver else None,
        receiver_kpp=receiver.kpp if receiver else None,
        receiver_bank_bik=receiver.bank_bik if receiver else None,
        receiver_bank_corr_acct=receiver.bank_corr_acct if receiver else None,
        operation_type=item.operation_type,
        loan=loan,
        loan_fact=loan_fact,
        category=item.category,
        status=item.status,
        payvo=item.payvo,
        vo=item.vo,
        description=item.description,
        document_date=item.document_date,
        document_number=item.document_number,
        currency=item.currency,
        amount_rub=item.amount_rub,
        priority=item.priority,
        delivery_kind=item.delivery_kind,
        vat=item.vat,
        vat_amount=item.vat_amount,
    )


def payload_to_creates(
    mkk_bank_fallback: str,
    payload: Any,
    *,
    only_credit: bool = True,
) -> list[BankOperationCreate]:
    """
    Распарсить JSON тела ответа прокси (список операций) в плоские записи для ORM.

    Если в элементе нет ``mkk_bank``, подставляется ``mkk_bank_fallback`` (ключ банка из URL).
    Если ``only_credit=False``, не отфильтровываются операции типа ``DEBIT`` —
    нужно для backfill, где хочется забрать всё.
    """
    if payload is None:
        return []
    if not isinstance(payload, list):
        logger.warning(
            "Ответ прокси — не список операций, пропуск: type=%s",
            type(payload).__name__,
        )
        return []

    creates: list[BankOperationCreate] = []
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            logger.warning("Пропуск элемента #%s: не объект", idx)
            continue
        data = dict(raw)
        if not data.get("mkk_bank"):
            data["mkk_bank"] = mkk_bank_fallback
        try:
            item = BankOperationProxyItem.model_validate(data)
            if only_credit and item.operation_type not in _CREDIT_OPERATION_TYPES:
                continue
            creates.append(_counterparty_to_flat(item))
        except ValidationError as e:
            logger.warning(
                "Пропуск операции #%s банк=%s: %s",
                idx,
                mkk_bank_fallback,
                e,
            )
    return creates
