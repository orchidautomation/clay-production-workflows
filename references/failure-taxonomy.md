# Failure Taxonomy

| Class | Examples | Safe response |
|---|---|---|
| Provider contract | HTML instead of JSON; malformed payload | Stop; verify side effects; retry only after cause is known |
| Rate/availability | Timeout, 429, upstream outage | Bounded retry only for safe reads |
| Destination policy | Blocklist, unsubscribe, reply, bounce | Suppress and reconcile; never bypass or delete/re-add |
| Validation | Missing field, malformed ID, schema mismatch | Repair/fallback or no-send; never submit partial payload |
| Runtime dependency | Unsupported module or import | Replace the dependency or use the bundled runtime; fixture-test before retry |
| Runtime undefined name | Missing helper or stale symbol | Define it, compile it, and exercise the branch before retry |
| Context contract | Tool output replaced prior context; missing pinned input; singular/list drift | Restore explicit input refs and replay only after side effects are reconciled |
| Authorization | Missing or expired connection | Stop and request exact credential repair |
| Partial write | Timeout after submission | Read destination before retry |
| Semantic contract | Manifest, prompt, schema, validator, payload disagreement | Block publish and scale |
| Reconciliation | Write response but readback disagrees | Mark failure and prevent scale |

Report the human-readable node, class, likely side-effect state, affected count, and
next read-only check. Never expose private record values in ordinary logs.
