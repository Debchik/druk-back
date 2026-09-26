import asyncio
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.dao.media_asset_dao import MediaAssetDao
from app.database import async_session
from app.models.boyfriend import Boyfriend
from app.models.chat import Chat
from app.models.media_asset import MediaAsset
from app.models.message import Message
from app.models.user import User
from app.services.media_quota_service import MediaQuotaExceeded, MediaQuotaService


pytestmark = pytest.mark.skipif(
    os.getenv('RUN_DB_TESTS') != '1',
    reason='requires PostgreSQL with migrated schema',
)


async def _create_user_chat(db, *, limited: bool) -> tuple[User, Chat, Boyfriend]:
    boyfriend = Boyfriend(
        name=f'Test {uuid4()}',
        description='test',
        system_prompt='test',
    )
    db.add(boyfriend)
    await db.flush()

    user = User(
        email=f'media-quota-{uuid4()}@example.com',
        password_hash='test',
        display_name='Media quota test',
        media_trial_limited=limited,
    )
    db.add(user)
    await db.flush()

    chat = Chat(
        user_id=user.id,
        boyfriend_id=boyfriend.id,
        title='test',
        platform='web',
    )
    db.add(chat)
    await db.flush()
    return user, chat, boyfriend


async def _add_media(db, chat: Chat, message_type: str, count: int) -> None:
    for index in range(count):
        message = Message(
            chat_id=chat.id,
            role='user',
            content=f'[{message_type} {index}]',
            platform='web',
            message_type=message_type,
            status='completed',
        )
        db.add(message)
        await db.flush()
        db.add(
            MediaAsset(
                message_id=message.id,
                platform='web',
                storage_key=f'{message_type}-{index}',
                mime_type='image/jpeg' if message_type == 'image' else 'video/mp4',
                size_bytes=100,
            )
        )
    await db.commit()


def test_new_user_image_quota_rejects_sixth_upload_and_persists_reply() -> None:
    async def scenario() -> None:
        async with async_session() as db:
            user, chat, boyfriend = await _create_user_chat(db, limited=True)
            assert user.media_trial_limited is True
            await _add_media(db, chat, 'image', 5)

            with pytest.raises(MediaQuotaExceeded) as error:
                await MediaQuotaService.ensure_upload_allowed(
                    db,
                    user.id,
                    chat.id,
                    'image',
                    'web',
                    lock_user=True,
                )

            assert 'попереписываемся' in error.value.user_message
            refreshed = await db.get(User, user.id)
            assert refreshed is not None
            assert refreshed.media_limit_rejection_count == 1

            assistant = await db.scalar(
                sa.select(Message)
                .where(Message.chat_id == chat.id, Message.role == 'assistant')
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            assert assistant is not None
            assert assistant.content == error.value.user_message

            await db.delete(user)
            await db.delete(boyfriend)
            await db.commit()

    asyncio.run(scenario())


def test_new_user_video_quota_is_one_but_existing_user_is_unlimited() -> None:
    async def scenario() -> None:
        async with async_session() as db:
            limited_user, limited_chat, limited_boyfriend = await _create_user_chat(db, limited=True)
            await _add_media(db, limited_chat, 'video', 1)
            with pytest.raises(MediaQuotaExceeded):
                await MediaQuotaService.ensure_upload_allowed(
                    db,
                    limited_user.id,
                    limited_chat.id,
                    'video',
                    'web',
                    lock_user=True,
                )

            existing_user, existing_chat, existing_boyfriend = await _create_user_chat(db, limited=False)
            await _add_media(db, existing_chat, 'image', 8)
            allowed_as_trial = await MediaQuotaService.ensure_upload_allowed(
                db,
                existing_user.id,
                existing_chat.id,
                'image',
                'web',
                lock_user=True,
            )
            assert allowed_as_trial is False

            await db.delete(limited_user)
            await db.delete(existing_user)
            await db.delete(limited_boyfriend)
            await db.delete(existing_boyfriend)
            await db.commit()

    asyncio.run(scenario())
