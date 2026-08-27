#!/usr/bin/env python3
"""Audit external writes, payload mappings, terminals, and readbacks in a graph."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


OUTCOMES = {
    "activated_verified", "already_satisfied", "review_only", "safely_suppressed",
    "provider_failure", "destination_rejection", "reconciliation_failure",
    "completed_verified", "enriched_verified", "routed_verified", "synced_verified",
    "review_required", "safely_skipped", "failed",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def node_text(node: dict[str, Any]) -> str:
    return json.dumps(node, sort_keys=True).lower()


def own_text(node: dict[str, Any]) -> str:
    """Return text owned by this node, excluding referenced graph metadata."""
    parts = [
        str(node.get("name") or ""),
        str(node.get("description") or ""),
        str(node.get("code") or ""),
    ]
    for tool in node.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        parts.extend(
            str(tool.get(key) or "")
            for key in ("actionKey", "name", "description", "toolType")
        )
    return " ".join(parts).lower()


def destination_for(node: dict[str, Any]) -> str | None:
    text = own_text(node)
    if "audience" in text or "upsert-audiences-record" in text:
        return "audience"
    if any(term in text for term in ("salesforce", "hubspot", "crm", "campaignmember")):
        return "crm"
    if any(term in text for term in ("instantly", "smartlead", "outreach", "sequencer", "enroll")):
        return "sequencer"
    return None


def mentions_destination(node: dict[str, Any], destination: str) -> bool:
    text = re.sub(r"[_-]+", " ", own_text(node))
    expected = re.sub(r"[_-]+", " ", destination.lower()).strip()
    return bool(expected and expected in text)


def action_keys(node: dict[str, Any]) -> list[str]:
    return [
        str(tool.get("actionKey") or "").lower()
        for tool in node.get("tools") or []
        if isinstance(tool, dict)
    ]


def custom_function_ids(node: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for tool in node.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("toolType") != "clay_function":
            continue
        function_id = tool.get("tableId") or tool.get("id")
        if function_id:
            ids.append(str(function_id))
    return sorted(set(ids))


def is_write(node: dict[str, Any]) -> bool:
    node_type = str(node.get("nodeType") or "").lower()
    text = own_text(node)
    markers = (
        "[external mutation]",
        "[external mutation function]",
        "[bounded mutation]",
        "[outbound activation]",
    )
    if node_type == "tool" and any(marker in text for marker in markers):
        return True
    verbs = ("create", "update", "upsert", "enroll", "add-lead", "send", "write")
    if node_type == "tool" and any(
        any(verb in action for verb in verbs) for action in action_keys(node)
    ):
        return True
    explicit_no_write = bool(
        re.search(
            r"\bno\s+(?:[a-z]+\s+){0,3}(?:external\s+)?(?:write|mutation|update|create)\b",
            text,
        )
    )
    return bool(
        node_type == "tool"
        and custom_function_ids(node)
        and not explicit_no_write
        and any(verb in text for verb in ("create", "update", "upsert", "mutation", "write"))
    )


def is_readback(node: dict[str, Any]) -> bool:
    if str(node.get("nodeType") or "").lower() != "tool" or is_write(node):
        return False
    read_verbs = ("get", "list", "lookup", "search", "find")
    keys = action_keys(node)
    if any(any(verb in action for verb in read_verbs) for action in keys):
        return True
    return "[read only]" in own_text(node) and bool(node.get("tools"))


def is_approval_control(node: dict[str, Any]) -> bool:
    name = str(node.get("name") or "").lower()
    code = str(node.get("code") or "").lower()
    return bool(
        any(term in name for term in ("approved?", "approval", "preflight"))
        or (
            str(node.get("nodeType") or "").lower() in {"code", "conditional"}
            and "config_hash" in code
            and "approv" in code
        )
    )


def assigned_names(value: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(value) if isinstance(item, ast.Name)}


def subscript_key(target: ast.AST) -> tuple[str | None, str | None]:
    if not isinstance(target, ast.Subscript) or not isinstance(target.value, ast.Name):
        return None, None
    key_node = target.slice
    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
        return target.value.id, key_node.value
    return target.value.id, None


def approval_assignment_target(target: ast.AST) -> tuple[str | None, str | None]:
    if isinstance(target, ast.Name):
        return None, target.id
    if isinstance(target, ast.Attribute):
        owner = target.value.id if isinstance(target.value, ast.Name) else None
        return owner, target.attr
    return subscript_key(target)


def circular_approval_assignments(node: dict[str, Any]) -> list[dict[str, Any]]:
    code = str(node.get("code") or "")
    if not code or "approv" not in code.lower() or "config_hash" not in code.lower():
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    findings: list[dict[str, Any]] = []
    risky = {
        "approved_config_hash": {"config_hash", "current_config_hash"},
        "approval_reference": {"required_approval_reference", "approval_reference"},
    }
    for item in ast.walk(tree):
        if not isinstance(item, (ast.Assign, ast.AnnAssign)):
            continue
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        value = item.value
        if value is None:
            continue
        names = assigned_names(value)
        for target in targets:
            owner, key = approval_assignment_target(target)
            owned_by_approval = owner is None or "approv" in owner.lower()
            if owned_by_approval and key in risky and names & risky[key]:
                findings.append({"field": key, "line": getattr(item, "lineno", None)})
    return findings


def edge_pair(edge: dict[str, Any]) -> tuple[str | None, str | None]:
    source = edge.get("sourceNodeId") or edge.get("sourceNode") or edge.get("source") or edge.get("from")
    target = edge.get("targetNodeId") or edge.get("targetNode") or edge.get("target") or edge.get("to")
    return (str(source) if source else None, str(target) if target else None)


def graph_edges(graph: dict[str, Any]) -> list[tuple[str, str]]:
    resolved: list[tuple[str, str]] = []
    for edge in (graph.get("summary") or {}).get("edges") or graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source, target = edge_pair(edge)
        if source and target:
            resolved.append((source, target))
    for node in graph.get("nodes") or []:
        target = node.get("id")
        for edge in node.get("incomingEdges") or []:
            if not isinstance(edge, dict):
                continue
            source = edge.get("sourceNode") or edge.get("sourceNodeId")
            if source and target:
                resolved.append((str(source), str(target)))
    return sorted(set(resolved))


def reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(adjacency.get(start, set()))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, set()) - seen)
    return seen


def mapped_fields(node: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for schema_key in ("inputSchema", "outputSchema"):
        schema = node.get(schema_key) or {}
        properties = schema.get("properties") if isinstance(schema, dict) else None
        if isinstance(properties, dict):
            fields.update(str(key) for key in properties)
        elif isinstance(schema, dict):
            fields.update(str(key) for key in schema)
    for tool in node.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        mapping = tool.get("inputMappingConfig") or {}
        if isinstance(mapping, dict):
            fields.update(str(key) for key in mapping)
    code = str(node.get("code") or "")
    fields.update(re.findall(r"[\"']([A-Za-z][A-Za-z0-9_]*)[\"']\s*:", code))
    return fields


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def analyze_graph_controls(
    graph: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    function_fingerprints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict)]
    by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    edges = graph_edges(graph)
    adjacency: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        adjacency[source].add(target)
        reverse[target].add(source)

    findings: list[dict[str, Any]] = []
    writes = [node for node in nodes if is_write(node)]
    readbacks = [node for node in nodes if is_readback(node)]
    approval_nodes = [node for node in nodes if is_approval_control(node)]
    for node in nodes:
        for detail in circular_approval_assignments(node):
            add(
                findings,
                "BLOCKER",
                "approval_evidence_derived_from_current_configuration",
                node=node.get("name"),
                node_id=node.get("id"),
                **detail,
            )
    if len(nodes) > 1 and not edges:
        add(findings, "MEDIUM", "graph_edges_unavailable", consequence="branch_and_readback_reachability_unknown")

    for write in writes:
        write_id = str(write.get("id"))
        destination = destination_for(write)
        # A generic lookup cannot prove a destination-specific mutation. Keep
        # unknown-destination reads paired only with unknown-destination writes.
        candidates = [
            node for node in readbacks
            if destination_for(node) == destination
        ]
        if edges:
            downstream = reachable(write_id, adjacency)
            candidates = [node for node in candidates if str(node.get("id")) in downstream]
            if not candidates:
                add(
                    findings,
                    "BLOCKER",
                    "external_write_without_downstream_readback",
                    node=write.get("name"),
                    destination=destination,
                )
        elif not candidates:
            add(
                findings,
                "HIGH",
                "external_write_readback_not_detected",
                node=write.get("name"),
                destination=destination,
            )

        if not approval_nodes:
            add(
                findings,
                "HIGH",
                "external_write_approval_control_not_detected",
                node=write.get("name"),
                destination=destination,
            )
        elif edges:
            ancestors = reachable(write_id, reverse)
            if not any(str(node.get("id")) in ancestors for node in approval_nodes):
                add(
                    findings,
                    "HIGH",
                    "external_write_not_downstream_of_approval",
                    node=write.get("name"),
                    destination=destination,
                )

    payload_contract = ((manifest or {}).get("payload_contract") or {}).get("destination_fields") or {}
    approvals = (manifest or {}).get("approvals") or {}
    destination_ids = (manifest or {}).get("destinations") or {}
    approval_key = {"audience": "audience_write", "crm": "crm_write", "sequencer": "sequencer_write"}
    unknown_contract_destinations = {
        str(destination) for destination in payload_contract if destination not in approval_key
    }
    for destination, required in payload_contract.items():
        destination_kind = destination if destination in approval_key else None
        destination_writes = [node for node in writes if destination_for(node) == destination_kind]
        if destination_kind is None:
            named_writes = [
                node for node in destination_writes if mentions_destination(node, str(destination))
            ]
            if named_writes:
                destination_writes = named_writes
            elif len(destination_writes) == 1 and len(unknown_contract_destinations) == 1:
                add(
                    findings,
                    "MEDIUM",
                    "generic_destination_binding_inferred",
                    destination=destination,
                    node=destination_writes[0].get("name"),
                )
            else:
                add(
                    findings,
                    "HIGH",
                    "generic_destination_write_binding_ambiguous",
                    destination=destination,
                    candidate_nodes=[node.get("name") for node in destination_writes],
                )
                destination_writes = []
        if approvals.get(approval_key.get(destination, "external_write")) is True and not destination_writes:
            add(findings, "BLOCKER", "approved_destination_write_not_detected", destination=destination)
            continue
        for write in destination_writes:
            evidence_nodes = [write]
            if edges:
                ancestors = reachable(str(write.get("id")), reverse)
                evidence_nodes.extend(by_id[node_id] for node_id in ancestors if node_id in by_id)
            observed: set[str] = set()
            for node in evidence_nodes:
                observed.update(mapped_fields(node))
            if not observed:
                add(
                    findings,
                    "MEDIUM",
                    "payload_mapping_not_inspectable",
                    node=write.get("name"),
                    destination=destination,
                )
                continue
            missing = sorted(set(required or []) - observed)
            if missing:
                add(
                    findings,
                    "BLOCKER",
                    "required_payload_fields_not_mapped",
                    node=write.get("name"),
                    destination=destination,
                    missing=missing,
                    observed=sorted(observed),
                )
            destination_key = {
                "audience": "audience_id", "crm": "crm_campaign_id", "sequencer": "sequencer_campaign_id"
            }.get(destination)
            destination_id = destination_ids.get(destination_key) if destination_key else None
            if destination_id and destination_id not in " ".join(node_text(node) for node in evidence_nodes):
                add(
                    findings,
                    "MEDIUM",
                    "destination_binding_not_statically_verified",
                    node=write.get("name"),
                    destination=destination,
                    expected_id=destination_id,
                )

    idempotency_nodes = [node for node in nodes if "idempot" in node_text(node)]
    if writes and not idempotency_nodes:
        add(findings, "HIGH", "idempotency_control_not_detected")
    elif edges:
        for write in writes:
            ancestors = reachable(str(write.get("id")), reverse)
            if not any(str(node.get("id")) in ancestors for node in idempotency_nodes):
                add(
                    findings,
                    "HIGH",
                    "external_write_not_downstream_of_idempotency",
                    node=write.get("name"),
                )

    sequencer_writes = [node for node in writes if destination_for(node) == "sequencer"]
    if sequencer_writes:
        suppression_nodes = [
            node for node in nodes
            if any(term in node_text(node) for term in ("suppress", "unsubscribe", "blocklist", "bounce", "prior reply"))
        ]
        if not suppression_nodes:
            add(findings, "HIGH", "sequencer_write_without_suppression_control")
        elif edges:
            for write in sequencer_writes:
                ancestors = reachable(str(write.get("id")), reverse)
                if not any(str(node.get("id")) in ancestors for node in suppression_nodes):
                    add(
                        findings,
                        "HIGH",
                        "sequencer_write_not_downstream_of_suppression",
                        node=write.get("name"),
                    )

    fingerprint_rows = {
        str(row.get("id")): row
        for row in (function_fingerprints or {}).get("data") or []
        if isinstance(row, dict) and row.get("id")
    }
    expected_functions = {
        str(row.get("id")): str(row.get("sha256") or "")
        for row in (((manifest or {}).get("dependencies") or {}).get("custom_functions") or [])
        if isinstance(row, dict) and row.get("id")
    }
    for node in nodes:
        for function_id in custom_function_ids(node):
            observed = fingerprint_rows.get(function_id)
            if not observed:
                add(
                    findings,
                    "HIGH",
                    "custom_function_fingerprint_missing",
                    node=node.get("name"),
                    function_id=function_id,
                )
                continue
            observed_hash = str(observed.get("sha256") or "")
            expected_hash = expected_functions.get(function_id)
            if not expected_hash:
                add(
                    findings,
                    "HIGH",
                    "custom_function_not_bound_to_manifest",
                    node=node.get("name"),
                    function_id=function_id,
                    observed_sha256=observed_hash,
                )
            elif expected_hash != observed_hash:
                add(
                    findings,
                    "BLOCKER",
                    "custom_function_fingerprint_mismatch",
                    node=node.get("name"),
                    function_id=function_id,
                    expected_sha256=expected_hash,
                    observed_sha256=observed_hash,
                )
            if observed.get("paid_action_keys"):
                add(
                    findings,
                    "MEDIUM",
                    "custom_function_contains_paid_actions",
                    node=node.get("name"),
                    function_id=function_id,
                    action_keys=observed.get("paid_action_keys"),
                )

    if edges:
        declared_outcomes = (
            ((manifest or {}).get("workflow_contract") or {}).get("terminal_outcomes") or []
        )
        accepted_outcomes = OUTCOMES | {
            str(outcome).lower() for outcome in declared_outcomes if isinstance(outcome, str)
        }
        leaves = [node for node in nodes if node.get("nodeType") != "trigger" and not adjacency.get(str(node.get("id")))]
        for leaf in leaves:
            text = node_text(leaf)
            if not any(outcome in text for outcome in accepted_outcomes):
                add(
                    findings,
                    "HIGH",
                    "leaf_without_terminal_outcome",
                    node=leaf.get("name"),
                    node_id=leaf.get("id"),
                )

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "valid": blockers == 0 and high == 0,
        "write_nodes": [{"id": node.get("id"), "name": node.get("name"), "destination": destination_for(node)} for node in writes],
        "readback_nodes": [{"id": node.get("id"), "name": node.get("name"), "destination": destination_for(node)} for node in readbacks],
        "custom_function_nodes": [
            {"id": node.get("id"), "name": node.get("name"), "function_ids": custom_function_ids(node)}
            for node in nodes if custom_function_ids(node)
        ],
        "findings": findings,
        "summary": {"blockers": blockers, "high": high, "warnings": len(findings) - blockers - high},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit production controls in a Clay graph.")
    parser.add_argument("graph", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--function-fingerprints", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        graph = load_json(args.graph)
        manifest = load_json(args.manifest) if args.manifest else None
        fingerprints = load_json(args.function_fingerprints) if args.function_fingerprints else None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_graph_controls(graph, manifest, fingerprints)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
