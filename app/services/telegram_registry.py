from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.models.telegram_chat import TelegramChat
from app.models.telegram_user import TelegramUser
from app.repositories.telegram_registry import TelegramChatRepository, TelegramUserRepository


@dataclass(slots=True)
class TelegramIdentity:
    user: TelegramUser
    chat: TelegramChat


class TelegramRegistryService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def ensure_identity(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        chat_type: str,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        chat_title: str | None,
    ) -> TelegramIdentity:
        with self.session_factory() as session:
            user_repo = TelegramUserRepository(session)
            chat_repo = TelegramChatRepository(session)
            user = user_repo.upsert(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            chat = chat_repo.upsert(
                telegram_chat_id=telegram_chat_id,
                chat_type=chat_type,
                title=chat_title,
            )
            session.commit()
            session.refresh(user)
            session.refresh(chat)
            return TelegramIdentity(user=user, chat=chat)
