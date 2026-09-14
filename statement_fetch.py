from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BankAccountRef(BaseModel):
    client_id: str
    account_number: str


class StatementProxyPayload(BaseModel):
    client_id: str
    account_number: str
    from_dt: datetime
    to_dt: datetime


class StatementFetchResult(BaseModel):
    mkk_bank: str
    client_id: str
    account_number: str
    from_dt: datetime
    to_dt: datetime
    payload: Any
