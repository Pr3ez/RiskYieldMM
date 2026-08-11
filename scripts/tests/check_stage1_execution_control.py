#!/usr/bin/env python3
"""Fail closed when the Stage 1 control ledger drifts from its recorded P0."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "docs/research/stage1_execution_control_2026-08-08.md"
GENERATOR_PATH = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py"
)
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
FINALIZER_PATH = (
    ROOT / "scripts/tests/finalize_raw_v8_step2_maximum_protocol_v2_v49f.py"
)
FINALIZER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_finalizer_v49f.py"
)
FINALIZATION_MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
FINALIZATION_MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"
CONSTRUCTIVE_BOUNDARY_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
CONSTRUCTIVE_BOUNDARY_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.py"
)
IMPLEMENTATION_FAIL_FIRST_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py"
)
INDEPENDENT_VERIFIER_PATH = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
INDEPENDENT_VERIFIER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v0_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_EXPANSION_V1_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_expansion_v1_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V1_DIFFERENTIAL_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_v1_runtime_differential_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V1_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v1_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_EXPANSION_V2_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_expansion_v2_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V2_DIFFERENTIAL_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_v2_runtime_differential_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V2_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v2_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_EXPANSION_V3_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_expansion_v3_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V3_DIFFERENTIAL_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_v3_runtime_differential_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V3_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v3_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_EXPANSION_V4_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_expansion_v4_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V4_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v4_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_ACCEPTANCE_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_v49f.py"
)
INDEPENDENT_VERIFIER_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/Archive/a4_p6_v_a_historical/"
    "test_raw_v8_step2_maximum_protocol_v2_independent_verifier_acceptance_v49f.py"
)
INDEPENDENT_VERIFIER_ACCEPTANCE_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_acceptance_report_v49f.json"
)
INDEPENDENT_VERIFIER_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_acceptance_2026-08-10.md"
)
INDEPENDENT_VERIFIER_ACCEPTANCE_REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2IndependentVerifierAcceptanceReportV1V4_9F_RawV8"
)
TYPED_RULE_RUNTIME_PATH = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
SEPARATE_PRODUCER_PATH = (
    ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
HISTORICAL_SEPARATE_PRODUCER_PATH = (
    ROOT / "scripts/tests/Archive/a4_p_predecessor_accepted/"
    "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
SEPARATE_PRODUCER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_separate_producer_v49f.py"
)
SEPARATE_PRODUCER_EXPANSION_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_v49f.py"
)
SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_v49f.py"
)
SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_report_v49f.json"
)
SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_v49f.py"
)
SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "separate_producer_expansion_acceptance_2026-08-10.md"
)
SEPARATE_PRODUCER_EXPANSION_REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2SeparateProducerExpansionAcceptanceReportV1"
    "V4_9F_RawV8"
)
PARENT_PILOT_RUNNER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_parent_pilot_runner_v49f.py"
)
PARENT_PILOT_RUNNER_ACCEPTANCE_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_v49f.py"
)
PARENT_PILOT_RUNNER_ACCEPTANCE_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_acceptance_report_v49f.json"
)
PARENT_PILOT_RUNNER_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_acceptance_v49f.py"
)
PARENT_PILOT_RUNNER_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "parent_pilot_runner_acceptance_2026-08-10.md"
)
PARENT_PILOT_RUNNER_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2ParentPilotRunnerAcceptanceReportV1"
)
SIX_CASE_END_TO_END_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "six_case_end_to_end_v49f.py"
)
SIX_CASE_END_TO_END_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "six_case_end_to_end_acceptance_report_v49f.json"
)
SIX_CASE_END_TO_END_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "six_case_end_to_end_acceptance_v49f.py"
)
SIX_CASE_END_TO_END_DESIGN_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "six_case_end_to_end_acceptance_design_2026-08-11.md"
)
SIX_CASE_END_TO_END_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "six_case_end_to_end_acceptance_2026-08-11.md"
)
SIX_CASE_END_TO_END_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2SixCaseEndToEndAcceptanceReportV1"
)
ALL_CASE_CAMPAIGN_CONTRACT_GENERATOR_PATH = (
    ROOT / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.py"
)
ALL_CASE_CAMPAIGN_CONTRACT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
ALL_CASE_CAMPAIGN_CONTRACT_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.py"
)
ALL_CASE_CAMPAIGN_CONTRACT_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_acceptance_report_v49f.json"
)
ALL_CASE_CAMPAIGN_CONTRACT_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.py"
)
ALL_CASE_CAMPAIGN_FAIL_FIRST_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_fail_first_v49f.py"
)
ALL_CASE_CAMPAIGN_CONTRACT_DESIGN_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "all_case_campaign_contract_design_2026-08-11.md"
)
ALL_CASE_CAMPAIGN_CONTRACT_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "all_case_campaign_contract_acceptance_2026-08-11.md"
)
ALL_CASE_CAMPAIGN_CONTRACT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractV1"
)
ALL_CASE_CAMPAIGN_CONTRACT_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "AllCaseCampaignContractAcceptanceReportV1"
)
ALL_CASE_VERIFIER_FOUNDATION_PATH = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
    "all_case_candidate_v49f.py"
)
ALL_CASE_VERIFIER_FOUNDATION_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_v49f.py"
)
ALL_CASE_VERIFIER_FOUNDATION_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_acceptance_report_v49f.json"
)
ALL_CASE_VERIFIER_FOUNDATION_FAIL_FIRST_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_fail_first_v49f.py"
)
ALL_CASE_VERIFIER_FOUNDATION_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_v49f.py"
)
ALL_CASE_VERIFIER_FOUNDATION_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_acceptance_v49f.py"
)
ALL_CASE_VERIFIER_FOUNDATION_DESIGN_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "all_case_verifier_foundation_design_2026-08-11.md"
)
ALL_CASE_VERIFIER_FOUNDATION_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "all_case_verifier_foundation_acceptance_2026-08-11.md"
)
ALL_CASE_VERIFIER_FOUNDATION_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "AllCaseVerifierFoundationAcceptanceReportV1"
)
INTRINSIC_ATTAINABILITY_ANALYZER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
INTRINSIC_ATTAINABILITY_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
INTRINSIC_ATTAINABILITY_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
INTRINSIC_ATTAINABILITY_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_acceptance_report_v49f.json"
)
INTRINSIC_ATTAINABILITY_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_acceptance_v49f.py"
)
INTRINSIC_ATTAINABILITY_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "intrinsic_template_attainability_falsification_2026-08-11.md"
)
INTRINSIC_ATTAINABILITY_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicTemplate"
    "AttainabilityFalsificationAcceptanceV1"
)
INTRINSIC_CORRECTION_CONTRACT_GENERATOR_PATH = (
    ROOT / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
INTRINSIC_CORRECTION_CONTRACT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
INTRINSIC_CORRECTION_CONTRACT_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
INTRINSIC_CORRECTION_CONTRACT_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
INTRINSIC_CORRECTION_CONTRACT_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_acceptance_report_v49f.json"
)
INTRINSIC_CORRECTION_CONTRACT_ACCEPTANCE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_acceptance_v49f.py"
)
INTRINSIC_CORRECTION_CONTRACT_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "intrinsic_correction_contract_acceptance_2026-08-11.md"
)
INTRINSIC_CORRECTION_CONTRACT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionContractV1"
)
INTRINSIC_CORRECTION_CONTRACT_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicExactnessCorrectionContractAcceptanceReportV1"
)
INTRINSIC_DUAL_SOURCE_FREEZE_GENERATOR_PATH = (
    ROOT / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.py"
)
INTRINSIC_DUAL_SOURCE_FREEZE_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
INTRINSIC_UPPER_SOURCE_PATH = (
    ROOT / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_v49f.py"
)
INTRINSIC_ATTAINER_SOURCE_PATH = (
    ROOT / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainers_v49f.py"
)
INTRINSIC_UPPER_SCHEMA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_result_schema_v49f.json"
)
INTRINSIC_ATTAINER_SCHEMA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_result_schema_v49f.json"
)
INTRINSIC_DUAL_SOURCE_FREEZE_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.py"
)
INTRINSIC_DUAL_SOURCE_FREEZE_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_acceptance_report_v49f.json"
)
INTRINSIC_DUAL_SOURCE_FREEZE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.py"
)
INTRINSIC_DUAL_SOURCE_FREEZE_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "intrinsic_dual_source_freeze_acceptance_2026-08-11.md"
)
INTRINSIC_DUAL_SOURCE_FREEZE_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicDualSourceFreezeV1"
)
INTRINSIC_DUAL_SOURCE_FREEZE_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicDualSourceFreezeAcceptanceReportV1"
)
INTRINSIC_UPPER_CHANNEL_RESULT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_result_v49f.json"
)
INTRINSIC_UPPER_CHANNEL_REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_v49f.py"
)
INTRINSIC_UPPER_CHANNEL_REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_acceptance_report_v49f.json"
)
INTRINSIC_UPPER_CHANNEL_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_v49f.py"
)
INTRINSIC_UPPER_CHANNEL_ACCEPTANCE_DOC_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "intrinsic_upper_channel_acceptance_2026-08-11.md"
)
INTRINSIC_UPPER_CHANNEL_RESULT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicLegalUpperResultV1"
)
INTRINSIC_UPPER_CHANNEL_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicUpperChannelAcceptanceV1"
)
INTRINSIC_C2_OFFICIAL_OUTPUT_PATHS = (
    INTRINSIC_UPPER_CHANNEL_RESULT_PATH,
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_channel_result_v49f.json",
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_witness_shard_1_v49f.json",
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_witness_shard_2_v49f.json",
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_witness_shard_3_v49f.json",
)
SIX_CASE_QUALIFICATION_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)
CASE435_ATTAINABILITY_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)
CASE435_ATTAINABILITY_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_profile_attainability_scope_and_correction_design_2026-08-10.md"
)
CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py"
)
CASE435_DEPENDENCY_CLOSURE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py"
)
CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_case435_dependency_closure_acceptance_2026-08-10.md"
)
CASE435_UPPER_SOLVER_PATH = (
    ROOT / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py"
)
CASE435_UPPER_CERTIFICATE_CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py"
)
CASE435_UPPER_CERTIFICATE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py"
)
CASE435_UPPER_ACCEPTANCE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_case435_exact_upper_acceptance_2026-08-10.md"
)
CASE435_ATTAINER_CONSTRUCTOR_PATH = (
    ROOT
    / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py"
)
CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)
CASE435_ATTAINER_CERTIFICATE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)
CASE435_ATTAINER_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_independent_attainer_acceptance_2026-08-10.md"
)
CASE435_EXACTNESS_JOIN_PATH = (
    ROOT / "scripts/tests/join_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_v49f.py"
)
CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_certificate_v49f.py"
)
CASE435_EXACTNESS_JOIN_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py"
)
CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_exactness_join_acceptance_2026-08-10.md"
)
CASE435_AUTHORITY_MIGRATOR_PATH = (
    ROOT / "scripts/tests/migrate_raw_v8_step2_maximum_protocol_v2_"
    "case435_authorities_v49f.py"
)
CASE435_AUTHORITY_TRANSITION_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_authority_transition_v49f.py"
)
CASE435_AUTHORITY_TRANSITION_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "case435_authority_transition_v49f.py"
)
CASE435_SEED_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
CASE435_MANIFEST_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_manifest_delta_v49f.json"
)
CASE435_BOUNDARY_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_boundary_delta_v49f.json"
)
CASE435_TARGET_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_authority_transition_acceptance_2026-08-10.md"
)
CASE435_CONTEXT_PACK_GENERATOR_PATH = (
    ROOT / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_v49f.py"
)
CASE435_CONTEXT_PACK_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_v49f.py"
)
CASE435_CONTEXT_PACK_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
CASE435_CONTEXT_PACK_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_v49f.py"
)
CASE435_CONTEXT_PACK_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_context_pack_boundary_acceptance_2026-08-10.md"
)
PARENT_PILOT_RUNNER_PATH = (
    ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)
CONSTRUCTIVE_BOUNDARY_DOMAIN = (
    "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
)
F2_RESOURCE_LIMIT_CATALOG_DOMAIN = "RiskYieldMMStep2F2ResourceLimitCatalogV1V4_9F_RawV8"
S1_A2_AUTHORITY_ROLES = (
    "PREFLIGHT_CONTRACT",
    "PREFLIGHT_A",
    "PREFLIGHT_A_TEST",
    "PREFLIGHT_B",
    "PREFLIGHT_B_TEST",
    "PREFLIGHT_COMPARATOR",
    "PREFLIGHT_COMPARATOR_TEST",
)
CONTROL_PATTERN = re.compile(
    r"<!-- STAGE1_CONTROL_JSON_START\n(?P<payload>\{.*?\})\n"
    r"STAGE1_CONTROL_JSON_END -->",
    re.DOTALL,
)
ALLOWED_STATES = {"ACCEPTED", "ACTIVE", "READY", "WAITING", "HOLD", "REJECTED"}
ACTIVE_GATE_PATTERN = re.compile(
    r"<!-- STAGE1_ACTIVE_GATE: (?P<gate>S1-(?:[A-Z][0-9]+|X)) -->"
)


class ControlFailure(RuntimeError):
    """The current tree does not match the Stage 1 control ledger."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ControlFailure(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _ordered_pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _load_control() -> dict[str, Any]:
    text = CONTROL_PATH.read_text(encoding="utf-8")
    match = CONTROL_PATTERN.search(text)
    _require(match is not None, "machine-readable control block is missing")
    control = json.loads(match.group("payload"))
    _require(isinstance(control, dict), "control block must be an object")
    return control


def _validate_gate_graph(control: dict[str, Any]) -> None:
    gates = control.get("gate_states")
    _require(isinstance(gates, dict) and gates, "gate_states must be nonempty")
    active = []
    for gate_id, row in gates.items():
        _require(
            re.fullmatch(r"S1-(?:[A-Z][0-9]+|X)", gate_id) is not None,
            f"bad gate {gate_id}",
        )
        _require(isinstance(row, dict), f"{gate_id} row must be an object")
        _require(set(row) == {"depends_on", "state"}, f"{gate_id} members differ")
        state = row["state"]
        _require(state in ALLOWED_STATES, f"{gate_id} has unknown state {state}")
        if state == "ACTIVE":
            active.append(gate_id)
        dependencies = row["depends_on"]
        _require(isinstance(dependencies, list), f"{gate_id} dependencies differ")
        _require(
            len(dependencies) == len(set(dependencies)),
            f"{gate_id} duplicates a dependency",
        )
        for dependency in dependencies:
            _require(
                dependency in gates, f"{gate_id} has unknown dependency {dependency}"
            )
            _require(dependency != gate_id, f"{gate_id} depends on itself")

    _require(
        active == [control.get("active_gate")],
        "exactly one declared active gate is required",
    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(gate_id: str) -> None:
        _require(gate_id not in visiting, f"gate dependency cycle reaches {gate_id}")
        if gate_id in visited:
            return
        visiting.add(gate_id)
        for dependency in gates[gate_id]["depends_on"]:
            visit(dependency)
        visiting.remove(gate_id)
        visited.add(gate_id)

    for gate_id in gates:
        visit(gate_id)

    for gate_id, row in gates.items():
        if row["state"] in {"ACTIVE", "READY"}:
            for dependency in row["depends_on"]:
                _require(
                    gates[dependency]["state"] == "ACCEPTED",
                    f"{gate_id} is {row['state']} before {dependency} is accepted",
                )


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_seed_generator", GENERATOR_PATH
    )
    _require(spec is not None and spec.loader is not None, "cannot load seed generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_intrinsic_upper_channel_reviewer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_intrinsic_upper_channel_reviewer",
        INTRINSIC_UPPER_CHANNEL_REVIEWER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load intrinsic upper-channel reviewer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainability_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainability_analyzer",
        CASE435_ATTAINABILITY_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainability analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_profile_attainability_scope_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_profile_attainability_scope_analyzer",
        PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load profile-attainability scope analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_dependency_closure_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_dependency_closure_analyzer",
        CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 dependency-closure analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_upper_solver() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_upper_solver",
        CASE435_UPPER_SOLVER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exact-upper solver",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_upper_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_upper_certificate_checker",
        CASE435_UPPER_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 upper-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainer_constructor() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainer_constructor",
        CASE435_ATTAINER_CONSTRUCTOR_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainer constructor",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainer_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainer_certificate_checker",
        CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainer-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_exactness_join() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_exactness_join",
        CASE435_EXACTNESS_JOIN_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exactness join",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_exactness_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_exactness_certificate_checker",
        CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exactness-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_authority_transition_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_authority_transition_checker",
        CASE435_AUTHORITY_TRANSITION_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 authority-transition checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_context_pack_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_context_pack_checker",
        CASE435_CONTEXT_PACK_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 context-pack checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_navigation(active_gate: str) -> None:
    pointers = {
        ROOT / "README.md": "docs/research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/README.md": "research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/research/README.md": "stage1_execution_control_2026-08-08.md",
        ROOT
        / "docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md": (
            "stage1_execution_control_2026-08-08.md"
        ),
    }
    for path, pointer in pointers.items():
        text = path.read_text(encoding="utf-8")
        _require(
            pointer in text,
            f"missing current pointer in {path}",
        )
        markers = ACTIVE_GATE_PATTERN.findall(text)
        _require(
            markers == [active_gate],
            f"active-gate navigation marker differs in {path}: {markers}",
        )


def _validate_s1_a2_snapshot(snapshot: dict[str, Any]) -> None:
    _require(
        set(snapshot)
        == {
            "comparison_payload_id",
            "comparison_raw_octets",
            "comparison_raw_sha256",
            "ordered_authority_records",
            "semantic_count_vector_sha256",
            "semantic_payload_id",
            "semantic_raw_octets",
            "semantic_raw_sha256",
        },
        "S1-A2 snapshot members differ",
    )
    records = snapshot["ordered_authority_records"]
    _require(isinstance(records, list), "S1-A2 authority records are missing")
    _require(
        [row.get("artifact_role") for row in records] == list(S1_A2_AUTHORITY_ROLES),
        "S1-A2 authority order differs",
    )
    paths: list[str] = []
    hashes: list[str] = []
    for position, row in enumerate(records, 1):
        _require(
            set(row)
            == {
                "artifact_position",
                "artifact_role",
                "raw_octets",
                "raw_sha256",
                "repository_relative_path",
            },
            f"S1-A2 authority {position} members differ",
        )
        _require(
            row["artifact_position"] == position,
            f"S1-A2 authority {position} position differs",
        )
        relative = row["repository_relative_path"]
        _require(
            isinstance(relative, str)
            and relative
            and not relative.startswith("/")
            and ".." not in Path(relative).parts,
            f"S1-A2 authority {position} path is invalid",
        )
        path = ROOT / relative
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A2 authority {position} is not a regular file",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == row["raw_octets"],
            f"S1-A2 authority {position} size drifted",
        )
        _require(
            _sha256(raw) == row["raw_sha256"],
            f"S1-A2 authority {position} hash drifted",
        )
        paths.append(relative)
        hashes.append(row["raw_sha256"])
    _require(len(paths) == len(set(paths)), "S1-A2 authority path is duplicated")
    _require(len(hashes) == len(set(hashes)), "S1-A2 authority hash is duplicated")

    for name in (
        "comparison_payload_id",
        "comparison_raw_sha256",
        "semantic_count_vector_sha256",
        "semantic_payload_id",
        "semantic_raw_sha256",
    ):
        value = snapshot[name]
        _require(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value),
            f"S1-A2 {name} is not a SHA-256 identity",
        )
    _require(
        snapshot["comparison_raw_octets"] == 1_206,
        "S1-A2 comparison size differs",
    )
    _require(
        snapshot["semantic_raw_octets"] == 1_702_217,
        "S1-A2 semantic size differs",
    )


def _validate_s1_a3_snapshot(
    snapshot: dict[str, Any], s1_a2_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "comparison_payload_id",
            "finalization_manifest_id",
            "finalization_manifest_raw_octets",
            "finalization_manifest_raw_sha256",
            "finalizer_raw_octets",
            "finalizer_raw_sha256",
            "finalizer_test_raw_octets",
            "finalizer_test_raw_sha256",
            "ordered_f2_limit_record_count",
            "semantic_count_vector_sha256",
            "semantic_payload_id",
        },
        "S1-A3 snapshot members differ",
    )
    artifacts = (
        (
            "finalizer",
            FINALIZER_PATH,
            snapshot["finalizer_raw_octets"],
            snapshot["finalizer_raw_sha256"],
        ),
        (
            "finalizer test",
            FINALIZER_TEST_PATH,
            snapshot["finalizer_test_raw_octets"],
            snapshot["finalizer_test_raw_sha256"],
        ),
        (
            "finalization manifest",
            FINALIZATION_MANIFEST_PATH,
            snapshot["finalization_manifest_raw_octets"],
            snapshot["finalization_manifest_raw_sha256"],
        ),
    )
    for label, path, expected_octets, expected_sha256 in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A3 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == expected_octets, f"S1-A3 {label} size drifted")
        _require(_sha256(raw) == expected_sha256, f"S1-A3 {label} hash drifted")

    manifest_raw = FINALIZATION_MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_raw)
    _require(isinstance(manifest, dict), "S1-A3 manifest root differs")
    _require(
        manifest_raw == _pretty_bytes(manifest),
        "S1-A3 manifest is not canonical pretty JSON",
    )
    expected_root = {
        "canonicalization_version",
        "comparison_evidence",
        "finalization_manifest_id",
        "finalization_manifest_version",
        "finalization_status",
        "ordered_f2_limit_records",
        "ordered_implementation_authorities",
        "preflight_contract_authority",
        "protocol_counting_semantics_id",
        "protocol_version",
        "seed_authority",
        "semantic_evidence",
    }
    _require(set(manifest) == expected_root, "S1-A3 manifest members differ")
    _require(
        manifest["finalization_status"] == "FINAL_V2_F2_FROZEN",
        "S1-A3 manifest status differs",
    )
    identity_payload = {
        name: value
        for name, value in manifest.items()
        if name != "finalization_manifest_id"
    }
    identity = _sha256(
        _canonical_bytes(
            {"domain": FINALIZATION_MANIFEST_DOMAIN, "payload": identity_payload}
        )
    )
    _require(
        manifest["finalization_manifest_id"]
        == snapshot["finalization_manifest_id"]
        == identity,
        "S1-A3 manifest identity differs",
    )

    semantic = manifest["semantic_evidence"]
    comparison = manifest["comparison_evidence"]
    _require(
        semantic["semantic_payload_id"]
        == snapshot["semantic_payload_id"]
        == s1_a2_snapshot["semantic_payload_id"],
        "S1-A3 semantic payload identity differs",
    )
    _require(
        semantic["semantic_count_vector_sha256"]
        == snapshot["semantic_count_vector_sha256"]
        == s1_a2_snapshot["semantic_count_vector_sha256"],
        "S1-A3 semantic count-vector identity differs",
    )
    _require(
        comparison["comparison_payload_id"]
        == snapshot["comparison_payload_id"]
        == s1_a2_snapshot["comparison_payload_id"],
        "S1-A3 comparison identity differs",
    )
    for name in (
        "semantic_payload_bytes_equal",
        "all_475_case_records_equal",
        "all_18_metric_summaries_equal",
        "all_resource_limits_satisfied",
    ):
        _require(comparison[name] is True, f"S1-A3 comparison flag {name} differs")

    authorities = {
        row["implementation_label"]: row
        for row in manifest["ordered_implementation_authorities"]
    }
    a2_authorities = {
        row["artifact_role"]: row for row in s1_a2_snapshot["ordered_authority_records"]
    }
    _require(
        [
            row["implementation_label"]
            for row in manifest["ordered_implementation_authorities"]
        ]
        == ["A", "B", "COMPARATOR"],
        "S1-A3 implementation order differs",
    )
    for label, role in (
        ("A", "PREFLIGHT_A"),
        ("B", "PREFLIGHT_B"),
        ("COMPARATOR", "PREFLIGHT_COMPARATOR"),
    ):
        _require(
            authorities[label]["raw_sha256"] == a2_authorities[role]["raw_sha256"],
            f"S1-A3 {label} source seal differs",
        )

    f2_records = manifest["ordered_f2_limit_records"]
    _require(
        isinstance(f2_records, list)
        and len(f2_records) == snapshot["ordered_f2_limit_record_count"] == 18,
        "S1-A3 F2 record count differs",
    )
    for position, row in enumerate(f2_records, 1):
        _require(row["metric_position"] == position, f"S1-A3 F2 {position} order")
        integer_names = (
            "required_per_case",
            "per_case_rounding_unit",
            "f2_per_case",
            "per_case_f0_ceiling",
            "required_full_run",
            "full_run_rounding_unit",
            "f2_full_run",
            "full_run_f0_ceiling",
        )
        _require(
            all(
                isinstance(row[name], int)
                and not isinstance(row[name], bool)
                and row[name] >= 0
                for name in integer_names
            ),
            f"S1-A3 F2 {position} integer domain differs",
        )
        per_unit = row["per_case_rounding_unit"]
        full_unit = row["full_run_rounding_unit"]
        _require(per_unit > 0 and full_unit > 0, f"S1-A3 F2 {position} zero unit")
        expected_per = row["required_per_case"] + (
            (per_unit - (row["required_per_case"] % per_unit)) % per_unit
        )
        expected_full = row["required_full_run"] + (
            (full_unit - (row["required_full_run"] % full_unit)) % full_unit
        )
        _require(
            row["f2_per_case"] == expected_per
            and row["required_per_case"]
            <= row["f2_per_case"]
            <= row["per_case_f0_ceiling"],
            f"S1-A3 F2 {position} per-case derivation differs",
        )
        _require(
            row["f2_full_run"] == expected_full
            and row["required_full_run"]
            <= row["f2_full_run"]
            <= row["full_run_f0_ceiling"],
            f"S1-A3 F2 {position} full-run derivation differs",
        )


def _validate_s1_a4_boundary_snapshot(
    snapshot: dict[str, Any], s1_a3_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "boundary_raw_octets",
            "boundary_raw_sha256",
            "boundary_test_raw_octets",
            "boundary_test_raw_sha256",
            "constructive_boundary_id",
            "f2_resource_limit_catalog_id",
            "focused_passed",
            "legacy_v1_bootstrap_raw_octets",
            "legacy_v1_bootstrap_raw_sha256",
            "maximum_protocol_sha256",
            "ordered_pilot_case_positions",
        },
        "S1-A4 boundary snapshot members differ",
    )
    artifacts = (
        (
            "constructive boundary",
            CONSTRUCTIVE_BOUNDARY_PATH,
            snapshot["boundary_raw_octets"],
            snapshot["boundary_raw_sha256"],
        ),
        (
            "constructive boundary test",
            CONSTRUCTIVE_BOUNDARY_TEST_PATH,
            snapshot["boundary_test_raw_octets"],
            snapshot["boundary_test_raw_sha256"],
        ),
    )
    for label, path, expected_octets, expected_sha256 in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == expected_octets, f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == expected_sha256, f"S1-A4 {label} hash drifted")

    raw = CONSTRUCTIVE_BOUNDARY_PATH.read_bytes()
    boundary = json.loads(raw)
    _require(isinstance(boundary, dict), "S1-A4 boundary root differs")
    _require(
        raw == _ordered_pretty_bytes(boundary),
        "S1-A4 boundary physical encoding differs",
    )
    expected_root_order = [
        "boundary_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "boundary_status",
        "authority_contract",
        "implementation_role_contract",
        "candidate_bundle_contract",
        "verifier_output_contract",
        "pilot_contract",
        "resource_enforcement_contract",
        "filesystem_contract",
        "independence_contract",
        "legacy_v1_exclusion_contract",
        "constructive_boundary_id",
    ]
    _require(
        list(boundary) == expected_root_order,
        "S1-A4 boundary root order differs",
    )
    _require(
        boundary["boundary_status"] == "A4_B0_V2_ONLY_BOUNDARY_FROZEN",
        "S1-A4 boundary status differs",
    )
    identity_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    identity = _sha256(
        _canonical_bytes(
            {"domain": CONSTRUCTIVE_BOUNDARY_DOMAIN, "payload": identity_payload}
        )
    )
    _require(
        boundary["constructive_boundary_id"]
        == snapshot["constructive_boundary_id"]
        == identity,
        "S1-A4 constructive boundary identity differs",
    )

    authority = boundary["authority_contract"]
    manifest_authority = authority["finalization_manifest_authority"]
    _require(
        manifest_authority["finalization_manifest_id"]
        == s1_a3_snapshot["finalization_manifest_id"],
        "S1-A4 finalization manifest identity differs",
    )
    _require(
        manifest_authority["raw_sha256"]
        == snapshot["maximum_protocol_sha256"]
        == s1_a3_snapshot["finalization_manifest_raw_sha256"],
        "S1-A4 maximum-protocol physical binding differs",
    )
    _require(
        authority["downstream_field_binding_rules"]["maximum_protocol_sha256"]
        == "FINALIZATION_MANIFEST_AUTHORITY_RAW_SHA256",
        "S1-A4 downstream maximum-protocol mapping differs",
    )

    manifest = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())
    f2_catalog = authority["f2_resource_limit_catalog"]
    f2_payload = {
        "catalog_version": f2_catalog["catalog_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": authority["seed_authority"]["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "ordered_f2_limit_records": manifest["ordered_f2_limit_records"],
    }
    f2_identity = _sha256(
        _canonical_bytes(
            {
                "domain": F2_RESOURCE_LIMIT_CATALOG_DOMAIN,
                "payload": f2_payload,
            }
        )
    )
    _require(
        f2_catalog["f2_resource_limit_catalog_id"]
        == snapshot["f2_resource_limit_catalog_id"]
        == f2_identity,
        "S1-A4 F2 resource-limit catalog identity differs",
    )

    pilot_positions = [
        row["case_position"]
        for row in boundary["pilot_contract"]["ordered_pilot_case_records"]
    ]
    _require(
        pilot_positions
        == snapshot["ordered_pilot_case_positions"]
        == [5, 24, 54, 69, 435, 475],
        "S1-A4 pilot case positions differ",
    )
    _require(snapshot["focused_passed"] == 28, "S1-A4 focused test count differs")

    legacy = boundary["legacy_v1_exclusion_contract"]["rejected_bootstrap_authority"]
    legacy_path = ROOT / legacy["repository_relative_path"]
    _require(
        legacy_path.is_file() and not legacy_path.is_symlink(),
        "S1-A4 legacy V1 bootstrap is absent",
    )
    legacy_raw = legacy_path.read_bytes()
    _require(
        len(legacy_raw)
        == legacy["raw_octets"]
        == snapshot["legacy_v1_bootstrap_raw_octets"],
        "S1-A4 legacy V1 bootstrap size drifted",
    )
    _require(
        _sha256(legacy_raw)
        == legacy["raw_sha256"]
        == snapshot["legacy_v1_bootstrap_raw_sha256"],
        "S1-A4 legacy V1 bootstrap hash drifted",
    )


def _validate_s1_a4_fail_first_snapshot(
    snapshot: dict[str, Any], boundary_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "constructive_boundary_id",
            "contract_hostile_passed",
            "fail_first_test_raw_octets",
            "fail_first_test_raw_sha256",
            "implementation_dependent_skipped",
            "implementation_paths_absent_at_acceptance",
            "intended_missing_path_failed",
            "next_subgate_at_acceptance",
            "ordered_failure_codes",
            "ordered_implementation_paths",
            "passing_selection_deselected",
            "unexpected_failed",
        },
        "S1-A4 fail-first snapshot members differ",
    )
    _require(
        IMPLEMENTATION_FAIL_FIRST_TEST_PATH.is_file()
        and not IMPLEMENTATION_FAIL_FIRST_TEST_PATH.is_symlink(),
        "S1-A4 fail-first test is absent",
    )
    raw = IMPLEMENTATION_FAIL_FIRST_TEST_PATH.read_bytes()
    _require(
        len(raw) == snapshot["fail_first_test_raw_octets"],
        "S1-A4 fail-first test size drifted",
    )
    _require(
        _sha256(raw) == snapshot["fail_first_test_raw_sha256"],
        "S1-A4 fail-first test hash drifted",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 fail-first boundary identity differs",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    role_rows = boundary["implementation_role_contract"]["ordered_role_records"]
    expected_paths = [row["repository_relative_path"] for row in role_rows]
    expected_codes = [
        "A4_T_INDEPENDENT_VERIFIER_MISSING",
        "A4_T_SEPARATE_PRODUCER_MISSING",
        "A4_T_PARENT_PILOT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_implementation_paths"] == expected_paths,
        "S1-A4 fail-first implementation paths differ",
    )
    _require(
        snapshot["ordered_failure_codes"] == expected_codes,
        "S1-A4 fail-first failure codes differ",
    )
    _require(
        snapshot["contract_hostile_passed"] == 50,
        "S1-A4 fail-first passing count differs",
    )
    _require(
        snapshot["implementation_dependent_skipped"] == 11,
        "S1-A4 fail-first skipped count differs",
    )
    _require(
        snapshot["intended_missing_path_failed"]
        == snapshot["passing_selection_deselected"]
        == 3,
        "S1-A4 fail-first missing-path count differs",
    )
    _require(snapshot["unexpected_failed"] == 0, "S1-A4 fail-first has failures")
    _require(
        snapshot["next_subgate_at_acceptance"] == "A4-V",
        "S1-A4 accepted fail-first next sub-gate differs",
    )
    _require(
        snapshot["implementation_paths_absent_at_acceptance"] is True,
        "S1-A4 fail-first acceptance absence state differs",
    )
    source = raw.decode("utf-8", errors="strict")
    for code, path, row in zip(expected_codes, expected_paths, role_rows, strict=True):
        _require(code in source, f"S1-A4 fail-first code is absent: {code}")
        _require(path in source, f"S1-A4 fail-first path is absent: {path}")
        _require(
            row["source_marker"] in source,
            f"S1-A4 fail-first source marker is absent: {path}",
        )
    for test_name in (
        "test_verifier_accepts_independent_legal_case5_attainer",
        "test_verifier_rejects_hostile_candidate_without_output",
        "test_producer_emits_only_the_legal_case5_candidate",
    ):
        _require(test_name in source, f"S1-A4 functional target is absent: {test_name}")


def _validate_s1_a4_verifier_snapshot(
    snapshot: dict[str, Any], boundary_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_at_acceptance_intended_failed",
            "a4_t_at_acceptance_passed",
            "a4_t_at_acceptance_skipped",
            "accepted_case_position",
            "case5_expected_maximum_octets",
            "case5_resource_vector_sha256",
            "case5_stream_sha256",
            "constructive_boundary_id",
            "focused_passed",
            "next_subgate_at_acceptance",
            "ordered_remaining_failure_codes_at_acceptance",
            "ordered_remaining_implementation_paths_at_acceptance",
            "source_marker",
            "successor_paths_absent_at_acceptance",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 verifier boundary identity differs",
    )
    _require(
        snapshot["verifier_raw_octets"] == 94_839,
        "S1-A4 verifier historical size drifted",
    )
    _require(
        snapshot["verifier_raw_sha256"]
        == "bd81e47b0c07dc82f28a8d02e536329446267290c4e0e41c6e5fb96fd5c356a7",
        "S1-A4 verifier hash drifted",
    )
    _require(
        INDEPENDENT_VERIFIER_TEST_PATH.is_file()
        and not INDEPENDENT_VERIFIER_TEST_PATH.is_symlink(),
        "S1-A4 verifier test is absent",
    )
    verifier_test_raw = INDEPENDENT_VERIFIER_TEST_PATH.read_bytes()
    _require(
        len(verifier_test_raw) == snapshot["verifier_test_raw_octets"],
        "S1-A4 verifier test size drifted",
    )
    _require(
        _sha256(verifier_test_raw) == snapshot["verifier_test_raw_sha256"],
        "S1-A4 verifier test hash drifted",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    roles = boundary["implementation_role_contract"]["ordered_role_records"]
    verifier_role = roles[0]
    _require(
        verifier_role["role_name"] == "INDEPENDENT_VERIFIER"
        and ROOT / verifier_role["repository_relative_path"]
        == INDEPENDENT_VERIFIER_PATH
        and verifier_role["source_marker"] == snapshot["source_marker"],
        "S1-A4 verifier role binding differs",
    )
    verifier_source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    _require(
        snapshot["source_marker"] in verifier_source,
        "S1-A4 verifier source marker is absent",
    )
    remaining_paths = [row["repository_relative_path"] for row in roles[1:]]
    remaining_codes = [
        "A4_T_SEPARATE_PRODUCER_MISSING",
        "A4_T_PARENT_PILOT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_remaining_implementation_paths_at_acceptance"]
        == remaining_paths,
        "S1-A4 verifier remaining implementation paths differ",
    )
    _require(
        snapshot["ordered_remaining_failure_codes_at_acceptance"] == remaining_codes,
        "S1-A4 verifier remaining failure codes differ",
    )
    _require(
        snapshot["successor_paths_absent_at_acceptance"] is True,
        "S1-A4 verifier historical successor state differs",
    )
    _require(
        snapshot["accepted_case_position"] == 5
        and snapshot["case5_expected_maximum_octets"] == 29,
        "S1-A4 verifier case-5 scope differs",
    )
    expected_vector = [
        1,
        3,
        4,
        8,
        8,
        0,
        4,
        2684,
        8104,
        10384,
        33573,
        0,
        0,
        0,
        3,
        3,
        3783,
        1359,
    ]
    _require(
        snapshot["case5_resource_vector_sha256"]
        == _sha256(_canonical_bytes(expected_vector)),
        "S1-A4 verifier case-5 resource vector differs",
    )
    _require(
        snapshot["case5_stream_sha256"]
        == "79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314",
        "S1-A4 verifier case-5 stream differs",
    )
    _require(snapshot["focused_passed"] == 12, "S1-A4 verifier focused count differs")
    _require(
        snapshot["a4_t_at_acceptance_passed"] == 57
        and snapshot["a4_t_at_acceptance_skipped"] == 5
        and snapshot["a4_t_at_acceptance_intended_failed"] == 2,
        "S1-A4 verifier A4-T transition counts differ",
    )
    _require(
        snapshot["next_subgate_at_acceptance"] == "A4-P",
        "S1-A4 verifier next sub-gate differs",
    )


def _validate_s1_a4_producer_snapshot(
    snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_current_intended_failed",
            "a4_t_current_passed",
            "a4_t_current_skipped",
            "a4_t_filtered_deselected",
            "a4_t_filtered_passed",
            "a4_t_filtered_skipped",
            "accepted_case_position",
            "candidate_raw_octets",
            "candidate_raw_sha256",
            "constructive_boundary_id",
            "constructive_candidate_id",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_failure_codes",
            "ordered_remaining_implementation_paths",
            "producer_raw_octets",
            "producer_raw_sha256",
            "producer_test_raw_octets",
            "producer_test_raw_sha256",
            "source_marker",
            "verifier_regression_passed",
        },
        "S1-A4 producer snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 producer boundary identity differs",
    )
    for label, path, octets, digest in (
        (
            "historical producer",
            HISTORICAL_SEPARATE_PRODUCER_PATH,
            snapshot["producer_raw_octets"],
            snapshot["producer_raw_sha256"],
        ),
        (
            "producer test",
            SEPARATE_PRODUCER_TEST_PATH,
            snapshot["producer_test_raw_octets"],
            snapshot["producer_test_raw_sha256"],
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 {label} hash drifted")

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    roles = boundary["implementation_role_contract"]["ordered_role_records"]
    producer_role = roles[1]
    _require(
        producer_role["role_name"] == "SEPARATE_PRODUCER"
        and ROOT / producer_role["repository_relative_path"] == SEPARATE_PRODUCER_PATH
        and producer_role["source_marker"] == snapshot["source_marker"],
        "S1-A4 producer role binding differs",
    )
    producer_source = HISTORICAL_SEPARATE_PRODUCER_PATH.read_text(encoding="utf-8")
    _require(
        snapshot["source_marker"] in producer_source,
        "S1-A4 producer source marker is absent",
    )
    _require(
        str(INDEPENDENT_VERIFIER_PATH.relative_to(ROOT)) not in producer_source,
        "S1-A4 producer references verifier source",
    )
    for forbidden in boundary["candidate_bundle_contract"][
        "forbidden_producer_claim_member_names"
    ]:
        _require(
            forbidden not in producer_source,
            f"S1-A4 producer contains verifier-owned field: {forbidden}",
        )
    verifier_stat = INDEPENDENT_VERIFIER_PATH.stat()
    producer_stat = HISTORICAL_SEPARATE_PRODUCER_PATH.stat()
    _require(
        (verifier_stat.st_dev, verifier_stat.st_ino)
        != (producer_stat.st_dev, producer_stat.st_ino),
        "S1-A4 verifier and producer share one file",
    )

    runner_role = roles[2]
    expected_remaining_paths = [runner_role["repository_relative_path"]]
    _require(
        snapshot["ordered_remaining_implementation_paths"] == expected_remaining_paths,
        "S1-A4 producer remaining implementation paths differ",
    )
    _require(
        snapshot["ordered_remaining_failure_codes"]
        == ["A4_T_PARENT_PILOT_RUNNER_MISSING"],
        "S1-A4 producer remaining failure codes differ",
    )
    _require(
        ROOT / runner_role["repository_relative_path"] == PARENT_PILOT_RUNNER_PATH,
        "S1-A4 historical producer runner path differs",
    )

    seed = json.loads(CATALOG_PATH.read_bytes())
    manifest = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())
    case = next(
        row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
        if row["case_position"] == 5
    )
    plan = next(
        row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
        if row["case_position"] == 5
    )
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    candidate: dict[str, Any] = {
        "candidate_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": 5,
        "case_kind": case["case_kind"],
        "case_binding": case["case_binding"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": {"kind": "BOOL", "value": False},
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    candidate["constructive_candidate_id"] = _sha256(
        _canonical_bytes(
            {"domain": schema["identity_domain"], "payload": identity_payload}
        )
    )
    candidate_raw = _pretty_bytes(candidate)
    _require(
        snapshot["accepted_case_position"] == 5,
        "S1-A4 producer accepted case differs",
    )
    _require(
        snapshot["constructive_candidate_id"] == candidate["constructive_candidate_id"],
        "S1-A4 producer candidate identity differs",
    )
    _require(
        snapshot["candidate_raw_octets"] == len(candidate_raw),
        "S1-A4 producer candidate size differs",
    )
    _require(
        snapshot["candidate_raw_sha256"] == _sha256(candidate_raw),
        "S1-A4 producer candidate hash differs",
    )
    _require(snapshot["focused_passed"] == 20, "S1-A4 producer focused count differs")
    _require(
        snapshot["verifier_regression_passed"] == 12,
        "S1-A4 producer verifier regression count differs",
    )
    _require(
        snapshot["a4_t_current_passed"] == 61
        and snapshot["a4_t_current_skipped"] == 2
        and snapshot["a4_t_current_intended_failed"] == 1,
        "S1-A4 producer A4-T transition counts differ",
    )
    _require(
        snapshot["a4_t_filtered_passed"] == 59
        and snapshot["a4_t_filtered_skipped"] == 2
        and snapshot["a4_t_filtered_deselected"] == 3,
        "S1-A4 producer filtered A4-T counts differ",
    )
    _require(
        snapshot["next_subgate"] == "A4-P6", "S1-A4 producer next sub-gate differs"
    )
    test_source = SEPARATE_PRODUCER_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_producer_emits_exact_closed_case5_bundle",
        "test_independent_verifier_accepts_producer_bytes_without_mutating_them",
        "test_producer_rejects_authority_substitution_and_link_aliases",
    ):
        _require(
            test_name in test_source, f"S1-A4 producer test is absent: {test_name}"
        )


def _validate_s1_a4_six_case_target_snapshot(
    snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
    producer_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "accepted_control_case_position",
            "constructive_boundary_id",
            "contract_and_case5_control_passed",
            "existing_pair_unmodified_at_acceptance",
            "fail_first_test_raw_octets",
            "fail_first_test_raw_sha256",
            "implementation_dependent_skipped",
            "intended_failed",
            "next_subgate",
            "ordered_case_positions",
            "ordered_failure_codes",
            "ordered_remaining_pipeline_case_positions",
            "passing_selection_deselected",
            "runner_absent_at_acceptance",
            "runner_path",
            "unexpected_failed",
        },
        "S1-A4 six-case target snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 six-case target boundary identity differs",
    )
    _require(
        SIX_CASE_QUALIFICATION_TEST_PATH.is_file()
        and not SIX_CASE_QUALIFICATION_TEST_PATH.is_symlink(),
        "S1-A4 six-case target is absent",
    )
    raw = SIX_CASE_QUALIFICATION_TEST_PATH.read_bytes()
    _require(
        len(raw) == snapshot["fail_first_test_raw_octets"],
        "S1-A4 six-case target size drifted",
    )
    _require(
        _sha256(raw) == snapshot["fail_first_test_raw_sha256"],
        "S1-A4 six-case target hash drifted",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    case_positions = [
        row["case_position"]
        for row in boundary["pilot_contract"]["ordered_pilot_case_records"]
    ]
    _require(
        snapshot["ordered_case_positions"]
        == case_positions
        == [5, 24, 54, 69, 435, 475],
        "S1-A4 six-case target case order differs",
    )
    _require(
        snapshot["accepted_control_case_position"]
        == producer_snapshot["accepted_case_position"]
        == 5,
        "S1-A4 six-case target control case differs",
    )
    remaining = case_positions[1:]
    _require(
        snapshot["ordered_remaining_pipeline_case_positions"] == remaining,
        "S1-A4 six-case target remaining case order differs",
    )
    expected_codes = [
        *(f"A4_P6_CASE_{position}_PRODUCER_NOT_QUALIFIED" for position in remaining),
        "A4_P6_PARENT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_failure_codes"] == expected_codes,
        "S1-A4 six-case target failure codes differ",
    )
    _require(
        snapshot["contract_and_case5_control_passed"] == 13
        and snapshot["implementation_dependent_skipped"] == 2
        and snapshot["intended_failed"] == 6
        and snapshot["passing_selection_deselected"] == 6
        and snapshot["unexpected_failed"] == 0,
        "S1-A4 six-case target test counts differ",
    )
    runner_relative = str(PARENT_PILOT_RUNNER_PATH.relative_to(ROOT))
    _require(
        snapshot["runner_path"] == runner_relative,
        "S1-A4 six-case target runner path differs",
    )
    _require(
        snapshot["runner_absent_at_acceptance"] is True,
        "S1-A4 six-case target runner acceptance state differs",
    )
    _require(
        snapshot["existing_pair_unmodified_at_acceptance"] is True,
        "S1-A4 six-case target existing-pair state differs",
    )
    _require(
        snapshot["next_subgate"] == "A4-P6-V",
        "S1-A4 six-case target next sub-gate differs",
    )

    source = raw.decode("utf-8", errors="strict")
    for test_name in (
        "test_f2_limits_are_exact_immutable_and_complete",
        "test_candidate_oracle_rejects_hostile_resealed_fixtures",
        "test_case5_pipeline_control_remains_exact_deterministic_and_immutable",
        "test_remaining_pilot_pipeline_is_exact_deterministic_and_candidate_immutable",
        "test_parent_runner_emits_exact_two_run_all_or_nothing_pilot",
    ):
        _require(
            test_name in source,
            f"S1-A4 six-case qualification target is absent: {test_name}",
        )


def _validate_s1_a4_case435_attainability_falsification_snapshot(
    snapshot: dict[str, Any],
    six_case_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "analysis_version",
        "attainability_analysis_id",
        "case_position",
        "constraint_scope_profile_id",
        "constructed_superset_canonical_sha256",
        "context_structural_superset_canonical_octets",
        "derived_legal_domain_superset_upper_bound_octets",
        "field_array_syntax_octets",
        "field_superset_upper_bound_sum_octets",
        "inventory_raw_sha256",
        "logical_count_plan_id",
        "measured_sequence_ordinal",
        "observation_fixed_nonfield_octets",
        "ordered_field_superset_bound_vector_sha256",
        "p2_structural_upper_bound_octets",
        "p3_equality_possible",
        "p3_unattainable_gap_octets",
        "registry_raw_sha256",
        "seed_raw_sha256",
        "target_field_count",
        "target_type_name",
    }
    control_members = {
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "correction_subgate",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 case-435 falsification snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "attainability analyzer",
            CASE435_ATTAINABILITY_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "attainability test",
            CASE435_ATTAINABILITY_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 case-435 {label} is absent",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == snapshot[octet_member],
            f"S1-A4 case-435 {label} size drifted",
        )
        _require(
            _sha256(raw) == snapshot[hash_member],
            f"S1-A4 case-435 {label} hash drifted",
        )

    analyzer = _load_case435_attainability_analyzer()
    actual_report = analyzer.analyze(ROOT)
    expected_report = {name: snapshot[name] for name in report_members}
    _require(
        actual_report == expected_report,
        "S1-A4 case-435 attainability report drifted",
    )
    _require(
        snapshot["case_position"]
        in six_case_snapshot["ordered_remaining_pipeline_case_positions"],
        "S1-A4 case-435 falsification is outside the frozen pilot",
    )
    _require(
        snapshot["seed_raw_sha256"] == seed_snapshot["catalog_sha256"],
        "S1-A4 case-435 falsification seed identity differs",
    )
    _require(
        snapshot["field_superset_upper_bound_sum_octets"]
        + snapshot["field_array_syntax_octets"]
        + snapshot["observation_fixed_nonfield_octets"]
        == snapshot["derived_legal_domain_superset_upper_bound_octets"],
        "S1-A4 case-435 falsification decomposition differs",
    )
    _require(
        snapshot["derived_legal_domain_superset_upper_bound_octets"]
        + snapshot["p3_unattainable_gap_octets"]
        == snapshot["p2_structural_upper_bound_octets"],
        "S1-A4 case-435 falsification gap differs",
    )
    _require(
        snapshot["p3_equality_possible"] is False
        and snapshot["p3_unattainable_gap_octets"] == 1_234,
        "S1-A4 case-435 P3 falsification differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435"
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 correction disposition differs",
    )
    test_source = CASE435_ATTAINABILITY_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_authority_complete_superset_falsifies_frozen_p3_endpoint",
        "test_case435_checker_is_independent_of_producer_verifier_and_legacy_v1",
        "test_case435_falsification_is_stronger_than_a_failed_candidate_search",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 attainability test is absent: {test_name}",
        )


def _validate_s1_a4_profile_attainability_scope_snapshot(
    snapshot: dict[str, Any],
    case435_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "affected_case_position_vector_sha256",
        "affected_profile_id_vector_sha256",
        "affected_profile_record_vector_sha256",
        "affected_program_id_vector_sha256",
        "affected_publication_case_maximum",
        "affected_publication_case_minimum",
        "application_aware_exact_program_count",
        "application_aware_exact_scope_case_count",
        "audit_version",
        "case435_is_affected",
        "current_catalog_satisfies_application_aware_exactness",
        "exact_control_case_position",
        "inventory_raw_sha256",
        "logical_plan_recipe_catalog_id",
        "p1_p3_exact_equality_program_count",
        "profile_attainability_scope_audit_id",
        "profile_program_count",
        "profile_scope_case_count",
        "required_disposition",
        "seed_catalog_id",
        "seed_raw_sha256",
        "selected_correction_contract_id",
        "structural_superset_application_invocation_count",
        "structural_superset_cross_rule_evaluation_count",
        "structural_superset_deleted_cross_application_count",
        "structural_superset_direct_cross_expression_node_count",
        "structural_superset_program_count",
        "structural_superset_scope_case_count",
        "structural_superset_selector_absent_scope_case_count",
        "structural_superset_selector_present_scope_case_count",
    }
    control_members = {
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "correction_subgate",
        "design_doc_raw_octets",
        "design_doc_raw_sha256",
        "focused_passed",
        "next_subgate",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 profile-attainability scope snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "profile-attainability analyzer",
            PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "profile-attainability test",
            PROFILE_ATTAINABILITY_SCOPE_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
        (
            "profile-attainability design",
            PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH,
            "design_doc_raw_octets",
            "design_doc_raw_sha256",
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    analyzer = _load_profile_attainability_scope_analyzer()
    actual = analyzer.analyze(ROOT)
    expected = {name: snapshot[name] for name in report_members}
    _require(
        {name: actual[name] for name in report_members} == expected,
        "S1-A4 profile-attainability scope report drifted",
    )
    _require(
        actual["selected_correction_contract"] == analyzer.CORRECTION_CONTRACT,
        "S1-A4 profile-attainability correction contract drifted",
    )
    correction = actual["selected_correction_contract"]
    _require(
        correction["upper_bound_channel"]["result_kind"] == "PROVED_LEGAL_UPPER_BOUND"
        and correction["attainment_channel"]["result_kind"]
        == "INDEPENDENT_LEGAL_ATTAINMENT"
        and correction["exactness_join"]["success_result_kind"]
        == "EXACT_ATTAINED_MAXIMUM"
        and correction["exactness_join"]["superset_join_policy"] == "FORBIDDEN",
        "S1-A4 profile-attainability three-channel contract differs",
    )
    _require(
        snapshot["seed_raw_sha256"]
        == case435_snapshot["seed_raw_sha256"]
        == seed_snapshot["catalog_sha256"],
        "S1-A4 profile-attainability seed identity differs",
    )
    _require(
        snapshot["inventory_raw_sha256"] == case435_snapshot["inventory_raw_sha256"],
        "S1-A4 profile-attainability inventory identity differs",
    )
    _require(
        snapshot["profile_program_count"]
        == snapshot["p1_p3_exact_equality_program_count"]
        == 408
        and snapshot["profile_scope_case_count"] == 475,
        "S1-A4 profile-attainability universe differs",
    )
    _require(
        snapshot["structural_superset_program_count"] == 407
        and snapshot["structural_superset_scope_case_count"] == 474
        and snapshot["application_aware_exact_program_count"] == 1
        and snapshot["application_aware_exact_scope_case_count"] == 1
        and snapshot["exact_control_case_position"] == 69,
        "S1-A4 profile-attainability strategy census differs",
    )
    _require(
        snapshot["case435_is_affected"] is True
        and snapshot["current_catalog_satisfies_application_aware_exactness"] is False,
        "S1-A4 profile-attainability fail-first state differs",
    )
    _require(
        snapshot["structural_superset_selector_present_scope_case_count"]
        + snapshot["structural_superset_selector_absent_scope_case_count"]
        == snapshot["structural_superset_scope_case_count"],
        "S1-A4 profile-attainability selector partition differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435-A"
        and snapshot["next_subgate"] == "A4-P6-C435-B"
        and snapshot["verifier_expansion_state"] == "HOLD"
        and snapshot["focused_passed"] == 10,
        "S1-A4 profile-attainability disposition differs",
    )
    test_source = PROFILE_ATTAINABILITY_SCOPE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_scope_audit_freezes_every_structural_p2_equality_surface",
        "test_scope_audit_is_independent_of_generator_runtime_and_candidate_pair",
        "test_fail_first_exactness_boundary_rejects_current_catalog",
        "test_scope_audit_rejects_structural_p2_disguised_as_exact",
        "test_scope_audit_rejects_weakened_p1_p3_equality",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 profile-attainability test is absent: {test_name}",
        )
    design = PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-A",
        snapshot["profile_attainability_scope_audit_id"],
        snapshot["selected_correction_contract_id"],
        "A4-P6-C435-B",
    ):
        _require(
            marker in design,
            f"S1-A4 profile-attainability design marker absent: {marker}",
        )


def _validate_s1_a4_case435_dependency_closure_snapshot(
    snapshot: dict[str, Any],
    profile_scope_snapshot: dict[str, Any],
    case435_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "a1_coupled_field_count",
        "audit_version",
        "case435_dependency_closure_audit_id",
        "complex_operator_count",
        "conditional_component_count",
        "conditional_factorization_proved",
        "correction_subgate",
        "dependency_closure_complete",
        "exact_case435_maximum_derived",
        "field_count",
        "legal_case435_attainer_constructed",
        "next_subgate",
        "ordinary_singleton_component_count",
        "required_disposition",
        "runtime_constant_closure_count",
        "runtime_function_closure_count",
        "schema_closure_intrinsic_rule_count",
        "schema_closure_type_count",
        "schema_closure_value_schema_count",
        "selected_cross_rule_count",
        "selected_rule_count",
        "selected_rule_expression_node_count",
        "unconditional_factorization_rejected",
        "verifier_expansion_state",
    }
    control_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "case435_conditional_factorization_proof_id",
        "case435_dependency_manifest_id",
        "focused_passed",
        "microdomain_brute_force_legal_tuple_count",
        "microdomain_exact_maximum",
        "runtime_constant_ast_vector_sha256",
        "runtime_function_ast_vector_sha256",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 case-435 dependency-closure snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 dependency-closure analyzer",
            CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "case-435 dependency-closure test",
            CASE435_DEPENDENCY_CLOSURE_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
        (
            "case-435 dependency-closure acceptance",
            CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    analyzer = _load_case435_dependency_closure_analyzer()
    actual = analyzer.analyze(ROOT)
    expected = {name: snapshot[name] for name in report_members}
    _require(
        {name: actual[name] for name in report_members} == expected,
        "S1-A4 case-435 dependency-closure report drifted",
    )
    manifest = actual["case435_dependency_manifest"]
    proof = actual["case435_conditional_factorization_proof"]
    microdomain = actual["microdomain_factorization_check"]
    _require(
        manifest["case435_dependency_manifest_id"]
        == snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 dependency-manifest identity differs",
    )
    _require(
        proof["case435_conditional_factorization_proof_id"]
        == snapshot["case435_conditional_factorization_proof_id"],
        "S1-A4 case-435 factorization-proof identity differs",
    )
    source_closure = manifest["runtime_source_closure"]
    _require(
        source_closure["function_ast_vector_sha256"]
        == snapshot["runtime_function_ast_vector_sha256"]
        and source_closure["constant_ast_vector_sha256"]
        == snapshot["runtime_constant_ast_vector_sha256"],
        "S1-A4 case-435 runtime AST closure differs",
    )
    _require(
        microdomain["brute_force_legal_tuple_count"]
        == snapshot["microdomain_brute_force_legal_tuple_count"]
        == 16
        and microdomain["brute_force_maximum"]
        == microdomain["factorized_maximum"]
        == snapshot["microdomain_exact_maximum"]
        == 29,
        "S1-A4 case-435 microdomain equivalence differs",
    )
    _require(
        manifest["global_codec_constraint"]["accepted_superset_analysis_id"]
        == case435_snapshot["attainability_analysis_id"],
        "S1-A4 case-435 dependency/falsification join differs",
    )
    _require(
        manifest["authority_sha256_by_path"][analyzer.SEED_RELATIVE_PATH]
        == profile_scope_snapshot["seed_raw_sha256"]
        and manifest["authority_sha256_by_path"][analyzer.INVENTORY_RELATIVE_PATH]
        == profile_scope_snapshot["inventory_raw_sha256"],
        "S1-A4 case-435 dependency/profile authority join differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435-B"
        and snapshot["next_subgate"] == "A4-P6-C435-C1"
        and snapshot["focused_passed"] == 12
        and snapshot["dependency_closure_complete"] is True
        and snapshot["conditional_factorization_proved"] is True
        and snapshot["unconditional_factorization_rejected"] is True
        and snapshot["exact_case435_maximum_derived"] is False
        and snapshot["legal_case435_attainer_constructed"] is False
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 dependency-closure disposition differs",
    )
    test_source = CASE435_DEPENDENCY_CLOSURE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_dependency_closure_freezes_complete_conditional_graph",
        "test_case435_dependency_closure_independently_reconstructs_schedule_and_types",
        "test_case435_dependency_manifest_rejects_operator_contract_weakening",
        "test_case435_factorization_proof_rejects_premature_maximum_claim",
        "test_case435_dependency_closure_rejects_runtime_source_drift",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 dependency-closure test is absent: {test_name}",
        )
    acceptance = CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-B",
        snapshot["case435_dependency_closure_audit_id"],
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_conditional_factorization_proof_id"],
        "A4-P6-C435-C1",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 dependency acceptance marker absent: {marker}",
        )


def _validate_s1_a4_case435_upper_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "a1_legal_reduced_tuple_count",
        "a1_maximum_component_canonical_octets",
        "a1_reduced_cartesian_tuple_count",
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "broad_reduced_candidate_count",
        "case435_dependency_manifest_id",
        "case435_upper_certificate_id",
        "certificate_version",
        "checker_raw_octets",
        "checker_raw_sha256",
        "context_canonical_octets",
        "correction_subgate",
        "exact_upper_bound_octets",
        "exact_upper_bound_proved",
        "field_count",
        "field_maximum_sum_octets",
        "focused_passed",
        "independent_attainer_accepted",
        "legal_reduced_candidate_count",
        "maximizing_observation_canonical_sha256",
        "maximizing_observation_id",
        "next_subgate",
        "ordinary_singleton_component_count",
        "separator_branch_count",
        "separator_observation_octet_vector",
        "separator_root_id",
        "solver_raw_octets",
        "solver_raw_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 exact-upper snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 exact-upper solver",
            CASE435_UPPER_SOLVER_PATH,
            "solver_raw_octets",
            "solver_raw_sha256",
        ),
        (
            "case-435 upper-certificate checker",
            CASE435_UPPER_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 upper-certificate test",
            CASE435_UPPER_CERTIFICATE_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 exact-upper acceptance",
            CASE435_UPPER_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    solver = _load_case435_upper_solver()
    checker = _load_case435_upper_certificate_checker()
    _require(
        solver.PINNED_SHA256 == checker.PINNED_SHA256,
        "S1-A4 case-435 upper authority sets differ",
    )
    try:
        certificate = solver.solve(ROOT)
        verification = checker.verify(ROOT, _canonical_bytes(certificate))
    except (solver.UpperBoundError, checker.CertificateError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 exact-upper replay failed: {error}"
        ) from error

    fields = certificate["ordered_field_maximum_records"]
    reduction = certificate["finite_domain_reduction"]
    composition = certificate["canonical_composition"]
    a1 = certificate["a1_component_certificate"]
    branches = certificate["ordered_separator_branch_bound_records"]
    feasibility = certificate["separator_feasibility_certificate"]
    actual = {
        "certificate_version": certificate["certificate_version"],
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "case435_upper_certificate_id": certificate["case435_upper_certificate_id"],
        "exact_upper_bound_octets": certificate["exact_upper_bound_octets"],
        "exact_upper_bound_proved": certificate["exact_upper_bound_proved"],
        "independent_attainer_accepted": certificate["independent_attainer_accepted"],
        "acceptance_state": certificate["acceptance_state"],
        "correction_subgate": certificate["correction_subgate"],
        "next_subgate": certificate["next_subgate"],
        "field_count": len(fields),
        "ordinary_singleton_component_count": reduction[
            "ordinary_singleton_component_count"
        ],
        "broad_reduced_candidate_count": sum(
            row["reduced_candidate_count"] for row in fields
        ),
        "legal_reduced_candidate_count": sum(
            row["legal_reduced_candidate_count"] for row in fields
        ),
        "a1_reduced_cartesian_tuple_count": a1["reduced_cartesian_tuple_count"],
        "a1_legal_reduced_tuple_count": a1["legal_reduced_tuple_count"],
        "a1_maximum_component_canonical_octets": a1[
            "maximum_component_canonical_octets"
        ],
        "context_canonical_octets": composition["context_canonical_octets"],
        "field_maximum_sum_octets": composition["field_maximum_sum_octets"],
        "maximizing_observation_id": composition["maximizing_observation_id"],
        "maximizing_observation_canonical_sha256": composition[
            "maximizing_observation_canonical_sha256"
        ],
        "separator_branch_count": len(branches),
        "separator_observation_octet_vector": [
            row["observation_canonical_octets"] for row in branches
        ],
        "separator_root_id": feasibility["root_id"],
    }
    expected = {name: snapshot[name] for name in actual}
    _require(actual == expected, "S1-A4 case-435 exact-upper result drifted")
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 upper/dependency manifest join differs",
    )
    _require(
        certificate["authority_sha256_by_path"][solver.DEPENDENCY_ANALYZER_PATH]
        == dependency_snapshot["analyzer_raw_sha256"],
        "S1-A4 case-435 upper/dependency source join differs",
    )
    _require(
        composition["fixed_noncontext_nonfield_octets"]
        + composition["context_canonical_octets"]
        + composition["field_array_bracket_octets"]
        + composition["field_array_comma_octets"]
        + composition["field_maximum_sum_octets"]
        == composition["exact_upper_bound_octets"]
        == snapshot["exact_upper_bound_octets"],
        "S1-A4 case-435 exact-upper composition differs",
    )
    _require(
        max(snapshot["separator_observation_octet_vector"])
        == snapshot["exact_upper_bound_octets"]
        and snapshot["separator_observation_octet_vector"]
        == [257_887, 188_317, 188_317, 188_506, 189_077],
        "S1-A4 case-435 separator maximum differs",
    )
    _require(
        verification
        == {
            "verification_version": (
                "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
                "case435_upper_certificate_verification.v1"
            ),
            "case435_upper_certificate_id": snapshot["case435_upper_certificate_id"],
            "exact_upper_bound_octets": snapshot["exact_upper_bound_octets"],
            "field_count": snapshot["field_count"],
            "separator_branch_count": snapshot["separator_branch_count"],
            "legal_reduced_candidate_count": snapshot["legal_reduced_candidate_count"],
            "legal_a1_tuple_count": snapshot["a1_legal_reduced_tuple_count"],
            "independent_attainer_accepted": False,
            "next_subgate": "A4-P6-C435-C2",
        },
        "S1-A4 case-435 upper-certificate verification differs",
    )
    _require(
        snapshot["focused_passed"] == 17
        and snapshot["exact_upper_bound_proved"] is True
        and snapshot["independent_attainer_accepted"] is False
        and snapshot["acceptance_state"]
        == "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING"
        and snapshot["correction_subgate"] == "A4-P6-C435-C1"
        and snapshot["next_subgate"] == "A4-P6-C435-C2"
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 exact-upper disposition differs",
    )
    test_source = CASE435_UPPER_CERTIFICATE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_solver_freezes_exact_upper_certificate",
        "test_case435_independent_checker_reconstructs_solver_certificate",
        "test_case435_solver_and_checker_are_separate_standard_library_programs",
        "test_case435_checker_rejects_resealed_semantic_mutations",
        "test_case435_checker_rejects_authority_drift",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 exact-upper test is absent: {test_name}",
        )
    acceptance = CASE435_UPPER_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C1",
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_upper_certificate_id"],
        f"{snapshot['exact_upper_bound_octets']:,}",
        "independent_attainer_accepted = false",
        "A4-P6-C435-C2",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 exact-upper acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_attainer_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "a1_cartesian_tuple_count",
        "a1_legal_tuple_count",
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "attainer_certificate_id",
        "attainer_certificate_version",
        "case435_dependency_manifest_id",
        "checker_raw_octets",
        "checker_raw_sha256",
        "constructor_raw_octets",
        "constructor_raw_sha256",
        "correction_subgate",
        "exactness_claimed",
        "external_upper_channel_imported",
        "field_count",
        "field_canonical_octet_sum",
        "focused_passed",
        "legal_attainer_constructed",
        "measured_attainer_canonical_octets",
        "measured_attainer_canonical_sha256",
        "measured_attainer_observation_id",
        "measured_observation_sequence_position",
        "next_subgate",
        "ordered_observation_id_vector_sha256",
        "p1_application_invocation_count",
        "p1_direct_expression_node_count",
        "p1_legal",
        "p1_receipt_vector_sha256",
        "p1_rule_evaluation_count",
        "precomputed_witness_imported",
        "root_canonical_sha256",
        "root_id",
        "test_raw_octets",
        "test_raw_sha256",
        "total_field_proposal_count",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 attainer snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 attainer constructor",
            CASE435_ATTAINER_CONSTRUCTOR_PATH,
            "constructor_raw_octets",
            "constructor_raw_sha256",
        ),
        (
            "case-435 attainer-certificate checker",
            CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 attainer-certificate test",
            CASE435_ATTAINER_CERTIFICATE_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 attainer acceptance",
            CASE435_ATTAINER_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "a1_cartesian_tuple_count": 10_164,
        "a1_legal_tuple_count": 9_989,
        "acceptance_state": "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING",
        "attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "attainer_certificate_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_attainer_certificate.v1"
        ),
        "case435_dependency_manifest_id": (
            "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
        ),
        "correction_subgate": "A4-P6-C435-C2",
        "exactness_claimed": False,
        "external_upper_channel_imported": False,
        "field_count": 185,
        "field_canonical_octet_sum": 255_532,
        "focused_passed": 17,
        "legal_attainer_constructed": True,
        "measured_attainer_canonical_octets": 257_887,
        "measured_attainer_canonical_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "measured_attainer_observation_id": (
            "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9"
        ),
        "measured_observation_sequence_position": 65,
        "next_subgate": "A4-P6-C435-C3",
        "ordered_observation_id_vector_sha256": (
            "6125c0b00f817fd1593013a547f24da965110b27fceaa70762b5ede43811c80c"
        ),
        "p1_application_invocation_count": 137,
        "p1_direct_expression_node_count": 125_431,
        "p1_legal": True,
        "p1_receipt_vector_sha256": (
            "71e39e33ccf923fb922d73336a4afba96051b741d1da5b3fc16af0b0cb95c44b"
        ),
        "p1_rule_evaluation_count": 12_531,
        "precomputed_witness_imported": False,
        "root_canonical_sha256": (
            "aa682944ac87cdd7e4180347d285145a4b4d231a2246a3246a184ae4757a655d"
        ),
        "root_id": ("65bc6b241b3ad861443401d3b101ad0b6eab9108a4653cdeef86b6f8a03e9147"),
        "total_field_proposal_count": 3_144,
        "verifier_expansion_state": "HOLD",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 attainer result drifted",
    )
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 attainer/dependency manifest join differs",
    )

    constructor = _load_case435_attainer_constructor()
    checker = _load_case435_attainer_certificate_checker()
    _require(
        constructor.PINNED_SHA256 == checker.PINNED_SHA256,
        "S1-A4 case-435 attainer authority sets differ",
    )
    try:
        certificate = constructor.construct(ROOT)
        verification = checker.verify(ROOT, certificate)
    except (constructor.AttainerError, checker.CertificateError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 attainer replay failed: {error}"
        ) from error

    protocol = certificate["construction_protocol"]
    measurement = certificate["measured_attainer"]
    execution = certificate["p1_execution_certificate"]
    selected_fields = certificate["ordered_selected_field_witness_records"]
    actual = {
        "a1_cartesian_tuple_count": protocol["a1_cartesian_tuple_count"],
        "a1_legal_tuple_count": protocol["a1_legal_tuple_count"],
        "acceptance_state": certificate["acceptance_state"],
        "attainer_certificate_id": certificate["case435_attainer_certificate_id"],
        "attainer_certificate_version": certificate["attainer_certificate_version"],
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "correction_subgate": certificate["correction_subgate"],
        "exactness_claimed": certificate["exactness_claimed"],
        "external_upper_channel_imported": protocol["external_upper_channel_imported"],
        "field_count": len(selected_fields),
        "field_canonical_octet_sum": sum(
            row["selected_canonical_octets"] for row in selected_fields
        ),
        "legal_attainer_constructed": certificate["legal_attainer_constructed"],
        "measured_attainer_canonical_octets": measurement["canonical_octets"],
        "measured_attainer_canonical_sha256": measurement["canonical_sha256"],
        "measured_attainer_observation_id": measurement["observation_id"],
        "measured_observation_sequence_position": measurement[
            "observation_sequence_position"
        ],
        "next_subgate": certificate["next_subgate"],
        "ordered_observation_id_vector_sha256": measurement[
            "ordered_observation_id_vector_sha256"
        ],
        "p1_application_invocation_count": execution["application_invocation_count"],
        "p1_direct_expression_node_count": execution["direct_expression_node_count"],
        "p1_legal": certificate["p1_legal"],
        "p1_receipt_vector_sha256": execution["receipt_vector_sha256"],
        "p1_rule_evaluation_count": execution["charged_rule_evaluation_count"],
        "precomputed_witness_imported": protocol["precomputed_witness_imported"],
        "root_canonical_sha256": measurement["root_canonical_sha256"],
        "root_id": measurement["root_id"],
        "total_field_proposal_count": protocol["total_field_proposal_count"],
    }
    _require(
        actual == {name: snapshot[name] for name in actual},
        "S1-A4 case-435 attainer replay result differs",
    )
    _require(
        verification["case435_attainer_certificate_id"]
        == snapshot["attainer_certificate_id"]
        and verification["measured_attainer_canonical_octets"]
        == snapshot["measured_attainer_canonical_octets"]
        and verification["measured_attainer_canonical_sha256"]
        == snapshot["measured_attainer_canonical_sha256"]
        and verification["p1_application_invocation_count"]
        == snapshot["p1_application_invocation_count"]
        and verification["p1_rule_evaluation_count"]
        == snapshot["p1_rule_evaluation_count"]
        and verification["p1_direct_expression_node_count"]
        == snapshot["p1_direct_expression_node_count"]
        and verification["p1_legal"] is True
        and verification["exactness_claimed"] is False
        and verification["next_subgate"] == "A4-P6-C435-C3",
        "S1-A4 case-435 attainer verification differs",
    )
    test_source = CASE435_ATTAINER_CERTIFICATE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_constructor_emits_a_legal_nonexact_c2_certificate",
        "test_independent_checker_replays_complete_p1",
        "test_constructor_and_checker_do_not_import_or_embed_c1_results",
        "test_rejects_resealed_premature_exactness_claim",
        "test_rejects_resealed_receipt_vector_substitution",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 attainer test is absent: {test_name}",
        )
    acceptance = CASE435_ATTAINER_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C2",
        snapshot["case435_dependency_manifest_id"],
        snapshot["attainer_certificate_id"],
        f"{snapshot['measured_attainer_canonical_octets']:,}",
        "exactness_claimed = false",
        "A4-P6-C435-C3",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 attainer acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_exactness_join_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
    upper_snapshot: dict[str, Any],
    attainer_snapshot: dict[str, Any],
    upper_certificate: dict[str, Any],
    attainer_certificate: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "attainer_certificate_id",
        "attainer_observation_id",
        "attainer_observation_sha256",
        "canonicalization_binding_sha256",
        "case435_dependency_manifest_id",
        "case435_exactness_join_certificate_id",
        "case_binding_sha256",
        "channel_source_set_sha256",
        "checker_raw_octets",
        "checker_raw_sha256",
        "correction_subgate",
        "exact_maximum_octets",
        "exact_maximum_proved",
        "exactness_claimed",
        "focused_passed",
        "join_raw_octets",
        "join_raw_sha256",
        "join_version",
        "next_subgate",
        "ordered_application_instruction_sha256",
        "p1_application_invocation_count",
        "p1_direct_expression_node_count",
        "p1_rule_evaluation_count",
        "required_join_predicate_count",
        "schedule_authority_sha256",
        "shared_raw_authority_set_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "upper_certificate_id",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 exactness-join snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 exactness join",
            CASE435_EXACTNESS_JOIN_PATH,
            "join_raw_octets",
            "join_raw_sha256",
        ),
        (
            "case-435 exactness-certificate checker",
            CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 exactness-join test",
            CASE435_EXACTNESS_JOIN_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 exactness-join acceptance",
            CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "acceptance_state": "EXACT_MAXIMUM_PROVED_BY_BOUND_AND_LEGAL_ATTAINMENT",
        "attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "attainer_observation_id": (
            "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9"
        ),
        "attainer_observation_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "canonicalization_binding_sha256": (
            "e2e1b3068a5f48ae3eb9e8797010f4c5023c03e97d95025cc4f503aa4420ddb8"
        ),
        "case435_dependency_manifest_id": (
            "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
        ),
        "case435_exactness_join_certificate_id": (
            "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        ),
        "case_binding_sha256": (
            "136dafc839046d8071f7d245367faa5583de32209fcf9d0df09b1ab185fc22c4"
        ),
        "channel_source_set_sha256": (
            "55153bd86b25735de198f7a3d0baae6527ed0ed409bdd2dd7b6c12b2dc6a9b99"
        ),
        "correction_subgate": "A4-P6-C435-C3",
        "exact_maximum_octets": 257_887,
        "exact_maximum_proved": True,
        "exactness_claimed": True,
        "focused_passed": 16,
        "join_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_exactness_join.v1"
        ),
        "next_subgate": "A4-P6-C435-D",
        "ordered_application_instruction_sha256": (
            "08955976b1ad455a7e18068ae8d8affe1316f50a56cf50dafd95dc0e0331b20e"
        ),
        "p1_application_invocation_count": 137,
        "p1_direct_expression_node_count": 125_431,
        "p1_rule_evaluation_count": 12_531,
        "required_join_predicate_count": 8,
        "schedule_authority_sha256": (
            "7b5d72df8bea5f01beb0b3d4ecb4ffad5d2a301b32013b72ad02a5457215ae0e"
        ),
        "shared_raw_authority_set_sha256": (
            "0b565a74447d12c80f1fc8f7ce0c8ce9127fb58e155e2b3cbca3cef638a4c593"
        ),
        "upper_certificate_id": (
            "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
        ),
        "verifier_expansion_state": "HOLD",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 exactness-join result drifted",
    )
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 exactness/dependency manifest join differs",
    )
    _require(
        snapshot["upper_certificate_id"]
        == upper_snapshot["case435_upper_certificate_id"]
        and snapshot["exact_maximum_octets"]
        == upper_snapshot["exact_upper_bound_octets"],
        "S1-A4 case-435 exactness/upper channel join differs",
    )
    _require(
        snapshot["attainer_certificate_id"]
        == attainer_snapshot["attainer_certificate_id"]
        and snapshot["exact_maximum_octets"]
        == attainer_snapshot["measured_attainer_canonical_octets"]
        and snapshot["attainer_observation_id"]
        == attainer_snapshot["measured_attainer_observation_id"]
        and snapshot["attainer_observation_sha256"]
        == attainer_snapshot["measured_attainer_canonical_sha256"],
        "S1-A4 case-435 exactness/attainer channel join differs",
    )

    joiner = _load_case435_exactness_join()
    checker = _load_case435_exactness_certificate_checker()
    _require(
        joiner.RAW_AUTHORITY_SHA256 == checker.RAW_AUTHORITY_SHA256
        and joiner.CHANNEL_SOURCE_SHA256 == checker.CHANNEL_SOURCE_SHA256,
        "S1-A4 case-435 exactness authority sets differ",
    )
    try:
        certificate = joiner.join(ROOT, upper_certificate, attainer_certificate)
        verification = checker.verify(
            ROOT,
            upper_certificate,
            attainer_certificate,
            certificate,
        )
    except (joiner.JoinError, checker.ExactnessError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 exactness-join replay failed: {error}"
        ) from error

    schedule = certificate["schedule_authority"]
    upper_channel = certificate["upper_channel"]
    attainer_channel = certificate["attainer_channel"]
    actual = {
        "acceptance_state": certificate["acceptance_state"],
        "attainer_certificate_id": attainer_channel["certificate_id"],
        "attainer_observation_id": attainer_channel["measured_attainer_observation_id"],
        "attainer_observation_sha256": attainer_channel[
            "measured_attainer_canonical_sha256"
        ],
        "canonicalization_binding_sha256": _sha256(
            _canonical_bytes(certificate["canonicalization_binding"])
        ),
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "case435_exactness_join_certificate_id": certificate[
            "case435_exactness_join_certificate_id"
        ],
        "case_binding_sha256": _sha256(_canonical_bytes(certificate["case_binding"])),
        "channel_source_set_sha256": _sha256(
            _canonical_bytes(certificate["channel_source_sha256_by_path"])
        ),
        "correction_subgate": certificate["correction_subgate"],
        "exact_maximum_octets": certificate["exact_maximum_octets"],
        "exact_maximum_proved": certificate["exact_maximum_proved"],
        "exactness_claimed": certificate["exactness_claimed"],
        "join_version": certificate["exactness_join_version"],
        "next_subgate": certificate["next_subgate"],
        "ordered_application_instruction_sha256": schedule[
            "ordered_application_instruction_sha256"
        ],
        "p1_application_invocation_count": schedule["application_invocation_count"],
        "p1_direct_expression_node_count": schedule[
            "direct_cross_expression_node_count"
        ],
        "p1_rule_evaluation_count": schedule["cross_rule_evaluation_count"],
        "required_join_predicate_count": len(
            certificate["ordered_required_join_predicates"]
        ),
        "schedule_authority_sha256": _sha256(_canonical_bytes(schedule)),
        "shared_raw_authority_set_sha256": _sha256(
            _canonical_bytes(certificate["shared_raw_authority_sha256_by_path"])
        ),
        "upper_certificate_id": upper_channel["certificate_id"],
        "verifier_expansion_state": certificate["verifier_expansion_state"],
    }
    _require(
        actual == {name: snapshot[name] for name in actual},
        "S1-A4 case-435 exactness-join replay result differs",
    )
    _require(
        verification
        == {
            "case435_exactness_join_certificate_id": snapshot[
                "case435_exactness_join_certificate_id"
            ],
            "upper_certificate_id": snapshot["upper_certificate_id"],
            "attainer_certificate_id": snapshot["attainer_certificate_id"],
            "exact_maximum_octets": snapshot["exact_maximum_octets"],
            "exact_maximum_proved": True,
            "exactness_claimed": True,
            "next_subgate": "A4-P6-C435-D",
            "verifier_expansion_state": "HOLD",
        },
        "S1-A4 case-435 exactness-certificate verification differs",
    )
    test_source = CASE435_EXACTNESS_JOIN_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_c3_join_accepts_only_the_two_frozen_channels",
        "test_independent_checker_reconstructs_join",
        "test_join_and_checker_have_no_local_cross_imports",
        "test_equality_predicate_rejects_different_legal_length",
        "test_checker_rejects_resealed_join_projection_mutation",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 exactness-join test is absent: {test_name}",
        )
    acceptance = CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C3",
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_exactness_join_certificate_id"],
        snapshot["upper_certificate_id"],
        snapshot["attainer_certificate_id"],
        f"{snapshot['exact_maximum_octets']:,}",
        "exactness_claimed = true",
        "A4-P6-C435-D",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 exactness acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_authority_transition_snapshot(
    snapshot: dict[str, Any],
    exactness_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
    s1_a3_snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "authorized_case_change_count",
        "authorized_case_plan_binding_change_count",
        "authorized_logical_plan_change_count",
        "authorized_profile_program_change_count",
        "boundary_delta_raw_octets",
        "boundary_delta_raw_sha256",
        "case435_exact_maximum_octets",
        "checker_raw_octets",
        "checker_raw_sha256",
        "correction_subgate",
        "exactness_join_certificate_id",
        "f2_resource_requalification_state",
        "focused_passed",
        "manifest_delta_raw_octets",
        "manifest_delta_raw_sha256",
        "migrator_raw_octets",
        "migrator_raw_sha256",
        "next_subgate",
        "predecessor_boundary_id",
        "predecessor_manifest_id",
        "predecessor_seed_catalog_id",
        "producer_expansion_state",
        "runner_state",
        "seed_delta_raw_octets",
        "seed_delta_raw_sha256",
        "successor_case435_logical_count_plan_id",
        "successor_case435_profile_conditioning_program_id",
        "successor_constructive_boundary_id",
        "successor_f2_resource_limit_catalog_id",
        "successor_manifest_id",
        "successor_seed_catalog_id",
        "successor_six_case_target_id",
        "target_delta_raw_octets",
        "target_delta_raw_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "unaffected_case_count",
        "unaffected_profile_program_count",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 authority-transition snapshot members differ",
    )
    artifacts = (
        (
            "case-435 authority migrator",
            CASE435_AUTHORITY_MIGRATOR_PATH,
            "migrator_raw_octets",
            "migrator_raw_sha256",
        ),
        (
            "case-435 authority-transition checker",
            CASE435_AUTHORITY_TRANSITION_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 authority-transition test",
            CASE435_AUTHORITY_TRANSITION_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 seed delta",
            CASE435_SEED_DELTA_PATH,
            "seed_delta_raw_octets",
            "seed_delta_raw_sha256",
        ),
        (
            "case-435 manifest delta",
            CASE435_MANIFEST_DELTA_PATH,
            "manifest_delta_raw_octets",
            "manifest_delta_raw_sha256",
        ),
        (
            "case-435 boundary delta",
            CASE435_BOUNDARY_DELTA_PATH,
            "boundary_delta_raw_octets",
            "boundary_delta_raw_sha256",
        ),
        (
            "case-435 target delta",
            CASE435_TARGET_DELTA_PATH,
            "target_delta_raw_octets",
            "target_delta_raw_sha256",
        ),
        (
            "case-435 authority-transition acceptance",
            CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    )
    for label, path, octet_member, hash_member in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "authorized_case_change_count": 1,
        "authorized_case_plan_binding_change_count": 1,
        "authorized_logical_plan_change_count": 1,
        "authorized_profile_program_change_count": 1,
        "case435_exact_maximum_octets": 257_887,
        "correction_subgate": "A4-P6-C435-D",
        "exactness_join_certificate_id": (
            "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        ),
        "f2_resource_requalification_state": "REQUIRED_IN_A4_P6_V",
        "focused_passed": 26,
        "next_subgate": "A4-P6-V",
        "predecessor_boundary_id": (
            "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
        ),
        "predecessor_manifest_id": (
            "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
        ),
        "predecessor_seed_catalog_id": (
            "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
        ),
        "producer_expansion_state": "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "runner_state": "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED",
        "successor_case435_logical_count_plan_id": (
            "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
        ),
        "successor_case435_profile_conditioning_program_id": (
            "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
        ),
        "successor_constructive_boundary_id": (
            "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
        ),
        "successor_f2_resource_limit_catalog_id": (
            "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
        ),
        "successor_manifest_id": (
            "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
        ),
        "successor_seed_catalog_id": (
            "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
        ),
        "successor_six_case_target_id": (
            "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
        ),
        "unaffected_case_count": 474,
        "unaffected_profile_program_count": 407,
        "verifier_expansion_state": "RELEASED_FOR_A4_P6_V_IMPLEMENTATION",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 authority-transition result drifted",
    )
    _require(
        snapshot["exactness_join_certificate_id"]
        == exactness_snapshot["case435_exactness_join_certificate_id"]
        and snapshot["case435_exact_maximum_octets"]
        == exactness_snapshot["exact_maximum_octets"],
        "S1-A4 case-435 transition/exactness binding differs",
    )
    _require(
        snapshot["predecessor_seed_catalog_id"]
        == seed_snapshot["prospective_seed_catalog_id"],
        "S1-A4 case-435 predecessor seed binding differs",
    )
    _require(
        snapshot["predecessor_manifest_id"]
        == s1_a3_snapshot["finalization_manifest_id"],
        "S1-A4 case-435 predecessor manifest binding differs",
    )
    _require(
        snapshot["predecessor_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 case-435 predecessor boundary binding differs",
    )

    transition_checker = _load_case435_authority_transition_checker()
    try:
        report = transition_checker.verify(ROOT)
    except transition_checker.AuthorityTransitionReject as error:
        raise ControlFailure(
            f"S1-A4 case-435 authority-transition replay failed: {error}"
        ) from error
    report_projection = {
        "authorized_case_change_count": report["authorized_case_change_count"],
        "authorized_case_plan_binding_change_count": report[
            "authorized_case_plan_binding_change_count"
        ],
        "authorized_logical_plan_change_count": report[
            "authorized_logical_plan_change_count"
        ],
        "authorized_profile_program_change_count": report[
            "authorized_profile_program_change_count"
        ],
        "case435_exact_maximum_octets": report["case435_exact_maximum_octets"],
        "f2_resource_requalification_state": report[
            "f2_resource_requalification_state"
        ],
        "next_subgate": report["next_subgate"],
        "successor_case435_logical_count_plan_id": report[
            "successor_case435_logical_count_plan_id"
        ],
        "successor_case435_profile_conditioning_program_id": report[
            "successor_case435_profile_conditioning_program_id"
        ],
        "successor_constructive_boundary_id": report[
            "successor_constructive_boundary_id"
        ],
        "successor_f2_resource_limit_catalog_id": report[
            "successor_f2_resource_limit_catalog_id"
        ],
        "successor_manifest_id": report["successor_manifest_id"],
        "successor_seed_catalog_id": report["successor_seed_catalog_id"],
        "successor_six_case_target_id": report["successor_six_case_target_id"],
        "unaffected_case_count": report["unaffected_case_count"],
        "unaffected_profile_program_count": report["unaffected_profile_program_count"],
        "verifier_expansion_state": report["verifier_expansion_state"],
    }
    _require(
        report_projection == {name: snapshot[name] for name in report_projection},
        "S1-A4 case-435 authority-transition replay result differs",
    )
    _require(report["verification_status"] == "ACCEPTED", "transition not accepted")

    test_source = CASE435_AUTHORITY_TRANSITION_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_independent_checker_accepts_exact_single_case_transition",
        "test_case435_effective_program_uses_exact_cell_without_relaxation",
        "test_manifest_does_not_relabel_predecessor_preflight_as_successor_evidence",
        "test_independent_checker_rejects_hostile_resealed_mutations",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 authority-transition test absent: {test_name}",
        )
    acceptance = CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-C435-D",
        snapshot["exactness_join_certificate_id"],
        snapshot["successor_seed_catalog_id"],
        snapshot["successor_manifest_id"],
        snapshot["successor_constructive_boundary_id"],
        snapshot["successor_six_case_target_id"],
        f"{snapshot['case435_exact_maximum_octets']:,}",
        "A4-P6-V",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 authority-transition acceptance marker absent: {marker}",
        )


def _validate_s1_a4_verifier_expansion_v0_snapshot(
    snapshot: dict[str, Any],
    historical_verifier_snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_mode_order",
            "case435_resource_requalification_state",
            "correction_subgate",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_case_positions",
            "predecessor_authority_file_count",
            "predecessor_authority_octets",
            "predecessor_file_headroom",
            "predecessor_octet_headroom",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_octets",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "successor_file_headroom",
            "successor_manifest_id",
            "successor_maximum_protocol_sha256",
            "successor_octet_headroom",
            "successor_seed_catalog_id",
            "successor_six_case_target_id",
            "typed_rule_runtime_raw_octets",
            "typed_rule_runtime_raw_sha256",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier-expansion V0 snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V0"
        and snapshot["acceptance_state"]
        == "EXACT_PREDECESSOR_SUCCESSOR_RESOLVER_AND_READ_BARRIER_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V1"
        and snapshot["accepted_case_positions"] == [5]
        and snapshot["ordered_remaining_case_positions"] == [24, 54, 69, 435, 475]
        and snapshot["authority_mode_order"]
        == [
            "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        ]
        and snapshot["case435_resource_requalification_state"]
        == "WAITING_FOR_A4_P6_V3_EXECUTION"
        and snapshot["focused_passed"] == 7,
        "S1-A4 verifier-expansion V0 state differs",
    )
    _require(
        snapshot["source_marker"] == historical_verifier_snapshot["source_marker"],
        "S1-A4 verifier-expansion source marker differs",
    )
    _require(
        snapshot["successor_seed_catalog_id"]
        == transition_snapshot["successor_seed_catalog_id"]
        and snapshot["successor_manifest_id"]
        == transition_snapshot["successor_manifest_id"]
        and snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"]
        and snapshot["successor_six_case_target_id"]
        == transition_snapshot["successor_six_case_target_id"]
        and snapshot["successor_maximum_protocol_sha256"]
        == transition_snapshot["manifest_delta_raw_sha256"],
        "S1-A4 verifier-expansion successor bindings differ",
    )

    # V0 is an immutable historical checkpoint.  Its accepted verifier bytes
    # have legitimately been superseded in-place by V1, so validate their seal
    # through the dated acceptance record rather than comparing them with the
    # live verifier.  V1 owns the current verifier byte identity below.
    for label, path, octets, digest in (
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "typed rule runtime",
            TYPED_RULE_RUNTIME_PATH,
            snapshot["typed_rule_runtime_raw_octets"],
            snapshot["typed_rule_runtime_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V0 {label} is absent"
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V0 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V0 {label} hash drifted")

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    seed_record = boundary["authority_contract"]["seed_authority"]
    manifest_record = boundary["authority_contract"]["finalization_manifest_authority"]
    seed_path = ROOT / seed_record["repository_relative_path"]
    manifest_path = ROOT / manifest_record["repository_relative_path"]
    seed = json.loads(seed_path.read_bytes())
    seed_delta = json.loads(CASE435_SEED_DELTA_PATH.read_bytes())
    target_delta = json.loads(CASE435_TARGET_DELTA_PATH.read_bytes())

    authority_specs: list[tuple[str, Path, int, str]] = [
        (
            "predecessor boundary",
            CONSTRUCTIVE_BOUNDARY_PATH,
            boundary_snapshot["boundary_raw_octets"],
            boundary_snapshot["boundary_raw_sha256"],
        ),
        (
            "predecessor seed",
            seed_path,
            seed_record["raw_octets"],
            seed_record["raw_sha256"],
        ),
        (
            "predecessor manifest",
            manifest_path,
            manifest_record["raw_octets"],
            manifest_record["raw_sha256"],
        ),
    ]
    for row in seed["ordered_authority_binding_records"]:
        authority_specs.append(
            (
                f"seed authority {row['authority_position']}",
                ROOT / row["repository_relative_path"],
                row["raw_octet_count"],
                row["raw_sha256"],
            )
        )
    legacy = boundary["legacy_v1_exclusion_contract"]
    for name in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        row = legacy[name]
        authority_specs.append(
            (
                name,
                ROOT / row["repository_relative_path"],
                row["raw_octets"],
                row["raw_sha256"],
            )
        )

    predecessor_count = len(authority_specs) + 1
    predecessor_octets = (
        sum(spec[2] for spec in authority_specs) + snapshot["verifier_raw_octets"]
    )
    _require(
        predecessor_count == snapshot["predecessor_authority_file_count"]
        and predecessor_octets == snapshot["predecessor_authority_octets"],
        "S1-A4 V0 predecessor authority footprint differs",
    )

    authority_specs.append(
        (
            "successor seed delta",
            CASE435_SEED_DELTA_PATH,
            transition_snapshot["seed_delta_raw_octets"],
            transition_snapshot["seed_delta_raw_sha256"],
        )
    )
    for row in seed_delta["exactness_theorem_authority"][
        "ordered_source_authority_records"
    ]:
        authority_specs.append(
            (
                f"exactness source {row['source_position']}",
                ROOT / row["repository_relative_path"],
                row["raw_octets"],
                row["raw_sha256"],
            )
        )
    authority_specs.extend(
        [
            (
                "successor manifest delta",
                CASE435_MANIFEST_DELTA_PATH,
                transition_snapshot["manifest_delta_raw_octets"],
                transition_snapshot["manifest_delta_raw_sha256"],
            ),
            (
                "successor boundary delta",
                CASE435_BOUNDARY_DELTA_PATH,
                transition_snapshot["boundary_delta_raw_octets"],
                transition_snapshot["boundary_delta_raw_sha256"],
            ),
        ]
    )
    target_source = target_delta["predecessor_six_case_target_authority"]
    authority_specs.extend(
        [
            (
                "predecessor six-case target",
                ROOT / target_source["repository_relative_path"],
                target_source["raw_octets"],
                target_source["raw_sha256"],
            ),
            (
                "successor six-case target delta",
                CASE435_TARGET_DELTA_PATH,
                transition_snapshot["target_delta_raw_octets"],
                transition_snapshot["target_delta_raw_sha256"],
            ),
            (
                "typed rule runtime",
                TYPED_RULE_RUNTIME_PATH,
                snapshot["typed_rule_runtime_raw_octets"],
                snapshot["typed_rule_runtime_raw_sha256"],
            ),
        ]
    )
    seen_paths: set[Path] = set()
    seen_inodes: set[tuple[int, int]] = set()
    for label, path, octets, digest in authority_specs:
        _require(path not in seen_paths, f"S1-A4 V0 {label} path aliases")
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V0 {label} is absent"
        )
        stat_result = path.stat()
        inode = (stat_result.st_dev, stat_result.st_ino)
        _require(inode not in seen_inodes, f"S1-A4 V0 {label} inode aliases")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V0 {label} authority size differs")
        _require(_sha256(raw) == digest, f"S1-A4 V0 {label} authority hash differs")
        seen_paths.add(path)
        seen_inodes.add(inode)

    successor_count = len(authority_specs) + 1
    successor_octets = (
        sum(spec[2] for spec in authority_specs) + snapshot["verifier_raw_octets"]
    )
    _require(
        successor_count == snapshot["successor_authority_file_count"]
        and successor_octets == snapshot["successor_authority_octets"],
        "S1-A4 V0 successor authority footprint differs",
    )
    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    _require(
        file_limit == 64
        and octet_limit == 67_108_864
        and file_limit - predecessor_count == snapshot["predecessor_file_headroom"]
        and octet_limit - predecessor_octets == snapshot["predecessor_octet_headroom"]
        and file_limit - successor_count == snapshot["successor_file_headroom"]
        and octet_limit - successor_octets == snapshot["successor_octet_headroom"],
        "S1-A4 V0 immutable F0 headroom differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    for marker in (
        snapshot["source_marker"],
        "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        transition_snapshot["successor_seed_catalog_id"],
        transition_snapshot["successor_manifest_id"],
        transition_snapshot["successor_constructive_boundary_id"],
    ):
        _require(marker in source, f"S1-A4 V0 verifier marker absent: {marker}")
    test_source = INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_v0_preserves_predecessor_case5_and_accepts_successor_case5",
        "test_v0_successor_mode_is_byte_deterministic",
        "test_v0_rejects_cross_mode_candidate_authority_ids",
        "test_v0_rejects_tampered_successor_authority_before_candidate_open",
    ):
        _require(test_name in test_source, f"S1-A4 V0 test absent: {test_name}")
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V0",
        "A4-P6-V1",
        snapshot["verifier_raw_sha256"],
        snapshot["successor_seed_catalog_id"],
        snapshot["successor_constructive_boundary_id"],
        "28,752,433",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V0 acceptance marker absent: {marker}")


def _validate_s1_a4_verifier_expansion_v1_snapshot(
    snapshot: dict[str, Any],
    v0_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_mode_order",
            "case24_candidate_raw_octets",
            "case24_context_object_count",
            "case24_context_raw_octets",
            "case24_file_headroom",
            "case24_maximum_canonical_octets",
            "case24_octet_headroom",
            "case24_plan_id",
            "case24_resource_vector",
            "case24_stream_sha256",
            "case24_total_input_file_count",
            "case24_total_input_octets",
            "case54_candidate_raw_octets",
            "case54_context_object_count",
            "case54_context_raw_octets",
            "case54_file_headroom",
            "case54_maximum_canonical_octets",
            "case54_octet_headroom",
            "case54_plan_id",
            "case54_resource_vector",
            "case54_stream_sha256",
            "case54_total_input_file_count",
            "case54_total_input_octets",
            "case435_resource_requalification_state",
            "core_matrix_passed",
            "correction_subgate",
            "differential_passed",
            "differential_test_raw_octets",
            "differential_test_raw_sha256",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_case_positions",
            "predecessor_case5_state",
            "producer_expansion_state",
            "runner_state",
            "source_isolation_state",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_file_headroom",
            "successor_authority_octets",
            "successor_authority_octet_headroom",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "typed_rule_runtime_raw_octets",
            "typed_rule_runtime_raw_sha256",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier-expansion V1 snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V1"
        and snapshot["acceptance_state"] == "EXACT_INTRINSIC_CASES_24_AND_54_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V2"
        and snapshot["accepted_case_positions"] == [5, 24, 54]
        and snapshot["ordered_remaining_case_positions"] == [69, 435, 475]
        and snapshot["authority_mode_order"] == v0_snapshot["authority_mode_order"]
        and snapshot["predecessor_case5_state"] == "PRESERVED"
        and snapshot["source_isolation_state"]
        == "STATIC_SUBSET_NO_DYNAMIC_CODE_EXECUTION"
        and snapshot["case435_resource_requalification_state"]
        == "WAITING_FOR_A4_P6_V3_EXECUTION"
        and snapshot["producer_expansion_state"] == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and snapshot["runner_state"]
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED"
        and snapshot["focused_passed"] == 19
        and snapshot["differential_passed"] == 7
        and snapshot["core_matrix_passed"] == 414,
        "S1-A4 verifier-expansion V1 state differs",
    )
    _require(
        snapshot["source_marker"] == v0_snapshot["source_marker"],
        "S1-A4 verifier-expansion V1 source marker differs",
    )
    _require(
        snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"],
        "S1-A4 verifier-expansion V1 successor binding differs",
    )

    for label, path, octets, digest in (
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V1_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "runtime differential test",
            INDEPENDENT_VERIFIER_EXPANSION_V1_DIFFERENTIAL_TEST_PATH,
            snapshot["differential_test_raw_octets"],
            snapshot["differential_test_raw_sha256"],
        ),
        (
            "typed rule runtime",
            TYPED_RULE_RUNTIME_PATH,
            snapshot["typed_rule_runtime_raw_octets"],
            snapshot["typed_rule_runtime_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V1_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V1 {label} is absent"
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V1 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V1 {label} hash drifted")

    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    authority_file_count = v0_snapshot["successor_authority_file_count"]
    authority_octets = (
        v0_snapshot["successor_authority_octets"]
        - v0_snapshot["verifier_raw_octets"]
        + snapshot["verifier_raw_octets"]
    )
    _require(
        file_limit == v0_snapshot["f0_input_file_count_limit"] == 64
        and octet_limit
        == v0_snapshot["f0_total_pinned_input_octets_limit"]
        == 67_108_864
        and snapshot["successor_authority_file_count"] == authority_file_count
        and snapshot["successor_authority_octets"] == authority_octets
        and snapshot["successor_authority_file_headroom"]
        == file_limit - authority_file_count
        and snapshot["successor_authority_octet_headroom"]
        == octet_limit - authority_octets,
        "S1-A4 V1 successor authority footprint differs",
    )
    for label, context_count, context_octets, candidate_octets in (
        (
            "case24",
            snapshot["case24_context_object_count"],
            snapshot["case24_context_raw_octets"],
            snapshot["case24_candidate_raw_octets"],
        ),
        (
            "case54",
            snapshot["case54_context_object_count"],
            snapshot["case54_context_raw_octets"],
            snapshot["case54_candidate_raw_octets"],
        ),
    ):
        total_files = authority_file_count + 1 + context_count
        total_octets = authority_octets + candidate_octets + context_octets
        _require(
            snapshot[f"{label}_total_input_file_count"] == total_files
            and snapshot[f"{label}_total_input_octets"] == total_octets
            and snapshot[f"{label}_file_headroom"] == file_limit - total_files
            and snapshot[f"{label}_octet_headroom"] == octet_limit - total_octets
            and total_files <= file_limit
            and total_octets <= octet_limit,
            f"S1-A4 V1 {label} F0 footprint differs",
        )

    _require(
        snapshot["case24_maximum_canonical_octets"] == 523_738
        and snapshot["case24_candidate_raw_octets"] == 596_722
        and snapshot["case24_context_object_count"] == 1
        and snapshot["case24_context_raw_octets"] == 524_287
        and snapshot["case24_plan_id"]
        == "428ff735837b841e66103d64cbcd4af7ceaf88d009c38229ad5e4cde0ab30d67"
        and snapshot["case24_resource_vector"]
        == [
            1,
            2_101_277,
            39,
            459,
            4_202_945,
            5,
            39,
            26_493,
            340_068,
            362_505,
            488_331,
            1,
            0,
            0,
            6,
            32,
            36_304,
            9_469,
        ]
        and snapshot["case24_stream_sha256"]
        == "bf6a4886b3bc7110a61a5170e2b03f5de402a08e5bd78eccafb54b719d99cbcd",
        "S1-A4 V1 case24 exact result differs",
    )
    _require(
        snapshot["case54_maximum_canonical_octets"] == 3_145_728
        and snapshot["case54_candidate_raw_octets"] == 3_151_660
        and snapshot["case54_context_object_count"] == 0
        and snapshot["case54_context_raw_octets"] == 0
        and snapshot["case54_plan_id"]
        == "4eeedde2c223693e62a2b89a2016b43f9954496771189616ad68ac8cf21e6da1"
        and snapshot["case54_resource_vector"]
        == [
            1,
            515,
            5,
            9,
            1_031,
            1,
            5,
            3_415,
            9_775,
            12_712,
            41_372,
            1,
            0,
            0,
            4,
            9,
            3_937,
            1_589,
        ]
        and snapshot["case54_stream_sha256"]
        == "9a9b153f3fee7073849416c8ccc3f419bda471b1c541165b20f49989cb6b379f",
        "S1-A4 V1 case54 exact result differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    calls = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    _require(
        calls.isdisjoint({"__import__", "compile", "eval", "exec"})
        and "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source
        and "validate_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py"
        not in source
        and "typed_runtime_raw = _load_additional_authority" in source,
        "S1-A4 V1 static source isolation differs",
    )
    for marker in (
        snapshot["source_marker"],
        "CASE24_POSITION = 24",
        "CASE54_POSITION = 54",
        transition_snapshot["successor_seed_catalog_id"],
        transition_snapshot["successor_manifest_id"],
    ):
        _require(marker in source, f"S1-A4 V1 verifier marker absent: {marker}")

    test_source = INDEPENDENT_VERIFIER_EXPANSION_V1_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_v1_source_preserves_static_independence_and_pinned_runtime_barrier",
        "test_v1_attainers_are_exact_deterministic_immutable_and_f2_bounded",
        "test_v1_rejects_resealed_illegal_or_nonattaining_witnesses",
        "test_v1_rejects_owner_witness_divergence_and_context_tamper",
        "test_v1_keeps_later_packets_fail_closed",
    ):
        _require(test_name in test_source, f"S1-A4 V1 test absent: {test_name}")
    differential_source = (
        INDEPENDENT_VERIFIER_EXPANSION_V1_DIFFERENTIAL_TEST_PATH.read_text(
            encoding="utf-8"
        )
    )
    for test_name in (
        "test_v1_static_subset_positive_attainers_match_the_pinned_runtime",
        "test_v1_static_subset_rejection_samples_match_the_pinned_runtime",
    ):
        _require(
            test_name in differential_source,
            f"S1-A4 V1 differential test absent: {test_name}",
        )
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V1_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V1",
        "A4-P6-V2",
        snapshot["verifier_raw_sha256"],
        snapshot["verifier_test_raw_sha256"],
        snapshot["differential_test_raw_sha256"],
        snapshot["case24_stream_sha256"],
        snapshot["case54_stream_sha256"],
        "523,738",
        "3,145,728",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V1 acceptance marker absent: {marker}")


def _validate_s1_a4_verifier_expansion_v2_snapshot(
    snapshot: dict[str, Any],
    v1_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "analytic_authority_tamper_state",
            "authority_mode_order",
            "case69_analytic_catalog_id",
            "case69_application_id",
            "case69_candidate_raw_octets",
            "case69_context_object_count",
            "case69_context_raw_octets",
            "case69_file_headroom",
            "case69_maximum_canonical_octets",
            "case69_octet_headroom",
            "case69_plan_id",
            "case69_profile_id",
            "case69_program_id",
            "case69_resource_vector",
            "case69_spec_id",
            "case69_stream_sha256",
            "case69_total_input_file_count",
            "case69_total_input_octets",
            "case69_witness_sha256",
            "case435_resource_requalification_state",
            "core_matrix_passed",
            "correction_subgate",
            "differential_passed",
            "differential_test_raw_octets",
            "differential_test_raw_sha256",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_case_positions",
            "predecessor_v0_v1_state",
            "producer_expansion_state",
            "runner_state",
            "source_isolation_state",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_file_headroom",
            "successor_authority_octets",
            "successor_authority_octet_headroom",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "typed_rule_runtime_raw_octets",
            "typed_rule_runtime_raw_sha256",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier-expansion V2 snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V2"
        and snapshot["acceptance_state"] == "EXACT_PROFILE_CASE_69_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V3"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69]
        and snapshot["ordered_remaining_case_positions"] == [435, 475]
        and snapshot["authority_mode_order"] == v1_snapshot["authority_mode_order"]
        and snapshot["predecessor_v0_v1_state"] == "PRESERVED"
        and snapshot["source_isolation_state"]
        == "STATIC_SUBSET_NO_DYNAMIC_CODE_EXECUTION"
        and snapshot["analytic_authority_tamper_state"]
        == "DIRECT_SHADOW_REPOSITORY_REJECTION_PROVED"
        and snapshot["case435_resource_requalification_state"]
        == "WAITING_FOR_A4_P6_V3_EXECUTION"
        and snapshot["producer_expansion_state"] == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and snapshot["runner_state"]
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED"
        and snapshot["focused_passed"] == 17
        and snapshot["differential_passed"] == 5
        and snapshot["core_matrix_passed"] == 440,
        "S1-A4 verifier-expansion V2 state differs",
    )
    _require(
        snapshot["source_marker"] == v1_snapshot["source_marker"],
        "S1-A4 verifier-expansion V2 source marker differs",
    )
    _require(
        snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"],
        "S1-A4 verifier-expansion V2 successor binding differs",
    )

    # V2 is an immutable historical checkpoint. Its accepted verifier bytes
    # have been superseded in-place by V3, so the dated V2 acceptance retains
    # their seal while V3 owns the live verifier byte identity below.
    for label, path, octets, digest in (
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V2_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "runtime differential test",
            INDEPENDENT_VERIFIER_EXPANSION_V2_DIFFERENTIAL_TEST_PATH,
            snapshot["differential_test_raw_octets"],
            snapshot["differential_test_raw_sha256"],
        ),
        (
            "typed rule runtime",
            TYPED_RULE_RUNTIME_PATH,
            snapshot["typed_rule_runtime_raw_octets"],
            snapshot["typed_rule_runtime_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V2_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V2 {label} is absent"
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V2 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V2 {label} hash drifted")

    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    authority_file_count = v1_snapshot["successor_authority_file_count"]
    authority_octets = (
        v1_snapshot["successor_authority_octets"]
        - v1_snapshot["verifier_raw_octets"]
        + snapshot["verifier_raw_octets"]
    )
    total_files = authority_file_count + 1 + snapshot["case69_context_object_count"]
    total_octets = (
        authority_octets
        + snapshot["case69_candidate_raw_octets"]
        + snapshot["case69_context_raw_octets"]
    )
    _require(
        file_limit == v1_snapshot["f0_input_file_count_limit"] == 64
        and octet_limit
        == v1_snapshot["f0_total_pinned_input_octets_limit"]
        == 67_108_864
        and snapshot["successor_authority_file_count"] == authority_file_count
        and snapshot["successor_authority_octets"] == authority_octets
        and snapshot["successor_authority_file_headroom"]
        == file_limit - authority_file_count
        and snapshot["successor_authority_octet_headroom"]
        == octet_limit - authority_octets
        and snapshot["case69_total_input_file_count"] == total_files
        and snapshot["case69_total_input_octets"] == total_octets
        and snapshot["case69_file_headroom"] == file_limit - total_files
        and snapshot["case69_octet_headroom"] == octet_limit - total_octets
        and total_files <= file_limit
        and total_octets <= octet_limit,
        "S1-A4 V2 case69 F0 footprint differs",
    )
    _require(
        snapshot["case69_maximum_canonical_octets"] == 2_581
        and snapshot["case69_candidate_raw_octets"] == 6_136
        and snapshot["case69_context_object_count"] == 0
        and snapshot["case69_context_raw_octets"] == 0
        and snapshot["case69_plan_id"]
        == "b991ffb7f0ea927d854228bcc52524e39fee7e88080d9171753b03cc59589fcb"
        and snapshot["case69_profile_id"]
        == "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
        and snapshot["case69_program_id"]
        == "6912414e364c4117822c7ad0d24d1436d46f29e945ed076140785f5c0c9fc442"
        and snapshot["case69_analytic_catalog_id"]
        == "759b3fbd70f3a36c0a6309ec35c4f5cd8efda7cf01d23bcd5e52e290ff29f0e0"
        and snapshot["case69_spec_id"]
        == "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
        and snapshot["case69_application_id"]
        == "770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18"
        and snapshot["case69_witness_sha256"]
        == "af8bf018a32ac4444cd00cfc6b3cb64c732654398a5904f0295ec77307d718f4"
        and snapshot["case69_resource_vector"]
        == [
            1,
            2_101_890,
            157,
            829,
            4_204_335,
            7,
            157,
            105_752,
            673_168,
            763_519,
            1_380_238,
            6,
            1,
            1,
            14,
            32,
            50_016,
            36_961,
        ]
        and snapshot["case69_stream_sha256"]
        == "7965e977eca8aa43ce84c97391a1ae4c51dfd2f79fa20e80ea7b6110ea5c808f",
        "S1-A4 V2 case69 exact result differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    calls = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    _require(
        calls.isdisjoint({"__import__", "compile", "eval", "exec"})
        and "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source
        and "validate_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py"
        not in source
        and "typed_runtime_raw = _load_additional_authority" in source,
        "S1-A4 V2 static source isolation differs",
    )
    for marker in (
        snapshot["source_marker"],
        "CASE69_POSITION = 69",
        "V2_SUCCESSOR_CASE_POSITIONS",
        snapshot["case69_analytic_catalog_id"],
        transition_snapshot["successor_seed_catalog_id"],
        transition_snapshot["successor_manifest_id"],
    ):
        _require(marker in source, f"S1-A4 V2 verifier marker absent: {marker}")

    test_source = INDEPENDENT_VERIFIER_EXPANSION_V2_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_v2_attainer_formula_is_independent_exact_and_signed_spec_bounded",
        "test_v2_rejects_case69_analytic_endpoint_authority_tamper",
        "test_v2_case69_is_exact_deterministic_immutable_and_f2_bounded",
        "test_v2_rejects_resealed_context_or_schedule_substitutions",
        "test_v2_rejects_resealed_p1_or_p3_failures",
        "test_v2_keeps_later_packets_fail_closed",
        "test_v2_source_remains_static_and_does_not_admit_later_packets",
    ):
        _require(test_name in test_source, f"S1-A4 V2 test absent: {test_name}")
    differential_source = (
        INDEPENDENT_VERIFIER_EXPANSION_V2_DIFFERENTIAL_TEST_PATH.read_text(
            encoding="utf-8"
        )
    )
    for test_name in (
        "test_v2_case69_static_subset_positive_pair_matches_the_pinned_runtime",
        "test_v2_case69_static_subset_rejection_samples_match_the_pinned_runtime",
    ):
        _require(
            test_name in differential_source,
            f"S1-A4 V2 differential test absent: {test_name}",
        )
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V2_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V2",
        "A4-P6-V3",
        snapshot["verifier_raw_sha256"],
        snapshot["verifier_test_raw_sha256"],
        snapshot["differential_test_raw_sha256"],
        snapshot["case69_stream_sha256"],
        snapshot["case69_witness_sha256"],
        "2,581",
        "440 passed",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V2 acceptance marker absent: {marker}")


def _validate_s1_a4_case435_context_pack_snapshot(
    snapshot: dict[str, Any],
    v2_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_mode_order",
            "case435_context_pack_boundary_delta_id",
            "case435_resource_requalification_state",
            "checker_raw_octets",
            "checker_raw_sha256",
            "corrected_authority_file_count",
            "correction_subgate",
            "delta_raw_octets",
            "delta_raw_sha256",
            "exact_maximum_octets",
            "f0_input_file_count_limit",
            "flat_minimum_input_file_count",
            "focused_passed",
            "generator_raw_octets",
            "generator_raw_sha256",
            "individual_pack_strict_upper_octets",
            "logical_context_object_count",
            "next_subgate",
            "ordered_remaining_case_positions",
            "packed_input_file_headroom",
            "packed_minimum_input_file_count",
            "producer_expansion_state",
            "required_context_pack_count",
            "runner_state",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "test_raw_octets",
            "test_raw_sha256",
        },
        "S1-A4 case435 context-pack snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V3-T"
        and snapshot["acceptance_state"]
        == "PACKED_CONTEXT_TRANSPORT_ACCEPTED_CASE435_STILL_UNSUPPORTED"
        and snapshot["next_subgate"] == "A4-P6-V3"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69]
        and snapshot["ordered_remaining_case_positions"] == [435, 475]
        and snapshot["authority_mode_order"]
        == [
            "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        ]
        and snapshot["case435_resource_requalification_state"]
        == "WAITING_FOR_A4_P6_V3_EXECUTION"
        and snapshot["producer_expansion_state"] == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and snapshot["runner_state"]
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED"
        and snapshot["focused_passed"] == 17,
        "S1-A4 case435 context-pack state differs",
    )
    _require(
        v2_snapshot["next_subgate"] == "A4-P6-V3"
        and snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"]
        and snapshot["exact_maximum_octets"]
        == transition_snapshot["case435_exact_maximum_octets"]
        == 257_887,
        "S1-A4 case435 context-pack authority binding differs",
    )
    for label, path, octets, digest in (
        (
            "generator",
            CASE435_CONTEXT_PACK_GENERATOR_PATH,
            snapshot["generator_raw_octets"],
            snapshot["generator_raw_sha256"],
        ),
        (
            "checker",
            CASE435_CONTEXT_PACK_CHECKER_PATH,
            snapshot["checker_raw_octets"],
            snapshot["checker_raw_sha256"],
        ),
        (
            "delta",
            CASE435_CONTEXT_PACK_DELTA_PATH,
            snapshot["delta_raw_octets"],
            snapshot["delta_raw_sha256"],
        ),
        (
            "test",
            CASE435_CONTEXT_PACK_TEST_PATH,
            snapshot["test_raw_octets"],
            snapshot["test_raw_sha256"],
        ),
        (
            "acceptance",
            CASE435_CONTEXT_PACK_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 case435 context-pack {label} is absent",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == octets,
            f"S1-A4 case435 context-pack {label} size drifted",
        )
        _require(
            _sha256(raw) == digest,
            f"S1-A4 case435 context-pack {label} hash drifted",
        )

    report = _load_case435_context_pack_checker().verify(ROOT)
    _require(
        report["verification_status"] == "ACCEPTED"
        and report["case435_context_pack_boundary_delta_id"]
        == snapshot["case435_context_pack_boundary_delta_id"]
        and report["correction_raw_octets"] == snapshot["delta_raw_octets"]
        and report["correction_raw_sha256"] == snapshot["delta_raw_sha256"]
        and report["flat_minimum_input_file_count"]
        == snapshot["flat_minimum_input_file_count"]
        and report["packed_minimum_input_file_count"]
        == snapshot["packed_minimum_input_file_count"]
        and report["packed_input_file_headroom"]
        == snapshot["packed_input_file_headroom"]
        and report["logical_context_object_count"]
        == snapshot["logical_context_object_count"]
        and report["required_context_pack_count"]
        == snapshot["required_context_pack_count"]
        and report["individual_pack_strict_upper_octets"]
        == snapshot["individual_pack_strict_upper_octets"]
        and report["unchanged_case435_exact_maximum_octets"]
        == snapshot["exact_maximum_octets"],
        "S1-A4 case435 context-pack report differs",
    )
    _require(
        snapshot["f0_input_file_count_limit"] == 64
        and snapshot["corrected_authority_file_count"]
        == v2_snapshot["successor_authority_file_count"] + 1
        == 39
        and snapshot["flat_minimum_input_file_count"] == 38 + 1 + 67 == 106
        and snapshot["flat_minimum_input_file_count"]
        > snapshot["f0_input_file_count_limit"]
        and snapshot["packed_minimum_input_file_count"] == 39 + 1 + 1 == 41
        and snapshot["packed_input_file_headroom"] == 64 - 41 == 23
        and snapshot["logical_context_object_count"] == 67
        and snapshot["required_context_pack_count"] == 1
        and snapshot["individual_pack_strict_upper_octets"] == 16_777_216,
        "S1-A4 case435 context-pack F0 arithmetic differs",
    )
    acceptance = CASE435_CONTEXT_PACK_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-V3-T",
        "A4-P6-V3",
        snapshot["case435_context_pack_boundary_delta_id"],
        snapshot["delta_raw_sha256"],
        "106 input files",
        "41 input files",
        "17 passed",
        "NO-GO",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case435 context-pack acceptance marker absent: {marker}",
        )


def _validate_s1_a4_verifier_expansion_v3_snapshot(
    snapshot: dict[str, Any],
    v2_snapshot: dict[str, Any],
    context_pack_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_filtered_passed",
            "a4_t_unfiltered_expected_failed",
            "a4_t_unfiltered_passed",
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_mode_order",
            "case435_attainer_id",
            "case435_candidate_id",
            "case435_candidate_raw_octets",
            "case435_candidate_raw_sha256",
            "case435_context_object_count",
            "case435_context_pack_id",
            "case435_context_pack_raw_octets",
            "case435_context_pack_raw_sha256",
            "case435_cross_rule_evaluation_count",
            "case435_direct_expression_node_count",
            "case435_exact_maximum_octets",
            "case435_exactness_join_certificate_id",
            "case435_maximum_attainer_raw_octets",
            "case435_maximum_attainer_raw_sha256",
            "case435_plan_id",
            "case435_profile_id",
            "case435_program_id",
            "case435_receipt_id",
            "case435_receipt_raw_octets",
            "case435_receipt_raw_sha256",
            "case435_resource_requalification_state",
            "case435_resource_report_id",
            "case435_resource_vector",
            "case435_stream_sha256",
            "case435_upper_certificate_id",
            "case435_witness_sha256",
            "combined_passed",
            "core_matrix_passed",
            "correction_subgate",
            "differential_passed",
            "differential_test_raw_octets",
            "differential_test_raw_sha256",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "next_subgate",
            "ordered_application_family_counts",
            "ordered_remaining_case_positions",
            "p6_filtered_passed",
            "p6_unfiltered_expected_failed",
            "p6_unfiltered_passed",
            "predecessor_context_regression_passed",
            "predecessor_v0_v1_v2_state",
            "producer_expansion_state",
            "runner_state",
            "source_isolation_state",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_file_headroom",
            "successor_authority_octets",
            "successor_authority_octet_headroom",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "total_input_file_count",
            "total_input_file_headroom",
            "total_input_octets",
            "total_input_octet_headroom",
            "typed_rule_runtime_raw_octets",
            "typed_rule_runtime_raw_sha256",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier-expansion V3 snapshot members differ",
    )
    expected_modes = [
        "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
    ]
    _require(
        snapshot["correction_subgate"] == "A4-P6-V3"
        and snapshot["acceptance_state"] == "EXACT_PACKED_CONTEXT_CASE_435_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V4"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69, 435]
        and snapshot["ordered_remaining_case_positions"] == [475]
        and snapshot["authority_mode_order"] == expected_modes
        and snapshot["predecessor_v0_v1_v2_state"] == "PRESERVED"
        and snapshot["source_isolation_state"]
        == "STATIC_TYPED_SUBSET_WITH_SEPARATE_GENERIC_RUNTIME_DIFFERENTIAL"
        and snapshot["case435_resource_requalification_state"]
        == "ACCEPTED_WITHIN_IMMUTABLE_F2"
        and snapshot["producer_expansion_state"] == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and snapshot["runner_state"]
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED"
        and snapshot["focused_passed"] == 21
        and snapshot["differential_passed"] == 7
        and snapshot["combined_passed"] == 28
        and snapshot["predecessor_context_regression_passed"] == 72
        and snapshot["core_matrix_passed"] == 487
        and snapshot["a4_t_filtered_passed"] == 59
        and snapshot["a4_t_unfiltered_passed"] == 61
        and snapshot["a4_t_unfiltered_expected_failed"] == 1
        and snapshot["p6_filtered_passed"] == 13
        and snapshot["p6_unfiltered_passed"] == 13
        and snapshot["p6_unfiltered_expected_failed"] == 6,
        "S1-A4 verifier-expansion V3 state differs",
    )
    _require(
        v2_snapshot["next_subgate"] == "A4-P6-V3"
        and context_pack_snapshot["correction_subgate"] == "A4-P6-V3-T"
        and context_pack_snapshot["next_subgate"] == "A4-P6-V3"
        and context_pack_snapshot["authority_mode_order"] == expected_modes
        and snapshot["source_marker"] == v2_snapshot["source_marker"]
        and snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        == context_pack_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"]
        == context_pack_snapshot["successor_f2_resource_limit_catalog_id"],
        "S1-A4 verifier-expansion V3 authority binding differs",
    )

    # V3 retains the verifier byte identity that was live at its acceptance;
    # the live verifier is now owned and checked by the V4 snapshot below.
    for label, path, octets, digest in (
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V3_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "runtime differential test",
            INDEPENDENT_VERIFIER_EXPANSION_V3_DIFFERENTIAL_TEST_PATH,
            snapshot["differential_test_raw_octets"],
            snapshot["differential_test_raw_sha256"],
        ),
        (
            "typed rule runtime",
            TYPED_RULE_RUNTIME_PATH,
            snapshot["typed_rule_runtime_raw_octets"],
            snapshot["typed_rule_runtime_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V3_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V3 {label} is absent"
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V3 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V3 {label} hash drifted")

    authority_file_count = context_pack_snapshot["corrected_authority_file_count"]
    authority_octets = (
        v2_snapshot["successor_authority_octets"]
        - v2_snapshot["verifier_raw_octets"]
        + snapshot["verifier_raw_octets"]
        + context_pack_snapshot["delta_raw_octets"]
    )
    total_files = authority_file_count + 1 + 1
    total_octets = (
        authority_octets
        + snapshot["case435_candidate_raw_octets"]
        + snapshot["case435_context_pack_raw_octets"]
    )
    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    _require(
        file_limit == v2_snapshot["f0_input_file_count_limit"] == 64
        and octet_limit
        == v2_snapshot["f0_total_pinned_input_octets_limit"]
        == 67_108_864
        and authority_file_count == snapshot["successor_authority_file_count"] == 39
        and authority_octets == snapshot["successor_authority_octets"]
        and snapshot["successor_authority_file_headroom"]
        == file_limit - authority_file_count
        and snapshot["successor_authority_octet_headroom"]
        == octet_limit - authority_octets
        and snapshot["total_input_file_count"] == total_files == 41
        and snapshot["total_input_octets"] == total_octets
        and snapshot["total_input_file_headroom"] == file_limit - total_files == 23
        and snapshot["total_input_octet_headroom"] == octet_limit - total_octets
        and snapshot["case435_context_pack_raw_octets"] < 16_777_216
        and total_files <= file_limit
        and total_octets <= octet_limit,
        "S1-A4 V3 case435 F0 footprint differs",
    )

    _require(
        snapshot["case435_exact_maximum_octets"] == 257_887
        and snapshot["case435_candidate_id"]
        == "3733dcc3ee96435a25e4b432434da6f0e9918f7a72d771625bc31fccbd1ba36a"
        and snapshot["case435_candidate_raw_octets"] == 385_701
        and snapshot["case435_candidate_raw_sha256"]
        == "3ddf81163d609d2e5e2a87055073c23510162b2b7032f5f013e0fae5165ad289"
        and snapshot["case435_context_pack_id"]
        == "a7b2de0d3e3bea1c61971193f25e023f28d0002251109358546a87fa8821a749"
        and snapshot["case435_context_pack_raw_octets"] == 12_645_617
        and snapshot["case435_context_pack_raw_sha256"]
        == "320b696f94e3f32114cf7facf94c9434f815aefeaed4cb979aabd870663e3a99"
        and snapshot["case435_plan_id"]
        == "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
        and snapshot["case435_profile_id"]
        == "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
        and snapshot["case435_program_id"]
        == "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
        and snapshot["case435_exactness_join_certificate_id"]
        == "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        and snapshot["case435_witness_sha256"]
        == "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        and snapshot["case435_attainer_id"]
        == "0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f"
        and snapshot["case435_maximum_attainer_raw_octets"] == 382_271
        and snapshot["case435_maximum_attainer_raw_sha256"]
        == "90d09148cbbbaef3e7b22530d4fbcf9086d1c74dd5c96470ef5b40d2a3a98d1f"
        and snapshot["case435_upper_certificate_id"]
        == "7a36dcb15bd3fae4125c51b88010793fa63f7a2c5f03421b343eea0cd9aa0c25"
        and snapshot["case435_resource_report_id"]
        == "3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9"
        and snapshot["case435_receipt_id"]
        == "fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd"
        and snapshot["case435_receipt_raw_octets"] == 32_276
        and snapshot["case435_receipt_raw_sha256"]
        == "dee73e8007af742bd116e10d0e7597b108a5a8cefe0cd3901470c2dcf6f33a20"
        and snapshot["case435_context_object_count"] == 67
        and snapshot["case435_cross_rule_evaluation_count"] == 12_531
        and snapshot["case435_direct_expression_node_count"] == 125_431
        and snapshot["ordered_application_family_counts"]
        == [
            ["APPLY/SELECTOR_MARKER_CONTRACT_V1", 1],
            ["APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1", 67],
            ["APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1", 67],
            ["APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1", 1],
            ["APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1", 1],
        ],
        "S1-A4 V3 case435 exact result differs",
    )
    _require(
        snapshot["case435_resource_vector"]
        == [
            1,
            35_384,
            158,
            1_002,
            347_899,
            4,
            158,
            106_269,
            789_225,
            879_955,
            1_480_733,
            10,
            12_531,
            137,
            17,
            137,
            38_451,
            37_195,
        ]
        and snapshot["case435_stream_sha256"]
        == "b35d70426261fc07da100f3d0f9486ccdd03a21e1699ab2008f97d58ecc3fc83",
        "S1-A4 V3 case435 resource result differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    _require(
        imports == {"hashlib", "json", "os", "pathlib", "stat", "sys", "tempfile"}
        and calls.isdisjoint({"__import__", "compile", "eval", "exec"})
        and "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source
        and "construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py"
        not in source
        and "class _Case435RuleRuntime:" in source
        and "typed_runtime_raw = _load_additional_authority" in source,
        "S1-A4 V3 static source isolation differs",
    )
    for marker in (
        snapshot["source_marker"],
        "CASE435_POSITION = 435",
        "V3_SUCCESSOR_CASE_POSITIONS",
        "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        snapshot["case435_plan_id"],
        snapshot["case435_program_id"],
        snapshot["case435_profile_id"],
    ):
        _require(marker in source, f"S1-A4 V3 verifier marker absent: {marker}")

    test_source = INDEPENDENT_VERIFIER_EXPANSION_V3_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_case435_is_exact_deterministic_immutable_and_f2_bounded",
        "test_case435_requires_the_packed_transport_boundary",
        "test_case435_rejects_resealed_authority_or_c2_trust_substitutions",
        "test_case435_rejects_resealed_context_or_schedule_substitutions",
        "test_case435_rejects_resealed_incomplete_or_duplicate_pack_closures",
        "test_case435_rejects_resealed_p1_or_p3_failures",
        "test_case435_rejects_distinct_resealed_semantic_guard_failures",
        "test_case435_keeps_candidate_pack_file_closure_exact",
        "test_v3_source_is_static_and_isolated_from_producers_and_proof_checkers",
    ):
        _require(test_name in test_source, f"S1-A4 V3 test absent: {test_name}")
    differential_source = (
        INDEPENDENT_VERIFIER_EXPANSION_V3_DIFFERENTIAL_TEST_PATH.read_text(
            encoding="utf-8"
        )
    )
    for test_name in (
        "test_v3_static_subset_positive_samples_match_the_pinned_generic_runtime",
        "test_v3_static_subset_descriptor_rejection_matches_the_generic_runtime",
        "test_v3_p1_acceptance_does_not_replace_the_separate_p3_check",
        "test_v3_field_context_rejection_matches_the_generic_runtime",
        "test_v3_a1_fifo_true_and_false_samples_match_the_static_and_generic_runtimes",
        "test_v3_root_relation_rejections_match_the_generic_runtime",
    ):
        _require(
            test_name in differential_source,
            f"S1-A4 V3 differential test absent: {test_name}",
        )
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V3_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V3",
        "A4-P6-V4",
        snapshot["verifier_raw_sha256"],
        snapshot["verifier_test_raw_sha256"],
        snapshot["differential_test_raw_sha256"],
        snapshot["case435_stream_sha256"],
        snapshot["case435_witness_sha256"],
        snapshot["case435_context_pack_id"],
        "257,887",
        "487 passed",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V3 acceptance marker absent: {marker}")


def _validate_s1_a4_verifier_expansion_v4_snapshot(
    snapshot: dict[str, Any],
    v3_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_filtered_passed",
            "a4_t_unfiltered_expected_failed",
            "a4_t_unfiltered_passed",
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "case475_baseline_operation_spec_id",
            "case475_better_objective_exclusion_sha256",
            "case475_candidate_id",
            "case475_candidate_raw_octets",
            "case475_candidate_raw_sha256",
            "case475_exact_maximum_octets",
            "case475_local_proof_scope_id",
            "case475_local_result_id",
            "case475_local_result_raw_octets",
            "case475_local_result_raw_sha256",
            "case475_minimality_certificate_id",
            "case475_mutated_operation_spec_id",
            "case475_plan_id",
            "case475_predecessor_maximum_octets",
            "case475_profile_id",
            "case475_prospective_result_id",
            "case475_receipt_id",
            "case475_receipt_raw_octets",
            "case475_receipt_raw_sha256",
            "case475_resource_report_id",
            "case475_resource_vector",
            "case475_stream_sha256",
            "case475_upper_certificate_id",
            "case475_winning_absolute_delta",
            "case475_winning_member_name",
            "case475_winning_mutated_value",
            "contract_variance_policy",
            "core_matrix_passed",
            "correction_subgate",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "lower_compatibility_passed",
            "next_subgate",
            "ordered_remaining_case_positions",
            "p6_filtered_passed",
            "p6_unfiltered_expected_failed",
            "p6_unfiltered_passed",
            "packed_v3_v4_compatibility_passed",
            "producer_expansion_state",
            "runner_state",
            "source_isolation_state",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_file_headroom",
            "successor_authority_octets",
            "successor_authority_octet_headroom",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "total_case475_input_file_count",
            "total_case475_input_file_headroom",
            "total_case475_input_octets",
            "total_case475_input_octet_headroom",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
            "worst_case435_input_file_count",
            "worst_case435_input_octets",
            "worst_case435_input_octet_headroom",
        },
        "S1-A4 verifier-expansion V4 snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V4"
        and snapshot["acceptance_state"]
        == "LOCAL_MINIMALITY_CASE_475_AND_CONSOLIDATED_F2_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V-A"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69, 435, 475]
        and snapshot["ordered_remaining_case_positions"] == []
        and snapshot["focused_passed"] == 16
        and snapshot["lower_compatibility_passed"] == 83
        and snapshot["packed_v3_v4_compatibility_passed"] == 61
        and snapshot["core_matrix_passed"] == 503
        and snapshot["a4_t_filtered_passed"] == 59
        and snapshot["a4_t_unfiltered_passed"] == 61
        and snapshot["a4_t_unfiltered_expected_failed"] == 1
        and snapshot["p6_filtered_passed"] == 13
        and snapshot["p6_unfiltered_passed"] == 13
        and snapshot["p6_unfiltered_expected_failed"] == 6
        and snapshot["producer_expansion_state"] == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and snapshot["runner_state"]
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED"
        and snapshot["source_isolation_state"]
        == "STATIC_STANDARD_LIBRARY_ONLY_NO_DYNAMIC_CODE_LOADING"
        and snapshot["contract_variance_policy"]
        == "CORRECTED_LOCAL_CERTIFICATE_FIELD_PLUS_EXECUTABLE_GENERIC_RESOURCE_REPORT",
        "S1-A4 verifier-expansion V4 state differs",
    )
    _require(
        v3_snapshot["next_subgate"] == "A4-P6-V4"
        and snapshot["source_marker"] == v3_snapshot["source_marker"]
        and snapshot["successor_constructive_boundary_id"]
        == v3_snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == v3_snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"],
        "S1-A4 verifier-expansion V4 authority binding differs",
    )

    for label, path, octets, digest in (
        (
            "verifier",
            INDEPENDENT_VERIFIER_PATH,
            snapshot["verifier_raw_octets"],
            snapshot["verifier_raw_sha256"],
        ),
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V4_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V4_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(), f"S1-A4 V4 {label} is absent"
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V4 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V4 {label} hash drifted")

    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    authority_octets = (
        v3_snapshot["successor_authority_octets"]
        - v3_snapshot["verifier_raw_octets"]
        + snapshot["verifier_raw_octets"]
    )
    case475_files = snapshot["successor_authority_file_count"] + 1
    case475_octets = authority_octets + snapshot["case475_candidate_raw_octets"]
    worst_case435_octets = (
        v3_snapshot["total_input_octets"]
        - v3_snapshot["verifier_raw_octets"]
        + snapshot["verifier_raw_octets"]
    )
    _require(
        file_limit == 64
        and octet_limit == 67_108_864
        and snapshot["successor_authority_file_count"]
        == v3_snapshot["successor_authority_file_count"]
        == 39
        and snapshot["successor_authority_file_headroom"] == 25
        and snapshot["successor_authority_octets"] == authority_octets
        and snapshot["successor_authority_octet_headroom"]
        == octet_limit - authority_octets
        and snapshot["total_case475_input_file_count"] == case475_files == 40
        and snapshot["total_case475_input_file_headroom"] == 24
        and snapshot["total_case475_input_octets"] == case475_octets
        and snapshot["total_case475_input_octet_headroom"]
        == octet_limit - case475_octets
        and snapshot["worst_case435_input_file_count"] == 41
        and snapshot["worst_case435_input_octets"] == worst_case435_octets
        and snapshot["worst_case435_input_octet_headroom"]
        == octet_limit - worst_case435_octets
        and case475_files <= file_limit
        and case475_octets <= octet_limit
        and worst_case435_octets <= octet_limit,
        "S1-A4 V4 F0 footprint differs",
    )
    _require(
        snapshot["case475_baseline_operation_spec_id"]
        == "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
        and snapshot["case475_mutated_operation_spec_id"]
        == "572155284c3b8b0852b406d5cbce662aba7579180f89ee3740a6c86ede66f16a"
        and snapshot["case475_plan_id"]
        == "2d46a1b71c9466fd3268b93dbc3e4a62a4855dd0324f4cfecfbb60d4589bbbc0"
        and snapshot["case475_profile_id"]
        == "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
        and snapshot["case475_winning_member_name"]
        == "maximum_terminal_ingress_batches"
        and snapshot["case475_winning_mutated_value"] == 1_948
        and snapshot["case475_winning_absolute_delta"] == 1_947
        and snapshot["case475_predecessor_maximum_octets"] == 524_112
        and snapshot["case475_exact_maximum_octets"] == 524_380
        and snapshot["case475_candidate_id"]
        == "ee38407312f872f0d8dc3f5d6b3ebe9990f294ce245b406ba3e33cce243dcb42"
        and snapshot["case475_candidate_raw_octets"] == 614_566
        and snapshot["case475_candidate_raw_sha256"]
        == "bdf7f8e4213cbf51b70b2dac0bdc97ffd1d55304b37bd3d20b8b9d54ba7977dc"
        and snapshot["case475_prospective_result_id"]
        == "8a22dfcb61a9e083c2edccc7902d0e4e414c8be4d130570a495b1cdecb1a014c"
        and snapshot["case475_local_proof_scope_id"]
        == "4db3b0d60c9487e2b0913cf54fc05fa88ee5cac9e7aa979b3c97d6d46d1974b1"
        and snapshot["case475_upper_certificate_id"]
        == "bc4594ce40f5ba4d80276ae1eec89c34f2e9eaff8328834093fa1e2cfa4dd118"
        and snapshot["case475_better_objective_exclusion_sha256"]
        == "4cf7a46c0488d044368be412db5f837be5b4bd8f5c71907df83271d89d5cceb9"
        and snapshot["case475_minimality_certificate_id"]
        == "62c6c97f9af5a8f4924f45a4c4e2d144d93eb17cd84d5b17b0cd06af6eb15792"
        and snapshot["case475_resource_report_id"]
        == "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8"
        and snapshot["case475_local_result_id"]
        == "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73"
        and snapshot["case475_local_result_raw_octets"] == 604_156
        and snapshot["case475_local_result_raw_sha256"]
        == "a1e1316c970e60db198d8775eeb89a1e0eb7e4cdda5ddca64f54c666130fb7f8"
        and snapshot["case475_receipt_id"]
        == "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f"
        and snapshot["case475_receipt_raw_octets"] == 3_173
        and snapshot["case475_receipt_raw_sha256"]
        == "93b1ab8dc2fdbbd8dadabae5bd5591f8129d0ce2611f6bb1d25e74f46078f5b2",
        "S1-A4 V4 case475 exact result differs",
    )
    expected_vector = [
        1,
        11,
        12,
        11,
        11,
        0,
        12,
        9_591,
        20_047,
        28_612,
        49_103,
        4,
        1,
        1,
        1,
        11,
        18_156,
        672,
    ]
    manifest = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())
    _require(
        snapshot["case475_resource_vector"] == expected_vector
        and snapshot["case475_stream_sha256"]
        == "5f2f61d0f9f09174d3bb17288c02f36d9ec7ec358468d36ed19a2e44958cbbb3"
        and all(
            measured <= limit["f2_per_case"]
            for measured, limit in zip(
                expected_vector,
                manifest["ordered_f2_limit_records"],
                strict=True,
            )
        ),
        "S1-A4 V4 case475 resource result differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    _require(
        imports == {"hashlib", "json", "os", "pathlib", "stat", "sys", "tempfile"}
        and calls.isdisjoint({"__import__", "compile", "eval", "exec"})
        and "CASE475_POSITION = 475" in source
        and "V4_SUCCESSOR_CASE_POSITIONS" in source
        and "def _execute_local_minimality" in source
        and "def _local_case_units" in source
        and "local_shutdown_minimality_certificate_id" in source
        and "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py" not in source,
        "S1-A4 V4 static source isolation differs",
    )
    test_source = INDEPENDENT_VERIFIER_EXPANSION_V4_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_case475_is_exact_deterministic_immutable_and_f2_bounded",
        "test_case475_rejects_equal_predecessor_or_wrong_winning_mutation",
        "test_case475_rejects_a_resealed_multi_field_mutation",
        "test_case475_rejects_resealed_prospective_result_substitutions",
        "test_case475_rejects_a_resealed_producer_proof_claim",
        "test_case475_requires_the_packed_successor_authority_mode",
        "test_case475_requires_an_empty_context_root",
        "test_v4_source_is_static_and_isolated_from_producers_and_proof_checkers",
    ):
        _require(test_name in test_source, f"S1-A4 V4 test absent: {test_name}")
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V4_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V4",
        "A4-P6-V-A",
        snapshot["verifier_raw_sha256"],
        snapshot["verifier_test_raw_sha256"],
        snapshot["case475_stream_sha256"],
        snapshot["case475_local_result_id"],
        snapshot["case475_minimality_certificate_id"],
        "524,380",
        "503 passed",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V4 acceptance marker absent: {marker}")


def _validate_s1_a4_verifier_acceptance_snapshot(
    snapshot: dict[str, Any],
    v4_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_p6_expected_red_failed",
            "a4_p6_expected_red_passed",
            "a4_p6_expected_red_skipped",
            "a4_t_expected_red_failed",
            "a4_t_expected_red_passed",
            "a4_t_expected_red_skipped",
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_closure_id",
            "authority_file_count",
            "authority_file_headroom",
            "authority_octets",
            "authority_octet_headroom",
            "candidate_and_context_immutability",
            "case_acceptance_record_count",
            "core_matrix_passed",
            "correction_subgate",
            "focused_passed",
            "formal_verifier_gate_state",
            "next_subgate",
            "ordered_authority_modes",
            "producer_expansion_state",
            "report_id",
            "report_raw_octets",
            "report_raw_sha256",
            "reviewed_fixture_source_count",
            "reviewer_raw_octets",
            "reviewer_raw_sha256",
            "runner_state",
            "source_isolation_state",
            "source_marker",
            "test_raw_octets",
            "test_raw_sha256",
            "verifier_raw_sha256",
            "verifier_replay_passed",
        },
        "S1-A4 verifier-acceptance snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V-A"
        and snapshot["acceptance_state"] == "INDEPENDENT_V0_V4_VERIFIER_ACCEPTED"
        and snapshot["formal_verifier_gate_state"] == "ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-P"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69, 435, 475]
        and snapshot["ordered_authority_modes"]
        == [
            "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        ]
        and snapshot["focused_passed"] == 37
        and snapshot["core_matrix_passed"] == 542
        and snapshot["verifier_replay_passed"] == 128
        and snapshot["case_acceptance_record_count"] == 7
        and snapshot["reviewed_fixture_source_count"] == 10
        and snapshot["a4_t_expected_red_failed"] == 1
        and snapshot["a4_t_expected_red_passed"] == 61
        and snapshot["a4_t_expected_red_skipped"] == 2
        and snapshot["a4_p6_expected_red_failed"] == 6
        and snapshot["a4_p6_expected_red_passed"] == 13
        and snapshot["a4_p6_expected_red_skipped"] == 2
        and snapshot["producer_expansion_state"]
        == "RELEASED_FOR_A4_P6_P_IMPLEMENTATION"
        and snapshot["runner_state"] == "HOLD_UNTIL_PRODUCER_EXPANSION_ACCEPTED"
        and snapshot["source_isolation_state"]
        == "STATIC_STANDARD_LIBRARY_ONLY_NO_DYNAMIC_CODE_LOADING"
        and snapshot["candidate_and_context_immutability"]
        == "VERIFIED_BY_PINNED_DOUBLE_RUN_AND_HOSTILE_REPLAY",
        "S1-A4 verifier-acceptance state differs",
    )
    _require(
        v4_snapshot["next_subgate"] == "A4-P6-V-A"
        and v4_snapshot["accepted_case_positions"]
        == snapshot["accepted_case_positions"]
        and v4_snapshot["verifier_raw_sha256"] == snapshot["verifier_raw_sha256"],
        "S1-A4 verifier-acceptance predecessor binding differs",
    )

    artifact_rows = (
        (
            "reviewer",
            INDEPENDENT_VERIFIER_ACCEPTANCE_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "test",
            INDEPENDENT_VERIFIER_ACCEPTANCE_TEST_PATH,
            snapshot["test_raw_octets"],
            snapshot["test_raw_sha256"],
        ),
        (
            "report",
            INDEPENDENT_VERIFIER_ACCEPTANCE_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "acceptance document",
            INDEPENDENT_VERIFIER_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifact_rows:
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 V-A {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V-A {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V-A {label} hash drifted")
        artifact_bytes[label] = raw

    report = json.loads(artifact_bytes["report"])
    _require(
        set(report)
        == {
            "acceptance_report_version",
            "authority_closure",
            "candidate_and_context_immutability",
            "control_checkpoint",
            "formal_stage1_state",
            "independent_verifier_acceptance_report_id",
            "next_subgate",
            "ordered_case_acceptance_records",
            "parent_runner_state",
            "predecessor_finalization_manifest_id",
            "predecessor_seed_catalog_id",
            "producer_expansion_state",
            "review_decision",
            "reviewer_source",
            "runtime_evidence",
            "source_marker",
            "static_isolation",
            "successor_f2_resource_limit_catalog_id",
            "successor_finalization_manifest_id",
            "successor_seed_catalog_id",
            "verifier_source",
        },
        "S1-A4 V-A report members differ",
    )
    report_payload = {
        name: value
        for name, value in report.items()
        if name != "independent_verifier_acceptance_report_id"
    }
    recomputed_report_id = _sha256(
        _canonical_bytes(
            {
                "domain": INDEPENDENT_VERIFIER_ACCEPTANCE_REPORT_DOMAIN,
                "payload": report_payload,
            }
        )
    )
    _require(
        report["independent_verifier_acceptance_report_id"]
        == snapshot["report_id"]
        == recomputed_report_id,
        "S1-A4 V-A report identity differs",
    )
    _require(
        report["acceptance_report_version"]
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "independent_verifier_acceptance_report.v1"
        and report["source_marker"] == snapshot["source_marker"]
        and report["review_decision"] == "ACCEPTED"
        and report["formal_stage1_state"] == "NO-GO"
        and report["next_subgate"] == "A4-P6-P"
        and report["producer_expansion_state"] == "HELD"
        and report["parent_runner_state"] == "ABSENT_AND_HELD"
        and report["candidate_and_context_immutability"]
        == snapshot["candidate_and_context_immutability"],
        "S1-A4 V-A report state differs",
    )
    _require(
        report["reviewer_source"]
        == {
            "repository_relative_path": (
                "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
                "independent_verifier_v49f.py"
            ),
            "raw_octets": snapshot["reviewer_raw_octets"],
            "raw_sha256": snapshot["reviewer_raw_sha256"],
        }
        and report["verifier_source"]
        == {
            "repository_relative_path": (
                "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
                "candidate_v49f.py"
            ),
            "raw_octets": v4_snapshot["verifier_raw_octets"],
            "raw_sha256": snapshot["verifier_raw_sha256"],
        },
        "S1-A4 V-A source binding differs",
    )

    authority = report["authority_closure"]
    authority_records = authority["ordered_authority_records"]
    _require(
        authority["authority_closure_sha256"] == snapshot["authority_closure_id"]
        and authority["input_file_count"] == snapshot["authority_file_count"] == 39
        and authority["input_file_headroom"]
        == snapshot["authority_file_headroom"]
        == 25
        and authority["total_pinned_input_octets"]
        == snapshot["authority_octets"]
        == 29_004_595
        and authority["total_pinned_input_octet_headroom"]
        == snapshot["authority_octet_headroom"]
        == 38_104_269
        and len(authority_records) == 39
        and _sha256(_canonical_bytes(authority_records))
        == snapshot["authority_closure_id"],
        "S1-A4 V-A authority closure differs",
    )
    paths = [row["repository_relative_path"] for row in authority_records]
    _require(
        paths == sorted(paths) and len(paths) == len(set(paths)),
        "S1-A4 V-A authority path order differs",
    )
    for row in authority_records:
        path = ROOT / row["repository_relative_path"]
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 V-A authority absent: {row['repository_relative_path']}",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == row["raw_octets"] and _sha256(raw) == row["raw_sha256"],
            f"S1-A4 V-A authority drifted: {row['repository_relative_path']}",
        )

    expected_cases = [
        (
            "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
            5,
            29,
            "ae6b76bc72b20531f8e72b5ccc40ef9450329d5d0165698a7230a982f5725272",
            "2b270c5b6f5df06cd5b3c781642d4a8878d62be6e5014db95d1eaa72970150fd",
            "e0bcabae55dba9f0b1e14b370c31aeb8ea93124a4ac2b2ac7754d4e1cbcbee37",
            [1, 3, 4, 8, 8, 0, 4, 2684, 8104, 10384, 33573, 0, 0, 0, 3, 3, 3783, 1359],
        ),
        (
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            5,
            29,
            "f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f",
            "de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba",
            "375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee",
            [1, 3, 4, 8, 8, 0, 4, 2684, 8104, 10384, 33573, 0, 0, 0, 3, 3, 3783, 1359],
        ),
        (
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            24,
            523_738,
            "2c9054a363632a7f0da2dace72677155df9bbf2f4527bc5ff3ab952f96d32876",
            "46d69394ea4b0a1ef555b9cd0e097fe5827b67b9a64aa573595adba29e45510d",
            "940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107",
            [
                1,
                2101277,
                39,
                459,
                4202945,
                5,
                39,
                26493,
                340068,
                362505,
                488331,
                1,
                0,
                0,
                6,
                32,
                36304,
                9469,
            ],
        ),
        (
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            54,
            3_145_728,
            "3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1",
            "2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81",
            "bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451",
            [
                1,
                515,
                5,
                9,
                1031,
                1,
                5,
                3415,
                9775,
                12712,
                41372,
                1,
                0,
                0,
                4,
                9,
                3937,
                1589,
            ],
        ),
        (
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            69,
            2_581,
            "1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e",
            "fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e",
            "48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740",
            [
                1,
                2101890,
                157,
                829,
                4204335,
                7,
                157,
                105752,
                673168,
                763519,
                1380238,
                6,
                1,
                1,
                14,
                32,
                50016,
                36961,
            ],
        ),
        (
            "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
            435,
            257_887,
            "0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f",
            "fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd",
            "3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9",
            [
                1,
                35384,
                158,
                1002,
                347899,
                4,
                158,
                106269,
                789225,
                879955,
                1480733,
                10,
                12531,
                137,
                17,
                137,
                38451,
                37195,
            ],
        ),
        (
            "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
            475,
            524_380,
            "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73",
            "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f",
            "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8",
            [
                1,
                11,
                12,
                11,
                11,
                0,
                12,
                9591,
                20047,
                28612,
                49103,
                4,
                1,
                1,
                1,
                11,
                18156,
                672,
            ],
        ),
    ]
    case_records = report["ordered_case_acceptance_records"]
    actual_cases = [
        (
            row["authority_mode"],
            row["case_position"],
            row["maximum_octets"],
            row["result_artifact_id"],
            row["verification_receipt_id"],
            row["proof_resource_report_id"],
            row["resource_vector"],
        )
        for row in case_records
    ]
    _require(actual_cases == expected_cases, "S1-A4 V-A case ledger differs")
    limits = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())[
        "ordered_f2_limit_records"
    ]
    for row in case_records:
        margins = [
            limit["f2_per_case"] - measured
            for measured, limit in zip(row["resource_vector"], limits, strict=True)
        ]
        _require(
            len(margins) == 18 and min(margins) >= 0 and row["f2_margins"] == margins,
            f"S1-A4 V-A F2 result differs for case {row['case_position']}",
        )

    expected_runtime = {
        "verifier_replay": {
            "passed": 128,
            "failed": 0,
            "skipped": 0,
            "test_artifact_count": 10,
        },
        "a4_t_expected_red": {
            "failed": 1,
            "passed": 61,
            "skipped": 2,
            "ordered_failure_codes": ["A4_T_PARENT_PILOT_RUNNER_MISSING"],
        },
        "a4_p6_expected_red": {
            "failed": 6,
            "passed": 13,
            "skipped": 2,
            "ordered_failure_codes": [
                "A4_P6_CASE_24_PRODUCER_NOT_QUALIFIED",
                "A4_P6_CASE_54_PRODUCER_NOT_QUALIFIED",
                "A4_P6_CASE_69_PRODUCER_NOT_QUALIFIED",
                "A4_P6_CASE_435_PRODUCER_NOT_QUALIFIED",
                "A4_P6_CASE_475_PRODUCER_NOT_QUALIFIED",
                "A4_P6_PARENT_RUNNER_MISSING",
            ],
        },
    }
    _require(
        report["runtime_evidence"] == expected_runtime,
        "S1-A4 V-A runtime evidence differs",
    )
    _require(
        report["static_isolation"]
        == {
            "reviewed_fixture_source_count": 10,
            "reviewed_fixture_sources_sha256": (
                "0477b314a12dfeeacbb895edcacd26633e37330fb25bfa548b070a58b8e446e1"
            ),
            "verifier": {
                "allowed_imports": [
                    "hashlib",
                    "json",
                    "os",
                    "pathlib",
                    "stat",
                    "sys",
                    "tempfile",
                ],
                "dynamic_code_loading": False,
                "producer_or_proof_checker_imports": False,
                "resource_limit_enforcement": "MEASURED_LE_F2_PER_CASE",
            },
        },
        "S1-A4 V-A source isolation differs",
    )

    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    test_source = artifact_bytes["test"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "INDEPENDENT_V0_V4_VERIFIER_ACCEPTANCE_REVIEWER_V1",
        "def _runtime_review",
        "def _validate_case_ledger",
        "def _static_isolation",
        "def _publish_report",
    ):
        _require(
            marker in reviewer_source, f"S1-A4 V-A reviewer marker absent: {marker}"
        )
    for marker in (
        "test_v_a_reviewer_executes_full_replay_and_matches_frozen_report",
        "test_f2_enforcement_accepts_minus_one_and_exact_but_rejects_plus_one",
        "test_reviewer_source_is_static_and_never_imports_reviewed_roles",
        snapshot["report_id"],
    ):
        _require(marker in test_source, f"S1-A4 V-A test marker absent: {marker}")
    for marker in (
        "A4-P6-V-A",
        "A4-P6-P",
        snapshot["report_id"],
        snapshot["report_raw_sha256"],
        snapshot["reviewer_raw_sha256"],
        snapshot["test_raw_sha256"],
        "128 passed",
        "37 passed",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V-A acceptance marker absent: {marker}")


def _validate_s1_a4_producer_expansion_snapshot(
    snapshot: dict[str, Any],
    producer_snapshot: dict[str, Any],
    verifier_acceptance_snapshot: dict[str, Any],
    context_pack_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_p6_expected_red_failed",
            "a4_p6_expected_red_passed",
            "a4_p6_expected_red_skipped",
            "a4_t_expected_red_failed",
            "a4_t_expected_red_passed",
            "a4_t_expected_red_skipped",
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "acceptance_test_raw_octets",
            "acceptance_test_raw_sha256",
            "accepted_case_positions",
            "candidate_immutability",
            "correction_subgate",
            "direct_producer_runs",
            "direct_verifier_runs",
            "formal_stage1_state",
            "historical_producer_raw_sha256",
            "historical_v_a_report_id",
            "next_subgate",
            "packed_boundary_id",
            "parent_runner_state",
            "producer_raw_octets",
            "producer_raw_sha256",
            "qualification_passed",
            "qualification_test_raw_octets",
            "qualification_test_raw_sha256",
            "report_id",
            "report_raw_octets",
            "report_raw_sha256",
            "reviewer_raw_octets",
            "reviewer_raw_sha256",
            "source_isolation_state",
            "verifier_raw_octets",
            "verifier_raw_sha256",
        },
        "S1-A4 producer-expansion snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-P"
        and snapshot["acceptance_state"] == "SEPARATE_PRODUCER_EXPANSION_ACCEPTED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_subgate"] == "A4-P6-R"
        and snapshot["parent_runner_state"] == "ABSENT_AND_HELD"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69, 435, 475]
        and snapshot["direct_producer_runs"] == 12
        and snapshot["direct_verifier_runs"] == 12
        and snapshot["qualification_passed"] == 17
        and snapshot["a4_t_expected_red_passed"] == 61
        and snapshot["a4_t_expected_red_skipped"] == 2
        and snapshot["a4_t_expected_red_failed"] == 1
        and snapshot["a4_p6_expected_red_passed"] == 13
        and snapshot["a4_p6_expected_red_skipped"] == 2
        and snapshot["a4_p6_expected_red_failed"] == 6
        and snapshot["candidate_immutability"]
        == "VERIFIED_BY_TWO_PASS_INDEPENDENT_REPLAY"
        and snapshot["source_isolation_state"]
        == "STATIC_STANDARD_LIBRARY_ONLY_NO_REVIEWED_ROLE_IMPORTS",
        "S1-A4 producer-expansion state differs",
    )
    _require(
        snapshot["historical_producer_raw_sha256"]
        == producer_snapshot["producer_raw_sha256"]
        and snapshot["historical_v_a_report_id"]
        == verifier_acceptance_snapshot["report_id"]
        and snapshot["packed_boundary_id"]
        == context_pack_snapshot["case435_context_pack_boundary_delta_id"]
        and snapshot["verifier_raw_sha256"]
        == verifier_acceptance_snapshot["verifier_raw_sha256"],
        "S1-A4 producer-expansion predecessor binding differs",
    )

    artifact_rows = (
        (
            "producer",
            SEPARATE_PRODUCER_PATH,
            snapshot["producer_raw_octets"],
            snapshot["producer_raw_sha256"],
        ),
        (
            "qualification test",
            SEPARATE_PRODUCER_EXPANSION_TEST_PATH,
            snapshot["qualification_test_raw_octets"],
            snapshot["qualification_test_raw_sha256"],
        ),
        (
            "reviewer",
            SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "report",
            SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "acceptance test",
            SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            SEPARATE_PRODUCER_EXPANSION_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifact_rows:
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 P6-P {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 P6-P {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 P6-P {label} hash drifted")
        artifact_bytes[label] = raw
    verifier_raw = INDEPENDENT_VERIFIER_PATH.read_bytes()
    _require(
        len(verifier_raw) == snapshot["verifier_raw_octets"]
        and _sha256(verifier_raw) == snapshot["verifier_raw_sha256"],
        "S1-A4 P6-P verifier identity drifted",
    )

    report = json.loads(artifact_bytes["report"])
    payload = {
        name: value
        for name, value in report.items()
        if name != "separate_producer_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {"domain": SEPARATE_PRODUCER_EXPANSION_REPORT_DOMAIN, "payload": payload}
        )
    )
    _require(
        report.get("separate_producer_acceptance_report_id")
        == snapshot["report_id"]
        == report_id,
        "S1-A4 P6-P report identity differs",
    )
    _require(
        report.get("acceptance_report_version")
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "separate_producer_expansion_acceptance_report.v1"
        and report.get("source_marker")
        == "INDEPENDENT_V2_SEPARATE_PRODUCER_EXPANSION_REVIEWER_V1"
        and report.get("review_decision") == "ACCEPTED"
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_subgate") == "A4-P6-R"
        and report.get("parent_runner_state") == "ABSENT_AND_HELD",
        "S1-A4 P6-P report state differs",
    )
    _require(
        report["producer_source"]
        == {
            "repository_relative_path": str(SEPARATE_PRODUCER_PATH.relative_to(ROOT)),
            "raw_octets": snapshot["producer_raw_octets"],
            "raw_sha256": snapshot["producer_raw_sha256"],
        }
        and report["verifier_source"]
        == {
            "repository_relative_path": str(
                INDEPENDENT_VERIFIER_PATH.relative_to(ROOT)
            ),
            "raw_octets": snapshot["verifier_raw_octets"],
            "raw_sha256": snapshot["verifier_raw_sha256"],
        },
        "S1-A4 P6-P role-source binding differs",
    )
    historical = report["historical_checkpoint"]
    _require(
        historical["a4_p_predecessor_producer"]["raw_sha256"]
        == snapshot["historical_producer_raw_sha256"]
        and historical["a4_p6_v_a_report_id"] == snapshot["historical_v_a_report_id"],
        "S1-A4 P6-P historical checkpoint differs",
    )
    _require(
        report["static_isolation"]
        == {
            "accepted_verifier_answer_literals": False,
            "allowed_imports": [
                "hashlib",
                "itertools",
                "json",
                "os",
                "pathlib",
                "stat",
                "sys",
                "typing",
            ],
            "dynamic_code_loading": False,
            "reviewed_role_imports": False,
        },
        "S1-A4 P6-P isolation report differs",
    )

    expected_cases = [
        (
            5,
            29,
            "f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f",
            "de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba",
            "375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee",
        ),
        (
            24,
            523_738,
            "55b5ecc89c5954d891be187220d649a510a136957d1a1a2f41d98a4766d3555d",
            "65066d0c7c5b45400a79fbc7caae90c79f98a00ba3125f4f890482a127a23096",
            "940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107",
        ),
        (
            54,
            3_145_728,
            "3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1",
            "2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81",
            "bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451",
        ),
        (
            69,
            2_581,
            "1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e",
            "fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e",
            "48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740",
        ),
        (
            435,
            257_887,
            "0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f",
            "fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd",
            "3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9",
        ),
        (
            475,
            524_380,
            "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73",
            "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f",
            "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8",
        ),
    ]
    observed_cases = [
        (
            row["case_position"],
            row["maximum_octets"],
            row["result_artifact_id"],
            row["verification_receipt_id"],
            row["proof_resource_report_id"],
        )
        for row in report["ordered_case_acceptance_records"]
    ]
    _require(observed_cases == expected_cases, "S1-A4 P6-P case ledger differs")
    runtime = report["runtime_evidence"]
    _require(
        runtime["direct_packed_successor_replay"]
        == {
            "byte_determinism": "VERIFIED",
            "candidate_immutability": "VERIFIED",
            "case_count": 6,
            "producer_runs": 12,
            "verifier_runs": 12,
        }
        and runtime["successor_qualification"]
        == {"failed": 0, "passed": 17, "skipped": 0}
        and runtime["a4_t_expected_red"]["failed"] == 1
        and runtime["a4_p6_predecessor_expected_red"]["failed"] == 6,
        "S1-A4 P6-P runtime evidence differs",
    )
    _require(
        report["parent_runner_state"] == "ABSENT_AND_HELD",
        "S1-A4 P6-P historical runner state differs",
    )

    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    for marker in (
        "A4-P6-P",
        "A4-P6-R",
        snapshot["report_id"],
        snapshot["report_raw_sha256"],
        snapshot["producer_raw_sha256"],
        "17 passed",
        "12 producer runs",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 P6-P acceptance marker absent: {marker}")
    for marker in (
        "test_full_reviewer_replay_matches_frozen_report",
        "test_historical_acceptance_is_archived_and_not_collected_as_current",
        "test_parent_runner_is_still_absent",
        snapshot["report_id"],
    ):
        _require(marker in acceptance_test, f"S1-A4 P6-P test marker absent: {marker}")


def _validate_s1_a4_parent_runner_snapshot(
    snapshot: dict[str, Any],
    producer_expansion_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "acceptance_test_raw_octets",
            "acceptance_test_raw_sha256",
            "accepted_case_positions",
            "all_or_nothing_publication",
            "candidate_immutability",
            "correction_subgate",
            "direct_parent_transactions",
            "direct_producer_runs",
            "direct_verifier_runs",
            "formal_stage1_state",
            "frozen_role_contract_passed",
            "full_run_f2_values",
            "historical_producer_report_id",
            "next_subgate",
            "producer_raw_sha256",
            "qualification_passed",
            "qualification_test_raw_octets",
            "qualification_test_raw_sha256",
            "read_only_check",
            "report_id",
            "report_raw_octets",
            "report_raw_sha256",
            "reviewer_raw_octets",
            "reviewer_raw_sha256",
            "runner_raw_octets",
            "runner_raw_sha256",
            "source_isolation_state",
            "source_marker",
            "verifier_raw_sha256",
        },
        "S1-A4 parent-runner snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-R"
        and snapshot["acceptance_state"] == "PARENT_PILOT_RUNNER_ACCEPTED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_subgate"] == "A4-P6-E"
        and snapshot["accepted_case_positions"] == [5, 24, 54, 69, 435, 475]
        and snapshot["direct_parent_transactions"] == 2
        and snapshot["direct_producer_runs"] == 12
        and snapshot["direct_verifier_runs"] == 12
        and snapshot["qualification_passed"] == 7
        and snapshot["frozen_role_contract_passed"] == 64
        and snapshot["candidate_immutability"]
        == "VERIFIED_ACROSS_ALL_SIX_VERIFIER_CHILD_RUNS"
        and snapshot["all_or_nothing_publication"]
        == "VERIFIED_WITH_ROOT_LAST_PUBLICATION_AND_INJECTED_ROLLBACK"
        and snapshot["read_only_check"] == "VERIFIED_BYTE_AND_MODE_STABLE"
        and snapshot["source_isolation_state"]
        == "PARENT_ONLY_STANDARD_LIBRARY_FIXED_EXECVE_NO_ACCEPTED_ANSWER_LITERALS",
        "S1-A4 parent-runner state differs",
    )
    _require(
        snapshot["historical_producer_report_id"]
        == producer_expansion_snapshot["report_id"]
        and snapshot["producer_raw_sha256"]
        == producer_expansion_snapshot["producer_raw_sha256"]
        and snapshot["verifier_raw_sha256"]
        == producer_expansion_snapshot["verifier_raw_sha256"],
        "S1-A4 parent-runner predecessor binding differs",
    )

    artifact_rows = (
        (
            "runner",
            PARENT_PILOT_RUNNER_PATH,
            snapshot["runner_raw_octets"],
            snapshot["runner_raw_sha256"],
        ),
        (
            "qualification test",
            PARENT_PILOT_RUNNER_TEST_PATH,
            snapshot["qualification_test_raw_octets"],
            snapshot["qualification_test_raw_sha256"],
        ),
        (
            "reviewer",
            PARENT_PILOT_RUNNER_ACCEPTANCE_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "report",
            PARENT_PILOT_RUNNER_ACCEPTANCE_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "acceptance test",
            PARENT_PILOT_RUNNER_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            PARENT_PILOT_RUNNER_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifact_rows:
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 P6-R {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 P6-R {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 P6-R {label} hash drifted")
        artifact_bytes[label] = raw

    report = json.loads(artifact_bytes["report"])
    payload = {
        name: value
        for name, value in report.items()
        if name != "parent_pilot_runner_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {"domain": PARENT_PILOT_RUNNER_REPORT_DOMAIN, "payload": payload}
        )
    )
    _require(
        report.get("parent_pilot_runner_acceptance_report_id")
        == snapshot["report_id"]
        == report_id,
        "S1-A4 P6-R report identity differs",
    )
    _require(
        report.get("acceptance_report_version")
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "parent_pilot_runner_acceptance_report.v1"
        and report.get("correction_subgate") == "A4-P6-R"
        and report.get("source_marker") == snapshot["source_marker"]
        and report.get("review_decision") == "ACCEPTED"
        and report.get("parent_runner_state") == "ACCEPTED"
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_subgate") == "A4-P6-E",
        "S1-A4 P6-R report state differs",
    )
    _require(
        report["historical_checkpoint"]["a4_p6_p_report_id"]
        == snapshot["historical_producer_report_id"]
        and report["historical_checkpoint"]["runner_absent_at_a4_p6_p_acceptance"]
        is True,
        "S1-A4 P6-R historical checkpoint differs",
    )
    _require(
        report["runner_source"]
        == {
            "repository_relative_path": str(PARENT_PILOT_RUNNER_PATH.relative_to(ROOT)),
            "raw_octets": snapshot["runner_raw_octets"],
            "raw_sha256": snapshot["runner_raw_sha256"],
        }
        and report["producer_source"]["raw_sha256"] == snapshot["producer_raw_sha256"]
        and report["verifier_source"]["raw_sha256"] == snapshot["verifier_raw_sha256"],
        "S1-A4 P6-R role-source binding differs",
    )
    runtime = report["runtime_evidence"]
    _require(
        runtime["direct_parent_transaction"]
        == {
            "all_or_nothing_publication": "VERIFIED",
            "byte_determinism": "VERIFIED",
            "candidate_immutability": "VERIFIED",
            "pilot_runs": 2,
            "producer_child_runs": 12,
            "read_only_check": "VERIFIED",
            "verifier_child_runs": 12,
        }
        and runtime["qualification_suite"] == {"failed": 0, "passed": 7, "skipped": 0}
        and runtime["frozen_role_contract_suite"]
        == {"failed": 0, "passed": 64, "skipped": 0},
        "S1-A4 P6-R runtime evidence differs",
    )
    _require(
        [row["case_position"] for row in report["ordered_case_acceptance_records"]]
        == snapshot["accepted_case_positions"],
        "S1-A4 P6-R case order differs",
    )
    f2_records = report["ordered_full_run_f2_reconciliation_records"]
    limits = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())[
        "ordered_f2_limit_records"
    ]
    _require(
        [row["measured_full_run_value"] for row in f2_records]
        == snapshot["full_run_f2_values"]
        and len(f2_records) == len(limits) == 18,
        "S1-A4 P6-R full-run vector differs",
    )
    for record, limit in zip(f2_records, limits, strict=True):
        _require(
            record
            == {
                "metric_position": limit["metric_position"],
                "metric_name": limit["metric_name"],
                "full_run_aggregation": limit["full_run_aggregation"],
                "measured_full_run_value": record["measured_full_run_value"],
                "f2_full_run": limit["f2_full_run"],
            }
            and record["measured_full_run_value"] <= limit["f2_full_run"],
            f"S1-A4 P6-R F2 reconciliation differs: {limit['metric_name']}",
        )

    runner_source = artifact_bytes["runner"].decode("utf-8")
    runner_tree = ast.parse(runner_source)
    calls = {
        node.func.attr
        for node in ast.walk(runner_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    role_rows = boundary["implementation_role_contract"]["ordered_role_records"]
    _require(
        role_rows[2]["source_marker"] in runner_source
        and role_rows[0]["source_marker"] not in runner_source
        and role_rows[1]["source_marker"] not in runner_source
        and {"fork", "execve", "wait4", "setrlimit"} <= calls,
        "S1-A4 P6-R source isolation differs",
    )
    for row in report["ordered_case_acceptance_records"]:
        for name in (
            "constructive_candidate_id",
            "verification_receipt_id",
            "verified_result_artifact_id",
        ):
            _require(
                row[name] not in runner_source,
                f"S1-A4 P6-R runner contains accepted answer: {name}",
            )

    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    for marker in (
        "A4-P6-R",
        "A4-P6-E",
        snapshot["report_id"],
        snapshot["report_raw_sha256"],
        snapshot["runner_raw_sha256"],
        "7 passed",
        "64 passed",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 P6-R acceptance marker absent: {marker}")
    for marker in (
        "test_full_independent_reviewer_replay_matches_frozen_report",
        "test_full_run_f2_modes_values_and_limits_are_exact",
        "test_report_identity_rejects_resealed_gate_or_resource_drift",
        snapshot["report_id"],
    ):
        _require(marker in acceptance_test, f"S1-A4 P6-R test marker absent: {marker}")


def _validate_s1_a4_pilot_end_to_end_snapshot(
    snapshot: dict[str, Any],
    parent_runner_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "acceptance_test_raw_octets",
            "acceptance_test_raw_sha256",
            "case_universe_count",
            "correction_subgate",
            "current_binaries_all_case_ready",
            "current_pilot_case_count",
            "design_raw_octets",
            "design_raw_sha256",
            "effective_parent_transactions_replayed",
            "effective_producer_child_runs_replayed",
            "effective_verifier_child_runs_replayed",
            "formal_stage1_state",
            "full_run_f2_values",
            "next_bounded_packet",
            "next_subgate",
            "non_pilot_case_count",
            "pilot_f2_implies_full_campaign_fit",
            "predecessor_runner_report_id",
            "qualification_rule",
            "release_decision",
            "release_criteria_passed",
            "report_id",
            "report_raw_octets",
            "report_raw_sha256",
            "reviewer_raw_octets",
            "reviewer_raw_sha256",
            "reviewer_replays",
            "source_marker",
        },
        "S1-A4 pilot end-to-end snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-E"
        and snapshot["acceptance_state"] == "SIX_CASE_END_TO_END_ACCEPTED"
        and snapshot["release_decision"]
        == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_subgate"] == "A4-R475"
        and snapshot["next_bounded_packet"] == "A4-R475-T"
        and snapshot["case_universe_count"] == 475
        and snapshot["current_pilot_case_count"] == 6
        and snapshot["non_pilot_case_count"] == 469
        and snapshot["current_binaries_all_case_ready"] is False
        and snapshot["pilot_f2_implies_full_campaign_fit"] is False
        and snapshot["reviewer_replays"] == 2
        and snapshot["effective_parent_transactions_replayed"] == 4
        and snapshot["effective_producer_child_runs_replayed"] == 24
        and snapshot["effective_verifier_child_runs_replayed"] == 24
        and snapshot["release_criteria_passed"] == 8
        and snapshot["qualification_rule"]
        == "ALL_SIX_CASES_PASS_TWICE_BYTE_IDENTICALLY_UNDER_IMMUTABLE_F2",
        "S1-A4 pilot end-to-end state differs",
    )
    _require(
        snapshot["predecessor_runner_report_id"] == parent_runner_snapshot["report_id"],
        "S1-A4 pilot end-to-end predecessor differs",
    )

    artifact_rows = (
        (
            "reviewer",
            SIX_CASE_END_TO_END_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "report",
            SIX_CASE_END_TO_END_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "acceptance test",
            SIX_CASE_END_TO_END_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "design",
            SIX_CASE_END_TO_END_DESIGN_PATH,
            snapshot["design_raw_octets"],
            snapshot["design_raw_sha256"],
        ),
        (
            "acceptance document",
            SIX_CASE_END_TO_END_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifact_rows:
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 P6-E {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 P6-E {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 P6-E {label} hash drifted")
        artifact_bytes[label] = raw

    report = json.loads(artifact_bytes["report"])
    payload = {
        name: value
        for name, value in report.items()
        if name != "six_case_end_to_end_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {"domain": SIX_CASE_END_TO_END_REPORT_DOMAIN, "payload": payload}
        )
    )
    _require(
        report.get("six_case_end_to_end_acceptance_report_id")
        == snapshot["report_id"]
        == report_id,
        "S1-A4 P6-E report identity differs",
    )
    _require(
        report.get("acceptance_report_version")
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "six_case_end_to_end_acceptance_report.v1"
        and report.get("correction_subgate") == "A4-P6-E"
        and report.get("source_marker") == snapshot["source_marker"]
        and report.get("review_decision") == "ACCEPTED"
        and report.get("release_decision") == snapshot["release_decision"]
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_subgate") == "A4-R475"
        and report.get("qualification_rule") == snapshot["qualification_rule"],
        "S1-A4 P6-E report state differs",
    )
    predecessor = report["predecessor_a4_p6_r"]
    _require(
        predecessor["report_id"] == parent_runner_snapshot["report_id"]
        and predecessor["report"]["raw_sha256"]
        == parent_runner_snapshot["report_raw_sha256"]
        and predecessor["reviewer"]["raw_sha256"]
        == parent_runner_snapshot["reviewer_raw_sha256"]
        and predecessor["runner"]["raw_sha256"]
        == parent_runner_snapshot["runner_raw_sha256"]
        and predecessor["producer"]["raw_sha256"]
        == parent_runner_snapshot["producer_raw_sha256"]
        and predecessor["verifier"]["raw_sha256"]
        == parent_runner_snapshot["verifier_raw_sha256"],
        "S1-A4 P6-E predecessor bindings differ",
    )
    _require(
        report["independent_replay_evidence"]
        == {
            "a4_p6_r_reviewer_replays": 2,
            "effective_parent_transactions_replayed": 4,
            "effective_producer_child_runs_replayed": 24,
            "effective_verifier_child_runs_replayed": 24,
            "frozen_report_match": "BOTH_BYTE_IDENTICAL",
            "reviewer_output_determinism": "VERIFIED",
        },
        "S1-A4 P6-E replay evidence differs",
    )
    _require(
        report["campaign_surface"]
        == {
            "case_universe_count": 475,
            "current_pilot_case_count": 6,
            "current_pilot_case_positions": [5, 24, 54, 69, 435, 475],
            "current_role_surface": "SIX_CASE_ONLY",
            "maximum_publication_case_count": 474,
            "non_pilot_case_count": 469,
            "local_minimality_case_count": 1,
            "release_scope": "VERSIONED_ALL_475_IMPLEMENTATION_THEN_EXECUTION",
            "unchanged_current_binaries_all_case_ready": False,
            "pilot_f2_implies_full_campaign_fit": False,
        },
        "S1-A4 P6-E campaign surface differs",
    )
    _require(
        [row["case_position"] for row in report["ordered_case_release_records"]]
        == [5, 24, 54, 69, 435, 475],
        "S1-A4 P6-E case order differs",
    )
    _require(
        [
            row["measured_full_run_value"]
            for row in report["ordered_full_run_f2_reconciliation_records"]
        ]
        == snapshot["full_run_f2_values"],
        "S1-A4 P6-E F2 vector differs",
    )
    _require(
        [row["criterion_position"] for row in report["ordered_release_criteria"]]
        == list(range(1, 9))
        and all(
            row["criterion_state"] == "PASS"
            for row in report["ordered_release_criteria"]
        ),
        "S1-A4 P6-E release criteria differ",
    )

    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    reviewer_tree = ast.parse(reviewer_source)
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        imports
        <= {
            "__future__",
            "argparse",
            "ast",
            "hashlib",
            "json",
            "os",
            "pathlib",
            "subprocess",
            "sys",
            "tempfile",
            "typing",
        }
        and "importlib" not in imports
        and snapshot["source_marker"] in reviewer_source,
        "S1-A4 P6-E reviewer isolation differs",
    )

    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    design = artifact_bytes["design"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "test_full_independent_reviewer_replay_matches_frozen_report",
        "test_resealed_gate_surface_case_replay_or_f2_drift_is_rejected",
        snapshot["report_id"],
        snapshot["report_raw_sha256"],
        snapshot["reviewer_raw_sha256"],
    ):
        _require(marker in acceptance_test, f"S1-A4 P6-E test marker absent: {marker}")
    for marker in (
        "A4-P6-E",
        "469",
        "versioned all-case",
        "FAIL-FIRST",
        "NO-GO",
    ):
        _require(marker in design, f"S1-A4 P6-E design marker absent: {marker}")
    for marker in (
        "A4-P6-E ACCEPTED",
        "A4-R475-T NEXT",
        snapshot["report_id"],
        "8 passed in 343.11s",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 P6-E acceptance marker absent: {marker}")


def _validate_s1_a4_all_case_contract_snapshot(
    snapshot: dict[str, Any],
    pilot_end_to_end_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "all_case_campaign_executed",
        "case_execution_ledger_id",
        "case_universe_count",
        "contract_id",
        "contract_raw_octets",
        "contract_raw_sha256",
        "correction_subgate",
        "design_raw_octets",
        "design_raw_sha256",
        "execution_family_counts",
        "f0_record_count",
        "f2_record_count",
        "fail_first_test_raw_octets",
        "fail_first_test_raw_sha256",
        "formal_stage1_state",
        "generator_raw_octets",
        "generator_raw_sha256",
        "intentional_missing_role_failures",
        "local_minimality_case_count",
        "maximum_publication_case_count",
        "next_bounded_packet",
        "ordered_case_execution_records_sha256",
        "predecessor_pilot_report_id",
        "report_id",
        "report_raw_octets",
        "report_raw_sha256",
        "required_full_run_f2_values",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "source_marker",
        "versioned_all_case_roles_accepted",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 all-case contract snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-R475-T"
        and snapshot["acceptance_state"] == "CONTRACT_ONLY_ACCEPTED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V0"
        and snapshot["case_universe_count"] == 475
        and snapshot["maximum_publication_case_count"] == 474
        and snapshot["local_minimality_case_count"] == 1
        and snapshot["f0_record_count"] == 12
        and snapshot["f2_record_count"] == 18
        and snapshot["acceptance_test_passed"] == 9
        and snapshot["intentional_missing_role_failures"] == 3
        and snapshot["versioned_all_case_roles_accepted"] is False
        and snapshot["all_case_campaign_executed"] is False,
        "S1-A4 all-case contract state differs",
    )
    _require(
        snapshot["predecessor_pilot_report_id"]
        == pilot_end_to_end_snapshot["report_id"],
        "S1-A4 all-case contract predecessor differs",
    )
    expected_families = {
        "CORRECTED_APPLICATION_EXACT_PROFILE": 1,
        "GENERIC_PROFILE_ATTAINMENT": 406,
        "INTRINSIC_TEMPLATE_ATTAINMENT": 66,
        "LOCAL_MINIMALITY": 1,
        "SIGNED_ANALYTIC_EXACT_PROFILE": 1,
    }
    _require(
        snapshot["execution_family_counts"] == expected_families,
        "S1-A4 all-case execution-family counts differ",
    )
    expected_f2 = [
        475,
        29_189_597,
        66_119,
        417_528,
        170_915_620,
        1_735,
        66_119,
        44_461_267,
        329_067_149,
        367_039_374,
        619_175_993,
        4_160,
        4_198_492,
        46_268,
        17,
        569,
        54_297,
        15_585_644,
    ]
    _require(
        snapshot["required_full_run_f2_values"] == expected_f2,
        "S1-A4 all-case required F2 vector differs",
    )

    artifacts = (
        (
            "generator",
            ALL_CASE_CAMPAIGN_CONTRACT_GENERATOR_PATH,
            snapshot["generator_raw_octets"],
            snapshot["generator_raw_sha256"],
        ),
        (
            "contract",
            ALL_CASE_CAMPAIGN_CONTRACT_PATH,
            snapshot["contract_raw_octets"],
            snapshot["contract_raw_sha256"],
        ),
        (
            "reviewer",
            ALL_CASE_CAMPAIGN_CONTRACT_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "report",
            ALL_CASE_CAMPAIGN_CONTRACT_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "acceptance test",
            ALL_CASE_CAMPAIGN_CONTRACT_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "fail-first test",
            ALL_CASE_CAMPAIGN_FAIL_FIRST_TEST_PATH,
            snapshot["fail_first_test_raw_octets"],
            snapshot["fail_first_test_raw_sha256"],
        ),
        (
            "design",
            ALL_CASE_CAMPAIGN_CONTRACT_DESIGN_PATH,
            snapshot["design_raw_octets"],
            snapshot["design_raw_sha256"],
        ),
        (
            "acceptance document",
            ALL_CASE_CAMPAIGN_CONTRACT_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"A4-R475-T {label} absent")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"A4-R475-T {label} size drifted")
        _require(_sha256(raw) == digest, f"A4-R475-T {label} hash drifted")
        artifact_bytes[label] = raw

    contract = json.loads(artifact_bytes["contract"])
    contract_payload = {
        name: value
        for name, value in contract.items()
        if name != "all_case_campaign_contract_id"
    }
    contract_id = _sha256(
        _canonical_bytes(
            {"domain": ALL_CASE_CAMPAIGN_CONTRACT_DOMAIN, "payload": contract_payload}
        )
    )
    _require(
        contract.get("all_case_campaign_contract_id")
        == snapshot["contract_id"]
        == contract_id,
        "S1-A4 all-case contract identity differs",
    )
    universe = contract["case_universe_contract"]
    rows = universe["ordered_case_execution_records"]
    _require(
        [row["case_position"] for row in rows] == list(range(1, 476))
        and universe["case_count"] == 475
        and universe["execution_family_counts"] == expected_families
        and universe["case_execution_ledger_id"]
        == snapshot["case_execution_ledger_id"]
        and universe["ordered_case_execution_records_sha256"]
        == snapshot["ordered_case_execution_records_sha256"],
        "S1-A4 all-case contract case ledger differs",
    )
    _require(
        contract["resource_contract"]["ordered_f0_limit_records"]
        and len(contract["resource_contract"]["ordered_f0_limit_records"]) == 12
        and [
            row["required_full_run"]
            for row in contract["resource_contract"]["ordered_f2_limit_records"]
        ]
        == expected_f2,
        "S1-A4 all-case contract resource ledger differs",
    )
    _require(
        contract["scheduler_and_checkpoint_contract"][
            "maximum_concurrent_case_attempts"
        ]
        == 1
        and contract["publication_contract"]["partial_acceptance_policy"]
        == "FORBIDDEN"
        and contract["gate_contract"]["next_bounded_packet_after_contract_acceptance"]
        == "A4-R475-V0",
        "S1-A4 all-case lifecycle contract differs",
    )

    report = json.loads(artifact_bytes["report"])
    report_payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_campaign_contract_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "domain": ALL_CASE_CAMPAIGN_CONTRACT_REPORT_DOMAIN,
                "payload": report_payload,
            }
        )
    )
    _require(
        report.get("all_case_campaign_contract_acceptance_report_id")
        == snapshot["report_id"]
        == report_id
        and report.get("source_marker") == snapshot["source_marker"]
        and report.get("review_decision") == "ACCEPTED_CONTRACT_ONLY"
        and report.get("next_bounded_packet") == "A4-R475-V0"
        and report.get("formal_stage1_state") == "NO-GO",
        "S1-A4 all-case acceptance report differs",
    )
    evidence = report["independent_reconstruction_evidence"]
    _require(
        evidence["case_count"] == 475
        and evidence["execution_family_counts"] == expected_families
        and evidence["f0_record_count"] == 12
        and evidence["f2_record_count"] == 18
        and evidence["required_full_run_f2_values"] == expected_f2,
        "S1-A4 all-case independent reconstruction differs",
    )

    generator_source = artifact_bytes["generator"].decode("utf-8")
    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    fail_first_source = artifact_bytes["fail-first test"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    design = artifact_bytes["design"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "A4_R475_T_ALL_CASE_CAMPAIGN_CONTRACT_GENERATOR_V1",
        "STRICT_SEQUENTIAL_SINGLE_WRITER_V1",
        "A4-R475-V0",
    ):
        _require(marker in generator_source, f"A4-R475-T generator marker absent: {marker}")
    for marker in (
        snapshot["source_marker"],
        "_reconstruct_cases",
        "ACCEPTED_CONTRACT_ONLY",
    ):
        _require(marker in reviewer_source, f"A4-R475-T reviewer marker absent: {marker}")
    for marker in (
        "test_versioned_all_case_producer_exists",
        "test_versioned_all_case_verifier_exists",
        "test_versioned_all_case_runner_exists",
    ):
        _require(marker in fail_first_source, f"A4-R475-T red marker absent: {marker}")
    for marker in (
        "test_resealed_case_resource_resume_and_publication_mutations_are_rejected",
        "test_current_six_case_producer_rejects_a_nonpilot_case_without_output",
        snapshot["contract_id"],
        snapshot["report_id"],
    ):
        _require(marker in acceptance_test, f"A4-R475-T test marker absent: {marker}")
    for marker in (
        "A4-R475-T DESIGN FROZEN",
        "Sequential resumable case commits",
        "A4-R475-V0",
        "exit Stage 1",
    ):
        _require(marker in design, f"A4-R475-T design marker absent: {marker}")
    for marker in (
        "A4-R475-T ACCEPTED",
        "9 passed",
        "3 failed",
        snapshot["contract_id"],
        snapshot["report_id"],
        "NO-GO",
    ):
        _require(marker in acceptance, f"A4-R475-T acceptance marker absent: {marker}")


def _validate_s1_a4_all_case_verifier_foundation_snapshot(
    snapshot: dict[str, Any],
    contract_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "accepted_constructive_case_count",
        "all_case_campaign_executed",
        "authority_file_count",
        "authority_file_headroom",
        "candidate_access_forbidden",
        "case_execution_ledger_id",
        "case_universe_count",
        "correction_subgate",
        "design_raw_octets",
        "design_raw_sha256",
        "execution_family_counts",
        "fail_first_initial_failures",
        "fail_first_test_raw_octets",
        "fail_first_test_raw_sha256",
        "formal_stage1_state",
        "next_bounded_packet",
        "pinned_input_octet_headroom",
        "pinned_input_octets",
        "predecessor_contract_id",
        "remaining_missing_role_failures",
        "report_id",
        "report_raw_octets",
        "report_raw_sha256",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "semantic_test_passed",
        "semantic_test_raw_octets",
        "semantic_test_raw_sha256",
        "source_marker",
        "typed_runtime_application_count",
        "typed_runtime_rule_count",
        "typed_runtime_sha256",
        "verifier_raw_octets",
        "verifier_raw_sha256",
        "verifier_source_marker",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 all-case verifier foundation snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-R475-V0"
        and snapshot["acceptance_state"] == "FOUNDATION_ONLY_ACCEPTED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V1"
        and snapshot["case_universe_count"] == 475
        and snapshot["accepted_constructive_case_count"] == 0
        and snapshot["candidate_access_forbidden"] is True
        and snapshot["all_case_campaign_executed"] is False
        and snapshot["fail_first_initial_failures"] == 1
        and snapshot["remaining_missing_role_failures"] == 2
        and snapshot["semantic_test_passed"] == 12
        and snapshot["acceptance_test_passed"] == 9,
        "S1-A4 all-case verifier foundation state differs",
    )
    _require(
        snapshot["predecessor_contract_id"] == contract_snapshot["contract_id"]
        and snapshot["case_execution_ledger_id"]
        == contract_snapshot["case_execution_ledger_id"]
        and snapshot["execution_family_counts"]
        == contract_snapshot["execution_family_counts"],
        "S1-A4 all-case verifier predecessor binding differs",
    )
    _require(
        snapshot["authority_file_count"] == 18
        and snapshot["authority_file_headroom"] == 46
        and snapshot["authority_file_count"] + snapshot["authority_file_headroom"]
        == 64
        and snapshot["pinned_input_octets"] == 16_717_988
        and snapshot["pinned_input_octet_headroom"] == 50_390_876
        and snapshot["pinned_input_octets"]
        + snapshot["pinned_input_octet_headroom"]
        == 67_108_864,
        "S1-A4 all-case verifier F0 evidence differs",
    )
    _require(
        snapshot["typed_runtime_rule_count"] == 42
        and snapshot["typed_runtime_application_count"] == 8
        and snapshot["typed_runtime_sha256"]
        == "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
        "S1-A4 all-case verifier typed-runtime authority differs",
    )

    artifacts = (
        (
            "verifier",
            ALL_CASE_VERIFIER_FOUNDATION_PATH,
            snapshot["verifier_raw_octets"],
            snapshot["verifier_raw_sha256"],
        ),
        (
            "reviewer",
            ALL_CASE_VERIFIER_FOUNDATION_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "report",
            ALL_CASE_VERIFIER_FOUNDATION_REPORT_PATH,
            snapshot["report_raw_octets"],
            snapshot["report_raw_sha256"],
        ),
        (
            "fail-first test",
            ALL_CASE_VERIFIER_FOUNDATION_FAIL_FIRST_TEST_PATH,
            snapshot["fail_first_test_raw_octets"],
            snapshot["fail_first_test_raw_sha256"],
        ),
        (
            "semantic test",
            ALL_CASE_VERIFIER_FOUNDATION_TEST_PATH,
            snapshot["semantic_test_raw_octets"],
            snapshot["semantic_test_raw_sha256"],
        ),
        (
            "acceptance test",
            ALL_CASE_VERIFIER_FOUNDATION_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "design",
            ALL_CASE_VERIFIER_FOUNDATION_DESIGN_PATH,
            snapshot["design_raw_octets"],
            snapshot["design_raw_sha256"],
        ),
        (
            "acceptance document",
            ALL_CASE_VERIFIER_FOUNDATION_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"A4-R475-V0 {label} absent")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"A4-R475-V0 {label} size drifted")
        _require(_sha256(raw) == digest, f"A4-R475-V0 {label} hash drifted")
        artifact_bytes[label] = raw

    report = json.loads(artifact_bytes["report"])
    report_payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_verifier_foundation_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "domain": ALL_CASE_VERIFIER_FOUNDATION_REPORT_DOMAIN,
                "payload": report_payload,
            }
        )
    )
    _require(
        report.get("all_case_verifier_foundation_acceptance_report_id")
        == snapshot["report_id"]
        == report_id
        and report.get("source_marker") == snapshot["source_marker"]
        and report.get("correction_subgate") == "A4-R475-V0"
        and report.get("review_decision") == "ACCEPTED_FOUNDATION_ONLY"
        and report.get("accepted_constructive_case_count") == 0
        and report.get("next_bounded_packet") == "A4-R475-V1"
        and report.get("formal_stage1_state") == "NO-GO",
        "S1-A4 all-case verifier acceptance report differs",
    )
    _require(
        report.get("contract_authority", {}).get("all_case_campaign_contract_id")
        == snapshot["predecessor_contract_id"],
        "S1-A4 all-case verifier report predecessor differs",
    )
    fail_first = report.get("fail_first_boundary", {})
    _require(
        fail_first
        == {
            "accepted_constructive_case_count": 0,
            "candidate_access_forbidden": True,
            "expected_remaining_role_failures": 2,
            "versioned_producer_present": False,
            "versioned_runner_present": False,
            "versioned_verifier_present": True,
        },
        "S1-A4 all-case verifier fail-first boundary differs",
    )
    reconstruction = report.get("independent_case_reconstruction", {})
    _require(
        reconstruction.get("case_count") == 475
        and reconstruction.get("case_execution_ledger_id")
        == snapshot["case_execution_ledger_id"]
        and reconstruction.get("execution_family_counts")
        == snapshot["execution_family_counts"]
        and reconstruction.get("successor_plan_case_positions") == [435]
        and reconstruction.get("ordered_case_execution_records_sha256")
        == contract_snapshot["ordered_case_execution_records_sha256"],
        "S1-A4 all-case verifier case reconstruction differs",
    )
    resources = report.get("resource_evidence", {})
    _require(
        resources
        == {
            "authority_file_count": snapshot["authority_file_count"],
            "authority_file_headroom": snapshot["authority_file_headroom"],
            "f0_limits_raised": False,
            "pinned_input_octet_headroom": snapshot["pinned_input_octet_headroom"],
            "pinned_input_octets": snapshot["pinned_input_octets"],
        },
        "S1-A4 all-case verifier resource evidence differs",
    )
    runtime = report.get("typed_runtime_replay", {})
    _require(
        runtime.get("replay_count") == 2
        and runtime.get("byte_identical") is True
        and runtime.get("rule_count") == snapshot["typed_runtime_rule_count"]
        and runtime.get("application_count")
        == snapshot["typed_runtime_application_count"]
        and runtime.get("resolver_count") == 2
        and runtime.get("unsupported_complex_rule_count") == 0,
        "S1-A4 all-case verifier runtime replay differs",
    )
    verifier_authority = report.get("verifier_authority", {})
    _require(
        verifier_authority.get("raw_octets") == snapshot["verifier_raw_octets"]
        and verifier_authority.get("raw_sha256") == snapshot["verifier_raw_sha256"]
        and verifier_authority.get("source_marker")
        == snapshot["verifier_source_marker"],
        "S1-A4 all-case verifier authority differs",
    )
    cli = report.get("verifier_cli_replay", {})
    _require(
        cli.get("replay_count") == 2
        and cli.get("byte_identical") is True
        and cli.get("candidate_paths_opened") == 0
        and cli.get("output_paths_created") == 0
        and cli.get("return_code") == 1,
        "S1-A4 all-case verifier CLI boundary differs",
    )

    verifier_source = artifact_bytes["verifier"].decode("utf-8")
    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    fail_first_source = artifact_bytes["fail-first test"].decode("utf-8")
    semantic_test = artifact_bytes["semantic test"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    design = artifact_bytes["design"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        snapshot["verifier_source_marker"],
        snapshot["typed_runtime_sha256"],
        "_load_foundation",
        "_validate_typed_value",
        "_evaluate_rule_ast",
        "_verify_foundation_only",
        "FOUNDATION_ONLY",
    ):
        _require(marker in verifier_source, f"A4-R475-V0 verifier marker absent: {marker}")
    for marker in (
        snapshot["source_marker"],
        "_reconstruct_case_ledger",
        "_review_source_ast",
        "_run_verifier_replays",
        "_run_runtime_replays",
        "ACCEPTED_FOUNDATION_ONLY",
    ):
        _require(marker in reviewer_source, f"A4-R475-V0 reviewer marker absent: {marker}")
    reviewer_tree = ast.parse(reviewer_source)
    reviewer_imports = {
        alias.name
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reviewer_imports.update(
        node.module
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all("verify_raw_v8_step2" not in name for name in reviewer_imports),
        "A4-R475-V0 reviewer imports the verifier",
    )
    _require(
        "test_a4_r475_v0_versioned_verifier_foundation_exists"
        in fail_first_source,
        "A4-R475-V0 fail-first marker absent",
    )
    for marker in (
        "test_v0_cli_rejects_before_candidate_or_output_access",
        "test_coherently_resealed_case_ledger_mutation_is_rejected",
        "test_resealed_role_scope_overclaim_is_rejected",
        "test_source_has_no_role_import_or_candidate_access_surface",
    ):
        _require(marker in semantic_test, f"A4-R475-V0 semantic marker absent: {marker}")
    for marker in (
        "test_independent_reviewer_reconstructs_without_verifier_import",
        "test_coherently_resealed_acceptance_overclaims_are_rejected",
        snapshot["report_id"],
    ):
        _require(marker in acceptance_test, f"A4-R475-V0 test marker absent: {marker}")
    for marker in (
        "A4-R475-V0",
        "Fresh resolver plus exact pinned accepted runtime",
        "A4-R475-V1",
        "NO-GO",
    ):
        _require(marker in design, f"A4-R475-V0 design marker absent: {marker}")
    for marker in (
        "A4-R475-V0 ACCEPTED",
        "FOUNDATION ONLY",
        "22 passed",
        snapshot["report_id"],
        "A4-R475-V1",
        "NO-GO",
    ):
        _require(marker in acceptance, f"A4-R475-V0 acceptance marker absent: {marker}")


def _validate_s1_a4_intrinsic_attainability_snapshot(
    snapshot: dict[str, Any],
    foundation_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_report_id",
        "acceptance_report_raw_octets",
        "acceptance_report_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "all_case_v1_acceptance_possible_under_frozen_authority",
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "attainability_falsification_id",
        "case8_exact_legal_maximum_octets",
        "case8_legal_attainer_sha256",
        "case8_p2_upper_bound_octets",
        "case8_unattainable_gap_octets",
        "contradiction_case_count",
        "contradiction_vector_sha256",
        "correction_subgate",
        "focused_passed",
        "formal_stage1_state",
        "intrinsic_case_count",
        "next_bounded_packet",
        "not_falsified_by_text_ceiling_case_count",
        "predecessor_verifier_raw_sha256",
        "producer_runner_or_campaign_implemented",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "semantic_test_passed",
        "semantic_test_raw_octets",
        "semantic_test_raw_sha256",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 intrinsic-attainability snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-R475-V1-F-A"
        and snapshot["acceptance_state"]
        == "FALSIFICATION_ACCEPTED_AUTHORITY_REPAIR_REQUIRED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V1-C"
        and snapshot["intrinsic_case_count"] == 66
        and snapshot["contradiction_case_count"] == 26
        and snapshot["not_falsified_by_text_ceiling_case_count"] == 40
        and snapshot["semantic_test_passed"] == 10
        and snapshot["acceptance_test_passed"] == 13
        and snapshot["focused_passed"] == 23
        and snapshot["all_case_v1_acceptance_possible_under_frozen_authority"]
        is False
        and snapshot["producer_runner_or_campaign_implemented"] is False,
        "S1-A4 intrinsic-attainability disposition differs",
    )
    _require(
        snapshot["case8_p2_upper_bound_octets"] == 524_288
        and snapshot["case8_exact_legal_maximum_octets"] == 928
        and snapshot["case8_unattainable_gap_octets"] == 523_360
        and snapshot["case8_p2_upper_bound_octets"]
        - snapshot["case8_exact_legal_maximum_octets"]
        == snapshot["case8_unattainable_gap_octets"]
        and snapshot["case8_legal_attainer_sha256"]
        == "9156a97a005f9d2264e34054f071a6b15169f88b23be54cb59bc254362888665",
        "S1-A4 intrinsic-attainability case8 evidence differs",
    )
    _require(
        snapshot["attainability_falsification_id"]
        == "0b53bd2d79c5f923f1887f7e33f167625fd43753c22345074ae2768dec0d58ad"
        and snapshot["contradiction_vector_sha256"]
        == "3d1c35477e174cde53ab163c516dea9d7132a468bfa7c7954f1ca538317f8e5d"
        and snapshot["acceptance_report_id"]
        == "7dfd4073f40f1825356b32c3ed0ca7f291a4a179827882fbbedbdeb96030102e",
        "S1-A4 intrinsic-attainability semantic identity differs",
    )
    _require(
        snapshot["predecessor_verifier_raw_sha256"]
        == foundation_snapshot["verifier_raw_sha256"],
        "S1-A4 intrinsic-attainability predecessor binding differs",
    )

    artifacts = (
        (
            "analyzer",
            INTRINSIC_ATTAINABILITY_ANALYZER_PATH,
            snapshot["analyzer_raw_octets"],
            snapshot["analyzer_raw_sha256"],
        ),
        (
            "semantic test",
            INTRINSIC_ATTAINABILITY_TEST_PATH,
            snapshot["semantic_test_raw_octets"],
            snapshot["semantic_test_raw_sha256"],
        ),
        (
            "reviewer",
            INTRINSIC_ATTAINABILITY_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "acceptance report",
            INTRINSIC_ATTAINABILITY_REPORT_PATH,
            snapshot["acceptance_report_raw_octets"],
            snapshot["acceptance_report_raw_sha256"],
        ),
        (
            "acceptance test",
            INTRINSIC_ATTAINABILITY_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            INTRINSIC_ATTAINABILITY_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(
            path.is_file() and not path.is_symlink(),
            f"A4-R475-V1-F-A {label} absent",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == octets,
            f"A4-R475-V1-F-A {label} size drifted",
        )
        _require(
            _sha256(raw) == digest,
            f"A4-R475-V1-F-A {label} hash drifted",
        )
        artifact_bytes[label] = raw

    report = json.loads(artifact_bytes["acceptance report"])
    report_payload = {
        name: value for name, value in report.items() if name != "acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": "riskyieldmm_canonical_json_v1",
                "domain": INTRINSIC_ATTAINABILITY_REPORT_DOMAIN,
                "payload": report_payload,
                "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8",
            }
        )
    )
    expected_positions = [
        1,
        2,
        7,
        8,
        9,
        12,
        18,
        19,
        21,
        22,
        25,
        28,
        30,
        31,
        32,
        34,
        36,
        37,
        42,
        44,
        45,
        48,
        49,
        52,
        59,
        60,
    ]
    _require(
        report.get("acceptance_report_id")
        == snapshot["acceptance_report_id"]
        == report_id
        and report.get("packet") == "A4-R475-V1-F-A"
        and report.get("decision")
        == "ACCEPTED_FALSIFICATION_AUTHORITY_REPAIR_REQUIRED"
        and report.get("accepted_scope") == "FALSIFICATION_ONLY_NO_AUTHORITY_REPAIR"
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_bounded_packet") == "A4-R475-V1-C"
        and report.get("attainability_falsification_id")
        == snapshot["attainability_falsification_id"]
        and report.get("contradiction_case_count")
        == snapshot["contradiction_case_count"]
        and report.get("contradiction_case_positions") == expected_positions
        and report.get("contradiction_vector_sha256")
        == snapshot["contradiction_vector_sha256"]
        and report.get("campaign_unattained_case_policy_enforced") is True
        and report.get("all_case_v1_acceptance_possible_under_frozen_authority")
        is False
        and report.get("accepted_six_case_verifier_unchanged") is True
        and report.get("producer_runner_or_campaign_implemented") is False,
        "S1-A4 intrinsic-attainability acceptance report differs",
    )
    case8 = report.get("case8_independent_review", {})
    _require(
        case8.get("case_position") == 8
        and case8.get("published_p2_upper_bound_octets")
        == snapshot["case8_p2_upper_bound_octets"]
        and case8.get("independently_derived_exact_legal_maximum_octets")
        == snapshot["case8_exact_legal_maximum_octets"]
        and case8.get("independent_legal_attainer_octets")
        == snapshot["case8_exact_legal_maximum_octets"]
        and case8.get("unattainable_gap_octets")
        == snapshot["case8_unattainable_gap_octets"]
        and case8.get("independent_legal_attainer_sha256")
        == snapshot["case8_legal_attainer_sha256"]
        and case8.get("typed_runtime_accepted") is True
        and case8.get("intrinsic_rule_root") is True
        and case8.get("standalone_identity_recomputed") is True
        and case8.get("p3_equality_possible") is False,
        "S1-A4 intrinsic-attainability case8 review differs",
    )

    analyzer_source = artifact_bytes["analyzer"].decode("utf-8")
    semantic_test = artifact_bytes["semantic test"].decode("utf-8")
    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "over-approximation of the P1-legal domain",
        "restore_text_languages",
        "_case8_exact_witness",
        "VERSIONED_INTRINSIC_TEMPLATE_AUTHORITY_REPAIR_BEFORE_A4_R475_V1",
    ):
        _require(
            marker in analyzer_source,
            f"A4-R475-V1-F-A analyzer marker absent: {marker}",
        )
    analyzer_tree = ast.parse(analyzer_source)
    analyzer_imports = {
        alias.name
        for node in ast.walk(analyzer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    analyzer_imports.update(
        node.module
        for node in ast.walk(analyzer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    forbidden_import_fragments = (
        "produce_raw_v8_step2",
        "verify_raw_v8_step2",
        "validate_raw_v8_step2",
        "intrinsic_template_attainability_acceptance",
    )
    _require(
        all(
            fragment not in imported
            for imported in analyzer_imports
            for fragment in forbidden_import_fragments
        ),
        "A4-R475-V1-F-A analyzer imports a constructive role or runtime",
    )
    for marker in (
        "test_intrinsic_language_aware_superset_falsifies_26_frozen_endpoints",
        "test_case8_exact_attainer_closes_the_corrected_928_octet_endpoint",
        "test_40_unfalsified_cases_are_not_promoted_to_attainability",
        "test_accepted_six_case_verifier_remains_byte_exact",
    ):
        _require(
            marker in semantic_test,
            f"A4-R475-V1-F-A semantic-test marker absent: {marker}",
        )
    for marker in (
        "_run_analyzer",
        "_review_case8",
        "ACCEPTED_FALSIFICATION_AUTHORITY_REPAIR_REQUIRED",
        "COMPLETE_CAMPAIGN_NO_GO_WITHOUT_LIMIT_OR_AUTHORITY_REPAIR",
    ):
        _require(
            marker in reviewer_source,
            f"A4-R475-V1-F-A reviewer marker absent: {marker}",
        )
    reviewer_tree = ast.parse(reviewer_source)
    reviewer_imports = {
        alias.name
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reviewer_imports.update(
        node.module
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all(
            "intrinsic_template_attainability" not in imported
            and "verify_raw_v8_step2" not in imported
            and "produce_raw_v8_step2" not in imported
            for imported in reviewer_imports
        ),
        "A4-R475-V1-F-A reviewer imports the analyzer or a constructive role",
    )
    for marker in (
        "test_reviewer_independently_closes_the_decisive_case8_contradiction",
        "test_reviewer_does_not_import_analyzer_or_any_constructive_role",
        "test_coherently_resealed_acceptance_overclaims_change_identity",
        "test_falsification_acceptance_does_not_modify_predecessor_roles",
    ):
        _require(
            marker in acceptance_test,
            f"A4-R475-V1-F-A acceptance-test marker absent: {marker}",
        )
    for marker in (
        "A4-R475-V1-F-A",
        "26 FROZEN P2 ENDPOINTS",
        "A4-R475-V1-C",
        "NO-GO",
    ):
        _require(
            marker in acceptance,
            f"A4-R475-V1-F-A acceptance marker absent: {marker}",
        )


def _validate_s1_a4_intrinsic_correction_contract_snapshot(
    snapshot: dict[str, Any],
    attainability_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_report_id",
        "acceptance_report_raw_octets",
        "acceptance_report_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "all_66_exact_maxima_accepted",
        "all_case_campaign_released",
        "case_vector_sha256",
        "contract_id",
        "contract_raw_octets",
        "contract_raw_sha256",
        "contradiction_case_count",
        "correction_subgate",
        "dependency_kind_counts",
        "dual_channel_sources_frozen_before_execution",
        "formal_stage1_state",
        "generator_raw_octets",
        "generator_raw_sha256",
        "intrinsic_case_count",
        "next_bounded_packet",
        "not_falsified_nonclaim_case_count",
        "predecessor_falsification_id",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "semantic_test_passed",
        "semantic_test_raw_octets",
        "semantic_test_raw_sha256",
        "total_case_dependency_records",
        "total_step_records",
        "verifier_producer_runner_or_campaign_implemented",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 intrinsic-correction snapshot members differ",
    )
    expected_dependency_counts = {
        "ARRAY_BATCH": 91,
        "ASCII_DFA": 35,
        "CODEC_COORDINATE_SET": 160,
        "IDENTITY_CONTRACT": 37,
        "INTRINSIC_RULE": 87,
        "TEXT_LANGUAGE": 404,
        "TYPE_DESCRIPTOR": 163,
        "UNICODE_IDENTIFIER_PROFILE": 23,
        "UNICODE_SOURCE": 108,
        "UNION_BRANCH": 22,
        "VALUE_SCHEMA": 676,
    }
    _require(
        snapshot["correction_subgate"] == "A4-R475-V1-C1"
        and snapshot["acceptance_state"] == "CONTRACT_ONLY_ACCEPTED"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V1-C2-S"
        and snapshot["intrinsic_case_count"] == 66
        and snapshot["contradiction_case_count"] == 26
        and snapshot["not_falsified_nonclaim_case_count"] == 40
        and snapshot["total_step_records"] == 1_647
        and snapshot["total_case_dependency_records"] == 1_806
        and snapshot["dependency_kind_counts"] == expected_dependency_counts
        and snapshot["semantic_test_passed"] == 12
        and snapshot["acceptance_test_passed"] == 10
        and snapshot["dual_channel_sources_frozen_before_execution"] is True
        and snapshot["all_66_exact_maxima_accepted"] is False
        and snapshot["all_case_campaign_released"] is False
        and snapshot["verifier_producer_runner_or_campaign_implemented"] is False,
        "S1-A4 intrinsic-correction disposition differs",
    )
    _require(
        snapshot["predecessor_falsification_id"]
        == attainability_snapshot["attainability_falsification_id"],
        "S1-A4 intrinsic-correction predecessor binding differs",
    )
    _require(
        snapshot["case_vector_sha256"]
        == "d0e9a0a0ae157e598da1dc8130e30bca6189966d4eadc853eb8a1a0db1f9300b"
        and snapshot["contract_id"]
        == "171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9"
        and snapshot["acceptance_report_id"]
        == "e3cdc9ea250f3b3b296aeb02fc9a51f0aa615655ec8ee37c77a319855907dc84",
        "S1-A4 intrinsic-correction semantic identity differs",
    )

    artifacts = (
        (
            "generator",
            INTRINSIC_CORRECTION_CONTRACT_GENERATOR_PATH,
            snapshot["generator_raw_octets"],
            snapshot["generator_raw_sha256"],
        ),
        (
            "contract",
            INTRINSIC_CORRECTION_CONTRACT_PATH,
            snapshot["contract_raw_octets"],
            snapshot["contract_raw_sha256"],
        ),
        (
            "semantic test",
            INTRINSIC_CORRECTION_CONTRACT_TEST_PATH,
            snapshot["semantic_test_raw_octets"],
            snapshot["semantic_test_raw_sha256"],
        ),
        (
            "reviewer",
            INTRINSIC_CORRECTION_CONTRACT_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "acceptance report",
            INTRINSIC_CORRECTION_CONTRACT_REPORT_PATH,
            snapshot["acceptance_report_raw_octets"],
            snapshot["acceptance_report_raw_sha256"],
        ),
        (
            "acceptance test",
            INTRINSIC_CORRECTION_CONTRACT_ACCEPTANCE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            INTRINSIC_CORRECTION_CONTRACT_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(
            path.is_file() and not path.is_symlink(),
            f"A4-R475-V1-C1 {label} absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"A4-R475-V1-C1 {label} size drifted")
        _require(_sha256(raw) == digest, f"A4-R475-V1-C1 {label} hash drifted")
        artifact_bytes[label] = raw

    contract = json.loads(artifact_bytes["contract"])
    contract_payload = {
        name: value
        for name, value in contract.items()
        if name != "intrinsic_exactness_correction_contract_id"
    }
    contract_id = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": "riskyieldmm_canonical_json_v1",
                "domain": INTRINSIC_CORRECTION_CONTRACT_DOMAIN,
                "payload": contract_payload,
                "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8",
            }
        )
    )
    _require(
        contract.get("intrinsic_exactness_correction_contract_id")
        == snapshot["contract_id"]
        == contract_id
        and contract.get("packet") == "A4-R475-V1-C1"
        and contract.get("formal_stage1_state") == "NO-GO"
        and contract.get("next_bounded_packet") == "A4-R475-V1-C2-S"
        and contract.get("ordered_intrinsic_case_records_sha256")
        == snapshot["case_vector_sha256"],
        "S1-A4 intrinsic-correction contract identity differs",
    )
    scope = contract.get("correction_scope_contract", {})
    _require(
        scope.get("intrinsic_case_count") == snapshot["intrinsic_case_count"]
        and scope.get("contradiction_case_count")
        == snapshot["contradiction_case_count"]
        and scope.get("not_falsified_case_count")
        == snapshot["not_falsified_nonclaim_case_count"]
        and scope.get("ordered_contradiction_case_positions")
        == [
            1,
            2,
            7,
            8,
            9,
            12,
            18,
            19,
            21,
            22,
            25,
            28,
            30,
            31,
            32,
            34,
            36,
            37,
            42,
            44,
            45,
            48,
            49,
            52,
            59,
            60,
        ],
        "S1-A4 intrinsic-correction scope differs",
    )
    aggregate = contract.get("aggregate_dependency_census", {})
    _require(
        aggregate.get("dependency_kind_counts") == expected_dependency_counts
        and aggregate.get("total_case_dependency_records")
        == snapshot["total_case_dependency_records"]
        and aggregate.get("total_step_records") == snapshot["total_step_records"],
        "S1-A4 intrinsic-correction dependency census differs",
    )
    cases = contract.get("ordered_intrinsic_case_records", [])
    _require(
        len(cases) == 66
        and [row.get("case_position") for row in cases] == list(range(1, 67))
        and sum(
            row.get("correction_status") == "FROZEN_P2_ENDPOINT_CONTRADICTED"
            for row in cases
        )
        == 26
        and sum(
            row.get("correction_status") == "EXACTNESS_UNRESOLVED_NOT_ACCEPTED"
            for row in cases
        )
        == 40,
        "S1-A4 intrinsic-correction case disposition differs",
    )
    channels = contract.get("dual_channel_contract", {})
    _require(
        channels.get("cross_channel_code_sharing_policy") == "FORBIDDEN"
        and channels.get("pre_execution_source_freeze")
        == {
            "both_channel_sources_and_output_schemas_frozen_before_execution": True,
            "channel_output_allowed_during_source_freeze": False,
            "mutual_import_read_or_generated_witness_access_policy": "FORBIDDEN",
            "required_packet": "A4-R475-V1-C2-S",
        }
        and channels.get("upper_channel", {}).get(
            "source_must_not_read_attainer_output"
        )
        is True
        and channels.get("attainer_channel", {}).get(
            "candidate_source_must_not_read_upper_output"
        )
        is True
        and channels.get("exactness_join", {}).get("unresolved_or_unequal_policy")
        == "NO_GO",
        "S1-A4 intrinsic-correction channel boundary differs",
    )
    _require(
        [row.get("packet") for row in contract.get("ordered_successor_packet_records", [])]
        == [
            "A4-R475-V1-C2-S",
            "A4-R475-V1-C2-U",
            "A4-R475-V1-C2-A",
            "A4-R475-V1-C3",
            "A4-R475-V1",
        ],
        "S1-A4 intrinsic-correction successor order differs",
    )
    resources = contract.get("resource_contract", {})
    _require(
        resources.get("authority_file_count") == 8
        and resources.get("authority_file_limit") == 64
        and resources.get("pinned_input_octets") == 15_869_888
        and resources.get("pinned_input_octet_limit") == 67_108_864
        and resources.get("contract_raw_octet_limit") == 16_777_216
        and resources.get("limit_tuning_from_observed_answer_allowed") is False,
        "S1-A4 intrinsic-correction resource boundary differs",
    )
    acceptance_claim = contract.get("acceptance_contract", {})
    successor = contract.get("successor_authority_contract", {})
    _require(
        acceptance_claim.get("acceptance_claim")
        == "DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY"
        and acceptance_claim.get("all_66_exact_maxima_accepted") is False
        and acceptance_claim.get("all_case_campaign_released") is False
        and successor.get("accepted_predecessor_edit_policy") == "FORBIDDEN"
        and successor.get("verifier_producer_runner_or_campaign_implemented_by_c1")
        is False,
        "S1-A4 intrinsic-correction nonclaim differs",
    )

    report = json.loads(artifact_bytes["acceptance report"])
    report_payload = {
        name: value for name, value in report.items() if name != "acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": "riskyieldmm_canonical_json_v1",
                "domain": INTRINSIC_CORRECTION_CONTRACT_REPORT_DOMAIN,
                "payload": report_payload,
                "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8",
            }
        )
    )
    _require(
        report.get("acceptance_report_id")
        == snapshot["acceptance_report_id"]
        == report_id
        and report.get("packet") == "A4-R475-V1-C1-A"
        and report.get("decision") == "ACCEPTED_CONTRACT_ONLY"
        and report.get("acceptance_scope")
        == "C1_DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY"
        and report.get("contract_id") == snapshot["contract_id"]
        and report.get("case_vector_sha256") == snapshot["case_vector_sha256"]
        and report.get("intrinsic_case_count") == 66
        and report.get("contradiction_case_count") == 26
        and report.get("not_falsified_nonclaim_case_count") == 40
        and report.get("total_step_records") == 1_647
        and report.get("total_case_dependency_records") == 1_806
        and report.get("all_66_exact_maxima_accepted") is False
        and report.get("all_case_campaign_released") is False
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_bounded_packet") == "A4-R475-V1-C2-S",
        "S1-A4 intrinsic-correction acceptance report differs",
    )

    generator_source = artifact_bytes["generator"].decode("utf-8")
    semantic_test = artifact_bytes["semantic test"].decode("utf-8")
    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    acceptance = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "A4_R475_V1_C1_INTRINSIC_CORRECTION_CONTRACT_GENERATOR_V1",
        "DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY",
        "pre_execution_source_freeze",
        "A4-R475-V1-C2-S",
    ):
        _require(
            marker in generator_source,
            f"A4-R475-V1-C1 generator marker absent: {marker}",
        )
    generator_tree = ast.parse(generator_source)
    generator_imports = {
        alias.name
        for node in ast.walk(generator_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    generator_imports.update(
        node.module
        for node in ast.walk(generator_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all(
            "intrinsic_template_attainability" not in imported
            and "verify_raw_v8_step2" not in imported
            and "produce_raw_v8_step2" not in imported
            and "validate_raw_v8_step2" not in imported
            for imported in generator_imports
        ),
        "A4-R475-V1-C1 generator imports a predecessor role or analyzer",
    )
    for marker in (
        "test_complete_step_and_dependency_census_is_frozen",
        "test_every_relaxed_predicate_class_has_a_frozen_dependency_surface",
        "test_dual_channels_and_join_are_separate_and_fail_closed",
        "test_coherently_resealed_overclaims_change_contract_identity",
    ):
        _require(
            marker in semantic_test,
            f"A4-R475-V1-C1 semantic-test marker absent: {marker}",
        )
    for marker in (
        "_reconstruct_cases",
        "generator check replay differs",
        "C1_DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY",
        "A4-R475-V1-C2-S",
    ):
        _require(
            marker in reviewer_source,
            f"A4-R475-V1-C1 reviewer marker absent: {marker}",
        )
    reviewer_tree = ast.parse(reviewer_source)
    reviewer_imports = {
        alias.name
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reviewer_imports.update(
        node.module
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all(
            "intrinsic_correction_contract" not in imported
            and "verify_raw_v8_step2" not in imported
            and "produce_raw_v8_step2" not in imported
            for imported in reviewer_imports
        ),
        "A4-R475-V1-C1 reviewer imports the generator or a constructive role",
    )
    for marker in (
        "test_independent_reviewer_reconstructs_exact_frozen_report",
        "test_independent_reconstruction_rejects_step_dependency_omission",
        "test_independent_reconstruction_rejects_case_promotion",
        "test_coherently_resealed_acceptance_overclaims_change_report_id",
    ):
        _require(
            marker in acceptance_test,
            f"A4-R475-V1-C1 acceptance-test marker absent: {marker}",
        )
    for marker in (
        "A4-R475-V1-C1",
        "1,647 postorder step records",
        "1,806 per-case unique dependency records",
        "A4-R475-V1-C2-S",
        "NO-GO",
    ):
        _require(
            marker in acceptance,
            f"A4-R475-V1-C1 acceptance marker absent: {marker}",
        )


def _validate_s1_a4_intrinsic_dual_source_freeze_snapshot(
    snapshot: dict[str, Any],
    correction_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_report_id",
        "acceptance_report_raw_octets",
        "acceptance_report_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "all_case_campaign_released",
        "attainer_output_schema_id",
        "attainer_output_schema_raw_octets",
        "attainer_output_schema_raw_sha256",
        "attainer_source_raw_octets",
        "attainer_source_raw_sha256",
        "authority_raw_octets",
        "authority_record_count",
        "channel_core_ast_fingerprints",
        "channel_results_accepted",
        "correction_subgate",
        "distinct_core_ast_fingerprint_count",
        "dual_source_freeze_id",
        "exact_maxima_accepted",
        "formal_stage1_state",
        "freeze_raw_octets",
        "freeze_raw_sha256",
        "generator_raw_octets",
        "generator_raw_sha256",
        "intrinsic_exactness_correction_contract_id",
        "next_bounded_packet",
        "pre_execution_absent_output_count",
        "projected_pinned_input_upper_octets",
        "projected_total_output_upper_octets",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "source_or_channel_execution_count",
        "upper_output_schema_id",
        "upper_output_schema_raw_octets",
        "upper_output_schema_raw_sha256",
        "upper_source_raw_octets",
        "upper_source_raw_sha256",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 intrinsic dual-source-freeze snapshot members differ",
    )
    expected_fingerprints = {
        "LEGAL_UPPER": "4b2fb1d5463c2d8aa6174652b3e35d6866bb4bb94a0eb046d355f232e3f87f4b",
        "P1_LEGAL_ATTAINER": "eaf7e544610c0ccf333b75f44c1dea1533fb523f73631f3932a69cf32a830586",
    }
    _require(
        snapshot["correction_subgate"] == "A4-R475-V1-C2-S"
        and snapshot["acceptance_state"]
        == "ACCEPTED_PRE_EXECUTION_DUAL_SOURCE_AND_SCHEMA_FREEZE"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V1-C2-U"
        and snapshot["authority_record_count"] == 4
        and snapshot["authority_raw_octets"] == 7_639_498
        and snapshot["channel_core_ast_fingerprints"] == expected_fingerprints
        and snapshot["distinct_core_ast_fingerprint_count"] == 2
        and snapshot["pre_execution_absent_output_count"] == 5
        and snapshot["projected_pinned_input_upper_octets"] == 7_969_945
        and snapshot["projected_total_output_upper_octets"] == 38_994_304
        and snapshot["source_or_channel_execution_count"] == 0
        and snapshot["channel_results_accepted"] is False
        and snapshot["exact_maxima_accepted"] is False
        and snapshot["all_case_campaign_released"] is False
        and snapshot["acceptance_test_passed"] == 16,
        "S1-A4 intrinsic dual-source-freeze disposition differs",
    )
    _require(
        snapshot["intrinsic_exactness_correction_contract_id"]
        == correction_snapshot["contract_id"],
        "S1-A4 intrinsic dual-source-freeze predecessor binding differs",
    )
    _require(
        snapshot["dual_source_freeze_id"]
        == "d6e17e638a99449bc806b72cfefb850d6f64ed578dc5314a135b8e71fe5b008e"
        and snapshot["acceptance_report_id"]
        == "18dcb2b97a13cb0a8912ad3bc152cb0e388740d386207fbad38dbbd19bef7ec5",
        "S1-A4 intrinsic dual-source-freeze semantic identity differs",
    )

    artifacts = (
        (
            "generator",
            INTRINSIC_DUAL_SOURCE_FREEZE_GENERATOR_PATH,
            snapshot["generator_raw_octets"],
            snapshot["generator_raw_sha256"],
        ),
        (
            "freeze manifest",
            INTRINSIC_DUAL_SOURCE_FREEZE_PATH,
            snapshot["freeze_raw_octets"],
            snapshot["freeze_raw_sha256"],
        ),
        (
            "upper source",
            INTRINSIC_UPPER_SOURCE_PATH,
            snapshot["upper_source_raw_octets"],
            snapshot["upper_source_raw_sha256"],
        ),
        (
            "upper output schema",
            INTRINSIC_UPPER_SCHEMA_PATH,
            snapshot["upper_output_schema_raw_octets"],
            snapshot["upper_output_schema_raw_sha256"],
        ),
        (
            "attainer output schema",
            INTRINSIC_ATTAINER_SCHEMA_PATH,
            snapshot["attainer_output_schema_raw_octets"],
            snapshot["attainer_output_schema_raw_sha256"],
        ),
        (
            "reviewer",
            INTRINSIC_DUAL_SOURCE_FREEZE_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "acceptance report",
            INTRINSIC_DUAL_SOURCE_FREEZE_REPORT_PATH,
            snapshot["acceptance_report_raw_octets"],
            snapshot["acceptance_report_raw_sha256"],
        ),
        (
            "acceptance test",
            INTRINSIC_DUAL_SOURCE_FREEZE_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            INTRINSIC_DUAL_SOURCE_FREEZE_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(
            path.is_file() and not path.is_symlink(),
            f"A4-R475-V1-C2-S {label} absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"A4-R475-V1-C2-S {label} size drifted")
        _require(_sha256(raw) == digest, f"A4-R475-V1-C2-S {label} hash drifted")
        artifact_bytes[label] = raw
    _require(
        INTRINSIC_ATTAINER_SOURCE_PATH.is_file()
        and not INTRINSIC_ATTAINER_SOURCE_PATH.is_symlink()
        and INTRINSIC_ATTAINER_SOURCE_PATH.stat().st_size
        == snapshot["attainer_source_raw_octets"],
        "A4-R475-V1-C2-S attainer source metadata drifted",
    )

    manifest = json.loads(artifact_bytes["freeze manifest"])
    _require(
        artifact_bytes["freeze manifest"]
        == (
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
        "S1-A4 intrinsic dual-source-freeze physical encoding differs",
    )
    manifest_payload = {
        name: value
        for name, value in manifest.items()
        if name != "dual_source_freeze_id"
    }
    manifest_id = _sha256(
        _canonical_bytes(
            {
                "domain": INTRINSIC_DUAL_SOURCE_FREEZE_DOMAIN,
                "payload": manifest_payload,
            }
        )
    )
    _require(
        manifest.get("dual_source_freeze_id")
        == snapshot["dual_source_freeze_id"]
        == manifest_id
        and manifest.get("packet") == "A4-R475-V1-C2-S"
        and manifest.get("intrinsic_exactness_correction_contract_id")
        == snapshot["intrinsic_exactness_correction_contract_id"]
        and manifest.get("formal_stage1_state") == "NO-GO"
        and manifest.get("next_bounded_packet") == "A4-R475-V1-C2-U",
        "S1-A4 intrinsic dual-source-freeze manifest identity differs",
    )
    channel_rows = manifest.get("ordered_channel_source_records", [])
    _require(
        len(channel_rows) == 2
        and [row.get("channel") for row in channel_rows]
        == ["LEGAL_UPPER", "P1_LEGAL_ATTAINER"]
        and [row.get("raw_sha256") for row in channel_rows]
        == [
            snapshot["upper_source_raw_sha256"],
            snapshot["attainer_source_raw_sha256"],
        ]
        and [row.get("output_schema_id") for row in channel_rows]
        == [
            snapshot["upper_output_schema_id"],
            snapshot["attainer_output_schema_id"],
        ]
        and all(
            row.get("channel_output_allowed_during_source_freeze") is False
            for row in channel_rows
        ),
        "S1-A4 intrinsic dual-source-freeze channel seal differs",
    )
    independence = manifest.get("independence_contract", {})
    _require(
        independence.get(
            "both_complete_sources_and_schemas_sealed_by_this_identity_before_execution"
        )
        is True
        and independence.get("shared_core_executable_code_policy") == "NONE"
        and independence.get(
            "mutual_source_import_read_invoke_or_output_access_policy"
        )
        == "FORBIDDEN"
        and independence.get("generated_witness_or_result_exchange_policy")
        == "FORBIDDEN"
        and independence.get("human_adaptation_control")
        == "BOTH_SOURCE_BYTES_SEALED_BEFORE_EITHER_OFFICIAL_RESULT_PATH_EXISTS",
        "S1-A4 intrinsic dual-source-freeze independence boundary differs",
    )
    resources = manifest.get("resource_contract", {})
    projection = manifest.get("output_transport_projection", {})
    _require(
        resources.get("projected_pinned_input_upper_octets")
        == snapshot["projected_pinned_input_upper_octets"]
        < resources.get("total_pinned_input_octets_limit")
        and resources.get("projected_pinned_input_file_count") == 9
        < resources.get("input_file_count_limit")
        and resources.get("limit_tuning_from_observed_channel_answer_allowed")
        is False
        and projection.get("projected_total_output_upper_octets")
        == snapshot["projected_total_output_upper_octets"]
        and projection.get("projected_output_file_count") == 5
        and projection.get("answer_observation_used_to_set_limits") is False,
        "S1-A4 intrinsic dual-source-freeze resource boundary differs",
    )
    acceptance_claim = manifest.get("acceptance_contract", {})
    _require(
        acceptance_claim.get("acceptance_claim")
        == "PRE_EXECUTION_DUAL_SOURCE_AND_OUTPUT_SCHEMA_FREEZE_ONLY"
        and acceptance_claim.get("source_files_executed_by_c2_s") is False
        and acceptance_claim.get("channel_results_accepted") is False
        and acceptance_claim.get("exact_maxima_accepted") is False
        and acceptance_claim.get("all_case_campaign_released") is False,
        "S1-A4 intrinsic dual-source-freeze nonclaim differs",
    )
    for path in INTRINSIC_C2_OFFICIAL_OUTPUT_PATHS[1:]:
        _require(
            not path.exists() and not path.is_symlink(),
            f"A4-R475-V1-C2-S attainer output exists before C2-A: {path.name}",
        )

    report = json.loads(artifact_bytes["acceptance report"])
    report_payload = {
        name: value
        for name, value in report.items()
        if name != "dual_source_freeze_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "domain": INTRINSIC_DUAL_SOURCE_FREEZE_REPORT_DOMAIN,
                "payload": report_payload,
            }
        )
    )
    _require(
        report.get("dual_source_freeze_acceptance_report_id")
        == snapshot["acceptance_report_id"]
        == report_id
        and report.get("dual_source_freeze_id")
        == snapshot["dual_source_freeze_id"]
        and report.get("decision")
        == "ACCEPTED_PRE_EXECUTION_DUAL_SOURCE_AND_SCHEMA_FREEZE"
        and report.get("source_or_channel_execution_count") == 0
        and report.get("channel_results_accepted") is False
        and report.get("exact_maxima_accepted") is False
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_bounded_packet") == "A4-R475-V1-C2-U",
        "S1-A4 intrinsic dual-source-freeze acceptance report differs",
    )

    generator_source = artifact_bytes["generator"].decode("utf-8")
    upper_source = artifact_bytes["upper source"].decode("utf-8")
    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    acceptance_doc = artifact_bytes["acceptance document"].decode("utf-8")
    for marker in (
        "A4_R475_V1_C2_S_DUAL_SOURCE_FREEZE_GENERATOR_V1",
        "source_files_executed_by_c2_s",
        "BOTH_SOURCE_BYTES_SEALED_BEFORE_EITHER_OFFICIAL_RESULT_PATH_EXISTS",
    ):
        _require(
            marker in generator_source,
            f"A4-R475-V1-C2-S generator marker absent: {marker}",
        )
    _require(
        "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1" in upper_source
        and INTRINSIC_ATTAINER_SOURCE_PATH.name not in upper_source,
        "A4-R475-V1-C2-S upper source isolation differs",
    )
    reviewer_tree = ast.parse(reviewer_source)
    reviewer_imports = {
        alias.name
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reviewer_imports.update(
        node.module
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all(
            "intrinsic_dual_source_freeze" not in imported
            and "intrinsic_upper" not in imported
            and "intrinsic_attainers" not in imported
            for imported in reviewer_imports
        ),
        "A4-R475-V1-C2-S reviewer imports generator or channel source",
    )
    for marker in (
        "test_manifest_is_exact_generator_output_and_semantically_sealed",
        "test_static_source_mutations_fail_closed",
        "test_schema_relaxation_with_stale_identity_fails_closed",
        "test_stored_acceptance_report_matches_two_independent_reviews",
    ):
        _require(
            marker in acceptance_test,
            f"A4-R475-V1-C2-S acceptance-test marker absent: {marker}",
        )
    for marker in (
        "A4-R475-V1-C2-S",
        "d6e17e638a99449bc806b72cfefb850d6f64ed578dc5314a135b8e71fe5b008e",
        "zero channel executions",
        "A4-R475-V1-C2-U",
        "NO-GO",
    ):
        _require(
            marker in acceptance_doc,
            f"A4-R475-V1-C2-S acceptance marker absent: {marker}",
        )


def _validate_s1_a4_intrinsic_upper_channel_snapshot(
    snapshot: dict[str, Any],
    freeze_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_report_id",
        "acceptance_report_raw_octets",
        "acceptance_report_raw_sha256",
        "acceptance_state",
        "acceptance_test_passed",
        "acceptance_test_raw_octets",
        "acceptance_test_raw_sha256",
        "all_case_campaign_released",
        "attainer_channel_consumed",
        "attainer_output_absent_count",
        "attainer_source_or_output_read_true_case_count",
        "case_count",
        "correction_subgate",
        "derivation_kind_census",
        "exact_maxima_accepted",
        "execution_pinned_input_file_count",
        "execution_pinned_input_octets",
        "formal_stage1_state",
        "intrinsic_exactness_correction_contract_id",
        "legal_domain_upper_maximum_octets",
        "legal_domain_upper_minimum_octets",
        "legal_domain_upper_vector_sha256",
        "next_bounded_packet",
        "official_output_file_count",
        "proof_method_case_census",
        "proof_step_count",
        "reviewer_raw_octets",
        "reviewer_raw_sha256",
        "source_freeze_id",
        "upper_case_record_id_vector_sha256",
        "upper_output_schema_id",
        "upper_result_accepted",
        "upper_result_id",
        "upper_result_raw_octets",
        "upper_result_raw_sha256",
        "upper_source_raw_sha256",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 intrinsic upper-channel snapshot members differ",
    )
    expected_derivations = {
        "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": 91,
        "CODEC_INTERSECTION": 160,
        "EXACT_BOOLEAN": 25,
        "NULLABLE_BRANCH": 145,
        "OBJECT_REFERENCE": 47,
        "RECORD_MEMBER_FOLD": 138,
        "SAFE_INTEGER_BAND": 247,
        "TAGGED_UNION_BRANCH": 22,
        "TEXT_BOUNDED_LANGUAGE": 183,
        "TEXT_BUILTIN_BOUNDED": 254,
        "TEXT_FINITE": 335,
    }
    expected_methods = {
        "ASCII_DFA_DYNAMIC_PROGRAMMING": 21,
        "CLOSED_BUILTIN_FORMULA": 51,
        "CODEC_INTERSECTION": 66,
        "FINITE_ENUMERATION": 58,
        "PINNED_UNICODE_PROFILE_PROGRAM": 18,
        "RULE_AWARE_COMPOSITION": 66,
    }
    _require(
        snapshot["correction_subgate"] == "A4-R475-V1-C2-U"
        and snapshot["acceptance_state"]
        == "ACCEPTED_LEGAL_DOMAIN_UPPER_CHANNEL_ONLY"
        and snapshot["formal_stage1_state"] == "NO-GO"
        and snapshot["next_bounded_packet"] == "A4-R475-V1-C2-A"
        and snapshot["source_freeze_id"] == freeze_snapshot["dual_source_freeze_id"]
        and snapshot["intrinsic_exactness_correction_contract_id"]
        == freeze_snapshot["intrinsic_exactness_correction_contract_id"]
        and snapshot["upper_source_raw_sha256"]
        == freeze_snapshot["upper_source_raw_sha256"]
        and snapshot["upper_output_schema_id"]
        == freeze_snapshot["upper_output_schema_id"]
        and snapshot["case_count"] == 66
        and snapshot["proof_step_count"] == 1_647
        and snapshot["derivation_kind_census"] == expected_derivations
        and snapshot["proof_method_case_census"] == expected_methods
        and snapshot["legal_domain_upper_minimum_octets"] == 29
        and snapshot["legal_domain_upper_maximum_octets"] == 524_288
        and snapshot["execution_pinned_input_file_count"] == 5
        and snapshot["execution_pinned_input_octets"] == 6_944_168
        and snapshot["official_output_file_count"] == 1
        and snapshot["attainer_output_absent_count"] == 4
        and snapshot["attainer_source_or_output_read_true_case_count"] == 0
        and snapshot["attainer_channel_consumed"] is False
        and snapshot["upper_result_accepted"] is True
        and snapshot["exact_maxima_accepted"] is False
        and snapshot["all_case_campaign_released"] is False
        and snapshot["acceptance_test_passed"] == 25,
        "S1-A4 intrinsic upper-channel disposition differs",
    )
    _require(
        snapshot["upper_result_id"]
        == "b57d8d494524ce964330fa2046c4d66f0c8a854b7eaa8fe1abae3bb09e5f8d2d"
        and snapshot["acceptance_report_id"]
        == "07ee9289eec657ff4907e00720fe29d449a6087b6ee5d4728a027fd8f5422123"
        and snapshot["legal_domain_upper_vector_sha256"]
        == "0791b5d5b97249ba4fac3b187efbe66a5cb85ba7c8ca3839279831fe25e540f5"
        and snapshot["upper_case_record_id_vector_sha256"]
        == "58ce6fe336c5001ab55cd18c1e6640723c6c0b9db3b39c1688c5d604d112cc0b",
        "S1-A4 intrinsic upper-channel semantic identity differs",
    )

    artifacts = (
        (
            "upper result",
            INTRINSIC_UPPER_CHANNEL_RESULT_PATH,
            snapshot["upper_result_raw_octets"],
            snapshot["upper_result_raw_sha256"],
        ),
        (
            "reviewer",
            INTRINSIC_UPPER_CHANNEL_REVIEWER_PATH,
            snapshot["reviewer_raw_octets"],
            snapshot["reviewer_raw_sha256"],
        ),
        (
            "acceptance report",
            INTRINSIC_UPPER_CHANNEL_REPORT_PATH,
            snapshot["acceptance_report_raw_octets"],
            snapshot["acceptance_report_raw_sha256"],
        ),
        (
            "acceptance test",
            INTRINSIC_UPPER_CHANNEL_TEST_PATH,
            snapshot["acceptance_test_raw_octets"],
            snapshot["acceptance_test_raw_sha256"],
        ),
        (
            "acceptance document",
            INTRINSIC_UPPER_CHANNEL_ACCEPTANCE_DOC_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    )
    artifact_bytes: dict[str, bytes] = {}
    for label, path, octets, digest in artifacts:
        _require(
            path.is_file() and not path.is_symlink(),
            f"A4-R475-V1-C2-U {label} absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == octets, f"A4-R475-V1-C2-U {label} size drifted")
        _require(_sha256(raw) == digest, f"A4-R475-V1-C2-U {label} hash drifted")
        artifact_bytes[label] = raw
    for path in INTRINSIC_C2_OFFICIAL_OUTPUT_PATHS[1:]:
        _require(
            not path.exists() and not path.is_symlink(),
            f"A4-R475-V1-C2-U attainer output exists before C2-A: {path.name}",
        )

    result = json.loads(artifact_bytes["upper result"])
    _require(
        artifact_bytes["upper result"]
        == (
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
        "S1-A4 intrinsic upper-channel result encoding differs",
    )
    result_payload = {
        name: value for name, value in result.items() if name != "upper_channel_result_id"
    }
    result_id = _sha256(
        _canonical_bytes(
            {
                "domain": INTRINSIC_UPPER_CHANNEL_RESULT_DOMAIN,
                "payload": result_payload,
            }
        )
    )
    _require(
        result.get("upper_channel_result_id")
        == snapshot["upper_result_id"]
        == result_id
        and result.get("packet") == "A4-R475-V1-C2-U"
        and result.get("source_freeze_id") == snapshot["source_freeze_id"]
        and result.get("source_sha256") == snapshot["upper_source_raw_sha256"]
        and result.get("output_schema_id") == snapshot["upper_output_schema_id"]
        and result.get("case_count") == snapshot["case_count"]
        and result.get("exactness_claimed") is False
        and result.get("attainer_channel_consumed") is False
        and result.get("formal_stage1_state") == "NO-GO"
        and result.get("next_bounded_packet") == "A4-R475-V1-C2-A",
        "S1-A4 intrinsic upper-channel result identity differs",
    )

    report = json.loads(artifact_bytes["acceptance report"])
    _require(
        artifact_bytes["acceptance report"]
        == (
            json.dumps(
                report,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
        "S1-A4 intrinsic upper-channel report encoding differs",
    )
    report_payload = {
        name: value
        for name, value in report.items()
        if name != "upper_channel_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes(
            {
                "domain": INTRINSIC_UPPER_CHANNEL_REPORT_DOMAIN,
                "payload": report_payload,
            }
        )
    )
    _require(
        report.get("upper_channel_acceptance_report_id")
        == snapshot["acceptance_report_id"]
        == report_id
        and report.get("upper_channel_result_id") == snapshot["upper_result_id"]
        and report.get("upper_result_raw_sha256")
        == snapshot["upper_result_raw_sha256"]
        and report.get("derivation_kind_census") == expected_derivations
        and report.get("proof_method_case_census") == expected_methods
        and report.get("attainer_source_or_output_read_true_case_count") == 0
        and report.get("attainer_channel_consumed") is False
        and report.get("exactness_claimed") is False
        and report.get("formal_stage1_state") == "NO-GO"
        and report.get("next_bounded_packet") == "A4-R475-V1-C2-A",
        "S1-A4 intrinsic upper-channel report differs",
    )
    reviewer = _load_intrinsic_upper_channel_reviewer()
    try:
        reconstructed_report = reviewer.verify(
            ROOT,
            artifact_bytes["upper result"],
        )
    except Exception as error:
        raise ControlFailure(
            f"A4-R475-V1-C2-U independent replay rejected: {error}"
        ) from None
    _require(
        reconstructed_report == report,
        "A4-R475-V1-C2-U independent replay differs",
    )

    reviewer_source = artifact_bytes["reviewer"].decode("utf-8")
    acceptance_test = artifact_bytes["acceptance test"].decode("utf-8")
    acceptance_doc = artifact_bytes["acceptance document"].decode("utf-8")
    reviewer_tree = ast.parse(reviewer_source)
    reviewer_imports = {
        alias.name
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reviewer_imports.update(
        node.module
        for node in ast.walk(reviewer_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(
        all(
            "intrinsic_upper_v49f" not in imported
            and "intrinsic_attainers" not in imported
            for imported in reviewer_imports
        )
        and "class CaseOracle" in reviewer_source
        and "def _reverse_dfa_upper" in reviewer_source,
        "A4-R475-V1-C2-U reviewer isolation differs",
    )
    for marker in (
        "test_c2u_independent_review_reads_only_its_declared_surface",
        "test_c2u_frozen_source_reproduces_result_in_attainer_free_sandbox",
        "test_c2u_reviewer_rejects_coherently_resealed_semantic_mutations",
        "test_c2u_reviewer_rejects_noncanonical_and_duplicate_json",
    ):
        _require(
            marker in acceptance_test,
            f"A4-R475-V1-C2-U acceptance-test marker absent: {marker}",
        )
    for marker in (
        "A4-R475-V1-C2-U",
        snapshot["upper_result_id"],
        snapshot["acceptance_report_id"],
        "25 passed",
        "A4-R475-V1-C2-A",
        "NO-GO",
    ):
        _require(
            marker in acceptance_doc,
            f"A4-R475-V1-C2-U acceptance marker absent: {marker}",
        )


def validate() -> dict[str, Any]:
    control = _load_control()
    _require(control.get("control_version") == 1, "unknown control version")
    _require(control.get("formal_stage1_state") == "NO-GO", "Stage 1 must remain NO-GO")
    _require(
        control.get("offline_stage2_state") == "BLOCKED",
        "offline Stage 2 state differs",
    )
    _require(
        control.get("live_activation_state") == "BLOCKED",
        "live activation must remain blocked",
    )
    _validate_gate_graph(control)
    _validate_navigation(control["active_gate"])
    s1_a2_snapshot = control.get("s1_a2_snapshot")
    _require(isinstance(s1_a2_snapshot, dict), "s1_a2_snapshot is missing")
    _validate_s1_a2_snapshot(s1_a2_snapshot)
    s1_a3_snapshot = control.get("s1_a3_snapshot")
    _require(isinstance(s1_a3_snapshot, dict), "s1_a3_snapshot is missing")
    _validate_s1_a3_snapshot(s1_a3_snapshot, s1_a2_snapshot)
    s1_a4_boundary_snapshot = control.get("s1_a4_boundary_snapshot")
    _require(
        isinstance(s1_a4_boundary_snapshot, dict),
        "s1_a4_boundary_snapshot is missing",
    )
    _validate_s1_a4_boundary_snapshot(s1_a4_boundary_snapshot, s1_a3_snapshot)
    s1_a4_fail_first_snapshot = control.get("s1_a4_fail_first_snapshot")
    _require(
        isinstance(s1_a4_fail_first_snapshot, dict),
        "s1_a4_fail_first_snapshot is missing",
    )
    _validate_s1_a4_fail_first_snapshot(
        s1_a4_fail_first_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_verifier_snapshot = control.get("s1_a4_verifier_snapshot")
    _require(
        isinstance(s1_a4_verifier_snapshot, dict),
        "s1_a4_verifier_snapshot is missing",
    )
    _validate_s1_a4_verifier_snapshot(
        s1_a4_verifier_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_producer_snapshot = control.get("s1_a4_producer_snapshot")
    _require(
        isinstance(s1_a4_producer_snapshot, dict),
        "s1_a4_producer_snapshot is missing",
    )
    _validate_s1_a4_producer_snapshot(
        s1_a4_producer_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_six_case_target_snapshot = control.get("s1_a4_six_case_target_snapshot")
    _require(
        isinstance(s1_a4_six_case_target_snapshot, dict),
        "s1_a4_six_case_target_snapshot is missing",
    )
    _validate_s1_a4_six_case_target_snapshot(
        s1_a4_six_case_target_snapshot,
        s1_a4_boundary_snapshot,
        s1_a4_producer_snapshot,
    )

    snapshot = control.get("seed_snapshot")
    _require(isinstance(snapshot, dict), "seed_snapshot is missing")
    case435_snapshot = control.get("s1_a4_case435_attainability_falsification_snapshot")
    _require(
        isinstance(case435_snapshot, dict),
        "s1_a4_case435_attainability_falsification_snapshot is missing",
    )
    _validate_s1_a4_case435_attainability_falsification_snapshot(
        case435_snapshot,
        s1_a4_six_case_target_snapshot,
        snapshot,
    )
    profile_scope_snapshot = control.get("s1_a4_profile_attainability_scope_snapshot")
    _require(
        isinstance(profile_scope_snapshot, dict),
        "s1_a4_profile_attainability_scope_snapshot is missing",
    )
    _validate_s1_a4_profile_attainability_scope_snapshot(
        profile_scope_snapshot,
        case435_snapshot,
        snapshot,
    )
    dependency_closure_snapshot = control.get(
        "s1_a4_case435_dependency_closure_snapshot"
    )
    _require(
        isinstance(dependency_closure_snapshot, dict),
        "s1_a4_case435_dependency_closure_snapshot is missing",
    )
    _validate_s1_a4_case435_dependency_closure_snapshot(
        dependency_closure_snapshot,
        profile_scope_snapshot,
        case435_snapshot,
    )
    upper_snapshot = control.get("s1_a4_case435_upper_snapshot")
    _require(
        isinstance(upper_snapshot, dict),
        "s1_a4_case435_upper_snapshot is missing",
    )
    upper_certificate = _validate_s1_a4_case435_upper_snapshot(
        upper_snapshot,
        dependency_closure_snapshot,
    )
    attainer_snapshot = control.get("s1_a4_case435_attainer_snapshot")
    _require(
        isinstance(attainer_snapshot, dict),
        "s1_a4_case435_attainer_snapshot is missing",
    )
    attainer_certificate = _validate_s1_a4_case435_attainer_snapshot(
        attainer_snapshot,
        dependency_closure_snapshot,
    )
    exactness_join_snapshot = control.get("s1_a4_case435_exactness_join_snapshot")
    _require(
        isinstance(exactness_join_snapshot, dict),
        "s1_a4_case435_exactness_join_snapshot is missing",
    )
    _validate_s1_a4_case435_exactness_join_snapshot(
        exactness_join_snapshot,
        dependency_closure_snapshot,
        upper_snapshot,
        attainer_snapshot,
        upper_certificate,
        attainer_certificate,
    )
    authority_transition_snapshot = control.get(
        "s1_a4_case435_authority_transition_snapshot"
    )
    _require(
        isinstance(authority_transition_snapshot, dict),
        "s1_a4_case435_authority_transition_snapshot is missing",
    )
    _validate_s1_a4_case435_authority_transition_snapshot(
        authority_transition_snapshot,
        exactness_join_snapshot,
        snapshot,
        s1_a3_snapshot,
        s1_a4_boundary_snapshot,
    )
    verifier_expansion_v0_snapshot = control.get("s1_a4_verifier_expansion_v0_snapshot")
    _require(
        isinstance(verifier_expansion_v0_snapshot, dict),
        "s1_a4_verifier_expansion_v0_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v0_snapshot(
        verifier_expansion_v0_snapshot,
        s1_a4_verifier_snapshot,
        s1_a4_boundary_snapshot,
        authority_transition_snapshot,
    )
    verifier_expansion_v1_snapshot = control.get("s1_a4_verifier_expansion_v1_snapshot")
    _require(
        isinstance(verifier_expansion_v1_snapshot, dict),
        "s1_a4_verifier_expansion_v1_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v1_snapshot(
        verifier_expansion_v1_snapshot,
        verifier_expansion_v0_snapshot,
        authority_transition_snapshot,
    )
    verifier_expansion_v2_snapshot = control.get("s1_a4_verifier_expansion_v2_snapshot")
    _require(
        isinstance(verifier_expansion_v2_snapshot, dict),
        "s1_a4_verifier_expansion_v2_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v2_snapshot(
        verifier_expansion_v2_snapshot,
        verifier_expansion_v1_snapshot,
        authority_transition_snapshot,
    )
    case435_context_pack_snapshot = control.get("s1_a4_case435_context_pack_snapshot")
    _require(
        isinstance(case435_context_pack_snapshot, dict),
        "s1_a4_case435_context_pack_snapshot is missing",
    )
    _validate_s1_a4_case435_context_pack_snapshot(
        case435_context_pack_snapshot,
        verifier_expansion_v2_snapshot,
        authority_transition_snapshot,
    )
    verifier_expansion_v3_snapshot = control.get("s1_a4_verifier_expansion_v3_snapshot")
    _require(
        isinstance(verifier_expansion_v3_snapshot, dict),
        "s1_a4_verifier_expansion_v3_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v3_snapshot(
        verifier_expansion_v3_snapshot,
        verifier_expansion_v2_snapshot,
        case435_context_pack_snapshot,
        authority_transition_snapshot,
    )
    verifier_expansion_v4_snapshot = control.get("s1_a4_verifier_expansion_v4_snapshot")
    _require(
        isinstance(verifier_expansion_v4_snapshot, dict),
        "s1_a4_verifier_expansion_v4_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v4_snapshot(
        verifier_expansion_v4_snapshot,
        verifier_expansion_v3_snapshot,
        authority_transition_snapshot,
    )
    verifier_acceptance_snapshot = control.get("s1_a4_verifier_acceptance_snapshot")
    _require(
        isinstance(verifier_acceptance_snapshot, dict),
        "s1_a4_verifier_acceptance_snapshot is missing",
    )
    _validate_s1_a4_verifier_acceptance_snapshot(
        verifier_acceptance_snapshot,
        verifier_expansion_v4_snapshot,
    )
    producer_expansion_snapshot = control.get("s1_a4_producer_expansion_snapshot")
    _require(
        isinstance(producer_expansion_snapshot, dict),
        "s1_a4_producer_expansion_snapshot is missing",
    )
    _validate_s1_a4_producer_expansion_snapshot(
        producer_expansion_snapshot,
        s1_a4_producer_snapshot,
        verifier_acceptance_snapshot,
        case435_context_pack_snapshot,
    )
    parent_runner_snapshot = control.get("s1_a4_parent_runner_snapshot")
    _require(
        isinstance(parent_runner_snapshot, dict),
        "s1_a4_parent_runner_snapshot is missing",
    )
    _validate_s1_a4_parent_runner_snapshot(
        parent_runner_snapshot,
        producer_expansion_snapshot,
    )
    pilot_end_to_end_snapshot = control.get("s1_a4_pilot_end_to_end_snapshot")
    _require(
        isinstance(pilot_end_to_end_snapshot, dict),
        "s1_a4_pilot_end_to_end_snapshot is missing",
    )
    _validate_s1_a4_pilot_end_to_end_snapshot(
        pilot_end_to_end_snapshot,
        parent_runner_snapshot,
    )
    all_case_contract_snapshot = control.get("s1_a4_all_case_contract_snapshot")
    _require(
        isinstance(all_case_contract_snapshot, dict),
        "s1_a4_all_case_contract_snapshot is missing",
    )
    _validate_s1_a4_all_case_contract_snapshot(
        all_case_contract_snapshot,
        pilot_end_to_end_snapshot,
    )
    all_case_verifier_foundation_snapshot = control.get(
        "s1_a4_all_case_verifier_foundation_snapshot"
    )
    _require(
        isinstance(all_case_verifier_foundation_snapshot, dict),
        "s1_a4_all_case_verifier_foundation_snapshot is missing",
    )
    _validate_s1_a4_all_case_verifier_foundation_snapshot(
        all_case_verifier_foundation_snapshot,
        all_case_contract_snapshot,
    )
    intrinsic_attainability_snapshot = control.get(
        "s1_a4_intrinsic_attainability_snapshot"
    )
    _require(
        isinstance(intrinsic_attainability_snapshot, dict),
        "s1_a4_intrinsic_attainability_snapshot is missing",
    )
    _validate_s1_a4_intrinsic_attainability_snapshot(
        intrinsic_attainability_snapshot,
        all_case_verifier_foundation_snapshot,
    )
    intrinsic_correction_contract_snapshot = control.get(
        "s1_a4_intrinsic_correction_contract_snapshot"
    )
    _require(
        isinstance(intrinsic_correction_contract_snapshot, dict),
        "s1_a4_intrinsic_correction_contract_snapshot is missing",
    )
    _validate_s1_a4_intrinsic_correction_contract_snapshot(
        intrinsic_correction_contract_snapshot,
        intrinsic_attainability_snapshot,
    )
    intrinsic_dual_source_freeze_snapshot = control.get(
        "s1_a4_intrinsic_dual_source_freeze_snapshot"
    )
    _require(
        isinstance(intrinsic_dual_source_freeze_snapshot, dict),
        "s1_a4_intrinsic_dual_source_freeze_snapshot is missing",
    )
    _validate_s1_a4_intrinsic_dual_source_freeze_snapshot(
        intrinsic_dual_source_freeze_snapshot,
        intrinsic_correction_contract_snapshot,
    )
    intrinsic_upper_channel_snapshot = control.get(
        "s1_a4_intrinsic_upper_channel_snapshot"
    )
    _require(
        isinstance(intrinsic_upper_channel_snapshot, dict),
        "s1_a4_intrinsic_upper_channel_snapshot is missing",
    )
    _validate_s1_a4_intrinsic_upper_channel_snapshot(
        intrinsic_upper_channel_snapshot,
        intrinsic_dual_source_freeze_snapshot,
    )
    generator_raw = GENERATOR_PATH.read_bytes()
    catalog_raw = CATALOG_PATH.read_bytes()
    _require(
        _sha256(generator_raw) == snapshot["generator_sha256"], "seed generator drifted"
    )
    _require(
        _sha256(catalog_raw) == snapshot["catalog_sha256"],
        "stored seed catalog drifted",
    )
    _require(
        len(catalog_raw) == snapshot["catalog_raw_octets"],
        "stored catalog size drifted",
    )

    generator = _load_generator()
    prospective = generator.build_catalog(ROOT)
    prospective_raw = generator._pretty_bytes(prospective)
    _require(
        len(prospective_raw) == snapshot["prospective_raw_octets"],
        "prospective seed size drifted",
    )
    _require(
        _sha256(prospective_raw) == snapshot["prospective_sha256"],
        "prospective seed bytes drifted",
    )
    _require(
        prospective["seed_catalog_id"] == snapshot["prospective_seed_catalog_id"],
        "prospective seed identity drifted",
    )
    _require(
        (catalog_raw != prospective_raw) is snapshot["catalog_stale"],
        "catalog staleness differs",
    )
    if control["gate_states"]["S1-A1"]["state"] == "ACCEPTED":
        _require(snapshot["catalog_stale"] is False, "accepted S1-A1 seed is stale")
        _require(snapshot["focused_failed"] == 0, "accepted S1-A1 has failures")
        _require(snapshot["focused_passed"] > 0, "accepted S1-A1 has no tests")
    operational_limit = snapshot["operational_output_maximum_octets"]
    _require(
        len(catalog_raw) <= operational_limit,
        "stored seed exceeds the operational output target",
    )
    _require(
        operational_limit - len(catalog_raw) == snapshot["operational_headroom_octets"],
        "operational seed headroom drifted",
    )
    f0 = {
        row["resource_name"]: row["ceiling_value"]
        for row in prospective["f0_seed_ceiling_catalog"][
            "ordered_platform_ceiling_records"
        ]
    }
    _require(
        f0["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
        == snapshot["strict_individual_file_upper_octets"],
        "strict individual-file cap drifted",
    )
    return control


def main() -> int:
    try:
        control = validate()
        snapshot = control["seed_snapshot"]
        print(
            "STAGE1_CONTROL_OK "
            f"active_gate={control['active_gate']} "
            f"formal_state={control['formal_stage1_state']} "
            f"catalog_stale={str(snapshot['catalog_stale']).lower()} "
            f"s1_a2_comparison_id={control['s1_a2_snapshot']['comparison_payload_id']} "
            f"s1_a3_manifest_id={control['s1_a3_snapshot']['finalization_manifest_id']} "
            f"s1_a4_boundary_id={control['s1_a4_boundary_snapshot']['constructive_boundary_id']} "
            f"s1_a4_fail_first_sha256={control['s1_a4_fail_first_snapshot']['fail_first_test_raw_sha256']} "
            f"s1_a4_verifier_sha256={control['s1_a4_verifier_expansion_v4_snapshot']['verifier_raw_sha256']} "
            f"s1_a4_producer_sha256={control['s1_a4_producer_snapshot']['producer_raw_sha256']} "
            f"s1_a4_six_case_target_sha256={control['s1_a4_six_case_target_snapshot']['fail_first_test_raw_sha256']} "
            f"s1_a4_case435_analysis_id={control['s1_a4_case435_attainability_falsification_snapshot']['attainability_analysis_id']} "
            f"s1_a4_case435_gap_octets={control['s1_a4_case435_attainability_falsification_snapshot']['p3_unattainable_gap_octets']} "
            f"s1_a4_profile_scope_audit_id={control['s1_a4_profile_attainability_scope_snapshot']['profile_attainability_scope_audit_id']} "
            f"s1_a4_profile_scope_affected={control['s1_a4_profile_attainability_scope_snapshot']['structural_superset_program_count']}/"
            f"{control['s1_a4_profile_attainability_scope_snapshot']['structural_superset_scope_case_count']} "
            f"s1_a4_case435_dependency_audit_id={control['s1_a4_case435_dependency_closure_snapshot']['case435_dependency_closure_audit_id']} "
            f"s1_a4_case435_components={control['s1_a4_case435_dependency_closure_snapshot']['ordinary_singleton_component_count']}+"
            f"{control['s1_a4_case435_dependency_closure_snapshot']['a1_coupled_field_count']} "
            f"s1_a4_case435_upper_certificate_id={control['s1_a4_case435_upper_snapshot']['case435_upper_certificate_id']} "
            f"s1_a4_case435_upper_octets={control['s1_a4_case435_upper_snapshot']['exact_upper_bound_octets']} "
            f"s1_a4_case435_attainer_certificate_id={control['s1_a4_case435_attainer_snapshot']['attainer_certificate_id']} "
            f"s1_a4_case435_attainer_octets={control['s1_a4_case435_attainer_snapshot']['measured_attainer_canonical_octets']} "
            f"s1_a4_case435_exactness_join_id={control['s1_a4_case435_exactness_join_snapshot']['case435_exactness_join_certificate_id']} "
            f"s1_a4_case435_exact_maximum_octets={control['s1_a4_case435_exactness_join_snapshot']['exact_maximum_octets']} "
            f"s1_a4_case435_successor_seed_id={control['s1_a4_case435_authority_transition_snapshot']['successor_seed_catalog_id']} "
            f"s1_a4_case435_successor_target_id={control['s1_a4_case435_authority_transition_snapshot']['successor_six_case_target_id']} "
            f"s1_a4_case435_verifier_expansion={control['s1_a4_case435_authority_transition_snapshot']['verifier_expansion_state']} "
            f"s1_a4_case435_context_pack_id={control['s1_a4_case435_context_pack_snapshot']['case435_context_pack_boundary_delta_id']} "
            f"s1_a4_case435_packed_file_headroom={control['s1_a4_case435_context_pack_snapshot']['packed_input_file_headroom']} "
            f"s1_a4_verifier_packet={control['s1_a4_verifier_acceptance_snapshot']['correction_subgate']} "
            f"s1_a4_verifier_report_id={control['s1_a4_verifier_acceptance_snapshot']['report_id']} "
            f"s1_a4_verifier_next={control['s1_a4_verifier_acceptance_snapshot']['next_subgate']} "
            f"s1_a4_producer_packet={control['s1_a4_producer_expansion_snapshot']['correction_subgate']} "
            f"s1_a4_producer_report_id={control['s1_a4_producer_expansion_snapshot']['report_id']} "
            f"s1_a4_producer_next={control['s1_a4_producer_expansion_snapshot']['next_subgate']} "
            f"s1_a4_runner_packet={control['s1_a4_parent_runner_snapshot']['correction_subgate']} "
            f"s1_a4_runner_report_id={control['s1_a4_parent_runner_snapshot']['report_id']} "
            f"s1_a4_runner_next={control['s1_a4_parent_runner_snapshot']['next_subgate']} "
            f"s1_a4_pilot_acceptance_packet={control['s1_a4_pilot_end_to_end_snapshot']['correction_subgate']} "
            f"s1_a4_pilot_acceptance_report_id={control['s1_a4_pilot_end_to_end_snapshot']['report_id']} "
            f"s1_a4_pilot_acceptance_next={control['s1_a4_pilot_end_to_end_snapshot']['next_subgate']} "
            f"s1_a4_all_case_contract_id={control['s1_a4_all_case_contract_snapshot']['contract_id']} "
            f"s1_a4_all_case_contract_report_id={control['s1_a4_all_case_contract_snapshot']['report_id']} "
            f"s1_a4_all_case_contract_packet={control['s1_a4_all_case_contract_snapshot']['correction_subgate']} "
            f"s1_a4_all_case_verifier_packet={control['s1_a4_all_case_verifier_foundation_snapshot']['correction_subgate']} "
            f"s1_a4_all_case_verifier_report_id={control['s1_a4_all_case_verifier_foundation_snapshot']['report_id']} "
            f"s1_a4_all_case_verifier_next={control['s1_a4_all_case_verifier_foundation_snapshot']['next_bounded_packet']} "
            f"s1_a4_intrinsic_attainability_packet={control['s1_a4_intrinsic_attainability_snapshot']['correction_subgate']} "
            f"s1_a4_intrinsic_attainability_id={control['s1_a4_intrinsic_attainability_snapshot']['attainability_falsification_id']} "
            f"s1_a4_intrinsic_contradictions={control['s1_a4_intrinsic_attainability_snapshot']['contradiction_case_count']}/"
            f"{control['s1_a4_intrinsic_attainability_snapshot']['intrinsic_case_count']} "
            f"s1_a4_intrinsic_case8={control['s1_a4_intrinsic_attainability_snapshot']['case8_exact_legal_maximum_octets']}/"
            f"{control['s1_a4_intrinsic_attainability_snapshot']['case8_p2_upper_bound_octets']} "
            f"s1_a4_intrinsic_attainability_next={control['s1_a4_intrinsic_attainability_snapshot']['next_bounded_packet']} "
            f"s1_a4_intrinsic_correction_packet={control['s1_a4_intrinsic_correction_contract_snapshot']['correction_subgate']} "
            f"s1_a4_intrinsic_correction_contract_id={control['s1_a4_intrinsic_correction_contract_snapshot']['contract_id']} "
            f"s1_a4_intrinsic_correction_census={control['s1_a4_intrinsic_correction_contract_snapshot']['total_step_records']}/"
            f"{control['s1_a4_intrinsic_correction_contract_snapshot']['total_case_dependency_records']} "
            f"s1_a4_intrinsic_correction_next={control['s1_a4_intrinsic_correction_contract_snapshot']['next_bounded_packet']} "
            f"s1_a4_intrinsic_source_freeze_packet={control['s1_a4_intrinsic_dual_source_freeze_snapshot']['correction_subgate']} "
            f"s1_a4_intrinsic_source_freeze_id={control['s1_a4_intrinsic_dual_source_freeze_snapshot']['dual_source_freeze_id']} "
            f"s1_a4_intrinsic_source_freeze_report_id={control['s1_a4_intrinsic_dual_source_freeze_snapshot']['acceptance_report_id']} "
            f"s1_a4_intrinsic_source_freeze_absent_outputs={control['s1_a4_intrinsic_dual_source_freeze_snapshot']['pre_execution_absent_output_count']} "
            f"s1_a4_intrinsic_source_freeze_next={control['s1_a4_intrinsic_dual_source_freeze_snapshot']['next_bounded_packet']} "
            f"s1_a4_intrinsic_upper_packet={control['s1_a4_intrinsic_upper_channel_snapshot']['correction_subgate']} "
            f"s1_a4_intrinsic_upper_result_id={control['s1_a4_intrinsic_upper_channel_snapshot']['upper_result_id']} "
            f"s1_a4_intrinsic_upper_report_id={control['s1_a4_intrinsic_upper_channel_snapshot']['acceptance_report_id']} "
            f"s1_a4_intrinsic_upper_census={control['s1_a4_intrinsic_upper_channel_snapshot']['case_count']}/"
            f"{control['s1_a4_intrinsic_upper_channel_snapshot']['proof_step_count']} "
            f"s1_a4_intrinsic_upper_next={control['s1_a4_intrinsic_upper_channel_snapshot']['next_bounded_packet']} "
            f"s1_a4_next_packet={control['s1_a4_intrinsic_upper_channel_snapshot']['next_bounded_packet']} "
            f"prospective_raw_octets={snapshot['prospective_raw_octets']} "
            f"strict_upper_octets={snapshot['strict_individual_file_upper_octets']}"
        )
        return 0
    except (ControlFailure, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"STAGE1_CONTROL_INVALID: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
