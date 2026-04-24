from __future__ import annotations

from io import BytesIO

from telegram import InputFile, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.runtime import get_backup_service
from handlers.common import ensure_admin, send_home_screen
from handlers.conversation import (
    backup_outcome_keyboard,
    cancel_message_fallback,
    conversation_message_filter,
    home_or_remove_markup,
    user_state,
)
from handlers.ui import cancel_markup
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
            "Не вдалося експортувати резервну копію під час читання файлів акордів."
        )
        return

    await update.effective_message.reply_document(
        document=InputFile(BytesIO(archive.content), filename=archive.filename),
        caption=(
            "Експорт резервної копії завершено.\n"
            f"Пісень: {archive.song_count}\n"
            f"Акордів: {archive.chart_count}"
        ),
    )
    await update.effective_message.reply_text(
        "Експорт резервної копії завершено.",
        reply_markup=home_or_remove_markup(update, context),
    )
    await update.effective_message.reply_text(
        "Що далі?",
        reply_markup=backup_outcome_keyboard(),
    )


async def import_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    user_state(context)[IMPORT_BACKUP_STATE_KEY] = {}
    await update.effective_message.reply_text(
        "Надішліть .zip файл резервної копії для імпорту або натисніть «Скасувати».",
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
        await update.effective_message.reply_text("Надішліть .zip файл документом.")
        return IMPORT_BACKUP_UPLOAD
    if not _looks_like_zip(document.file_name, document.mime_type):
        await update.effective_message.reply_text(
            "Імпорт резервної копії очікує .zip файл документом."
        )
        return IMPORT_BACKUP_UPLOAD

    telegram_file = await document.get_file()
    content = bytes(await telegram_file.download_as_bytearray())

    service = get_backup_service(context)
    try:
        summary = await service.import_backup(content)
    except (BackupValidationError, ChartStorageError, ValueError) as error:
        await update.effective_message.reply_text(f"Помилка імпорту резервної копії: {error}")
        return ConversationHandler.END

    user_state(context).pop(IMPORT_BACKUP_STATE_KEY, None)
    await update.effective_message.reply_text(
        (
            "Імпорт резервної копії завершено.\n"
            f"Відновлено пісень: {summary.song_count}\n"
            f"Відновлено акордів: {summary.chart_count}"
        ),
        reply_markup=home_or_remove_markup(update, context),
    )
    await update.effective_message.reply_text(
        "Що далі?",
        reply_markup=backup_outcome_keyboard(),
    )
    return ConversationHandler.END


async def cancel_import_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_state(context).pop(IMPORT_BACKUP_STATE_KEY, None)
    await send_home_screen(update, context, prefix="Скасовано.")
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
                    conversation_message_filter(filters.ALL),
                    import_backup_file,
                )
            ],
        },
        fallbacks=[cancel_message_fallback(cancel_import_backup)],
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
