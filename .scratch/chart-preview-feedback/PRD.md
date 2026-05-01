# Chart Preview Feedback

Status: needs-triage

## Problem Statement

Users retrieve songs from the Telegram bot to quickly access repertoire details during practice, rehearsal, or service preparation. When a song has a source URL, especially a YouTube link to the original song, Telegram automatically expands that link into a video preview. The preview takes up vertical space, distracts from the repertoire information, and competes with the chart, which is the more useful artifact in this context.

Users also have to press a separate button to view the chart even when a chart already exists for the song. That extra step slows down the main workflow: find a song, read its details, and see the harmony immediately.

## Solution

When the bot sends song detail text or other song-rendering messages that include source URLs, it should suppress Telegram link previews. The source URL should remain visible as text, but Telegram should not expand it into a YouTube or web preview.

When a user opens a single-song detail view and an active chart exists, the bot should send the chart immediately after rendering the song detail message. The chart should be sent as a visible photo/image preview when possible, with the current document attachment behavior retained as a fallback. The chart button should remain available only when an active chart exists, so users can manually resend the chart without seeing a dead action on songs that have no chart.

## User Stories

1. As a repertoire user, I want song source links to stay compact, so that retrieved songs do not get visually dominated by YouTube previews.
2. As a repertoire user, I want the original song link to remain visible as text, so that I can still open the source manually when I need it.
3. As a repertoire user, I want a song's active chart to appear immediately after I open song details, so that I do not need an extra tap to see the harmony.
4. As a repertoire user, I want the chart to display as an image when possible, so that I can read it directly in the Telegram conversation.
5. As a repertoire user, I want the bot to keep song details visible even if chart delivery fails, so that a storage issue does not block access to the repertoire entry.
6. As a repertoire user, I want a clear short error if the chart cannot be loaded, so that I understand why the expected chart did not appear.
7. As a repertoire user, I want the chart to be sent every time I open song details, so that returning to a song behaves predictably.
8. As a repertoire user, I want list and search results to remain compact, so that browsing multiple songs does not flood the chat with charts.
9. As a repertoire user, I want the manual chart button to remain when a chart exists, so that I can resend the chart without reopening the song.
10. As a repertoire user, I do not want a manual chart button when no chart exists, so that the interface does not offer an action that only reports absence.
11. As an administrator, I want the upload chart action to remain available even when no chart exists, so that I can add missing harmony files from the song detail view.
12. As an administrator, I want the upload chart action to remain available when a chart already exists, so that I can replace or update the active chart.
13. As a repertoire user, I want source-link previews suppressed consistently across song detail, browse, search, creation, and update confirmations, so that the bot has predictable message formatting.
14. As a repertoire user, I want the chart auto-send behavior limited to single-song detail views, so that broad result lists remain easy to scan.
15. As a maintainer, I want chart button visibility to be based on lightweight chart metadata, so that the bot does not download chart bytes just to render a keyboard.
16. As a maintainer, I want chart sending behavior to reuse the existing chart retrieval path where practical, so that missing chart and storage failure behavior stays consistent.
17. As a maintainer, I want photo delivery to fall back to document delivery, so that users still receive the chart if Telegram cannot render it as a photo.
18. As a maintainer, I want the feature implemented without schema changes, so that it can ship as a focused handler and service change.
19. As a maintainer, I want the behavior covered by handler and service tests, so that future navigation changes do not reintroduce previews or missing chart actions.
20. As a maintainer, I want chart source URL behavior left alone, so that this work does not conflict with the planned removal of chart source URLs.

## Implementation Decisions

- Suppress Telegram link previews everywhere the bot renders song details or song source URLs.
- Keep the song source URL visible in message text; only suppress the automatic Telegram preview.
- Auto-send charts only from the single-song detail flow.
- Do not auto-send charts from browse results, search results, tag results, or other multi-song result lists.
- Render the song detail message first, then attempt chart delivery afterward.
- If chart delivery fails because the song has no chart, do not show an error during detail rendering; absence is represented by hiding the chart button.
- If chart delivery fails because storage cannot return the active chart file, keep the song detail message and send a short follow-up error.
- Add or expose a lightweight chart metadata/presence interface in the chart service. This interface should answer whether a song has an active chart without downloading chart bytes.
- Use the lightweight chart presence result to decide whether the manual chart button is shown.
- Show the manual chart button only when an active chart exists.
- Keep administrator edit, archive, and upload chart actions governed by the existing administrator checks.
- Keep upload chart available for administrators regardless of whether an active chart exists.
- Send auto-delivered charts as visible Telegram photos when possible.
- Preserve document delivery as a fallback path when photo delivery is not appropriate or fails.
- Keep the existing explicit chart command and manual chart callback behavior available.
- Do not introduce database schema changes for this feature.
- Do not change the song source URL model or validation rules.
- Do not expand chart source URL behavior; chart source URL is out of scope because it is expected to be removed soon.
- Prefer handler-level orchestration with business rules and chart lookup behavior encapsulated in services.
- Preserve async boundaries end to end.

## Testing Decisions

- Tests should cover externally visible bot behavior: sent messages, reply markup, chart delivery calls, and error messages. They should avoid asserting private helper structure unless there is no practical public surface.
- Add handler tests for song detail rendering when a chart exists: the detail text is sent or edited, the manual chart button is present, and chart delivery is attempted immediately.
- Add handler tests for song detail rendering when no chart exists: the manual chart button is absent and no chart file is sent.
- Add handler tests for non-admin song detail views: administrator actions remain hidden while the chart button follows chart availability.
- Add handler tests for admin song detail views: administrator actions remain visible and upload chart remains available regardless of chart availability.
- Add handler tests for storage failure during auto-send: song details still render and the user receives a short chart-load failure message.
- Add handler tests for link preview suppression on song-rendering messages that include source URLs.
- Add tests for chart photo delivery and document fallback behavior.
- Add service tests for the lightweight active-chart presence or metadata lookup.
- Reuse existing navigation handler tests as prior art for callback-driven song detail behavior.
- Reuse existing chart handler tests as prior art for missing chart and storage failure responses.
- Reuse existing song handler tests as prior art for create/update/search/list message rendering.
- Existing full-suite checks should include pytest, ruff, formatting check, and mypy before implementation is considered complete.

## Out of Scope

- Removing chart source URL storage or backup behavior.
- Changing song source URL validation or storage.
- Hiding source URLs entirely.
- Auto-sending charts for browse, search, tag, or other multi-song result lists.
- Changing the chart upload workflow.
- Adding support for non-image chart files.
- Changing database schema or migrations.
- Reworking the repertoire domain model.
- Changing backup/export/import behavior beyond whatever is needed to keep existing tests passing.

## Further Notes

The implementation should respect the existing architecture boundaries: Telegram handlers parse updates and format responses, services own repertoire and chart operations, models own persistence mappings, and runtime settings stay isolated in configuration. The useful deep module here is a chart service interface that gives handlers a simple answer about active chart availability without forcing them to know storage details or download chart content prematurely.
