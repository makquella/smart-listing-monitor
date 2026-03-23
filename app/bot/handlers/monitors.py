import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.context import get_bot_services
from app.bot.keyboards import (
    main_menu_keyboard,
    monitor_action_keyboard,
    notifications_menu_keyboard,
    priority_mode_keyboard,
    skip_keyboard,
    source_keyboard,
    status_back_keyboard,
    yes_no_keyboard,
)
from app.bot.states import CreateMonitorStates
from app.repositories.sources import SourceRepository
from app.services.monitor_runner import RunLockedError
from app.services.types import MonitorProfileCreate


router = Router()


def _source_choices() -> list[tuple[int, str]]:
    services = get_bot_services()
    with services.session_factory() as session:
        return [(source.id, source.name) for source in SourceRepository(session).list_sources()]


def _chat_title(message: Message | None) -> str | None:
    if message is None or message.chat is None:
        return None
    return getattr(message.chat, "title", None) or getattr(message.chat, "full_name", None)


def _ensure_message_identity(message: Message) -> dict:
    user = message.from_user
    if user is None:
        raise RuntimeError("Telegram message has no user context")
    return {
        "telegram_user_external_id": user.id,
        "telegram_chat_external_id": message.chat.id,
        "chat_type": message.chat.type,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "chat_title": _chat_title(message),
    }


def _build_monitor_summary(profile) -> str:
    filters = []
    if profile.category:
        filters.append(f"category={profile.category}")
    if profile.min_price is not None:
        filters.append(f"min={profile.min_price:.2f}")
    if profile.max_price is not None:
        filters.append(f"max={profile.max_price:.2f}")
    if profile.include_keywords_json:
        filters.append(f"include={', '.join(profile.include_keywords_json)}")
    if profile.exclude_keywords_json:
        filters.append(f"exclude={', '.join(profile.exclude_keywords_json)}")
    if not filters:
        filters.append("no additional filters")
    return (
        f"{profile.name}\n"
        f"Status: {'active' if profile.is_active else 'paused'}\n"
        f"Priority mode: {profile.priority_mode}\n"
        f"Instant alerts: {'on' if profile.instant_alerts_enabled else 'off'} | "
        f"Digest: {'on' if profile.digest_enabled else 'off'}\n"
        f"Filters: {'; '.join(filters)}"
    )


def _parse_optional_price(raw: str) -> float | None:
    normalized = raw.strip().lower()
    if normalized in {"", "skip"}:
        return None
    return float(normalized)


@router.callback_query(lambda callback: callback.data == "menu:create_monitor")
async def begin_create_monitor(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            "Choose a supported source for the monitor:",
            reply_markup=source_keyboard(_source_choices()),
        )
    await state.set_state(CreateMonitorStates.source)


@router.callback_query(CreateMonitorStates.source, F.data.startswith("create:source:"))
async def choose_source(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    source_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    parser = None
    source_name = "Source"
    with services.session_factory() as session:
        source = SourceRepository(session).get(source_id)
        if source is not None:
            source_name = source.name
            parser = services.runner.parsers.get(source.parser_key)
    categories = parser.supported_categories() if parser else []
    preview = ", ".join(categories[:10]) if categories else "No predefined categories"
    await state.update_data(source_id=source_id, source_name=source_name)
    if callback.message:
        await callback.message.edit_text(
            f"Source selected: {source_name}\n"
            f"Send a category name or skip.\n"
            f"Examples: {preview}",
            reply_markup=skip_keyboard("create:skip:category"),
        )
    await state.set_state(CreateMonitorStates.category)


@router.callback_query(CreateMonitorStates.category, F.data == "create:skip:category")
async def skip_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(category=None)
    if callback.message:
        await callback.message.edit_text(
            "Send minimum price, or type `skip`.",
            reply_markup=skip_keyboard("create:skip:min_price"),
        )
    await state.set_state(CreateMonitorStates.min_price)


@router.message(CreateMonitorStates.category)
async def capture_category(message: Message, state: FSMContext) -> None:
    category = message.text.strip() if message.text else ""
    await state.update_data(category=category or None, **_ensure_message_identity(message))
    await message.answer(
        "Send minimum price, or type `skip`.",
        reply_markup=skip_keyboard("create:skip:min_price"),
    )
    await state.set_state(CreateMonitorStates.min_price)


@router.callback_query(CreateMonitorStates.min_price, F.data == "create:skip:min_price")
async def skip_min_price(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(min_price=None)
    if callback.message:
        await callback.message.edit_text(
            "Send maximum price, or type `skip`.",
            reply_markup=skip_keyboard("create:skip:max_price"),
        )
    await state.set_state(CreateMonitorStates.max_price)


@router.message(CreateMonitorStates.min_price)
async def capture_min_price(message: Message, state: FSMContext) -> None:
    try:
        value = _parse_optional_price(message.text or "")
    except ValueError:
        await message.answer("Minimum price should be a number like `25` or `19.99`, or type `skip`.")
        return
    await state.update_data(min_price=value, **_ensure_message_identity(message))
    await message.answer(
        "Send maximum price, or type `skip`.",
        reply_markup=skip_keyboard("create:skip:max_price"),
    )
    await state.set_state(CreateMonitorStates.max_price)


@router.callback_query(CreateMonitorStates.max_price, F.data == "create:skip:max_price")
async def skip_max_price(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(max_price=None)
    if callback.message:
        await callback.message.edit_text(
            "Send include keywords separated by commas, or type `skip`.",
            reply_markup=skip_keyboard("create:skip:include_keywords"),
        )
    await state.set_state(CreateMonitorStates.include_keywords)


@router.message(CreateMonitorStates.max_price)
async def capture_max_price(message: Message, state: FSMContext) -> None:
    try:
        value = _parse_optional_price(message.text or "")
    except ValueError:
        await message.answer("Maximum price should be a number like `30` or `49.50`, or type `skip`.")
        return
    await state.update_data(max_price=value, **_ensure_message_identity(message))
    await message.answer(
        "Send include keywords separated by commas, or type `skip`.",
        reply_markup=skip_keyboard("create:skip:include_keywords"),
    )
    await state.set_state(CreateMonitorStates.include_keywords)


@router.callback_query(CreateMonitorStates.include_keywords, F.data == "create:skip:include_keywords")
async def skip_include_keywords(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(include_keywords=[])
    if callback.message:
        await callback.message.edit_text(
            "Send exclude keywords separated by commas, or type `skip`.",
            reply_markup=skip_keyboard("create:skip:exclude_keywords"),
        )
    await state.set_state(CreateMonitorStates.exclude_keywords)


@router.message(CreateMonitorStates.include_keywords)
async def capture_include_keywords(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    include_keywords = [] if raw.lower() == "skip" or not raw else raw.split(",")
    await state.update_data(include_keywords=include_keywords, **_ensure_message_identity(message))
    await message.answer(
        "Send exclude keywords separated by commas, or type `skip`.",
        reply_markup=skip_keyboard("create:skip:exclude_keywords"),
    )
    await state.set_state(CreateMonitorStates.exclude_keywords)


@router.callback_query(CreateMonitorStates.exclude_keywords, F.data == "create:skip:exclude_keywords")
async def skip_exclude_keywords(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(exclude_keywords=[])
    if callback.message:
        await callback.message.edit_text(
            "Enable instant alerts?",
            reply_markup=yes_no_keyboard(yes="create:instant:yes", no="create:instant:no"),
        )
    await state.set_state(CreateMonitorStates.instant_alerts)


@router.message(CreateMonitorStates.exclude_keywords)
async def capture_exclude_keywords(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    exclude_keywords = [] if raw.lower() == "skip" or not raw else raw.split(",")
    await state.update_data(exclude_keywords=exclude_keywords, **_ensure_message_identity(message))
    await message.answer(
        "Enable instant alerts?",
        reply_markup=yes_no_keyboard(yes="create:instant:yes", no="create:instant:no"),
    )
    await state.set_state(CreateMonitorStates.instant_alerts)


@router.callback_query(CreateMonitorStates.instant_alerts, F.data.startswith("create:instant:"))
async def capture_instant_alerts(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    enabled = callback.data.endswith("yes")
    await state.update_data(instant_alerts_enabled=enabled)
    if callback.message:
        await callback.message.edit_text(
            "Enable digest delivery?",
            reply_markup=yes_no_keyboard(yes="create:digest:yes", no="create:digest:no"),
        )
    await state.set_state(CreateMonitorStates.digest)


@router.callback_query(CreateMonitorStates.digest, F.data.startswith("create:digest:"))
async def capture_digest(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    enabled = callback.data.endswith("yes")
    await state.update_data(digest_enabled=enabled)
    if callback.message:
        await callback.message.edit_text(
            "Choose priority mode for notifications:",
            reply_markup=priority_mode_keyboard(),
        )
    await state.set_state(CreateMonitorStates.priority_mode)


@router.callback_query(CreateMonitorStates.priority_mode, F.data.startswith("create:priority:"))
async def capture_priority_mode(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    priority_mode = callback.data.rsplit(":", 1)[-1]
    await state.update_data(priority_mode=priority_mode)
    if callback.message:
        await callback.message.edit_text(
            "Send monitor name, or type `skip` for an automatic name.",
            reply_markup=skip_keyboard("create:skip:name"),
        )
    await state.set_state(CreateMonitorStates.name)


@router.callback_query(CreateMonitorStates.name, F.data == "create:skip:name")
async def skip_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(name=None)
    if callback.message:
        await _finalize_monitor(callback.message, state)


@router.message(CreateMonitorStates.name)
async def capture_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    await state.update_data(name=None if name.lower() == "skip" else name, **_ensure_message_identity(message))
    await _finalize_monitor(message, state)


async def _finalize_monitor(message: Message, state: FSMContext) -> None:
    services = get_bot_services()
    payload = await state.get_data()
    generated_name = payload.get("name") or _generate_monitor_name(payload)
    try:
        profile = services.monitor_profiles.create(
            MonitorProfileCreate(
                telegram_user_external_id=payload["telegram_user_external_id"],
                telegram_chat_external_id=payload["telegram_chat_external_id"],
                chat_type=payload["chat_type"],
                username=payload.get("username"),
                first_name=payload.get("first_name"),
                last_name=payload.get("last_name"),
                chat_title=payload.get("chat_title"),
                source_id=payload["source_id"],
                name=generated_name,
                category=payload.get("category"),
                min_price=payload.get("min_price"),
                max_price=payload.get("max_price"),
                include_keywords=payload.get("include_keywords", []),
                exclude_keywords=payload.get("exclude_keywords", []),
                instant_alerts_enabled=payload.get("instant_alerts_enabled", True),
                digest_enabled=payload.get("digest_enabled", True),
                priority_mode=payload.get("priority_mode", "high_medium"),
            )
        )
    except ValueError as exc:
        await message.answer(
            f"Monitor could not be created: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"Monitor created.\n\n{_build_monitor_summary(profile)}",
        reply_markup=monitor_action_keyboard(profile.id, is_active=profile.is_active),
    )


def _generate_monitor_name(payload: dict) -> str:
    name_parts = [payload.get("source_name", "Monitor")]
    if payload.get("category"):
        name_parts.append(str(payload["category"]))
    if payload.get("max_price") is not None:
        name_parts.append(f"<= {payload['max_price']}")
    include_keywords = payload.get("include_keywords") or []
    if include_keywords:
        name_parts.append(f"kw: {include_keywords[0].strip()}")
    return " / ".join(name_parts)


@router.callback_query(lambda callback: callback.data == "menu:my_monitors")
async def my_monitors(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    services = get_bot_services()
    profiles = services.monitor_profiles.list_for_chat(callback.message.chat.id)
    if not profiles:
        await callback.message.edit_text(
            "No monitors configured in this chat yet.",
            reply_markup=status_back_keyboard(),
        )
        return
    lines = ["Monitors in this chat:"]
    for profile in profiles:
        lines.append(f"- #{profile.id} {profile.name} ({'active' if profile.is_active else 'paused'})")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=notifications_menu_keyboard([profile.id for profile in profiles]),
    )


@router.callback_query(lambda callback: callback.data == "menu:notifications")
async def notifications_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    services = get_bot_services()
    profiles = services.monitor_profiles.list_for_chat(callback.message.chat.id)
    if not profiles:
        await callback.message.edit_text(
            "No monitor notification preferences exist for this chat yet.",
            reply_markup=status_back_keyboard(),
        )
        return
    await callback.message.edit_text(
        "Choose a monitor to inspect or toggle notification settings:",
        reply_markup=notifications_menu_keyboard([profile.id for profile in profiles]),
    )


@router.callback_query(F.data.startswith("monitor:open:"))
async def open_monitor(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    profile = services.monitor_profiles.get(monitor_id)
    if profile is None:
        await callback.message.edit_text("Monitor not found.", reply_markup=status_back_keyboard())
        return
    await callback.message.edit_text(
        _build_monitor_summary(profile),
        reply_markup=monitor_action_keyboard(profile.id, is_active=profile.is_active),
    )


@router.callback_query(F.data.startswith("monitor:toggle:"))
async def toggle_monitor(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    profile = services.monitor_profiles.get(monitor_id)
    if profile is None:
        await callback.message.edit_text("Monitor not found.", reply_markup=status_back_keyboard())
        return
    updated = services.monitor_profiles.pause(monitor_id) if profile.is_active else services.monitor_profiles.resume(monitor_id)
    await callback.message.edit_text(
        _build_monitor_summary(updated),
        reply_markup=monitor_action_keyboard(updated.id, is_active=updated.is_active),
    )


@router.callback_query(F.data.startswith("monitor:delete:"))
async def delete_monitor(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    services.monitor_profiles.delete(monitor_id)
    await callback.message.edit_text("Monitor deleted.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("monitor:instant:"))
async def toggle_instant(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    profile = services.monitor_profiles.get(monitor_id)
    if profile is None:
        await callback.message.edit_text("Monitor not found.", reply_markup=status_back_keyboard())
        return
    updated = services.monitor_profiles.update_notifications(
        monitor_id,
        instant_alerts_enabled=not profile.instant_alerts_enabled,
    )
    await callback.message.edit_text(
        _build_monitor_summary(updated),
        reply_markup=monitor_action_keyboard(updated.id, is_active=updated.is_active),
    )


@router.callback_query(F.data.startswith("monitor:digest:"))
async def toggle_digest(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    profile = services.monitor_profiles.get(monitor_id)
    if profile is None:
        await callback.message.edit_text("Monitor not found.", reply_markup=status_back_keyboard())
        return
    updated = services.monitor_profiles.update_notifications(
        monitor_id,
        digest_enabled=not profile.digest_enabled,
    )
    await callback.message.edit_text(
        _build_monitor_summary(updated),
        reply_markup=monitor_action_keyboard(updated.id, is_active=updated.is_active),
    )


@router.callback_query(F.data.startswith("monitor:run:"))
async def run_monitor_source(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    monitor_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    profile = services.monitor_profiles.get(monitor_id)
    if profile is None:
        await callback.message.edit_text("Monitor not found.", reply_markup=status_back_keyboard())
        return
    try:
        run = await asyncio.to_thread(services.runner.run_source, profile.source_id, "telegram_manual")
        await callback.message.edit_text(
            f"Run requested for monitor {profile.name}.\nRun #{run.id} finished with status {run.status}.",
            reply_markup=monitor_action_keyboard(profile.id, is_active=profile.is_active),
        )
    except RunLockedError:
        await callback.message.edit_text(
            "This source is already running. Try again shortly.",
            reply_markup=monitor_action_keyboard(profile.id, is_active=profile.is_active),
        )


@router.callback_query(F.data.startswith("run:source:"))
async def run_source_now(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    source_id = int(callback.data.rsplit(":", 1)[-1])
    services = get_bot_services()
    try:
        run = await asyncio.to_thread(services.runner.run_source, source_id, "telegram_manual")
        await callback.message.edit_text(
            f"Source run completed.\nRun #{run.id}: {run.status}\nItems: {run.items_parsed} | Events: {run.events_count}",
            reply_markup=main_menu_keyboard(),
        )
    except RunLockedError:
        await callback.message.edit_text(
            "That source is already running. Try again shortly.",
            reply_markup=main_menu_keyboard(),
        )
