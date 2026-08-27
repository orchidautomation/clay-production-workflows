#!/usr/bin/env python3
"""Collect a bounded, read-only evidence bundle for one Clay Workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKFLOW_RE = re.compile(r"^wf_[A-Za-z0-9]+$")
RUN_RE = re.compile(r"^wfr_[A-Za-z0-9]+$")
EVIDENCE_CONTRACT_VERSION = 2
SAFE_TRACE_FIELDS = {
    "workflow_outcome",
    "terminal_outcome",
    "activation_executed",
    "instantly_write_executed",
    "instantly_campaign_enrollment_executed",
    "instantly_campaign_membership_verified",
    "salesforce_readback_pass",
    "salesforce_readback_completed",
    "salesforce_readback_identity_match",
    "salesforce_readback_patch_match",
    "salesforce_campaign_members_verified_count",
    "salesforce_write_executed",
    "salesforce_contact_write_executed",
    "salesforce_account_write_executed",
    "salesforce_campaign_member_write_executed",
    "salesforce_primary_campaign_member_verified",
    "salesforce_secondary_campaign_member_verified",
    "audience_person_upsert_executed",
    "audience_activation_marker_write_executed",
    "audience_company_salesforce_id_sync_executed",
    "audience_person_salesforce_id_sync_executed",
    "campaign_queue_status",
    "external_send_executed",
    "write_executed",
    "mutation_executed",
    "readback_verified",
    "enrichment_verified",
    "routing_verified",
    "sync_verified",
}
SAFE_DECLARED_TRACE_FIELD = re.compile(
    r"^[a-z][a-z0-9_]*(?:_executed|_verified|_pass|_completed|_match)$"
)
SENSITIVE_FIELD_TERMS = (
    "email", "phone", "name", "address", "message", "body", "subject",
    "credential", "secret", "token", "key", "payload",
)


class CollectError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 5):
        super().__init__(message)
        self.exit_code = exit_code


def run_clay(args: list[str], timeout: int = 90) -> Any:
    allowed = {
        ("whoami",),
        ("workflows", "get"),
        ("workflows", "graph", "get"),
        ("workflows", "graph", "validate"),
        ("workflows", "diagram"),
        ("workflows", "snapshots", "list"),
        ("workflows", "snapshots", "get"),
        ("workflows", "triggers", "get"),
        ("workflows", "runs", "list"),
        ("workflows", "runs", "get"),
        ("audiences", "get"),
        ("audiences", "records", "search-count"),
        ("functions", "get"),
    }
    if not any(tuple(args[: len(prefix)]) == prefix for prefix in allowed):
        raise CollectError(f"Refusing non-read-only Clay command: {' '.join(args)}", 2)

    completed = subprocess.run(
        ["clay", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        auth = any(term in detail.lower() for term in ("login", "auth", "unauthorized", "forbidden"))
        raise CollectError(
            f"Clay command failed ({' '.join(args)}): {detail[:1200]}",
            4 if auth else 5,
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CollectError(
            f"Clay returned non-JSON for {' '.join(args)}: {completed.stdout[:300]!r}", 5
        ) from exc


def write_json(path: Path, value: Any) -> None:
    try:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise CollectError(f"Unable to write {path}: {exc}", 6) from exc


def clay_version() -> str | None:
    completed = subprocess.run(
        ["clay", "--version"], capture_output=True, text=True, timeout=30, check=False
    )
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr).strip() or None


def load_local_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectError(f"Unable to read local JSON from {path}: {exc}", 2) from exc


def graph_trigger_ids(graph: dict[str, Any]) -> list[str]:
    summary = graph.get("summary") or {}
    return [str(item["id"]) for item in summary.get("triggers", []) if item.get("id")]


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def scalar_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, dict):
        for key in ("count", "total", "result"):
            candidate = value.get(key)
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                return candidate
    return None


def identity_value_type(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text or " " in text:
        return None
    if len(text) in {15, 18} and text.isalnum() and not text.upper().startswith("00D"):
        return "crm_id"
    if text.startswith(("http://", "https://")) and "linkedin.com/" in text:
        return "linkedin_url"
    if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", text):
        return "domain"
    return None


def audience_summary(trigger: dict[str, Any], audience: dict[str, Any], count: Any) -> dict[str, Any]:
    identity_hashes: set[str] = set()
    identity_types: dict[str, int] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("operator") in {"Equal", "Contain"}:
                kind = identity_value_type(value.get("value"))
                if kind:
                    digest = hashlib.sha256(
                        f"{kind}:{str(value.get('value')).strip().lower()}".encode("utf-8")
                    ).hexdigest()
                    identity_hashes.add(digest)
                    identity_types[kind] = identity_types.get(kind, 0) + 1
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    filter_value = audience.get("filter") or {}
    visit(filter_value)
    return {
        "trigger_id": trigger.get("id"),
        "trigger_state": trigger.get("status") or trigger.get("state"),
        "segment_id": trigger.get("segmentId") or audience.get("id"),
        "name": audience.get("name"),
        "entity_type": audience.get("entityType"),
        "count": scalar_count(count),
        "filter_sha256": sha256_json(filter_value),
        "identity_value_hashes": sorted(identity_hashes),
        "identity_value_type_counts": dict(sorted(identity_types.items())),
        "raw_filter_values_written": False,
    }


def graph_function_ids(graph: dict[str, Any]) -> list[str]:
    ids: set[str] = set()
    for node in graph.get("nodes") or []:
        for tool in node.get("tools") or []:
            if not isinstance(tool, dict) or tool.get("toolType") != "clay_function":
                continue
            function_id = tool.get("tableId") or tool.get("id")
            if function_id:
                ids.add(str(function_id))
    return sorted(ids)


def recursive_values(value: Any, key_name: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == key_name and isinstance(item, str) and item:
                found.append(item)
            found.extend(recursive_values(item, key_name))
    elif isinstance(value, list):
        for item in value:
            found.extend(recursive_values(item, key_name))
    return found


def function_fingerprint(function_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    actions = sorted(set(recursive_values(definition, "actionKey")))
    write_terms = ("create", "update", "upsert", "add", "enroll", "send", "write")
    paid_terms = ("enrich", "claygent", "find-email", "waterfall", "cpj")
    serialized = json.dumps(definition, sort_keys=True, default=str).lower()
    behavior_markers = sorted(
        term for term in (
            "salesforce", "hubspot", "instantly", "audience", "enrich",
            "claygent", "create", "update", "upsert", "email",
        ) if term in serialized
    )
    write_actions = [key for key in actions if any(term in key.lower() for term in write_terms)]
    paid_actions = [key for key in actions if any(term in key.lower() for term in paid_terms)]
    if not write_actions:
        write_actions = [f"schema-marker:{term}" for term in behavior_markers if term in write_terms]
    if not paid_actions:
        paid_actions = [f"schema-marker:{term}" for term in behavior_markers if term in paid_terms]
    return {
        "id": function_id,
        "name": definition.get("name"),
        "sha256": sha256_json(definition),
        "action_keys": actions,
        "write_action_keys": write_actions,
        "paid_action_keys": paid_actions,
        "behavior_markers": behavior_markers,
        "tool_types": sorted(set(recursive_values(definition, "toolType"))),
        "raw_definition_written": False,
    }


def declared_trace_fields(manifest: dict[str, Any] | None) -> set[str]:
    declared = ((manifest or {}).get("workflow_contract") or {}).get(
        "monotonic_evidence_fields"
    ) or []
    return {
        field
        for field in declared
        if isinstance(field, str)
        and SAFE_DECLARED_TRACE_FIELD.fullmatch(field)
        and not any(term in field.lower() for term in SENSITIVE_FIELD_TERMS)
    }


def safe_trace_fields(value: Any, extra_fields: set[str] | None = None) -> dict[str, Any]:
    allowed = SAFE_TRACE_FIELDS | (extra_fields or set())
    found: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in allowed and (
                isinstance(item, (str, int, float, bool)) or item is None
            ):
                found[key] = item
        # Only unwrap provider/result containers. Do not recurse through
        # _branchOutputs or inherited context, which can contain stale state.
        for key in ("result", "structuredOutput", "structuredOutputs"):
            found.update(safe_trace_fields(value.get(key), extra_fields))
    elif isinstance(value, list):
        for item in value:
            found.update(safe_trace_fields(item, extra_fields))
    return found


def compact_run_trace(run: dict[str, Any], extra_fields: set[str] | None = None) -> dict[str, Any]:
    nodes = []
    for node in run.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        produced = (
            node.get("outputs")
            if node.get("outputs") is not None
            else node.get("output")
            if node.get("output") is not None
            else node.get("result")
        )
        fields = safe_trace_fields(produced, extra_fields)
        if fields:
            nodes.append(
                {
                    "nodeId": node.get("nodeId") or node.get("id"),
                    "name": node.get("name") or node.get("nodeName"),
                    "status": node.get("status"),
                    "fields": fields,
                }
            )
    return {"runId": run.get("runId"), "status": run.get("status"), "nodes": nodes}


def compact_failed_run(run: dict[str, Any]) -> dict[str, Any]:
    failed = []
    for node in run.get("nodes") or []:
        if node.get("status") == "failed":
            failed.append(
                {
                    "nodeId": node.get("nodeId") or node.get("id"),
                    "name": node.get("name") or node.get("nodeName"),
                    "errors": node.get("errors") or [],
                    "waitingReason": node.get("waitingReason"),
                }
            )
    return {
        "runId": run.get("runId"),
        "status": run.get("status"),
        "progress": run.get("progress"),
        "failed_nodes": failed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only Clay Workflow evidence into JSON files."
    )
    parser.add_argument("workflow_id", help="Clay Workflow ID, for example wf_abc123")
    parser.add_argument("--output", required=True, type=Path, help="Evidence output directory")
    parser.add_argument("--run-limit", type=int, default=50, help="Maximum run metadata rows (default: 50)")
    parser.add_argument(
        "--failed-runs-limit",
        type=int,
        default=5,
        help="Maximum failed runs to inspect without verbose inputs/outputs (default: 5)",
    )
    parser.add_argument("--manifest", type=Path, help="Optional local workflow contract to copy into the evidence bundle")
    parser.add_argument("--receipts", type=Path, help="Optional local reconciliation receipts to copy into the evidence bundle")
    parser.add_argument(
        "--trace-run",
        action="append",
        default=[],
        help="Optional run ID to collect as a redacted outcome trace; repeat for multiple runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not WORKFLOW_RE.fullmatch(args.workflow_id):
        print("Error: workflow_id must match ^wf_[A-Za-z0-9]+$", file=sys.stderr)
        return 2
    if args.run_limit < 0 or args.failed_runs_limit < 0:
        print("Error: run limits must be non-negative", file=sys.stderr)
        return 2
    if any(not RUN_RE.fullmatch(run_id) for run_id in args.trace_run):
        print("Error: every --trace-run value must match ^wfr_[A-Za-z0-9]+$", file=sys.stderr)
        return 2
    if shutil.which("clay") is None:
        print("Error: clay CLI is not available. Install or enable the Clay plugin.", file=sys.stderr)
        return 3

    try:
        local_manifest = load_local_json(args.manifest) if args.manifest else None
        extra_trace_fields = declared_trace_fields(local_manifest)
        args.output.mkdir(parents=True, exist_ok=True)
        identity = run_clay(["whoami"])
        workflow = run_clay(["workflows", "get", args.workflow_id])
        graph = run_clay(["workflows", "graph", "get", args.workflow_id, "--mode", "full"])
        validation = run_clay(["workflows", "graph", "validate", args.workflow_id])
        diagram = run_clay(["workflows", "diagram", args.workflow_id])
        snapshots = run_clay(["workflows", "snapshots", "list", args.workflow_id])
        runs = run_clay(["workflows", "runs", "list", args.workflow_id])

        run_rows = list(runs.get("data") or [])[: args.run_limit]
        runs = {**runs, "data": run_rows}
        triggers = [
            run_clay(["workflows", "triggers", "get", trigger_id])
            for trigger_id in graph_trigger_ids(graph)
        ]

        snapshot_rows = list(snapshots.get("data") or [])
        current_snapshot = {}
        if snapshot_rows and snapshot_rows[0].get("id"):
            current_snapshot = run_clay(
                ["workflows", "snapshots", "get", args.workflow_id, str(snapshot_rows[0]["id"])]
            )

        audience_segments = []
        seen_segments: set[str] = set()
        for trigger in triggers:
            segment_id = str(trigger.get("segmentId") or "")
            if not segment_id or segment_id in seen_segments:
                continue
            seen_segments.add(segment_id)
            audience = run_clay(["audiences", "get", segment_id])
            entity_type = str(audience.get("entityType") or "")
            count = run_clay(
                [
                    "audiences", "records", "search-count",
                    "--entity-type", entity_type,
                    "--audience-id", segment_id,
                ]
            ) if entity_type else None
            audience_segments.append(audience_summary(trigger, audience, count))

        function_fingerprints = [
            function_fingerprint(function_id, run_clay(["functions", "get", function_id]))
            for function_id in graph_function_ids(graph)
        ]

        run_traces = [
            compact_run_trace(
                run_clay(["workflows", "runs", "get", args.workflow_id, run_id, "--verbose"]),
                extra_trace_fields,
            )
            for run_id in args.trace_run
        ]

        failed_runs = []
        for row in (item for item in run_rows if item.get("status") == "failed"):
            if len(failed_runs) >= args.failed_runs_limit:
                break
            run_id = row.get("runId")
            if not run_id:
                continue
            detail = run_clay(
                ["workflows", "runs", "get", args.workflow_id, str(run_id), "--nodes"]
            )
            failed_runs.append(compact_failed_run(detail))

        bundle = {
            "collector-metadata.json": {
                "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
                "clay_cli_version": clay_version(),
                "redaction_receipt": {
                    "audience_filter_values_hashed": True,
                    "custom_function_definitions_hashed": True,
                    "run_traces_allowlisted": True,
                    "raw_sensitive_values_written": False,
                },
            },
            "identity.json": identity,
            "workflow.json": workflow,
            "graph.json": graph,
            "validation.json": validation,
            "diagram.json": diagram,
            "snapshots.json": snapshots,
            "current-snapshot.json": current_snapshot,
            "triggers.json": {"data": triggers},
            "audience-segments.json": {"data": audience_segments},
            "function-fingerprints.json": {"data": function_fingerprints},
            "runs.json": runs,
            "failed-runs.json": {"data": failed_runs},
            "run-traces.json": {"data": run_traces},
        }
        if local_manifest is not None:
            bundle["manifest.json"] = local_manifest
        if args.receipts:
            bundle["receipts.json"] = load_local_json(args.receipts)
        for filename, payload in bundle.items():
            write_json(args.output / filename, payload)

        statuses: dict[str, int] = {}
        for row in run_rows:
            status = str(row.get("status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
        print(
            json.dumps(
                {
                    "workflow_id": args.workflow_id,
                    "workflow_name": workflow.get("name"),
                    "workspace_id": (identity.get("workspace") or {}).get("id"),
                    "output": str(args.output),
                    "node_count": (graph.get("summary") or {}).get("nodeCount"),
                    "trigger_count": len(triggers),
                    "audience_segment_count": len(audience_segments),
                    "custom_function_count": len(function_fingerprints),
                    "trace_run_count": len(run_traces),
                    "run_count": len(run_rows),
                    "run_status_counts": statuses,
                    "failed_runs_inspected": len(failed_runs),
                },
                sort_keys=True,
            )
        )
        return 0
    except CollectError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except subprocess.TimeoutExpired as exc:
        print(f"Error: Clay command timed out: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"Error: filesystem failure: {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
