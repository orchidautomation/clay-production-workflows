# Enrichment and Research Profile

Read this reference when paid or cached data providers enrich, research, normalize,
or score people, companies, or other records.

## Additional invariants

- Define required fields, acceptable evidence, freshness, normalization, and source
  precedence before selecting providers.
- Use deterministic existing values and valid cache entries before paid actions.
- Calculate worst-case credits per record and per bounded cohort, including fallbacks.
- Distinguish provider success from a usable value; validate the actual returned field.
- Record provider, timestamp, confidence or evidence, credit use, and fallback path
  when those facts affect downstream decisions.
- Bound waterfalls and retries. A missing value is not permission to run every provider.
- Treat unsupported, stale, conflicting, and unverifiable values as explicit outcomes.
- If enriched values are written elsewhere, also load the relevant mutation profile.

Do not require campaign copy or outbound suppression for enrichment-only workflows.
