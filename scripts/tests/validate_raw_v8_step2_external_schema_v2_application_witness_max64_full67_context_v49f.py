#!/usr/bin/env python3
"""Independently validate the max64/full-67 pilot context authority.

The checker is standard-library-only and imports neither its producer,
production ``riskyieldmm``, the accepted application runtime, nor any maximum
producer/checker.  It validates strict/pinned bytes, every recursively reached
schema and record identity, the two relevant application descriptors and
fixed-position resolvers, and all 68 rule invocations.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
UINT128_MAXIMUM: Final = (1 << 128) - 1
MAXIMUM_ARTIFACT_OCTETS: Final = 16_777_216

REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
APPLICATION_WITNESS_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)
CONTEXT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_"
    "application_witness_max64_full67_context_v49f.json"
)

REGISTRY_RAW_OCTETS: Final = 1_469_663
REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
REGISTRY_SEMANTIC_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
LITERAL_RAW_OCTETS: Final = 484_301
LITERAL_RAW_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
LITERAL_SEMANTIC_ID: Final = (
    "5239e6ec09244d772c72c7883393da5707984408f7a7e21e1731948a82ea647e"
)
WITNESS_RAW_OCTETS: Final = 697_208
WITNESS_RAW_SHA256: Final = (
    "d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415"
)
WITNESS_SEMANTIC_ID: Final = (
    "1d859520c24a973a5a157139183ae24ef0184ce4cede5531bb4b442227e1a8ba"
)
CONTEXT_RAW_OCTETS: Final = 16_121_125
CONTEXT_RAW_SHA256: Final = (
    "afab90030ac96fa21157bdd3e696dd25798d7755be028c5cb8eaca103f73de97"
)
CONTEXT_CANONICAL_OCTETS: Final = 12_698_603
CONTEXT_CANONICAL_SHA256: Final = (
    "ab67d30d11d19670652b4c1a7aeb2d1483b97f6c4dde7bd673d9f25a3079059e"
)
SEQUENCE_CANONICAL_OCTETS: Final = 12_660_543
SEQUENCE_CANONICAL_SHA256: Final = (
    "e1a8ed64c6c94d5f80624e011f474904f872211e671c89e276aa61460fc1cd9f"
)
ROOT_CANONICAL_SHA256: Final = (
    "9df17464ca761b9f3be18f9ecced73ab6e2f6cee20de4c7ffceba8c6ac8e52f2"
)
ROOT_IDENTITY: Final = (
    "e988ccf6af1691103875d355aa64b91baabb2dc0f965999b9007bb64321a113e"
)
ORDERED_IDS_CANONICAL_SHA256: Final = (
    "17bdff1114c67db9e4fb0770890bbd68ad5e63e0845f49073cdca3213291b16e"
)
SELECTOR_IDENTITY: Final = (
    "6cc3c8c09a08675ecbddddb4131dabbdd24ea3e879bc467fe56e3089834ff2f9"
)

OBSERVATION_RESOLVER_ID: Final = (
    "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
)
SELECTOR_RESOLVER_ID: Final = (
    "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
)
MEMBERSHIP_APPLICATION_ID: Final = (
    "0737d82dae748ff1bf3b19230be2196973c7d6d0fa6c97ef834e9517e09e5f0a"
)
LIFECYCLE_APPLICATION_ID: Final = (
    "86a3acbf53805768a1a462fe28c75a7e7192487f71579ba021aa03d7992a9a42"
)
SOURCE_ERROR_DETAIL_DOMAIN: Final = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"

SELECTOR_MARKER_ORDER_BY_OPERATION: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "ACK_DEADLINE_NOT_DUE",
        "ACK_DEADLINE_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "INGRESS": (
        "RAW_PREFIX_COMMITTED",
        "PARSER_UNIT_CONVERGED",
        "INGRESS_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "LOCAL_SHUTDOWN": (
        "LOCAL_CLOSE_DISPATCH_CONVERGED",
        "TLS_CONTROL_CONVERGED",
        "TCP_HALF_CLOSE_CONVERGED",
        "SHUTDOWN_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "OUTBOUND_ARTIFACTS_PREPARED",
        "KERNEL_SEND_RESULT_CONVERGED",
        "DISPATCH_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
}


class ContextValidationError(ValueError):
    """Raised for any authority, schema, identity, or application mismatch."""


def _fail(message: str, path: tuple[str | int, ...] = ()) -> NoReturn:
    location = "" if not path else " at /" + "/".join(map(str, path))
    raise ContextValidationError(message + location)


def _require(
    condition: bool,
    message: str,
    path: tuple[str | int, ...] = (),
) -> None:
    if not condition:
        _fail(message, path)


def _reject_json_float(value: str) -> NoReturn:
    _fail(f"floating-point JSON is forbidden: {value}")


def _reject_json_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON is forbidden: {value}")


def _parse_json_integer(value: str) -> int:
    if len(value) > 17:
        _fail("JSON integer exceeds predecode digit bound")
    parsed = int(value)
    if not -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM:
        _fail("JSON integer is outside safe I-JSON")
    return parsed


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _assert_exact_json(value: Any, path: tuple[str | int, ...] = ()) -> None:
    if value is None or type(value) in {bool, str}:
        return
    if type(value) is int:
        _require(
            -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM,
            "unsafe integer",
            path,
        )
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _assert_exact_json(item, (*path, index))
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "object key is not text", (*path, key))
            _assert_exact_json(item, (*path, key))
        return
    _fail(f"non-I-JSON value: {type(value).__name__}", path)


def _canonical_bytes(value: Any) -> bytes:
    _assert_exact_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    _assert_exact_json(value)
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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )


def _read_no_follow(path: Path, expected_octets: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    chunks: list[bytes] = []
    total = 0
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), f"not a regular file: {path}")
        _require(metadata.st_size == expected_octets, f"octet count differs: {path}")
        while True:
            chunk = os.read(descriptor, min(1_048_576, expected_octets - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            _require(total <= expected_octets, f"input grew while reading: {path}")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(len(raw) == expected_octets, f"short read: {path}")
    return raw


def _load_pinned(
    path: Path,
    *,
    expected_octets: int,
    expected_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_no_follow(path, expected_octets)
    _require(_sha256(raw) == expected_sha256, f"raw SHA-256 differs: {path}")
    value = json.loads(
        raw,
        object_pairs_hook=_strict_object,
        parse_int=_parse_json_integer,
        parse_float=_reject_json_float,
        parse_constant=_reject_json_constant,
    )
    _require(type(value) is dict, f"root is not an object: {path}")
    _require(_pretty_bytes(value) == raw, f"pretty bytes differ: {path}")
    return value, raw


def _traverse(value: Any, path: list[str | int], base: tuple[str | int, ...]) -> Any:
    current = value
    walked = base
    for member in path:
        walked = (*walked, member)
        if type(member) is str:
            _require(
                type(current) is dict and member in current,
                "path is unresolved",
                walked,
            )
        else:
            _require(
                type(current) is list and 0 <= member < len(current),
                "path is unresolved",
                walked,
            )
        current = current[member]
    return current


def _exact_equal(left: Any, right: Any) -> bool:
    return type(left) is type(right) and _canonical_bytes(left) == _canonical_bytes(
        right
    )


class _RegistryValidator:
    def __init__(self, registry: dict[str, Any], literals: dict[str, Any]) -> None:
        self.registry = registry
        self.literals = literals
        self.schemas = {
            item["value_schema_id"]: item for item in registry["value_schema_catalog"]
        }
        self.types = {
            item["type_name"]: item
            for item in registry["ordered_external_type_descriptors"]
        }
        self.rules = {
            item["rule_id"]: item
            for item in registry["ordered_cross_field_rule_descriptors"]
        }
        self.applications = {
            item["application_name"]: item
            for item in registry["ordered_rule_application_descriptors"]
        }
        self.resolvers = {
            item["fixed_position_resolver_profile_id"]: item
            for item in registry["fixed_position_resolver_profile_catalog"]
        }
        self.languages = {
            item["text_language_id"]: item for item in registry["text_language_catalog"]
        }
        self.dfas = {
            item["ascii_dfa_id"]: item for item in registry["ascii_dfa_catalog"]
        }
        self.identifier_profiles = {
            item["unicode_identifier_profile_id"]: item
            for item in registry["identifier_profile_catalog"]
        }
        self.identity_check_count = 0
        self.record_validation_count = 0
        self.rule_invocation_count = 0
        _require(len(self.schemas) == 236, "value-schema catalog differs")
        _require(len(self.types) == 52, "type catalog differs")
        _require(len(self.rules) == 42, "rule catalog differs")
        _require(len(self.applications) == 8, "application catalog differs")
        _require(len(self.resolvers) == 2, "resolver catalog differs")

    def validate_type(
        self,
        type_name: str,
        value: Any,
        *,
        owner_type_name: str | None = None,
        owner_value: dict[str, Any] | None = None,
        path: tuple[str | int, ...] = (),
    ) -> None:
        descriptor = self.types.get(type_name)
        _require(descriptor is not None, f"type is unresolved: {type_name}", path)
        if descriptor["type_form"] == "TAGGED_UNION":
            self._validate_union(
                descriptor,
                value,
                owner_type_name=owner_type_name,
                owner_value=owner_value,
                path=path,
            )
            return
        _require(type(value) is dict, f"{type_name} requires an object", path)
        members = descriptor["record_member_descriptors"]
        expected_names = [member["member_name"] for member in members]
        _require(
            len(expected_names) == len(set(expected_names)),
            "record descriptor duplicates member",
            path,
        )
        _require(
            set(value) == set(expected_names), f"{type_name} member set differs", path
        )
        _require(
            [member["member_position"] for member in members]
            == list(range(1, len(members) + 1)),
            f"{type_name} member positions differ",
            path,
        )
        self.record_validation_count += 1
        for member in members:
            name = member["member_name"]
            self.validate_schema(
                member["value_schema_id"],
                value[name],
                owner_type_name=type_name,
                owner_value=value,
                path=(*path, name),
            )
        identity_field = descriptor["identity_field"]
        if identity_field is not None:
            payload = {
                name: value[name]
                for name in descriptor["identity_payload_member_order"]
            }
            expected = _semantic_id(descriptor["described_record_domain"], payload)
            _require(
                value[identity_field] == expected,
                f"{type_name} identity differs",
                (*path, identity_field),
            )
            self.identity_check_count += 1
        self._validate_codec(descriptor, value, path)
        for rule_id in descriptor["ordered_intrinsic_rule_ids"]:
            _require(
                self.evaluate_rule(rule_id, {"self": value}, path=path),
                f"intrinsic rule is false: {rule_id}",
                path,
            )

    def validate_schema(
        self,
        schema_id: str,
        value: Any,
        *,
        owner_type_name: str | None = None,
        owner_value: dict[str, Any] | None = None,
        path: tuple[str | int, ...] = (),
    ) -> None:
        schema = self.schemas.get(schema_id)
        _require(schema is not None, f"schema is unresolved: {schema_id}", path)
        if value is None:
            _require(
                schema["nullable"] is True, "non-nullable schema received null", path
            )
            return
        kind = schema["schema_kind"]
        if kind == "EXACT_BOOLEAN":
            _require(type(value) is bool, "exact Boolean requires bool", path)
            literal = schema["boolean_literal"]
            _require(literal is None or value is literal, "exact Boolean differs", path)
            return
        if kind == "SAFE_INTEGER":
            _require(type(value) is int, "safe integer requires exact int", path)
            _require(
                schema["integer_minimum"] <= value <= schema["integer_maximum"],
                "safe integer bound differs",
                path,
            )
            return
        if kind == "TEXT":
            self._validate_text(schema["text_language_id"], value, path)
            return
        if kind == "ARRAY":
            _require(type(value) is list, "array schema requires exact array", path)
            _require(
                schema["array_minimum_items"]
                <= len(value)
                <= schema["array_maximum_items"],
                "array cardinality differs",
                path,
            )
            for index, item in enumerate(value):
                self.validate_schema(
                    schema["array_item_value_schema_id"],
                    item,
                    owner_type_name=owner_type_name,
                    owner_value=owner_value,
                    path=(*path, index),
                )
            return
        _require(kind == "OBJECT_REF", f"unknown schema kind: {kind}", path)
        self.validate_type(
            schema["referenced_type_name"],
            value,
            owner_type_name=owner_type_name,
            owner_value=owner_value,
            path=path,
        )

    def _validate_union(
        self,
        descriptor: dict[str, Any],
        value: Any,
        *,
        owner_type_name: str | None,
        owner_value: dict[str, Any] | None,
        path: tuple[str | int, ...],
    ) -> None:
        _require(type(value) is dict, "tagged union requires an object", path)
        union = descriptor["tagged_union_descriptor"]
        actual: dict[str, str] = {}
        for discriminator in union["ordered_discriminator_descriptors"]:
            if discriminator["discriminator_scope"] == "SELECTED_VALUE":
                source = value
            else:
                _require(
                    owner_type_name == discriminator["discriminator_owner_type_name"]
                    and type(owner_value) is dict,
                    "tagged-union owner differs",
                    path,
                )
                source = owner_value
            member_path = discriminator["discriminator_typed_member_path"]
            selected = _traverse(source, member_path, path)
            self._validate_text(discriminator["text_language_id"], selected, path)
            actual[member_path[-1]] = selected
        matches = []
        for alternative in union["ordered_alternatives"]:
            required = {
                literal["member_name"]: literal["text_value"]
                for literal in alternative["ordered_discriminator_literals"]
            }
            if actual == required:
                matches.append(alternative)
        _require(
            len(matches) == 1, "tagged union did not select exactly one branch", path
        )
        self.validate_type(matches[0]["referenced_type_name"], value, path=path)
        self._validate_codec(descriptor, value, path)

    @staticmethod
    def _validate_codec(
        descriptor: dict[str, Any],
        value: Any,
        path: tuple[str | int, ...],
    ) -> None:
        length = len(_canonical_bytes(value))
        relation = descriptor["codec_byte_bound_relation"]
        limit = descriptor["codec_octet_limit"]
        _require(
            length < limit if relation == "LT" else length <= limit,
            "record codec bound differs",
            path,
        )

    def _validate_text(
        self,
        language_id: str,
        value: Any,
        path: tuple[str | int, ...],
    ) -> None:
        _require(type(value) is str, "text schema requires exact text", path)
        language = self.languages.get(language_id)
        _require(language is not None, "text language is unresolved", path)
        _require(
            not any(0xD800 <= ord(item) <= 0xDFFF for item in value),
            "text contains surrogate",
            path,
        )
        encoded = value.encode("utf-8")
        minimum = language["minimum_utf8_octets"]
        maximum = language["maximum_utf8_octets"]
        if minimum is not None:
            _require(
                minimum <= len(encoded) <= maximum, "text UTF-8 bound differs", path
            )
        kind = language["language_kind"]
        if kind in {"LITERAL", "ENUM"}:
            _require(
                value in language["ordered_literals"],
                "text is outside closed language",
                path,
            )
            return
        if kind == "ASCII_DFA":
            self._validate_ascii_dfa(language["ascii_dfa_id"], value, path)
            return
        if kind == "UNICODE_IDENTIFIER":
            self._validate_unicode_identifier(
                language["unicode_identifier_profile_id"], value, path
            )
            return
        _require(kind == "BUILTIN", "text language kind differs", path)
        built_in = language["built_in_language_kind"]
        if built_in == "LOWERCASE_SHA256":
            _require(
                re.fullmatch(r"[0-9a-f]{64}", value) is not None,
                "SHA-256 text differs",
                path,
            )
        elif built_in == "UINT128_DECIMAL":
            _require(
                re.fullmatch(r"0|[1-9][0-9]*", value) is not None,
                "uint128 decimal differs",
                path,
            )
            _require(int(value) <= UINT128_MAXIMUM, "uint128 exceeds bound", path)
        elif built_in == "CANONICAL_BASE64":
            try:
                ascii_value = value.encode("ascii", errors="strict")
                decoded = base64.b64decode(ascii_value, validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ContextValidationError("base64 text is malformed") from exc
            _require(
                base64.b64encode(decoded) == ascii_value,
                "base64 text is noncanonical",
                path,
            )
            _require(
                language["minimum_decoded_octets"]
                <= len(decoded)
                <= language["maximum_decoded_octets"],
                "base64 decoded bound differs",
                path,
            )
        elif built_in == "RFC3339_UTC":
            match = re.fullmatch(
                r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):"
                r"([0-9]{2}):([0-9]{2})(?:\.([0-9]{6}))?Z",
                value,
            )
            _require(
                match is not None and len(encoded) in {20, 27},
                "UTC timestamp grammar differs",
                path,
            )
            _require(
                match.group(7) != "000000",
                "zero fractional timestamp is noncanonical",
                path,
            )
            try:
                dt.datetime(
                    *(int(match.group(index)) for index in range(1, 7)),
                    int(match.group(7) or "0"),
                    tzinfo=dt.timezone.utc,
                )
            except ValueError as exc:
                raise ContextValidationError("UTC timestamp is invalid") from exc
        else:
            _require(
                built_in == "RAW_CANONICAL_JSON_STRING",
                "unknown built-in text language",
                path,
            )

    def _validate_ascii_dfa(
        self,
        dfa_id: str,
        value: str,
        path: tuple[str | int, ...],
    ) -> None:
        dfa = self.dfas.get(dfa_id)
        _require(dfa is not None, "ASCII DFA is unresolved", path)
        try:
            octets = value.encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise ContextValidationError("ASCII DFA received non-ASCII text") from exc
        _require(
            dfa["minimum_octets"] <= len(octets) <= dfa["maximum_octets"],
            "ASCII DFA bound differs",
            path,
        )
        transitions: dict[tuple[int, int], int] = {}
        for row in dfa["ordered_transition_rows"]:
            for octet in range(
                row["inclusive_byte_minimum"], row["inclusive_byte_maximum"] + 1
            ):
                key = (row["source_state"], octet)
                _require(key not in transitions, "ASCII DFA transition overlaps", path)
                transitions[key] = row["target_state"]
        state = dfa["start_state"]
        for octet in octets:
            _require((state, octet) in transitions, "ASCII DFA rejects text", path)
            state = transitions[(state, octet)]
        _require(
            state in dfa["ordered_accepting_states"],
            "ASCII DFA rejects final state",
            path,
        )

    def _validate_unicode_identifier(
        self,
        profile_id: str,
        value: str,
        path: tuple[str | int, ...],
    ) -> None:
        profile = self.identifier_profiles.get(profile_id)
        _require(profile is not None, "Unicode profile is unresolved", path)
        _require(
            unicodedata.unidata_version == profile["unicode_version"] == "15.0.0",
            "Unicode version differs",
            path,
        )
        _require(
            value != "" and len(value) <= profile["maximum_scalar_values"],
            "identifier scalar bound differs",
            path,
        )
        _require(
            unicodedata.normalize("NFC", value) == value, "identifier is not NFC", path
        )
        _require(
            len(value.encode("utf-8")) <= profile["maximum_utf8_octets"],
            "identifier UTF-8 bound differs",
            path,
        )

        def code_point(item: str) -> int:
            _require(
                re.fullmatch(r"U\+[0-9A-F]{4,6}", item) is not None,
                "code-point authority differs",
                path,
            )
            return int(item[2:], 16)

        forbidden = [
            (code_point(lower), code_point(upper))
            for lower, upper in profile["forbidden_code_point_ranges"]
        ]
        _require(
            not any(
                lower <= ord(character) <= upper
                for character in value
                for lower, upper in forbidden
            ),
            "identifier contains forbidden code point",
            path,
        )
        edge_trim = {code_point(item) for item in profile["edge_trim_code_points"]}
        _require(
            ord(value[0]) not in edge_trim and ord(value[-1]) not in edge_trim,
            "identifier edge trim differs",
            path,
        )

    def evaluate_rule(
        self,
        rule_id: str,
        bindings: dict[str, Any],
        *,
        path: tuple[str | int, ...],
    ) -> bool:
        rule = self.rules.get(rule_id)
        _require(rule is not None, f"rule is unresolved: {rule_id}", path)
        expected_bindings = [
            item["binding_name"] for item in rule["ordered_rule_input_bindings"]
        ]
        _require(
            list(bindings) == expected_bindings,
            f"rule binding order differs: {rule_id}",
            path,
        )
        nodes = rule["ordered_expression_nodes"]
        _require(
            len(nodes) == rule["maximum_expression_nodes"],
            "rule node count differs",
            path,
        )
        results: dict[int, Any] = {}
        for expected_position, node in enumerate(nodes, start=1):
            _require(
                node["expression_position"] == expected_position,
                "rule positions differ",
                path,
            )
            _require(
                all(
                    position in results
                    for position in node["ordered_operand_positions"]
                ),
                "rule edge is not prior",
                path,
            )
            operands = [
                results[position] for position in node["ordered_operand_positions"]
            ]
            results[expected_position] = self._execute_operator(
                node, operands, bindings, path
            )
        result = results[rule["root_expression_position"]]
        _require(type(result) is bool, "rule root is not Boolean", path)
        self.rule_invocation_count += 1
        return result

    def _execute_operator(
        self,
        node: dict[str, Any],
        operands: list[Any],
        bindings: dict[str, Any],
        path: tuple[str | int, ...],
    ) -> Any:
        operator = node["operator"]
        if operator == "INPUT_PATH":
            binding = node["input_binding_name"]
            _require(binding in bindings, "input binding is unresolved", path)
            return _traverse(bindings[binding], node["typed_member_path"], path)
        if operator == "LITERAL":
            value = node["literal_value"]
            _require(
                node["literal_value_schema_id"] == node["result_value_schema_id"],
                "literal schema differs",
                path,
            )
            self.validate_schema(node["literal_value_schema_id"], value, path=path)
            return value
        if operator == "IS_NULL":
            return operands[0] is None
        if operator == "NOT":
            _require(type(operands[0]) is bool, "NOT requires Boolean", path)
            return not operands[0]
        if operator in {"AND", "OR", "IMPLIES"}:
            _require(
                all(type(value) is bool for value in operands),
                f"{operator} requires Boolean",
                path,
            )
            if operator == "AND":
                return operands[0] and operands[1]
            if operator == "OR":
                return operands[0] or operands[1]
            return (not operands[0]) or operands[1]
        if operator in {"EQ", "NE"}:
            equal = _exact_equal(operands[0], operands[1])
            return equal if operator == "EQ" else not equal
        if operator == "PRESENT_LE":
            if operands[0] is None or operands[1] is None:
                return False
            _require(
                type(operands[0]) is type(operands[1])
                and type(operands[0]) in {int, str},
                "PRESENT_LE types differ",
                path,
            )
            return operands[0] <= operands[1]
        if operator == "ARRAY_LENGTH":
            _require(type(operands[0]) is list, "ARRAY_LENGTH requires array", path)
            return len(operands[0])
        if operator == "ARRAY_UNIQUE":
            _require(type(operands[0]) is list, "ARRAY_UNIQUE requires array", path)
            keys = [(type(value), _canonical_bytes(value)) for value in operands[0]]
            return len(keys) == len(set(keys))
        if operator == "ARRAY_STRICT_ASCENDING":
            _require(
                type(operands[0]) is list, "ARRAY_STRICT_ASCENDING requires array", path
            )
            return all(
                type(left) is type(right) and type(left) in {int, str} and left < right
                for left, right in zip(operands[0], operands[0][1:])
            )
        if operator == "ARRAY_PROJECT_REQUIRED_MEMBER":
            _require(type(operands[0]) is list, "array projection requires array", path)
            return [
                _traverse(value, node["typed_member_path"], (*path, index))
                for index, value in enumerate(operands[0])
            ]
        if operator == "CHECKPOINT_SELECTOR_INTRINSIC_VALID":
            return self._checkpoint_selector_intrinsic_valid(operands[0], path)
        if operator == "FIELD_OBSERVATION_INTRINSIC_VALID":
            return self._field_observation_intrinsic_valid(operands[0], path)
        if operator == "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD":
            return self._source_error_detail_recomputes(operands[0], path)
        if operator == "V2_ROOT_SEQUENCE_SELECTOR_VALID":
            return self._root_sequence_selector_valid(
                operands[0], operands[1], operands[2], path
            )
        _fail(f"operator is outside max64 context closure: {operator}", path)

    def _checkpoint_selector_intrinsic_valid(
        self,
        selector: Any,
        path: tuple[str | int, ...],
    ) -> bool:
        _require(type(selector) is dict, "selector is not an object", path)
        operation = selector["operation_kind"]
        entries = selector["ordered_entries"]
        declared_length = selector["selector_length"]
        declared_ids = selector["ordered_checkpoint_selector_entry_ids"]
        _require(
            type(entries) is list and type(declared_ids) is list,
            "selector arrays differ",
            path,
        )
        _require(
            len(entries) <= 64 and len(declared_ids) <= 64,
            "selector exceeds max64",
            path,
        )
        order = SELECTOR_MARKER_ORDER_BY_OPERATION.get(operation)
        _require(order is not None, "selector operation is unresolved", path)
        rank_by_marker = {marker: rank for rank, marker in enumerate(order)}
        last_rank = -1
        last_occurrence: dict[str, int] = {}
        coordinates: set[tuple[str, int]] = set()
        recomputed_ids: list[str] = []
        entry_descriptor = self.types["CheckpointSelectorEntryV1"]
        for ordinal, entry in enumerate(entries, start=1):
            _require(
                type(entry) is dict,
                "selector entry is not object",
                (*path, ordinal - 1),
            )
            position = entry["selector_position"]
            marker = entry["checkpoint_marker_kind"]
            occurrence = entry["occurrence_index_within_kind"]
            if position != ordinal or entry["operation_kind"] != operation:
                return False
            rank = rank_by_marker.get(marker)
            if rank is None or rank < last_rank:
                return False
            last_rank = rank
            coordinate = (marker, occurrence)
            if coordinate in coordinates or occurrence <= last_occurrence.get(
                marker, 0
            ):
                return False
            coordinates.add(coordinate)
            last_occurrence[marker] = occurrence
            recomputed_ids.append(
                _semantic_id(
                    entry_descriptor["described_record_domain"],
                    {
                        name: entry[name]
                        for name in entry_descriptor["identity_payload_member_order"]
                    },
                )
            )
        return declared_length == len(entries) and declared_ids == recomputed_ids

    @staticmethod
    def _field_observation_intrinsic_valid(
        field: Any,
        path: tuple[str | int, ...],
    ) -> bool:
        _require(type(field) is dict, "field observation is not object", path)
        availability = field["availability"]
        value = field["value"]
        method = field["observation_method"]
        attempt = field["observation_attempt"]
        span_status = field["adapter_span_status"]
        started = field["observation_started_offset_nanoseconds"]
        completed = field["observation_completed_offset_nanoseconds"]
        reason = field["unavailable_reason"]
        censoring = field["censoring"]
        errno_number = field["source_errno_number"]
        errno_name = field["source_errno_name"]
        failure_phase = field["source_failure_phase"]
        error_class = field["source_error_class"]
        error_digest = field["source_error_detail_sha256"]
        span_valid = (
            span_status == "AVAILABLE"
            and type(started) is int
            and type(completed) is int
            and started <= completed
        ) or (span_status != "AVAILABLE" and started is None and completed is None)
        if not span_valid or (errno_number is None) != (errno_name is None):
            return False
        if (error_class is None) != (error_digest is None):
            return False
        source_absent = (
            errno_number is None
            and errno_name is None
            and error_class is None
            and error_digest is None
        )
        attempted_method_valid = (
            attempt == "ATTEMPTED" and method != "NOT_ATTEMPTED"
        ) or (attempt == "NOT_ATTEMPTED" and method == "NOT_ATTEMPTED")
        if not attempted_method_valid:
            return False
        if availability in {"AVAILABLE", "CENSORED"}:
            if (
                value is None
                or attempt != "ATTEMPTED"
                or method == "NOT_ATTEMPTED"
                or span_status != "AVAILABLE"
                or reason is not None
                or failure_phase != "NONE"
                or not source_absent
            ):
                return False
            if availability == "AVAILABLE":
                return censoring == "NONE" and (
                    type(value) is not dict
                    or value.get("kind") != "DURATION_BOUND"
                    or value.get("relation") == "EXACT"
                )
            relation = {
                "LEFT": "UPPER_BOUND",
                "RIGHT": "LOWER_BOUND",
                "INTERVAL": "INTERVAL",
            }
            return (
                type(value) is dict
                and value.get("kind") == "DURATION_BOUND"
                and censoring in relation
                and value.get("relation") == relation[censoring]
            )
        if availability == "NOT_APPLICABLE":
            return (
                value is None
                and reason
                in {"NOT_APPLICABLE_TO_OPERATION", "NOT_APPLICABLE_TO_REACHED_STATE"}
                and method == "NOT_ATTEMPTED"
                and attempt == "NOT_ATTEMPTED"
                and span_status == "NOT_APPLICABLE"
                and censoring == "NONE"
                and failure_phase == "NONE"
                and source_absent
            )
        if availability == "UNAVAILABLE":
            return value is None and reason is not None and censoring == "NONE"
        return False

    @staticmethod
    def _source_error_detail_recomputes(
        field: Any,
        path: tuple[str | int, ...],
    ) -> bool:
        _require(type(field) is dict, "field observation is not object", path)
        if field["source_error_class"] is None:
            return field["source_error_detail_sha256"] is None
        payload = {
            "field_id": field["field_id"],
            "observation_method": field["observation_method"],
            "source_failure_phase": field["source_failure_phase"],
            "source_errno_number": field["source_errno_number"],
            "source_errno_name": field["source_errno_name"],
            "source_error_class": field["source_error_class"],
        }
        _require(
            len(
                _canonical_bytes(
                    {
                        "canonicalization_version": CANONICALIZATION_VERSION,
                        "domain": SOURCE_ERROR_DETAIL_DOMAIN,
                        "payload": payload,
                        "schema_version": MEASUREMENT_SCHEMA_VERSION,
                    }
                )
            )
            <= 2_048,
            "source-error preimage exceeds bound",
            path,
        )
        return field["source_error_detail_sha256"] == _semantic_id(
            SOURCE_ERROR_DETAIL_DOMAIN, payload
        )

    def _root_sequence_selector_valid(
        self,
        root: Any,
        observations: Any,
        selector: Any,
        path: tuple[str | int, ...],
    ) -> bool:
        _require(
            type(root) is dict and type(observations) is list,
            "root/sequence types differ",
            path,
        )
        _require(
            1 <= len(observations) <= 67, "observation sequence bound differs", path
        )
        if root["observation_count"] != len(observations):
            return False
        recomputed_ids: list[str] = []
        contexts: list[dict[str, Any]] = []
        observation_descriptor = self.types["TargetObservationV2"]
        for ordinal, observation in enumerate(observations):
            _require(
                type(observation) is dict, "observation is not object", (*path, ordinal)
            )
            recomputed = _semantic_id(
                observation_descriptor["described_record_domain"],
                {
                    name: observation[name]
                    for name in observation_descriptor["identity_payload_member_order"]
                },
            )
            _require(
                observation["observation_id"] == recomputed,
                "observation identity does not recompute",
                (*path, ordinal),
            )
            recomputed_ids.append(recomputed)
            contexts.append(observation["observation_context"])
        _require(
            root["ordered_observation_ids"] == recomputed_ids,
            "observation resolver sequence differs",
            path,
        )
        for context in contexts:
            if any(
                context[member] != root[member]
                for member in (
                    "candidate_id",
                    "attempt_id",
                    "operation_kind",
                    "instrumentation_mode",
                    "target_field_registry_id",
                )
            ):
                return False
        roles = [context["observation_role"] for context in contexts]
        if not (
            len(roles) >= 3
            and roles[0] == "BEFORE_OPERATION"
            and roles[-2:] == ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
            and all(role == "STABLE_CHECKPOINT" for role in roles[1:-2])
        ):
            return False
        _require(type(selector) is dict, "ON attempted root requires selector", path)
        if not self._checkpoint_selector_intrinsic_valid(selector, (*path, "selector")):
            return False
        selector_descriptor = self.types["CheckpointSelectorV1"]
        selector_id = _semantic_id(
            selector_descriptor["described_record_domain"],
            {
                name: selector[name]
                for name in selector_descriptor["identity_payload_member_order"]
            },
        )
        _require(
            selector["checkpoint_selector_id"] == selector_id,
            "selector identity does not recompute",
            path,
        )
        entries = selector["ordered_entries"]
        if (
            selector["operation_kind"] != root["operation_kind"]
            or selector_id != root["full_checkpoint_selector_id"]
            or len(contexts) != selector["selector_length"] + 3
        ):
            return False
        exact_ordinals: list[int] = []
        for context, entry in zip(contexts[1:-2], entries, strict=True):
            if (
                context["full_checkpoint_selector_id"] != selector_id
                or context["checkpoint_selector_position"] != entry["selector_position"]
                or context["checkpoint_selector_entry_id"]
                != entry["checkpoint_selector_entry_id"]
                or context["expected_checkpoint_marker_kind"]
                != entry["checkpoint_marker_kind"]
                or context["expected_occurrence_index_within_kind"]
                != entry["occurrence_index_within_kind"]
            ):
                return False
            if context["checkpoint_binding_status"] == "EXACT_MARKER":
                _require(
                    type(context["marker_ordinal"]) is int,
                    "exact marker lacks ordinal",
                    path,
                )
                exact_ordinals.append(context["marker_ordinal"])
        return all(
            left < right for left, right in zip(exact_ordinals, exact_ordinals[1:])
        )


def _validate_authority_roots(
    registry: dict[str, Any],
    literals: dict[str, Any],
    witness: dict[str, Any],
) -> None:
    _require(
        registry["external_schema_registry_id"] == REGISTRY_SEMANTIC_ID,
        "registry semantic ID differs",
    )
    _require(
        literals["rule_literal_authority_sha256"] == LITERAL_SEMANTIC_ID,
        "literal semantic ID differs",
    )
    _require(
        witness["application_witness_sha256"] == WITNESS_SEMANTIC_ID,
        "witness semantic ID differs",
    )
    literal_payload = {
        key: value
        for key, value in literals.items()
        if key != "rule_literal_authority_sha256"
    }
    _require(
        _semantic_id(
            "RiskYieldMMA2MStep2RuleLiteralAuthorityV1V4_9F_RawV8", literal_payload
        )
        == LITERAL_SEMANTIC_ID,
        "literal semantic ID does not recompute",
    )
    witness_payload = {
        key: value
        for key, value in witness.items()
        if key != "application_witness_sha256"
    }
    _require(
        _sha256(
            _canonical_bytes(
                {
                    "domain": "RiskYieldMMRawV8Step2ExternalSchemaV2ApplicationWitnessV1",
                    "payload": witness_payload,
                }
            )
        )
        == WITNESS_SEMANTIC_ID,
        "witness semantic ID does not recompute",
    )
    recipe = witness["materialization_recipes"]["ordinary_on_max64_full67"]
    _require(
        recipe["expected_observation_count"] == 67
        and recipe["expected_root_identity"] == ROOT_IDENTITY
        and recipe["expected_root_canonical_sha256"] == ROOT_CANONICAL_SHA256
        and recipe["expected_sequence_canonical_sha256"] == SEQUENCE_CANONICAL_SHA256
        and recipe["expected_ordered_observation_ids_canonical_sha256"]
        == ORDERED_IDS_CANONICAL_SHA256
        and recipe["source_root_fixture"] == "maximum_selector_root"
        and recipe["selector_fixture"] == "selector_ingress_max64",
        "witness recipe expectations differ",
    )
    for name, fixture in witness["fixture_records"].items():
        _require(
            fixture["provenance"]["frozen_value_canonical_sha256"]
            == _sha256(_canonical_bytes(fixture["value"])),
            f"fixture digest differs: {name}",
        )


def _recompute_record_identity(
    record_descriptors: dict[str, dict[str, Any]],
    value: dict[str, Any],
    type_name: str,
) -> None:
    descriptor = record_descriptors[type_name]
    identity_field = descriptor["identity_field"]
    _require(type(identity_field) is str, f"recipe record lacks identity: {type_name}")
    value[identity_field] = _semantic_id(
        descriptor["described_record_domain"],
        {name: value[name] for name in descriptor["identity_payload_member_order"]},
    )


def _reconstruct_outer_observation(
    record_descriptors: dict[str, dict[str, Any]],
    witness: dict[str, Any],
    root: dict[str, Any],
    role: str,
) -> dict[str, Any]:
    value = copy.deepcopy(
        witness["fixture_records"]["exact_marker_observation"]["value"]
    )
    context = value["observation_context"]
    replacements = {
        "attempt_id": root["attempt_id"],
        "candidate_id": root["candidate_id"],
        "instrumentation_mode": "ON",
        "observation_role": role,
        "operation_kind": root["operation_kind"],
        "target_field_registry_id": root["target_field_registry_id"],
    }
    for member_name, replacement in replacements.items():
        context[member_name] = replacement
    for member_name in (
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_marker_kind",
        "checkpoint_selector_entry_id",
        "checkpoint_selector_position",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "full_checkpoint_selector_id",
        "marker_ordinal",
    ):
        context[member_name] = None
    _recompute_record_identity(
        record_descriptors, context, "TargetObservationContextV2"
    )
    value["observation_context_id"] = context["observation_context_id"]
    for field in value["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _recompute_record_identity(
            record_descriptors,
            field,
            "TargetFieldObservationV1",
        )
    _recompute_record_identity(record_descriptors, value, "TargetObservationV2")
    return value


def _reconstruct_checkpoint_observation(
    record_descriptors: dict[str, dict[str, Any]],
    witness: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    value = copy.deepcopy(
        witness["fixture_records"]["target_boundary_placeholder_observation"]["value"]
    )
    context = value["observation_context"]
    replacements = {
        "attempt_id": root["attempt_id"],
        "candidate_id": root["candidate_id"],
        "checkpoint_binding_status": "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
        "checkpoint_binding_unavailable_reason": "TARGET_BOUNDARY_NOT_REACHED",
        "checkpoint_marker_kind": None,
        "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
        "checkpoint_selector_position": entry["selector_position"],
        "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
        "expected_occurrence_index_within_kind": entry["occurrence_index_within_kind"],
        "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
        "instrumentation_mode": "ON",
        "marker_ordinal": None,
        "observation_role": "STABLE_CHECKPOINT",
        "operation_kind": root["operation_kind"],
        "target_field_registry_id": root["target_field_registry_id"],
    }
    for member_name, replacement in replacements.items():
        context[member_name] = replacement
    _recompute_record_identity(
        record_descriptors, context, "TargetObservationContextV2"
    )
    value["observation_context_id"] = context["observation_context_id"]
    for field in value["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _recompute_record_identity(
            record_descriptors,
            field,
            "TargetFieldObservationV1",
        )
    _recompute_record_identity(record_descriptors, value, "TargetObservationV2")
    return value


def _independently_reconstruct_recipe(
    registry: dict[str, Any],
    witness: dict[str, Any],
) -> dict[str, Any]:
    recipe = witness["materialization_recipes"]["ordinary_on_max64_full67"]
    _require(
        recipe["recipe_kind"] == "CAUSAL_V2_ROOT_SEQUENCE"
        and recipe["instrumentation_mode"] == "ON"
        and recipe["startup_recovery"] is False,
        "recipe execution mode differs",
    )
    records = {
        item["type_name"]: item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_form"] == "RECORD"
    }
    fixtures = witness["fixture_records"]
    root = copy.deepcopy(fixtures[recipe["source_root_fixture"]]["value"])
    selector = copy.deepcopy(fixtures[recipe["selector_fixture"]]["value"])
    observations = [
        _reconstruct_outer_observation(records, witness, root, "BEFORE_OPERATION")
    ]
    for entry in selector["ordered_entries"]:
        observations.append(
            _reconstruct_checkpoint_observation(
                records,
                witness,
                root,
                selector,
                entry,
            )
        )
    observations.append(
        _reconstruct_outer_observation(records, witness, root, "AFTER_OPERATION")
    )
    observations.append(
        _reconstruct_outer_observation(records, witness, root, "OPERATION_AGGREGATE")
    )
    root["instrumentation_mode"] = recipe["instrumentation_mode"]
    root["full_checkpoint_selector_id"] = selector["checkpoint_selector_id"]
    root["observation_count"] = len(observations)
    root["ordered_observation_ids"] = [item["observation_id"] for item in observations]
    _recompute_record_identity(records, root, "TargetObservationRootV2")
    return {"observations": observations, "root": root, "selector": selector}


def _validate_applications_and_resolvers(
    validator: _RegistryValidator,
    context: dict[str, Any],
) -> None:
    observations = context["observations"]
    root = context["root"]
    selector = context["selector"]
    observation_resolver = validator.resolvers[OBSERVATION_RESOLVER_ID]
    selector_resolver = validator.resolvers[SELECTOR_RESOLVER_ID]
    _require(
        observation_resolver
        == {
            "fixed_position_resolver_profile_id": OBSERVATION_RESOLVER_ID,
            "maximum_items": 67,
            "minimum_items": 1,
            "ordered_source_identity_path_descriptors": [
                {
                    "null_semantics": "REJECT_NULL",
                    "path_position": 1,
                    "result_kind": "ARRAY",
                    "typed_member_path": ["ordered_observation_ids"],
                }
            ],
            "profile_name": "RAW_V8_V2_ROOT_OBSERVATION_RESOLVER_V1",
            "resolution_semantics": "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER",
            "resolved_item_type_name": "TargetObservationV2",
            "source_root_type_name": "TargetObservationRootV2",
        },
        "observation resolver descriptor differs",
    )
    _require(
        selector_resolver
        == {
            "fixed_position_resolver_profile_id": SELECTOR_RESOLVER_ID,
            "maximum_items": 1,
            "minimum_items": 0,
            "ordered_source_identity_path_descriptors": [
                {
                    "null_semantics": "NULL_TO_EMPTY_SEQUENCE",
                    "path_position": 1,
                    "result_kind": "OPTIONAL_SCALAR",
                    "typed_member_path": ["full_checkpoint_selector_id"],
                }
            ],
            "profile_name": "RAW_V8_V2_ROOT_SELECTOR_RESOLVER_V1",
            "resolution_semantics": "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER",
            "resolved_item_type_name": "CheckpointSelectorV1",
            "source_root_type_name": "TargetObservationRootV2",
        },
        "selector resolver descriptor differs",
    )
    _require(
        root["ordered_observation_ids"]
        == [item["observation_id"] for item in observations],
        "observation resolver failed",
    )
    _require(
        root["full_checkpoint_selector_id"] == selector["checkpoint_selector_id"],
        "selector resolver failed",
    )

    membership = validator.applications["APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"]
    lifecycle = validator.applications["APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1"]
    _require(
        membership["rule_application_id"] == MEMBERSHIP_APPLICATION_ID
        and membership["application_kind"] == "FOR_EACH_FIXED_POSITION_BINDING"
        and membership["maximum_rule_evaluations"] == 67
        and membership["rule_id"] == "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"
        and membership["ordered_sequence_input_bindings"][0][
            "fixed_position_resolver_profile_id"
        ]
        == OBSERVATION_RESOLVER_ID,
        "membership application descriptor differs",
    )
    _require(
        lifecycle["rule_application_id"] == LIFECYCLE_APPLICATION_ID
        and lifecycle["application_kind"] == "FIXED_SEQUENCE_AGGREGATE"
        and lifecycle["maximum_rule_evaluations"] == 1
        and lifecycle["rule_id"] == "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1"
        and [
            item["fixed_position_resolver_profile_id"]
            for item in lifecycle["ordered_sequence_input_bindings"]
        ]
        == [OBSERVATION_RESOLVER_ID, SELECTOR_RESOLVER_ID],
        "lifecycle application descriptor differs",
    )
    for ordinal, observation in enumerate(observations):
        _require(
            validator.evaluate_rule(
                membership["rule_id"],
                {
                    "root": root,
                    "observation": observation,
                    "observation_ordinal": ordinal,
                },
                path=("observations", ordinal),
            ),
            "membership rule is false",
            ("observations", ordinal),
        )
    _require(
        validator.evaluate_rule(
            lifecycle["rule_id"],
            {"root": root, "observations": observations, "selector": selector},
            path=(),
        ),
        "lifecycle rule is false",
    )


def validate(repository_root: Path, context_path: Path) -> dict[str, int | str]:
    registry, _ = _load_pinned(
        repository_root / REGISTRY_RELATIVE_PATH,
        expected_octets=REGISTRY_RAW_OCTETS,
        expected_sha256=REGISTRY_RAW_SHA256,
    )
    literals, _ = _load_pinned(
        repository_root / LITERAL_AUTHORITY_RELATIVE_PATH,
        expected_octets=LITERAL_RAW_OCTETS,
        expected_sha256=LITERAL_RAW_SHA256,
    )
    witness, _ = _load_pinned(
        repository_root / APPLICATION_WITNESS_RELATIVE_PATH,
        expected_octets=WITNESS_RAW_OCTETS,
        expected_sha256=WITNESS_RAW_SHA256,
    )
    context, raw = _load_pinned(
        context_path,
        expected_octets=CONTEXT_RAW_OCTETS,
        expected_sha256=CONTEXT_RAW_SHA256,
    )
    _validate_authority_roots(registry, literals, witness)
    independently_reconstructed = _independently_reconstruct_recipe(registry, witness)
    _require(
        _canonical_bytes(independently_reconstructed) == _canonical_bytes(context),
        "context differs from independent field-by-field recipe reconstruction",
    )
    _require(
        set(context) == {"observations", "root", "selector"},
        "context root member set differs",
    )
    _require(len(raw) < MAXIMUM_ARTIFACT_OCTETS, "context exceeds raw ceiling")
    canonical = _canonical_bytes(context)
    _require(
        len(canonical) == CONTEXT_CANONICAL_OCTETS, "context canonical count differs"
    )
    _require(
        _sha256(canonical) == CONTEXT_CANONICAL_SHA256,
        "context canonical SHA-256 differs",
    )
    observations = context["observations"]
    root = context["root"]
    selector = context["selector"]
    _require(
        type(observations) is list and len(observations) == 67,
        "observation count differs",
    )
    _require(
        type(root) is dict and type(selector) is dict, "root/selector shape differs"
    )

    validator = _RegistryValidator(registry, literals)
    for ordinal, observation in enumerate(observations):
        validator.validate_type(
            "TargetObservationV2", observation, path=("observations", ordinal)
        )
    validator.validate_type("TargetObservationRootV2", root, path=("root",))
    validator.validate_type("CheckpointSelectorV1", selector, path=("selector",))
    _require(
        validator.identity_check_count == 12_595, "identity validation count differs"
    )
    _validate_applications_and_resolvers(validator, context)
    _require(
        validator.rule_invocation_count == 12_930,
        f"rule invocation count differs: {validator.rule_invocation_count}",
    )

    sequence = _canonical_bytes(observations)
    _require(
        len(sequence) == SEQUENCE_CANONICAL_OCTETS, "sequence canonical count differs"
    )
    _require(
        _sha256(sequence) == SEQUENCE_CANONICAL_SHA256,
        "sequence canonical SHA-256 differs",
    )
    _require(
        root["target_observation_root_sha256"] == ROOT_IDENTITY, "root identity differs"
    )
    _require(
        _sha256(_canonical_bytes(root)) == ROOT_CANONICAL_SHA256,
        "root canonical SHA-256 differs",
    )
    _require(
        _sha256(_canonical_bytes(root["ordered_observation_ids"]))
        == ORDERED_IDS_CANONICAL_SHA256,
        "ordered ID digest differs",
    )
    _require(
        selector["checkpoint_selector_id"] == SELECTOR_IDENTITY,
        "selector identity differs",
    )
    roles = [item["observation_context"]["observation_role"] for item in observations]
    _require(
        roles
        == ["BEFORE_OPERATION"]
        + ["STABLE_CHECKPOINT"] * 64
        + ["AFTER_OPERATION", "OPERATION_AGGREGATE"],
        "role sequence differs",
    )
    _require(
        [
            item["observation_context"]["checkpoint_selector_position"]
            for item in observations[1:65]
        ]
        == list(range(1, 65)),
        "checkpoint positions differ",
    )
    return {
        "application_rule_invocations": 68,
        "canonical_octets": len(canonical),
        "canonical_sha256": CONTEXT_CANONICAL_SHA256,
        "identity_checks": validator.identity_check_count,
        "intrinsic_rule_invocations": 12_862,
        "raw_octets": len(raw),
        "raw_sha256": CONTEXT_RAW_SHA256,
        "record_validations": validator.record_validation_count,
        "root_identity": ROOT_IDENTITY,
        "total_rule_invocations": validator.rule_invocation_count,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--context", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        repository_root = args.repository_root.resolve(strict=True)
        context_path = (
            repository_root / CONTEXT_RELATIVE_PATH
            if args.context is None
            else args.context.resolve(strict=True)
        )
        report = validate(repository_root, context_path)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ContextValidationError, KeyError, OSError, TypeError) as exc:
        print(f"max64/full-67 context validation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
