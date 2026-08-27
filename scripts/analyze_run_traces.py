#!/usr/bin/env python3
"""Detect contradictory terminal and side-effect states in compact run traces."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MONOTONIC_TRUE_FIELDS = (
    "activation_executed",
    "external_send_executed",
    "instantly_write_executed",
    "instantly_campaign_enrollment_executed",
    "instantly_campaign_membership_verified",
    "salesforce_write_executed",
    "salesforce_contact_write_executed",
    "salesforce_account_write_executed",
    "salesforce_campaign_member_write_executed",
    "salesforce_primary_campaign_member_verified",
    "salesforce_secondary_campaign_member_verified",
    "salesforce_readback_pass",
    "salesforce_readback_completed",
    "salesforce_readback_identity_match",
    "salesforce_readback_patch_match",
    "audience_person_upsert_executed",
    "audience_activation_marker_write_executed",
    "audience_company_salesforce_id_sync_executed",
    "audience_person_salesforce_id_sync_executed",
    "write_executed",
    "mutation_executed",
    "readback_verified",
    "enrichment_verified",
    "routing_verified",
    "sync_verified",
)


def is_monotonic_true_field(field: str) -> bool:
    return field in MONOTONIC_TRUE_FIELDS or bool(
        re.search(r"(?:_executed|_verified|_pass|_completed|_match)$", field)
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def outcome_class(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if "activated" in text or "enrollment_verified" in text:
        return "activated"
    if any(term in text for term in ("completed_verified", "enriched_verified", "routed_verified", "synced_verified")):
        return "successful"
    if text.endswith("_verified"):
        return "successful"
    if "already" in text and "satisfied" in text:
        return "already_satisfied"
    if "suppress" in text or "no_send" in text:
        return "safely_suppressed"
    if "stopped_before" in text or text.startswith("stop"):
        return "stopped"
    if "review" in text:
        return "review"
    if "skip" in text:
        return "safely_skipped"
    if "provider" in text or "destination" in text or "reconciliation" in text:
        return "failure"
    if "fail" in text or "error" in text:
        return "failure"
    return "other"


def node_fields(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("fields", "output", "result"):
        value = node.get(key)
        if isinstance(value, dict):
            return value
    return {}


def analyze_run_traces(
    payload: dict[str, Any], declared_outcomes: set[str] | None = None
) -> dict[str, Any]:
    runs = [run for run in payload.get("data") or [] if isinstance(run, dict)]
    findings: list[dict[str, Any]] = []
    run_summaries: list[dict[str, Any]] = []
    traced_node_count = 0
    for run in runs:
        seen_true: dict[str, str] = {}
        outcomes: list[dict[str, Any]] = []
        nodes = run.get("nodes") or []
        traced_node_count += len(nodes)
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            fields = node_fields(node)
            node_name = str(node.get("name") or node.get("nodeId") or index)
            for field in sorted(str(key) for key in fields if is_monotonic_true_field(str(key))):
                if fields.get(field) is True:
                    seen_true.setdefault(field, node_name)
                elif fields.get(field) is False and field in seen_true:
                    add(
                        findings,
                        "BLOCKER",
                        "proven_side_effect_downgraded_later_in_run",
                        run_id=run.get("runId"),
                        field=field,
                        proven_at=seen_true[field],
                        downgraded_at=node_name,
                    )
            outcome = fields.get("workflow_outcome") or fields.get("terminal_outcome")
            category = outcome_class(outcome)
            if category:
                outcome_value = str(outcome)
                normalized_declared = {
                    str(item).strip().lower() for item in declared_outcomes or set()
                }
                if declared_outcomes is not None and outcome_value.strip().lower() not in normalized_declared:
                    add(
                        findings,
                        "BLOCKER",
                        "terminal_outcome_not_declared",
                        run_id=run.get("runId"),
                        node=node_name,
                        outcome=outcome_value,
                        declared_outcomes=sorted(declared_outcomes),
                    )
                outcomes.append(
                    {"node": node_name, "value": outcome_value, "class": category, "index": index}
                )

        activated = [item for item in outcomes if item["class"] == "activated"]
        stopped = [item for item in outcomes if item["class"] == "stopped"]
        if activated and stopped and max(item["index"] for item in stopped) > min(item["index"] for item in activated):
            add(
                findings,
                "BLOCKER",
                "activated_outcome_reclassified_as_pre_activation_stop",
                run_id=run.get("runId"),
                activated=activated,
                stopped=stopped,
            )
        successful = [item for item in outcomes if item["class"] == "successful"]
        if successful and stopped and max(item["index"] for item in stopped) > min(item["index"] for item in successful):
            add(
                findings,
                "BLOCKER",
                "verified_success_reclassified_as_pre_completion_stop",
                run_id=run.get("runId"),
                successful=successful,
                stopped=stopped,
            )
        terminal_classes = {
            item["class"] for item in outcomes
            if item["class"] in {
                "activated", "successful", "already_satisfied", "review",
                "safely_suppressed", "safely_skipped", "stopped", "failure",
            }
        }
        if len(terminal_classes) > 1:
            add(
                findings,
                "HIGH",
                "multiple_incompatible_outcome_classes_in_run",
                run_id=run.get("runId"),
                classes=sorted(terminal_classes),
                outcomes=outcomes,
            )
        if not outcomes:
            add(
                findings,
                "MEDIUM",
                "terminal_outcome_unknown",
                run_id=run.get("runId"),
                consequence="run evidence cannot prove terminal outcome coverage",
            )
        run_summaries.append(
            {
                "run_id": run.get("runId"),
                "node_count": len(run.get("nodes") or []),
                "outcomes": outcomes,
                "proven_true_fields": sorted(seen_true),
            }
        )

    if not runs:
        add(
            findings,
            "MEDIUM",
            "run_trace_outcomes_unknown",
            consequence="no_redacted_run_trace_was_collected",
        )
    elif traced_node_count == 0:
        add(
            findings,
            "MEDIUM",
            "run_trace_outcomes_unknown",
            consequence="run_metadata_exists_but_no_node_outputs_were_collected",
        )

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "valid": blockers == 0 and high == 0,
        "run_count": len(runs),
        "traced_node_count": traced_node_count,
        "runs": run_summaries,
        "findings": findings,
        "summary": {
            "blockers": blockers,
            "high": high,
            "warnings": len(findings) - blockers - high,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit compact Clay run outcome traces.")
    parser.add_argument("run_traces", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = load_json(args.run_traces)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_run_traces(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
