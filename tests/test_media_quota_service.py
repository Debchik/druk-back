import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.dao.media_asset_dao import MediaAssetDao
from app.services.local_storage_service import LocalStorageService
from app.services.media_ai_service import GeminiMultimodalService
from app.services.media_probe_service import MediaProbeService
from app.services.media_quota_service import MediaQuotaService
from app.services.media_service import MediaService


def test_media_limit_replies_rotate_without_llm_calls() -> None:
    replies = [MediaQuotaService.rejection_message(index) for index in range(1, 7)]
    assert len(set(replies)) == 6
    assert MediaQuotaService.rejection_message(7) == replies[0]


def test_media_limits_match_product_contract() -> None:
    assert MediaQuotaService._limit_for('image') == 5
    assert MediaQuotaService._limit_for('video') == 1
    assert MediaQuotaService._limit_for('audio') is None
    assert MediaQuotaService._limit_for('sticker') is None


def test_long_trial_video_processes_only_first_30_seconds(monkeypatch) -> None:
    asset = SimpleNamespace(
        storage_key='video.mp4',
        mime_type='video/mp4',
        metadata_json={'preview_limit_seconds': 30, 'trial_limited': True},
        duration_seconds=None,
    )
    message = SimpleNamespace(content='')

    monkeypatch.setattr(
        MediaService,
        '_get_asset_message',
        AsyncMock(return_value=(asset, message)),
    )
    monkeypatch.setattr(MediaAssetDao, 'mark_processing', AsyncMock(return_value=asset))
    monkeypatch.setattr(LocalStorageService, 'get_path', lambda _: Path('/tmp/video.mp4'))
    monkeypatch.setattr(MediaProbeService, 'duration_seconds', AsyncMock(return_value=74))
    extract = AsyncMock(return_value=([b'frame'], None))
    monkeypatch.setattr(MediaService, '_extract_video_media', extract)
    monkeypatch.setattr(
        GeminiMultimodalService,
        'describe_video_frames',
        AsyncMock(return_value='Описание первых секунд'),
    )
    monkeypatch.setattr(MediaAssetDao, 'mark_completed', AsyncMock(return_value=asset))
    enqueue = AsyncMock()
    monkeypatch.setattr(MediaService, '_enqueue_message', enqueue)

    asyncio.run(MediaService.process_video(SimpleNamespace(), SimpleNamespace()))

    extract.assert_awaited_once_with(Path('/tmp/video.mp4'), 30)
    assert asset.metadata_json['truncated'] is True
    assert asset.metadata_json['processed_duration_seconds'] == 30
    assert 'только первые 30 секунд' in message.content
    enqueue.assert_awaited_once()
