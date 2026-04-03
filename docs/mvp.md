# MVP

The first usable version is an admin-operated repertoire bot.

## Included

- Start and help commands
- List active songs
- Search songs by title, source, and tag text
- Guided add-song flow
- Guided edit-song flow
- Soft-archive command
- Tag listing
- Rich song metadata fields (capo, time signature, arrangement notes)
- One current chart image per song, managed by admins
- Admin-only chart upload command
- Song chart retrieval command for all users
- S3-compatible chart storage for local/dev via MinIO
- Admin-only repertoire backup export/import (ZIP with songs + charts)

## Chart handling

Charts are part of the MVP as admin-managed image attachments.

- A chart is an uploaded image attached to a song.
- Each song has at most one active chart in the MVP.
- Replacing a chart archives the previous chart metadata instead of deleting it.
- Chart binaries live in S3-compatible object storage, with MinIO used in Docker Compose for local development.
- Chart metadata is stored separately from the song record so future arrangement support remains possible.
- Chart metadata includes optional `source_url` and optional chart key in the musical sense.
- Chart upload happens in a dedicated step after song creation rather than inside `/addsong`.
- Chart retrieval is available to all bot users in the MVP.

## Out of scope

- Deployment and hosting beyond local Docker Compose
- Webhooks
- Non-admin workflows
- Role management
- Approval flows
- PDF chart uploads
- Multiple active charts or arrangement management per song
- OCR, preview generation, or other chart processing

## TODO

- [x] Establish project baseline with `uv`, CI, linting, formatting, and pre-commit
- [x] Define the initial song data model and migration flow
- [x] Implement admin-only repertoire CRUD command flows
- [x] Add Postgres-backed integration tests for migrations and persistence
- [x] Improve guided edit flows with field previews and validation feedback
- [x] Add pagination or compact summaries for long `/songs` and `/search` results
- [x] Add chart attachment storage, metadata persistence, and admin commands
- [x] Support richer song metadata such as capo, time signature, and arrangement notes
- [x] Add import/export support for repertoire backups
