# Suppress song source link previews

Status: done

## What to build

Suppress Telegram link previews everywhere the bot renders song details or song source URLs, while keeping the original song source URL visible in the message text.

## Acceptance criteria

- [x] Song detail messages that include a source URL keep the source URL as visible text and do not generate Telegram web previews.
- [x] Browse, search, creation confirmation, and update confirmation messages that render song source URLs suppress Telegram web previews consistently.
- [x] The implementation does not change song source URL storage, validation, or chart source URL behavior.
- [x] Handler tests cover link preview suppression on song-rendering messages that include source URLs.

## Blocked by

None - can start immediately
