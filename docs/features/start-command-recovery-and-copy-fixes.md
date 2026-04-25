# Start Command Recovery and Copy Fixes

## Summary

This update addresses three UX bugs in the Ukrainian Telegram bot flow:

- Song detail copy now labels source as `Джерело (оригінал)`.
- The chart-key optional step now shows both `Пропустити` and `Скасувати`.
- `/start` is restored in Telegram command surfaces for easier recovery after chat history cleanup.

## What changed

- Updated the shared song detail formatter to render:
  - `Джерело (оригінал): ...`
- Updated chart upload prompt keyboard for optional chart key:
  - changed from cancel-only keyboard to skip+cancel keyboard.
- Updated bot startup command publication:
  - publish only one command: `/start` with description `Відкрити головне меню`
  - set global chat menu button to Telegram commands menu (`MenuButtonCommands`)

## Handler and startup impact

- `handlers/repertoire.py`
  - copy-only change in `format_song` output.
- `handlers/charts.py`
  - reply markup change for the chart-key prompt; no state-machine or parsing changes.
- `bot/application.py`
  - replaced `delete_my_commands()` with explicit command publishing and commands menu button setup.

## Testing

- Updated handler tests to assert:
  - new source label text in detailed song cards
  - presence of both `Пропустити` and `Скасувати` buttons at chart-key step
- Updated application startup test to assert:
  - `/start` command is published
  - chat menu button is set to `MenuButtonCommands`
