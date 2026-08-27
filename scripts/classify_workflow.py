#!/usr/bin/env python3
"""Classify Clay Workflow capabilities and route only applicable production checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from validate_graph_controls import custom_function_ids, destination_for, is_write


PROFILES = {
    "generic_production",
    "enrichment_sync",
    "inbound_routing",
    "crm_sync",
    "outbound_campaign",
    "audience_integration",
}

CAPABILITIES = {
    "routing",
    "paid_enrichment",
    "external_mutation",
    "audience_sync",
    "audience_triggered",
    "crm_sync",
    "copy_sequence",
    "sequencer_activation",
    "suppression",
    "custom_functions",
}

PROFILE_DEFAULTS = {
    "generic_production": set(),
    "enrichment_sync": {"paid_enrichment"},
    "inbound_routing": {"routing"},
    "crm_sync": {"external_mutation", "crm_sync"},
    "outbound_campaign": {
        "external_mutation",
        "copy_sequence",
        "sequencer_activation",
        "suppression",
    },
    "audience_integration": set(),
}

PROFILE_REFERENCES = {
    "generic_production": "references/applicability-and-profiles.md",
    "enrichment_sync": "references/profile-enrichment-sync.md",
    "inbound_routing": "references/profile-inbound-routing.md",
    "crm_sync": "references/profile-crm-sync.md",
    "outbound_campaign": "references/profile-outbound-campaign.md",
    "audience_integration": "references/profile-audience-triggered.md",
}

UNIVERSAL_CHECKS = {
    "approval_binding",
    "cost_and_authorization",
    "evidence_compatibility",
    "graph_controls",
    "runtime_outcomes",
    "snapshot_semantics",
    "structural_validation",
}

CAPABILITY_CHECKS = {
    "audience_triggered": {"trigger_overlap"},
    "copy_sequence": {"sequence_contract"},
    "custom_functions": {"custom_function_fingerprints"},
    "external_mutation": {"destination_reconciliation", "idempotency"},
    "paid_enrichment": {"credit_budget", "cache_policy"},
    "routing": {"assignment_contract", "routing_coverage"},
    "sequencer_activation": {"suppression", "activation_readback"},
}
CAPABILITY_IMPLICATIONS = {
    "audience_sync": {"external_mutation"},
    "crm_sync": {"external_mutation"},
    "sequencer_activation": {"external_mutation", "suppression"},
}


def expand_capabilities(capabilities: set[str]) -> set[str]:
    expanded = set(capabilities)
    changed = True
    while changed:
        before = len(expanded)
        for capability in tuple(expanded):
            expanded.update(CAPABILITY_IMPLICATIONS.get(capability, set()))
        changed = len(expanded) != before
    return expanded


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def owned_text(node: dict[str, Any]) -> str:
    parts = [
        str(node.get("name") or ""),
        str(node.get("description") or ""),
        str(node.get("code") or ""),
        str(node.get("agentPrompt") or ""),
    ]
    for tool in node.get("tools") or []:
        if isinstance(tool, dict):
            parts.extend(str(tool.get(key) or "") for key in ("actionKey", "name", "description"))
    return " ".join(parts).lower()


def declared_contract(manifest: dict[str, Any] | None) -> tuple[str | None, set[str]]:
    contract = (manifest or {}).get("workflow_contract") or {}
    profile = str(contract.get("profile") or "").strip() or None
    capabilities = {
        str(item) for item in contract.get("capabilities") or [] if str(item).strip()
    }
    if profile in PROFILE_DEFAULTS:
        capabilities.update(PROFILE_DEFAULTS[profile])
    return profile, expand_capabilities(capabilities)


def detect_capabilities(
    graph: dict[str, Any], triggers: dict[str, Any] | None = None
) -> set[str]:
    nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict)]
    detected: set[str] = set()
    writes = [node for node in nodes if is_write(node)]
    if writes:
        detected.add("external_mutation")
    destinations = {destination_for(node) for node in writes}
    if "audience" in destinations:
        detected.add("audience_sync")
    if "crm" in destinations:
        detected.add("crm_sync")
    if "sequencer" in destinations:
        detected.update({"sequencer_activation", "suppression"})
    if any(custom_function_ids(node) for node in nodes):
        detected.add("custom_functions")
    if any(
        str(node.get("nodeType") or "").lower() == "conditional"
        and re.search(
            r"\b(route|routing|assign|assignment|owner|rep|territory|round[- ]robin|queue|sla)\b",
            owned_text(node),
        )
        for node in nodes
    ):
        detected.add("routing")

    text = " ".join(owned_text(node) for node in nodes)
    if re.search(r"\b(subject|body)_?\d+\b|copy[_ -]?sequence|sequence_length", text):
        detected.add("copy_sequence")
    if re.search(r"\b(paid|credit-consuming|enrich|claygent|waterfall|find[- ]email)\b", text):
        detected.add("paid_enrichment")
    if re.search(r"\b(suppress|unsubscribe|blocklist|bounce|prior reply)\b", text):
        detected.add("suppression")

    trigger_rows = [
        row for row in (triggers or {}).get("data") or [] if isinstance(row, dict)
    ]
    if any(row.get("segmentId") for row in trigger_rows):
        detected.add("audience_triggered")
    return expand_capabilities(detected)


def infer_profiles(capabilities: set[str], graph: dict[str, Any]) -> set[str]:
    profiles: set[str] = set()
    text = " ".join(
        owned_text(node) for node in graph.get("nodes") or [] if isinstance(node, dict)
    )
    if {"copy_sequence", "sequencer_activation"} & capabilities:
        profiles.add("outbound_campaign")
    if "crm_sync" in capabilities and "sequencer_activation" not in capabilities:
        profiles.add("crm_sync")
    if "paid_enrichment" in capabilities and "copy_sequence" not in capabilities:
        profiles.add("enrichment_sync")
    if "routing" in capabilities and re.search(
        r"\b(inbound|route|routing|assign|assignment|owner|rep|territory|sla)\b", text
    ):
        profiles.add("inbound_routing")
    if not profiles:
        profiles.add("generic_production")
    return profiles


def classify_workflow(
    graph: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    triggers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    declared_profile, declared = declared_contract(manifest)
    detected = detect_capabilities(graph, triggers)
    effective = declared | detected
    inferred_profiles = infer_profiles(effective, graph)
    profiles = set(inferred_profiles)
    if declared_profile:
        profiles.add(declared_profile)
    if {"audience_triggered", "audience_sync"} & effective:
        profiles.add("audience_integration")

    findings: list[dict[str, Any]] = []
    if declared_profile and declared_profile not in PROFILES:
        findings.append({
            "severity": "BLOCKER",
            "code": "workflow_profile_unknown",
            "observed": declared_profile,
            "allowed": sorted(PROFILES),
        })
    unknown_capabilities = sorted(declared - CAPABILITIES)
    if unknown_capabilities:
        findings.append({
            "severity": "BLOCKER",
            "code": "workflow_capability_unknown",
            "observed": unknown_capabilities,
            "allowed": sorted(CAPABILITIES),
        })
    undeclared_detected = sorted(detected - declared)
    if manifest and undeclared_detected:
        findings.append({
            "severity": "MEDIUM",
            "code": "detected_capability_not_declared",
            "capabilities": undeclared_detected,
            "consequence": "relevant_checks_still_apply_but_the_manifest_should_be_reconciled",
        })
    observable_declared = set(declared)
    if triggers is None:
        observable_declared.discard("audience_triggered")
    declared_not_detected = sorted(observable_declared - detected)
    if manifest and graph.get("nodes") and declared_not_detected:
        findings.append({
            "severity": "MEDIUM",
            "code": "declared_capability_not_detected",
            "capabilities": declared_not_detected,
            "consequence": "confirm_the_graph_is_incomplete_or_correct_the_declared_contract",
        })

    applicable_checks = set(UNIVERSAL_CHECKS)
    for capability in effective:
        applicable_checks.update(CAPABILITY_CHECKS.get(capability, set()))
    all_conditional_checks = set().union(*CAPABILITY_CHECKS.values())
    references = {"references/applicability-and-profiles.md"}
    references.update(PROFILE_REFERENCES[profile] for profile in profiles if profile in PROFILE_REFERENCES)

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    return {
        "valid": blockers == 0,
        "primary_profile": declared_profile or sorted(inferred_profiles)[0],
        "profile_source": "manifest" if declared_profile else "inferred",
        "profiles": sorted(profiles),
        "capabilities": {
            "declared": sorted(declared),
            "detected": sorted(detected),
            "effective": sorted(effective),
        },
        "applicable_checks": sorted(applicable_checks),
        "not_applicable_checks": sorted(all_conditional_checks - applicable_checks),
        "references_to_read": sorted(references),
        "findings": findings,
        "summary": {
            "blockers": blockers,
            "warnings": len(findings) - blockers,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify Clay Workflow production capabilities.")
    parser.add_argument("graph", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--triggers", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        graph = load_json(args.graph)
        manifest = load_json(args.manifest) if args.manifest else None
        triggers = load_json(args.triggers) if args.triggers else None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = classify_workflow(graph, manifest, triggers)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
