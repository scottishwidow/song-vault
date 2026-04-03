from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
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

from bot.runtime import get_song_service
from handlers.common import ensure_admin
from models.song import Song
from services.song_service import (
    SongCreate,
    SongNotFoundError,
    SongUpdate,
    parse_tag_input,
)

ADD_TITLE, ADD_ARTIST, ADD_KEY, ADD_TEMPO, ADD_TAGS, ADD_NOTES = range(6)
EDIT_FIELD, EDIT_VALUE = range(2)
RESULT_MESSAGE_CHAR_LIMIT = 3500

PENDING_SONG_KEY = "pending_song"
EDIT_SONG_ID_KEY = "edit_song_id"
EDIT_FIELD_KEY = "edit_field"


@dataclass(frozen=True, slots=True)
class EditFieldSpec:
    label: str
    prompt: str
    format_current: Callable[[Song], str]
    parse_input: Callable[[str], SongUpdate]


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


def format_compact_song(song: Song) -> str:
    return f"#{song.id} {song.title} | {song.artist_or_source} | Key: {song.key}"


def _truncate_text(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _continuation_header(base_header: str, chunk_number: int, total_chunks: int) -> str:
    return f"{base_header} (cont. {chunk_number}/{total_chunks}):"


def _chunk_compact_lines(
    lines: list[str],
    *,
    first_header: str,
    continuation_header_base: str,
    total_chunks: int,
) -> list[list[str]]:
    chunks: list[list[str]] = []
    current_lines: list[str] = []
    chunk_number = 1

    for raw_line in lines:
        header = (
            first_header
            if chunk_number == 1
            else _continuation_header(continuation_header_base, chunk_number, total_chunks)
        )
        line = _truncate_text(raw_line, RESULT_MESSAGE_CHAR_LIMIT - len(header) - 1)
        candidate_lines = [*current_lines, line]
        candidate_body = "\n".join(candidate_lines)
        candidate_message = f"{header}\n{candidate_body}"
        if len(candidate_message) <= RESULT_MESSAGE_CHAR_LIMIT:
            current_lines = candidate_lines
            continue

        if current_lines:
            chunks.append(current_lines)
            chunk_number += 1
            current_lines = [line]
            continue

        current_lines = [line]

    if current_lines:
        chunks.append(current_lines)
    return chunks


def _build_compact_messages(
    lines: list[str],
    *,
    first_header: str,
    continuation_header_base: str,
) -> list[str]:
    total_chunks = 1
    while True:
        chunks = _chunk_compact_lines(
            lines,
            first_header=first_header,
            continuation_header_base=continuation_header_base,
            total_chunks=total_chunks,
        )
        if len(chunks) == total_chunks:
            break
        total_chunks = len(chunks)

    messages: list[str] = []
    for chunk_number, chunk_lines in enumerate(chunks, start=1):
        header = (
            first_header
            if chunk_number == 1
            else _continuation_header(continuation_header_base, chunk_number, total_chunks)
        )
        messages.append(f"{header}\n" + "\n".join(chunk_lines))
    return messages


async def _reply_song_results(
    update: Update,
    songs: list[Song],
    *,
    first_header: str,
    continuation_header_base: str,
) -> None:
    message = update.effective_message
    if message is None:
        return

    detailed_body = "\n\n".join(format_song(song) for song in songs)
    if len(detailed_body) <= RESULT_MESSAGE_CHAR_LIMIT:
        await message.reply_text(detailed_body)
        return

    compact_lines = [format_compact_song(song) for song in songs]
    compact_messages = _build_compact_messages(
        compact_lines,
        first_header=first_header,
        continuation_header_base=continuation_header_base,
    )
    for compact_message in compact_messages:
        await message.reply_text(compact_message)


def _message_text(update: Update) -> str:
    message = update.effective_message
    if message is None or message.text is None:
        return ""
    return message.text.strip()


def _user_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    return cast(dict[str, object], context.user_data)


def _parse_required_text(
    raw_value: str,
    *,
    label: str,
    build_update: Callable[[str], SongUpdate],
) -> SongUpdate:
    if not raw_value:
        raise ValueError(f"{label} cannot be empty. Send a non-empty value.")
    return build_update(raw_value)


def _parse_title_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="Title",
        build_update=lambda value: SongUpdate(title=value),
    )


def _parse_artist_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="Artist or source",
        build_update=lambda value: SongUpdate(artist_or_source=value),
    )


def _parse_key_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="Key",
        build_update=lambda value: SongUpdate(key=value),
    )


def _parse_tempo_update(raw_value: str) -> SongUpdate:
    if raw_value.lower() == "clear":
        return SongUpdate(tempo_bpm=None)
    if not raw_value:
        raise ValueError("Tempo must be a number or 'clear'.")
    try:
        return SongUpdate(tempo_bpm=int(raw_value))
    except ValueError as error:
        raise ValueError("Tempo must be a number or 'clear'.") from error


def _parse_tags_update(raw_value: str) -> SongUpdate:
    if raw_value.lower() == "clear":
        return SongUpdate(tags=[])
    if not raw_value:
        raise ValueError("Tags must be comma-separated values or 'clear'.")
    tags = parse_tag_input(raw_value)
    if not tags:
        raise ValueError("Tags must be comma-separated values or 'clear'.")
    return SongUpdate(tags=tags)


def _parse_notes_update(raw_value: str) -> SongUpdate:
    if raw_value.lower() == "clear":
        return SongUpdate(notes=None)
    if not raw_value:
        raise ValueError("Notes must be text or 'clear'.")
    return SongUpdate(notes=raw_value)


def _format_tempo(song: Song) -> str:
    return str(song.tempo_bpm) if song.tempo_bpm is not None else "-"


def _format_tags(song: Song) -> str:
    return ", ".join(song.tags) if song.tags else "-"


def _format_notes(song: Song) -> str:
    return song.notes or "-"


EDIT_FIELD_SPECS: dict[str, EditFieldSpec] = {
    "title": EditFieldSpec(
        label="title",
        prompt="New title?",
        format_current=lambda song: song.title,
        parse_input=_parse_title_update,
    ),
    "artist": EditFieldSpec(
        label="artist",
        prompt="New artist or source?",
        format_current=lambda song: song.artist_or_source,
        parse_input=_parse_artist_update,
    ),
    "key": EditFieldSpec(
        label="key",
        prompt="New key?",
        format_current=lambda song: song.key,
        parse_input=_parse_key_update,
    ),
    "tempo": EditFieldSpec(
        label="tempo",
        prompt="New tempo BPM? Use a number or 'clear'.",
        format_current=_format_tempo,
        parse_input=_parse_tempo_update,
    ),
    "tags": EditFieldSpec(
        label="tags",
        prompt="New comma-separated tags? Use 'clear' for none.",
        format_current=_format_tags,
        parse_input=_parse_tags_update,
    ),
    "notes": EditFieldSpec(
        label="notes",
        prompt="New notes? Use 'clear' for none.",
        format_current=_format_notes,
        parse_input=_parse_notes_update,
    ),
}


def _editable_field_list() -> str:
    return ", ".join(EDIT_FIELD_SPECS)


def _edit_field_previews(song: Song) -> str:
    return "\n".join(
        f"{field_name}: {spec.format_current(song)}"
        for field_name, spec in EDIT_FIELD_SPECS.items()
    )


def _edit_value_prompt(song: Song, field_name: str) -> str:
    spec = EDIT_FIELD_SPECS[field_name]
    return f"{spec.prompt}\nCurrent {spec.label}: {spec.format_current(song)}"


async def _reply_with_edit_value_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    song_id: int,
    field_name: str,
    error_message: str | None = None,
) -> int:
    if update.effective_message is None:
        return ConversationHandler.END
    if field_name not in EDIT_FIELD_SPECS:
        await update.effective_message.reply_text(
            "Edit state was lost. Start again with /editsong <id>."
        )
        return ConversationHandler.END

    service = get_song_service(context)
    try:
        song = await service.get_song(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    prompt = _edit_value_prompt(song, field_name)
    if error_message:
        prompt = f"{error_message}\n{prompt}"
    await update.effective_message.reply_text(prompt)
    return EDIT_VALUE


async def list_songs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = get_song_service(context)
    songs = await service.list_songs()
    if update.effective_message is None:
        return
    if not songs:
        await update.effective_message.reply_text("No active songs yet.")
        return
    count = len(songs)
    base_header = f"Active songs ({count})"
    await _reply_song_results(
        update,
        songs,
        first_header=base_header + ":",
        continuation_header_base=base_header,
    )


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

    count = len(songs)
    base_header = f'Matches for "{query}" ({count})'
    await _reply_song_results(
        update,
        songs,
        first_header=base_header + ":",
        continuation_header_base=base_header,
    )


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
        + "\n\nCurrent editable fields:\n"
        + _edit_field_previews(song)
        + "\n\nWhich field? Choose one of: "
        + _editable_field_list()
        + ".\nUse /cancel to stop."
    )
    return EDIT_FIELD


async def edit_song_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END
    field_name = _message_text(update).lower()
    if field_name not in EDIT_FIELD_SPECS:
        await update.effective_message.reply_text(
            "Invalid field. Choose one of: " + _editable_field_list() + "."
        )
        return EDIT_FIELD

    state = _user_state(context)
    song_id = state.get(EDIT_SONG_ID_KEY)
    if not isinstance(song_id, int):
        await update.effective_message.reply_text(
            "Edit state was lost. Start again with /editsong <id>."
        )
        return ConversationHandler.END

    state[EDIT_FIELD_KEY] = field_name
    return await _reply_with_edit_value_prompt(
        update,
        context,
        song_id=song_id,
        field_name=field_name,
    )


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
    if field_name not in EDIT_FIELD_SPECS:
        await update.effective_message.reply_text(
            "Edit state was lost. Start again with /editsong <id>."
        )
        return ConversationHandler.END

    try:
        update_payload = _build_update_payload(field_name, _message_text(update))
    except ValueError as error:
        return await _reply_with_edit_value_prompt(
            update,
            context,
            song_id=song_id,
            field_name=field_name,
            error_message=str(error),
        )

    service = get_song_service(context)
    try:
        song = await service.update_song(song_id, update_payload)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END
    except ValueError as error:
        return await _reply_with_edit_value_prompt(
            update,
            context,
            song_id=song_id,
            field_name=field_name,
            error_message=str(error),
        )

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
    spec = EDIT_FIELD_SPECS.get(field_name)
    if spec is None:
        raise ValueError(f"Unsupported field: {field_name}")
    return spec.parse_input(raw_value)


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
