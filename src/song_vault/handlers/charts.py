from __future__ import annotations

from io import BytesIO
from typing import cast
from urllib.parse import urlparse

from telegram import InputFile, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from song_vault.bot.runtime import get_chart_service
from song_vault.handlers.common import ensure_admin
from song_vault.services.chart_service import ChartFile, ChartUpload, SongChartNotFoundError
from song_vault.services.song_service import SongNotFoundError
from song_vault.storage.chart_storage import ChartStorageError

UPLOAD_MEDIA, UPLOAD_SOURCE_URL, UPLOAD_CHART_KEY = range(3)
UPLOAD_CHART_STATE_KEY = "upload_chart_state"


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return

    song_id = _parse_song_id(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Usage: /chart <song_id>")
        return

    service = get_chart_service(context)
    try:
        chart_file = await service.get_active_chart_file(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return
    except SongChartNotFoundError:
        await update.effective_message.reply_text(f"No chart uploaded yet for song #{song_id}.")
        return
    except ChartStorageError:
        await update.effective_message.reply_text("Could not load chart binary from storage.")
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
        await update.effective_message.reply_text("Usage: /uploadchart <song_id>")
        return ConversationHandler.END

    service = get_chart_service(context)
    try:
        await service.assert_song_exists(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context)[UPLOAD_CHART_STATE_KEY] = {"song_id": song_id}
    await update.effective_message.reply_text("Send the chart image as a photo or image document.")
    return UPLOAD_MEDIA


async def upload_chart_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    state = _upload_state(context)
    song_id = state.get("song_id")
    if not isinstance(song_id, int):
        await update.effective_message.reply_text(
            "Upload state was lost. Start again with /uploadchart <song_id>."
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
            "Please send a photo or image document (for example image/png)."
        )
        return UPLOAD_MEDIA

    state["content"] = content
    state["content_type"] = content_type
    state["filename"] = filename
    await update.effective_message.reply_text("Optional source URL? Send an http(s) URL or 'skip'.")
    return UPLOAD_SOURCE_URL


async def upload_chart_source_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    text = (update.effective_message.text or "").strip()
    if text.lower() == "skip":
        source_url: str | None = None
    else:
        if not _looks_like_http_url(text):
            await update.effective_message.reply_text(
                "Source URL must start with http:// or https://, or send 'skip'."
            )
            return UPLOAD_SOURCE_URL
        source_url = text

    state = _upload_state(context)
    state["source_url"] = source_url
    await update.effective_message.reply_text("Optional chart key? Send text or 'skip'.")
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
    source_url = state.get("source_url")
    if (
        not isinstance(song_id, int)
        or not isinstance(content, bytes)
        or not isinstance(content_type, str)
        or not isinstance(filename, str)
    ):
        await update.effective_message.reply_text(
            "Upload state was lost. Start again with /uploadchart <song_id>."
        )
        return ConversationHandler.END

    raw_key = (update.effective_message.text or "").strip()
    chart_key = None if raw_key.lower() == "skip" else raw_key
    try:
        chart = await chart_service.upload_chart(
            song_id,
            ChartUpload(
                original_filename=filename,
                content_type=content_type,
                content=content,
                source_url=source_url if isinstance(source_url, str) else None,
                chart_key=chart_key,
            ),
        )
    except (SongNotFoundError, ValueError, ChartStorageError) as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
    await update.effective_message.reply_text(
        f"Uploaded chart #{chart.id} for song #{song_id}.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cancel_upload_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context).pop(UPLOAD_CHART_STATE_KEY, None)
    if update.effective_message is not None:
        await update.effective_message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def build_upload_chart_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("uploadchart", upload_chart_start)],
        states={
            UPLOAD_MEDIA: [MessageHandler(filters.ALL & ~filters.COMMAND, upload_chart_media)],
            UPLOAD_SOURCE_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_chart_source_url)
            ],
            UPLOAD_CHART_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_chart_chart_key)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_upload_chart)],
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


def _looks_like_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _upload_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    state = _user_state(context).get(UPLOAD_CHART_STATE_KEY)
    if isinstance(state, dict):
        return state
    fresh_state: dict[str, object] = {}
    _user_state(context)[UPLOAD_CHART_STATE_KEY] = fresh_state
    return fresh_state


def _chart_caption(chart_file: ChartFile) -> str:
    lines = [
        f"Song #{chart_file.song_id}: {chart_file.song_title}",
    ]
    if chart_file.chart_key:
        lines.append(f"Chart key: {chart_file.chart_key}")
    if chart_file.source_url:
        lines.append(f"Source: {chart_file.source_url}")
    return "\n".join(lines)


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)
