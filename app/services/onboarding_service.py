from datetime import datetime, timezone
import re
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.onboarding_dao import OnboardingDao
from app.dao.user_dao import UserDao
from app.dao.user_profile_dao import UserProfileDao
from app.dto.onboarding import OnboardingResponse
from app.dto.user import UserProfileResponse
from app.logging import logger
from app.models.onboarding_state import OnboardingState
from app.models.user_profile import UserProfile


class OnboardingService:
    _question = 'Как тебя зовут?'

    @classmethod
    async def start(cls: type['OnboardingService'], db: AsyncSession, user_id: UUID) -> OnboardingResponse:
        profile = await UserProfileDao.ensure(db, user_id)
        state = await OnboardingDao.ensure(db, user_id)
        if profile.preferred_address:
            if state.status != 'completed':
                await cls._complete(db, state, profile.preferred_address)
        elif state.status == 'completed' or state.step != 'preferred_address':
            state.status = 'in_progress'
            state.step = 'preferred_address'
            state.completed_at = None
        await db.commit()
        logger.info('onboarding_started user_id=%s step=%s', user_id, state.step)
        return cls._response(profile, state)

    @classmethod
    async def answer(cls: type['OnboardingService'], db: AsyncSession, user_id: UUID, answer: str) -> OnboardingResponse:
        profile = await UserProfileDao.ensure(db, user_id)
        state = await OnboardingDao.ensure(db, user_id)
        if state.status == 'completed' and profile.preferred_address:
            return cls._response(profile, state)
        name = ' '.join(answer.strip().split())
        name = re.sub(r'(?iu)^(?:привет[,!]?\s+)?(?:меня зовут|мо[её] имя|я)\s+', '', name).strip(' .,!?')
        if not name or len(name) > 60 or len(name.split()) > 4 or name.startswith('/'):
            raise ValueError('Напиши, пожалуйста, короткое имя или обращение — до четырёх слов.')
        profile.preferred_address = name
        profile.companion_role = 'companion'
        profile.companion_gender = 'male'
        user = await UserDao.get_by_id(db, user_id)
        if user is not None:
            user.display_name = name
        await cls._complete(db, state, name)
        await db.commit()
        await db.refresh(profile)
        await db.refresh(state)
        logger.info('onboarding_name_saved user_id=%s', user_id)
        return cls._response(profile, state)

    @classmethod
    async def _complete(cls: type['OnboardingService'], db: AsyncSession, state: OnboardingState, name: str) -> None:
        answers = dict(state.answers)
        answers['preferred_address'] = name
        await OnboardingDao.advance(
            db, state, 'completed', 'completed', answers,
            datetime.now(timezone.utc).replace(tzinfo=None),
        )

    @classmethod
    async def update_profile(
        cls: type['OnboardingService'],
        db: AsyncSession,
        user_id: UUID,
        companion_role: Optional[str],
        companion_gender: Optional[str],
        user_gender: Optional[str],
        user_pronouns: Optional[str],
        preferred_address: Optional[str],
        language: Optional[str],
        timezone: Optional[str],
    ) -> UserProfileResponse:
        if companion_role not in (None, 'companion') or companion_gender not in (None, 'male'):
            raise ValueError('Друк — единственный доступный спутник.')
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except ZoneInfoNotFoundError as error:
                raise ValueError('Неизвестный часовой пояс') from error
        if preferred_address is not None:
            preferred_address = ' '.join(preferred_address.strip().split())
            if not preferred_address or len(preferred_address) > 60:
                raise ValueError('Напиши короткое имя или обращение.')
        profile = await UserProfileDao.ensure(db, user_id)
        await UserProfileDao.update_preferences(
            db, profile, 'companion', 'male', user_gender, user_pronouns,
            preferred_address, language, timezone,
        )
        if preferred_address is not None:
            state = await OnboardingDao.ensure(db, user_id)
            await cls._complete(db, state, preferred_address)
            user = await UserDao.get_by_id(db, user_id)
            if user is not None:
                user.display_name = preferred_address
        await db.commit()
        await db.refresh(profile)
        logger.info('user_profile_updated user_id=%s', user_id)
        return UserProfileResponse.model_validate(profile)

    @classmethod
    def _response(cls: type['OnboardingService'], profile: UserProfile, state: OnboardingState) -> OnboardingResponse:
        return OnboardingResponse(
            status=state.status,
            step=state.step,
            question=cls._question if state.status != 'completed' else None,
            profile=UserProfileResponse.model_validate(profile),
        )
