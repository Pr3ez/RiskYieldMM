from __future__ import annotations

import hashlib
from dataclasses import replace
from itertools import product

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    MAX_CAPACITY_MEASUREMENT_NEUTRALITY_PREFIX_OCTETS_V49F,
    MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F,
    RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F,
    RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F,
    RAW_V7_PHYSICAL_NEUTRALITY_CLAIM_SCOPE_V49F,
    CapacityMeasurementLiteralNeutralityTraceV49F,
    CapacityMeasurementNeutralityArmV49FV7,
    CapacityMeasurementNeutralityReportV49F,
    CapacityMeasurementPhysicalNeutralityTraceV49F,
    compare_capacity_measurement_neutrality_v49f,
)


def _literal(
    arm: CapacityMeasurementNeutralityArmV49FV7,
) -> CapacityMeasurementLiteralNeutralityTraceV49F:
    return CapacityMeasurementLiteralNeutralityTraceV49F(
        neutrality_arm=arm,
        raw_prefix_bytes=b"raw-prefix",
        actor_prefix_bytes=b"actor-prefix",
        projection_prefix_bytes=b"projection-prefix",
        logical_output_bytes=b"logical-output",
        outcome_classes=("PASS",),
    )


def _physical(
    arm: CapacityMeasurementNeutralityArmV49FV7,
) -> CapacityMeasurementPhysicalNeutralityTraceV49F:
    return CapacityMeasurementPhysicalNeutralityTraceV49F(
        neutrality_arm=arm,
        actor_event_kinds=("RAW_INGRESS_COMMITTED", "PARSER_TRANSITION"),
        causal_parent_ordinals=((), (0,)),
        logical_frames=(("PONG", hashlib.sha256(b"").hexdigest()),),
        admission_decisions=("ADMITTED",),
        operation_outcomes=("PASS",),
        runtime_states=("SESSION_COMMITTED",),
        chain_verified=True,
        projection_verified=True,
    )


def test_every_admissible_v7_neutrality_arm_keeps_lifecycle_journaling_on() -> None:
    assert tuple(CapacityMeasurementNeutralityArmV49FV7) == (
        CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF,
        CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON,
    )
    for arm in CapacityMeasurementNeutralityArmV49FV7:
        assert arm.lifecycle_journaling_enabled is True
        assert (
            arm.raw_protocol_profile
            == RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
        )
    assert (
        CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF.resource_probes_enabled
        is False
    )
    assert (
        CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON.resource_probes_enabled
        is True
    )


@pytest.mark.parametrize(
    "bad_arm",
    (
        "RAW_V6_NO_LIFECYCLE",
        "RAW_V7_RESOURCE_PROBES_OFF",
        False,
        None,
    ),
)
def test_neutrality_traces_reject_untagged_or_no_lifecycle_arms(
    bad_arm: object,
) -> None:
    with pytest.raises(TypeError, match="Raw-V7 lifecycle-on arm"):
        replace(
            _literal(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
            neutrality_arm=bad_arm,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"outcome_classes": ["PASS"]}, "bounded exact tuple"),
        ({"outcome_classes": iter(("PASS",))}, "bounded exact tuple"),
        ({"outcome_classes": (1,)}, "entries must be exact strings"),
        ({"raw_prefix_bytes": bytearray(b"raw")}, "exact bytes"),
    ),
)
def test_literal_trace_rejects_sequence_and_element_type_substitution(
    changes: dict[str, object], message: str
) -> None:
    trace = _literal(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF)
    with pytest.raises(CanonicalizationError, match=message):
        replace(trace, **changes)


def test_literal_trace_enforces_one_over_byte_item_and_utf8_ceilings() -> None:
    trace = _literal(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF)
    with pytest.raises(CanonicalizationError, match="octet ceiling"):
        replace(
            trace,
            raw_prefix_bytes=b"x"
            * (MAX_CAPACITY_MEASUREMENT_NEUTRALITY_PREFIX_OCTETS_V49F + 1),
        )
    with pytest.raises(CanonicalizationError, match="bounded exact tuple"):
        replace(
            trace,
            outcome_classes=("PASS",)
            * (MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F + 1),
        )
    with pytest.raises(CanonicalizationError, match="UTF-8 octet ceiling"):
        replace(trace, outcome_classes=("😀" * 64 + "a",))


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"actor_event_kinds": ["RAW_INGRESS_COMMITTED"]}, "bounded exact tuple"),
        ({"admission_decisions": iter(("ADMITTED",))}, "bounded exact tuple"),
        ({"operation_outcomes": (1,)}, "entries must be exact strings"),
        ({"runtime_states": ["SESSION_COMMITTED"]}, "bounded exact tuple"),
        ({"logical_frames": [["PONG", "0" * 64]]}, "exact tuple"),
        (
            {"causal_parent_ordinals": [(), (0,)]},
            "causal_parent_ordinals must align exactly",
        ),
        (
            {"causal_parent_ordinals": ((), [0])},
            "exact earlier event ordinals",
        ),
    ),
)
def test_physical_trace_rejects_outer_inner_and_element_type_substitution(
    changes: dict[str, object], message: str
) -> None:
    trace = _physical(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF)
    with pytest.raises(CanonicalizationError, match=message):
        replace(trace, **changes)


def test_physical_trace_enforces_one_over_sequence_ceiling() -> None:
    trace = _physical(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF)
    with pytest.raises(CanonicalizationError, match="bounded exact tuple"):
        replace(
            trace,
            actor_event_kinds=("EVENT",)
            * (MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F + 1),
        )
    with pytest.raises(CanonicalizationError, match="item ceiling"):
        replace(
            trace,
            logical_frames=(("PONG", "0" * 64),)
            * (MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F + 1),
        )


def test_literal_comparator_only_claims_equivalence_inside_v7_lifecycle_baseline() -> (
    None
):
    for left_arm, right_arm in product(
        CapacityMeasurementNeutralityArmV49FV7, repeat=2
    ):
        report = compare_capacity_measurement_neutrality_v49f(
            _literal(left_arm), _literal(right_arm)
        )
        assert report.passed
        assert (
            report.lifecycle_baseline_profile
            == RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
        )
        assert report.left_arm is left_arm
        assert report.right_arm is right_arm
        assert (
            report.equivalence_claim_scope == RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F
        )
        assert report.byte_or_root_equivalence_claimed is True

    changed = replace(
        _literal(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON),
        raw_prefix_bytes=b"changed",
    )
    report = compare_capacity_measurement_neutrality_v49f(
        _literal(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
        changed,
    )
    assert not report.passed
    assert report.mismatch_fields == ("raw_prefix_bytes",)


def test_physical_comparator_never_claims_byte_or_root_equivalence() -> None:
    for left_arm, right_arm in product(
        CapacityMeasurementNeutralityArmV49FV7, repeat=2
    ):
        report = compare_capacity_measurement_neutrality_v49f(
            _physical(left_arm), _physical(right_arm)
        )
        assert report.passed
        assert (
            report.lifecycle_baseline_profile
            == RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
        )
        assert (
            report.equivalence_claim_scope
            == RAW_V7_PHYSICAL_NEUTRALITY_CLAIM_SCOPE_V49F
        )
        assert report.byte_or_root_equivalence_claimed is False


def test_callers_cannot_construct_a_passing_neutrality_report() -> None:
    with pytest.raises(TypeError, match="only be constructed by the comparator"):
        CapacityMeasurementNeutralityReportV49F(
            comparison_profile=("LITERAL_DETERMINISTIC_AUTHORITY_PREFIX_RAW_V7_V49F"),
            lifecycle_baseline_profile=(
                RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
            ),
            left_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
            right_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON),
            equivalence_claim_scope=RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F,
            byte_or_root_equivalence_claimed=True,
            mismatch_fields=(),
        )
