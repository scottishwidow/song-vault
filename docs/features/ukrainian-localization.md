# Ukrainian-Only Bot Localization

## Summary

All user-facing Telegram bot text was localized to Ukrainian, and English control words were removed from conversational flows.

## Behavior changes

- Main menu labels and action buttons are now fully Ukrainian.
- Home/help/admin/error messages are Ukrainian.
- Navigation screens (song browser, details, archive confirmations, backup menu) are Ukrainian.
- Add/edit song flows use Ukrainian prompts and validation messages.
- Chart upload/view and backup export/import flows use Ukrainian prompts and result messages.
- Conversation control words were localized:
  - `Skip` -> `Пропустити`
  - `clear` -> `очистити`
- Follow-up copy simplifications:
  - Main admin action label changed from `Завантажити акорди` to `Завантажити гармонію`.
  - Add-song source prompt changed to `Джерело? (Посилання на оригінал)`.
  - Add-song flow no longer prompts for arrangement notes.
  - Chart upload flow no longer prompts for optional source URL before chart key.

## Service-layer localization

- User-visible exceptions from song/chart/backup services were translated to Ukrainian so surfaced errors stay localized end-to-end.

## Tests and verification

- Updated handler/navigation tests to assert Ukrainian copy and updated button labels.
- Verified quality gates:
  - `uv run ruff check .`
  - `uv run mypy`
  - `uv run pytest`
