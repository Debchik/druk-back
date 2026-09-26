from app.services.media_quota_service import MediaQuotaService


def test_media_limit_replies_rotate_without_llm_calls() -> None:
    replies = [MediaQuotaService.rejection_message(index) for index in range(1, 7)]
    assert len(set(replies)) == 6
    assert MediaQuotaService.rejection_message(7) == replies[0]


def test_media_limits_match_product_contract() -> None:
    assert MediaQuotaService._limit_for('image') == 5
    assert MediaQuotaService._limit_for('video') == 1
    assert MediaQuotaService._limit_for('audio') is None
    assert MediaQuotaService._limit_for('sticker') is None
