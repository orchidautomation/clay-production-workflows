#!/usr/bin/env python3
"""Detect duplicate or overlapping Clay trigger cohorts without exposing identities."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def trigger_state(trigger: dict[str, Any]) -> str:
    raw = str(trigger.get("status") or trigger.get("state") or "").strip().lower()
    if raw in {"active", "enabled", "running", "live", "published"}:
        return "active"
    if raw in {"paused", "disabled", "inactive", "draft", "archived"}:
        return "inactive"
    if isinstance(trigger.get("enabled"), bool):
        return "active" if trigger["enabled"] else "inactive"
    return "unknown"


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def analyze_trigger_safety(
    triggers: dict[str, Any], audience_segments: dict[str, Any] | None = None
) -> dict[str, Any]:
    trigger_rows = [row for row in triggers.get("data") or [] if isinstance(row, dict)]
    summaries = {
        str(row.get("segment_id")): row
        for row in (audience_segments or {}).get("data") or []
        if isinstance(row, dict) and row.get("segment_id")
    }
    findings: list[dict[str, Any]] = []
    states = {str(row.get("id")): trigger_state(row) for row in trigger_rows}

    for left, right in combinations(trigger_rows, 2):
        left_segment = str(left.get("segmentId") or "")
        right_segment = str(right.get("segmentId") or "")
        if not left_segment or not right_segment:
            continue
        left_state = trigger_state(left)
        right_state = trigger_state(right)
        if "inactive" in {left_state, right_state}:
            continue
        severity = "BLOCKER" if left_state == right_state == "active" else "HIGH"
        common = {
            "left_trigger_id": left.get("id"),
            "right_trigger_id": right.get("id"),
            "left_state": left_state,
            "right_state": right_state,
        }
        if left_segment == right_segment:
            add(
                findings,
                severity,
                "multiple_triggers_share_segment",
                segment_id=left_segment,
                **common,
            )
            continue
        left_summary = summaries.get(left_segment) or {}
        right_summary = summaries.get(right_segment) or {}
        if not left_summary or not right_summary:
            add(
                findings,
                severity,
                "trigger_cohort_overlap_unresolved",
                left_segment_id=left_segment,
                right_segment_id=right_segment,
                consequence="redacted segment evidence is insufficient to prove disjointness",
                **common,
            )
            continue
        if left_summary.get("entity_type") != right_summary.get("entity_type"):
            continue
        left_hashes = set(left_summary.get("identity_value_hashes") or [])
        right_hashes = set(right_summary.get("identity_value_hashes") or [])
        overlap = left_hashes & right_hashes
        same_filter = bool(
            left_summary.get("filter_sha256")
            and left_summary.get("filter_sha256") == right_summary.get("filter_sha256")
        )
        if overlap or same_filter:
            add(
                findings,
                severity,
                "trigger_cohorts_overlap",
                left_segment_id=left_segment,
                right_segment_id=right_segment,
                left_name=left_summary.get("name"),
                right_name=right_summary.get("name"),
                overlapping_identity_count=len(overlap),
                identical_filter=same_filter,
                activation_state_proven=left_state != "unknown" and right_state != "unknown",
                **common,
            )
        else:
            add(
                findings,
                severity,
                "trigger_cohort_overlap_unresolved",
                left_segment_id=left_segment,
                right_segment_id=right_segment,
                left_name=left_summary.get("name"),
                right_name=right_summary.get("name"),
                overlapping_identity_count=0,
                identical_filter=False,
                consequence="distinct filters do not prove disjointness",
                **common,
            )

    unknown_count = sum(state == "unknown" for state in states.values())
    if trigger_rows and unknown_count:
        add(
            findings,
            "MEDIUM",
            "trigger_activation_state_unknown",
            trigger_count=len(trigger_rows),
            unknown_count=unknown_count,
        )
    if trigger_rows and not summaries:
        add(
            findings,
            "MEDIUM",
            "audience_segment_fingerprints_not_supplied",
            consequence="cohort_overlap_not_checked",
        )

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "valid": blockers == 0 and high == 0,
        "trigger_count": len(trigger_rows),
        "trigger_states": states,
        "findings": findings,
        "summary": {
            "blockers": blockers,
            "high": high,
            "warnings": len(findings) - blockers - high,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Clay trigger overlap and activation state.")
    parser.add_argument("triggers", type=Path)
    parser.add_argument("--audience-segments", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        triggers = load_json(args.triggers)
        segments = load_json(args.audience_segments) if args.audience_segments else None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_trigger_safety(triggers, segments)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
