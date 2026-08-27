# PR #6 readiness-gate repair plan

## Context and current behavior

PR #6 adds capability-aware production audit gates, but review against head
`39e187fa1d215753c8d7b3e288cbbd210844ef87` reproduced two false-positive
readiness paths:

1. `audit_workflow.audit` can return `LIVE_READY` when a run trace contains a
   monotonic success field but no terminal outcome, and it does not require the
   trace or reconciliation success outcome to belong to
   `workflow_contract.terminal_outcomes`.
2. `validate_trigger_safety.analyze_trigger_safety` treats distinct active
   Audience filter fingerprints as proven non-overlapping even though unequal
   filters can select the same records.

The existing 52-test suite and GitHub validation job pass, so both cases need
explicit regression coverage.

## Objective

Make `LIVE_READY` fail closed unless runtime evidence proves an exact declared
terminal outcome and every pair of active or unknown-state Audience cohorts is
either proven disjoint or reported as unresolved.

## Scope

- Bind observed run-trace outcomes to the manifest's declared terminal outcomes.
- Bind the reconciliation success outcome to the same declared outcome set.
- Require at least one observed terminal outcome before run evidence is proven.
- Mark non-identical Audience cohorts unresolved unless overlap or disjointness
  is positively established.
- Add regression tests for both original review reproductions and preserve valid
  fixture behavior.
- Remove the five trailing blank-line warnings reported by `git diff --check`.

## Out of scope

- Changing Clay APIs or collecting raw record identities.
- Adding mutating Clay commands or live production tests.
- Redesigning capability classification, workflow profiles, or unrelated audit
  heuristics.
- Merging PR #6 or deploying/publishing the skill.

## Acceptance mapping

1. A trace with no terminal outcome cannot contribute proven run-outcome
   coverage or produce `LIVE_READY`.
   - Implementation: tighten `analyze_run_traces` and the audit handoff.
   - Validation: a regression test based on the enrichment fixture.
2. Every runtime terminal outcome used for readiness is declared by
   `workflow_contract.terminal_outcomes`.
   - Implementation: pass declared outcomes into trace analysis and validate
     reconciliation `success_outcome` against the contract.
   - Validation: reject a manifest declaring only `failed` when evidence reports
     `activated_verified`.
3. Distinct Audience fingerprints do not prove disjointness.
   - Implementation: emit an unresolved-overlap finding for relevant pairs when
     neither overlap nor disjointness is positively proven.
   - Validation: two active, same-entity segments with different hashes and no
     shared identity hashes must fail closed.
4. Existing valid campaign and enrichment fixtures still reach their expected
   readiness ceilings.
   - Validation: full unit suite and existing positive audit tests.
5. Repository validation is clean.
   - Validation: Python compilation, JSON parsing, `git diff --check`, and the
     repository's full unit suite.

## Affected files and symbols

- `scripts/analyze_run_traces.py`
  - `analyze_run_traces`: require terminal-outcome evidence and optionally check
    exact declared outcome membership.
- `scripts/audit_workflow.py`
  - `audit`: supply the declared terminal outcomes and keep readiness contingent
    on proven outcome coverage.
- `scripts/validate_manifest.py`
  - `analyze_manifest`: validate `reconciliation.success_outcome` against the
    declared terminal outcome contract for external mutations.
- `scripts/validate_trigger_safety.py`
  - `analyze_trigger_safety`: distinguish detected overlap from unresolved
    disjointness instead of silently proving safety.
- `tests/test_scripts.py`
  - Add focused regressions for missing/undeclared outcomes and unresolved
    Audience overlap.
- `references/*.md`
  - Remove only the trailing blank lines identified by `git diff --check`.

## Ordered implementation steps

1. Add failing tests reproducing the exact false `LIVE_READY` and false trigger
   safety results.
2. Extend run-trace analysis with an optional declared-outcomes contract, record
   missing terminal outcomes as unresolved, and reject observed values outside
   the contract.
3. Pass the manifest contract into audit synthesis and validate reconciliation's
   configured success outcome against it.
4. Make trigger cohort comparison fail closed for relevant pairs where the
   available redacted evidence cannot establish disjointness.
5. Remove the existing whitespace warnings without changing reference content.
6. Run focused tests, the complete suite, compilation/JSON checks, and diff
   hygiene.

## Compatibility and migration

- Keep `analyze_run_traces(payload)` valid for callers that do not provide a
  manifest contract; the stricter declared-outcome check is opt-in at the helper
  boundary and always used by `audit_workflow` when a manifest is present.
- Preserve existing outcome classification and contradiction detection.
- Existing evidence bundles without terminal outcomes become `UNKNOWN` rather
  than falsely proven; this is an intentional fail-closed behavior change.
- Distinct Audience segments without positive disjointness evidence become
  unresolved; operators must supply stronger evidence or disable overlapping
  trigger generations before `LIVE_READY`.

## Risks and safety boundaries

- The stricter gates may lower existing workflows from `LIVE_READY` to
  `DRAFT_BLOCKED` or `CANARY_READY`; that is preferable to false production
  proof and should be explicit in findings.
- Do not persist raw Audience identities or provider payloads to prove
  disjointness.
- No production mutation, merge, release, or deployment is authorized.

## Rollout, observability, and rollback

- Deliver as an update to the existing PR #6 branch.
- The audit's existing findings and coverage fields expose the new fail-closed
  reasons.
- Rollback is the single repair commit if the stricter contract causes an
  unintended compatibility regression; no data migration is involved.

## Blockers and readiness verdict

No product decision or external dependency blocks implementation. The fix is
localized and has deterministic offline regression coverage.

Verdict: `READY_TO_PIN`.
