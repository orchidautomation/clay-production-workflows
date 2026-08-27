#!/usr/bin/env python3
"""Validate raw Clay snapshot transitions, entrypoints, and context contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


TRANSITION_RE = re.compile(
    r"context\.transition_to\(\s*([\"'])(.*?)\1\s*,\s*([\"'])(.*?)\3\s*\)"
)
CONTEXT_KEY_RE = re.compile(r"context\.get\(\s*[\"']([A-Za-z][A-Za-z0-9_]*)[\"']")
FIELD_TOKEN_RE = re.compile(r"[\"']([A-Za-z][A-Za-z0-9_]*_ids?)[\"']")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def add(findings: list[dict[str, Any]], severity: str, code: str, **detail: Any) -> None:
    findings.append({"severity": severity, "code": code, **detail})


def node_code(node: dict[str, Any]) -> str:
    version = node.get("currentScriptVersion") or {}
    return str(version.get("code") or node.get("code") or "")


def transition_calls(node: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"target_name": match.group(2), "transition_id": match.group(4)}
        for match in TRANSITION_RE.finditer(node_code(node))
    ]


def transition_config(node: dict[str, Any]) -> list[dict[str, Any]]:
    conditional = ((node.get("nodeConfig") or {}).get("conditionalConfig") or {})
    rows = conditional.get("codeTransitions") or []
    return [row for row in rows if isinstance(row, dict)]


def edge_handle(edge: dict[str, Any]) -> str | None:
    raw = str(((edge.get("metadata") or {}).get("conditionalSourceHandle") or ""))
    prefix = "conditional-code-"
    return raw[len(prefix):] if raw.startswith(prefix) else (raw or None)


def context_keys(node: dict[str, Any]) -> set[str]:
    return set(CONTEXT_KEY_RE.findall(node_code(node)))


def input_ref_keys(node: dict[str, Any]) -> set[str]:
    refs = (node.get("nodeConfig") or {}).get("inputRefs") or {}
    return set(str(key) for key in refs) if isinstance(refs, dict) else set()


def identifier_tokens(node: dict[str, Any]) -> set[str]:
    tokens = set(FIELD_TOKEN_RE.findall(node_code(node)))
    for schema_name in ("inputSchema", "outputSchema"):
        schema = (node.get("currentScriptVersion") or {}).get(schema_name)
        if not isinstance(schema, dict):
            schema = (node.get("nodeConfig") or {}).get(schema_name) or {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if isinstance(properties, dict):
            tokens.update(str(key) for key in properties if str(key).endswith(("_id", "_ids")))
    return tokens


def analyze_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in snapshot.get("nodes") or [] if isinstance(node, dict)]
    edges = [edge for edge in snapshot.get("edges") or [] if isinstance(edge, dict)]
    by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    by_name = {str(node.get("name")): node for node in nodes if node.get("name")}
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("sourceNodeId") or "")
        target = str(edge.get("targetNodeId") or "")
        if source and target:
            outgoing[source].append(edge)
            incoming[target].append(edge)

    findings: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        node_name = node.get("name")
        if node.get("isInitial") is True:
            non_trigger = [
                edge for edge in incoming.get(node_id, [])
                if str((by_id.get(str(edge.get("sourceNodeId"))) or {}).get("nodeType")) != "trigger"
            ]
            if non_trigger:
                add(
                    findings,
                    "BLOCKER",
                    "initial_node_has_non_trigger_incoming_edge",
                    node=node_name,
                    node_id=node_id,
                    source_nodes=[edge.get("sourceNodeId") for edge in non_trigger],
                )
        if node.get("isTerminal") is True and outgoing.get(node_id):
            add(
                findings,
                "BLOCKER",
                "terminal_node_has_outgoing_edges",
                node=node_name,
                node_id=node_id,
            )

        if str(node.get("nodeType") or "") == "conditional":
            calls = transition_calls(node)
            configured = transition_config(node)
            configured_by_id = {
                str(row.get("id")): row for row in configured if row.get("id")
            }
            handled_edges = {
                edge_handle(edge): edge for edge in outgoing.get(node_id, []) if edge_handle(edge)
            }
            for call in calls:
                transition_id = call["transition_id"]
                target = by_name.get(call["target_name"])
                row = configured_by_id.get(transition_id)
                if row is None:
                    add(
                        findings,
                        "BLOCKER",
                        "conditional_transition_not_registered",
                        node=node_name,
                        node_id=node_id,
                        transition_id=transition_id,
                        target_name=call["target_name"],
                    )
                if target is None:
                    add(
                        findings,
                        "BLOCKER",
                        "conditional_transition_target_missing",
                        node=node_name,
                        transition_id=transition_id,
                        target_name=call["target_name"],
                    )
                    continue
                target_id = str(target.get("id"))
                if row is not None and row.get("targetNodeId") not in {None, target_id}:
                    add(
                        findings,
                        "BLOCKER",
                        "conditional_transition_target_mismatch",
                        node=node_name,
                        transition_id=transition_id,
                        configured_target=row.get("targetNodeId"),
                        called_target=target_id,
                    )
                edge = handled_edges.get(transition_id)
                if edge is None:
                    target_edges = [
                        candidate for candidate in outgoing.get(node_id, [])
                        if str(candidate.get("targetNodeId")) == target_id
                    ]
                    if target_edges:
                        add(
                            findings,
                            "MEDIUM",
                            "conditional_edge_handle_drift",
                            node=node_name,
                            transition_id=transition_id,
                            observed_handles=[edge_handle(candidate) for candidate in target_edges],
                            target_name=call["target_name"],
                        )
                    else:
                        add(
                            findings,
                            "BLOCKER",
                            "conditional_transition_edge_missing",
                            node=node_name,
                            transition_id=transition_id,
                            target_name=call["target_name"],
                        )
                elif str(edge.get("targetNodeId")) != target_id:
                    add(
                        findings,
                        "BLOCKER",
                        "conditional_edge_target_mismatch",
                        node=node_name,
                        transition_id=transition_id,
                        edge_target=edge.get("targetNodeId"),
                        called_target=target_id,
                    )
            for handle, edge in handled_edges.items():
                if handle not in configured_by_id:
                    add(
                        findings,
                        "MEDIUM",
                        "conditional_edge_handle_not_registered",
                        node=node_name,
                        transition_id=handle,
                        target_node_id=edge.get("targetNodeId"),
                    )

        required_context = {
            key for key in context_keys(node)
            if key == "prior_context_json" or key.endswith("_context_json")
        }
        missing_context = sorted(required_context - input_ref_keys(node))
        tool_predecessors = [
            by_id.get(str(edge.get("sourceNodeId"))) for edge in incoming.get(node_id, [])
        ]
        tool_predecessors = [
            predecessor for predecessor in tool_predecessors
            if predecessor and predecessor.get("nodeType") == "tool"
        ]
        if missing_context and tool_predecessors:
            add(
                findings,
                "BLOCKER",
                "context_snapshot_not_pinned_after_tool",
                node=node_name,
                node_id=node_id,
                missing_input_refs=missing_context,
                tool_predecessors=[item.get("name") for item in tool_predecessors],
            )

    token_nodes: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        for token in identifier_tokens(node):
            token_nodes[token].append(str(node.get("name") or node.get("id")))
    for singular, names in sorted(token_nodes.items()):
        if not singular.endswith("_id") or not any(
            marker in singular for marker in ("member_id", "membership_id")
        ):
            continue
        plural = singular + "s"
        if plural in token_nodes:
            add(
                findings,
                "MEDIUM",
                "singular_plural_identifier_contract_drift",
                singular=singular,
                plural=plural,
                singular_nodes=sorted(set(names)),
                plural_nodes=sorted(set(token_nodes[plural])),
            )

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "valid": blockers == 0 and high == 0,
        "snapshot_id": snapshot.get("id"),
        "snapshot_hash": snapshot.get("hash"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "findings": findings,
        "summary": {
            "blockers": blockers,
            "high": high,
            "warnings": len(findings) - blockers - high,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit raw Clay snapshot semantics.")
    parser.add_argument("snapshot", type=Path, help="current-snapshot.json from the evidence collector")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshot = load_json(args.snapshot)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    result = analyze_snapshot(snapshot)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["valid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
