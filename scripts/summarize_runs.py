#!/usr/bin/env python3
"""Summarize Clay run statuses without claiming completed means activated."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def classify_error(text: str) -> tuple[str, str]:
    lower = text.lower()
    if "modulenotfounderror" in lower or "no module named" in lower or "importerror" in lower:
        return "runtime_dependency_failure", "replace_unsupported_dependency_or_use_bundled_runtime"
    if "nameerror" in lower or "is not defined" in lower:
        return "runtime_undefined_name", "define_and_fixture_test_the_missing_helper_before_retry"
    if ("unexpected token '<'" in lower or "<html" in lower) and "json" in lower:
        return "provider_contract_failure", "verify_provider_side_effects_before_retry"
    if "blocklist" in lower:
        return "destination_rejection", "reconcile_as_suppressed_and_do_not_bypass"
    if any(term in lower for term in ("unsubscribed", "bounced", "prior reply", "replied")):
        return "destination_policy_suppression", "reconcile_as_safely_suppressed"
    if "429" in lower or "rate limit" in lower:
        return "rate_limited", "bounded_retry_only_if_operation_is_read_only"
    if "timeout" in lower or "timed out" in lower:
        return "timeout", "read_destination_before_retrying_a_write"
    if any(term in lower for term in ("unauthorized", "forbidden", "credential", "not logged in")):
        return "authorization_failure", "repair_exact_connection_or_scope"
    if "bad_request" in lower or "invalid" in lower or "missing" in lower:
        return "validation_failure", "repair_inputs_or_route_to_no_send"
    return "unclassified_failure", "inspect_failed_node_and_reconcile_side_effects"


def summarize(
    runs: dict[str, Any],
    failed_runs: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = list(runs.get("data") or [])
    counts = Counter(str(row.get("status") or "unknown") for row in rows)
    node_names = {
        str(node.get("id")): str(node.get("name"))
        for node in (graph or {}).get("nodes") or []
        if isinstance(node, dict) and node.get("id") and node.get("name")
    }
    failures = []
    for run in (failed_runs or {}).get("data") or []:
        for node in run.get("failed_nodes") or []:
            for error in node.get("errors") or ["unknown failure"]:
                category, action = classify_error(str(error))
                failures.append(
                    {
                        "run_id": run.get("runId"),
                        "node_id": node.get("nodeId"),
                        "node_name": node.get("name") or node_names.get(str(node.get("nodeId"))),
                        "category": category,
                        "safe_next_action": action,
                        "error_excerpt": re.sub(r"\s+", " ", str(error))[:500],
                    }
                )
    return {
        "run_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "completed_count": counts.get("completed", 0),
        "activation_rate": None,
        "activation_rate_reason": "Run metadata does not prove terminal business outcomes or destination readbacks.",
        "completed_is_not_business_success": True,
        "failures": failures,
        "failure_category_counts": dict(sorted(Counter(item["category"] for item in failures).items())),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize Clay Workflow run metadata and failed-node errors.")
    parser.add_argument("runs", type=Path, help="runs.json from the evidence collector")
    parser.add_argument("--failed-runs", type=Path, help="Optional failed-runs.json")
    parser.add_argument("--graph", type=Path, help="Optional graph.json for node ID to name mapping")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        runs = load_json(args.runs)
        failed = load_json(args.failed_runs) if args.failed_runs else None
        graph = load_json(args.graph) if args.graph else None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summarize(runs, failed, graph), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
