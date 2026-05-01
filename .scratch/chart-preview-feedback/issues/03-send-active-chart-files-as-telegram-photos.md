# Send active chart files as Telegram photos

Status: needs-triage

## What to build

Update the shared chart delivery path so active image chart files are sent as visible Telegram photos when possible, including both the `/chart` command and manual chart callback.

## Acceptance criteria

- [ ] Active chart delivery attempts Telegram photo delivery for image chart files.
- [ ] The `/chart` command uses the shared photo-capable chart delivery path.
- [ ] Manual chart callbacks use the shared photo-capable chart delivery path.
- [ ] Captions continue to include the same chart context currently shown during chart delivery.
- [ ] Handler tests cover successful photo delivery for active charts.

## Blocked by

None - can start immediately
