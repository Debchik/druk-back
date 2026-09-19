from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeedbackRequest(BaseModel):
    reaction: Literal['like', 'dislike', 'helpful', 'not_helpful']
    reason: Optional[Literal['not_understood', 'too_cold', 'repetitive', 'unsafe', 'out_of_character']] = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    message_id: UUID
    reaction: str
    reason: Optional[str]
    created_at: datetime
    updated_at: datetime
