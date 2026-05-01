# PRD: Song Browser Navigation State Module

Triage label: needs-triage

## Problem Statement

Song Vault uses button-first navigation for browsing songs, searching repertoire, opening song
details, archiving songs, returning to lists, and selecting upload targets. The current browser
behavior depends on raw user state, callback payload strings, mode flags, page indexes, stale-state
recovery, and return-page conventions that are known by several handlers.

From a maintainer's perspective, the browser Interface is too wide: callers need to know the shape
of stored state, short mode codes, callback formats, pagination rules, and recovery behavior. That
makes the Module shallow and makes future navigation work more brittle.

## Solution

Introduce a deeper Song Browser Navigation State Module that owns browser state, pagination,
callback encoding and decoding, return-page tracking, stale-state rebuilding decisions, and render
models for browser pages and song-detail return actions.

Telegram handlers should act as Adapters that pass menu actions and callback data into this Module,
then render the returned text and keyboard models. The existing button-first user experience should
remain stable.

## User Stories

1. As a repertoire user, I want to browse active songs with stable pagination, so that long song lists stay usable.
2. As a repertoire user, I want search results to paginate the same way as the full song list, so that navigation is predictable.
3. As a repertoire user, I want song detail screens to return me to the right page, so that I do not lose my place.
4. As an administrator, I want upload target selection to reuse song browser behavior, so that selecting a song for chart upload is familiar.
5. As an administrator, I want archive and edit outcomes to offer sensible next actions, so that I can continue the workflow efficiently.
6. As a user, I want stale browser callbacks to recover gracefully where possible, so that old inline buttons do not create confusing failures.
7. As a user, I want closed browser views to stop accepting page actions cleanly, so that old state does not linger unexpectedly.
8. As a maintainer, I want callback payload formats owned by one Module, so that adding a new browser action does not require scattered regex updates.
9. As a maintainer, I want browser mode rules owned by one Module, so that browse and upload modes cannot drift.
10. As a maintainer, I want return-page behavior owned by one Module, so that edit and upload flows do not duplicate state lookup logic.
11. As a maintainer, I want pure tests for pagination and callback parsing, so that behavior can be verified without Telegram-shaped mocks.
12. As a maintainer, I want the Telegram handler Interface to stay small, so that handlers only adapt updates and responses.
13. As a maintainer, I want navigation state validation in one place, so that malformed user state is handled consistently.
14. As a maintainer, I want menu alias routing to remain compatible, so that older keyboards keep working.

## Implementation Decisions

- Build or deepen a Song Browser Navigation State Module around browser state, callback payloads, pagination, and return actions.
- Keep button-first navigation and `/start` recovery behavior unchanged.
- Keep browse mode and upload-target mode as separate browser modes behind the same Interface.
- The Module should expose behavior-oriented operations such as building a page, decoding an action, resolving a return page, and rebuilding stale state.
- Telegram-specific objects should stay outside the Module; handlers should translate Module output into Telegram messages and keyboards.
- Callback string formats should be generated and parsed by the Module rather than duplicated by callers.
- The Module should own validation for stored browser state and normalize missing or malformed page values.
- No database schema changes are required.
- No changes are required to repertoire persistence behavior.

## Testing Decisions

- Good tests should exercise browser behavior through the navigation Module Interface: page bounds, mode handling, callback decoding, stale-state handling, and return-page behavior.
- Handler tests should verify that Telegram updates are adapted into navigation calls and that returned render models are sent.
- Existing navigation tests are prior art for expected browser text, callback compatibility, menu alias behavior, and stale callback recovery.
- Add pure tests for page normalization, callback round trips, mode-specific actions, and invalid payloads.
- Avoid tests that assert internal user-state dictionary layout except at the Adapter Seam.

## Out of Scope

- Redesigning the user-visible navigation structure.
- Adding new browsing filters or sorting options.
- Changing page size unless required by the extraction.
- Replacing Telegram inline keyboards with another interaction model.
- Changing authorization rules for admin-only actions.

## Further Notes

This PRD targets a real Seam: the same browser behavior is already used by browsing, upload target
selection, edit return actions, archive return actions, and chart upload return actions. Two or more
callers already vary across the same behavior, so the Seam is not hypothetical.
