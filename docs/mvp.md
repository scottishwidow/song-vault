# MVP Scope

The MVP is finished. This document records the delivered scope of the first usable version: an admin-operated repertoire bot.

## Included

- Button-first navigation with `/start` as the only typed entry/reset command
- List active songs
- Search songs by title, artist, and tag text
- Guided add-song flow
- Guided edit-song flow
- Soft-archive flow
- Tag listing
- Rich song metadata fields (capo, time signature)
- Stored `arrangement_notes` field for backups/domain compatibility (currently non-user-facing)
- One current chart image per song, managed by admins
- Admin-only chart upload flow
- Song chart retrieval flow for all users
- S3-compatible chart storage for local/dev via MinIO
- Admin-only repertoire backup export/import (ZIP with songs + charts)

## Chart handling

Charts shipped in the MVP as admin-managed image attachments.

- A chart is an uploaded image attached to a song.
- Each song has at most one active chart in the delivered MVP.
- Replacing a chart archives the previous chart metadata instead of deleting it.
- Chart binaries live in S3-compatible object storage, with MinIO used in Docker Compose for local development.
- Chart metadata is stored separately from the song record so future arrangement support remains possible.
- Chart metadata includes optional `source_url` and optional chart key in the musical sense.
- Chart upload happens in a dedicated step after song creation.
- Chart retrieval is available to all bot users in the delivered MVP.

## Out of scope

- Deployment and hosting beyond local Docker Compose
- Webhooks
- Non-admin workflows
- Role management
- Approval flows
- PDF chart uploads
- Multiple active charts or arrangement management per song
- OCR, preview generation, or other chart processing

## Completed delivery checklist

- [x] Establish project baseline with `uv`, CI, linting, formatting, and pre-commit
- [x] Define the initial song data model and migration flow
- [x] Implement admin-only repertoire CRUD flows
- [x] Add Postgres-backed integration tests for migrations and persistence
- [x] Improve guided edit flows with field previews and validation feedback
- [x] Add pagination or compact summaries for long list/search result sets
- [x] Add chart attachment storage, metadata persistence, and admin upload/view flows
- [x] Support richer song metadata such as capo, time signature, and persisted arrangement notes
- [x] Add import/export support for repertoire backups

## Next planning location

Future feature implementation plans should live under `docs/features/`.
