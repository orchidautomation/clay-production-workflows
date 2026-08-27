# Script Contracts

- Non-interactive; flags only; concise `--help`.
- JSON to stdout; diagnostics to stderr.
- Exit `2` invalid input, `3` missing dependency, `4` auth/access, `5` Clay command,
  `6` filesystem, and `10` strict audit blockers.
- Collector commands are read-only: never test, publish, update triggers, resume, or mutate.
- Evidence bundles carry `evidence_contract_version`; reject incompatible required
  JSON shapes rather than silently treating absent fields as empty evidence.
- Contract v2 adds `current-snapshot.json`, redacted `audience-segments.json`,
  `function-fingerprints.json`, and allowlisted `run-traces.json`. Contract v1 remains
  readable but must report those checks as unavailable.
- Hash Audience identity values and custom-function definitions before writing them.
  Outcome traces may contain only the documented safety/status allowlist; never
  write emails, message bodies, credentials, or raw provider payloads.
- Raw data goes to an explicit directory; stdout stays compact.
- Fixture analysis works offline.
- Add unit tests whenever parsing or severity logic changes.
- Classifiers return applicable and not-applicable checks explicitly. Conditional
  validators must use `NOT_APPLICABLE`; absence of an irrelevant feature is not a pass
  or a failure.
- Declared capabilities express intent; detected executable capabilities may only add
  safeguards, never suppress them. Report the drift so the contract can be reconciled.
