# Song Artist and Source URL Split

## Summary

This feature-fix splits the previous combined song metadata field into two explicit song fields:

- required `artist`
- optional `source_url`

The goal is to stop conflating artist names with source links and make edit behavior predictable.

## What changed

- Added a new Alembic migration that:
  - adds `songs.artist` and `songs.source_url`
  - copies legacy `songs.artist_or_source` values into `songs.artist`
  - drops `songs.artist_or_source`
- Updated song model and song service contracts to use `artist` and `source_url`.
- Updated add-song flow:
  - prompt for `Artist`
  - prompt for optional `Source URL` (text or `skip`)
- Updated edit-song flow:
  - added editable `source` field
  - updated invalid field guidance to include `source`
- Updated song formatting:
  - `Artist:` now shows artist name
  - `Source:` now shows song-level source URL or `-`
- Updated song browser/list compact lines to show artist.
- Kept chart metadata unchanged but relabeled chart captions to `Chart source URL:` to avoid confusion with song source.

## Backup compatibility

- Backup export now writes songs with `artist` and `source_url`.
- Backup import accepts both:
  - current manifests using `artist`
  - legacy manifests using `artist_or_source` (mapped to `artist`)

## Testing

- Updated handler, navigation, service, and Postgres integration tests for the new field names.
- Added a backup import test for legacy manifest version `1` with `artist_or_source`.
- Updated backup tests to assert song-level `source_url` round-trips.
