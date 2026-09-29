# Consent-Gated Fallback Verification Plan

**Goal:** Guarantee that every configured automatic fallback pauses before the fallback provider receives conversation history, tool state, or reasoning, and resumes only after explicit user consent.

**Target contract:** On primary failure with `require_confirmation:true`, fallback runtime may be prepared but no fallback model request may be dispatched. The turn returns one deterministic pause prompt. The cached thread accepts only explicit `continue on Tiiny`/`continue locally`; explicit wait restores primary. Consent causes exactly one fallback request with the existing thread. This applies to network, rate-limit, auth, malformed/empty response, safety/content-filter, and retry-exhaustion paths.

## Plan

1. Enumerate all `_try_activate_fallback()` call sites and the inner retry loop.
2. Introduce one control-flow signal owned by the conversation loop, not a late outer-loop flag.
3. At every successful confirmation-required activation, unwind immediately to the deterministic pause result before another API dispatch.
4. Keep per-thread pending state on the cached agent; do not persist hidden reasoning or secrets.
5. On next turn:
   - explicit continue: retain fallback runtime and allow one request;
   - explicit wait/no: clear pending state, restore primary, return deterministic acknowledgment;
   - anything else: repeat the choice without model invocation.
6. Add table-driven tests for every activation path and a central dispatch tripwire asserting zero fallback calls pre-consent.
7. Build `scripts/verify_confirmed_fallback.py` using an unreachable primary and a local counting fake fallback server:
   - first turn must pause and server request count remain zero;
   - consent turn must return the fallback sentinel and request count become one;
   - wait path must remain zero;
   - no conversation/reasoning payload appears before consent.
8. Run fallback/runtime suites plus the full conversation-loop suite.
9. Push to Cameron’s Hermes fork branch, restart default/Compass gateways, and run isolated live smoke tests.
10. Finish only when verifier returns `ok:true` for all configured profiles.

## Rollback

Remove `require_confirmation` from fallback entries or switch back to the pre-change Hermes commit, restart gateways, and confirm normal primary operation. Do not silently restore automatic context-bearing fallback; if rollback is required, prefer disabling fallback until repaired.
