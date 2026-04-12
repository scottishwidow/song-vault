from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    BaseHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.runtime import get_song_service
from handlers.common import ensure_admin, send_home_screen
from handlers.ui import (
    BUTTON_SKIP,
    CANCEL_BUTTON_PATTERN,
    MENU_ADD_SONG,
    cancel_markup,
    home_menu_markup,
    skip_cancel_markup,
)
from models.song import Song, SongStatus
from services.song_service import (
    SongCreate,
    SongNotFoundError,
    SongUpdate,
    parse_tag_input,
)

(
    ADD_TITLE,
    ADD_ARTIST,
    ADD_SOURCE,
    ADD_KEY,
    ADD_CAPO,
    ADD_TIME_SIGNATURE,
    ADD_TEMPO,
    ADD_TAGS,
    ADD_NOTES,
    ADD_ARRANGEMENT_NOTES,
) = range(10)
EDIT_FIELD, EDIT_VALUE = range(2)
RESULT_MESSAGE_CHAR_LIMIT = 3500
CLEAR_INPUT = "очистити"

PENDING_SONG_KEY = "pending_song"
EDIT_SONG_ID_KEY = "edit_song_id"
EDIT_FIELD_KEY = "edit_field"


@dataclass(frozen=True, slots=True)
class EditFieldSpec:
    label: str
    prompt: str
    format_current: Callable[[Song], str]
    parse_input: Callable[[str], SongUpdate]
    aliases: tuple[str, ...]


def format_song(song: Song) -> str:
    capo_text = str(song.capo) if song.capo is not None else "-"
    source_text = song.source_url or "-"
    time_signature_text = song.time_signature or "-"
    tag_text = ", ".join(song.tags) if song.tags else "-"
    tempo_text = str(song.tempo_bpm) if song.tempo_bpm is not None else "-"
    notes_text = song.notes or "-"
    arrangement_notes_text = song.arrangement_notes or "-"
    return (
        f"#{song.id} {song.title}\n"
        f"Виконавець: {song.artist}\n"
        f"Джерело: {source_text}\n"
        f"Тональність: {song.key}\n"
        f"Каподастр: {capo_text}\n"
        f"Розмір: {time_signature_text}\n"
        f"Темп: {tempo_text}\n"
        f"Теги: {tag_text}\n"
        f"Нотатки: {notes_text}\n"
        f"Нотатки аранжування: {arrangement_notes_text}\n"
        f"Статус: {_status_label(song.status)}"
    )


def format_compact_song(song: Song) -> str:
    return f"#{song.id} {song.title} | {song.artist} | Тональність: {song.key}"


def _status_label(status: SongStatus) -> str:
    labels = {
        SongStatus.ACTIVE: "активна",
        SongStatus.ARCHIVED: "архівована",
    }
    return labels[status]


def _truncate_text(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _continuation_header(base_header: str, chunk_number: int, total_chunks: int) -> str:
    return f"{base_header} (продовження {chunk_number}/{total_chunks}):"


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
        raise ValueError(f"Поле «{label}» не може бути порожнім. Надішліть непорожнє значення.")
    return build_update(raw_value)


def _parse_title_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="назва",
        build_update=lambda value: SongUpdate(title=value),
    )


def _parse_artist_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="виконавець",
        build_update=lambda value: SongUpdate(artist=value),
    )


def _parse_source_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(source_url=None)
    if not raw_value:
        raise ValueError("Джерело має бути текстом або «очистити».")
    return SongUpdate(source_url=raw_value)


def _parse_key_update(raw_value: str) -> SongUpdate:
    return _parse_required_text(
        raw_value,
        label="тональність",
        build_update=lambda value: SongUpdate(key=value),
    )


def _parse_tempo_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(tempo_bpm=None)
    if not raw_value:
        raise ValueError("Темп має бути числом або «очистити».")
    try:
        return SongUpdate(tempo_bpm=int(raw_value))
    except ValueError as error:
        raise ValueError("Темп має бути числом або «очистити».") from error


def _parse_capo_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(capo=None)
    if not raw_value:
        raise ValueError("Каподастр має бути додатним числом або «очистити».")
    try:
        capo = int(raw_value)
    except ValueError as error:
        raise ValueError("Каподастр має бути додатним числом або «очистити».") from error
    if capo <= 0:
        raise ValueError("Каподастр має бути додатним числом або «очистити».")
    return SongUpdate(capo=capo)


def _parse_time_signature_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(time_signature=None)
    if not raw_value:
        raise ValueError("Розмір має бути текстом або «очистити».")
    return SongUpdate(time_signature=raw_value)


def _parse_tags_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(tags=[])
    if not raw_value:
        raise ValueError("Теги мають бути значеннями через кому або «очистити».")
    tags = parse_tag_input(raw_value)
    if not tags:
        raise ValueError("Теги мають бути значеннями через кому або «очистити».")
    return SongUpdate(tags=tags)


def _parse_notes_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(notes=None)
    if not raw_value:
        raise ValueError("Нотатки мають бути текстом або «очистити».")
    return SongUpdate(notes=raw_value)


def _parse_arrangement_notes_update(raw_value: str) -> SongUpdate:
    if _is_clear(raw_value):
        return SongUpdate(arrangement_notes=None)
    if not raw_value:
        raise ValueError("Нотатки аранжування мають бути текстом або «очистити».")
    return SongUpdate(arrangement_notes=raw_value)


def _is_clear(raw_value: str) -> bool:
    return raw_value.lower() == CLEAR_INPUT


def _format_capo(song: Song) -> str:
    return str(song.capo) if song.capo is not None else "-"


def _format_time_signature(song: Song) -> str:
    return song.time_signature or "-"


def _format_source(song: Song) -> str:
    return song.source_url or "-"


def _format_tempo(song: Song) -> str:
    return str(song.tempo_bpm) if song.tempo_bpm is not None else "-"


def _format_tags(song: Song) -> str:
    return ", ".join(song.tags) if song.tags else "-"


def _format_notes(song: Song) -> str:
    return song.notes or "-"


def _format_arrangement_notes(song: Song) -> str:
    return song.arrangement_notes or "-"


EDIT_FIELD_SPECS: dict[str, EditFieldSpec] = {
    "title": EditFieldSpec(
        label="назва",
        prompt="Нова назва?",
        format_current=lambda song: song.title,
        parse_input=_parse_title_update,
        aliases=("назва",),
    ),
    "artist": EditFieldSpec(
        label="виконавець",
        prompt="Новий виконавець?",
        format_current=lambda song: song.artist,
        parse_input=_parse_artist_update,
        aliases=("виконавець",),
    ),
    "source": EditFieldSpec(
        label="джерело",
        prompt="Нове джерело? Надішліть текст або «очистити».",
        format_current=_format_source,
        parse_input=_parse_source_update,
        aliases=("джерело",),
    ),
    "key": EditFieldSpec(
        label="тональність",
        prompt="Нова тональність?",
        format_current=lambda song: song.key,
        parse_input=_parse_key_update,
        aliases=("тональність",),
    ),
    "capo": EditFieldSpec(
        label="каподастр",
        prompt="Новий каподастр? Надішліть додатне число або «очистити».",
        format_current=_format_capo,
        parse_input=_parse_capo_update,
        aliases=("каподастр",),
    ),
    "time_signature": EditFieldSpec(
        label="розмір",
        prompt="Новий розмір? Надішліть текст або «очистити».",
        format_current=_format_time_signature,
        parse_input=_parse_time_signature_update,
        aliases=("розмір",),
    ),
    "tempo": EditFieldSpec(
        label="темп",
        prompt="Новий темп (BPM)? Надішліть число або «очистити».",
        format_current=_format_tempo,
        parse_input=_parse_tempo_update,
        aliases=("темп",),
    ),
    "tags": EditFieldSpec(
        label="теги",
        prompt="Нові теги через кому? Надішліть «очистити», якщо без тегів.",
        format_current=_format_tags,
        parse_input=_parse_tags_update,
        aliases=("теги",),
    ),
    "notes": EditFieldSpec(
        label="нотатки",
        prompt="Нові нотатки? Надішліть «очистити», якщо без нотаток.",
        format_current=_format_notes,
        parse_input=_parse_notes_update,
        aliases=("нотатки",),
    ),
    "arrangement_notes": EditFieldSpec(
        label="нотатки аранжування",
        prompt="Нові нотатки аранжування? Надішліть текст або «очистити».",
        format_current=_format_arrangement_notes,
        parse_input=_parse_arrangement_notes_update,
        aliases=("нотатки аранжування",),
    ),
}


def _editable_field_list() -> str:
    return ", ".join(spec.aliases[0] for spec in EDIT_FIELD_SPECS.values())


def _edit_field_previews(song: Song) -> str:
    return "\n".join(
        f"{spec.aliases[0]}: {spec.format_current(song)}" for spec in EDIT_FIELD_SPECS.values()
    )


def _edit_value_prompt(song: Song, field_name: str) -> str:
    spec = EDIT_FIELD_SPECS[field_name]
    return f"{spec.prompt}\nПоточне значення поля «{spec.label}»: {spec.format_current(song)}"


def _resolve_edit_field(raw_value: str) -> str | None:
    normalized = raw_value.strip().lower()
    for field_name, spec in EDIT_FIELD_SPECS.items():
        if normalized in spec.aliases:
            return field_name
    return None


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
            "Стан редагування втрачено. Почніть знову з екрана деталей пісні.",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
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
    await update.effective_message.reply_text(prompt, reply_markup=cancel_markup(update))
    return EDIT_VALUE


async def list_songs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service = get_song_service(context)
    songs = await service.list_songs()
    if update.effective_message is None:
        return
    if not songs:
        await update.effective_message.reply_text("Ще немає активних пісень.")
        return
    count = len(songs)
    base_header = f"Активні пісні ({count})"
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
        await update.effective_message.reply_text("Використання: /search <запит>")
        return

    service = get_song_service(context)
    songs = await service.search_songs(query)
    if not songs:
        await update.effective_message.reply_text("Нічого не знайдено.")
        return

    count = len(songs)
    base_header = f'Результати для "{query}" ({count})'
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
        await update.effective_message.reply_text("Теги ще не додано.")
        return
    await update.effective_message.reply_text("Теги: " + ", ".join(tags))


async def archive_song_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update, context):
        return
    if update.effective_message is None:
        return
    song_id = _parse_song_id(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Використання: /archivesong <id_пісні>")
        return

    service = get_song_service(context)
    try:
        song = await service.archive_song(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return

    await update.effective_message.reply_text(f"Пісню #{song.id} архівовано: {song.title}")


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
    await send_home_screen(update, context, prefix="Скасовано.")
    return ConversationHandler.END


async def add_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    _user_state(context)[PENDING_SONG_KEY] = {}
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Назва?",
            reply_markup=cancel_markup(update),
        )
    return ADD_TITLE


async def add_song_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _user_state(context)[PENDING_SONG_KEY] = {"title": _message_text(update)}
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Виконавець?",
            reply_markup=cancel_markup(update),
        )
    return ADD_ARTIST


async def add_song_artist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    payload["artist"] = _message_text(update)
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Джерело? Надішліть текст або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_SOURCE


async def add_song_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    payload["source_url"] = None if text.lower() == BUTTON_SKIP.lower() else text
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Тональність?",
            reply_markup=cancel_markup(update),
        )
    return ADD_KEY


async def add_song_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    payload["key"] = _message_text(update)
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Каподастр? Надішліть додатне число або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_CAPO


async def add_song_capo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    if text.lower() == BUTTON_SKIP.lower():
        payload["capo"] = None
    else:
        try:
            capo = int(text)
        except ValueError:
            if update.effective_message is not None:
                await update.effective_message.reply_text(
                    "Каподастр має бути додатним числом або «Пропустити»."
                )
            return ADD_CAPO
        if capo <= 0:
            if update.effective_message is not None:
                await update.effective_message.reply_text(
                    "Каподастр має бути додатним числом або «Пропустити»."
                )
            return ADD_CAPO
        payload["capo"] = capo
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Розмір? Надішліть текст або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_TIME_SIGNATURE


async def add_song_time_signature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    payload["time_signature"] = None if text.lower() == BUTTON_SKIP.lower() else text
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Темп BPM? Надішліть число або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_TEMPO


async def add_song_tempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    if text.lower() == BUTTON_SKIP.lower():
        payload["tempo_bpm"] = None
    else:
        try:
            payload["tempo_bpm"] = int(text)
        except ValueError:
            if update.effective_message is not None:
                await update.effective_message.reply_text("Темп має бути числом або «Пропустити».")
            return ADD_TEMPO
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Теги? Надішліть значення через кому або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_TAGS


async def add_song_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    payload["tags"] = [] if text.lower() == BUTTON_SKIP.lower() else parse_tag_input(text)
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Нотатки? Надішліть текст або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_NOTES


async def add_song_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    payload["notes"] = None if text.lower() == BUTTON_SKIP.lower() else text
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Нотатки аранжування? Надішліть текст або «Пропустити».",
            reply_markup=skip_cancel_markup(update),
        )
    return ADD_ARRANGEMENT_NOTES


async def add_song_arrangement_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    payload = _pending_song(context)
    text = _message_text(update)
    arrangement_notes = None if text.lower() == BUTTON_SKIP.lower() else text
    service = get_song_service(context)
    try:
        song = await service.create_song(
            SongCreate(
                title=str(payload["title"]),
                artist=str(payload["artist"]),
                source_url=cast(str | None, payload.get("source_url")),
                key=str(payload["key"]),
                capo=cast(int | None, payload.get("capo")),
                time_signature=cast(str | None, payload.get("time_signature")),
                tempo_bpm=cast(int | None, payload.get("tempo_bpm")),
                tags=cast(list[str], payload.get("tags", [])),
                notes=cast(str | None, payload.get("notes")),
                arrangement_notes=arrangement_notes,
            )
        )
    except ValueError as error:
        if update.effective_message is not None:
            await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context).pop(PENDING_SONG_KEY, None)
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Пісню створено:\n" + format_song(song),
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


async def edit_song_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_admin(update, context):
        return ConversationHandler.END
    if update.effective_message is None:
        return ConversationHandler.END

    song_id = _parse_song_id(context.args or [])
    if song_id is None:
        await update.effective_message.reply_text("Використання: /editsong <id_пісні>")
        return ConversationHandler.END
    return await _start_edit_song(update, context, song_id)


async def edit_song_start_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    song_id = _song_id_from_callback(query.data, prefix="edit:start:")
    if song_id is None:
        if update.effective_message is not None:
            await update.effective_message.reply_text(
                "Не вдалося розпізнати вибір пісні для редагування."
            )
        return ConversationHandler.END
    return await _start_edit_song(update, context, song_id)


async def _start_edit_song(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    song_id: int,
) -> int:
    if update.effective_message is None:
        return ConversationHandler.END

    service = get_song_service(context)
    try:
        song = await service.get_song(song_id)
    except SongNotFoundError as error:
        await update.effective_message.reply_text(str(error))
        return ConversationHandler.END

    _user_state(context)[EDIT_SONG_ID_KEY] = song_id
    await update.effective_message.reply_text(
        "Редагування пісні:\n"
        + format_song(song)
        + "\n\nПоточні поля для редагування:\n"
        + _edit_field_previews(song)
        + "\n\nЯке поле змінити? Оберіть одне з: "
        + _editable_field_list()
        + ".\nНатисніть «Скасувати», щоб зупинити.",
        reply_markup=cancel_markup(update),
    )
    return EDIT_FIELD


async def edit_song_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message is None:
        return ConversationHandler.END
    field_name = _resolve_edit_field(_message_text(update))
    if field_name is None:
        await update.effective_message.reply_text(
            "Невірне поле. Оберіть одне з: " + _editable_field_list() + ".",
            reply_markup=cancel_markup(update),
        )
        return EDIT_FIELD

    state = _user_state(context)
    song_id = state.get(EDIT_SONG_ID_KEY)
    if not isinstance(song_id, int):
        await update.effective_message.reply_text(
            "Стан редагування втрачено. Почніть знову з екрана деталей пісні.",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
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
            "Стан редагування втрачено. Почніть знову з екрана деталей пісні.",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
        )
        return ConversationHandler.END
    if field_name not in EDIT_FIELD_SPECS:
        await update.effective_message.reply_text(
            "Стан редагування втрачено. Почніть знову з екрана деталей пісні.",
            reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
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
        "Пісню оновлено:\n" + format_song(song),
        reply_markup=home_menu_markup(update, context) or ReplyKeyboardRemove(),
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
        raise ValueError(f"Непідтримуване поле: {field_name}")
    return spec.parse_input(raw_value)


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


def _conversation_fallbacks() -> list[BaseHandler]:
    return [
        MessageHandler(
            filters.Regex(CANCEL_BUTTON_PATTERN) & ~filters.COMMAND & filters.UpdateType.MESSAGE,
            cancel_command,
        ),
    ]


def _text_step(
    callback: Callable[
        [Update, ContextTypes.DEFAULT_TYPE],
        Coroutine[Any, Any, object],
    ],
) -> BaseHandler:
    return MessageHandler(_conversation_text_filter(), callback)


def _conversation_text_filter() -> filters.BaseFilter:
    return (
        filters.TEXT
        & ~filters.COMMAND
        & ~filters.Regex(CANCEL_BUTTON_PATTERN)
        & filters.UpdateType.MESSAGE
    )


def _menu_entry(
    label: str,
    callback: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, object]],
) -> BaseHandler:
    pattern = re.compile(rf"^{re.escape(label)}$")
    return MessageHandler(
        filters.Regex(pattern) & ~filters.COMMAND & filters.UpdateType.MESSAGE,
        callback,
    )


def build_add_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            _menu_entry(MENU_ADD_SONG, add_song_start),
        ],
        states={
            ADD_TITLE: [_text_step(add_song_title)],
            ADD_ARTIST: [_text_step(add_song_artist)],
            ADD_SOURCE: [_text_step(add_song_source)],
            ADD_KEY: [_text_step(add_song_key)],
            ADD_CAPO: [_text_step(add_song_capo)],
            ADD_TIME_SIGNATURE: [_text_step(add_song_time_signature)],
            ADD_TEMPO: [_text_step(add_song_tempo)],
            ADD_TAGS: [_text_step(add_song_tags)],
            ADD_NOTES: [_text_step(add_song_notes)],
            ADD_ARRANGEMENT_NOTES: [_text_step(add_song_arrangement_notes)],
        },
        fallbacks=_conversation_fallbacks(),
        name="add_song",
        persistent=False,
    )


def build_edit_song_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_song_start_from_callback, pattern=r"^edit:start:\d+$"),
        ],
        states={
            EDIT_FIELD: [_text_step(edit_song_field)],
            EDIT_VALUE: [_text_step(edit_song_value)],
        },
        fallbacks=_conversation_fallbacks(),
        name="edit_song",
        persistent=False,
    )
