from __future__ import annotations

from io import BytesIO

from telegram import InputFile, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.runtime import get_chart_service
from handlers.common import ensure_admin, send_home_screen
from handlers.conversation import (
    cancel_message_fallback,
    conversation_message_filter,
    home_or_remove_markup,
    parse_callback_int,
    parse_song_id_arg,
    reply_state_lost,
    song_outcome_keyboard,
    user_state,
)
from handlers.messages import NEXT_ACTIONS_MESSAGE
from handlers.ui import BUTTON_SKIP, cancel_markup, skip_cancel_markup
from services.chart_service import ChartFile, ChartUpload, SongChartNotFoundError
from services.song_service import SongNotFoundError
from storage.chart_storage import ChartStorageError

UPLOAD_MEDIA, UPLOAD_CHART_KEY = range(2)
UPLOAD_CHART_STATE_KEY = "upload_chart_state"
TELEGRAM_PHOTO_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    song_id = parse_song_id_arg(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Використання: /chart <id_пісні>")
        return
    await send_chart_for_song_id(update, context, song_id)


async def send_chart_for_song_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    song_id: int,
) -> None:
    if update.effective_message is None:
        return

    service = get_chart_service(context)
    try:
        chart_file = await service.get_active_chart_file(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return
    except SongChartNotFoundError:
        await update.effective_message.reply_text(
            f"Для пісні #{song_id} ще не завантажено гармонію."
        )
        return
    except ChartStorageError:
        await update.effective_message.reply_text(
            "Не вдалося завантажити файл гармонії зі сховища."
        )
        return

    caption = _chart_caption(chart_file)
    if _can_send_as_photo(chart_file):
        try:
            await update.effective_message.reply_photo(
                photo=_chart_input_file(chart_file),
                caption=caption,
            )
            return
        except TelegramError:
            pass

    await update.effective_message.reply_document(
        document=_chart_input_file(chart_file),
        caption=caption,
    )


async def upload_chart_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    song_id = parse_song_id_arg(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Використання: /uploadchart <id_пісні>")
        return ConversationHandler.END
    return await _begin_upload_for_song_id(update, context, song_id)


async def upload_chart_start_from_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    song_id = parse_callback_int(query.data, prefix="upload:start:")
    if song_id is None:
        if update.effective_message is not None:
            await update.effective_message.reply_text("Не вдалося розпізнати вибір пісні.")
        return ConversationHandler.END
    return await _begin_upload_for_song_id(update, context, song_id)


async def _begin_upload_for_song_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    song_id: int,
) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    service = get_chart_service(context)
    try:
        await service.assert_song_exists(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    user_state(context)[UPLOAD_CHART_STATE_KEY] = {
        "song_id": song_id,
        "return_mode": "upload",
        "return_page": _browser_return_page(context),
    }
    await update.effective_message.reply_text(
        f"Ціль завантаження: пісня #{song_id}.\nНадішліть зображення гармонії як фото або файл.",
        reply_markup=cancel_markup(update),
    )
    return UPLOAD_MEDIA


async def upload_chart_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    state = _upload_state(context)
    song_id = state.get("song_id")
    if not isinstance(song_id, int):
        await reply_state_lost(
            update,
            context,
            "Стан завантаження втрачено. Почніть знову через «Завантажити гармонію».",
        )
        return ConversationHandler.END

    content: bytes
    content_type: str
    filename: str
    photo = update.effective_message.photo
    document = update.effective_message.document
    if photo:
        telegram_file = await photo[-1].get_file()
        content = bytes(await telegram_file.download_as_bytearray())
        content_type = "image/jpeg"
        filename = f"song-{song_id}-chart.jpg"
    elif document is not None and (document.mime_type or "").startswith("image/"):
        telegram_file = await document.get_file()
        content = bytes(await telegram_file.download_as_bytearray())
        content_type = document.mime_type or "application/octet-stream"
        filename = document.file_name or f"song-{song_id}-chart"
    else:
        await update.effective_message.reply_text(
            "Надішліть фото або зображення-документ гармонії (наприклад, image/png)."
        )
        return UPLOAD_MEDIA

    state["content"] = content
    state["content_type"] = content_type
    state["filename"] = filename
    await update.effective_message.reply_text(
        "Тональність гармонії необов'язкова. Надішліть текст або «Пропустити».",
        reply_markup=skip_cancel_markup(update),
    )
    return UPLOAD_CHART_KEY


async def upload_chart_chart_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    chart_service = get_chart_service(context)
    state = _upload_state(context)
    song_id = state.get("song_id")
    return_mode = state.get("return_mode")
    return_page = state.get("return_page")
    content = state.get("content")
    content_type = state.get("content_type")
    filename = state.get("filename")
    if (
        not isinstance(song_id, int)
        or not isinstance(content, bytes)
        or not isinstance(content_type, str)
        or not isinstance(filename, str)
    ):
        await reply_state_lost(
            update,
            context,
            "Стан завантаження втрачено. Почніть знову через «Завантажити гармонію».",
        )
        return ConversationHandler.END

    list_mode_short = "u" if return_mode == "upload" else "b"
    if not isinstance(return_page, int) or return_page < 0:
        return_page = 0

    raw_key = (update.effective_message.text or "").strip()
    chart_key = None if raw_key.lower() == BUTTON_SKIP.lower() else raw_key
    try:
        chart = await chart_service.upload_chart(
            song_id,
            ChartUpload(
                original_filename=filename,
                content_type=content_type,
                content=content,
                source_url=None,
                chart_key=chart_key,
            ),
        )
    except (SongNotFoundError, ValueError, ChartStorageError) as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
    await update.effective_message.reply_text(
        f"Гармонію #{chart.id} для пісні #{song_id} завантажено.",
        reply_markup=home_or_remove_markup(update, context),
    )
    await update.effective_message.reply_text(
        NEXT_ACTIONS_MESSAGE,
        reply_markup=song_outcome_keyboard(
            song_id=song_id,
            page=return_page,
            list_mode_short=list_mode_short,
        ),
    )
    return ConversationHandler.END


async def cancel_upload_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
    await send_home_screen(update, context, prefix="Скасовано.")
    return ConversationHandler.END


def build_upload_chart_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(upload_chart_start_from_callback, pattern=r"^upload:start:\d+$"),
        ],
        states={
            UPLOAD_MEDIA: [
                MessageHandler(
                    conversation_message_filter(filters.ALL),
                    upload_chart_media,
                )
            ],
            UPLOAD_CHART_KEY: [
                MessageHandler(
                    conversation_message_filter(),
                    upload_chart_chart_key,
                )
            ],
        },
        fallbacks=[cancel_message_fallback(cancel_upload_chart)],
        name="upload_chart",
        persistent=False,
    )


def _upload_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    state = user_state(context).get(UPLOAD_CHART_STATE_KEY)
    if isinstance(state, dict):
        return state
    fresh_state: dict[str, object] = {}
    user_state(context)[UPLOAD_CHART_STATE_KEY] = fresh_state
    return fresh_state


def _browser_return_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    browser_state = user_state(context).get("song_browser_state")
    if not isinstance(browser_state, dict):
        return 0
    raw_page = browser_state.get("current_page")
    if isinstance(raw_page, int) and raw_page >= 0:
        return raw_page
    return 0


def _chart_caption(chart_file: ChartFile) -> str:
    lines = [
        f"Пісня #{chart_file.song_id}: {chart_file.song_title}",
    ]
    if chart_file.chart_key:
        lines.append(f"Тональність гармонії: {chart_file.chart_key}")
    if chart_file.source_url:
        lines.append(f"Джерело гармонії: {chart_file.source_url}")
    return "\n".join(lines)


def _chart_input_file(chart_file: ChartFile) -> InputFile:
    return InputFile(BytesIO(chart_file.content), filename=chart_file.original_filename)


def _can_send_as_photo(chart_file: ChartFile) -> bool:
    content_type = chart_file.content_type.split(";", maxsplit=1)[0].strip().lower()
    return content_type in TELEGRAM_PHOTO_CONTENT_TYPES
