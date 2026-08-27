import json
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_workflow import audit
from analyze_run_traces import analyze_run_traces
from classify_workflow import classify_workflow
from collect_workflow_evidence import (
    audience_summary, compact_run_trace, declared_trace_fields, function_fingerprint,
)
from explain_workflow import build_model, render_markdown
from summarize_runs import classify_error, summarize
from validate_contract import analyze
from check_evidence_compat import analyze_evidence
from validate_graph_controls import analyze_graph_controls, is_readback, is_write
from validate_manifest import analyze_manifest, configuration_hash
from validate_reconciliation import analyze_reconciliation
from validate_snapshot_semantics import analyze_snapshot
from validate_trigger_safety import analyze_trigger_safety


def fixture(name):
    return json.loads((ROOT / "evals" / "fixtures" / name).read_text(encoding="utf-8"))


class PackageTests(unittest.TestCase):
    def test_eval_file_references_exist(self):
        evals = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        missing = [
            relative
            for case in evals["evals"]
            for relative in case.get("files", [])
            if not (ROOT / "evals" / relative).is_file()
        ]
        self.assertEqual(missing, [])

    def test_trigger_queries_cover_positive_and_negative_train_validation_sets(self):
        queries = json.loads(
            (ROOT / "evals" / "trigger-queries.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len({row["query"] for row in queries}), len(queries))
        coverage = {
            (row.get("split"), row.get("should_trigger")) for row in queries
        }
        self.assertEqual(
            coverage,
            {
                ("train", True), ("train", False),
                ("validation", True), ("validation", False),
            },
        )


class ContractTests(unittest.TestCase):
    def test_valid_five_email_contract(self):
        result = analyze(fixture("valid-production-workflow.json"), {"valid": True})
        self.assertTrue(result["valid"])
        self.assertEqual(result["canonical_sequence_length"], 5)
        self.assertEqual(result["summary"]["blockers"], 0)

    def test_detects_two_vs_five_mismatch(self):
        result = analyze(fixture("sequence-contract-mismatch.json"), {"valid": True})
        self.assertFalse(result["valid"])
        self.assertEqual(result["canonical_sequence_length"], 5)
        self.assertGreaterEqual(result["summary"]["blockers"], 1)


class ManifestTests(unittest.TestCase):
    def test_valid_draft_manifest(self):
        result = analyze_manifest(fixture("valid-campaign-manifest.json"))
        self.assertTrue(result["valid"])
        self.assertTrue(result["configuration_hash"].startswith("sha256:"))

    def test_configuration_change_invalidates_approval(self):
        manifest = fixture("valid-campaign-manifest.json")
        manifest["approvals"].update({
            "paid_work": True,
            "config_hash": configuration_hash(manifest),
            "reference": "APPROVAL-1",
            "approver": "growth-lead",
            "approved_at": "2025-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        self.assertTrue(analyze_manifest(manifest)["valid"])
        manifest["budgets"]["worst_case_credits_per_record"] = 3
        result = analyze_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertIn("approval_config_hash_mismatch", {item["code"] for item in result["findings"]})

    def test_enrichment_profile_does_not_require_campaign_or_copy_sections(self):
        result = analyze_manifest(fixture("valid-enrichment-manifest.json"))
        self.assertTrue(result["valid"], result["findings"])
        self.assertEqual(result["profile"], "enrichment_sync")
        self.assertNotIn("copy_sequence", result["capabilities"])

    def test_capability_implications_cannot_hide_external_mutation_controls(self):
        manifest = fixture("valid-enrichment-manifest.json")
        manifest["workflow_contract"]["capabilities"] = ["crm_sync"]
        result = analyze_manifest(manifest)
        self.assertIn("external_mutation", result["capabilities"])
        missing = {
            item.get("section")
            for item in result["findings"]
            if item["code"] == "manifest_section_missing"
        }
        self.assertIn("payload_contract", missing)
        self.assertIn("reconciliation", missing)

    def test_sensitive_monotonic_evidence_field_is_rejected(self):
        manifest = fixture("valid-enrichment-manifest.json")
        manifest["workflow_contract"]["monotonic_evidence_fields"] = ["email_verified"]
        result = analyze_manifest(manifest)
        self.assertIn(
            "monotonic_evidence_fields_unsafe",
            {item["code"] for item in result["findings"]},
        )

    def test_template_placeholders_block_instantiation(self):
        template = json.loads((ROOT / "assets" / "campaign-manifest.template.json").read_text())
        result = analyze_manifest(template)
        self.assertFalse(result["valid"])
        self.assertIn("manifest_placeholders_present", {item["code"] for item in result["findings"]})

    def test_live_write_requires_owners_kill_switch_and_retention(self):
        manifest = fixture("valid-campaign-manifest.json")
        manifest["ownership"]["incident_owner"] = ""
        manifest["operations"]["kill_switch"]["pause_method"] = ""
        manifest["data_handling"]["evidence_retention_days"] = -1
        manifest["approvals"].update({
            "sequencer_write": True,
            "config_hash": configuration_hash(manifest),
            "reference": "APPROVAL-OPS-1",
            "approver": "growth-lead",
            "approved_at": "2025-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        result = analyze_manifest(manifest)
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("production_owners_missing", codes)
        self.assertIn("kill_switch_incomplete", codes)
        self.assertIn("evidence_retention_invalid", codes)

    def test_live_ready_requires_configured_destination_and_activation_approvals(self):
        manifest = copy.deepcopy(fixture("valid-campaign-manifest.json"))
        manifest["campaign"].update({"state": "LIVE_READY", "ready": True})
        manifest["workflow_contract"].update({"state": "LIVE_READY", "ready": True})
        result = analyze_manifest(manifest)
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("live_ready_destination_approvals_missing", codes)
        self.assertIn("live_ready_outbound_activation_approval_missing", codes)


class ApplicabilityTests(unittest.TestCase):
    def test_enrichment_routes_only_relevant_profile_checks(self):
        result = classify_workflow(
            fixture("enrichment-only-workflow.json"),
            fixture("valid-enrichment-manifest.json"),
        )
        self.assertTrue(result["valid"], result["findings"])
        self.assertEqual(result["primary_profile"], "enrichment_sync")
        self.assertIn("credit_budget", result["applicable_checks"])
        self.assertIn("sequence_contract", result["not_applicable_checks"])
        self.assertIn("trigger_overlap", result["not_applicable_checks"])

    def test_inbound_crm_graph_composes_routing_and_sync_profiles(self):
        result = classify_workflow(fixture("inbound-routing-workflow.json"))
        self.assertTrue(result["valid"], result["findings"])
        self.assertIn("inbound_routing", result["profiles"])
        self.assertIn("crm_sync", result["profiles"])
        self.assertIn("assignment_contract", result["applicable_checks"])
        self.assertIn("destination_reconciliation", result["applicable_checks"])
        self.assertIn("sequence_contract", result["not_applicable_checks"])

    def test_generic_condition_does_not_imply_business_routing(self):
        graph = {
            "nodes": [{
                "id": "check",
                "name": "Required Fields Present?",
                "nodeType": "conditional",
                "code": "return bool(domain)",
            }]
        }
        result = classify_workflow(graph)
        self.assertNotIn("routing", result["capabilities"]["detected"])
        self.assertNotIn("inbound_routing", result["profiles"])

    def test_detected_capability_adds_checks_when_manifest_omits_it(self):
        manifest = fixture("valid-enrichment-manifest.json")
        result = classify_workflow(fixture("valid-governed-graph.json"), manifest)
        self.assertIn("copy_sequence", result["capabilities"]["effective"])
        self.assertIn("sequence_contract", result["applicable_checks"])
        self.assertIn(
            "detected_capability_not_declared",
            {item["code"] for item in result["findings"]},
        )


class GraphControlTests(unittest.TestCase):
    def test_valid_graph_has_payload_suppression_and_readback(self):
        result = analyze_graph_controls(
            fixture("valid-governed-graph.json"), fixture("valid-campaign-manifest.json")
        )
        self.assertTrue(result["valid"], result["findings"])

    def test_missing_payload_fields_readback_and_terminal_block(self):
        result = analyze_graph_controls(
            fixture("unsafe-governed-graph.json"), fixture("valid-campaign-manifest.json")
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("required_payload_fields_not_mapped", codes)
        self.assertIn("external_write_without_downstream_readback", codes)
        self.assertIn("leaf_without_terminal_outcome", codes)
        self.assertIn("idempotency_control_not_detected", codes)

    def test_node_classification_uses_own_executable_behavior(self):
        router = {
            "id": "router",
            "name": "Stage Person Available?",
            "description": "Routes to [EXTERNAL MUTATION] Stage Person",
            "nodeType": "conditional",
            "code": "context.transition_to('[EXTERNAL MUTATION] Stage Person', 'yes')",
        }
        function = {
            "id": "function",
            "name": "[EXTERNAL MUTATION FUNCTION] Create/Update Contact",
            "nodeType": "tool",
            "tools": [{"toolType": "clay_function", "tableId": "t_fixture"}],
        }
        response_parser = {
            "id": "parser",
            "name": "Audience Reconciliation Receipt",
            "nodeType": "code",
            "code": "return {'verified': bool(context.get('result'))}",
        }
        self.assertFalse(is_write(router))
        self.assertTrue(is_write(function))
        self.assertFalse(is_readback(response_parser))

        paid_read_function = {
            "id": "paid_read",
            "name": "[PAID FUNCTION] Company Qualification",
            "description": "Uses Salesforce lookup and enrichment. No Salesforce write.",
            "nodeType": "tool",
            "tools": [{"toolType": "clay_function", "tableId": "t_read_fixture"}],
        }
        self.assertFalse(is_write(paid_read_function))

    def test_circular_approval_binding_is_a_blocker(self):
        graph = {
            "summary": {"nodeCount": 1, "edges": []},
            "nodes": [{
                "id": "preflight",
                "name": "Campaign Preflight",
                "nodeType": "code",
                "code": "config_hash = 'current'\napprovals = {}\napprovals['approved_config_hash'] = config_hash",
            }],
        }
        result = analyze_graph_controls(graph)
        self.assertIn(
            "approval_evidence_derived_from_current_configuration",
            {item["code"] for item in result["findings"]},
        )

        graph["nodes"][0]["code"] = "current_config_hash = 'current'\napproved_config_hash = current_config_hash"
        direct_result = analyze_graph_controls(graph)
        self.assertIn(
            "approval_evidence_derived_from_current_configuration",
            {item["code"] for item in direct_result["findings"]},
        )

    def test_custom_function_fingerprint_must_match_manifest(self):
        graph = {
            "summary": {"nodeCount": 1, "edges": []},
            "nodes": [{
                "id": "function",
                "name": "Qualification Function",
                "description": "Read-only qualification helper.",
                "nodeType": "tool",
                "tools": [{"toolType": "clay_function", "tableId": "t_fixture"}],
            }],
        }
        manifest = copy.deepcopy(fixture("valid-campaign-manifest.json"))
        manifest["dependencies"]["custom_functions"] = [{
            "id": "t_fixture",
            "sha256": "sha256:" + "a" * 64,
        }]
        fingerprints = {"data": [{
            "id": "t_fixture",
            "sha256": "sha256:" + "b" * 64,
            "paid_action_keys": [],
        }]}
        result = analyze_graph_controls(graph, manifest, fingerprints)
        self.assertIn(
            "custom_function_fingerprint_mismatch",
            {item["code"] for item in result["findings"]},
        )

    def test_generic_lookup_does_not_satisfy_crm_readback(self):
        graph = {
            "summary": {"nodeCount": 2, "edges": [{"source": "write", "target": "lookup"}]},
            "nodes": [
                {
                    "id": "write",
                    "name": "[EXTERNAL MUTATION] Salesforce Contact Update",
                    "nodeType": "tool",
                    "tools": [{"actionKey": "salesforce-update-record"}],
                },
                {
                    "id": "lookup",
                    "name": "[READ ONLY] Generic Lookup",
                    "nodeType": "tool",
                    "tools": [{"actionKey": "generic-lookup"}],
                },
            ],
        }
        result = analyze_graph_controls(graph)
        self.assertIn(
            "external_write_without_downstream_readback",
            {item["code"] for item in result["findings"]},
        )


class SnapshotSemanticTests(unittest.TestCase):
    def test_valid_transition_registry_and_entrypoint(self):
        result = analyze_snapshot(fixture("valid-runtime-snapshot.json"))
        self.assertTrue(result["valid"], result["findings"])

    def test_detects_unregistered_transition_initial_incoming_and_context_loss(self):
        result = analyze_snapshot(fixture("unsafe-runtime-snapshot.json"))
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("conditional_transition_not_registered", codes)
        self.assertIn("initial_node_has_non_trigger_incoming_edge", codes)
        self.assertIn("context_snapshot_not_pinned_after_tool", codes)
        self.assertIn("singular_plural_identifier_contract_drift", codes)


class TriggerSafetyTests(unittest.TestCase):
    def test_overlapping_unknown_trigger_generations_block_readiness(self):
        payload = fixture("overlapping-trigger-segments.json")
        result = analyze_trigger_safety(payload["triggers"], payload["audience_segments"])
        self.assertFalse(result["valid"])
        finding = next(item for item in result["findings"] if item["code"] == "trigger_cohorts_overlap")
        self.assertEqual(finding["overlapping_identity_count"], 1)
        self.assertFalse(finding["activation_state_proven"])

    def test_distinct_audience_filters_without_overlap_proof_are_unresolved(self):
        result = analyze_trigger_safety(
            {"data": [
                {"id": "trigger_a", "segmentId": "segment_a", "status": "active"},
                {"id": "trigger_b", "segmentId": "segment_b", "status": "active"},
            ]},
            {"data": [
                {"segment_id": "segment_a", "entity_type": "companies", "filter_sha256": "sha256:a"},
                {"segment_id": "segment_b", "entity_type": "companies", "filter_sha256": "sha256:b"},
            ]},
        )
        self.assertFalse(result["valid"])
        self.assertIn(
            "trigger_cohort_overlap_unresolved",
            {item["code"] for item in result["findings"]},
        )


class RunTraceTests(unittest.TestCase):
    def test_detects_activation_downgrade_and_contradictory_terminal(self):
        result = analyze_run_traces(fixture("contradictory-run-trace.json"))
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("proven_side_effect_downgraded_later_in_run", codes)
        self.assertIn("activated_outcome_reclassified_as_pre_activation_stop", codes)

    def test_consistent_activation_trace_passes(self):
        result = analyze_run_traces(fixture("valid-run-trace.json"))
        self.assertTrue(result["valid"], result["findings"])

    def test_metadata_only_trace_is_unknown(self):
        result = analyze_run_traces({"data": [{"runId": "run_1", "nodes": []}]})
        self.assertTrue(result["valid"])
        self.assertEqual(result["traced_node_count"], 0)
        self.assertIn(
            "run_trace_outcomes_unknown",
            {item["code"] for item in result["findings"]},
        )

    def test_empty_trace_bundle_is_unknown(self):
        result = analyze_run_traces({"data": []})
        self.assertEqual(result["run_count"], 0)
        self.assertIn(
            "run_trace_outcomes_unknown",
            {item["code"] for item in result["findings"]},
        )

    def test_generic_verified_outcome_cannot_be_reclassified_as_failure(self):
        result = analyze_run_traces({"data": [{
            "runId": "run_generic",
            "nodes": [
                {"name": "Sync", "fields": {"terminal_outcome": "custom_sync_verified"}},
                {"name": "Final", "fields": {"terminal_outcome": "failed"}},
            ],
        }]})
        self.assertFalse(result["valid"])
        self.assertIn(
            "multiple_incompatible_outcome_classes_in_run",
            {item["code"] for item in result["findings"]},
        )

    def test_missing_terminal_outcome_is_unknown(self):
        result = analyze_run_traces({"data": [{"runId": "run_missing", "nodes": [
            {"name": "Enrichment", "fields": {"enrichment_verified": True}},
        ]}]})
        self.assertTrue(result["valid"])
        self.assertIn("terminal_outcome_unknown", {item["code"] for item in result["findings"]})

    def test_observed_outcome_must_be_declared(self):
        result = analyze_run_traces(
            {"data": [{"runId": "run_undeclared", "nodes": [
                {"name": "Final", "fields": {"terminal_outcome": "activated_verified"}},
            ]}]},
            {"failed"},
        )
        self.assertFalse(result["valid"])
        self.assertIn("terminal_outcome_not_declared", {item["code"] for item in result["findings"]})


class CollectorRedactionTests(unittest.TestCase):
    def test_audience_and_function_summaries_hash_sensitive_values(self):
        audience = {
            "id": "seg_fixture",
            "name": "Fixture",
            "entityType": "companies",
            "filter": {"operator": "Equal", "value": "private-example.com"},
        }
        summary = audience_summary({"id": "trigger", "segmentId": "seg_fixture"}, audience, {"count": 1})
        self.assertNotIn("private-example.com", json.dumps(summary))
        self.assertEqual(len(summary["identity_value_hashes"]), 1)

        fingerprint = function_fingerprint(
            "t_fixture",
            {"name": "Function", "secret": "do-not-write", "steps": [{"actionKey": "salesforce-create-record"}]},
        )
        self.assertNotIn("do-not-write", json.dumps(fingerprint))
        self.assertTrue(fingerprint["sha256"].startswith("sha256:"))

    def test_compact_run_trace_allowlists_outcome_fields(self):
        trace = compact_run_trace({
            "runId": "wfr_fixture",
            "nodes": [{
                "id": "node",
                "name": "Final",
                "status": "completed",
                "inputs": {"activation_executed": False, "workflow_outcome": "STALE_INPUT"},
                "output": {"email": "private@example.com", "body1": "private copy", "activation_executed": True},
            }],
        })
        rendered = json.dumps(trace)
        self.assertNotIn("private@example.com", rendered)
        self.assertNotIn("private copy", rendered)
        self.assertTrue(trace["nodes"][0]["fields"]["activation_executed"])
        self.assertNotIn("workflow_outcome", trace["nodes"][0]["fields"])

    def test_declared_monotonic_fields_expand_safely(self):
        manifest = fixture("valid-enrichment-manifest.json")
        manifest["workflow_contract"]["monotonic_evidence_fields"].extend([
            "custom_readback_verified", "email_verified", "api_key_verified",
        ])
        allowed = declared_trace_fields(manifest)
        self.assertIn("custom_readback_verified", allowed)
        self.assertNotIn("email_verified", allowed)
        self.assertNotIn("api_key_verified", allowed)


class RunSummaryTests(unittest.TestCase):
    def test_completed_does_not_become_activation_rate(self):
        result = summarize(fixture("runs-mixed.json"), fixture("provider-html-failure.json"))
        self.assertIsNone(result["activation_rate"])
        self.assertTrue(result["completed_is_not_business_success"])
        self.assertEqual(result["failure_category_counts"]["provider_contract_failure"], 1)

    def test_blocklist_is_destination_rejection(self):
        category, action = classify_error("Lead is in blocklist")
        self.assertEqual(category, "destination_rejection")
        self.assertIn("do_not_bypass", action)

    def test_runtime_errors_are_classified_and_node_names_are_resolved(self):
        failed = {
            "data": [{
                "runId": "wfr_fixture",
                "failed_nodes": [
                    {"nodeId": "hash", "name": None, "errors": ["NameError: name '_sha256' is not defined"]},
                    {"nodeId": "date", "name": None, "errors": ["ModuleNotFoundError: No module named datetime"]},
                ],
            }]
        }
        graph = {"nodes": [{"id": "hash", "name": "Build Hash"}, {"id": "date", "name": "Parse Date"}]}
        result = summarize({"data": []}, failed, graph)
        self.assertEqual(result["failures"][0]["node_name"], "Build Hash")
        self.assertEqual(result["failure_category_counts"]["runtime_undefined_name"], 1)
        self.assertEqual(result["failure_category_counts"]["runtime_dependency_failure"], 1)


class ReconciliationTests(unittest.TestCase):
    def test_verified_canary_can_prove_live_ready(self):
        result = analyze_reconciliation(fixture("valid-reconciliation-receipts.json"))
        self.assertTrue(result["valid"])
        self.assertTrue(result["live_ready_proven"])

    def test_duplicate_rerun_detects_two_activations(self):
        result = analyze_reconciliation(fixture("duplicate-reconciliation-receipts.json"))
        self.assertFalse(result["valid"])
        self.assertIn(
            "duplicate_activation_for_idempotency_key",
            {item["code"] for item in result["findings"]},
        )

    def test_timeout_after_submission_requires_readback(self):
        result = analyze_reconciliation(fixture("ambiguous-timeout-receipt.json"))
        self.assertFalse(result["valid"])
        finding = next(item for item in result["findings"] if item["code"] == "external_write_side_effect_unknown")
        self.assertEqual(finding["safe_next_action"], "read_destination_before_retry")

    def test_receipt_must_match_manifest_configuration(self):
        manifest = fixture("valid-campaign-manifest.json")
        result = analyze_reconciliation(
            fixture("valid-reconciliation-receipts.json"), configuration_hash(manifest)
        )
        self.assertFalse(result["valid"])
        self.assertIn("receipt_config_hash_mismatch", {item["code"] for item in result["findings"]})

    def test_activated_receipt_requires_non_empty_receipt_and_exact_readback_id(self):
        payload = copy.deepcopy(fixture("valid-reconciliation-receipts.json"))
        row = payload["data"][0]
        row["external_receipts"]["sequencer"] = {}
        row["readbacks"]["sequencer"].pop("campaign_id")
        result = analyze_reconciliation(payload)
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["valid"])
        self.assertIn("activated_without_external_receipts", codes)
        self.assertIn("readback_destination_mismatch", codes)

    def test_generic_success_outcome_accepts_exact_record_readback(self):
        payload = {"data": [{
            "workflow_id": "wf_fixture",
            "config_hash": "sha256:fixture",
            "stable_identity_hash": "sha256:company",
            "idempotency_key": "sync:company",
            "terminal_outcome": "synced_verified",
            "reconciliation_required": True,
            "reconciliation_owner": "revenue-operations",
            "intended_destinations": {"crm": "003-fixture"},
            "external_receipts": {"crm": {"request_id": "req-fixture"}},
            "readbacks": {"crm": {"verified": True, "record_id": "003-fixture"}},
        }]}
        result = analyze_reconciliation(
            payload,
            allowed_outcomes={"synced_verified"},
            success_outcomes={"synced_verified"},
        )
        self.assertTrue(result["valid"], result["findings"])
        self.assertTrue(result["live_ready_proven"])


def write_evidence(directory, *, graph=None, manifest=None, receipts=None, runs=None, run_traces=None):
    values = {
        "collector-metadata.json": {
            "evidence_contract_version": 2,
            "clay_cli_version": "fixture",
            "redaction_receipt": {"raw_sensitive_values_written": False},
        },
        "identity.json": {"workspace": {"id": "ws_fixture"}, "user": {"id": "user_fixture"}},
        "workflow.json": {"id": "wf_fixture_governed", "name": "Governed Fixture"},
        "graph.json": graph or fixture("valid-governed-graph.json"),
        "validation.json": {"valid": True, "errors": [], "warnings": []},
        "snapshots.json": {"data": []},
        "current-snapshot.json": fixture("valid-runtime-snapshot.json"),
        "triggers.json": {"data": []},
        "audience-segments.json": {"data": []},
        "function-fingerprints.json": {"data": []},
        "runs.json": runs or {"data": []},
        "failed-runs.json": {"data": []},
        "run-traces.json": run_traces or {"data": []},
    }
    if manifest is not None:
        values["manifest.json"] = manifest
    if receipts is not None:
        values["receipts.json"] = receipts
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value), encoding="utf-8")


class EvidenceCompatibilityTests(unittest.TestCase):
    def test_current_evidence_shape_is_compatible(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_evidence(directory)
            self.assertTrue(analyze_evidence(directory)["compatible"])

    def test_changed_graph_shape_blocks_automated_audit(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            graph = fixture("valid-governed-graph.json")
            graph["nodes"] = {"unexpected": "shape"}
            write_evidence(directory, graph=graph)
            result = analyze_evidence(directory)
            self.assertFalse(result["compatible"])
            self.assertIn("graph_shape_changed", {item["code"] for item in result["findings"]})

    def test_empty_current_snapshot_blocks_v2_compatibility(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_evidence(directory)
            (directory / "current-snapshot.json").write_text("{}", encoding="utf-8")
            result = analyze_evidence(directory)
            self.assertFalse(result["compatible"])
            self.assertIn(
                "current_snapshot_shape_changed",
                {item["code"] for item in result["findings"]},
            )


class AuditTests(unittest.TestCase):
    def test_untested_mismatch_is_draft_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_evidence(directory, graph=fixture("sequence-contract-mismatch.json"))
            result = audit(directory)
            self.assertEqual(result["readiness_ceiling"], "DRAFT_BLOCKED")
            self.assertFalse(result["live_ready_proven"])

    def test_enrichment_audit_marks_outbound_checks_not_applicable(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_evidence(
                directory,
                graph=fixture("enrichment-only-workflow.json"),
                manifest=fixture("valid-enrichment-manifest.json"),
            )
            result = audit(directory)
            self.assertEqual(result["readiness_ceiling"], "PREVIEW_READY", result)
            self.assertEqual(result["coverage"]["semantic_contract"], "NOT_APPLICABLE")
            self.assertEqual(result["coverage"]["trigger_safety"], "NOT_APPLICABLE")
            self.assertEqual(result["coverage"]["destination_reconciliation"], "NOT_APPLICABLE")

    def test_enrichment_trace_without_terminal_outcome_cannot_reach_live(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = fixture("valid-enrichment-manifest.json")
            manifest["workflow_contract"].update({"state": "LIVE_READY", "ready": True})
            manifest["approvals"].update({
                "paid_work": True, "publish": True,
                "config_hash": configuration_hash(manifest),
                "reference": "APPROVAL-ENRICH-UNKNOWN", "approver": "revenue-operations",
                "approved_at": "2025-01-01T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z",
            })
            write_evidence(
                directory, graph=fixture("enrichment-only-workflow.json"), manifest=manifest,
                runs={"data": [{"status": "completed"}]},
                run_traces={"data": [{"runId": "wfr_unknown", "nodes": [{
                    "name": "Finalize", "fields": {"enrichment_verified": True},
                }]}]},
            )
            result = audit(directory)
            self.assertNotEqual(result["readiness_ceiling"], "LIVE_READY")
            self.assertEqual(result["coverage"]["run_outcome_consistency"], "UNKNOWN")

    def test_reconciliation_success_outcome_must_be_declared(self):
        manifest = fixture("valid-campaign-manifest.json")
        manifest["reconciliation"]["success_outcome"] = "activated_verified"
        manifest["workflow_contract"]["terminal_outcomes"] = ["failed"]
        result = analyze_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertIn("reconciliation_success_outcome_not_declared", {item["code"] for item in result["findings"]})

    def test_non_mutating_enrichment_can_reach_live_without_destination_receipts(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = fixture("valid-enrichment-manifest.json")
            manifest["workflow_contract"].update({"state": "LIVE_READY", "ready": True})
            manifest["approvals"].update({
                "paid_work": True,
                "publish": True,
                "config_hash": configuration_hash(manifest),
                "reference": "APPROVAL-ENRICH-1",
                "approver": "revenue-operations",
                "approved_at": "2025-01-01T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            write_evidence(
                directory,
                graph=fixture("enrichment-only-workflow.json"),
                manifest=manifest,
                runs={"data": [{"status": "completed"}]},
                run_traces={"data": [{
                    "runId": "wfr_enrichment",
                    "nodes": [{
                        "name": "Finalize Verified Enrichment",
                        "fields": {
                            "terminal_outcome": "enriched_verified",
                            "enrichment_verified": True,
                        },
                    }],
                }]},
            )
            result = audit(directory)
            self.assertEqual(result["readiness_ceiling"], "LIVE_READY", result)
            self.assertEqual(result["coverage"]["destination_reconciliation"], "NOT_APPLICABLE")

    def test_verified_canary_and_governance_can_reach_live_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            manifest = copy.deepcopy(fixture("valid-campaign-manifest.json"))
            manifest["campaign"].update({"state": "LIVE_READY", "ready": True})
            manifest["workflow_contract"].update({"state": "LIVE_READY", "ready": True})
            manifest["approvals"].update({
                "paid_work": True,
                "copy_generation": True,
                "publish": True,
                "sequencer_write": True,
                "outbound_activation": True,
                "config_hash": configuration_hash(manifest),
                "reference": "APPROVAL-LIVE-1",
                "approver": "growth-lead",
                "approved_at": "2025-01-01T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            receipts = copy.deepcopy(fixture("valid-reconciliation-receipts.json"))
            receipts["data"][0]["config_hash"] = configuration_hash(manifest)
            write_evidence(
                directory,
                manifest=manifest,
                receipts=receipts,
                runs={"data": [{"status": "completed"}]},
                run_traces=fixture("valid-run-trace.json"),
            )
            result = audit(directory)
            self.assertEqual(result["readiness_ceiling"], "LIVE_READY", result)
            self.assertTrue(result["live_ready_proven"])


class ExplainerTests(unittest.TestCase):
    def test_plain_english_model_preserves_evidence_boundaries(self):
        model = build_model(
            fixture("explainable-workflow.json"),
            {"valid": True, "errors": [], "warnings": []},
            {"data": [{"status": "completed"}]},
        )
        self.assertEqual(model["unit_of_work"], "one person or queued contact")
        self.assertIn("Salesforce", model["systems"])
        self.assertIn("Instantly", model["systems"])
        self.assertTrue(model["paid_steps"])
        self.assertTrue(model["external_writes"])
        self.assertTrue(model["readbacks"])
        self.assertFalse(model["evidence"]["business_outcome_proven"])
        self.assertEqual(model["field_contract"]["account"]["account_employee_min"], 250)
        self.assertIn("marketing operations", model["field_contract"]["contact"]["target_title_include_terms"])
        self.assertIn("HasOptedOutOfEmail = false", model["field_contract"]["salesforce_contact_predicates"])
        self.assertIn("Cleaned Domain", model["field_contract"]["account_source_fields"])

    def test_markdown_explains_journey_and_next_proof(self):
        model = build_model(fixture("explainable-workflow.json"), {"valid": True}, {"data": []})
        rendered = render_markdown(model)
        for required in (
            "The story",
            "Each selected person is then given a separate queue record",
            "Only after those cheaper checks does the workflow spend credits",
            "`Campaign Launch Ready`",
            "`# Open Oppty` must be zero",
            "`marketing operations`",
            "`HasOptedOutOfEmail = false`",
            "How the story can end",
            "What is real today",
            "Receipts from the graph",
            "In one sentence:",
            "Next check:",
        ):
            self.assertIn(required, rendered)
        self.assertLess(rendered.index("## The story"), rendered.index("## Receipts from the graph"))
        self.assertNotIn("1. **Entry and configuration:**", rendered)
        self.assertIn("configured behavior rather than observed production behavior", rendered)

    def test_explainer_translates_semantic_blocker_before_canary(self):
        model = build_model(fixture("sequence-contract-mismatch.json"), {"valid": True}, {"data": []})
        rendered = render_markdown(model)
        self.assertIn("handles 2 emails", rendered)
        self.assertIn("requires 5", rendered)
        self.assertIn("before any canary", rendered)


if __name__ == "__main__":
    unittest.main()
