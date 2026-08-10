#!/usr/bin/env python3
"""Independent fail-closed attainability check for frozen V2 pilot case 435.

This is not a producer and it does not validate a candidate.  It answers the
question that must be settled before the six-case verifier can honestly accept
case 435: can the retained ``TargetObservationV2`` at the frozen max64/full67
coordinate reach the structural P2 endpoint of 262,143 canonical octets?

The calculation deliberately constructs an *over-approximation* of every
field-observation state admitted by the frozen target registry.  It allows
some combinations that the exact checkpoint/context predicates would later
reject.  Therefore its result is an upper bound on the legal P1 domain, not a
candidate and not an attainable maximum.  If even that upper bound is below
P2.U, P3 equality is impossible.
"""

import hashlib
import json
import pathlib
import sys

SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
INVENTORY_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)

SEED_RAW_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
INVENTORY_RAW_SHA256 = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)
REGISTRY_RAW_SHA256 = "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"

CASE_POSITION = 435
PROFILE_POSITION = 369
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
TARGET_TYPE = "TargetObservationV2"
TARGET_FIELD_TYPE = "TargetFieldObservationV1"
TARGET_CONTEXT_TYPE = "TargetObservationContextV2"
MEASURED_SEQUENCE_ORDINAL = 64
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
SOURCE_ERROR_DETAIL_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
ANALYSIS_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435AttainabilityFalsificationV1V4_9F_RawV8"
)


class AttainabilityCheckError(RuntimeError):
    """Raised when an authority or derivation invariant differs."""


def _require(condition, message):
    if not condition:
        raise AttainabilityCheckError(message)


def _canonical_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(canonicalization_version, schema_version, domain, payload):
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization_version,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _load_pinned(root, relative_path, expected_sha256):
    path = root / relative_path
    raw = path.read_bytes()
    _require(
        _sha256(raw) == expected_sha256, f"authority hash differs: {relative_path}"
    )
    value = json.loads(raw)
    _require(type(value) is dict, f"authority root differs: {relative_path}")
    return value


def _index(rows, member_name, expected_count, label):
    _require(
        type(rows) is list and len(rows) == expected_count, f"{label} count differs"
    )
    result = {}
    for row in rows:
        key = row[member_name]
        _require(key not in result, f"{label} identifier is duplicated")
        result[key] = row
    return result


def _record_identity(record, descriptor, canonicalization_version, schema_version):
    identity_field = descriptor["identity_field"]
    _require(type(identity_field) is str, "record identity field is absent")
    payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    record[identity_field] = _semantic_id(
        canonicalization_version,
        schema_version,
        descriptor["described_record_domain"],
        payload,
    )


def _longest_canonical_text(values):
    _require(type(values) is list and values, "closed text domain is empty")
    _require(all(type(value) is str for value in values), "text domain differs")
    return max(values, key=lambda value: (len(_canonical_bytes(value)), value))


def _ascii_dfa_accepts(descriptor, value):
    raw = value.encode("ascii")
    if not descriptor["minimum_octets"] <= len(raw) <= descriptor["maximum_octets"]:
        return False
    state = descriptor["start_state"]
    for byte in raw:
        matches = [
            row
            for row in descriptor["ordered_transition_rows"]
            if row["source_state"] == state
            and row["inclusive_byte_minimum"] <= byte <= row["inclusive_byte_maximum"]
        ]
        if len(matches) != 1:
            return False
        state = matches[0]["target_state"]
    return state in descriptor["ordered_accepting_states"]


def _require_dfa_has_no_json_expanding_bytes(descriptor, label):
    for row in descriptor["ordered_transition_rows"]:
        minimum = row["inclusive_byte_minimum"]
        maximum = row["inclusive_byte_maximum"]
        _require(
            minimum >= 32
            and not minimum <= ord('"') <= maximum
            and not minimum <= ord("\\") <= maximum,
            f"{label} admits a JSON-expanding ASCII byte",
        )


def _maximum_scalar(constraint, vocabularies):
    profile = constraint["scalar_profile"]
    if profile == "EXACT_BOOL":
        return False
    if profile == "SAFE_IJSON_UINT":
        return constraint["integer_maximum"]
    if profile == "ENUM":
        return _longest_canonical_text(
            vocabularies[constraint["vocabulary_id"]]["members"]
        )
    if profile == "SHA256":
        return "f" * 64
    if profile == "UINT128_DECIMAL":
        return constraint["decimal_maximum"]
    if profile == "PLATFORM_ERRNO":
        return "E" + "A" * 63
    raise AttainabilityCheckError(f"scalar profile is unresolved: {profile}")


def _maximum_target_value(descriptor, constraints, shapes, vocabularies, censored=None):
    constraint = constraints[descriptor["value_constraint_id"]]
    kind = descriptor["value_kind"]
    if kind == "DURATION_BOUND":
        maximum = constraint["integer_maximum"]
        relation = (
            "EXACT"
            if censored is None
            else {
                "INTERVAL": "INTERVAL",
                "LEFT": "UPPER_BOUND",
                "RIGHT": "LOWER_BOUND",
            }[censored]
        )
        return {
            "kind": kind,
            "lower_nanoseconds": (
                maximum if relation in {"EXACT", "LOWER_BOUND", "INTERVAL"} else None
            ),
            "relation": relation,
            "upper_nanoseconds": (
                maximum if relation in {"EXACT", "UPPER_BOUND", "INTERVAL"} else None
            ),
        }
    if kind in {"BOOL", "UINT", "TEXT"}:
        return {"kind": kind, "value": _maximum_scalar(constraint, vocabularies)}
    if kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
        present = {
            "kind": kind,
            "present": True,
            "value": _maximum_scalar(constraint, vocabularies),
        }
        absent = {"kind": kind, "present": False, "value": None}
        return max((present, absent), key=lambda value: len(_canonical_bytes(value)))
    item_constraint = constraints[constraint["collection_item_constraint_id"]]
    shape = shapes[descriptor["value_shape_id"]]
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        maximum_items = shape["maximum_items"]
        item = _maximum_scalar(item_constraint, vocabularies)
        # Repetition is an intentional over-approximation for TEXT_LIST.  It
        # cannot understate a legal sequence even if uniqueness later applies.
        values = [item] * maximum_items
        return {"kind": kind, "values": values}
    if kind == "FIXED_UINT_MAP":
        item = _maximum_scalar(item_constraint, vocabularies)
        return {
            "kind": kind,
            "ordered": [
                {"key": key, "value": item} for key in descriptor["value_shape_keys"]
            ],
        }
    raise AttainabilityCheckError(f"target value kind is unresolved: {kind}")


def _source_error_digest(
    field,
    canonicalization_version,
    schema_version,
):
    if field["source_error_class"] is None:
        return None
    payload = {
        name: field[name]
        for name in (
            "field_id",
            "observation_method",
            "source_failure_phase",
            "source_errno_number",
            "source_errno_name",
            "source_error_class",
        )
    }
    return _semantic_id(
        canonicalization_version,
        schema_version,
        SOURCE_ERROR_DETAIL_DOMAIN,
        payload,
    )


def _base_field(
    frozen,
    context_id,
    registry_id,
):
    value = dict(frozen)
    value["observation_context_id"] = context_id
    value["target_field_registry_id"] = registry_id
    return value


def _attempted_method_upper(descriptor, all_methods):
    rows = descriptor["observation_method_role_pairs"]
    methods = [row["observation_method"] for row in rows]
    # Falling back to the full structural enum is deliberately looser than
    # the exact role predicate and therefore remains a sound upper bound.
    return _longest_canonical_text(methods or all_methods)


def _available_field_candidate(
    frozen,
    descriptor,
    context_id,
    registry_id,
    method,
    constraints,
    shapes,
    vocabularies,
    field_record_descriptor,
    canonicalization_version,
    schema_version,
    censored=None,
):
    value = _base_field(frozen, context_id, registry_id)
    value.update(
        {
            "adapter_span_status": "AVAILABLE",
            "availability": "AVAILABLE" if censored is None else "CENSORED",
            "censoring": "NONE" if censored is None else censored,
            "observation_attempt": "ATTEMPTED",
            "observation_completed_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "observation_method": method,
            "observation_started_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "source_errno_name": None,
            "source_errno_number": None,
            "source_error_class": None,
            "source_error_detail_sha256": None,
            "source_failure_phase": "NONE",
            "unavailable_reason": None,
            "value": _maximum_target_value(
                descriptor,
                constraints,
                shapes,
                vocabularies,
                censored=censored,
            ),
        }
    )
    _record_identity(
        value,
        field_record_descriptor,
        canonicalization_version,
        schema_version,
    )
    return value


def _reason_field_candidate(
    frozen,
    descriptor,
    context_id,
    registry_id,
    method,
    reason,
    reason_rule,
    attempt_row,
    error_form,
    field_record_descriptor,
    canonicalization_version,
    schema_version,
):
    del descriptor
    value = _base_field(frozen, context_id, registry_id)
    span = {
        "AVAILABLE_ONLY": "AVAILABLE",
        "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
        "UNAVAILABLE_ONLY": "UNAVAILABLE",
    }[attempt_row["adapter_span_policy"]]
    attempted = attempt_row["attempt_state"] == "ATTEMPTED"
    value.update(
        {
            "adapter_span_status": span,
            "availability": reason_rule["required_availability"],
            "censoring": "NONE",
            "observation_attempt": attempt_row["attempt_state"],
            "observation_completed_offset_nanoseconds": (
                SAFE_INTEGER_MAXIMUM if span == "AVAILABLE" else None
            ),
            "observation_method": method if attempted else "NOT_ATTEMPTED",
            "observation_started_offset_nanoseconds": (
                SAFE_INTEGER_MAXIMUM if span == "AVAILABLE" else None
            ),
            "source_failure_phase": _longest_canonical_text(
                attempt_row["permitted_failure_phases"]
            ),
            "unavailable_reason": reason,
            "value": None,
        }
    )
    if error_form == "OS":
        # The frozen policy selects OS whenever errno is present.  Retaining a
        # maximal non-OS detail pair as well only enlarges this upper domain.
        value["source_errno_number"] = SAFE_INTEGER_MAXIMUM
        value["source_errno_name"] = "E" + "A" * 63
        value["source_error_class"] = "A" * 256
    elif error_form == "NON_OS":
        value["source_errno_number"] = None
        value["source_errno_name"] = None
        value["source_error_class"] = "A" * 256
    else:
        value["source_errno_number"] = None
        value["source_errno_name"] = None
        value["source_error_class"] = None
    value["source_error_detail_sha256"] = _source_error_digest(
        value,
        canonicalization_version,
        schema_version,
    )
    _record_identity(
        value,
        field_record_descriptor,
        canonicalization_version,
        schema_version,
    )
    return value


def _maximum_field_superset(
    frozen,
    descriptor,
    context_id,
    registry_id,
    all_methods,
    status_policy,
    constraints,
    shapes,
    vocabularies,
    field_record_descriptor,
    canonicalization_version,
    schema_version,
):
    method = _attempted_method_upper(descriptor, all_methods)
    candidates = [
        _available_field_candidate(
            frozen,
            descriptor,
            context_id,
            registry_id,
            method,
            constraints,
            shapes,
            vocabularies,
            field_record_descriptor,
            canonicalization_version,
            schema_version,
        )
    ]
    if descriptor["censoring_allowed"] and descriptor["value_kind"] == "DURATION_BOUND":
        candidates.extend(
            _available_field_candidate(
                frozen,
                descriptor,
                context_id,
                registry_id,
                method,
                constraints,
                shapes,
                vocabularies,
                field_record_descriptor,
                canonicalization_version,
                schema_version,
                censored=censoring,
            )
            for censoring in ("INTERVAL", "LEFT", "RIGHT")
        )
    reason_rules = status_policy["reason_rules"]
    rules_by_reason = _index(
        reason_rules,
        "reason",
        len(reason_rules),
        "status reason",
    )
    for reason in descriptor["allowed_status_reasons"]:
        reason_rule = rules_by_reason.get(reason)
        if reason_rule is None:
            continue
        for attempt_row in reason_rule["attempt_state_error_forms"]:
            for error_form in attempt_row["permitted_error_forms"]:
                candidates.append(
                    _reason_field_candidate(
                        frozen,
                        descriptor,
                        context_id,
                        registry_id,
                        method,
                        reason,
                        reason_rule,
                        attempt_row,
                        error_form,
                        field_record_descriptor,
                        canonicalization_version,
                        schema_version,
                    )
                )
    winner = max(candidates, key=lambda value: len(_canonical_bytes(value)))
    winner_octets = len(_canonical_bytes(winner))
    _require(winner_octets <= 4096, "field superset exceeds the frozen field codec")
    return winner, winner_octets


def _clock_span_superset(span, clock_descriptor, schemas, languages):
    members = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in clock_descriptor["record_member_descriptors"]
    }
    status_language = languages[members["span_status"]["text_language_id"]]
    reason_language = languages[members["unavailable_reason"]["text_language_id"]]
    value = dict(span)
    value["span_status"] = _longest_canonical_text(status_language["ordered_literals"])
    value["started_offset_nanoseconds"] = SAFE_INTEGER_MAXIMUM
    value["completed_offset_nanoseconds"] = SAFE_INTEGER_MAXIMUM
    value["unavailable_reason"] = _longest_canonical_text(
        reason_language["ordered_literals"]
    )
    return value


def _text_schema_superset(schema, languages):
    language = languages[schema["text_language_id"]]
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        maximum = _longest_canonical_text(language["ordered_literals"])
    elif kind == "BUILTIN" and language["built_in_language_kind"] == "LOWERCASE_SHA256":
        maximum = "f" * 64
    else:
        raise AttainabilityCheckError(
            f"context text language is unresolved: {kind}:{language.get('built_in_language_kind')}"
        )
    if schema["nullable"] and len(_canonical_bytes(None)) > len(
        _canonical_bytes(maximum)
    ):
        return None
    return maximum


def analyze(repository_root):
    repository_root = pathlib.Path(repository_root)
    seed = _load_pinned(repository_root, SEED_RELATIVE_PATH, SEED_RAW_SHA256)
    inventory = _load_pinned(
        repository_root,
        INVENTORY_RELATIVE_PATH,
        INVENTORY_RAW_SHA256,
    )
    registry = _load_pinned(
        repository_root, REGISTRY_RELATIVE_PATH, REGISTRY_RAW_SHA256
    )
    canonicalization_version = seed["canonicalization_version"]
    schema_version = seed["measurement_schema_version"]

    recipe = seed["logical_plan_recipe_catalog"]
    plan = recipe["ordered_logical_count_plan_records"][CASE_POSITION - 1]
    _require(
        plan["case_position"] == CASE_POSITION
        and plan["logical_count_plan_id"] == PLAN_ID,
        "case-435 logical plan differs",
    )
    program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"]
        == plan["profile_conditioning_program_id"]
    )
    _require(
        program["profile_position"] == PROFILE_POSITION
        and program["maximum_constraint_scope_profile_id"] == PROFILE_ID
        and program["measured_type_name"] == TARGET_TYPE,
        "case-435 profile binding differs",
    )
    scope_cases = program["scope_root_operation"]["ordered_scope_case_records"]
    _require(
        len(scope_cases) == 1
        and scope_cases[0]["measured_sequence_ordinal"] == MEASURED_SEQUENCE_ORDINAL,
        "case-435 measured sequence coordinate differs",
    )
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    _require(
        p2["upper_bound_source"] == "STRUCTURAL_TEMPLATE_SUPERSET_V1"
        and p2["generic_attainability_claimed"] is False,
        "case-435 P2 claim differs",
    )
    templates = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    template = templates[program["logical_plan_template_id"]]
    root_step = template["ordered_template_steps"][template["root_step_position"] - 1]
    coordinates = root_step["recurrence_parameters"]["ordered_codec_coordinate_records"]
    _require(
        root_step["derivation_kind"] == "CODEC_INTERSECTION"
        and len(coordinates) == 1
        and coordinates[0]["codec_byte_bound_relation"] == "LT"
        and coordinates[0]["codec_octet_limit"] == 262144,
        "case-435 structural root coordinate differs",
    )
    p2_upper = coordinates[0]["derived_payload_octet_ceiling"]

    types = _index(
        registry["ordered_external_type_descriptors"],
        "type_name",
        52,
        "external type",
    )
    schemas = _index(registry["value_schema_catalog"], "value_schema_id", 236, "schema")
    languages = _index(
        registry["text_language_catalog"],
        "text_language_id",
        103,
        "text language",
    )
    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    _require(len(descriptors) == 185, "target descriptor count differs")
    constraints = _index(
        target_registry["ordered_value_constraint_definitions"],
        "value_constraint_id",
        17,
        "target constraint",
    )
    shapes = _index(
        target_registry["ordered_value_shape_definitions"],
        "value_shape_id",
        6,
        "target shape",
    )
    vocabularies = _index(
        target_registry["ordered_vocabulary_definitions"],
        "vocabulary_id",
        25,
        "target vocabulary",
    )
    registry_id = target_registry["target_field_registry_id"]
    _require(
        registry_id
        == program["ordered_fixed_authority_operations"][0]["expected_authority_id"],
        "case-435 registry authority differs",
    )

    fixtures = inventory["fixture_records"]["target_observation_v2_fixtures"]
    witness = json.loads(json.dumps(fixtures["checkpoint_exact_marker_observation"]))
    root = fixtures["maximum_selector_target_observation_root"]
    selector = inventory["checkpoint_selector_catalog"][3]["selector"]
    selected_entry = selector["ordered_entries"][MEASURED_SEQUENCE_ORDINAL - 1]
    _require(
        selected_entry["selector_position"] == MEASURED_SEQUENCE_ORDINAL,
        "case-435 selector coordinate differs",
    )

    context = witness["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_binding_status": "EXACT_MARKER",
            "checkpoint_binding_unavailable_reason": None,
            "checkpoint_marker_kind": selected_entry["checkpoint_marker_kind"],
            "checkpoint_selector_entry_id": selected_entry[
                "checkpoint_selector_entry_id"
            ],
            "checkpoint_selector_position": selected_entry["selector_position"],
            "expected_checkpoint_marker_kind": selected_entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": selected_entry[
                "occurrence_index_within_kind"
            ],
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": "ON",
            "marker_ordinal": SAFE_INTEGER_MAXIMUM,
            "observation_role": "STABLE_CHECKPOINT",
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": registry_id,
        }
    )
    clock_descriptor = types["TargetObservationClockSpanV2"]
    for member in (
        "boottime_clock_span",
        "loop_clock_span",
        "observer_clock_span",
    ):
        context[member] = _clock_span_superset(
            context[member],
            clock_descriptor,
            schemas,
            languages,
        )
    # Maximize every scalar member independently.  This intentionally admits
    # mutually inconsistent discriminator/status combinations and is therefore
    # a structural superset of every exact-marker and unavailable-marker
    # context at the frozen sequence coordinate.
    for member in types[TARGET_CONTEXT_TYPE]["record_member_descriptors"]:
        name = member["member_name"]
        if name in {
            "boottime_clock_span",
            "loop_clock_span",
            "observer_clock_span",
            "observation_context_id",
        }:
            continue
        schema = schemas[member["value_schema_id"]]
        if schema["schema_kind"] == "TEXT":
            context[name] = _text_schema_superset(schema, languages)
        elif schema["schema_kind"] == "SAFE_INTEGER":
            candidates = [schema["integer_minimum"], schema["integer_maximum"]]
            if schema["nullable"]:
                candidates.append(None)
            context[name] = max(
                candidates, key=lambda value: len(_canonical_bytes(value))
            )
        else:
            _require(
                schema["schema_kind"] == "OBJECT_REF",
                f"context schema kind is unresolved: {name}",
            )
    _record_identity(
        context,
        types[TARGET_CONTEXT_TYPE],
        canonicalization_version,
        schema_version,
    )
    context_id = context["observation_context_id"]
    witness["observation_context_id"] = context_id

    observation_method_schema = next(
        schemas[row["value_schema_id"]]
        for row in types[TARGET_FIELD_TYPE]["record_member_descriptors"]
        if row["member_name"] == "observation_method"
    )
    field_member_schemas = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in types[TARGET_FIELD_TYPE]["record_member_descriptors"]
    }
    error_class_language = languages[
        field_member_schemas["source_error_class"]["text_language_id"]
    ]
    errno_name_language = languages[
        field_member_schemas["source_errno_name"]["text_language_id"]
    ]
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", 9, "ASCII DFA")
    _require(
        error_class_language["language_kind"] == "ASCII_DFA"
        and dfas[error_class_language["ascii_dfa_id"]]["maximum_octets"] == 256,
        "source-error-class structural ceiling differs",
    )
    _require(
        errno_name_language["language_kind"] == "ASCII_DFA"
        and dfas[errno_name_language["ascii_dfa_id"]]["maximum_octets"] == 64,
        "errno-name structural ceiling differs",
    )
    error_class_dfa = dfas[error_class_language["ascii_dfa_id"]]
    errno_name_dfa = dfas[errno_name_language["ascii_dfa_id"]]
    _require_dfa_has_no_json_expanding_bytes(
        error_class_dfa,
        "source-error-class DFA",
    )
    _require_dfa_has_no_json_expanding_bytes(errno_name_dfa, "errno-name DFA")
    _require(
        _ascii_dfa_accepts(error_class_dfa, "A" * 256)
        and _ascii_dfa_accepts(errno_name_dfa, "E" + "A" * 63),
        "maximal source-error text witness differs",
    )
    _require(
        field_member_schemas["source_errno_number"]["integer_maximum"]
        == SAFE_INTEGER_MAXIMUM,
        "errno-number structural ceiling differs",
    )
    _require(
        types[TARGET_FIELD_TYPE]["codec_byte_bound_relation"] == "LE"
        and types[TARGET_FIELD_TYPE]["codec_octet_limit"] == 4096,
        "field-observation codec ceiling differs",
    )
    all_methods = languages[observation_method_schema["text_language_id"]][
        "ordered_literals"
    ]
    frozen_fields = fixtures["checkpoint_exact_marker_observation"][
        "field_observations"
    ]
    _require(len(frozen_fields) == len(descriptors), "frozen field count differs")
    maximum_fields = []
    field_rows = []
    for position, (frozen, descriptor) in enumerate(
        zip(frozen_fields, descriptors, strict=True),
        1,
    ):
        _require(
            frozen["field_id"] == descriptor["field_id"],
            "field/descriptor order differs",
        )
        maximum, octets = _maximum_field_superset(
            frozen,
            descriptor,
            context_id,
            registry_id,
            all_methods,
            target_registry["status_reason_policy_definition"],
            constraints,
            shapes,
            vocabularies,
            types[TARGET_FIELD_TYPE],
            canonicalization_version,
            schema_version,
        )
        maximum_fields.append(maximum)
        field_rows.append(
            {
                "field_position": position,
                "field_id": descriptor["field_id"],
                "superset_upper_bound_octets": octets,
            }
        )
    witness["field_observations"] = maximum_fields
    _record_identity(
        witness,
        types[TARGET_TYPE],
        canonicalization_version,
        schema_version,
    )
    constructed_raw = _canonical_bytes(witness)
    constructed_upper = len(constructed_raw)

    empty_fields = dict(witness)
    empty_fields["field_observations"] = []
    empty_raw = _canonical_bytes(empty_fields)
    field_array_value_octets = (
        2
        + sum(row["superset_upper_bound_octets"] for row in field_rows)
        + (len(field_rows) - 1)
    )
    empty_array_octets = len(_canonical_bytes([]))
    decomposed_upper = len(empty_raw) - empty_array_octets + field_array_value_octets
    _require(
        decomposed_upper == constructed_upper,
        "independent canonical-length decomposition differs",
    )
    _require(
        constructed_upper < p2_upper,
        "case-435 legal superset no longer falsifies P3 equality",
    )

    field_vector_sha = _sha256(_canonical_bytes(field_rows))
    field_sum = sum(row["superset_upper_bound_octets"] for row in field_rows)
    observation_fixed_octets = len(empty_raw) - empty_array_octets
    payload = {
        "analysis_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_attainability.v1"
        ),
        "case_position": CASE_POSITION,
        "logical_count_plan_id": PLAN_ID,
        "constraint_scope_profile_id": PROFILE_ID,
        "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
        "target_type_name": TARGET_TYPE,
        "target_field_count": len(field_rows),
        "context_structural_superset_canonical_octets": len(_canonical_bytes(context)),
        "field_superset_upper_bound_sum_octets": field_sum,
        "field_array_syntax_octets": 2 + len(field_rows) - 1,
        "observation_fixed_nonfield_octets": observation_fixed_octets,
        "p2_structural_upper_bound_octets": p2_upper,
        "derived_legal_domain_superset_upper_bound_octets": constructed_upper,
        "p3_unattainable_gap_octets": p2_upper - constructed_upper,
        "p3_equality_possible": False,
        "ordered_field_superset_bound_vector_sha256": field_vector_sha,
        "constructed_superset_canonical_sha256": _sha256(constructed_raw),
        "seed_raw_sha256": SEED_RAW_SHA256,
        "inventory_raw_sha256": INVENTORY_RAW_SHA256,
        "registry_raw_sha256": REGISTRY_RAW_SHA256,
    }
    payload["attainability_analysis_id"] = _sha256(
        _canonical_bytes({"domain": ANALYSIS_DOMAIN, "payload": payload})
    )
    return payload


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise SystemExit("usage: check...py [repository-root]")
    root = (
        pathlib.Path(argv[0]).resolve() if argv else pathlib.Path(__file__).parents[2]
    )
    try:
        result = analyze(root)
    except AttainabilityCheckError as error:
        sys.stderr.write(f"CASE435_ATTAINABILITY_REJECT: {error}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
