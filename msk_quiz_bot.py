import asyncio
import logging
import mysql.connector
import re
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import BotCommand, ReplyKeyboardRemove
from aiogram.types import BotCommandScopeDefault
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from mysql.connector import Error

# --- Константы и настройки ---
# !!! ЗАМЕНИТЕ ЗДЕСЬ НА ВАШИ ЗНАЧЕНИЯ !!!
API_TOKEN = ""

DB_CONFIG = {
    'host': '',      # Адрес сервера БД (часто localhost или IP)
    'user': '',      # Имя пользователя БД
    'password': '', # Пароль пользователя БД
    'database': ''   # Имя вашей базы данных
}
# !!! ЗАМЕНИТЕ ВЫШЕ НА ВАШИ ЗНАЧЕНИЯ !!!

# Уровень логирования: DEBUG - для подробной отладки, INFO - для обычной работы
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- Инициализация бота и диспетчера ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Определение состояний для FSM ---
class OrganizerFilterStates(StatesGroup):
    waiting_for_organizer_selection = State()
    waiting_for_date_selection = State()

class LocationFilterStates(StatesGroup):
    waiting_for_location_selection = State()
    waiting_for_date_selection = State()

class CategoryFilterStates(StatesGroup):
    waiting_for_category_selection = State()
    waiting_for_date_selection = State()


# --- Словари (Русские названия) ---
RUSSIAN_MONTH_NAMES_GENITIVE = {
    1: "Января", 2: "Февраля", 3: "Марта", 4: "Апреля",
    5: "Мая", 6: "Июня", 7: "Июля", 8: "Августа",
    9: "Сентября", 10: "Октября", 11: "Ноября", 12: "Декабря",
}

RUSSIAN_WEEKDAY_NAMES = {
    0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг",
    4: "Пятница", 5: "Суббота", 6: "Воскресенье",
}

# --- Функции для работы с БД ---
# *** ЭТОТ БЛОК С ФУНКЦИЯМИ БД ДОЛЖЕН НАХОДИТЬСЯ ВЫШЕ БЛОКА ХЭНДЛЕРОВ ***

def create_db_connection():
    connection = None
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        logging.error(f"Ошибка подключения к базе данных: {e}")
        connection = None
    return connection

def get_events_by_date(target_date: date):
    events = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        select_events_sql = """
        SELECT
            title, start_time, type, price, category, difficulty,
            location_name, location_address, url, `date`, organizer
        FROM `msk_events`
        WHERE `date` = %s
        ORDER BY `start_time`;
        """
        cursor.execute(select_events_sql, (target_date,))
        events = cursor.fetchall()

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении мероприятий по дате: {e}")
        events = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return events


def get_distinct_event_dates():
    dates = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_dates_sql = """
        SELECT DISTINCT `date`
        FROM `msk_events`
        WHERE `date` >= CURDATE()
        ORDER BY `date`
        LIMIT 30;
        """
        cursor.execute(select_dates_sql)
        dates_raw = cursor.fetchall()
        dates = [d[0] for d in dates_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении уникальных дат: {e}")
        dates = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return dates


def get_distinct_organizers():
    organizers = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_organizers_sql = """
        SELECT DISTINCT `organizer`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `organizer` IS NOT NULL AND `organizer` != ''
        ORDER BY `organizer`;
        """
        cursor.execute(select_organizers_sql)
        organizers_raw = cursor.fetchall()
        organizers = [o[0] for o in organizers_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении уникальных организаторов: {e}")
        organizers = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return organizers


def get_distinct_dates_by_organizer(organizer_name: str):
    dates = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_dates_sql = """
        SELECT DISTINCT `date`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `organizer` = %s
        ORDER BY `date`
        LIMIT 30;
        """
        cursor.execute(select_dates_sql, (organizer_name,))
        dates_raw = cursor.fetchall()
        dates = [d[0] for d in dates_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении дат по организатору ({organizer_name}): {e}")
        dates = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return dates


def get_events_by_organizer_and_date(organizer_name: str, target_date: date):
    events = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        select_events_sql = """
        SELECT
            title, start_time, type, price, category, difficulty,
            location_name, location_address, url, `date`, organizer
        FROM `msk_events`
        WHERE `date` = %s AND `organizer` = %s
        ORDER BY `start_time`;
        """
        cursor.execute(select_events_sql, (target_date, organizer_name))
        events = cursor.fetchall()

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении мероприятий по организатору и дате ({organizer_name}, {target_date}): {e}")
        events = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return events


def get_distinct_locations():
    locations = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_locations_sql = """
        SELECT DISTINCT `location_name`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `location_name` IS NOT NULL AND `location_name` != ''
        ORDER BY `location_name`;
        """
        cursor.execute(select_locations_sql)
        locations_raw = cursor.fetchall()
        locations = [loc[0] for loc in locations_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении уникальных названий мест: {e}")
        locations = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return locations


def get_distinct_dates_by_location(location_name: str):
    dates = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_dates_sql = """
        SELECT DISTINCT `date`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `location_name` = %s
        ORDER BY `date`
        LIMIT 30;
        """
        cursor.execute(select_dates_sql, (location_name,))
        dates_raw = cursor.fetchall()
        dates = [d[0] for d in dates_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении дат по месту ({location_name}): {e}")
        dates = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return dates


def get_events_by_location_and_date(location_name: str, target_date: date):
    events = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        select_events_sql = """
        SELECT
            title, start_time, type, price, category, difficulty,
            location_name, location_address, url, `date`, organizer
        FROM `msk_events`
        WHERE `date` = %s AND `location_name` = %s
        ORDER BY `start_time`;
        """
        cursor.execute(select_events_sql, (target_date, location_name))
        events = cursor.fetchall()

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении мероприятий по месту и дате ({location_name}, {target_date}): {e}")
        events = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return events

def get_distinct_categories():
    categories = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_categories_sql = """
        SELECT DISTINCT `category`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `category` IS NOT NULL AND `category` != ''
        ORDER BY `category`;
        """
        cursor.execute(select_categories_sql)
        categories_raw = cursor.fetchall()
        categories = [cat[0] for cat in categories_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении уникальных категорий: {e}")
        categories = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return categories


def get_distinct_dates_by_category(category_name: str):
    dates = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor()
    try:
        select_dates_sql = """
        SELECT DISTINCT `date`
        FROM `msk_events`
        WHERE `date` >= CURDATE() AND `category` = %s
        ORDER BY `date`
        LIMIT 30;
        """
        cursor.execute(select_dates_sql, (category_name,))
        dates_raw = cursor.fetchall()
        dates = [d[0] for d in dates_raw]

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении дат по категории ({category_name}): {e}")
        dates = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return dates


def get_events_by_category_and_date(category_name: str, target_date: date):
    events = []
    connection = create_db_connection()
    if connection is None:
        return None

    cursor = connection.cursor(dictionary=True)
    try:
        select_events_sql = """
        SELECT
            title, start_time, type, price, category, difficulty,
            location_name, location_address, url, `date`, organizer
        FROM `msk_events`
        WHERE `date` = %s AND `category` = %s
        ORDER BY `start_time`;
        """
        cursor.execute(select_events_sql, (target_date, category_name))
        events = cursor.fetchall()

    except Error as e:
        logging.error(f"Ошибка выполнения SQL запроса при получении мероприятий по категории и дате ({category_name}, {target_date}): {e}")
        events = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return events

# ОБНОВЛЕНО: Функция для добавления записи о выборе фильтра или команде в таблицу статистики
def insert_filter_selection(user_id: int, user_name: str | None, interaction_type: str, interaction_value: str):
    """
    Записывает в таблицу msk_user_filter_stats информацию о действии пользователя.
    interaction_type: тип взаимодействия (например, 'command', 'filter_organizer', 'filter_location', 'filter_category').
    interaction_value: значение взаимодействия (например, '/start', '/today', 'Название Организатора', 'Название Бара').
    """
    connection = create_db_connection()
    if connection is None:
        return

    cursor = connection.cursor()
    try:
        insert_sql = """
        INSERT INTO msk_user_filter_stats (user_id, user_name, filter_type, filter_value)
        VALUES (%s, %s, %s, %s);
        """
        cursor.execute(insert_sql, (user_id, user_name, interaction_type, interaction_value))
        connection.commit()
        logging.info(f"Статистика записана: user_id={user_id}, user_name='{user_name}', type='{interaction_type}', value='{interaction_value}'")

    except Error as e:
        logging.error(f"Ошибка при записи статистики в БД: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.close()


# --- Вспомогательная функция для HTML-экранирования символов (остается без изменений) ---
def escape_html(text: str) -> str:
    """
    Экранирует специальные символы HTML в тексте: &, <, >.
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


# --- Клавиатуры ---
# Reply клавиатура с кнопками фильтров
def main_reply_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Организатор")
    builder.button(text="Бар")
    builder.button(text="Тематика")

    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# Функция для создания Inline клавиатуры со списком Организаторов (без Base64)
def organizers_inline_keyboard(organizer_list: list[str]):
    builder = InlineKeyboardBuilder()
    if not organizer_list:
        return None

    for organizer in organizer_list:
        organizer_escaped_for_callback = organizer.replace(':', '\\:')
        callback_data = f"select_organizer:{organizer_escaped_for_callback}"

        builder.button(text=organizer, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры с датами (для фильтра Организатора, без Base64)
def dates_inline_keyboard_for_organizer(dates_list: list[date], organizer_name_escaped_for_callback: str):
    builder = InlineKeyboardBuilder()
    if not dates_list:
        return None

    for event_date in dates_list:
        day = event_date.day
        month_name = RUSSIAN_MONTH_NAMES_GENITIVE.get(event_date.month, f"Месяц{event_date.month}")
        weekday_name = RUSSIAN_WEEKDAY_NAMES.get(event_date.weekday(), "День недели")

        button_text = f"{day} {month_name}, {weekday_name}"

        callback_data = f"select_org_date:{organizer_name_escaped_for_callback}:{event_date.strftime('%Y-%m-%d')}"

        builder.button(text=button_text, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры со списком Названий мест (с ID в callback_data)
def locations_inline_keyboard_with_ids(location_choices: dict[str, str]):
    builder = InlineKeyboardBuilder()
    if not location_choices:
        return None

    sorted_locations = sorted(location_choices.items(), key=lambda item: item[1])

    for loc_id, location_name in sorted_locations:
        callback_data = f"select_location_id:{loc_id}"
        builder.button(text=location_name, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры с датами (для фильтра Места, с ID места в callback_data)
def dates_inline_keyboard_for_location_with_id(dates_list: list[date], location_id: str):
    builder = InlineKeyboardBuilder()
    if not dates_list:
        return None

    for event_date in dates_list:
        day = event_date.day
        month_name = RUSSIAN_MONTH_NAMES_GENITIVE.get(event_date.month, f"Месяц{event_date.month}")
        weekday_name = RUSSIAN_WEEKDAY_NAMES.get(event_date.weekday(), "День недели")

        button_text = f"{day} {month_name}, {weekday_name}"

        callback_data = f"select_loc_date_id:{location_id}:{event_date.strftime('%Y-%m-%d')}"

        builder.button(text=button_text, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры со списком Категорий (с ID в callback_data)
def categories_inline_keyboard_with_ids(category_choices: dict[str, str]):
    builder = InlineKeyboardBuilder()
    if not category_choices:
        return None

    sorted_categories = sorted(category_choices.items(), key=lambda item: item[1])

    for cat_id, category_name in sorted_categories:
        callback_data = f"select_category_id:{cat_id}"
        builder.button(text=category_name, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры с датами (для фильтра Категории, с ID категории в callback_data)
def dates_inline_keyboard_for_category_with_id(dates_list: list[date], category_id: str):
    builder = InlineKeyboardBuilder()
    if not dates_list:
        return None

    for event_date in dates_list:
        day = event_date.day
        month_name = RUSSIAN_MONTH_NAMES_GENITIVE.get(event_date.month, f"Месяц{event_date.month}")
        weekday_name = RUSSIAN_WEEKDAY_NAMES.get(event_date.weekday(), "День недели")

        button_text = f"{day} {month_name}, {weekday_name}"

        callback_data = f"select_cat_date_id:{category_id}:{event_date.strftime('%Y-%m-%d')}"

        builder.button(text=button_text, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# Функция для создания Inline клавиатуры с датами (оригинальная, для /by_date из меню)
def dates_inline_keyboard(dates_list: list[date]):
    builder = InlineKeyboardBuilder()
    if not dates_list:
        return None

    for event_date in dates_list:
        day = event_date.day
        month_name = RUSSIAN_MONTH_NAMES_GENITIVE.get(event_date.month, f"Месяц{event_date.month}")
        weekday_name = RUSSIAN_WEEKDAY_NAMES.get(event_date.weekday(), "День недели")

        button_text = f"{day} {month_name}, {weekday_name}"

        callback_data = f"date:{event_date.strftime('%Y-%m-%d')}"

        builder.button(text=button_text, callback_data=callback_data)

    builder.adjust(2)
    return builder.as_markup()


# --- Функция для отправки "карточки" мероприятия (с HTML) ---
async def send_event_card(message: types.Message, event: dict):
     """
     Форматирует данные одного мероприятия с использованием HTML.
     """
     event_date_str = event.get('date').strftime('%d.%m.%Y') if isinstance(event.get('date'), date) else 'Не указана'

     organizer_html = escape_html(event.get('organizer', 'Не указан'))
     title_html = escape_html(event.get('title', 'Без названия'))
     location_name_html = escape_html(event.get('location_name', 'Не указано'))

     start_time_html = escape_html(event.get('start_time', 'Не указано'))
     event_type_html = escape_html(event.get('type', 'Не указан'))
     price_html = escape_html(event.get('price', 'Не указана'))
     category_html = escape_html(event.get('category', 'Не указана'))
     difficulty_html = escape_html(event.get('difficulty', 'Не указана'))
     location_address_html = escape_html(event.get('location_address', 'Не указан'))
     event_date_str_html = escape_html(event_date_str)

     url_raw = event.get('url')
     url_line = f"🔗 Подробнее: Нет ссылки"

     if url_raw and isinstance(url_raw, str) and url_raw.strip():
         link_text_html = escape_html("Перейти")
         if re.match(r'https?://\S+', url_raw.strip()):
              url_line = f"🔗 Подробнее: <a href=\"{url_raw.strip()}\">{link_text_html}</a>"
         else:
              logging.warning(f"URL '{url_raw}' не подходит для прямого форматирования ссылки. Вывожу как текст.")
              url_line = f"🔗 Подробнее: {escape_html(url_raw)}"

     card_text_html = (
         f"<b>{organizer_html}</b>\n\n"
         f"📅 Дата: {event_date_str_html}\n"
         f"📚 Название: <b>{title_html}</b>\n"
         f"⏰ Время: {start_time_html}\n"
         f"🏷️ Тип: {event_type_html}\n"
         f"💰 Цена: {price_html}\n"
         f"🗂️ Категория: {category_html}\n"
         f"💪 Сложность: {difficulty_html}\n"
         f"📍 Место: <b>{location_name_html}</b>\n"
         f"🗺️ Адрес: {location_address_html}\n"
         f"{url_line}\n"
     )

     try:
         await message.answer(card_text_html, parse_mode="HTML")
         logging.info("Сообщение с карточкой отправлено в режиме HTML.")
     except Exception as e:
         logging.error(f"Ошибка отправки сообщения с карточкой мероприятия в режиме HTML: {e}")
         logging.error(f"Проблемный текст сообщения (HTML):\n{card_text_html}")
         try:
             await message.answer(f"Не удалось отформатировать информацию о мероприятии:\n{card_text_html}", parse_mode=None)
             logging.info("Отправлен простой текст сообщения (с HTML тегами) после ошибки форматирования.")
         except Exception as e_plain:
              logging.error(f"Не удалось отправить сообщение с карточкой даже как простой текст: {e_plain}")
              await message.answer("Не удалось отправить информацию о мероприятии.")

     await asyncio.sleep(0.2)


# --- Хэндлеры ---
# *** ЭТОТ БЛОК ХЭНДЛЕРОВ ДОЛЖЕН НАХОДИТЬСЯ НИЖЕ БЛОКА ФУНКЦИЙ БД И КЛАВИАТУР ***

# Хэндлер команды /start - Отправляет приветствие и Reply клавиатуру с кнопками фильтров
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    """
    Отправляет приветственное сообщение, список команд меню
    и Reply клавиатуру с кнопками фильтров.
    """
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'command', '/start') # <-- ЭТА СТРОКА ДОБАВЛЕНА
    welcome_text = (
        "Привет! 🤗\n\nЯ бот-афиша квизов и барных викторин в Москве.\n\n"
        "Используйте кнопку <b>Menu</b>, чтобы найти все квизы сегодня или в любой другой день и "
        "<b>кнопки внизу экрана</b> ⬇️ для поиска по фильтрам\n\n"
        "- /instruction: 🕵️‍♂️ все возможности бота\n\n"

    )
    await message.answer(
        welcome_text,
        parse_mode="HTML"
    )
    await message.answer(
         "Приятного поиска!",
         reply_markup=main_reply_keyboard()
    )


# Хэндлер команды /today ("Квизы сегодня") - Доступна через меню бота
@dp.message(Command("today"))
async def handle_today_quizzes_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'command', '/today') # <-- ЭТА СТРОКА ДОБАВЛЕНА
    logging.info(f"Получен запрос /today (команда) от {user_id} в чате {message.chat.id}")
    today = date.today()

    await message.answer(f"Ищу мероприятия на сегодня ({today.strftime('%d.%m.%Y')})...")

    events = get_events_by_date(today)

    if events is None:
        await message.answer("Произошла ошибка при получении данных из базы.")
    elif not events:
        await message.answer(f"На сегодня ({today.strftime('%d.%m.%Y')}) мероприятий не найдено.")
    else:
        await message.answer(f"Найдено мероприятий на {today.strftime('%d.%m.%Y')}: {len(events)}")
        for event in events:
            await send_event_card(message, event)


# Хэндлер команды /by_date ("Квизы по дате") - Доступна через меню бота
@dp.message(Command("by_date"))
async def handle_quizzes_by_date_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'command', '/by_date') # <-- ЭТА СТРОКА ДОБАВЛЕНА
    logging.info(f"Получен запрос /by_date (команда) от {user_id} в чате {message.chat.id}")
    dates = get_distinct_event_dates()

    if dates is None:
        await message.answer("Произошла ошибка при получении доступных дат.")
    elif not dates:
        await message.answer("В базе пока нет предстоящих мероприятий с указанными датами.")
    else:
        keyboard = dates_inline_keyboard(dates)
        if keyboard:
            await message.answer("Выберите дату:", reply_markup=keyboard)
        else:
             await message.answer("В базе пока нет предстоящих мероприятий с указанными датами.")


# Хэндлер команды /instruction - Доступна через меню бота
@dp.message(Command("instruction"))
async def handle_instruction_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'command', '/instruction') # <-- ЭТА СТРОКА ДОБАВЛЕНА
    logging.info(f"Получен запрос /instruction (команда) от {user_id} в чате {message.chat.id}")
    instruction_text = (
        "<b>Инструкция по использованию бота-афиши квизов в Москве:</b>\n\n"
        "Используйте кнопку <b>Menu</b> (/) рядом с полем ввода текста, "
        "чтобы увидеть список команд:\n"
        "- /start: выводит приветственное сообщение.\n"
        "- /today: покажет список мероприятий, запланированных на сегодня.\n"
        "- /by_date: предложит выбрать дату из списка всех доступных мероприятий.\n"
        "- /instruction: прочитать инструкцию.\n\n"
        "Используйте кнопки внизу экрана для поиска по фильтрам:\n"
        "- Кнопка \"Организатор\" позволяет выбрать квизы по Организатору.\n"
        "- Кнопка \"Бар\" позволяет выбрать квизы по месту проведения.\n"
        "- Кнопка \"Тематика\" позволяет выбрать квизы по их тематике/категории.\n\n"
        "Если мероприятия по выбранным критериям не найдены, бот сообщит об этом.\n\n"
    )
    await message.answer(instruction_text, parse_mode="HTML")
    await message.answer(
         "Выберите фильтр:",
         reply_markup=main_reply_keyboard()
    )


# Хэндлер нажатий на Inline кнопки с датами для оригинального /by_date (callback_data начинается с 'date:')
# Этот хэндлер срабатывает ТОЛЬКО если бот НЕ находится в каком-либо состоянии FSM
@dp.callback_query(F.data.startswith('date:'), StateFilter(None))
async def handle_date_callback(callback: types.CallbackQuery, state: FSMContext):
    # При выборе даты из /by_date мы не фиксируем статистику фильтров, т.к. не знаем, какой фильтр привел к этому (это общий список дат).
    # Но если хотите, можете добавить здесь запись, например:
    # insert_filter_selection(callback.from_user.id, callback.from_user.username, 'date_selection_from_by_date', selected_date_str)

    logging.info(f"Получен колбэк выбора даты (ориг /by_date) '{callback.data.split(':', 1)[1]}' от {callback.from_user.id} в чате {callback.message.chat.id}")

    try:
        selected_date_str = callback.data.split(':', 1)[1]
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except (ValueError, IndexError):
        logging.error(f"Неверный формат callback_data для выбора даты (ориг /by_date): {callback.data}")
        await callback.answer("Ошибка распознавания даты!", show_alert=True)
        await callback.message.answer("Произошла ошибка с данными даты. Попробуйте снова выбрать дату из меню /by_date.", parse_mode=None)
        return

    await callback.answer(f"Запрашиваю мероприятия на {selected_date.strftime('%d.%m.%Y')}...", show_alert=False)

    events = get_events_by_date(selected_date)

    try:
        await callback.message.edit_text(
            f"Выбрана дата: <b>{selected_date.strftime('%d.%m.%Y')}</b>",
            reply_markup=None,
            parse_mode="HTML"
        )
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с кнопками дат: {e}")


    if events is None:
        await callback.message.answer("Произошла ошибка при получении данных из базы.")
    elif not events:
        await callback.message.answer(f"На дату {selected_date.strftime('%d.%m.%Y')} мероприятий не найдено.")
    else:
        await callback.message.answer(f"Найдено мероприятий на {selected_date.strftime('%d.%m.%Y')}: {len(events)}")
        for event in events:
            await send_event_card(callback.message, event)


# --- Хэндлеры для фильтра Организатора ---

@dp.message(F.text == "Организатор")
async def handle_organizer_button(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'filter_selection', 'Организатор') # Запись нажатия на кнопку фильтра

    logging.info(f"Нажата кнопка 'Организатор' от {user_id} в чате {message.chat.id}")

    organizers = get_distinct_organizers()

    if organizers is None:
        await message.answer("Произошла ошибка при получении списка организаторов.")
        await state.clear()
    elif not organizers:
        await message.answer("На ближайшие даты мероприятий с указанными организаторами не найдено.")
        await state.clear()
    else:
        keyboard = organizers_inline_keyboard(organizers)
        if keyboard:
            await message.answer("Выберите организатора:", reply_markup=keyboard)
            await state.set_state(OrganizerFilterStates.waiting_for_organizer_selection)
        else:
             await message.answer("На ближайшие даты мероприятий с указанными организаторами не найдено.")
             await state.clear()


@dp.callback_query(OrganizerFilterStates.waiting_for_organizer_selection, F.data.startswith('select_organizer:'))
async def handle_organizer_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        prefix, organizer_name_escaped = callback.data.split(':', 1)
        organizer_name = organizer_name_escaped.replace('\\:', ':')
        logging.info(f"Выбран организатор: '{organizer_name}' от {callback.from_user.id}")

        # Записываем статистику выбора Организатора
        insert_filter_selection(callback.from_user.id, callback.from_user.username, 'filter_organizer', organizer_name)

    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора организатора: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных организатора!", show_alert=True)
        await callback.message.answer("Произошла ошибка. Пожалуйста, начните выбор организатора заново.", parse_mode=None)
        await state.clear()
        return

    try:
        await callback.message.edit_text(f"Выбран организатор: {organizer_name}")
        await callback.answer(f"Выбран: {organizer_name}. Ищу даты...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором организатора: {e}")
         await callback.answer(f"Выбран: {organizer_name}. Ищу даты...", show_alert=False)


    dates = get_distinct_dates_by_organizer(organizer_name)

    if dates is None:
        await callback.message.answer("Произошла ошибка при получении списка дат для выбранного организатора.")
        await state.clear()
    elif not dates:
        await callback.message.answer(f"Мероприятий от '{organizer_name}' на ближайшие даты не найдено.")
        await state.clear()
    else:
        keyboard = dates_inline_keyboard_for_organizer(dates, organizer_name_escaped)
        if keyboard:
            await callback.message.answer("Выберите дату:", reply_markup=keyboard)
            await state.set_state(OrganizerFilterStates.waiting_for_date_selection)
        else:
             await callback.message.answer(f"Мероприятий от '{organizer_name}' на ближайшие даты не найдено.")
             await state.clear()


@dp.callback_query(OrganizerFilterStates.waiting_for_date_selection, F.data.startswith('select_org_date:'))
async def handle_organizer_date_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_name = callback.from_user.username
    try:
        prefix, organizer_name_escaped, selected_date_str = callback.data.split(':', 2)
        organizer_name = organizer_name_escaped.replace('\\:', ':')
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        logging.info(f"Выбрана дата '{selected_date_str}' для организатора '{organizer_name}' от {user_id} (@{user_name})")

        # Записываем статистику выбора даты для организатора
        # Мы уже записали выбор организатора, теперь записываем выбор даты.
        # insert_filter_selection(user_id, user_name, 'filter_organizer_date', selected_date_str) # можно добавить, но пользователь просил только до фильтров

    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора даты после организатора: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных даты!", show_alert=True)
        await state.clear()
        return

    try:
        await callback.message.edit_text(
            f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Организатор: {organizer_name}",
            parse_mode=None
        )
        await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором даты: {e}")
         await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)


    events = get_events_by_organizer_and_date(organizer_name, selected_date)

    if events is None:
        await callback.message.answer("Произошла ошибка при получении данных из базы.")
    elif not events:
        await callback.message.answer(
            f"Мероприятий от '{organizer_name}' "
            f"на дату {selected_date.strftime('%d.%m.%Y')} не найдено."
        )
    else:
        await callback.message.answer(
             f"Найдено мероприятий от '{organizer_name}' "
             f"на {selected_date.strftime('%d.%m.%Y')}: {len(events)}"
        )
        for event in events:
            await send_event_card(callback.message, event)

    await state.clear()
    logging.info(f"Состояние FSM сброшено для пользователя {user_id} (@{user_name})")


# --- Хэндлеры для фильтра Места ---

@dp.message(F.text == "Бар")
async def handle_location_button(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'filter_selection', 'Бар') # Запись нажатия на кнопку фильтра

    logging.info(f"Нажата кнопка 'Бар' от {user_id} в чате {message.chat.id}")

    locations = get_distinct_locations()

    if locations is None:
        await message.answer("Произошла ошибка при получении списка мест проведения.")
        await state.clear()
    elif not locations:
        await message.answer("На ближайшие даты мероприятий с указанными местами не найдено.")
        await state.clear()
    else:
        location_choices = {f"loc_{i}": loc for i, loc in enumerate(locations)}
        await state.update_data(location_choices=location_choices)
        logging.debug(f"Сохранен словарь location_choices в state: {location_choices}")

        keyboard = locations_inline_keyboard_with_ids(location_choices)

        if keyboard:
            await message.answer("Выберите место проведения:", reply_markup=keyboard)
            await state.set_state(LocationFilterStates.waiting_for_location_selection)
        else:
             await message.answer("На ближайшие даты мероприятий с указанными местами не найдено.")
             await state.clear()


@dp.callback_query(LocationFilterStates.waiting_for_location_selection, F.data.startswith('select_location_id:'))
async def handle_location_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        prefix, location_id = callback.data.split(':', 1)
        data = await state.get_data()
        location_choices = data.get('location_choices')

        if location_choices is None or location_id not in location_choices:
            logging.error(f"Не найден словарь location_choices в state или ID '{location_id}' не найден.")
            await callback.answer("Ошибка данных места!", show_alert=True)
            await state.clear()
            return

        location_name = location_choices[location_id]
        logging.info(f"Выбрано место (ID: {location_id}): '{location_name}' от {callback.from_user.id}")

        # Записываем статистику выбора Места
        insert_filter_selection(callback.from_user.id, callback.from_user.username, 'filter_location', location_name)


    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора места: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных места!", show_alert=True)
        await state.clear()
        return

    try:
        await callback.message.edit_text(f"Выбрано место: {location_name}")
        await callback.answer(f"Выбрано: {location_name}. Ищу даты...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором места: {e}")
         await callback.answer(f"Выбрано: {location_name}. Ищу даты...", show_alert=False)

    dates = get_distinct_dates_by_location(location_name)

    if dates is None:
        await callback.message.answer("Произошла ошибка при получении списка дат для выбранного места.")
        await state.clear()
    elif not dates:
        await callback.message.answer(f"Мероприятий в месте '{location_name}' на ближайшие даты не найдено.")
        await state.clear()
    else:
        keyboard = dates_inline_keyboard_for_location_with_id(dates, location_id)
        if keyboard:
            await callback.message.answer("Выберите дату:", reply_markup=keyboard)
            await state.set_state(LocationFilterStates.waiting_for_date_selection)
        else:
             await callback.message.answer(f"Мероприятий в месте '{location_name}' на ближайшие даты не найдено.")
             await state.clear()


@dp.callback_query(LocationFilterStates.waiting_for_date_selection, F.data.startswith('select_loc_date_id:'))
async def handle_location_date_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_name = callback.from_user.username
    try:
        prefix, location_id, selected_date_str = callback.data.split(':', 2)
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

        data = await state.get_data()
        location_choices = data.get('location_choices')

        if location_choices is None or location_id not in location_choices:
            logging.error(f"Не найден словарь location_choices в state или ID '{location_id}' не найден.")
            await callback.answer("Ошибка данных места!", show_alert=True)
            await state.clear()
            return

        location_name = location_choices[location_id]
        logging.info(f"Выбрана дата '{selected_date_str}' для места (ID: {location_id}) '{location_name}' от {user_id} (@{user_name})")

        # Мы уже записали выбор места, выбор даты не пишем в данном случае, чтобы не дублировать
        # insert_filter_selection(user_id, user_name, 'filter_location_date', selected_date_str) # можно добавить

    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора даты после места: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных даты!", show_alert=True)
        await state.clear()
        return

    try:
        await callback.message.edit_text(
            f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Место: {location_name}",
            parse_mode=None
        )
        await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором даты: {e}")
         await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)


    events = get_events_by_location_and_date(location_name, selected_date)

    if events is None:
        await callback.message.answer("Произошла ошибка при получении данных из базы.")
    elif not events:
        await callback.message.answer(
            f"Мероприятий в месте '{location_name}' "
            f"на дату {selected_date.strftime('%d.%m.%Y')} не найдено."
        )
    else:
        await callback.message.answer(
             f"Найдено мероприятий в месте '{location_name}' "
             f"на {selected_date.strftime('%d.%m.%Y')}: {len(events)}"
        )
        for event in events:
            await send_event_card(callback.message, event)

    await state.clear()
    logging.info(f"Состояние FSM сброшено для пользователя {user_id} (@{user_name})")


# --- Хэндлеры для фильтра Тематики ---

@dp.message(F.text == "Тематика")
async def handle_category_button(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.username
    insert_filter_selection(user_id, user_name, 'filter_selection', 'Тематика') # Запись нажатия на кнопку фильтра

    logging.info(f"Нажата кнопка 'Тематика' от {user_id} в чате {message.chat.id}")

    categories = get_distinct_categories()

    if categories is None:
        await message.answer("Произошла ошибка при получении списка тематик.")
        await state.clear()
    elif not categories:
        await message.answer("На ближайшие даты мероприятий с указанными тематиками не найдено.")
        await state.clear()
    else:
        category_choices = {f"cat_{i}": cat for i, cat in enumerate(categories)}
        await state.update_data(category_choices=category_choices)
        logging.debug(f"Сохранен словарь category_choices в state: {category_choices}")

        keyboard = categories_inline_keyboard_with_ids(category_choices)

        if keyboard:
            await message.answer("Выберите тематику:", reply_markup=keyboard)
            await state.set_state(CategoryFilterStates.waiting_for_category_selection)
        else:
             await message.answer("На ближайшие даты мероприятий с указанными тематиками не найдено.")
             await state.clear()


@dp.callback_query(CategoryFilterStates.waiting_for_category_selection, F.data.startswith('select_category_id:'))
async def handle_category_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        prefix, category_id = callback.data.split(':', 1)
        data = await state.get_data()
        category_choices = data.get('category_choices')

        if category_choices is None or category_id not in category_choices:
            logging.error(f"Не найден словарь category_choices в state или ID '{category_id}' не найден.")
            await callback.answer("Ошибка данных тематики!", show_alert=True)
            await state.clear()
            return

        category_name = category_choices[category_id]
        logging.info(f"Выбрана тематика (ID: {category_id}): '{category_name}' от {callback.from_user.id}")

        # Записываем статистику выбора Тематики
        insert_filter_selection(callback.from_user.id, callback.from_user.username, 'filter_category', category_name)

    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора тематики: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных тематики!", show_alert=True)
        await state.clear()
        return

    try:
        await callback.message.edit_text(f"Выбрана тематика: {category_name}")
        await callback.answer(f"Выбрана: {category_name}. Ищу даты...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором тематики: {e}")
         await callback.answer(f"Выбрана: {category_name}. Ищу даты...", show_alert=False)

    dates = get_distinct_dates_by_category(category_name)

    if dates is None:
        await callback.message.answer("Произошла ошибка при получении списка дат для выбранной тематики.")
        await state.clear()
    elif not dates:
        await callback.message.answer(f"Мероприятий по тематике '{category_name}' на ближайшие даты не найдено.")
        await state.clear()
    else:
        keyboard = dates_inline_keyboard_for_category_with_id(dates, category_id)
        if keyboard:
            await callback.message.answer("Выберите дату:", reply_markup=keyboard)
            await state.set_state(CategoryFilterStates.waiting_for_date_selection)
        else:
             await callback.message.answer(f"Мероприятий по тематике '{category_name}' на ближайшие даты не найдено.")
             await state.clear()


@dp.callback_query(CategoryFilterStates.waiting_for_date_selection, F.data.startswith('select_cat_date_id:'))
async def handle_category_date_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_name = callback.from_user.username
    try:
        prefix, category_id, selected_date_str = callback.data.split(':', 2)
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

        data = await state.get_data()
        category_choices = data.get('category_choices')

        if category_choices is None or category_id not in category_choices:
            logging.error(f"Не найден словарь category_choices в state или ID '{category_id}' не найден.")
            await callback.answer("Ошибка данных тематики!", show_alert=True)
            await state.clear()
            return

        category_name = category_choices[category_id]
        logging.info(f"Выбрана дата '{selected_date_str}' для тематики (ID: {category_id}) '{category_name}' от {user_id} (@{user_name})")

        # Мы уже записали выбор тематики, выбор даты не пишем в данном случае, чтобы не дублировать
        # insert_filter_selection(user_id, user_name, 'filter_category_date', selected_date_str) # можно добавить

    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка парсинга callback_data для выбора даты после тематики: {callback.data}. Ошибка: {e}")
        await callback.answer("Ошибка данных даты!", show_alert=True)
        await state.clear()
        return

    try:
        await callback.message.edit_text(
            f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Тематика: {category_name}",
            parse_mode=None
        )
        await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)
    except Exception as e:
         logging.warning(f"Не удалось отредактировать сообщение с выбором даты: {e}")
         await callback.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}. Ищу мероприятия...", show_alert=False)


    events = get_events_by_category_and_date(category_name, selected_date)

    if events is None:
        await callback.message.answer("Произошла ошибка при получении данных из базы.")
    elif not events:
        await callback.message.answer(
            f"Мероприятий по тематике '{category_name}' "
            f"на дату {selected_date.strftime('%d.%m.%Y')} не найдено."
        )
    else:
        await callback.message.answer(
             f"Найдено мероприятий по тематике '{category_name}' "
             f"на {selected_date.strftime('%d.%m.%Y')}: {len(events)}"
        )
        for event in events:
            await send_event_card(callback.message, event)

    await state.clear()
    logging.info(f"Состояние FSM сброшено для пользователя {user_id} (@{user_name})")


# --- Функция для регистрации команд меню ---
async def set_default_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="👋 Привет!"),
        BotCommand(command="today", description="⚡ Все квизы сегодня"),
        BotCommand(command="by_date", description="📅 Квизы по датам"),
        BotCommand(command="instruction", description="🔎 Как найти свой квиз")
    ]
    await bot.set_my_commands(commands, scope=types.BotCommandScopeDefault())
    logging.info("Команды меню зарегистрированы.")


# Основная функция запуска бота
async def main():
    logging.info("Бот запускается...")

    await set_default_commands(bot)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Удалены ожидающие обновления (drop_pending_updates=True).")
    except Exception as e:
        logging.warning(f"Не удалось удалить вебхук или ожидающие обновления: {e}")

    logging.info("Бот готов к поллингу.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.exception("Произошла критическая ошибка при запуске/работе бота:")
