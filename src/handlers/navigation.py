from __future__ import annotations

from typing import TypedDict, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from bot.runtime import get_song_service
from handlers.backup import export_backup_command
from handlers.charts import send_chart_for_song_id
from handlers.common import help_command, send_home_screen
from handlers.conversation import (
    NAV_HOME_CALLBACK,
    home_or_remove_markup,
    parse_callback_int,
    parse_callback_int_pair,
    song_outcome_keyboard,
    user_state,
)
from handlers.repertoire import format_song, tags_command
from handlers.ui import (
    BUTTON_CANCEL,
    MAIN_MENU_BUTTONS,
    MENU_BACKUP,
    MENU_HELP,
    MENU_SEARCH,
    MENU_SONGS,
    MENU_START,
    MENU_TAGS,
    MENU_UPLOAD_CHART,
    cancel_markup,
    home_menu_markup,
    is_admin_user,
)
from models.song import Song
from services.song_service import SongNotFoundError

BROWSER_PAGE_SIZE = 8
SEARCH_PENDING_KEY = "search_pending"
SONG_BROWSER_STATE_KEY = "song_browser_state"


class BrowserItem(TypedDict):
    id: int
    title: str
    artist: str


class BrowserState(TypedDict):
    mode: str
    title: str
    items: list[BrowserItem]
    current_page: int


async def menu_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    text = message.text.strip()
    state = user_state(context)

    if text == MENU_START:
        _reset_navigation_state(context)
        await send_home_screen(update, context)
        return
    if text == MENU_SONGS:
        _clear_search_pending(context)
        await show_song_browser(update, context)
        return
    if text == MENU_SEARCH:
        state[SEARCH_PENDING_KEY] = True
        await message.reply_text(
            "Надішліть текст для пошуку або натисніть «Скасувати».",
            reply_markup=cancel_markup(update),
        )
        return
    if text == MENU_TAGS:
        _clear_search_pending(context)
        await tags_command(update, context)
        return
    if text == MENU_HELP:
        _clear_search_pending(context)
        await help_command(update, context)
        return
    if text == MENU_UPLOAD_CHART:
        _clear_search_pending(context)
        if not is_admin_user(update, context):
            await message.reply_text("Для цієї дії потрібні права адміністратора.")
            return
        await show_upload_target_picker(update, context)
        return
    if text == MENU_BACKUP:
        _clear_search_pending(context)
        if not is_admin_user(update, context):
            await message.reply_text("Для цієї дії потрібні права адміністратора.")
            return
        await show_backup_menu(update, context)
        return

    if bool(state.get(SEARCH_PENDING_KEY)):
        if text == BUTTON_CANCEL:
            _reset_navigation_state(context)
            await send_home_screen(update, context, prefix="Скасовано.")
            return
        if text in MAIN_MENU_BUTTONS:
            _clear_search_pending(context)
            await message.reply_text("Для навігації використовуйте кнопки меню.")
            return
        _clear_search_pending(context)
        await show_song_browser(update, context, query=text)
        return

    await message.reply_text(
        "Скористайтеся кнопками меню або натисніть «Головна».",
        reply_markup=home_menu_markup(update, context),
    )


async def navigation_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not isinstance(query.data, str):
        return
    data = query.data

    if data.startswith("browser:page:"):
        await query.answer()
        page_payload = _parse_browser_page(data)
        if page_payload is None:
            await query.edit_message_text("Не вдалося розпізнати сторінку списку.")
            return
        mode, page = page_payload
        await _render_browser_page(update, context, mode=mode, page=page, edit=True)
        return

    if data == "browser:close":
        await query.answer()
        await query.edit_message_text("Закрито.")
        return

    if data.startswith("song:detail:"):
        await query.answer()
        detail_payload = parse_callback_int_pair(data, prefix="song:detail:")
        if detail_payload is None:
            await query.edit_message_text("Не вдалося завантажити деталі пісні.")
            return
        song_id, page = detail_payload
        await _render_song_detail(update, context, song_id=song_id, page=page)
        return

    if data.startswith("song:view:"):
        await query.answer()
        view_song_id = parse_callback_int(data, prefix="song:view:")
        if view_song_id is None:
            if update.effective_message is not None:
                await update.effective_message.reply_text(
                    "Не вдалося розпізнати пісню для перегляду акордів."
                )
            return
        await send_chart_for_song_id(update, context, view_song_id)
        return

    if data.startswith("song:archiveconfirm:"):
        await query.answer()
        confirm_payload = parse_callback_int_pair(data, prefix="song:archiveconfirm:")
        if confirm_payload is None:
            await query.edit_message_text("Не вдалося розпізнати запит на архівацію.")
            return
        song_id, page = confirm_payload
        await _archive_song_from_detail(update, context, song_id=song_id, page=page)
        return

    if data == NAV_HOME_CALLBACK:
        await query.answer()
        _reset_navigation_state(context)
        await send_home_screen(update, context)
        return

    if data.startswith("song:archive:"):
        await query.answer()
        archive_payload = parse_callback_int_pair(data, prefix="song:archive:")
        if archive_payload is None:
            await query.edit_message_text("Не вдалося розпізнати запит на архівацію.")
            return
        song_id, page = archive_payload
        await _render_archive_confirmation(update, context, song_id=song_id, page=page)
        return

    if data == "backup:menu":
        await query.answer()
        await show_backup_menu(update, context, edit=True)
        return

    if data == "backup:export":
        await query.answer()
        await export_backup_command(update, context)
        return

    if data == "backup:close":
        await query.answer()
        await query.edit_message_text("Меню резервних копій закрито.")


def build_navigation_callback_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        navigation_callback_router,
        pattern=(
            r"^(browser:|song:(detail|view|archive|archiveconfirm):|"
            r"backup:(menu|export|close)|nav:home)$"
        ),
    )


def build_menu_text_handler() -> MessageHandler:
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        menu_text_router,
    )


async def show_song_browser(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    query: str | None = None,
) -> None:
    service = get_song_service(context)
    if query is None:
        songs = await service.list_songs()
        title = "Активні пісні"
    else:
        songs = await service.search_songs(query)
        title = f'Результати для "{query}"'
    if update.effective_message is None:
        return
    if not songs:
        text = "Нічого не знайдено." if query else "Ще немає активних пісень."
        await update.effective_message.reply_text(text)
        return

    state: BrowserState = {
        "mode": "browse",
        "title": title,
        "items": _browser_items(songs),
        "current_page": 0,
    }
    user_state(context)[SONG_BROWSER_STATE_KEY] = state
    await _render_browser_page(update, context, mode="browse", page=0, edit=False)


async def show_upload_target_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = get_song_service(context)
    songs = await service.list_songs()
    if update.effective_message is None:
        return
    if not songs:
        await update.effective_message.reply_text("Ще немає активних пісень.")
        return

    state: BrowserState = {
        "mode": "upload",
        "title": "Оберіть пісню для завантаження акордів",
        "items": _browser_items(songs),
        "current_page": 0,
    }
    user_state(context)[SONG_BROWSER_STATE_KEY] = state
    await _render_browser_page(update, context, mode="upload", page=0, edit=False)


async def show_backup_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit: bool = False,
) -> None:
    if not is_admin_user(update, context):
        if update.effective_message is not None:
            await update.effective_message.reply_text("Для цієї дії потрібні права адміністратора.")
        return

    text = "Дії з резервними копіями:"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Експорт резервної копії", callback_data="backup:export"),
                InlineKeyboardButton("Імпорт резервної копії", callback_data="backup:import:start"),
            ],
            [InlineKeyboardButton("Закрити", callback_data="backup:close")],
        ]
    )
    query = update.callback_query
    if edit and query is not None:
        await query.edit_message_text(text, reply_markup=keyboard)
        return
    if update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def _render_browser_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    page: int,
    edit: bool,
) -> None:
    browser_state = _active_browser_state(context)
    if browser_state is None or browser_state["mode"] != mode:
        browser_state = await _rebuild_browser_state(context, mode=mode)
        if browser_state is None:
            if update.callback_query is not None:
                await update.callback_query.edit_message_text("Сесія перегляду пісень завершилася.")
            elif update.effective_message is not None:
                await update.effective_message.reply_text("Сесія перегляду пісень завершилася.")
            return

    items = browser_state["items"]
    total = len(items)
    if total == 0:
        if update.callback_query is not None:
            await update.callback_query.edit_message_text("Немає пісень для відображення.")
        elif update.effective_message is not None:
            await update.effective_message.reply_text("Немає пісень для відображення.")
        return

    total_pages = (total + BROWSER_PAGE_SIZE - 1) // BROWSER_PAGE_SIZE
    normalized_page = min(max(page, 0), total_pages - 1)
    browser_state["current_page"] = normalized_page
    start = normalized_page * BROWSER_PAGE_SIZE
    end = start + BROWSER_PAGE_SIZE
    page_items = items[start:end]

    body_lines = [
        f"{browser_state['title']} ({total})",
        f"Сторінка {normalized_page + 1}/{total_pages}",
    ]
    for item in page_items:
        body_lines.append(f"#{item['id']} {item['title']} | {item['artist']}")
    body_lines.append("Оберіть пісню нижче.")
    text = "\n".join(body_lines)
    keyboard = _browser_keyboard(
        mode=mode,
        page=normalized_page,
        total_pages=total_pages,
        items=page_items,
    )

    query = update.callback_query
    if edit and query is not None:
        await query.edit_message_text(text, reply_markup=keyboard)
        return
    if update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


def _browser_keyboard(
    *,
    mode: str,
    page: int,
    total_pages: int,
    items: list[BrowserItem],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        label = f"#{item['id']} {_truncate_label(item['title'])}"
        if mode == "browse":
            callback_data = f"song:detail:{item['id']}:{page}"
        else:
            callback_data = f"upload:start:{item['id']}"
        rows.append([InlineKeyboardButton(label, callback_data=callback_data)])

    mode_short = "b" if mode == "browse" else "u"
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("Назад", callback_data=f"browser:page:{mode_short}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("Далі", callback_data=f"browser:page:{mode_short}:{page + 1}")
        )
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton("Закрити", callback_data="browser:close")])
    return InlineKeyboardMarkup(rows)


async def _render_song_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    song_id: int,
    page: int,
) -> None:
    query = update.callback_query
    if query is None:
        return

    service = get_song_service(context)
    try:
        song = await service.get_song(song_id)
    except SongNotFoundError as error:
        await query.edit_message_text(str(error))
        return

    keyboard = _song_detail_keyboard(
        song_id=song_id,
        page=page,
        is_admin=is_admin_user(update, context),
    )
    await query.edit_message_text("Деталі пісні:\n" + format_song(song), reply_markup=keyboard)


def _song_detail_keyboard(*, song_id: int, page: int, is_admin: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Переглянути акорди", callback_data=f"song:view:{song_id}")],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton("Редагувати", callback_data=f"edit:start:{song_id}"),
                InlineKeyboardButton("Архівувати", callback_data=f"song:archive:{song_id}:{page}"),
            ]
        )
        rows.append(
            [InlineKeyboardButton("Завантажити гармонію", callback_data=f"upload:start:{song_id}")]
        )
    rows.append(
        [InlineKeyboardButton("Назад до результатів", callback_data=f"browser:page:b:{page}")]
    )
    return InlineKeyboardMarkup(rows)


async def _render_archive_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    song_id: int,
    page: int,
) -> None:
    query = update.callback_query
    if query is None:
        return
    if not is_admin_user(update, context):
        await query.answer("Потрібні права адміністратора.", show_alert=True)
        return

    service = get_song_service(context)
    try:
        song = await service.get_song(song_id)
    except SongNotFoundError as error:
        await query.edit_message_text(str(error))
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Підтвердити архівацію",
                    callback_data=f"song:archiveconfirm:{song_id}:{page}",
                )
            ],
            [InlineKeyboardButton("Назад", callback_data=f"song:detail:{song_id}:{page}")],
        ]
    )
    await query.edit_message_text(
        f"Архівувати пісню #{song_id}: {song.title}?",
        reply_markup=keyboard,
    )


async def _archive_song_from_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    song_id: int,
    page: int,
) -> None:
    query = update.callback_query
    if query is None:
        return
    if not is_admin_user(update, context):
        await query.answer("Потрібні права адміністратора.", show_alert=True)
        return

    service = get_song_service(context)
    try:
        song = await service.archive_song(song_id)
    except SongNotFoundError as error:
        await query.edit_message_text(str(error))
        return

    if update.effective_message is None:
        await query.edit_message_text(f"Пісню #{song.id} архівовано: {song.title}")
        return

    await query.edit_message_reply_markup(reply_markup=None)
    await update.effective_message.reply_text(
        f"Пісню #{song.id} архівовано: {song.title}",
        reply_markup=home_or_remove_markup(update, context),
    )
    await update.effective_message.reply_text(
        "Що далі?",
        reply_markup=song_outcome_keyboard(song_id=song.id, page=page, list_mode_short="b"),
    )


def _browser_items(songs: list[Song]) -> list[BrowserItem]:
    items: list[BrowserItem] = []
    for song in songs:
        song_id = int(song.id)
        items.append(
            {
                "id": song_id,
                "title": song.title,
                "artist": song.artist,
            }
        )
    return items


def _active_browser_state(context: ContextTypes.DEFAULT_TYPE) -> BrowserState | None:
    value = user_state(context).get(SONG_BROWSER_STATE_KEY)
    if isinstance(value, dict):
        state = cast(BrowserState, value)
        if "mode" in state and "title" in state and "items" in state:
            if not isinstance(state.get("current_page"), int):
                state["current_page"] = 0
            return state
    return None


async def _rebuild_browser_state(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
) -> BrowserState | None:
    if mode not in {"browse", "upload"}:
        return None
    service = get_song_service(context)
    songs = await service.list_songs()
    title = "Активні пісні" if mode == "browse" else "Оберіть пісню для завантаження акордів"
    state: BrowserState = {
        "mode": mode,
        "title": title,
        "items": _browser_items(songs),
        "current_page": 0,
    }
    user_state(context)[SONG_BROWSER_STATE_KEY] = state
    return state


def _truncate_label(value: str, limit: int = 28) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _parse_browser_page(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None
    _, _, mode_short, raw_page = parts
    mode = "browse" if mode_short == "b" else "upload" if mode_short == "u" else None
    if mode is None:
        return None
    try:
        page = int(raw_page)
    except ValueError:
        return None
    return mode, page


def _clear_search_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_state(context).pop(SEARCH_PENDING_KEY, None)


def _reset_navigation_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    _clear_search_pending(context)
    user_state(context).pop(SONG_BROWSER_STATE_KEY, None)
