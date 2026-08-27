#!/usr/bin/env python3
"""Validate a governed Clay Workflow contract and its approval binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from classify_workflow import CAPABILITIES, PROFILES, PROFILE_DEFAULTS, expand_capabilities


APPROVAL_KEYS = (
    "paid_work",
    "external_write",
    "publish",
    "copy_generation",
    "audience_write",
    "crm_write",
    "sequencer_write",
    "outbound_activation",
)
OWNER_KEYS = (
    "business_owner",
    "builder",
    "approver",
    "reconciliation_owner",
    "incident_owner",
)
PLACEHOLDER_MARKERS = ("REPLACE_ME", "REPLACE_WITH_")
CONTRACT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
MONOTONIC_FIELD = re.compile(
    r"^[a-z][a-z0-9_]*(?:_executed|_verified|_pass|_completed|_match)$"
)
SENSITIVE_FIELD_TERMS = (
    "email", "phone", "name", "address", "message", "body", "subject",
    "credential", "secret", "token", "key", "payload",
)
WORKFLOW_STATES = {"DRAFT", "PREVIEW_READY", "CANARY_READY", "LIVE_READY"}
CORE_SECTIONS = (
    "template", "sources", "eligibility", "budgets", "approvals",
    "ownership", "operations", "data_handling", "dependencies",
)
DESTINATION_APPROVALS = {
    "audience": "audience_write",
    "crm": "crm_write",
    "sequencer": "sequencer_write",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def normalized_configuration(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the approval-independent configuration that approvals bind to."""
    return {key: value for key, value in manifest.items() if key != "approvals"}


def configuration_hash(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        normalized_configuration(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def placeholder_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(placeholder_paths(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(placeholder_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str) and any(marker in value for marker in PLACEHOLDER_MARKERS):
        found.append(prefix)
    return found


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def exact_sequence_fields(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{index}" for index in range(1, count + 1)]


def workflow_model(manifest: dict[str, Any]) -> tuple[str, set[str], dict[str, Any]]:
    """Resolve the declared profile/capabilities, preserving legacy campaign manifests."""
    contract = manifest.get("workflow_contract")
    if isinstance(contract, dict):
        profile = str(contract.get("profile") or "").strip()
        declared = contract.get("capabilities")
        capabilities = {
            str(item) for item in declared or [] if isinstance(item, str) and item.strip()
        }
        if profile in PROFILE_DEFAULTS:
            capabilities.update(PROFILE_DEFAULTS[profile])
        return profile, expand_capabilities(capabilities), contract

    # v0.7 and earlier manifests were outbound campaign contracts without an
    # explicit profile. Route them through outbound defaults so migration findings
    # are specific instead of treating their shape as an unknown profile.
    campaign = manifest.get("campaign") or {}
    capabilities = expand_capabilities(set(PROFILE_DEFAULTS["outbound_campaign"]))
    return "outbound_campaign", capabilities, {
        "profile": "outbound_campaign",
        "capabilities": sorted(capabilities),
        "state": campaign.get("state"),
        "ready": campaign.get("ready"),
        "unit_of_work": "person",
        "stable_identity_fields": ["campaign_key"],
        "terminal_outcomes": [],
        "monotonic_evidence_fields": [],
    }


def required_approval_keys(capabilities: set[str]) -> set[str]:
    required = {"publish"}
    if "paid_enrichment" in capabilities:
        required.add("paid_work")
    if "copy_sequence" in capabilities:
        required.add("copy_generation")
    if "audience_sync" in capabilities:
        required.add("audience_write")
    if "crm_sync" in capabilities:
        required.add("crm_write")
    if "sequencer_activation" in capabilities:
        required.update({"sequencer_write", "outbound_activation"})
    if "external_mutation" in capabilities and not capabilities.intersection(
        {"audience_sync", "crm_sync", "sequencer_activation"}
    ):
        required.add("external_write")
    return required


def analyze_manifest(
    manifest: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(manifest, dict):
        return {
            "valid": False,
            "configuration_hash": None,
            "findings": [{"severity": "BLOCKER", "code": "manifest_not_an_object"}],
            "summary": {"blockers": 1, "high": 0, "warnings": 0},
        }

    profile, capabilities, workflow_contract = workflow_model(manifest)
    required_sections = list(CORE_SECTIONS)
    if "copy_sequence" in capabilities:
        required_sections.extend(("campaign", "copy_contract"))
    if "external_mutation" in capabilities:
        required_sections.extend(("payload_contract", "destinations", "reconciliation"))
    for section in required_sections:
        if not isinstance(manifest.get(section), dict):
            add(findings, "BLOCKER", "manifest_section_missing", section=section)

    if profile not in PROFILES:
        add(
            findings, "BLOCKER", "workflow_profile_unknown",
            observed=profile, allowed=sorted(PROFILES),
        )
    declared_capabilities = workflow_contract.get("capabilities")
    if not isinstance(declared_capabilities, list) or not all(
        isinstance(item, str) and item.strip() for item in declared_capabilities
    ):
        add(findings, "BLOCKER", "workflow_capabilities_invalid")
    unknown_capabilities = sorted(capabilities - CAPABILITIES)
    if unknown_capabilities:
        add(
            findings, "BLOCKER", "workflow_capability_unknown",
            observed=unknown_capabilities, allowed=sorted(CAPABILITIES),
        )

    placeholders = placeholder_paths(manifest)
    if placeholders:
        add(findings, "BLOCKER", "manifest_placeholders_present", paths=placeholders)

    expected_hash = configuration_hash(manifest)
    approvals = manifest.get("approvals") or {}
    ownership = manifest.get("ownership") or {}
    operations = manifest.get("operations") or {}
    data_handling = manifest.get("data_handling") or {}
    budgets = manifest.get("budgets") or {}
    copy_contract = manifest.get("copy_contract") or {}
    payload_contract = manifest.get("payload_contract") or {}
    dependencies = manifest.get("dependencies") or {}

    state = workflow_contract.get("state")
    if state not in WORKFLOW_STATES:
        add(findings, "BLOCKER", "workflow_state_invalid", observed=state)
    if not isinstance(workflow_contract.get("ready"), bool):
        add(findings, "BLOCKER", "workflow_ready_invalid")
    if not str(workflow_contract.get("unit_of_work") or "").strip():
        add(findings, "BLOCKER", "workflow_unit_of_work_missing")
    for key in ("stable_identity_fields", "terminal_outcomes", "monotonic_evidence_fields"):
        observed = workflow_contract.get(key)
        if not isinstance(observed, list) or not all(
            isinstance(item, str) and item.strip() for item in observed
        ):
            add(findings, "BLOCKER", "workflow_contract_list_invalid", field=key)
    stable_identity_value = workflow_contract.get("stable_identity_fields")
    stable_identity_fields = stable_identity_value if isinstance(stable_identity_value, list) else []
    if isinstance(stable_identity_value, list) and not stable_identity_fields:
        add(findings, "BLOCKER", "stable_identity_fields_missing")
    terminal_outcome_value = workflow_contract.get("terminal_outcomes")
    terminal_outcomes = terminal_outcome_value if isinstance(terminal_outcome_value, list) else []
    if isinstance(terminal_outcome_value, list) and not terminal_outcomes:
        add(findings, "BLOCKER", "terminal_outcomes_missing")
    valid_outcome_names = [item for item in terminal_outcomes if isinstance(item, str)]
    if len(valid_outcome_names) != len(set(valid_outcome_names)):
        add(findings, "BLOCKER", "terminal_outcomes_duplicated")
    invalid_outcomes = sorted(
        str(item) for item in terminal_outcomes
        if not isinstance(item, str) or not CONTRACT_NAME.fullmatch(item)
    )
    if invalid_outcomes:
        add(findings, "BLOCKER", "terminal_outcome_names_invalid", observed=invalid_outcomes)
    if "external_mutation" in capabilities:
        success_outcome = (manifest.get("reconciliation") or {}).get("success_outcome")
        if success_outcome and success_outcome not in valid_outcome_names:
            add(
                findings,
                "BLOCKER",
                "reconciliation_success_outcome_not_declared",
                observed=success_outcome,
                declared_outcomes=valid_outcome_names,
            )
    monotonic_value = workflow_contract.get("monotonic_evidence_fields")
    monotonic_fields = monotonic_value if isinstance(monotonic_value, list) else []
    unsafe_monotonic_fields = sorted(
        str(item)
        for item in monotonic_fields
        if not isinstance(item, str)
        or not MONOTONIC_FIELD.fullmatch(item)
        or any(term in item.lower() for term in SENSITIVE_FIELD_TERMS)
    )
    if unsafe_monotonic_fields:
        add(
            findings,
            "BLOCKER",
            "monotonic_evidence_fields_unsafe",
            observed=unsafe_monotonic_fields,
        )

    campaign = manifest.get("campaign") or {}
    if "copy_sequence" in capabilities:
        for field in ("state", "ready"):
            if field in campaign and campaign.get(field) != workflow_contract.get(field):
                add(
                    findings,
                    "BLOCKER",
                    "campaign_workflow_contract_drift",
                    field=field,
                    workflow_contract=workflow_contract.get(field),
                    campaign=campaign.get(field),
                )

    if "copy_sequence" in capabilities:
        sequence_length = copy_contract.get("sequence_length")
        if not isinstance(sequence_length, int) or isinstance(sequence_length, bool) or sequence_length < 1:
            add(findings, "BLOCKER", "sequence_length_invalid", observed=sequence_length)
        else:
            for key, prefix in (("subject_fields", "subject"), ("body_fields", "body")):
                expected = exact_sequence_fields(prefix, sequence_length)
                observed = copy_contract.get(key)
                if observed != expected:
                    add(
                        findings,
                        "BLOCKER",
                        "sequence_field_contract_mismatch",
                        field=key,
                        expected=expected,
                        observed=observed,
                    )

    destination_fields = payload_contract.get("destination_fields")
    if "external_mutation" in capabilities and not isinstance(destination_fields, dict):
        add(findings, "BLOCKER", "payload_destination_contract_missing")
    elif isinstance(destination_fields, dict):
        for destination, fields in destination_fields.items():
            if not isinstance(fields, list) or not fields or not all(isinstance(item, str) and item for item in fields):
                add(
                    findings,
                    "BLOCKER",
                    "payload_required_fields_invalid",
                    destination=destination,
                    observed=fields,
                )

    numeric_budget_keys = (
        "expected_records", "worst_case_credits_per_record",
        "approved_total_clay_credits", "approved_byoa_cost_usd",
    )
    for key in numeric_budget_keys:
        value = budgets.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            add(findings, "BLOCKER", "budget_invalid", field=key, observed=value)

    custom_functions = dependencies.get("custom_functions")
    if not isinstance(custom_functions, list):
        add(findings, "BLOCKER", "custom_function_dependencies_invalid")
    else:
        seen_function_ids: set[str] = set()
        for index, row in enumerate(custom_functions):
            if not isinstance(row, dict) or not row.get("id"):
                add(findings, "BLOCKER", "custom_function_dependency_invalid", index=index)
                continue
            function_id = str(row["id"])
            if function_id in seen_function_ids:
                add(findings, "BLOCKER", "custom_function_dependency_duplicated", function_id=function_id)
            seen_function_ids.add(function_id)
            digest = str(row.get("sha256") or "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                add(
                    findings,
                    "BLOCKER",
                    "custom_function_dependency_hash_invalid",
                    function_id=function_id,
                    observed=digest,
                )

    applicable_approval_keys = required_approval_keys(capabilities)
    enabled_approvals = [key for key in APPROVAL_KEYS if approvals.get(key) is True]
    missing_approval_flags = sorted(key for key in applicable_approval_keys if key not in approvals)
    if missing_approval_flags:
        add(findings, "BLOCKER", "approval_flags_missing", fields=missing_approval_flags)
    invalid_approval_values = [
        key for key in APPROVAL_KEYS
        if key in approvals and not isinstance(approvals.get(key), bool)
    ]
    if invalid_approval_values:
        add(findings, "BLOCKER", "approval_flags_not_boolean", fields=invalid_approval_values)

    if enabled_approvals:
        if approvals.get("config_hash") != expected_hash:
            add(
                findings,
                "BLOCKER",
                "approval_config_hash_mismatch",
                expected=expected_hash,
                observed=approvals.get("config_hash"),
            )
        for key in ("reference", "approver", "approved_at", "expires_at"):
            if not approvals.get(key):
                add(findings, "BLOCKER", "approval_evidence_missing", field=key)
        approved_at = parse_time(approvals.get("approved_at"))
        expires_at = parse_time(approvals.get("expires_at"))
        if approvals.get("approved_at") and approved_at is None:
            add(findings, "BLOCKER", "approval_timestamp_invalid", field="approved_at")
        if approvals.get("expires_at") and expires_at is None:
            add(findings, "BLOCKER", "approval_timestamp_invalid", field="expires_at")
        if approved_at and approved_at > now + timedelta(minutes=5):
            add(
                findings,
                "BLOCKER",
                "approval_timestamp_in_future",
                approved_at=approved_at.isoformat(),
            )
        if expires_at and expires_at <= now:
            add(findings, "BLOCKER", "approval_expired", expires_at=expires_at.isoformat())
        if approved_at and expires_at and approved_at >= expires_at:
            add(findings, "BLOCKER", "approval_window_invalid")

    if approvals.get("paid_work") is True:
        expected_records = budgets.get("expected_records")
        per_record = budgets.get("worst_case_credits_per_record")
        approved_total = budgets.get("approved_total_clay_credits")
        if all(isinstance(value, (int, float)) for value in (expected_records, per_record, approved_total)):
            worst_total = expected_records * per_record
            if approved_total < worst_total:
                add(
                    findings,
                    "BLOCKER",
                    "approved_clay_credits_below_worst_case",
                    required=worst_total,
                    approved=approved_total,
                )

    if "sequencer_activation" in capabilities and approvals.get("outbound_activation") is True and approvals.get("sequencer_write") is not True:
        add(findings, "BLOCKER", "activation_without_sequencer_write_approval")

    # A LIVE_READY claim must carry approval for every destination the payload
    # contract actually writes to, plus the separate activation approval.  A
    # manifest with configured writes and all-false approvals must never pass
    # merely because it has otherwise complete governance metadata.
    if state == "LIVE_READY":
        missing_capability_approvals = sorted(
            key for key in applicable_approval_keys if approvals.get(key) is not True
        )
        if missing_capability_approvals:
            add(
                findings,
                "BLOCKER",
                "live_ready_capability_approvals_missing",
                fields=missing_capability_approvals,
            )
        configured_destinations = sorted(
            destination
            for destination in (payload_contract.get("destination_fields") or {})
        )
        missing_destination_approvals = [
            DESTINATION_APPROVALS.get(destination, "external_write")
            for destination in configured_destinations
            if approvals.get(DESTINATION_APPROVALS.get(destination, "external_write")) is not True
        ]
        if missing_destination_approvals:
            add(
                findings,
                "BLOCKER",
                "live_ready_destination_approvals_missing",
                fields=missing_destination_approvals,
            )
        if "sequencer_activation" in capabilities and approvals.get("outbound_activation") is not True:
            add(findings, "BLOCKER", "live_ready_outbound_activation_approval_missing")

    production_claim = bool(enabled_approvals or workflow_contract.get("ready") or state == "LIVE_READY")
    if production_claim:
        missing_owners = [key for key in OWNER_KEYS if not ownership.get(key)]
        if missing_owners:
            add(findings, "HIGH", "production_owners_missing", fields=missing_owners)
        if approvals.get("approver") and ownership.get("approver") and approvals.get("approver") != ownership.get("approver"):
            add(findings, "HIGH", "approval_owner_mismatch")
        reconciliation_owner = (manifest.get("reconciliation") or {}).get("owner")
        if reconciliation_owner and ownership.get("reconciliation_owner") and reconciliation_owner != ownership.get("reconciliation_owner"):
            add(findings, "HIGH", "reconciliation_owner_mismatch")

    external_write_approved = any(
        approvals.get(key) is True
        for key in ("external_write", "audience_write", "crm_write", "sequencer_write")
    )
    if external_write_approved:
        kill_switch = operations.get("kill_switch") or {}
        missing_kill_switch = [
            key for key in ("owner", "pause_method", "rollback_snapshot_id", "downstream_remediation_owner")
            if not kill_switch.get(key)
        ]
        if missing_kill_switch:
            add(findings, "HIGH", "kill_switch_incomplete", fields=missing_kill_switch)

    retention_days = data_handling.get("evidence_retention_days")
    if not isinstance(retention_days, int) or isinstance(retention_days, bool) or retention_days < 0:
        add(findings, "HIGH", "evidence_retention_invalid", observed=retention_days)
    redacted = data_handling.get("redacted_fields")
    if not isinstance(redacted, list) or not redacted:
        add(findings, "HIGH", "redacted_fields_missing")
        redacted = []
    raw_retention = data_handling.get("raw_payload_retention_days")
    if not isinstance(raw_retention, int) or isinstance(raw_retention, bool) or raw_retention < 0:
        add(findings, "HIGH", "raw_payload_retention_invalid", observed=raw_retention)
    allowed_logs = data_handling.get("allowed_log_fields")
    if not isinstance(allowed_logs, list):
        add(findings, "HIGH", "allowed_log_fields_invalid")
        allowed_logs = []
    overlap = sorted(set(str(item) for item in allowed_logs) & set(str(item) for item in redacted))
    if overlap:
        add(findings, "BLOCKER", "redacted_fields_allowed_in_logs", fields=overlap)
    if not any(any(term in str(item).lower() for term in ("credential", "secret", "token", "api_key")) for item in redacted):
        add(findings, "HIGH", "credential_redaction_not_declared")
    if not data_handling.get("classification"):
        add(findings, "HIGH", "data_classification_missing")

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "valid": blockers == 0 and high == 0,
        "profile": profile,
        "capabilities": sorted(capabilities),
        "configuration_hash": expected_hash,
        "enabled_approvals": enabled_approvals,
        "findings": findings,
        "summary": {
            "blockers": blockers,
            "high": high,
            "warnings": len(findings) - blockers - high,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a governed Clay Workflow contract.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit 10 for BLOCKER or HIGH findings")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = load_json(args.manifest)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_manifest(manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
