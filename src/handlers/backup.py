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

from bot.runtime import get_backup_service
from handlers.common import ensure_admin, send_home_screen
from handlers.ui import CANCEL_BUTTON_PATTERN, cancel_markup, home_menu_markup
from services.repertoire_backup_service import BackupValidationError
from storage.chart_storage import ChartStorageError

IMPORT_BACKUP_UPLOAD = 0
IMPORT_BACKUP_STATE_KEY = "import_backup_state"


async def export_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update, context):
        return
    if update.effective_message is None:
        return

    service = get_backup_service(context)
    try:
        archive = await service.export_backup()
    except ChartStorageError:
        await update.effective_message.reply_text(
            "Backup export failed while reading chart binaries."
        )
        return

    await update.effective_message.reply_document(
        document=InputFile(BytesIO(archive.content), filename=archive.filename),
        caption=(
            f"Backup export complete.\nSongs: {archive.song_count}\nCharts: {archive.chart_count}"
        ),
    )


async def import_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    _user_state(context)[IMPORT_BACKUP_STATE_KEY] = {}
    await update.effective_message.reply_text(
        "Send a .zip backup file to import, or tap Cancel.",
        reply_markup=cancel_markup(update),
    )
    return IMPORT_BACKUP_UPLOAD


async def import_backup_start_from_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    return await import_backup_start(update, context)


async def import_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    document = update.effective_message.document
    if document is None:
        await update.effective_message.reply_text("Please send a .zip document file.")
        return IMPORT_BACKUP_UPLOAD
    if not _looks_like_zip(document.file_name, document.mime_type):
        await update.effective_message.reply_text("Backup import expects a .zip document file.")
        return IMPORT_BACKUP_UPLOAD

    telegram_file = await document.get_file()
    content = bytes(await telegram_file.download_as_bytearray())

    service = get_backup_service(context)
    try:
        summary = await service.import_backup(content)
    except (BackupValidationError, ChartStorageError, ValueError) as error:
        await update.effective_message.reply_text(f"Backup import failed: {error}")
        return ConversationHandler.END

    _user_state(context).pop(IMPORT_BACKUP_STATE_KEY, None)
    await update.effective_message.reply_text(
        (
            "Backup import complete.\n"
            f"Songs restored: {summary.song_count}\n"
            f"Charts restored: {summary.chart_count}"
        ),
        reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cancel_import_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context).pop(IMPORT_BACKUP_STATE_KEY, None)
    await send_home_screen(update, context, prefix="Cancelled.")
    return ConversationHandler.END


def build_import_backup_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                import_backup_start_from_callback,
                pattern=r"^backup:import:start$",
            ),
        ],
        states={
            IMPORT_BACKUP_UPLOAD: [
                MessageHandler(
                    filters.ALL
                    & ~filters.COMMAND
                    & ~filters.Regex(CANCEL_BUTTON_PATTERN)
                    & filters.UpdateType.MESSAGE,
                    import_backup_file,
                )
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(CANCEL_BUTTON_PATTERN)
                & ~filters.COMMAND
                & filters.UpdateType.MESSAGE,
                cancel_import_backup,
            ),
        ],
        name="import_backup",
        persistent=False,
    )


def _looks_like_zip(filename: str | None, mime_type: str | None) -> bool:
    if isinstance(filename, str) and filename.lower().endswith(".zip"):
        return True
    if isinstance(mime_type, str):
        return mime_type.lower() in {
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        }
    return False


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)
