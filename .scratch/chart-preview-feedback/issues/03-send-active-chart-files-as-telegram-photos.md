# Send active chart files as Telegram photos

Status: done

## What to build

Update the shared chart delivery path so active image chart files are sent as visible Telegram photos when possible, including both the `/chart` command and manual chart callback.

## Acceptance criteria

- [x] Active chart delivery attempts Telegram photo delivery for image chart files.
- [x] The `/chart` command uses the shared photo-capable chart delivery path.
- [x] Manual chart callbacks use the shared photo-capable chart delivery path.
- [x] Captions continue to include the same chart context currently shown during chart delivery.
- [x] Handler tests cover successful photo delivery for active charts.

## Blocked by

None - can start immediately
