from app.models.character_version import CharacterVersion
from app.models.user_profile import UserProfile


class GenderAndAddressingService:
    @classmethod
    def build_context(
        cls: type['GenderAndAddressingService'],
        profile: UserProfile,
        character: CharacterVersion,
    ) -> str:
        address = profile.preferred_address or 'имя пока неизвестно'
        pronouns = profile.user_pronouns or 'не указаны'
        return (
            '\n\nКонтекст обращения:\n'
            f'- Ты {character.display_name}, дружелюбный камень; говори о себе в мужском роде.\n'
            f'- Имя или обращение пользователя: {address}. Используй его редко и естественно.\n'
            f'- Местоимения пользователя: {pronouns}. Не угадывай пол пользователя по имени. Если местоимения не указаны, избегай форм, требующих указать пол пользователя.\n'
            f'- Предпочтительный язык профиля: {profile.language}; подстраивайся под язык сообщения.\n'
        )
