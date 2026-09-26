from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.chat_dao import ChatDao
from app.dao.media_asset_dao import MediaAssetDao
from app.dao.message_dao import MessageDao
from app.dao.user_dao import UserDao
from app.logging import logger
from settings import config


class MediaQuotaExceeded(Exception):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class MediaQuotaService:
    _replies = (
        'Я уже немного устал смотреть фотографии и ролики. Давай пока просто попереписываемся.',
        'Кажется, моим глазам нужен перерыв от картинок. Но поболтать с тобой я всё ещё готов.',
        'С фотографиями я пока немного выдохся. Пиши текстом - я здесь.',
        'Я уже насмотрелся картинок и видео, так что давай пока без новых файлов. Переписываться могу сколько угодно.',
        'Давай дадим моим виртуальным глазам передышку от фотографий. А вот поговорить я совсем не против.',
        'Кажется, с визуальным контентом мне уже хватит. Но сообщения присылай - с ними я никуда не делся.',
    )

    @classmethod
    def rejection_message(cls: type['MediaQuotaService'], rejection_count: int) -> str:
        index = max(1, rejection_count) - 1
        return cls._replies[index % len(cls._replies)]

    @classmethod
    def _limit_for(cls: type['MediaQuotaService'], message_type: str) -> int | None:
        if message_type == 'image':
            return config.media.new_user_image_limit
        if message_type == 'video':
            return config.media.new_user_video_limit
        return None

    @classmethod
    async def ensure_upload_allowed(
        cls: type['MediaQuotaService'],
        db: AsyncSession,
        user_id: UUID,
        chat_id: UUID,
        message_type: str,
        platform: str,
        *,
        lock_user: bool,
    ) -> bool:
        limit = cls._limit_for(message_type)
        if limit is None:
            return False

        if await ChatDao.get(db, user_id, chat_id) is None:
            raise LookupError('Chat not found')

        user = (
            await UserDao.get_by_id_for_update(db, user_id)
            if lock_user
            else await UserDao.get_by_id(db, user_id)
        )
        if user is None:
            raise LookupError('User not found')
        if not user.media_trial_limited:
            return False

        used = await MediaAssetDao.count_for_user_by_type(db, user_id, message_type)
        if used < limit:
            return True

        rejection_count = await UserDao.increment_media_limit_rejection_count(db, user_id)
        reply = cls.rejection_message(rejection_count)
        await MessageDao.create(
            db,
            chat_id,
            'assistant',
            reply,
            platform=platform,
            message_type='text',
            status='completed',
        )
        await ChatDao.touch(db, chat_id)
        await db.commit()
        logger.info(
            'media_trial_quota_rejected user_id=%s chat_id=%s type=%s used=%s limit=%s rejection=%s',
            user_id,
            chat_id,
            message_type,
            used,
            limit,
            rejection_count,
        )
        raise MediaQuotaExceeded(reply)
