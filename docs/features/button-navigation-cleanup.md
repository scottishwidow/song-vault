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

## Testing

Coverage added or updated for:

- emoji menu rendering and `Start` button placement
- `Start` clearing navigation state and reopening the home screen
- search cancel returning to the home menu
- conversation handlers refusing to consume `Cancel` as normal input
- cancel handlers clearing state and returning the home menu
- bot startup clearing published Telegram commands

## Notes

- `Cancel` and `Skip` remain plain-text buttons.
- Existing command-oriented helper functions still exist where they support internal callback-driven flows, but userspace is now button-first with `/start` as the only typed reset path.

## Implementation note: handler conversation helpers

Shared conversation plumbing now lives in `handlers.conversation`. Repertoire, chart upload,
backup import, and navigation handlers use it for typed `context.user_data` access, song ID and
callback payload parsing, cancel-message filters/fallbacks, home-screen reply markup fallback, and
state-lost replies. This keeps the handler behavior and callback payloads unchanged while removing
duplicated private helper code.
