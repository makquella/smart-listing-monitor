from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.telegram_chat import TelegramChat
from app.models.telegram_user import TelegramUser


class TelegramUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_telegram_id(self, telegram_user_id: int) -> TelegramUser | None:
        statement = select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        return self.session.scalar(statement)

    def upsert(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> TelegramUser:
        now = utcnow()
        user = self.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = TelegramUser(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                created_at=now,
                updated_at=now,
            )
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.updated_at = now
        self.session.add(user)
        self.session.flush()
        return user

    def list_recent(self, limit: int = 50) -> list[TelegramUser]:
        statement = select(TelegramUser).order_by(TelegramUser.updated_at.desc()).limit(limit)
        return list(self.session.scalars(statement))


class TelegramChatRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_telegram_id(self, telegram_chat_id: int) -> TelegramChat | None:
        statement = select(TelegramChat).where(TelegramChat.telegram_chat_id == telegram_chat_id)
        return self.session.scalar(statement)

    def upsert(
        self,
        *,
        telegram_chat_id: int,
        chat_type: str,
        title: str | None,
    ) -> TelegramChat:
        now = utcnow()
        chat = self.get_by_telegram_id(telegram_chat_id)
        if chat is None:
            chat = TelegramChat(
                telegram_chat_id=telegram_chat_id,
                chat_type=chat_type,
                title=title,
                created_at=now,
                updated_at=now,
            )
        else:
            chat.chat_type = chat_type
            chat.title = title
            chat.updated_at = now
        self.session.add(chat)
        self.session.flush()
        return chat

    def list_recent(self, limit: int = 50) -> list[TelegramChat]:
        statement = select(TelegramChat).order_by(TelegramChat.updated_at.desc()).limit(limit)
        return list(self.session.scalars(statement))
