from __future__ import annotations

from io import BytesIO
from typing import cast

from telegram import InputFile, ReplyKeyboardRemove, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.runtime import get_chart_service
from handlers.common import ensure_admin, send_home_screen
from handlers.ui import BUTTON_SKIP, CANCEL_BUTTON_PATTERN, cancel_markup, home_menu_markup
from services.chart_service import ChartFile, ChartUpload, SongChartNotFoundError
from services.song_service import SongNotFoundError
from storage.chart_storage import ChartStorageError

UPLOAD_MEDIA, UPLOAD_CHART_KEY = range(2)
UPLOAD_CHART_STATE_KEY = "upload_chart_state"


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    song_id = _parse_song_id(context.args or [])
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
        await update.effective_message.reply_text(f"Для пісні #{song_id} ще не завантажено акорди.")
        return
    except ChartStorageError:
        await update.effective_message.reply_text("Не вдалося завантажити файл акордів зі сховища.")
        return

    caption = _chart_caption(chart_file)
    file_stream = BytesIO(chart_file.content)
    await update.effective_message.reply_document(
        document=InputFile(file_stream, filename=chart_file.original_filename),
        caption=caption,
    )


async def upload_chart_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    song_id = _parse_song_id(context.args or [])
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
    song_id = _song_id_from_callback(query.data, prefix="upload:start:")
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

    _user_state(context)[UPLOAD_CHART_STATE_KEY] = {"song_id": song_id}
    await update.effective_message.reply_text(
        f"Ціль завантаження: пісня #{song_id}.\nНадішліть зображення акордів як фото або файл.",
        reply_markup=cancel_markup(update),
    )
    return UPLOAD_MEDIA


async def upload_chart_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    state = _upload_state(context)
    song_id = state.get("song_id")
    if not isinstance(song_id, int):
        await update.effective_message.reply_text(
            "Стан завантаження втрачено. Почніть знову через «Завантажити гармонію».",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
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
            "Надішліть фото або зображення-документ (наприклад, image/png)."
        )
        return UPLOAD_MEDIA

    state["content"] = content
    state["content_type"] = content_type
    state["filename"] = filename
    await update.effective_message.reply_text(
        "Тональність акордів необов'язкова. Надішліть текст або «Пропустити».",
        reply_markup=cancel_markup(update),
    )
    return UPLOAD_CHART_KEY


async def upload_chart_chart_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    chart_service = get_chart_service(context)
    state = _upload_state(context)
    song_id = state.get("song_id")
    content = state.get("content")
    content_type = state.get("content_type")
    filename = state.get("filename")
    if (
        not isinstance(song_id, int)
        or not isinstance(content, bytes)
        or not isinstance(content_type, str)
        or not isinstance(filename, str)
    ):
        await update.effective_message.reply_text(
            "Стан завантаження втрачено. Почніть знову через «Завантажити гармонію».",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

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

    _user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
    await update.effective_message.reply_text(
        f"Акорди #{chart.id} для пісні #{song_id} завантажено.",
        reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cancel_upload_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
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
                    filters.ALL
                    & ~filters.COMMAND
                    & ~filters.Regex(CANCEL_BUTTON_PATTERN)
                    & filters.UpdateType.MESSAGE,
                    upload_chart_media,
                )
            ],
            UPLOAD_CHART_KEY: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND
                    & ~filters.Regex(CANCEL_BUTTON_PATTERN)
                    & filters.UpdateType.MESSAGE,
                    upload_chart_chart_key,
                )
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(CANCEL_BUTTON_PATTERN)
                & ~filters.COMMAND
                & filters.UpdateType.MESSAGE,
                cancel_upload_chart,
            ),
        ],
        name="upload_chart",
        persistent=False,
    )


def _parse_song_id(args: list[str]) -> int | None:
    if len(args) != 1:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


def _song_id_from_callback(data: str | None, *, prefix: str) -> int | None:
    if not isinstance(data, str):
        return None
    if not data.startswith(prefix):
        return None
    raw_value = data[len(prefix) :]
    try:
        return int(raw_value)
    except ValueError:
        return None


def _upload_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    state = _user_state(context).get(UPLOAD_CHART_STATE_KEY)
    if isinstance(state, dict):
        return state
    fresh_state: dict[str, object] = {}
    _user_state(context)[UPLOAD_CHART_STATE_KEY] = fresh_state
    return fresh_state


def _chart_caption(chart_file: ChartFile) -> str:
    lines = [
        f"Пісня #{chart_file.song_id}: {chart_file.song_title}",
    ]
    if chart_file.chart_key:
        lines.append(f"Тональність акордів: {chart_file.chart_key}")
    if chart_file.source_url:
        lines.append(f"Джерело акордів: {chart_file.source_url}")
    return "\n".join(lines)


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)
