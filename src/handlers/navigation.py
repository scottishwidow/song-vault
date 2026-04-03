from __future__ import annotations

from typing import TypedDict, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from bot.runtime import get_song_service
from handlers.backup import export_backup_command
from handlers.charts import send_chart_for_song_id
from handlers.common import help_command
from handlers.repertoire import format_song, tags_command
from handlers.ui import (
    BUTTON_CANCEL,
    MAIN_MENU_BUTTONS,
    MENU_BACKUP,
    MENU_HELP,
    MENU_SEARCH,
    MENU_SONGS,
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
    artist_or_source: str


class BrowserState(TypedDict):
    mode: str
    title: str
    items: list[BrowserItem]


async def menu_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    text = message.text.strip()
    state = _user_state(context)

    if text == MENU_SONGS:
        _clear_search_pending(context)
        await show_song_browser(update, context)
        return
    if text == MENU_SEARCH:
        state[SEARCH_PENDING_KEY] = True
        await message.reply_text("Send search text, or Cancel.", reply_markup=cancel_markup(update))
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
            await message.reply_text("Admin access is required for this action.")
            return
        await show_upload_target_picker(update, context)
        return
    if text == MENU_BACKUP:
        _clear_search_pending(context)
        if not is_admin_user(update, context):
            await message.reply_text("Admin access is required for this action.")
            return
        await show_backup_menu(update, context)
        return

    if bool(state.get(SEARCH_PENDING_KEY)):
        if text == BUTTON_CANCEL:
            _clear_search_pending(context)
            await message.reply_text(
                "Cancelled.",
                reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
            )
            return
        if text in MAIN_MENU_BUTTONS:
            _clear_search_pending(context)
            await message.reply_text("Use menu buttons to navigate.")
            return
        _clear_search_pending(context)
        await show_song_browser(update, context, query=text)
        return

    await message.reply_text(
        "Use the menu buttons or /help.",
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
            await query.edit_message_text("Could not parse browser page.")
            return
        mode, page = page_payload
        await _render_browser_page(update, context, mode=mode, page=page, edit=True)
        return

    if data == "browser:close":
        await query.answer()
        await query.edit_message_text("Closed.")
        return

    if data.startswith("song:detail:"):
        await query.answer()
        detail_payload = _parse_song_action(data, prefix="song:detail:")
        if detail_payload is None:
            await query.edit_message_text("Could not load song details.")
            return
        song_id, page = detail_payload
        await _render_song_detail(update, context, song_id=song_id, page=page)
        return

    if data.startswith("song:view:"):
        await query.answer()
        view_song_id = _parse_single_song_id(data, prefix="song:view:")
        if view_song_id is None:
            if update.effective_message is not None:
                await update.effective_message.reply_text("Could not parse chart target song.")
            return
        await send_chart_for_song_id(update, context, view_song_id)
        return

    if data.startswith("song:archiveconfirm:"):
        await query.answer()
        confirm_payload = _parse_song_action(data, prefix="song:archiveconfirm:")
        if confirm_payload is None:
            await query.edit_message_text("Could not parse archive request.")
            return
        song_id, page = confirm_payload
        await _archive_song_from_detail(update, context, song_id=song_id, page=page)
        return

    if data.startswith("song:archive:"):
        await query.answer()
        archive_payload = _parse_song_action(data, prefix="song:archive:")
        if archive_payload is None:
            await query.edit_message_text("Could not parse archive request.")
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
        await query.edit_message_text("Backup menu closed.")


def build_navigation_callback_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(
        navigation_callback_router,
        pattern=r"^(browser:|song:(detail|view|archive|archiveconfirm):|backup:(menu|export|close)$)",
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
        title = "Active songs"
    else:
        songs = await service.search_songs(query)
        title = f'Matches for "{query}"'
    if update.effective_message is None:
        return
    if not songs:
        text = "No matching songs found." if query else "No active songs yet."
        await update.effective_message.reply_text(text)
        return

    state: BrowserState = {
        "mode": "browse",
        "title": title,
        "items": _browser_items(songs),
    }
    _user_state(context)[SONG_BROWSER_STATE_KEY] = state
    await _render_browser_page(update, context, mode="browse", page=0, edit=False)


async def show_upload_target_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = get_song_service(context)
    songs = await service.list_songs()
    if update.effective_message is None:
        return
    if not songs:
        await update.effective_message.reply_text("No active songs yet.")
        return

    state: BrowserState = {
        "mode": "upload",
        "title": "Select a song to upload a chart",
        "items": _browser_items(songs),
    }
    _user_state(context)[SONG_BROWSER_STATE_KEY] = state
    await _render_browser_page(update, context, mode="upload", page=0, edit=False)


async def show_backup_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    edit: bool = False,
) -> None:
    if not is_admin_user(update, context):
        if update.effective_message is not None:
            await update.effective_message.reply_text("Admin access is required for this action.")
        return

    text = "Backup actions:"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Export Backup", callback_data="backup:export"),
                InlineKeyboardButton("Import Backup", callback_data="backup:import:start"),
            ],
            [InlineKeyboardButton("Close", callback_data="backup:close")],
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
    if browser_state is None:
        if update.callback_query is not None:
            await update.callback_query.edit_message_text("The song browser session expired.")
        elif update.effective_message is not None:
            await update.effective_message.reply_text("The song browser session expired.")
        return
    if browser_state["mode"] != mode:
        if update.callback_query is not None:
            await update.callback_query.edit_message_text("Song browser mode is out of sync.")
        return

    items = browser_state["items"]
    total = len(items)
    if total == 0:
        if update.callback_query is not None:
            await update.callback_query.edit_message_text("No songs to display.")
        elif update.effective_message is not None:
            await update.effective_message.reply_text("No songs to display.")
        return

    total_pages = (total + BROWSER_PAGE_SIZE - 1) // BROWSER_PAGE_SIZE
    normalized_page = min(max(page, 0), total_pages - 1)
    start = normalized_page * BROWSER_PAGE_SIZE
    end = start + BROWSER_PAGE_SIZE
    page_items = items[start:end]

    body_lines = [
        f"{browser_state['title']} ({total})",
        f"Page {normalized_page + 1}/{total_pages}",
    ]
    for item in page_items:
        body_lines.append(f"#{item['id']} {item['title']} | {item['artist_or_source']}")
    body_lines.append("Tap a song below.")
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
            InlineKeyboardButton("Prev", callback_data=f"browser:page:{mode_short}:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("Next", callback_data=f"browser:page:{mode_short}:{page + 1}")
        )
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton("Close", callback_data="browser:close")])
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
    await query.edit_message_text("Song details:\n" + format_song(song), reply_markup=keyboard)


def _song_detail_keyboard(*, song_id: int, page: int, is_admin: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("View Chart", callback_data=f"song:view:{song_id}")],
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton("Edit", callback_data=f"edit:start:{song_id}"),
                InlineKeyboardButton("Archive", callback_data=f"song:archive:{song_id}:{page}"),
            ]
        )
        rows.append([InlineKeyboardButton("Upload Chart", callback_data=f"upload:start:{song_id}")])
    rows.append([InlineKeyboardButton("Back to Results", callback_data=f"browser:page:b:{page}")])
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
        await query.answer("Admin access is required.", show_alert=True)
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
                    "Confirm Archive",
                    callback_data=f"song:archiveconfirm:{song_id}:{page}",
                )
            ],
            [InlineKeyboardButton("Back", callback_data=f"song:detail:{song_id}:{page}")],
        ]
    )
    await query.edit_message_text(
        f"Archive song #{song_id}: {song.title}?",
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
        await query.answer("Admin access is required.", show_alert=True)
        return

    service = get_song_service(context)
    try:
        song = await service.archive_song(song_id)
    except SongNotFoundError as error:
        await query.edit_message_text(str(error))
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back to Results", callback_data=f"browser:page:b:{page}")]]
    )
    await query.edit_message_text(
        f"Archived song #{song.id}: {song.title}",
        reply_markup=keyboard,
    )


def _browser_items(songs: list[Song]) -> list[BrowserItem]:
    items: list[BrowserItem] = []
    for song in songs:
        song_id = int(song.id)
        items.append(
            {
                "id": song_id,
                "title": song.title,
                "artist_or_source": song.artist_or_source,
            }
        )
    return items


def _active_browser_state(context: ContextTypes.DEFAULT_TYPE) -> BrowserState | None:
    value = _user_state(context).get(SONG_BROWSER_STATE_KEY)
    if isinstance(value, dict):
        state = cast(BrowserState, value)
        if "mode" in state and "title" in state and "items" in state:
            return state
    return None


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


def _parse_song_action(data: str, *, prefix: str) -> tuple[int, int] | None:
    if not data.startswith(prefix):
        return None
    parts = data[len(prefix) :].split(":")
    if len(parts) != 2:
        return None
    try:
        song_id = int(parts[0])
        page = int(parts[1])
    except ValueError:
        return None
    return song_id, page


def _parse_single_song_id(data: str, *, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    raw_song_id = data[len(prefix) :]
    try:
        return int(raw_song_id)
    except ValueError:
        return None


def _clear_search_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    _user_state(context).pop(SEARCH_PENDING_KEY, None)


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)
