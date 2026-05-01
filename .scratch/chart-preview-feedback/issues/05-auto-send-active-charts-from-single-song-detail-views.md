# Auto-send active charts from single-song detail views

Status: needs-triage

## What to build

After rendering a single-song detail view, automatically send the song's active chart when one exists, while keeping broad result lists compact and keeping song details visible even if chart delivery fails.

## Acceptance criteria

- [ ] Opening a single-song detail view renders the song detail message first and then attempts active chart delivery when a chart exists.
- [ ] Returning to the same song detail view auto-sends the active chart each time.
- [ ] Songs without an active chart do not show the manual chart button and do not send a no-chart error during detail rendering.
- [ ] Storage failure during auto-send leaves the song detail message visible and sends a short chart-load failure follow-up.
- [ ] Browse, search, tag, and other multi-song result lists do not auto-send charts.
- [ ] Handler tests cover chart auto-send, no-chart behavior, storage failure behavior, and list/search compactness.

## Blocked by

- .scratch/chart-preview-feedback/issues/02-use-active-chart-availability-for-song-detail-actions.md
- .scratch/chart-preview-feedback/issues/03-send-active-chart-files-as-telegram-photos.md
- .scratch/chart-preview-feedback/issues/04-fall-back-to-document-delivery-when-photo-sending-fails.md
