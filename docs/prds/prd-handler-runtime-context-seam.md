# PRD: Handler Runtime Context Seam

Triage label: needs-triage

## Problem Statement

Song Vault handlers depend on Telegram context shape, bot-data keys, runtime settings, service
instances, user state, and authorization checks. Tests repeatedly recreate Telegram-shaped context
objects and bot-data dictionaries to exercise handler behavior.

From a maintainer's perspective, this makes handler tests more brittle than necessary. The current
Seam exposes too much Telegram runtime plumbing, so tests often verify setup shape rather than
repertoire behavior.

## Solution

Introduce a deeper Handler Runtime Context Seam that gives handlers a small Interface for runtime
dependencies, authorization, and typed user state. Telegram context remains the Adapter at the
outside of the Seam.

Handlers should use the runtime context Interface instead of reaching directly into bot-data keys or
raw user-state dictionaries where practical. This should reduce repeated test setup and make handler
behavior easier to verify.

## User Stories

1. As a maintainer, I want handlers to access settings through a small Interface, so that bot-data key details are localized.
2. As a maintainer, I want handlers to access repertoire operations through a small Interface, so that tests can provide simple test doubles.
3. As a maintainer, I want handlers to access chart operations through a small Interface, so that chart tests do not recreate unrelated runtime state.
4. As a maintainer, I want handlers to access backup operations through a small Interface, so that backup handler tests stay focused.
5. As a maintainer, I want authorization checks behind one Interface, so that admin-only behavior uses one rule.
6. As a maintainer, I want user state access typed or wrapped, so that state keys and expected value shapes have Locality.
7. As a maintainer, I want handler tests to use compact fixtures, so that test intent is visible.
8. As a maintainer, I want Telegram context to remain the outer Adapter, so that the bot runtime keeps using python-telegram-bot normally.
9. As a maintainer, I want runtime dependency failures to surface clearly, so that misconfigured application startup is easier to debug.
10. As a maintainer, I want existing handler behavior to remain stable, so that users see no navigation or copy changes.
11. As a maintainer, I want the Seam to be real rather than hypothetical, so that multiple handler groups use it immediately.
12. As a maintainer, I want tests to assert behavior at the handler Interface, so that refactors do not break tests unnecessarily.
13. As a maintainer, I want service construction to stay centralized at application startup, so that dependency wiring remains simple.
14. As a maintainer, I want async behavior preserved, so that handler calls remain compatible with existing operations.

## Implementation Decisions

- Build or deepen a Handler Runtime Context Module that wraps Telegram context access for settings, runtime Modules, authorization, and user state.
- Keep Telegram context as the concrete Adapter.
- Keep application startup responsible for creating and storing runtime Modules.
- Move repeated bot-data key access behind the runtime context Interface.
- Move repeated admin authorization logic behind the runtime context Interface or a closely related authorization Module.
- Move repeated user-state lookup patterns behind typed helpers where this improves Locality.
- Do not change Telegram update handling, command registration, or handler registration order as part of this PRD.
- No schema changes are required.
- No user-facing copy changes are required.

## Testing Decisions

- Good tests should use a simple test Adapter for the runtime context Interface where handler behavior does not need real Telegram context details.
- Telegram Adapter tests should verify that real context objects are mapped correctly to the runtime context Interface.
- Existing handler and navigation tests are prior art for repeated context construction that should become simpler.
- Authorization tests should verify the shared admin rule once and handler-level rejection behavior where user-facing copy matters.
- User-state tests should focus on externally visible state transitions, not raw dictionary internals except at the Adapter Seam.
- Avoid introducing a Seam with only one Adapter unless multiple handlers immediately use it; one Adapter would be hypothetical.

## Out of Scope

- Replacing python-telegram-bot.
- Changing application startup behavior beyond dependency access.
- Introducing a dependency injection framework.
- Changing admin configuration.
- Changing handler registration order.
- Rewriting every handler in one pass if an incremental migration is safer.

## Further Notes

This PRD should be implemented carefully because it touches many handlers. The value comes from
reducing repeated runtime plumbing, not from adding abstraction for its own sake. The Seam is worth
considering because many handler Modules already depend on the same runtime dependencies and user
state patterns.
