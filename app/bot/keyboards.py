from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Create monitor", callback_data="menu:create_monitor")],
            [InlineKeyboardButton(text="My monitors", callback_data="menu:my_monitors")],
            [InlineKeyboardButton(text="Notifications", callback_data="menu:notifications")],
            [InlineKeyboardButton(text="Run check", callback_data="menu:run_check")],
            [InlineKeyboardButton(text="Status", callback_data="menu:status")],
        ]
    )


def yes_no_keyboard(*, yes: str, no: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Yes", callback_data=yes),
                InlineKeyboardButton(text="No", callback_data=no),
            ]
        ]
    )


def priority_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="High only", callback_data="create:priority:high_only")],
            [InlineKeyboardButton(text="High + Medium", callback_data="create:priority:high_medium")],
            [InlineKeyboardButton(text="All", callback_data="create:priority:all")],
        ]
    )


def monitor_action_keyboard(monitor_id: int, *, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Pause" if is_active else "Resume",
                    callback_data=f"monitor:toggle:{monitor_id}",
                ),
                InlineKeyboardButton(text="Run now", callback_data=f"monitor:run:{monitor_id}"),
            ],
            [
                InlineKeyboardButton(text="Instant alerts", callback_data=f"monitor:instant:{monitor_id}"),
                InlineKeyboardButton(text="Digest", callback_data=f"monitor:digest:{monitor_id}"),
            ],
            [InlineKeyboardButton(text="Delete", callback_data=f"monitor:delete:{monitor_id}")],
        ]
    )


def source_keyboard(sources: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"create:source:{source_id}")] for source_id, name in sources]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def run_source_keyboard(sources: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"run:source:{source_id}")] for source_id, name in sources]
    rows.append([InlineKeyboardButton(text="Back to menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def status_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Back to menu", callback_data="menu:home")]]
    )


def notifications_menu_keyboard(monitor_ids: list[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Monitor #{monitor_id}", callback_data=f"monitor:open:{monitor_id}")]
            for monitor_id in monitor_ids
        ]
        + [[InlineKeyboardButton(text="Back to menu", callback_data="menu:home")]]
    )


def skip_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Skip", callback_data=callback_data)]]
    )
