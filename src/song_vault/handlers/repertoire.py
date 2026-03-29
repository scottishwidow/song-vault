from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, cast

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    BaseHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from song_vault.bot.runtime import get_song_service
from song_vault.handlers.common import ensure_admin
from song_vault.models.song import Song
from song_vault.services.song_service import (
    SongCreate,
    SongNotFoundError,
    SongUpdate,
    parse_tag_input,
)

ADD_TITLE, ADD_ARTIST, ADD_KEY, ADD_TEMPO, ADD_TAGS, ADD_NOTES = range(6)
EDIT_FIELD, EDIT_VALUE = range(2)

PENDING_SONG_KEY = "pending_song"
EDIT_SONG_ID_KEY = "edit_song_id"
EDIT_FIELD_KEY = "edit_field"
EDITABLE_FIELDS = {"title", "artist", "key", "tempo", "tags", "notes"}


def format_song(song: Song) -> str:
    tag_text = ", ".join(song.tags) if song.tags else "-"
    tempo_text = str(song.tempo_bpm) if song.tempo_bpm is not None else "-"
    notes_text = song.notes or "-"
    return (
        f"#{song.id} {song.title}\n"
        f"Source: {song.artist_or_source}\n"
        f"Key: {song.key}\n"
        f"Tempo: {tempo_text}\n"
        f"Tags: {tag_text}\n"
        f"Notes: {notes_text}\n"
        f"Status: {song.status.value}"
    )


def _message_text(update: Update) -> str:
    message = update.effective_message
    if message is None or message.text is None:
        return ""
    return message.text.strip()


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)


async def list_songs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = get_song_service(context)
    songs = await service.list_songs()
    if update.effective_message is None:
        return
    if not songs:
        await update.effective_message.reply_text("No active songs yet.")
        return
    body = "\n\n".join(format_song(song) for song in songs)
    await update.effective_message.reply_text(body)


async def search_songs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    query = " ".join(context.args or []).strip()
    if not query:
        await update.effective_message.reply_text("Usage: /search <text>")
        return

    service = get_song_service(context)
    songs = await service.search_songs(query)
    if not songs:
        await update.effective_message.reply_text("No matching songs found.")
        return

    body = "\n\n".join(format_song(song) for song in songs)
    await update.effective_message.reply_text(body)


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    service = get_song_service(context)
    tags = await service.list_tags()
    if not tags:
        await update.effective_message.reply_text("No tags found yet.")
        return
    await update.effective_message.reply_text("Tags: " + ", ".join(tags))


async def archive_song_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update, context):
        return
    if update.effective_message is None:
        return
    song_id = _parse_song_id(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Usage: /archivesong <id>")
        return

    service = get_song_service(context)
    try:
        song = await service.archive_song(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return

    await update.effective_message.reply_text(f"Archived song #{song.id}: {song.title}")


def _parse_song_id(args: list[str]) -> int | None:
    if len(args) != 1:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context).pop(PENDING_SONG_KEY, None)
    _user_state(context).pop(EDIT_SONG_ID_KEY, None)
    _user_state(context).pop(EDIT_FIELD_KEY, None)
    if update.effective_message is not None:
        await update.effective_message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def add_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    _user_state(context)[PENDING_SONG_KEY] = {}
    if update.effective_message is not None:
        await update.effective_message.reply_text("Title?")
    return ADD_TITLE


async def add_song_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context)[PENDING_SONG_KEY] = {"title": _message_text(update)}
    if update.effective_message is not None:
        await update.effective_message.reply_text("Artist or source?")
    return ADD_ARTIST


async def add_song_artist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    payload["artist_or_source"] = _message_text(update)
    if update.effective_message is not None:
        await update.effective_message.reply_text("Key?")
    return ADD_KEY


async def add_song_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    payload["key"] = _message_text(update)
    if update.effective_message is not None:
        await update.effective_message.reply_text("Tempo BPM? Send a number or 'skip'.")
    return ADD_TEMPO


async def add_song_tempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    if text.lower() == "skip":
        payload["tempo_bpm"] = None
    else:
        try:
            payload["tempo_bpm"] = int(text)
        except ValueError:
            if update.effective_message is not None:
                await update.effective_message.reply_text("Tempo must be a number or 'skip'.")
            return ADD_TEMPO
    if update.effective_message is not None:
        await update.effective_message.reply_text("Tags? Send comma-separated values or 'skip'.")
    return ADD_TAGS


async def add_song_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    payload["tags"] = [] if text.lower() == "skip" else parse_tag_input(text)
    if update.effective_message is not None:
        await update.effective_message.reply_text("Notes? Send text or 'skip'.")
    return ADD_NOTES


async def add_song_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    notes = None if text.lower() == "skip" else text
    service = get_song_service(context)
    try:
        song = await service.create_song(
            SongCreate(
                title=str(payload["title"]),
                artist_or_source=str(payload["artist_or_source"]),
                key=str(payload["key"]),
                tempo_bpm=cast(int | None, payload.get("tempo_bpm")),
                tags=cast(list[str], payload.get("tags", [])),
                notes=notes,
            )
        )
    except ValueError as error:
        if update.effective_message is not None:
            await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context).pop(PENDING_SONG_KEY, None)
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Created song:\n" + format_song(song),
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


async def edit_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    song_id = _parse_song_id(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Usage: /editsong <id>")
        return ConversationHandler.END

    service = get_song_service(context)
    try:
        song = await service.get_song(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context)[EDIT_SONG_ID_KEY] = song_id
    await update.effective_message.reply_text(
        "Editing song:\n"
        + format_song(song)
        + "\n\nWhich field? Choose one of: title, artist, key, tempo, tags, notes."
    )
    return EDIT_FIELD


async def edit_song_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END
    field_name = _message_text(update).lower()
    if field_name not in EDITABLE_FIELDS:
        await update.effective_message.reply_text(
            "Invalid field. Choose one of: title, artist, key, tempo, tags, notes."
        )
        return EDIT_FIELD

    _user_state(context)[EDIT_FIELD_KEY] = field_name
    prompt = {
        "title": "New title?",
        "artist": "New artist or source?",
        "key": "New key?",
        "tempo": "New tempo BPM? Use a number or 'clear'.",
        "tags": "New comma-separated tags? Use 'clear' for none.",
        "notes": "New notes? Use 'clear' for none.",
    }[field_name]
    await update.effective_message.reply_text(prompt)
    return EDIT_VALUE


async def edit_song_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    state = _user_state(context)
    song_id = state.get(EDIT_SONG_ID_KEY)
    field_name = state.get(EDIT_FIELD_KEY)
    if not isinstance(song_id, int) or not isinstance(field_name, str):
        await update.effective_message.reply_text(
            "Edit state was lost. Start again with /editsong <id>."
        )
        return ConversationHandler.END

    try:
        update_payload = _build_update_payload(field_name, _message_text(update))
        service = get_song_service(context)
        song = await service.update_song(song_id, update_payload)
    except (SongNotFoundError, ValueError) as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    state.pop(EDIT_SONG_ID_KEY, None)
    state.pop(EDIT_FIELD_KEY, None)
    await update.effective_message.reply_text(
        "Updated song:\n" + format_song(song),
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def _pending_song(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    payload = _user_state(context).get(PENDING_SONG_KEY)
    if isinstance(payload, dict):
        return payload
    new_payload: dict[str, object] = {}
    _user_state(context)[PENDING_SONG_KEY] = new_payload
    return new_payload


def _build_update_payload(field_name: str, raw_value: str) -> SongUpdate:
    if field_name == "title":
        return SongUpdate(title=raw_value)
    if field_name == "artist":
        return SongUpdate(artist_or_source=raw_value)
    if field_name == "key":
        return SongUpdate(key=raw_value)
    if field_name == "tempo":
        if raw_value.lower() == "clear":
            return SongUpdate(tempo_bpm=None)
        return SongUpdate(tempo_bpm=int(raw_value))
    if field_name == "tags":
        tags = [] if raw_value.lower() == "clear" else parse_tag_input(raw_value)
        return SongUpdate(tags=tags)
    if field_name == "notes":
        return SongUpdate(notes=None if raw_value.lower() == "clear" else raw_value)
    raise ValueError(f"Unsupported field: {field_name}")


def _conversation_fallbacks() -> list[BaseHandler]:
    return [CommandHandler("cancel", cancel_command)]


def _text_step(
    callback: Callable[
        [Update, ContextTypes.DEFAULT_TYPE],
        Coroutine[Any, Any, object],
    ],
) -> BaseHandler:
    return MessageHandler(filters.TEXT & ~filters.COMMAND, callback)


def build_add_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("addsong", add_song_start)],
        states={
            ADD_TITLE: [_text_step(add_song_title)],
            ADD_ARTIST: [_text_step(add_song_artist)],
            ADD_KEY: [_text_step(add_song_key)],
            ADD_TEMPO: [_text_step(add_song_tempo)],
            ADD_TAGS: [_text_step(add_song_tags)],
            ADD_NOTES: [_text_step(add_song_notes)],
        },
        fallbacks=_conversation_fallbacks(),
        name="add_song",
        persistent=False,
    )


def build_edit_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("editsong", edit_song_start)],
        states={
            EDIT_FIELD: [_text_step(edit_song_field)],
            EDIT_VALUE: [_text_step(edit_song_value)],
        },
        fallbacks=_conversation_fallbacks(),
        name="edit_song",
        persistent=False,
    )
