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

## Out of scope

- Deployment and hosting
- Webhooks
- Non-admin workflows
- Role management
- Approval flows
- Media uploads or sheet storage

## TODO

- [x] Establish project baseline with `uv`, CI, linting, formatting, and pre-commit
- [x] Define the initial song data model and migration flow
- [x] Implement admin-only repertoire CRUD command flows
- [x] Add Postgres-backed integration tests for migrations and persistence
- [ ] Improve guided edit flows with field previews and validation feedback
- [ ] Add pagination or compact summaries for long `/songs` and `/search` results
- [ ] Support richer song metadata such as capo, time signature, and arrangement notes
- [ ] Add import/export support for repertoire backups
