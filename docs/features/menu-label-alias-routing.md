# Menu Label Alias Routing

## Summary

The button router now accepts both emoji-prefixed menu labels and plain-text aliases. This keeps navigation working for users who still have older keyboard labels such as `Пісні`.

## What changed

- Added menu alias resolution in `handlers.navigation.menu_text_router`.
- Mapped plain labels to existing canonical actions:
  - `Головна`
  - `Пісні`
  - `Пошук`
  - `Теги`
  - `Допомога`
  - `Завантажити гармонію`
  - `Резервна копія`
- Reused alias resolution in search-pending guard logic so plain menu labels are not treated as search queries.
- Fixed inline callback routing regex in `build_navigation_callback_handler` so these callbacks are actually handled:
  - `song:detail:<id>:<page>`
  - `song:view:<id>`
  - `song:archive:<id>:<page>`
  - `song:archiveconfirm:<id>:<page>`
  - `browser:page:<mode>:<page>`
  - `browser:close`

## Testing

- Added a regression test proving `Пісні` opens the songs browser:
  - `tests/test_navigation.py::test_plain_songs_label_opens_song_browser`
- Added a regression test proving callback regex matches real inline payloads:
  - `tests/test_navigation.py::test_navigation_callback_handler_matches_song_and_browser_callbacks`
- Verified navigation and handler suites:
  - `uv run pytest tests/test_navigation.py tests/test_handlers.py`
