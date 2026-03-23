from aiogram import Router
from aiogram.types import CallbackQuery

from app.bot.context import get_bot_services
from app.bot.keyboards import status_back_keyboard
from app.repositories.deliveries import NotificationDeliveryRepository
from app.repositories.runs import RunRepository
from app.repositories.sources import SourceRepository
from app.repositories.telegram_registry import TelegramChatRepository

router = Router()


@router.callback_query(lambda callback: callback.data == "menu:status")
async def bot_status(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return

    services = get_bot_services()
    profiles = services.monitor_profiles.list_for_chat(callback.message.chat.id)
    with services.session_factory() as session:
        chat = TelegramChatRepository(session).get_by_telegram_id(callback.message.chat.id)
        deliveries = (
            NotificationDeliveryRepository(session).list_by_chat(chat.id, limit=5) if chat else []
        )
        recent_run = RunRepository(session).list_recent(limit=1)
        recent_run = recent_run[0] if recent_run else None
        sources = SourceRepository(session).list_sources()

    lines = [
        "Parset Monitor status",
        f"Active monitors in this chat: {len([profile for profile in profiles if profile.is_active])}",
        f"Total monitors in this chat: {len(profiles)}",
        f"Supported sources: {len(sources)}",
    ]
    if recent_run:
        lines.append(
            f"Last run: #{recent_run.id} ({recent_run.status}) "
            f"items={recent_run.items_parsed} events={recent_run.events_count}"
        )
    if deliveries:
        lines.append("Recent deliveries:")
        for delivery in deliveries[:3]:
            lines.append(f"- {delivery.delivery_type}: {delivery.status}")

    await callback.message.edit_text("\n".join(lines), reply_markup=status_back_keyboard())
