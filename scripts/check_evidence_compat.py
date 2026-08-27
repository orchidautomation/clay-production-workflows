#!/usr/bin/env python3
"""Check that a collected evidence directory matches the parser contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CONTRACT_VERSION = 2
SUPPORTED_CONTRACT_VERSIONS = {1, 2}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read JSON from {path}: {exc}") from exc


def analyze_evidence(directory: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    required = {
        "identity.json": dict,
        "workflow.json": dict,
        "graph.json": dict,
        "validation.json": dict,
        "snapshots.json": dict,
        "triggers.json": dict,
        "runs.json": dict,
        "failed-runs.json": dict,
    }
    loaded: dict[str, Any] = {}
    for filename, expected_type in required.items():
        path = directory / filename
        if not path.exists():
            findings.append({"severity": "BLOCKER", "code": "evidence_file_missing", "file": filename})
            continue
        try:
            value = load_json(path)
        except ValueError as exc:
            findings.append({"severity": "BLOCKER", "code": "evidence_json_invalid", "file": filename, "detail": str(exc)})
            continue
        loaded[filename] = value
        if not isinstance(value, expected_type):
            findings.append({"severity": "BLOCKER", "code": "evidence_top_level_shape_changed", "file": filename})

    workflow = loaded.get("workflow.json") or {}
    if not isinstance(workflow.get("id"), str) or not workflow.get("id", "").startswith("wf_"):
        findings.append({"severity": "BLOCKER", "code": "workflow_id_shape_changed"})
    graph = loaded.get("graph.json") or {}
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("summary"), dict):
        findings.append({"severity": "BLOCKER", "code": "graph_shape_changed"})
    validation = loaded.get("validation.json") or {}
    if not isinstance(validation.get("valid"), bool):
        findings.append({"severity": "BLOCKER", "code": "validation_shape_changed", "field": "valid"})
    for filename in ("snapshots.json", "triggers.json", "runs.json", "failed-runs.json"):
        value = loaded.get(filename) or {}
        if not isinstance(value.get("data"), list):
            findings.append({"severity": "BLOCKER", "code": "collection_shape_changed", "file": filename, "field": "data"})
    identity = loaded.get("identity.json") or {}
    if not isinstance(identity.get("workspace"), dict):
        findings.append({"severity": "HIGH", "code": "workspace_identity_shape_changed"})

    metadata_path = directory / "collector-metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            candidate = load_json(metadata_path)
            if isinstance(candidate, dict):
                metadata = candidate
            else:
                findings.append({"severity": "BLOCKER", "code": "collector_metadata_shape_changed"})
        except ValueError as exc:
            findings.append({"severity": "BLOCKER", "code": "collector_metadata_invalid", "detail": str(exc)})
    observed_version = metadata.get("evidence_contract_version") if metadata else None
    if not metadata:
        findings.append({"severity": "MEDIUM", "code": "collector_metadata_missing"})
    elif observed_version not in SUPPORTED_CONTRACT_VERSIONS:
        findings.append({
            "severity": "BLOCKER",
            "code": "evidence_contract_version_unsupported",
            "supported": sorted(SUPPORTED_CONTRACT_VERSIONS),
            "observed": observed_version,
        })
    elif observed_version == 1:
        findings.append({
            "severity": "MEDIUM",
            "code": "legacy_evidence_contract_lacks_runtime_semantics",
            "missing_capabilities": [
                "raw_snapshot_semantics",
                "redacted_trigger_overlap",
                "custom_function_fingerprints",
                "run_outcome_traces",
            ],
        })
    elif observed_version == 2:
        advanced = {
            "current-snapshot.json": dict,
            "audience-segments.json": dict,
            "function-fingerprints.json": dict,
            "run-traces.json": dict,
        }
        for filename, expected_type in advanced.items():
            path = directory / filename
            if not path.exists():
                findings.append({"severity": "BLOCKER", "code": "evidence_file_missing", "file": filename})
                continue
            try:
                value = load_json(path)
            except ValueError as exc:
                findings.append({"severity": "BLOCKER", "code": "evidence_json_invalid", "file": filename, "detail": str(exc)})
                continue
            if not isinstance(value, expected_type):
                findings.append({"severity": "BLOCKER", "code": "evidence_top_level_shape_changed", "file": filename})
            if (
                filename != "current-snapshot.json"
                and isinstance(value, dict)
                and not isinstance(value.get("data"), list)
            ):
                findings.append({"severity": "BLOCKER", "code": "collection_shape_changed", "file": filename, "field": "data"})
            if filename == "current-snapshot.json" and isinstance(value, dict) and (
                not isinstance(value.get("nodes"), list)
                or not isinstance(value.get("edges"), list)
            ):
                findings.append({
                    "severity": "BLOCKER",
                    "code": "current_snapshot_shape_changed",
                    "file": filename,
                })
        redaction = metadata.get("redaction_receipt") or {}
        if redaction.get("raw_sensitive_values_written") is not False:
            findings.append({"severity": "HIGH", "code": "evidence_redaction_receipt_missing_or_unsafe"})

    blockers = sum(item["severity"] == "BLOCKER" for item in findings)
    high = sum(item["severity"] == "HIGH" for item in findings)
    return {
        "compatible": blockers == 0 and high == 0,
        "evidence_contract_version": observed_version,
        "latest_evidence_contract_version": CONTRACT_VERSION,
        "clay_cli_version": metadata.get("clay_cli_version"),
        "findings": findings,
        "summary": {"blockers": blockers, "high": high, "warnings": len(findings) - blockers - high},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check a Clay evidence directory for parser compatibility.")
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = analyze_evidence(args.evidence_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 10 if args.strict and not result["compatible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
