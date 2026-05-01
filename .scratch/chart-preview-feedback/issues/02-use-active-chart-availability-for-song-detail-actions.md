# Use active chart availability for song detail actions

Status: needs-triage

## What to build

Use lightweight active-chart availability from the chart service when rendering single-song detail actions, so the manual chart button is shown only when an active chart exists and administrator actions keep their existing rules.

## Acceptance criteria

- [ ] The chart service exposes an async active-chart availability or metadata lookup that does not download chart bytes.
- [ ] Single-song detail keyboards show the manual chart button only when an active chart exists.
- [ ] Non-admin song detail views hide administrator actions while still reflecting chart button availability.
- [ ] Admin song detail views keep edit, archive, and upload chart actions visible according to existing administrator checks.
- [ ] Upload chart remains available to administrators whether or not an active chart exists.
- [ ] Service and handler tests cover chart availability, chart button visibility, and admin action visibility.

## Blocked by

None - can start immediately
