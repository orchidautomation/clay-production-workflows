#!/usr/bin/env python3
"""Validate reconciliation receipts, idempotency, and side-effect certainty."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OUTCOMES = {
    "activated_verified", "already_satisfied", "review_only", "safely_suppressed",
    "provider_failure", "destination_rejection", "reconciliation_failure",
    "completed_verified", "enriched_verified", "routed_verified", "synced_verified",
    "review_required", "safely_skipped", "failed",
}
REQUIRED = (
    "workflow_id", "config_hash", "stable_identity_hash",
    "idempotency_key", "terminal_outcome", "reconciliation_required",
)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def receipt_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [row for row in payload["data"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def intended_destinations(receipt: dict[str, Any]) -> set[str]:
    value = receipt.get("intended_destinations") or {}
    if isinstance(value, list):
        return {str(item) for item in value if item}
    if isinstance(value, dict):
        return {str(key) for key, item in value.items() if item not in (None, False, "")}
    return set()


def verified_readback(value: Any) -> bool:
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    return value.get("verified") is True or str(value.get("status") or "").lower() in {
        "verified", "matched", "already_satisfied",
    }


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def analyze_reconciliation(
    payload: Any,
    expected_config_hash: str | None = None,
    allowed_outcomes: set[str] | None = None,
    success_outcomes: set[str] | None = None,
) -> dict[str, Any]:
    rows = receipt_rows(payload)
    findings: list[dict[str, Any]] = []
    accepted_outcomes = OUTCOMES | (allowed_outcomes or set())
    successful_outcomes = success_outcomes or {"activated_verified"}
    if not rows:
        add(findings, "HIGH", "reconciliation_receipts_missing")

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcome_counts: Counter[str] = Counter()
    for index, receipt in enumerate(rows):
        missing = [key for key in REQUIRED if receipt.get(key) in (None, "")]
        if missing:
            add(findings, "BLOCKER", "reconciliation_required_fields_missing", index=index, fields=missing)
        if expected_config_hash and receipt.get("config_hash") != expected_config_hash:
            add(
                findings,
                "BLOCKER",
                "receipt_config_hash_mismatch",
                index=index,
                expected=expected_config_hash,
                observed=receipt.get("config_hash"),
            )
        outcome = str(receipt.get("terminal_outcome") or "")
        outcome_counts[outcome or "unknown"] += 1
        if outcome not in accepted_outcomes:
            add(findings, "BLOCKER", "terminal_outcome_invalid", index=index, observed=outcome)

        key = str(receipt.get("idempotency_key") or "")
        if key:
            by_key[key].append(receipt)

        intended = intended_destinations(receipt)
        readbacks = receipt.get("readbacks") or {}
        verified = {
            str(destination)
            for destination, value in readbacks.items()
            if verified_readback(value)
        } if isinstance(readbacks, dict) else set()

        if outcome in successful_outcomes:
            outcome_prefix = "activated" if outcome == "activated_verified" else "successful_mutation"
            if not intended:
                add(findings, "BLOCKER", f"{outcome_prefix}_without_intended_destinations", index=index)
            missing_readbacks = sorted(intended - verified)
            if missing_readbacks:
                add(
                    findings,
                    "BLOCKER",
                    f"{outcome_prefix}_without_verified_readbacks",
                    index=index,
                    destinations=missing_readbacks,
                )
            external_receipts = receipt.get("external_receipts") or {}
            missing_write_receipts = sorted(
                destination
                for destination in intended
                if not isinstance(external_receipts, dict)
                or not isinstance(external_receipts.get(destination), dict)
                or not external_receipts[destination]
            )
            if missing_write_receipts:
                add(
                    findings,
                    "BLOCKER",
                    f"{outcome_prefix}_without_external_receipts",
                    index=index,
                    destinations=missing_write_receipts,
                )

            intended_values = receipt.get("intended_destinations") or {}
            for destination in sorted(intended & verified):
                intended_value = intended_values.get(destination) if isinstance(intended_values, dict) else None
                readback_value = readbacks.get(destination) if isinstance(readbacks, dict) else None
                if not isinstance(intended_value, str) or not intended_value:
                    add(
                        findings,
                        "BLOCKER",
                        "intended_destination_id_missing",
                        index=index,
                        destination=destination,
                    )
                    continue
                if not isinstance(readback_value, dict):
                    add(
                        findings,
                        "BLOCKER",
                        "readback_destination_id_missing",
                        index=index,
                        destination=destination,
                        intended=intended_value,
                    )
                    continue
                observed_ids = {
                    str(readback_value[key])
                    for key in (
                        "destination_id", "record_id", "object_id", "external_id",
                        "campaign_id", "audience_id", "contact_id", "company_id",
                        "owner_id", "membership_id",
                    )
                    if readback_value.get(key)
                }
                if intended_value not in observed_ids:
                    add(
                        findings,
                        "BLOCKER",
                        "readback_destination_mismatch",
                        index=index,
                        destination=destination,
                        intended=intended_value,
                        observed=sorted(observed_ids),
                    )

        external_receipts = receipt.get("external_receipts") or {}
        side_effect_state = str(receipt.get("side_effect_state") or "").lower()
        error_text = json.dumps(receipt.get("errors") or receipt.get("error") or "").lower()
        ambiguous = side_effect_state in {"unknown", "uncertain", "submitted_unknown"} or (
            "timeout" in error_text and bool(external_receipts)
        )
        if ambiguous and intended - verified:
            add(
                findings,
                "BLOCKER",
                "external_write_side_effect_unknown",
                index=index,
                destinations=sorted(intended - verified),
                safe_next_action="read_destination_before_retry",
            )

        if receipt.get("reconciliation_required") is True and not receipt.get("reconciliation_owner"):
            add(findings, "HIGH", "reconciliation_owner_missing", index=index)

    for key, duplicates in by_key.items():
        activated = [row for row in duplicates if row.get("terminal_outcome") in successful_outcomes]
        receipt_sets = {
            json.dumps(row.get("external_receipts") or {}, sort_keys=True)
            for row in activated
        }
        if len(activated) > 1 and len(receipt_sets) > 1:
            add(
                findings,
                "BLOCKER",
                (
                    "duplicate_activation_for_idempotency_key"
                    if successful_outcomes == {"activated_verified"}
                    else "duplicate_successful_mutation_for_idempotency_key"
                ),
                idempotency_key=key,
                activated_receipts=len(activated),
            )

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    successful_count = sum(outcome_counts.get(outcome, 0) for outcome in successful_outcomes)
    return {
        "valid": blockers == 0 and high == 0,
        "live_ready_proven": bool(rows) and successful_count > 0 and blockers == 0 and high == 0,
        "receipt_count": len(rows),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "findings": findings,
        "summary": {"blockers": blockers, "high": high, "warnings": len(findings) - blockers - high},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Clay reconciliation receipts.")
    parser.add_argument("receipts", type=Path)
    parser.add_argument("--manifest", type=Path, help="Optional manifest whose normalized configuration hash must match receipts")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = load_json(args.receipts)
        expected_hash = None
        allowed_outcomes = None
        success_outcomes = None
        if args.manifest:
            from validate_manifest import configuration_hash
            manifest = load_json(args.manifest)
            expected_hash = configuration_hash(manifest)
            contract = manifest.get("workflow_contract") or {}
            allowed_outcomes = {
                str(item) for item in contract.get("terminal_outcomes") or [] if item
            }
            success = (manifest.get("reconciliation") or {}).get("success_outcome")
            success_outcomes = {str(success)} if success else None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_reconciliation(
        payload, expected_hash, allowed_outcomes, success_outcomes
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
