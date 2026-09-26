from typing import List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.boyfriend import Boyfriend
from app.models.character_version import CharacterVersion
from app.models.chat import Chat
from app.models.user_profile import UserProfile
from app.services.druk_persona import DRUK_NAME, DRUK_DESCRIPTION, DRUK_SYSTEM_PROMPT


class BoyfriendDao:
    @classmethod
    async def list_active(cls: type['BoyfriendDao'], db: AsyncSession) -> List[Boyfriend]:
        result = await db.scalars(sa.select(Boyfriend).where(Boyfriend.is_active.is_(True)).order_by(Boyfriend.name))
        return list(result)

    @classmethod
    async def get_active(cls: type['BoyfriendDao'], db: AsyncSession, boyfriend_id: UUID) -> Optional[Boyfriend]:
        return await db.scalar(sa.select(Boyfriend).where(Boyfriend.id == boyfriend_id, Boyfriend.is_active.is_(True)))

    @classmethod
    async def get_first_active(cls: type['BoyfriendDao'], db: AsyncSession) -> Optional[Boyfriend]:
        return await db.scalar(sa.select(Boyfriend).where(Boyfriend.is_active.is_(True)).order_by(Boyfriend.created_at).limit(1))

    @classmethod
    async def get_any(cls: type['BoyfriendDao'], db: AsyncSession) -> Optional[Boyfriend]:
        return await db.scalar(sa.select(Boyfriend).limit(1))

    @classmethod
    async def create(cls: type['BoyfriendDao'], db: AsyncSession, name: str, description: str, system_prompt: str) -> Boyfriend:
        boyfriend = Boyfriend(name=name, description=description, system_prompt=system_prompt)
        db.add(boyfriend)
        await db.flush()
        return boyfriend

    @classmethod
    async def ensure_druk(cls: type['BoyfriendDao'], db: AsyncSession) -> Boyfriend:
        """Make the one public companion Druk, including pre-existing test chats."""
        companion = await db.scalar(
            sa.select(Boyfriend).where(Boyfriend.name == DRUK_NAME).order_by(Boyfriend.created_at).limit(1)
        )
        if companion is None:
            companion = await cls.get_any(db)
        if companion is None:
            companion = await cls.create(db, DRUK_NAME, DRUK_DESCRIPTION, DRUK_SYSTEM_PROMPT)
        companion.name = DRUK_NAME
        companion.description = DRUK_DESCRIPTION
        companion.system_prompt = DRUK_SYSTEM_PROMPT
        companion.is_active = True
        await db.execute(sa.update(Boyfriend).where(Boyfriend.id != companion.id).values(is_active=False))
        await db.execute(sa.update(Chat).where(Chat.boyfriend_id != companion.id).values(boyfriend_id=companion.id))
        await db.execute(sa.update(UserProfile).values(companion_role='companion', companion_gender='male'))

        character = await db.scalar(
            sa.select(CharacterVersion)
            .where(CharacterVersion.boyfriend_id == companion.id)
            .order_by(CharacterVersion.version.desc())
            .limit(1)
        )
        await db.execute(
            sa.update(CharacterVersion)
            .where(CharacterVersion.boyfriend_id == companion.id)
            .values(is_active=False)
        )
        if character is None:
            character = CharacterVersion(boyfriend_id=companion.id, version=1)
            db.add(character)
        character.display_name = DRUK_NAME
        character.style = 'Тёплый, любознательный, чуткий и живой; без навязчивости.'
        character.boundaries = 'Без флирта, романтической роли и эмоциональной зависимости.'
        character.system_prompt = DRUK_SYSTEM_PROMPT
        character.role_type = 'companion'
        character.gender = 'male'
        character.pronouns = 'он/его'
        character.prompt_version = 'druk-enfp-v1'
        character.is_active = True
        await db.commit()
        return companion
