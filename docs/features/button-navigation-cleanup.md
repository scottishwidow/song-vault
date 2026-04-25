# Button Navigation Cleanup

## Summary

This update finishes the shift to button-first navigation for end users. The bot now exposes `Start` as a visible reply-keyboard entrypoint, removes published slash commands from Telegram userspace, routes cancellation back to the main menu, and adds emoji to home-menu items.

## What changed

- Added emoji-labelled home menu buttons:
  - `🏠 Start`
  - `🎵 Songs`
  - `🔎 Search`
  - `🏷️ Tags`
  - `❓ Help`
  - `➕ Add Song`
  - `🖼️ Upload Chart`
  - `💾 Backup`
- Added `Start` as a first-class reply-keyboard action that resets transient navigation state and re-renders the home menu.
- Kept `/start` as the only typed entry/reset fallback.
- Removed published bot commands from Telegram by clearing `set_my_commands` output during startup.
- Removed non-`/start` command handlers from the application wiring so end-user navigation stays inside buttons and callbacks.
- Updated help and unknown-command messaging to point users back to the button flow.

## Cancel behavior fix

The `Cancel` reply-keyboard button previously leaked into conversation state because some state handlers accepted generic text or all message types before the cancel fallback ran.

The implementation now:

- excludes the `Cancel` button from conversation state handler filters
- lets the cancel fallback win first
- clears per-flow state before ending the conversation
- sends the user back to the main menu consistently

This was applied to:

- search prompt flow
- add-song flow
- edit-song flow
- upload-chart flow
- import-backup flow

## Edit field selection

The edit-song flow now uses inline buttons for choosing which existing field to edit. After an administrator selects a field, the bot keeps the existing Ukrainian prompt and accepts free text only for the new field value.

Editable fields remain limited to the current user-facing song fields: title, artist, source, key, capo, time signature, tempo, tags, and notes. Arrangement notes stay non-user-facing.

## Testing

Coverage added or updated for:

- emoji menu rendering and `Start` button placement
- `Start` clearing navigation state and reopening the home screen
- search cancel returning to the home menu
- conversation handlers refusing to consume `Cancel` as normal input
- cancel handlers clearing state and returning the home menu
- bot startup clearing published Telegram commands
- edit field selection rendering inline field buttons
- selected edit fields prompting for values with existing validation copy
- invalid edit field callbacks and inline edit cancellation

## Notes

- `Cancel` and `Skip` remain plain-text buttons.
- Existing command-oriented helper functions still exist where they support internal callback-driven flows, but userspace is now button-first with `/start` as the only typed reset path.

## Implementation note: handler conversation helpers

Shared conversation plumbing now lives in `handlers.conversation`. Repertoire, chart upload,
backup import, and navigation handlers use it for typed `context.user_data` access, song ID and
callback payload parsing, cancel-message filters/fallbacks, home-screen reply markup fallback, and
state-lost replies. This keeps the handler behavior and callback payloads unchanged while removing
duplicated private helper code.

## Implementation note: navigation recovery and return actions

Stage 3 hardens callback-driven navigation without changing service contracts or persistence:

- `song_browser_state` now tracks `current_page` in addition to mode/title/items.
- Stale browser callbacks (`browser:page:b:*` and `browser:page:u:*`) rebuild list state from
  `SongService.list_songs()` when state is missing or mode drifted.
- Added deterministic home callback `nav:home` for inline-button return to the home screen.
- Added shared inline next-action keyboards for:
  - song outcomes: details, list, home
  - backup outcomes: backup menu, home
- Archive/edit/upload/export/import success paths now use a two-message pattern:
  first message keeps reply-keyboard reset behavior, second message offers inline return actions.
- Upload flow now keeps return context (`return_mode`, `return_page`) in upload state so post-upload
  navigation can reopen the upload target list page.

## Implementation note: existing flow copy consistency

Stage 4 aligns existing Ukrainian bot copy without adding capabilities or changing service
contracts:

- Admin-only rejections now share one user-facing message across menu, command-helper, callback,
  upload, archive, and backup entry points.
- Empty states are explicit for repertoire, search, and tag flows.
- Add-song prompts use consistent "Надішліть..." wording while preserving the current fields and
  skip/cancel behavior.
- Chart upload/view text now uses "гармонія" consistently to match the reply-keyboard menu label.
- Archive, backup export, and backup import outcomes use consistent success text and keep the
  Stage 3 next-action buttons.

## Implementation note: docs and final verification

Stage 5 finalizes documentation and verification for this UX cleanup:

- README/MVP docs now explicitly describe the current userspace surface as button-first with
  `/start` as the only typed entry/reset command.
- `arrangement_notes` is now explicitly documented as persisted for domain/backup compatibility but
  currently non-user-facing in bot flows.
- Final quality gates were run after Stage 5 updates:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy`
  - `uv run pytest`
