# Fall back to document delivery when photo sending fails

Status: needs-triage

## What to build

Preserve document delivery as the fallback chart delivery path when Telegram photo delivery is not appropriate or fails, so users still receive the active chart through existing document attachment behavior.

## Acceptance criteria

- [ ] Chart delivery falls back to Telegram document delivery when photo delivery fails.
- [ ] Chart delivery uses document delivery when the chart cannot reasonably be sent as a photo.
- [ ] The fallback preserves the original chart filename and caption.
- [ ] Existing missing-chart and storage-failure responses for explicit chart delivery remain consistent.
- [ ] Handler tests cover document fallback behavior after photo delivery failure.

## Blocked by

- .scratch/chart-preview-feedback/issues/03-send-active-chart-files-as-telegram-photos.md
