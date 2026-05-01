# PRD: Backup Manifest Restore Module

Triage label: needs-triage

## Problem Statement

Song Vault can export and import a ZIP backup containing repertoire data and chart binaries. The
current backup Module has a small external Interface, but its Implementation owns several different
concerns at once: ZIP IO, manifest schema versions, manifest validation, legacy compatibility,
object-storage lifecycle, transactional replacement, and Postgres sequence reset.

From a maintainer's perspective, backup import is difficult to reason about because understanding
one behavior requires scanning several unrelated concerns. The Module has useful Depth externally,
but its internal Locality is overloaded.

## Solution

Keep the external backup Interface small while deepening the internal Modules around backup manifest
parsing, manifest validation, archive materialization, restore orchestration, and persistence
replacement.

The manifest Module should own schema version compatibility and validation. The restore
orchestration Module should own object upload ordering, cleanup, and replacement sequencing. The
persistence replacement Module should own database replacement and sequence reset behavior.

## User Stories

1. As an administrator, I want to export a complete repertoire backup, so that I can preserve songs and chart binaries.
2. As an administrator, I want to import a valid backup, so that I can restore repertoire data.
3. As an administrator, I want invalid backups rejected with clear messages, so that I do not partially restore bad data.
4. As an administrator, I want legacy backup manifests to remain supported, so that older exports do not become unusable.
5. As an administrator, I want chart binaries restored with the imported metadata, so that restored songs can still serve charts.
6. As an administrator, I want failed imports to clean up newly uploaded chart binaries, so that storage remains tidy.
7. As an administrator, I want old chart binaries deleted after a successful replacement, so that storage does not grow indefinitely.
8. As a maintainer, I want manifest validation isolated, so that schema compatibility can be tested exhaustively.
9. As a maintainer, I want restore orchestration isolated, so that cleanup and ordering behavior is explicit.
10. As a maintainer, I want persistence replacement isolated, so that transaction and sequence behavior can be verified separately.
11. As a maintainer, I want the backup external Interface to stay stable, so that handlers do not care about internal backup structure.
12. As a maintainer, I want manifest row mapping to be clear, so that future song or chart fields have one compatibility point.
13. As a maintainer, I want archive path validation in one place, so that unsafe paths cannot leak into restore logic.
14. As a maintainer, I want import summaries to remain simple, so that handlers can report successful restores without knowing internals.
15. As a maintainer, I want Postgres-specific sequence reset behavior isolated, so that test-only SQLite behavior stays contained.

## Implementation Decisions

- Keep the public backup Interface stable: export returns an archive summary and content, import returns an import summary.
- Build or deepen an internal Manifest Module for manifest schema versions, row parsing, validation, and legacy compatibility.
- Build or deepen an internal Archive Module for ZIP reading and writing.
- Build or deepen an internal Restore Orchestration Module for upload ordering, failure cleanup, successful old-object cleanup, and restore prefix generation.
- Build or deepen an internal Persistence Replacement Module for deleting and recreating repertoire rows and resetting database sequences.
- Preserve the current backup manifest version unless a separate feature requires a version bump.
- Preserve support for existing legacy manifest compatibility.
- Preserve async database and storage operations.
- No user-facing Telegram flow changes are required.
- No schema changes are required.

## Testing Decisions

- Good tests should exercise each deep Module through its Interface: manifest parsing, archive validation, restore cleanup, and persistence replacement.
- Manifest compatibility tests should be cheap, table-driven, and exhaustive across valid and invalid payloads.
- Restore orchestration tests should cover successful restore, missing chart content, upload failure, replacement failure, and cleanup behavior.
- Persistence replacement tests should cover row replacement and sequence reset behavior with the appropriate database.
- Existing backup tests are prior art for manifest content, import replacement, storage cleanup, missing chart rejection, and legacy manifest support.
- Avoid tests that require reading one large backup Implementation to understand which concern failed.

## Out of Scope

- Changing backup file format from ZIP.
- Introducing incremental backups.
- Supporting partial restore or merge restore.
- Adding encryption or password protection.
- Adding non-admin backup workflows.
- Changing chart storage provider.

## Further Notes

This PRD does not argue that the backup Module is shallow externally. Its public Interface is already
small. The deepening opportunity is internal: give each backup concern Locality while preserving the
external Depth that callers already benefit from.
