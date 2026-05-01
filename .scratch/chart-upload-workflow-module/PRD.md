# PRD: Chart Upload Workflow Module

Triage label: needs-triage

## Problem Statement

Song Vault supports one active chart image per song, with previous charts archived on replacement
and chart binaries stored outside Postgres. The current implementation has a real Chart Storage
Adapter, but chart upload behavior still spans Telegram media extraction, transient upload state,
song existence checks, content validation, storage writes, metadata replacement, cleanup, and
caption formatting.

From a maintainer's perspective, the chart upload workflow has too many details exposed at handler
and test call sites. Tests for chart behavior currently need fake persistence objects that understand
implementation details, which suggests the Interface is not deep enough for the behavior being
tested.

## Solution

Introduce a deeper Chart Upload Workflow Module that owns the chart upload and replacement flow
behind a small Interface. Handlers should adapt Telegram media into an upload intent, then the
workflow should validate the chart, upload the binary, replace active metadata, archive prior chart
metadata, and clean up storage on failure.

The existing Chart Storage Adapter remains the storage Seam. The new workflow should improve
Locality around chart replacement behavior without changing the user-facing upload flow.

## User Stories

1. As an administrator, I want to upload a chart image for a song, so that users can retrieve the current harmony.
2. As an administrator, I want photo uploads and image-document uploads to behave consistently, so that I can use either Telegram input style.
3. As an administrator, I want non-image uploads rejected clearly, so that invalid chart files are not stored.
4. As an administrator, I want chart key metadata to remain optional, so that I can upload charts quickly.
5. As an administrator, I want replacing a chart to archive the previous chart metadata, so that history is preserved.
6. As an administrator, I want failed metadata writes to clean up uploaded chart binaries, so that storage does not accumulate orphaned files.
7. As a repertoire user, I want chart retrieval to return the active chart for a song, so that I get the current version.
8. As a repertoire user, I want chart captions to show song title and chart key when available, so that files are understandable outside the bot.
9. As a maintainer, I want Telegram media extraction isolated from chart replacement rules, so that storage behavior can be tested without Telegram mocks.
10. As a maintainer, I want chart replacement tested through a behavior-oriented Interface, so that tests do not depend on persistence implementation details.
11. As a maintainer, I want object-key generation and cleanup rules in one place, so that storage lifecycle bugs have Locality.
12. As a maintainer, I want chart validation errors to stay user-facing and localized, so that handlers do not translate low-level failures ad hoc.
13. As a maintainer, I want the Chart Storage Adapter to remain narrow, so that S3-compatible storage can vary without affecting workflow logic.
14. As a maintainer, I want the chart workflow to remain async-first, so that it fits the existing bot runtime.

## Implementation Decisions

- Build or deepen a Chart Upload Workflow Module that coordinates chart validation, storage writes, metadata replacement, and cleanup.
- Keep Telegram media extraction in the handler Adapter or in a small Telegram-specific Adapter, not in the chart workflow itself.
- Preserve the one-active-chart-per-song rule.
- Preserve soft archive semantics for replaced charts.
- Preserve chart binaries outside Postgres.
- Keep the existing storage Seam and S3-compatible Adapter.
- Keep chart upload prompts and optional chart key behavior stable.
- The workflow Interface should accept a normalized upload intent rather than raw Telegram update objects.
- No schema changes are required.
- Error messages surfaced to users should remain localized.

## Testing Decisions

- Good tests should exercise chart workflow behavior: successful upload, replacement archives, missing song, invalid content type, storage failure, persistence failure, and cleanup.
- Handler tests should verify Telegram photo/document adaptation and conversation state, not chart replacement internals.
- Existing chart behavior tests are prior art for upload, retrieval, replacement, and cleanup.
- Existing handler tests are prior art for Telegram media branches and reply copy.
- Add tests around failure ordering so cleanup behavior is explicit.
- Avoid fake persistence objects that need to parse query internals where a deeper Interface can expose behavior directly.

## Out of Scope

- Supporting PDF chart uploads.
- Supporting multiple active charts per song.
- OCR, preview generation, or chart processing.
- Changing object storage provider.
- Changing chart retrieval permissions.
- Exposing chart source URL input again.

## Further Notes

The goal is not to hide all complexity in one large class. The goal is to put chart workflow
complexity behind a small Interface, with internal seams where useful, so callers get Leverage and
maintainers get Locality.
