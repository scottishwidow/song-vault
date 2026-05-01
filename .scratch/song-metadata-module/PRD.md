# PRD: Song Metadata Module

Triage label: needs-triage

## Problem Statement

Song Vault already supports a rich repertoire record: title, artist, source URL, original key,
capo, time signature, tempo, tags, notes, status, and a stored arrangement-notes field. The current
implementation makes the meaning of those fields hard to maintain because field behavior is spread
across Telegram conversations, display formatting, validation, persistence payloads, and backup
compatibility.

From a maintainer's perspective, adding or changing one song field requires editing many places and
remembering which flows are user-facing, which fields are optional, how blank values are normalized,
which fields can be cleared, and how values should be displayed. That reduces Locality and makes the
repertoire Module shallower than it should be.

## Solution

Introduce a deeper Song Metadata Module that owns user-facing song metadata semantics behind a small
Interface. The Module should concentrate labels, prompt text, required and optional rules,
normalization, clear/skip semantics, display formatting, and mapping into create and update payloads.

Telegram handlers should remain thin Adapters: they collect user input, call the Song Metadata
Module, and pass normalized results to the repertoire persistence Module. The existing bot behavior
should remain stable while field knowledge moves behind one Seam.

Backup manifest compatibility should remain its own concern unless a later design explicitly
decides that manifest rows should consume the same metadata description. The first step should focus
on user-facing repertoire metadata.

## User Stories

1. As an administrator, I want song metadata prompts to behave consistently, so that adding songs feels predictable.
2. As an administrator, I want required song metadata to reject blank values consistently, so that incomplete repertoire records are not created.
3. As an administrator, I want optional song metadata to support skip behavior consistently, so that I can add a song quickly.
4. As an administrator, I want editable song metadata to support clear behavior consistently, so that I can remove stale optional values.
5. As an administrator, I want numeric song metadata such as capo and tempo to validate consistently, so that invalid values do not enter the repertoire.
6. As an administrator, I want tag input to normalize and deduplicate consistently, so that tag lists stay useful for browsing.
7. As an administrator, I want edit previews to use the same formatting as song detail views where appropriate, so that current values are easy to understand.
8. As a repertoire user, I want song detail text to remain clear and stable, so that I can understand song metadata without learning internal field names.
9. As a maintainer, I want one place to update a song metadata label, so that copy changes do not drift between add, edit, list, and detail flows.
10. As a maintainer, I want one place to update field validation, so that create and edit flows do not diverge.
11. As a maintainer, I want the Song Metadata Interface to be the test surface, so that tests describe behavior instead of Telegram conversation plumbing.
12. As a maintainer, I want arrangement notes handled deliberately, so that stored domain compatibility does not accidentally become user-facing.
13. As a maintainer, I want persistence payloads built from normalized metadata, so that the database layer does not need to know Telegram control words.
14. As a maintainer, I want future song fields to have an obvious extension point, so that metadata changes have high Leverage.

## Implementation Decisions

- Build or deepen a Song Metadata Module with a small Interface for field definitions, parsing, normalization, formatting, and payload creation.
- Treat user-facing song metadata as the initial scope: title, artist, source URL, original key, capo, time signature, tempo, tags, and notes.
- Keep arrangement notes persisted but outside the user-facing metadata Interface unless a later product decision exposes them.
- Keep status, IDs, and timestamps outside the user-facing metadata Interface.
- Use the Song Metadata Module from add-song and edit-song flows so both flows share validation and normalization.
- Keep Telegram handlers as Adapters that translate Telegram updates into field input and translate Module results into replies.
- Keep service-layer persistence async-first and free of Telegram update objects.
- Avoid schema changes for this PRD.
- Avoid changing the user-facing Ukrainian copy except where unifying existing copy is necessary for consistency.
- Do not fold backup manifest versioning into the first implementation; manifest compatibility has different invariants and should remain separate for now.

## Testing Decisions

- Good tests should exercise the Song Metadata Interface directly: given raw field input, assert normalized values, errors, display strings, and payloads.
- Handler tests should verify routing, state transitions, and that normalized payloads are passed forward, not duplicate every field rule.
- Existing handler tests for add-song and edit-song flows are prior art for behavior that must remain stable.
- Existing song persistence tests are prior art for validating that normalized payloads persist correctly.
- Add focused tests for required fields, optional clear/skip behavior, numeric validation, tag normalization, and display formatting.
- Keep tests external-behavior oriented; avoid asserting private field-definition data structures directly.

## Out of Scope

- Adding new song metadata fields.
- Changing database schema.
- Exposing arrangement notes in Telegram flows.
- Redesigning backup manifest versioning.
- Changing button-first navigation behavior.
- Rewriting all handler tests in one pass.

## Further Notes

This is the highest-priority deepening opportunity because field semantics are a repeated source of
cross-module knowledge. The deletion test shows that deleting the current helper code would push the
same rules back into many callers, so a deeper Module should improve both Leverage and Locality.
