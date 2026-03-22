from aiogram.fsm.state import State, StatesGroup


class CreateMonitorStates(StatesGroup):
    source = State()
    category = State()
    min_price = State()
    max_price = State()
    include_keywords = State()
    exclude_keywords = State()
    instant_alerts = State()
    digest = State()
    priority_mode = State()
    name = State()
