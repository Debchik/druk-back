from app.dto.memory import DeletionRequest, FactCandidate, PersonCandidate
from app.services.memory_extraction_service import MemoryExtractionService


def test_additional_preference_is_not_replacement_by_default() -> None:
    fact = FactCandidate(
        kind='preference',
        subject='user',
        predicate='likes_drink',
        value='кофе',
        confidence=0.95,
        stability='stable',
        sensitivity='normal',
        store=True,
        reason='explicit preference',
    )
    assert fact.replace_existing is False
    assert fact.supersedes_predicates == []


def test_cross_predicate_correction_can_be_declared_explicitly() -> None:
    fact = FactCandidate(
        kind='preference',
        subject='user',
        predicate='likes_drink',
        value='капучино',
        confidence=0.99,
        stability='stable',
        sensitivity='normal',
        store=True,
        supersedes_predicates=['dislikes_drink'],
        reason='user explicitly changed the preference',
    )
    assert fact.supersedes_predicates == ['dislikes_drink']


def test_same_turn_forget_wins_over_fact_extraction() -> None:
    fact = FactCandidate(
        kind='preference',
        subject='user',
        predicate='likes_drink',
        value='фильтр-кофе',
        confidence=0.99,
        stability='stable',
        sensitivity='normal',
        store=True,
        reason='explicit preference',
    )
    deletion = DeletionRequest(
        target_text='я люблю фильтр-кофе',
        scope='fact',
        kind='preference',
        subject='user',
        predicate='likes_drink',
        value='фильтр-кофе',
    )
    assert MemoryExtractionService._fact_matches_same_turn_deletion(fact, [deletion])


def test_same_turn_forget_person_wins_over_person_extraction() -> None:
    person = PersonCandidate(
        name='Маша',
        relation_to_user='коллега',
        disambiguator='Маша с работы',
        confidence=0.95,
    )
    deletion = DeletionRequest(
        target_text='всё про Машу',
        scope='all_matching',
        person_name='Маша',
    )
    assert MemoryExtractionService._person_matches_same_turn_deletion(person, [deletion])
