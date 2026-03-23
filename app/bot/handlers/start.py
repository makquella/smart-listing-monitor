from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.context import get_bot_services
from app.bot.keyboards import main_menu_keyboard, run_source_keyboard
from app.repositories.sources import SourceRepository


router = Router()


def _source_choices() -> list[tuple[int, str]]:
    services = get_bot_services()
    with services.session_factory() as session:
        return [(source.id, source.name) for source in SourceRepository(session).list_sources() if source.is_active]


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    await message.answer(
        "Parset Monitor control plane.\nChoose an action:",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(lambda callback: callback.data == "menu:home")
async def menu_home(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Parset Monitor control plane.\nChoose an action:",
            reply_markup=main_menu_keyboard(),
        )


@router.callback_query(lambda callback: callback.data == "menu:run_check")
async def run_check_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Choose a supported source to run now:",
            reply_markup=run_source_keyboard(_source_choices()),
        )
