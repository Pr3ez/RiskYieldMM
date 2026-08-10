#!/usr/bin/env python3
"""Independent S1-A4 verifier for one closed constructive V2 candidate.

The accepted predecessor slice implements the frozen exhaustive case-5 Boolean
attainer.  A4-P6-V0 adds an exact predecessor/successor authority dispatcher and
read barrier without replacing that path.  Unsupported cases still reject;
they are added only through later A4-P6 verifier packets.  The candidate is
data, never proof: this process reloads every pinned authority before reading
it and independently recomputes legality, the exact bound, attainment,
identities, and resources.
"""

import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile

SOURCE_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"

BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
BOUNDARY_OCTETS = 27_334
BOUNDARY_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)

SUCCESSOR_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SUCCESSOR_BOUNDARY_OCTETS = 4_806
SUCCESSOR_BOUNDARY_SHA256 = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)
SUCCESSOR_BOUNDARY_ID = (
    "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
)
SUCCESSOR_BOUNDARY_DOMAIN = (
    "RiskYieldMMStep2Case435ExactBoundaryDeltaV1V4_9F_RawV8"
)

SEED_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
SEED_DELTA_OCTETS = 22_976
SEED_DELTA_SHA256 = (
    "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da"
)
SUCCESSOR_SEED_ID = (
    "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
)
SEED_DELTA_DOMAIN = "RiskYieldMMStep2Case435ExactSeedDeltaV1V4_9F_RawV8"

MANIFEST_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
MANIFEST_DELTA_OCTETS = 2_192
MANIFEST_DELTA_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
MANIFEST_DELTA_DOMAIN = (
    "RiskYieldMMStep2Case435ExactManifestDeltaV1V4_9F_RawV8"
)

TARGET_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
)
TARGET_DELTA_OCTETS = 4_768
TARGET_DELTA_SHA256 = (
    "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b"
)
SUCCESSOR_TARGET_ID = (
    "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
)
TARGET_DELTA_DOMAIN = (
    "RiskYieldMMStep2Case435ExactSixCaseTargetDeltaV1V4_9F_RawV8"
)

SUCCESSOR_F2_ID = (
    "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
)
SUCCESSOR_F2_DOMAIN = (
    "RiskYieldMMStep2Case435ExactF2ResourceLimitCatalogV2V4_9F_RawV8"
)
SUCCESSOR_CASE435_PROGRAM_ID = (
    "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
)
SUCCESSOR_CASE435_PLAN_ID = (
    "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
)
CASE435_EXACTNESS_JOIN_ID = (
    "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
)
CASE435_EXACT_MAXIMUM_OCTETS = 257_887
CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS = 262_143
CASE435_POSITION = 435
SUCCESSOR_PILOT_CASE_POSITIONS = (5, 24, 54, 69, 435, 475)

PREDECESSOR_TARGET_RELATIVE_PATH = (
    "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)
PREDECESSOR_TARGET_OCTETS = 60_279
PREDECESSOR_TARGET_SHA256 = (
    "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886"
)

TYPED_RULE_RUNTIME_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
TYPED_RULE_RUNTIME_OCTETS = 249_268
TYPED_RULE_RUNTIME_SHA256 = (
    "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
)

SUCCESSOR_PROGRAM_DOMAIN = (
    "RiskYieldMMStep2Case435ExactProfileConditioningProgramV2V4_9F_RawV8"
)
SUCCESSOR_PLAN_DOMAIN = (
    "RiskYieldMMStep2Case435ExactLogicalCountPlanV4V4_9F_RawV8"
)

SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
MANIFEST_ID = "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"

CONSTRAINT_SCOPE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV2V4_9F_RawV8"
)
ROW_CONTEXT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRowContextClosureV2V4_9F_RawV8"
)
REGISTRY_DOMAIN = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
EVALUATION_SEMANTICS = (
    "FULL_GRAPH_EXACT_IJSON_INTRINSIC_DEPENDENCY_POSTORDER_THEN_"
    "LEXICAL_APPLICATION_NAME_THEN_INVOCATION_ORDINAL_V1"
)

CASE5_POSITION = 5
CASE5_TYPE = "CapacityMeasurementBoolValueV1"
MAY_BE_NONEMPTY = "MAY_BE_NONEMPTY"
U128_MAX = (1 << 128) - 1
SAFE_INTEGER_MAX = 9_007_199_254_740_991
DEFAULT_FILE_LIMIT = 16_777_216
DEFAULT_JSON_DEPTH_LIMIT = 96
DEFAULT_JSON_NODE_LIMIT = 2_097_152
DEFAULT_ARRAY_ENTRY_LIMIT = 1_048_576
DEFAULT_OBJECT_MEMBER_LIMIT = 1_048_576


class VerifierReject(Exception):
    """Stable fail-closed verifier rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = str(message).replace("\n", " ").replace("\r", " ")[:768]


def _reject(code, message):
    raise VerifierReject(code, message)


def _require(condition, code, message):
    if not condition:
        _reject(code, message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value, label="value"):
    _require(
        _is_int(value) and 0 <= value <= U128_MAX,
        "CHECKED_ARITHMETIC_REJECT",
        f"{label} is not UInt128",
    )
    return value


def _checked_add(*values):
    total = 0
    for value in values:
        value = _u128(value, "addend")
        _require(
            value <= U128_MAX - total,
            "CHECKED_ARITHMETIC_REJECT",
            "UInt128 addition overflow",
        )
        total += value
    return total


def _checked_sub(left, right):
    left = _u128(left, "minuend")
    right = _u128(right, "subtrahend")
    _require(
        right <= left,
        "CHECKED_ARITHMETIC_REJECT",
        "UInt128 subtraction underflow",
    )
    return left - right


def _checked_mul(left, right):
    left = _u128(left, "multiplicand")
    right = _u128(right, "multiplier")
    _require(
        not left or right <= U128_MAX // left,
        "CHECKED_ARITHMETIC_REJECT",
        "UInt128 multiplication overflow",
    )
    return left * right


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"canonical JSON rejected: {error}")


def _pretty_bytes(value, sort_keys=True):
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=sort_keys,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"pretty JSON rejected: {error}")


def _semantic_id(domain, payload):
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _seed_semantic_id(seed, domain, payload):
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": seed["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": seed["measurement_schema_version"],
            }
        )
    )


def _duplicate_guard(pairs):
    value = {}
    for key, child in pairs:
        _require(
            key not in value,
            "CANONICALIZATION_INVALID",
            f"duplicate JSON key: {key}",
        )
        value[key] = child
    return value


def _reject_float(value):
    _reject("CANONICALIZATION_INVALID", f"floating JSON number is forbidden: {value}")


def _reject_constant(value):
    _reject("CANONICALIZATION_INVALID", f"non-finite JSON number is forbidden: {value}")


def _validate_json_shape(value, limits):
    stack = [(value, 1)]
    nodes = 0
    arrays = 0
    members = 0
    while stack:
        child, depth = stack.pop()
        nodes += 1
        _require(
            depth <= limits["JSON_NESTING_DEPTH"],
            "INPUT_LIMIT_EXCEEDED",
            "JSON nesting depth exceeded",
        )
        _require(
            nodes <= limits["DECODED_JSON_NODE_COUNT"],
            "INPUT_LIMIT_EXCEEDED",
            "decoded JSON node count exceeded",
        )
        if isinstance(child, dict):
            members += len(child)
            _require(
                members <= limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON object-member count exceeded",
            )
            for key, nested in child.items():
                _require(
                    isinstance(key, str),
                    "CANONICALIZATION_INVALID",
                    "JSON object key is not text",
                )
                stack.append((key, depth + 1))
                stack.append((nested, depth + 1))
        elif isinstance(child, list):
            arrays += len(child)
            _require(
                arrays <= limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON array-entry count exceeded",
            )
            stack.extend((nested, depth + 1) for nested in child)
        elif isinstance(child, str):
            _require(
                all(not 0xD800 <= ord(character) <= 0xDFFF for character in child),
                "CANONICALIZATION_INVALID",
                "lone surrogate is forbidden",
            )
        elif child is None or isinstance(child, bool):
            continue
        elif _is_int(child):
            _require(
                -SAFE_INTEGER_MAX <= child <= SAFE_INTEGER_MAX,
                "CANONICALIZATION_INVALID",
                "JSON integer exceeds the safe-integer domain",
            )
        else:
            _reject("CANONICALIZATION_INVALID", "unsupported decoded JSON value")


def _strict_loads(raw, limits=None):
    if limits is None:
        limits = {
            "JSON_NESTING_DEPTH": DEFAULT_JSON_DEPTH_LIMIT,
            "DECODED_JSON_NODE_COUNT": DEFAULT_JSON_NODE_LIMIT,
            "DECODED_JSON_ARRAY_ENTRY_COUNT": DEFAULT_ARRAY_ENTRY_LIMIT,
            "DECODED_JSON_OBJECT_MEMBER_COUNT": DEFAULT_OBJECT_MEMBER_LIMIT,
        }
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(
            not text.startswith("\ufeff"),
            "CANONICALIZATION_INVALID",
            "UTF-8 BOM is forbidden",
        )
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except VerifierReject:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"strict JSON rejected: {error}")
    _validate_json_shape(value, limits)
    return value


def _closed(value, names, label):
    _require(isinstance(value, dict), "SCHEMA_INVALID", f"{label} is not an object")
    _require(
        set(value) == set(names),
        "SCHEMA_INVALID",
        f"{label} members differ",
    )
    return value


def _sha(value, label):
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        "SCHEMA_INVALID",
        f"{label} is not lowercase SHA-256",
    )
    return value


def _absolute_lexical_path(value, label, must_exist):
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    probe = path if must_exist else path.parent
    _require(probe.exists(), "INVOCATION_INVALID", f"{label} anchor is absent")
    current = pathlib.Path(path.anchor)
    for component in probe.parts[1:]:
        _require(
            component not in {"", ".", ".."},
            "INVOCATION_INVALID",
            f"{label} has a forbidden component",
        )
        current = current / component
        info = os.lstat(current)
        _require(
            not stat.S_ISLNK(info.st_mode),
            "FILESYSTEM_INVALID",
            f"{label} traverses a symlink",
        )
    return path


def _signature(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _directory_signature(path, label):
    info = os.lstat(path)
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct directory",
    )
    return _signature(info)


def _read_regular(path, limit, label):
    before = os.lstat(path)
    _require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct regular file",
    )
    _require(
        before.st_nlink == 1,
        "FILESYSTEM_INVALID",
        f"{label} is not single-link",
    )
    _require(
        0 <= before.st_size < limit,
        "INPUT_LIMIT_EXCEEDED",
        f"{label} exceeds the strict file limit",
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        _require(
            _signature(opened) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed before read",
        )
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            _require(chunk, "INPUT_RACE_DETECTED", f"{label} ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(
            os.read(descriptor, 1) == b"",
            "INPUT_RACE_DETECTED",
            f"{label} grew during read",
        )
        after = os.fstat(descriptor)
        _require(
            _signature(after) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed during read",
        )
    finally:
        os.close(descriptor)
    return b"".join(chunks), _signature(before)


def _safe_relative_path(root, relative, label):
    _require(
        isinstance(relative, str) and relative and not relative.startswith("/"),
        "AUTHORITY_INVALID",
        f"{label} relative path is invalid",
    )
    parts = pathlib.PurePosixPath(relative).parts
    _require(
        parts and all(part not in {"", ".", ".."} for part in parts),
        "AUTHORITY_INVALID",
        f"{label} relative path escapes",
    )
    path = root.joinpath(*parts)
    current = root
    for component in parts[:-1]:
        current = current / component
        _directory_signature(current, label)
    return path


def _f0_limits(seed):
    rows = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    _require(
        isinstance(rows, list) and len(rows) == 12,
        "AUTHORITY_INVALID",
        "F0 catalog differs",
    )
    limits = {}
    for position, row in enumerate(rows, 1):
        _require(
            row.get("ceiling_position") == position,
            "AUTHORITY_INVALID",
            "F0 order differs",
        )
        limits[row["resource_name"]] = _u128(row["ceiling_value"], "F0 ceiling")
    return limits


def _authority_recheck(records):
    seen = set()
    total = 0
    for record in records:
        raw, signature = _read_regular(record["path"], record["limit"], record["label"])
        _require(
            signature == record["signature"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} snapshot drifted",
        )
        _require(
            len(raw) == record["octets"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} size drifted",
        )
        _require(
            _sha256(raw) == record["sha256"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} hash drifted",
        )
        inode = signature[:2]
        _require(
            inode not in seen, "FILESYSTEM_INVALID", "authority inode alias detected"
        )
        seen.add(inode)
        total += len(raw)
    return total


def _load_predecessor_authorities(repository_root, boundary_path):
    expected_boundary = repository_root / BOUNDARY_RELATIVE_PATH
    _require(
        boundary_path == expected_boundary,
        "INVOCATION_INVALID",
        "boundary path differs",
    )
    boundary_raw, boundary_signature = _read_regular(
        boundary_path, DEFAULT_FILE_LIMIT, "constructive boundary"
    )
    _require(
        len(boundary_raw) == BOUNDARY_OCTETS,
        "AUTHORITY_INVALID",
        "boundary size differs",
    )
    _require(
        _sha256(boundary_raw) == BOUNDARY_SHA256,
        "AUTHORITY_INVALID",
        "boundary hash differs",
    )
    boundary = _strict_loads(boundary_raw)
    _require(
        boundary_raw == _pretty_bytes(boundary, sort_keys=False),
        "AUTHORITY_INVALID",
        "boundary encoding differs",
    )
    boundary_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    _require(
        boundary.get("constructive_boundary_id")
        == _semantic_id(BOUNDARY_DOMAIN, boundary_payload)
        == BOUNDARY_ID,
        "AUTHORITY_INVALID",
        "boundary identity differs",
    )

    authority = boundary["authority_contract"]
    seed_record = authority["seed_authority"]
    seed_path = _safe_relative_path(
        repository_root, seed_record["repository_relative_path"], "seed"
    )
    seed_raw, seed_signature = _read_regular(seed_path, DEFAULT_FILE_LIMIT, "seed")
    _require(
        len(seed_raw) == seed_record["raw_octets"],
        "AUTHORITY_INVALID",
        "seed size differs",
    )
    _require(
        _sha256(seed_raw) == seed_record["raw_sha256"],
        "AUTHORITY_INVALID",
        "seed hash differs",
    )
    seed = _strict_loads(seed_raw)
    _require(
        seed.get("seed_catalog_id") == seed_record["seed_catalog_id"] == SEED_ID,
        "AUTHORITY_INVALID",
        "seed ID differs",
    )
    seed_identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "SEED_CATALOG"
        ),
        None,
    )
    _require(
        seed_identity is not None,
        "AUTHORITY_INVALID",
        "seed identity authority is absent",
    )
    seed_payload = {
        name: seed[name] for name in seed_identity["ordered_payload_member_names"]
    }
    _require(
        _seed_semantic_id(seed, seed_identity["domain_literal"], seed_payload)
        == SEED_ID,
        "AUTHORITY_INVALID",
        "seed identity does not reproduce",
    )
    limits = _f0_limits(seed)
    _validate_json_shape(seed, limits)
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]

    manifest_record = authority["finalization_manifest_authority"]
    manifest_path = _safe_relative_path(
        repository_root, manifest_record["repository_relative_path"], "manifest"
    )
    manifest_raw, manifest_signature = _read_regular(
        manifest_path, file_limit, "manifest"
    )
    _require(
        len(manifest_raw) == manifest_record["raw_octets"],
        "AUTHORITY_INVALID",
        "manifest size differs",
    )
    _require(
        _sha256(manifest_raw) == manifest_record["raw_sha256"] == MANIFEST_SHA256,
        "AUTHORITY_INVALID",
        "manifest hash differs",
    )
    manifest = _strict_loads(manifest_raw, limits)
    manifest_payload = {
        name: value
        for name, value in manifest.items()
        if name != "finalization_manifest_id"
    }
    _require(
        manifest.get("finalization_manifest_id")
        == _semantic_id(MANIFEST_DOMAIN, manifest_payload)
        == MANIFEST_ID,
        "AUTHORITY_INVALID",
        "manifest identity differs",
    )

    records = [
        {
            "path": boundary_path,
            "limit": file_limit,
            "label": "constructive boundary",
            "signature": boundary_signature,
            "octets": len(boundary_raw),
            "sha256": _sha256(boundary_raw),
        },
        {
            "path": seed_path,
            "limit": file_limit,
            "label": "seed",
            "signature": seed_signature,
            "octets": len(seed_raw),
            "sha256": _sha256(seed_raw),
        },
        {
            "path": manifest_path,
            "limit": file_limit,
            "label": "manifest",
            "signature": manifest_signature,
            "octets": len(manifest_raw),
            "sha256": _sha256(manifest_raw),
        },
    ]
    authority_bytes = {}
    seen_paths = {str(boundary_path), str(seed_path), str(manifest_path)}
    seen_inodes = {boundary_signature[:2], seed_signature[:2], manifest_signature[:2]}
    total = len(boundary_raw) + len(seed_raw) + len(manifest_raw)

    verifier_role = boundary["implementation_role_contract"]["ordered_role_records"][0]
    _require(
        verifier_role["role_name"] == "INDEPENDENT_VERIFIER",
        "AUTHORITY_INVALID",
        "verifier role binding differs",
    )
    verifier_path = _safe_relative_path(
        repository_root,
        verifier_role["repository_relative_path"],
        "verifier source",
    )
    _require(
        verifier_path == pathlib.Path(__file__),
        "AUTHORITY_INVALID",
        "executed verifier path differs from the frozen role path",
    )
    verifier_raw, verifier_signature = _read_regular(
        verifier_path, file_limit, "verifier source"
    )
    _require(
        verifier_role["source_marker"].encode("utf-8") in verifier_raw,
        "AUTHORITY_INVALID",
        "verifier source marker is absent",
    )
    _require(
        str(verifier_path) not in seen_paths
        and verifier_signature[:2] not in seen_inodes,
        "FILESYSTEM_INVALID",
        "verifier source aliases an authority",
    )
    seen_paths.add(str(verifier_path))
    seen_inodes.add(verifier_signature[:2])
    total += len(verifier_raw)
    records.append(
        {
            "path": verifier_path,
            "limit": file_limit,
            "label": "verifier source",
            "signature": verifier_signature,
            "octets": len(verifier_raw),
            "sha256": _sha256(verifier_raw),
        }
    )

    authority_rows = seed["ordered_authority_binding_records"]
    _require(
        len(authority_rows)
        == seed_record["ordered_authority_binding_record_count"]
        == 17,
        "AUTHORITY_INVALID",
        "authority count differs",
    )
    for position, row in enumerate(authority_rows, 1):
        _require(
            row["authority_position"] == position,
            "AUTHORITY_INVALID",
            "authority order differs",
        )
        path = _safe_relative_path(
            repository_root, row["repository_relative_path"], f"authority {position}"
        )
        _require(
            str(path) not in seen_paths,
            "AUTHORITY_INVALID",
            "authority path alias detected",
        )
        raw, signature = _read_regular(path, file_limit, f"authority {position}")
        _require(
            len(raw) == row["raw_octet_count"],
            "AUTHORITY_INVALID",
            f"authority {position} size differs",
        )
        _require(
            _sha256(raw) == row["raw_sha256"],
            "AUTHORITY_INVALID",
            f"authority {position} hash differs",
        )
        _require(
            signature[:2] not in seen_inodes,
            "FILESYSTEM_INVALID",
            "authority inode alias detected",
        )
        seen_paths.add(str(path))
        seen_inodes.add(signature[:2])
        total += len(raw)
        authority_bytes[row["authority_role"]] = raw
        records.append(
            {
                "path": path,
                "limit": file_limit,
                "label": f"authority {position}",
                "signature": signature,
                "octets": len(raw),
                "sha256": _sha256(raw),
            }
        )

    legacy = boundary["legacy_v1_exclusion_contract"]
    for member in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        row = legacy[member]
        path = _safe_relative_path(
            repository_root, row["repository_relative_path"], member
        )
        _require(
            str(path) not in seen_paths,
            "AUTHORITY_INVALID",
            "legacy authority path alias detected",
        )
        raw, signature = _read_regular(path, file_limit, member)
        _require(
            signature[:2] not in seen_inodes,
            "FILESYSTEM_INVALID",
            "legacy authority inode alias detected",
        )
        _require(
            len(raw) == row["raw_octets"] and _sha256(raw) == row["raw_sha256"],
            "AUTHORITY_INVALID",
            f"{member} identity differs",
        )
        required_fragment = row.get(
            "required_status_fragment", row.get("required_module_fragment")
        )
        if required_fragment is not None:
            _require(
                required_fragment.encode("utf-8") in raw,
                "AUTHORITY_INVALID",
                f"{member} rejection marker is absent",
            )
        seen_paths.add(str(path))
        seen_inodes.add(signature[:2])
        total += len(raw)
        records.append(
            {
                "path": path,
                "limit": file_limit,
                "label": member,
                "signature": signature,
                "octets": len(raw),
                "sha256": _sha256(raw),
            }
        )

    _require(
        len(records) <= limits["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "input file count exceeded",
    )
    _require(
        total <= limits["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "total pinned input octets exceeded",
    )
    registry = _strict_loads(authority_bytes["STRUCTURAL_REGISTRY"], limits)
    return {
        "authority_mode": "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "boundary": boundary,
        "seed": seed,
        "manifest": manifest,
        "registry": registry,
        "authority_bytes": authority_bytes,
        "authority_records": records,
        "limits": limits,
        "effective_seed_id": SEED_ID,
        "effective_manifest_id": MANIFEST_ID,
        "effective_protocol_sha256": MANIFEST_SHA256,
        "effective_f2_id": None,
    }


def _authority_descriptor(relative_path, raw, identity_name=None, identity=None):
    value = {
        "repository_relative_path": relative_path,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }
    if identity_name is not None:
        value[identity_name] = identity
    return value


def _load_additional_authority(
    repository_root,
    authorities,
    relative_path,
    expected_octets,
    expected_sha256,
    label,
):
    path = _safe_relative_path(repository_root, relative_path, label)
    records = authorities["authority_records"]
    _require(
        all(record["path"] != path for record in records),
        "AUTHORITY_INVALID",
        f"{label} path aliases an earlier authority",
    )
    raw, signature = _read_regular(
        path,
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
        label,
    )
    _require(
        len(raw) == expected_octets and _sha256(raw) == expected_sha256,
        "AUTHORITY_INVALID",
        f"{label} identity differs",
    )
    _require(
        all(record["signature"][:2] != signature[:2] for record in records),
        "FILESYSTEM_INVALID",
        f"{label} inode aliases an earlier authority",
    )
    _require(
        len(records) + 1 <= authorities["limits"]["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "input file count exceeded while loading successor authorities",
    )
    _require(
        sum(record["octets"] for record in records) + len(raw)
        <= authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "total pinned input octets exceeded while loading successor authorities",
    )
    records.append(
        {
            "path": path,
            "limit": authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
            "label": label,
            "signature": signature,
            "octets": len(raw),
            "sha256": _sha256(raw),
        }
    )
    return path, raw


def _load_additional_json_authority(
    repository_root,
    authorities,
    relative_path,
    expected_octets,
    expected_sha256,
    label,
):
    path, raw = _load_additional_authority(
        repository_root,
        authorities,
        relative_path,
        expected_octets,
        expected_sha256,
        label,
    )
    value = _strict_loads(raw, authorities["limits"])
    _require(
        isinstance(value, dict) and raw == _pretty_bytes(value, sort_keys=False),
        "AUTHORITY_INVALID",
        f"{label} encoding differs",
    )
    return path, raw, value


def _payload_identity(value, identity_name, domain, expected_identity, label):
    payload = {name: child for name, child in value.items() if name != identity_name}
    _require(
        value.get(identity_name)
        == _semantic_id(domain, payload)
        == expected_identity,
        "AUTHORITY_INVALID",
        f"{label} semantic identity differs",
    )


def _one_by_position(rows, position, label):
    matches = [row for row in rows if row.get("case_position") == position]
    _require(
        len(matches) == 1,
        "AUTHORITY_INVALID",
        f"{label} resolution is missing or ambiguous",
    )
    return matches[0]


def _validate_successor_seed_delta(
    repository_root, authorities, seed_delta_raw, seed_delta
):
    _payload_identity(
        seed_delta,
        "successor_seed_catalog_id",
        SEED_DELTA_DOMAIN,
        SUCCESSOR_SEED_ID,
        "successor seed delta",
    )
    seed = authorities["seed"]
    predecessor_seed_raw = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "seed"
    )
    _require(
        seed_delta.get("predecessor_seed_authority")
        == {
            "raw_octets": predecessor_seed_raw["octets"],
            "raw_sha256": predecessor_seed_raw["sha256"],
            "repository_relative_path": SEED_RELATIVE_PATH,
            "seed_catalog_id": SEED_ID,
        },
        "AUTHORITY_INVALID",
        "successor seed predecessor binding differs",
    )
    theorem = seed_delta.get("exactness_theorem_authority")
    _require(
        isinstance(theorem, dict)
        and theorem.get("case_position") == CASE435_POSITION
        and theorem.get("profile_position") == 369
        and theorem.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and theorem.get("proved_legal_upper_bound_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("independently_measured_legal_attainer_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("exact_maximum_octets") == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("exact_cell_kind") == "EXACT_ATTAINED_MAXIMUM",
        "AUTHORITY_INVALID",
        "case435 exactness theorem binding differs",
    )
    source_rows = theorem.get("ordered_source_authority_records")
    _require(
        isinstance(source_rows, list) and len(source_rows) == 8,
        "AUTHORITY_INVALID",
        "case435 exactness source set differs",
    )
    for position, row in enumerate(source_rows, 1):
        _require(
            isinstance(row, dict)
            and row.get("source_position") == position
            and isinstance(row.get("source_role"), str)
            and isinstance(row.get("repository_relative_path"), str)
            and _is_int(row.get("raw_octets"))
            and isinstance(row.get("raw_sha256"), str),
            "AUTHORITY_INVALID",
            "case435 exactness source record differs",
        )
        _load_additional_authority(
            repository_root,
            authorities,
            row["repository_relative_path"],
            row["raw_octets"],
            row["raw_sha256"],
            f"case435 exactness source {position}",
        )

    resolution = seed_delta.get("resolution_contract")
    _require(
        isinstance(resolution, dict)
        and resolution.get("ordered_override_case_positions") == [CASE435_POSITION]
        and resolution.get("override_cardinality") == 1
        and resolution.get("base_fallback_case_count") == 474
        and resolution.get("shadowed_predecessor_case435_use_policy") == "REJECT"
        and resolution.get("structural_superset_as_exact_maximum_policy") == "REJECT"
        and resolution.get("unknown_duplicate_or_extra_override_policy") == "REJECT",
        "AUTHORITY_INVALID",
        "successor seed resolution contract differs",
    )

    program = seed_delta.get("successor_case435_profile_conditioning_program")
    plan = seed_delta.get("successor_case435_logical_count_plan")
    binding = seed_delta.get("successor_case435_case_plan_binding")
    _require(
        isinstance(program, dict) and isinstance(plan, dict) and isinstance(binding, dict),
        "AUTHORITY_INVALID",
        "case435 successor records are absent",
    )
    program_payload = {
        name: child
        for name, child in program.items()
        if name != "profile_conditioning_program_id"
    }
    plan_payload = {
        name: child for name, child in plan.items() if name != "logical_count_plan_id"
    }
    _require(
        program.get("profile_conditioning_program_id")
        == _semantic_id(SUCCESSOR_PROGRAM_DOMAIN, program_payload)
        == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get("logical_count_plan_id")
        == _semantic_id(SUCCESSOR_PLAN_DOMAIN, plan_payload)
        == SUCCESSOR_CASE435_PLAN_ID,
        "AUTHORITY_INVALID",
        "case435 successor program or plan identity differs",
    )
    _require(
        plan.get("case_position") == CASE435_POSITION
        and plan.get("profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get("upper_bound_mode") == "EXACT_LEGAL_DOMAIN"
        and plan.get("ordered_safe_relaxation_rule_ids") == []
        and binding
        == {
            "case_position": CASE435_POSITION,
            "logical_count_plan_id": SUCCESSOR_CASE435_PLAN_ID,
            "logical_count_plan_position": CASE435_POSITION,
        },
        "AUTHORITY_INVALID",
        "case435 successor plan binding differs",
    )
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    instructions = p2.get("ordered_instruction_records")
    _require(
        isinstance(instructions, list)
        and [row.get("opcode") for row in instructions]
        == [
            "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
            "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
        ]
        and instructions[0]["parameters"]["exact_maximum_octets"]
        == CASE435_EXACT_MAXIMUM_OCTETS
        and instructions[0]["parameters"]["exactness_join_certificate_id"]
        == CASE435_EXACTNESS_JOIN_ID
        and instructions[1]["parameters"]["predecessor_structural_upper_bound_octets"]
        == CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS
        and CASE435_EXACT_MAXIMUM_OCTETS
        <= CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS,
        "AUTHORITY_INVALID",
        "case435 exact-cell P2 program differs",
    )

    recipe = seed["logical_plan_recipe_catalog"]
    unaffected_programs = [
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["case_position"] != CASE435_POSITION
    ]
    unaffected_plans = [
        row
        for row in recipe["ordered_logical_count_plan_records"]
        if row["case_position"] != CASE435_POSITION
    ]
    unaffected_bindings = [
        row
        for row in recipe["ordered_case_plan_bindings"]
        if row["case_position"] != CASE435_POSITION
    ]
    inherited = {
        name: child
        for name, child in recipe.items()
        if name
        not in {
            "logical_plan_recipe_catalog_id",
            "ordered_profile_conditioning_program_records",
            "ordered_logical_count_plan_records",
            "ordered_case_plan_bindings",
        }
    }
    no_drift = seed_delta.get("no_unrelated_drift_proof")
    _require(
        no_drift
        == {
            "authorized_override_json_pointers": [
                "/logical_plan_recipe_catalog/ordered_profile_conditioning_program_records/368",
                "/logical_plan_recipe_catalog/ordered_logical_count_plan_records/434",
                "/logical_plan_recipe_catalog/ordered_case_plan_bindings/434",
            ],
            "case_universe_record_count": 475,
            "case_universe_records_sha256": _sha256(
                _canonical_bytes(
                    seed["case_universe_catalog"]["ordered_case_bindings"]
                )
            ),
            "inherited_recipe_member_names": sorted(inherited),
            "inherited_recipe_members_sha256": _sha256(_canonical_bytes(inherited)),
            "unaffected_case_plan_binding_count": 474,
            "unaffected_case_plan_binding_records_sha256": _sha256(
                _canonical_bytes(unaffected_bindings)
            ),
            "unaffected_case_plan_count": 474,
            "unaffected_case_plan_records_sha256": _sha256(
                _canonical_bytes(unaffected_plans)
            ),
            "unaffected_profile_program_count": 407,
            "unaffected_profile_program_records_sha256": _sha256(
                _canonical_bytes(unaffected_programs)
            ),
        },
        "AUTHORITY_INVALID",
        "successor seed no-unrelated-drift proof differs",
    )
    return seed_delta_raw


def _validate_successor_manifest_delta(
    authorities, seed_delta_raw, manifest_delta_raw, manifest_delta
):
    _payload_identity(
        manifest_delta,
        "successor_manifest_id",
        MANIFEST_DELTA_DOMAIN,
        SUCCESSOR_MANIFEST_ID,
        "successor manifest delta",
    )
    manifest_record = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "manifest"
    )
    _require(
        manifest_delta.get("predecessor_finalization_manifest_authority")
        == {
            "finalization_manifest_id": MANIFEST_ID,
            "raw_octets": manifest_record["octets"],
            "raw_sha256": manifest_record["sha256"],
            "repository_relative_path": MANIFEST_RELATIVE_PATH,
        }
        and manifest_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and manifest_delta.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and manifest_delta.get("case435_exact_maximum_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS,
        "AUTHORITY_INVALID",
        "successor manifest authority binding differs",
    )
    f2 = manifest_delta.get("f2_limit_authority")
    f2_digest = _sha256(
        _canonical_bytes(authorities["manifest"]["ordered_f2_limit_records"])
    )
    _require(
        isinstance(f2, dict)
        and f2.get("limit_record_count") == 18
        and f2.get("ordered_f2_limit_records_sha256") == f2_digest
        and f2.get("limits_are_byte_exact_predecessor_ceilings") is True
        and f2.get("limits_may_not_be_raised_or_repaired_by_case435") is True
        and f2.get("case435_successor_resource_requalification")
        == "REQUIRED_DURING_A4_P6_V_BEFORE_CASE_ACCEPTANCE"
        and manifest_delta.get("manifest_status")
        == "CASE435_EXACT_DELTA_BOUND_VERIFIER_RESOURCE_REQUALIFICATION_REQUIRED",
        "AUTHORITY_INVALID",
        "successor manifest F2 contract differs",
    )
    return manifest_delta_raw


def _validate_successor_boundary_delta(
    authorities,
    boundary_delta_path,
    seed_delta_raw,
    manifest_delta_raw,
    boundary_delta_raw,
    boundary_delta,
):
    _require(
        boundary_delta_path
        == authorities["repository_root"] / SUCCESSOR_BOUNDARY_RELATIVE_PATH,
        "INVOCATION_INVALID",
        "successor boundary path differs",
    )
    _payload_identity(
        boundary_delta,
        "successor_constructive_boundary_id",
        SUCCESSOR_BOUNDARY_DOMAIN,
        SUCCESSOR_BOUNDARY_ID,
        "successor boundary delta",
    )
    boundary_record = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "constructive boundary"
    )
    _require(
        boundary_delta.get("predecessor_constructive_boundary_authority")
        == {
            "constructive_boundary_id": BOUNDARY_ID,
            "raw_octets": boundary_record["octets"],
            "raw_sha256": boundary_record["sha256"],
            "repository_relative_path": BOUNDARY_RELATIVE_PATH,
        }
        and boundary_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and boundary_delta.get("successor_manifest_delta_authority")
        == _authority_descriptor(
            MANIFEST_DELTA_RELATIVE_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            SUCCESSOR_MANIFEST_ID,
        ),
        "AUTHORITY_INVALID",
        "successor boundary authority binding differs",
    )
    resolution = boundary_delta.get("effective_authority_resolution")
    expected_load_order = [
        "PREDECESSOR_BOUNDARY",
        "PREDECESSOR_SEED_AND_MANIFEST",
        "SUCCESSOR_SEED_DELTA",
        "SUCCESSOR_MANIFEST_DELTA",
    ]
    _require(
        isinstance(resolution, dict)
        and resolution.get("load_order") == expected_load_order
        and resolution.get("case435_resolution") == "SUCCESSOR_EXACT_RECORDS_ONLY"
        and resolution.get("all_other_case_resolution")
        == "BYTE_EXACT_PREDECESSOR_RECORDS_ONLY"
        and resolution.get("ambiguous_missing_duplicate_or_extra_resolution_policy")
        == "REJECT"
        and resolution.get("candidate_read_barrier")
        == "ALL_PREDECESSOR_AND_DELTA_AUTHORITIES_ACCEPTED_BEFORE_OPENING_CANDIDATE_BYTES",
        "AUTHORITY_INVALID",
        "successor authority resolution differs",
    )
    overrides = resolution.get("downstream_field_binding_overrides")
    _require(
        isinstance(overrides, dict)
        and overrides.get("seed_catalog_id") == "SUCCESSOR_SEED_CATALOG_ID"
        and overrides.get("finalization_manifest_id") == "SUCCESSOR_MANIFEST_ID"
        and overrides.get("maximum_protocol_sha256")
        == "SUCCESSOR_MANIFEST_DELTA_RAW_SHA256"
        and overrides.get("derivation_plan_id_for_case435")
        == "SUCCESSOR_CASE435_LOGICAL_COUNT_PLAN_ID"
        and overrides.get("upper_bound_mode_for_case435") == "EXACT_LEGAL_DOMAIN"
        and overrides.get("ordered_safe_relaxation_rule_ids_for_case435") == []
        and overrides.get("resource_limit_catalog_id")
        == "SUCCESSOR_F2_RESOURCE_LIMIT_CATALOG_ID",
        "AUTHORITY_INVALID",
        "successor downstream binding overrides differ",
    )
    f2 = boundary_delta.get("successor_f2_resource_limit_catalog")
    f2_payload = {
        name: child
        for name, child in f2.items()
        if name
        not in {
            "f2_resource_limit_catalog_id",
            "limit_records_source",
            "resource_requalification_rule",
        }
    }
    _require(
        isinstance(f2, dict)
        and f2.get("f2_resource_limit_catalog_id")
        == _semantic_id(SUCCESSOR_F2_DOMAIN, f2_payload)
        == SUCCESSOR_F2_ID
        and f2.get("successor_seed_catalog_id") == SUCCESSOR_SEED_ID
        and f2.get("successor_manifest_id") == SUCCESSOR_MANIFEST_ID
        and f2.get("predecessor_ordered_f2_limit_records_sha256")
        == _sha256(
            _canonical_bytes(authorities["manifest"]["ordered_f2_limit_records"])
        ),
        "AUTHORITY_INVALID",
        "successor F2 identity differs",
    )
    predecessor_pilot = _one_by_position(
        authorities["boundary"]["pilot_contract"]["ordered_pilot_case_records"],
        CASE435_POSITION,
        "predecessor case435 pilot",
    )
    expected_pilot = dict(predecessor_pilot)
    expected_pilot["logical_count_plan_id"] = SUCCESSOR_CASE435_PLAN_ID
    expected_pilot["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    _require(
        boundary_delta.get("case435_pilot_record_override") == expected_pilot,
        "AUTHORITY_INVALID",
        "successor case435 pilot override differs",
    )
    inherited = {
        name: child
        for name, child in authorities["boundary"].items()
        if name
        not in {
            "constructive_boundary_id",
            "authority_contract",
            "pilot_contract",
            "resource_enforcement_contract",
        }
    }
    preserved = boundary_delta.get("preserved_boundary_contract")
    _require(
        isinstance(preserved, dict)
        and preserved.get("inherited_member_names") == sorted(inherited)
        and preserved.get("inherited_members_sha256")
        == _sha256(_canonical_bytes(inherited))
        and preserved.get("candidate_and_result_schemas_unchanged") is True
        and preserved.get("filesystem_and_independence_contracts_unchanged") is True
        and preserved.get("implementation_role_records_unchanged") is True
        and boundary_delta.get("verifier_expansion_state")
        == "RELEASED_FOR_A4_P6_V_IMPLEMENTATION"
        and boundary_delta.get("producer_expansion_state")
        == "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "AUTHORITY_INVALID",
        "successor preserved-boundary contract differs",
    )
    return boundary_delta_raw


def _validate_successor_target_delta(
    authorities,
    target_source_raw,
    seed_delta_raw,
    manifest_delta_raw,
    boundary_delta_raw,
    target_delta,
):
    _payload_identity(
        target_delta,
        "successor_six_case_target_id",
        TARGET_DELTA_DOMAIN,
        SUCCESSOR_TARGET_ID,
        "successor six-case target delta",
    )
    _require(
        target_delta.get("predecessor_six_case_target_authority")
        == _authority_descriptor(PREDECESSOR_TARGET_RELATIVE_PATH, target_source_raw)
        and target_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and target_delta.get("successor_manifest_delta_authority")
        == _authority_descriptor(
            MANIFEST_DELTA_RELATIVE_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            SUCCESSOR_MANIFEST_ID,
        )
        and target_delta.get("successor_boundary_delta_authority")
        == _authority_descriptor(
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            boundary_delta_raw,
            "successor_constructive_boundary_id",
            SUCCESSOR_BOUNDARY_ID,
        ),
        "AUTHORITY_INVALID",
        "successor target authority binding differs",
    )
    expected_pilots = [
        dict(row)
        for row in authorities["boundary"]["pilot_contract"][
            "ordered_pilot_case_records"
        ]
    ]
    expected_case435 = _one_by_position(
        expected_pilots, CASE435_POSITION, "successor target case435 pilot"
    )
    expected_case435["logical_count_plan_id"] = SUCCESSOR_CASE435_PLAN_ID
    expected_case435["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    _require(
        target_delta.get("ordered_pilot_case_records") == expected_pilots
        and tuple(
            row["case_position"]
            for row in target_delta["ordered_pilot_case_records"]
        )
        == SUCCESSOR_PILOT_CASE_POSITIONS,
        "AUTHORITY_INVALID",
        "successor target pilot set differs",
    )
    expectation = target_delta.get("case435_exact_expectation")
    qualification = target_delta.get("qualification_contract")
    _require(
        isinstance(expectation, dict)
        and expectation.get("case_position") == CASE435_POSITION
        and expectation.get("successor_profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and expectation.get("successor_logical_count_plan_id")
        == SUCCESSOR_CASE435_PLAN_ID
        and expectation.get("upper_bound_mode") == "EXACT_LEGAL_DOMAIN"
        and expectation.get("ordered_safe_relaxation_rule_ids") == []
        and expectation.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and expectation.get("certified_upper_bound_octets")
        == expectation.get("required_legal_attainer_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and isinstance(qualification, dict)
        and qualification.get("verifier_expansion_state") == "NEXT"
        and qualification.get("producer_expansion_state") == "WAITING"
        and qualification.get("runner_state") == "WAITING"
        and qualification.get("next_subgate") == "A4-P6-V"
        and qualification.get("no_case_result_or_profitability_claimed") is True,
        "AUTHORITY_INVALID",
        "successor target acceptance contract differs",
    )


def _load_successor_authorities(repository_root, boundary_delta_path, authorities):
    authorities["repository_root"] = repository_root
    _, seed_delta_raw, seed_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        SEED_DELTA_RELATIVE_PATH,
        SEED_DELTA_OCTETS,
        SEED_DELTA_SHA256,
        "successor seed delta",
    )
    _validate_successor_seed_delta(
        repository_root, authorities, seed_delta_raw, seed_delta
    )

    _, manifest_delta_raw, manifest_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        MANIFEST_DELTA_RELATIVE_PATH,
        MANIFEST_DELTA_OCTETS,
        MANIFEST_DELTA_SHA256,
        "successor manifest delta",
    )
    _validate_successor_manifest_delta(
        authorities, seed_delta_raw, manifest_delta_raw, manifest_delta
    )

    loaded_boundary_path, boundary_delta_raw, boundary_delta = (
        _load_additional_json_authority(
            repository_root,
            authorities,
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            SUCCESSOR_BOUNDARY_OCTETS,
            SUCCESSOR_BOUNDARY_SHA256,
            "successor boundary delta",
        )
    )
    _require(
        loaded_boundary_path == boundary_delta_path,
        "INVOCATION_INVALID",
        "successor boundary invocation does not select the loaded authority",
    )
    _validate_successor_boundary_delta(
        authorities,
        boundary_delta_path,
        seed_delta_raw,
        manifest_delta_raw,
        boundary_delta_raw,
        boundary_delta,
    )

    _, target_source_raw = _load_additional_authority(
        repository_root,
        authorities,
        PREDECESSOR_TARGET_RELATIVE_PATH,
        PREDECESSOR_TARGET_OCTETS,
        PREDECESSOR_TARGET_SHA256,
        "predecessor six-case target source",
    )
    _, target_delta_raw, target_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        TARGET_DELTA_RELATIVE_PATH,
        TARGET_DELTA_OCTETS,
        TARGET_DELTA_SHA256,
        "successor six-case target delta",
    )
    _validate_successor_target_delta(
        authorities,
        target_source_raw,
        seed_delta_raw,
        manifest_delta_raw,
        boundary_delta_raw,
        target_delta,
    )
    _load_additional_authority(
        repository_root,
        authorities,
        TYPED_RULE_RUNTIME_RELATIVE_PATH,
        TYPED_RULE_RUNTIME_OCTETS,
        TYPED_RULE_RUNTIME_SHA256,
        "accepted typed rule runtime",
    )

    authorities.update(
        {
            "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            "seed_delta": seed_delta,
            "manifest_delta": manifest_delta,
            "successor_boundary": boundary_delta,
            "target_delta": target_delta,
            "effective_seed_id": SUCCESSOR_SEED_ID,
            "effective_manifest_id": SUCCESSOR_MANIFEST_ID,
            "effective_protocol_sha256": MANIFEST_DELTA_SHA256,
            "effective_f2_id": SUCCESSOR_F2_ID,
            "effective_case435_program_id": SUCCESSOR_CASE435_PROGRAM_ID,
            "effective_case435_plan_id": SUCCESSOR_CASE435_PLAN_ID,
        }
    )
    return authorities


def _load_authorities(repository_root, boundary_path):
    predecessor_path = repository_root / BOUNDARY_RELATIVE_PATH
    successor_path = repository_root / SUCCESSOR_BOUNDARY_RELATIVE_PATH
    if boundary_path == predecessor_path:
        authorities = _load_predecessor_authorities(
            repository_root, predecessor_path
        )
        authorities["repository_root"] = repository_root
        return authorities
    _require(
        boundary_path == successor_path,
        "INVOCATION_INVALID",
        "boundary path does not select a frozen predecessor or successor authority",
    )
    authorities = _load_predecessor_authorities(repository_root, predecessor_path)
    return _load_successor_authorities(
        repository_root, successor_path, authorities
    )


def _contains_forbidden_member(value, forbidden):
    if isinstance(value, dict):
        return any(
            name in forbidden or _contains_forbidden_member(child, forbidden)
            for name, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_member(child, forbidden) for child in value)
    return False


def _candidate_snapshot(candidate_root, authorities):
    root_signature = _directory_signature(candidate_root, "candidate root")
    names = sorted(entry.name for entry in os.scandir(candidate_root))
    expected = sorted(
        authorities["boundary"]["candidate_bundle_contract"]["bundle_root_member_paths"]
    )
    _require(names == expected, "FILESYSTEM_INVALID", "candidate root members differ")
    context_root = candidate_root / "context_objects"
    context_signature = _directory_signature(context_root, "candidate context root")
    _require(
        not any(os.scandir(context_root)),
        "FILESYSTEM_INVALID",
        "case 5 context root is not empty",
    )
    candidate_path = candidate_root / "candidate.json"
    raw, file_signature = _read_regular(
        candidate_path,
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
        "candidate envelope",
    )
    return {
        "root_signature": root_signature,
        "context_signature": context_signature,
        "file_signature": file_signature,
        "raw": raw,
    }


def _candidate_recheck(candidate_root, snapshot, authorities):
    current = _candidate_snapshot(candidate_root, authorities)
    _require(
        current == snapshot,
        "INPUT_RACE_DETECTED",
        "candidate bundle changed during verification",
    )


def _resolve_case_and_plan(authorities, case_position):
    seed = authorities["seed"]
    case_rows = seed["case_universe_catalog"]["ordered_case_bindings"]
    _require(
        _is_int(case_position) and 1 <= case_position <= len(case_rows),
        "SCHEMA_INVALID",
        "candidate case position is outside the frozen universe",
    )
    case = case_rows[case_position - 1]
    _require(
        case["case_position"] == case_position,
        "AUTHORITY_INVALID",
        "case-universe order differs",
    )
    if (
        authorities["authority_mode"] == "SUCCESSOR_CASE435_EXACT_DELTA_V1"
        and case_position == CASE435_POSITION
    ):
        plan = authorities["seed_delta"]["successor_case435_logical_count_plan"]
        binding = authorities["seed_delta"][
            "successor_case435_case_plan_binding"
        ]
    else:
        plan = seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ][case_position - 1]
        binding = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"][
            case_position - 1
        ]
    _require(
        plan["case_position"] == binding["case_position"] == case_position
        and binding["logical_count_plan_id"] == plan["logical_count_plan_id"],
        "AUTHORITY_INVALID",
        "effective case-plan resolution differs",
    )
    return case, plan


def _validate_candidate(candidate, raw, authorities):
    boundary = authorities["boundary"]
    contract = boundary["candidate_bundle_contract"]
    schema = contract["candidate_envelope_schema"]
    _closed(candidate, schema["ordered_member_names"], "candidate envelope")
    _require(
        raw == _pretty_bytes(candidate),
        "CANONICALIZATION_INVALID",
        "candidate envelope encoding differs",
    )
    _require(
        candidate["candidate_version"] == schema["version_literal"],
        "SCHEMA_INVALID",
        "candidate version differs",
    )
    _require(
        candidate["canonicalization_version"] == boundary["canonicalization_version"],
        "AUTHORITY_INVALID",
        "candidate canonicalization differs",
    )
    _require(
        candidate["measurement_schema_version"]
        == boundary["measurement_schema_version"],
        "AUTHORITY_INVALID",
        "candidate measurement schema differs",
    )
    _require(
        candidate["protocol_version"] == boundary["protocol_version"],
        "AUTHORITY_INVALID",
        "candidate protocol differs",
    )
    _require(
        candidate["seed_catalog_id"] == authorities["effective_seed_id"],
        "AUTHORITY_INVALID",
        "candidate seed differs",
    )
    _require(
        candidate["finalization_manifest_id"]
        == authorities["effective_manifest_id"],
        "AUTHORITY_INVALID",
        "candidate manifest differs",
    )
    case, plan = _resolve_case_and_plan(authorities, candidate["case_position"])
    _require(
        candidate["case_position"] == CASE5_POSITION,
        "UNSUPPORTED_CASE",
        "A4-P6-V0 accepts case 5; cases 24, 54, 69, 435, and 475 remain fail-closed",
    )
    _require(
        case["case_position"] == plan["case_position"] == CASE5_POSITION,
        "AUTHORITY_INVALID",
        "case 5 order differs",
    )
    _require(
        candidate["case_kind"] == case["case_kind"] == "MAXIMUM_PUBLICATION_ROW",
        "SCHEMA_INVALID",
        "candidate case kind differs",
    )
    _require(
        candidate["case_binding"] == case["case_binding"] == plan["case_binding"],
        "SCHEMA_INVALID",
        "candidate case binding differs",
    )
    _require(
        candidate["logical_count_plan_id"] == plan["logical_count_plan_id"],
        "SCHEMA_INVALID",
        "candidate logical plan differs",
    )

    payload = candidate["candidate_payload"]
    alternative = contract["candidate_payload_tagged_union"][
        "ordered_alternative_records"
    ][0]
    _closed(payload, alternative["ordered_member_names"], "candidate payload")
    _require(
        payload["candidate_kind"]
        == alternative["candidate_kind"]
        == "MAXIMUM_WITNESS_CONTEXT",
        "SCHEMA_INVALID",
        "candidate payload tag differs",
    )
    _require(
        isinstance(payload["witness_record"], dict),
        "SCHEMA_INVALID",
        "witness record is not an object",
    )
    _require(
        payload["scope_witness_context"] is None,
        "SCHEMA_INVALID",
        "intrinsic case 5 has scope context",
    )
    _require(
        payload["ordered_context_object_entries"] == [],
        "SCHEMA_INVALID",
        "intrinsic case 5 has context entries",
    )
    forbidden = set(contract["forbidden_producer_claim_member_names"])
    _require(
        not _contains_forbidden_member(candidate, forbidden),
        "PRODUCER_CLAIM_REJECT",
        "candidate contains a verifier-owned claim",
    )
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        candidate["constructive_candidate_id"]
        == _semantic_id(schema["identity_domain"], identity_payload),
        "IDENTITY_INVALID",
        "candidate identity differs",
    )
    return case, plan, payload["witness_record"]


def _eval_meter_expression(expression, step):
    _require(
        isinstance(expression, dict) and "opcode" in expression,
        "DERIVATION_INVALID",
        "meter expression differs",
    )
    opcode = expression["opcode"]
    if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
        return _u128(expression["value"], "meter constant")
    if opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY" and set(expression) == {"opcode"}:
        return _u128(step["logical_transfer_multiplicity"], "transfer multiplicity")
    if opcode == "PARAM_U128" and set(expression) == {"opcode", "parameter_name"}:
        return _u128(
            step["recurrence_parameters"][expression["parameter_name"]],
            "meter parameter",
        )
    if opcode == "PARAM_LIST_COUNT" and set(expression) == {"opcode", "parameter_name"}:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        _require(
            isinstance(value, list),
            "DERIVATION_INVALID",
            "meter list parameter differs",
        )
        return len(value)
    if opcode in {"INDICATOR_PARAM_NONZERO", "INDICATOR_PARAM_IS_NULL"} and set(
        expression
    ) == {"opcode", "parameter_name"}:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        return (
            int(value is not None)
            if opcode == "INDICATOR_PARAM_NONZERO"
            else int(value is None)
        )
    if opcode in {"CHECKED_ADD", "CHECKED_MUL"} and set(expression) == {
        "opcode",
        "ordered_operands",
    }:
        values = [
            _eval_meter_expression(child, step)
            for child in expression["ordered_operands"]
        ]
        _require(values, "DERIVATION_INVALID", "meter arithmetic has no operands")
        if opcode == "CHECKED_ADD":
            return _checked_add(*values)
        result = 1
        for value in values:
            result = _checked_mul(result, value)
        return result
    _reject("DERIVATION_INVALID", f"meter opcode differs: {opcode}")


def _cell(lower, upper):
    lower = _u128(lower, "cell lower bound")
    upper = _u128(upper, "cell upper bound")
    _require(lower <= upper, "DERIVATION_INVALID", "cell bounds are inverted")
    return {"status": MAY_BE_NONEMPTY, "lower": lower, "upper": upper, "state": []}


def _locator_value(witness, locator):
    value = witness
    typed_path = locator["typed_path"]
    _require(isinstance(typed_path, list), "DERIVATION_INVALID", "typed path differs")
    for step in typed_path:
        _closed(
            step,
            ["member_name", "path_step_kind", "union_alternative_name"],
            "typed-path step",
        )
        _require(
            step["path_step_kind"] == "RECORD_MEMBER",
            "UNSUPPORTED_CASE",
            "case 5 path step is not a record member",
        )
        _require(
            step["union_alternative_name"] is None,
            "UNSUPPORTED_CASE",
            "case 5 path selects a union",
        )
        name = step["member_name"]
        _require(
            isinstance(value, dict) and name in value,
            "WITNESS_ILLEGAL",
            f"witness member is absent: {name}",
        )
        value = value[name]
    return value


def _case5_template(seed, plan):
    recipe = seed["logical_plan_recipe_catalog"]
    templates = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    template = templates.get(plan["logical_plan_template_id"])
    _require(template is not None, "DERIVATION_INVALID", "case 5 template is absent")
    _require(
        plan["logical_root_reference"]
        == {
            "root_kind": "LOGICAL_PLAN_TEMPLATE",
            "root_id": template["logical_plan_template_id"],
        },
        "DERIVATION_INVALID",
        "case 5 root reference differs",
    )
    _require(
        plan["profile_conditioning_program_id"] is None,
        "DERIVATION_INVALID",
        "case 5 unexpectedly has profile conditioning",
    )
    _require(
        plan["local_analytic_catalog_id"] is None,
        "DERIVATION_INVALID",
        "case 5 unexpectedly has local analytics",
    )
    _require(
        plan["root_step_position"] == template["root_step_position"],
        "DERIVATION_INVALID",
        "case 5 root step differs",
    )
    _require(
        template["root_type_name"] == CASE5_TYPE
        and template["root_alternative_name"] is None,
        "DERIVATION_INVALID",
        "case 5 template root binding differs",
    )
    return template


def _plan_identity_preimage(seed, plan):
    identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_COUNT_PLAN"
        ),
        None,
    )
    _require(
        identity is not None,
        "AUTHORITY_INVALID",
        "logical-plan identity authority is absent",
    )
    payload = {name: plan[name] for name in identity["ordered_payload_member_names"]}
    raw = _canonical_bytes(
        {
            "canonicalization_version": seed["canonicalization_version"],
            "domain": identity["domain_literal"],
            "payload": payload,
            "schema_version": seed["measurement_schema_version"],
        }
    )
    _require(
        _sha256(raw) == plan["logical_count_plan_id"],
        "DERIVATION_INVALID",
        "logical-plan identity does not reproduce",
    )
    return raw


def _execute_case5_bound(seed, registry, plan, witness):
    _require(
        set(witness) == {"kind", "value"},
        "WITNESS_ILLEGAL",
        "case 5 witness members differ",
    )
    _require(type(witness["kind"]) is str, "WITNESS_ILLEGAL", "case 5 kind is not text")
    _require(
        type(witness["value"]) is bool, "WITNESS_ILLEGAL", "case 5 value is not Boolean"
    )
    template = _case5_template(seed, plan)
    recurrence = seed["recurrence_catalog"]
    kernels = {
        row["derivation_kind"]: row
        for row in recurrence["ordered_derivation_kernel_records"]
    }
    opcode_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    opcode_contracts = {row["opcode"]: row for row in opcode_rows}
    _require(
        len(kernels) == 18 and len(opcode_contracts) == 18,
        "AUTHORITY_INVALID",
        "recurrence instruction catalog differs",
    )
    cells = []
    actual_lengths = []
    for position, step in enumerate(template["ordered_template_steps"], 1):
        _require(
            step["template_step_position"] == position,
            "DERIVATION_INVALID",
            "template is not strict postorder",
        )
        kernel = kernels.get(step["derivation_kind"])
        _require(
            kernel is not None
            and kernel["kernel_record_sha256"] == step["kernel_record_sha256"],
            "DERIVATION_INVALID",
            "step kernel identity differs",
        )
        children = step["ordered_child_step_positions"]
        _require(
            isinstance(children, list)
            and all(_is_int(child) and 1 <= child < position for child in children),
            "DERIVATION_INVALID",
            "step child order differs",
        )
        parameters = step["recurrence_parameters"]
        _require(
            isinstance(parameters, dict)
            and set(parameters) == set(kernel["ordered_parameter_member_names"]),
            "DERIVATION_INVALID",
            "step parameters differ",
        )
        for target, expression in (
            ("physical_transition_count", "transition_attempt_count_expression"),
            (
                "logical_unbatched_transition_equivalent_count",
                "logical_unbatched_transition_equivalent_count_expression",
            ),
            ("physical_batch_application_count", "batch_application_count_expression"),
        ):
            _require(
                _eval_meter_expression(kernel["meter_program"][expression], step)
                == step[target],
                "DERIVATION_INVALID",
                f"step meter differs: {target}",
            )
        opcode = kernel["transfer_program"]["opcode"]
        contract = opcode_contracts.get(opcode)
        _require(
            contract is not None
            and contract["transfer_rule_id"]
            in {
                row["transfer_rule_id"]
                for row in recurrence["transfer_rule_catalog"][
                    "ordered_transfer_rule_records"
                ]
            },
            "DERIVATION_INVALID",
            "step transfer rule is unresolved",
        )
        _require(
            set(parameters) == set(contract["ordered_required_parameter_names"]),
            "DERIVATION_INVALID",
            "transfer parameter contract differs",
        )
        actual_value = _locator_value(witness, step["subject_locator"])
        actual_length = len(_canonical_bytes(actual_value))

        if opcode == "CELL_FINITE_TEXT_V1":
            literals = parameters["ordered_literals"]
            _require(
                isinstance(literals, list)
                and literals
                and all(type(value) is str for value in literals),
                "DERIVATION_INVALID",
                "finite-text authority differs",
            )
            _require(
                actual_value in literals,
                "WITNESS_ILLEGAL",
                "witness text is outside the finite language",
            )
            lengths = [len(_canonical_bytes(value)) for value in literals]
            cell = _cell(min(lengths), max(lengths))
        elif opcode == "CELL_BOOLEAN_LITERAL_V1":
            literal = parameters["boolean_literal"]
            domain = [False, True] if literal is None else [literal]
            _require(
                all(type(value) is bool for value in domain),
                "DERIVATION_INVALID",
                "Boolean authority differs",
            )
            _require(
                type(actual_value) is bool and actual_value in domain,
                "WITNESS_ILLEGAL",
                "witness Boolean is outside the legal domain",
            )
            lengths = [len(_canonical_bytes(value)) for value in domain]
            cell = _cell(min(lengths), max(lengths))
        elif opcode == "CELL_RECORD_V1":
            rows = parameters["ordered_member_records"]
            _require(
                parameters["record_member_count"] == len(rows) == len(children),
                "DERIVATION_INVALID",
                "record member count differs",
            )
            names = []
            syntax = 2 + max(0, len(rows) - 1)
            for member_position, row in enumerate(rows, 1):
                _require(
                    row["member_position"] == member_position
                    and row["child_step_position"] == children[member_position - 1],
                    "DERIVATION_INVALID",
                    "record member order differs",
                )
                name = row["member_name"]
                names.append(name)
                name_octets = len(_canonical_bytes(name))
                _require(
                    row["member_name_canonical_octets"] == name_octets,
                    "DERIVATION_INVALID",
                    "record member-name length differs",
                )
                syntax = _checked_add(syntax, name_octets, 1)
            _require(
                parameters["record_syntax_octets_excluding_child_values"] == syntax,
                "DERIVATION_INVALID",
                "record syntax authority differs",
            )
            _require(
                isinstance(actual_value, dict) and set(actual_value) == set(names),
                "WITNESS_ILLEGAL",
                "witness record members differ",
            )
            child_cells = [cells[child - 1] for child in children]
            cell = _cell(
                _checked_add(syntax, *(child["lower"] for child in child_cells)),
                _checked_add(syntax, *(child["upper"] for child in child_cells)),
            )
        elif opcode == "CELL_CODEC_INTERSECTION_V1":
            _require(
                children == [parameters["child_step_position"]],
                "DERIVATION_INVALID",
                "codec child differs",
            )
            child = cells[children[0] - 1]
            ceiling = recurrence["arithmetic_policy"]["published_maximum"]
            coordinates = parameters["ordered_codec_coordinate_records"]
            _require(
                isinstance(coordinates, list) and coordinates,
                "DERIVATION_INVALID",
                "codec coordinates are absent",
            )
            for coordinate_position, coordinate in enumerate(coordinates, 1):
                _require(
                    coordinate["coordinate_position"] == coordinate_position,
                    "DERIVATION_INVALID",
                    "codec coordinate order differs",
                )
                relation = coordinate["codec_byte_bound_relation"]
                limit = _u128(coordinate["codec_octet_limit"], "codec limit")
                _require(
                    relation in {"LE", "LT"},
                    "DERIVATION_INVALID",
                    "codec relation differs",
                )
                effective = _checked_sub(limit, int(relation == "LT"))
                sibling = _u128(
                    coordinate["minimum_sibling_and_syntax_octets"],
                    "codec sibling minimum",
                )
                payload_ceiling = 0 if sibling > effective else effective - sibling
                _require(
                    coordinate["derived_payload_octet_ceiling"] == payload_ceiling,
                    "DERIVATION_INVALID",
                    "codec residual differs",
                )
                ceiling = min(ceiling, payload_ceiling)
            _require(
                child["lower"] <= ceiling,
                "DERIVATION_INVALID",
                "codec intersection is empty",
            )
            cell = _cell(child["lower"], min(child["upper"], ceiling))
        else:
            _reject(
                "UNSUPPORTED_CASE",
                f"A4-V case 5 does not admit transfer opcode {opcode}",
            )

        _require(
            cell["lower"] <= actual_length <= cell["upper"],
            "WITNESS_ILLEGAL",
            f"witness misses step {position} bounds",
        )
        cells.append(cell)
        actual_lengths.append(actual_length)

    _require(
        template["root_step_position"] == len(cells),
        "DERIVATION_INVALID",
        "template root is not last",
    )
    root = cells[-1]
    witness_raw = _canonical_bytes(witness)
    _require(
        actual_lengths[-1] == len(witness_raw) == root["upper"],
        "ATTAINMENT_REJECT",
        "witness does not attain the exact upper bound",
    )

    descriptors = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    descriptor = descriptors.get(CASE5_TYPE)
    _require(
        descriptor is not None and descriptor["type_form"] == "RECORD",
        "AUTHORITY_INVALID",
        "case 5 descriptor is absent",
    )
    _require(
        [
            (row["member_name"], row["value_schema_id"])
            for row in descriptor["record_member_descriptors"]
        ]
        == [
            ("kind", template["ordered_template_steps"][0]["value_schema_id"]),
            ("value", template["ordered_template_steps"][1]["value_schema_id"]),
        ],
        "AUTHORITY_INVALID",
        "case 5 descriptor member-schema bindings differ",
    )
    root_coordinate = template["ordered_template_steps"][-1]["recurrence_parameters"][
        "ordered_codec_coordinate_records"
    ][0]
    _require(
        descriptor["codec_byte_bound_relation"]
        == root_coordinate["codec_byte_bound_relation"]
        and descriptor["codec_octet_limit"] == root_coordinate["codec_octet_limit"],
        "AUTHORITY_INVALID",
        "case 5 descriptor/plan codec binding differs",
    )
    return template, cells, descriptor, witness_raw


def _tagged_subject(schema, values):
    members = schema["ordered_member_names"]
    version_member = members[0]
    complete = {version_member: schema[version_member], **values}
    _require(
        set(complete) == set(members),
        "RESOURCE_DERIVATION_INVALID",
        "tagged subject members differ",
    )
    return {name: complete[name] for name in members}


class _CaseEvents:
    def __init__(self, seed, plan):
        self.seed = seed
        self.plan = plan
        self.recurrence = seed["recurrence_catalog"]
        self.grammar = seed["logical_event_catalog"]["case_level_event_grammar"]
        self.programs = {
            row["program_name"]: row
            for row in self.grammar["ordered_case_program_records"]
        }
        self.metadata = {
            row["program_name"]: row
            for row in self.grammar["event_metadata_program"][
                "ordered_program_metadata_records"
            ]
        }
        self.subject_schemas = {
            row["event_kind"]: row
            for row in self.grammar["ordered_subject_schema_records"]
        }
        execution = self.grammar["full_case_execution_program"]
        self.constructors = {
            row["event_kind"]: row
            for row in execution["ordered_subject_constructor_records"]
        }
        self.metric_programs = {
            row["event_kind"]: row["ordered_metric_update_program"]
            for row in seed["logical_event_catalog"]["ordered_event_kind_records"]
        }
        _require(
            len(self.programs) == len(self.metadata) == 9,
            "AUTHORITY_INVALID",
            "case event programs differ",
        )
        _require(
            len(self.subject_schemas) == len(self.constructors) == 16,
            "AUTHORITY_INVALID",
            "case event constructors differ",
        )
        self.tokens = []
        self.event_ordinals = {}
        self.measurements = dict.fromkeys(range(1, 19), 0)

    def construct(self, event_kind, context):
        constructor = self.constructors[event_kind]
        _require(
            constructor["event_kind"] == event_kind,
            "RESOURCE_DERIVATION_INVALID",
            "subject constructor binding differs",
        )
        if constructor["constructor_opcode"] == "USE_EXACT_HASH_SOURCE_BYTES_V1":
            raw = context.get("ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES")
            _require(
                type(raw) is bytes,
                "RESOURCE_DERIVATION_INVALID",
                "hash preimage bytes are absent",
            )
            return raw
        values = {}
        for position, row in enumerate(constructor["ordered_value_source_records"], 1):
            _require(
                row["value_source_position"] == position,
                "RESOURCE_DERIVATION_INVALID",
                "constructor value order differs",
            )
            source = row["value_source"]
            if source.startswith("CONST:"):
                value = source[6:]
            elif source == "null":
                value = None
            elif source in context:
                value = context[source]
            else:
                _reject(
                    "RESOURCE_DERIVATION_INVALID",
                    f"constructor source is unresolved: {event_kind}:{source}",
                )
            _require(
                row["member_name"] not in values,
                "RESOURCE_DERIVATION_INVALID",
                "constructor member is duplicate",
            )
            values[row["member_name"]] = value
        source = constructor["subject_member_order_source"]
        if source == "CONSTRUCTOR_ORDERED_VALUE_SOURCE_RECORDS":
            members = [
                row["member_name"]
                for row in constructor["ordered_value_source_records"]
            ]
        elif source == "/recurrence_catalog/cache_key_schema/ordered_member_names":
            members = self.recurrence["cache_key_schema"]["ordered_member_names"]
        elif (
            source == "/recurrence_catalog/transition_token_schema/ordered_member_names"
        ):
            members = self.recurrence["transition_token_schema"]["ordered_member_names"]
        elif source == "/recurrence_catalog/result_cell_schema/ordered_member_names":
            members = self.recurrence["result_cell_schema"]["ordered_member_names"]
        elif (
            source == "/recurrence_catalog/step_commitment_schema/ordered_member_names"
        ):
            members = self.recurrence["step_commitment_schema"]["ordered_member_names"]
        elif (
            source
            == "/logical_event_catalog/case_level_event_grammar/final_result_subject_contract/ordered_member_names"
        ):
            members = self.grammar["final_result_subject_contract"][
                "ordered_member_names"
            ]
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "subject member-order source differs"
            )
        _require(
            set(values) == set(members),
            "RESOURCE_DERIVATION_INVALID",
            f"subject members differ: {event_kind}",
        )
        return {name: values[name] for name in members}

    def add(
        self,
        program_name,
        emission_position,
        subject,
        source_record=None,
        collection_ordinal=None,
        derivation_unit_ordinal=None,
        ordinary_step_position=None,
    ):
        program = self.programs[program_name]
        metadata = self.metadata[program_name]
        emission = program["ordered_event_emission_records"][emission_position - 1]
        _require(
            emission["emission_position"] == emission_position,
            "RESOURCE_DERIVATION_INVALID",
            "event emission order differs",
        )
        event_kind = emission["event_kind"]
        source_record = source_record or {}

        def expression_value(expression, default=None):
            opcode = expression["opcode"]
            if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
                return _u128(expression["value"], "event constant")
            if opcode == "SOURCE_FIELD_U128" and set(expression) == {
                "opcode",
                "field_name",
            }:
                name = expression["field_name"]
                if name not in source_record:
                    if default is not None:
                        return default
                    _reject(
                        "RESOURCE_DERIVATION_INVALID",
                        f"event source field is absent: {name}",
                    )
                return _u128(source_record[name], f"event source field {name}")
            _reject("RESOURCE_DERIVATION_INVALID", "event expression opcode differs")

        _require(
            expression_value(emission["condition_expression"]) == 1,
            "RESOURCE_DERIVATION_INVALID",
            "event condition is false",
        )
        aggregation = expression_value(
            emission["aggregation_multiplicity_expression"], 1
        )
        logical = expression_value(
            emission["logical_unbatched_equivalent_count_expression"], 0
        )
        ordinal = self.event_ordinals.get(event_kind, 0) + 1
        ordinal_source = metadata["subject_ordinal_sources"][emission_position - 1]
        if ordinal_source == "NULL":
            subject_ordinal = None
        elif ordinal_source == "EMISSION_SUBJECT_COLLECTION_ORDINAL":
            subject_ordinal = collection_ordinal
        elif ordinal_source == "EVENT_KIND_ORDINAL":
            subject_ordinal = ordinal
        elif ordinal_source == "DERIVATION_UNIT_ORDINAL":
            subject_ordinal = derivation_unit_ordinal
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "event subject-ordinal source differs"
            )
        _require(
            ordinal_source == "NULL" or subject_ordinal is not None,
            "RESOURCE_DERIVATION_INVALID",
            "event subject ordinal is unresolved",
        )
        step_source = metadata["logical_derivation_step_position_source"]
        step_position = (
            ordinary_step_position
            if step_source == "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
            else None
        )
        _require(
            step_source in {"CURRENT_ORDINARY_TEMPLATE_STEP_POSITION", "NULL"},
            "RESOURCE_DERIVATION_INVALID",
            "event step source differs",
        )
        _require(
            step_source == "NULL" or step_position is not None,
            "RESOURCE_DERIVATION_INVALID",
            "event step is unresolved",
        )
        observed_source = metadata["observed_value_sources"][emission_position - 1]
        if observed_source == "NULL":
            observed = None
        elif observed_source == "SUBJECT_OBSERVED_VALUE":
            _require(
                isinstance(subject, dict),
                "RESOURCE_DERIVATION_INVALID",
                "observed subject differs",
            )
            observed = subject.get(
                "observed_value",
                subject.get("derived_depth", subject.get("iteration_depth")),
            )
            _u128(observed, "observed event value")
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "event observed-value source differs"
            )
        raw = subject if type(subject) is bytes else _canonical_bytes(subject)
        schema = self.subject_schemas[event_kind]
        token = {
            "event_position": len(self.tokens) + 1,
            "execution_phase": emission["execution_phase"],
            "logical_derivation_step_position": step_position,
            "event_kind": event_kind,
            "event_ordinal": ordinal,
            "subject_schema_version": schema["subject_schema_version"],
            "subject_kind": schema["subject_kind"],
            "subject_role": metadata["ordered_subject_role_literals"][
                emission_position - 1
            ],
            "subject_ordinal": subject_ordinal,
            "subject_canonical_octets": len(raw),
            "subject_sha256": _sha256(raw),
            "aggregation_multiplicity": aggregation,
            "logical_unbatched_equivalent_count": logical,
            "observed_value": observed,
        }
        self.tokens.append(token)
        self.event_ordinals[event_kind] = ordinal
        for update in self.metric_programs[event_kind]:
            source = update["value_source"]
            if source == "ONE":
                value = 1
            elif source == "SUBJECT_CANONICAL_OCTETS":
                value = len(raw)
            elif source == "AGGREGATION_MULTIPLICITY":
                value = aggregation
            elif source == "LOGICAL_UNBATCHED_EQUIVALENT_COUNT":
                value = logical
            elif source == "OBSERVED_VALUE":
                value = observed
            else:
                _reject("RESOURCE_DERIVATION_INVALID", "metric value source differs")
            value = _u128(value, "metric event value")
            metric_position = update["metric_position"]
            if update["update_kind"] == "ADD":
                self.measurements[metric_position] = _checked_add(
                    self.measurements[metric_position], value
                )
            elif update["update_kind"] == "MAX":
                self.measurements[metric_position] = max(
                    self.measurements[metric_position], value
                )
            else:
                _reject("RESOURCE_DERIVATION_INVALID", "metric update kind differs")
        return raw


def _base_context(events):
    plan = events.plan
    recurrence = events.recurrence
    return {
        "PLAN.case_position": plan["case_position"],
        "PLAN.case_kind": plan["case_kind"],
        "PLAN.logical_count_plan_id": plan["logical_count_plan_id"],
        "PLAN.local_analytic_catalog_id": plan["local_analytic_catalog_id"],
        "PLAN.scope_summary.schedule_authority_id": plan["scope_summary"][
            "schedule_authority_id"
        ],
        "PLAN.scope_summary.cross_rule_evaluation_count": plan["scope_summary"][
            "cross_rule_evaluation_count"
        ],
        "PLAN.scope_summary.application_invocation_count": plan["scope_summary"][
            "application_invocation_count"
        ],
        "RECURRENCE.cache_key_schema.cache_key_version": recurrence["cache_key_schema"][
            "cache_key_version"
        ],
        "RECURRENCE.transition_token_schema.transition_token_version": recurrence[
            "transition_token_schema"
        ]["transition_token_version"],
        "RECURRENCE.result_cell_schema.result_cell_version": recurrence[
            "result_cell_schema"
        ]["result_cell_version"],
        "RECURRENCE.step_commitment_schema.step_commitment_version": recurrence[
            "step_commitment_schema"
        ]["step_commitment_version"],
    }


def _live_entries(raw_pairs, commitment_digests):
    entries = []
    for pair in sorted(raw_pairs, key=lambda item: item["key_raw"]):
        entries.extend(
            [
                {
                    "entry_kind": "RECURRENCE_CACHE_KEY_V2",
                    "entry_id": pair["key_sha256"],
                    "canonical_octets": len(pair["key_raw"]),
                },
                {
                    "entry_kind": "RECURRENCE_RESULT_CELL_V2",
                    "entry_id": pair["cell_sha256"],
                    "canonical_octets": len(pair["cell_raw"]),
                },
            ]
        )
    entries.extend(
        {
            "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
            "entry_id": digest,
            "canonical_octets": 32,
        }
        for digest in commitment_digests
    )
    return entries


def _retention_context(events, entries, label):
    observed = _checked_add(*(row["canonical_octets"] for row in entries))
    return {
        "CONTIGUOUS_ONE_BASED_RETENTION_OBSERVATION_ORDINAL": events.event_ordinals.get(
            "RETENTION_OBSERVATION", 0
        )
        + 1,
        "RETENTION.observation_label": label,
        "RETENTION.ordered_live_entry_records": entries,
        "SUM:RETENTION.ordered_live_entry_records.canonical_octets": observed,
    }


def _ordinary_case_units(events, template, cells):
    base = _base_context(events)
    plan = events.plan
    recurrence = events.recurrence
    ceiling = recurrence["arithmetic_policy"]["published_maximum"]
    steps = template["ordered_template_steps"]
    last_parent = {position: position for position in range(1, len(steps) + 1)}
    for parent in steps:
        for child in parent["ordered_child_step_positions"]:
            last_parent[child] = max(
                last_parent[child], parent["template_step_position"]
            )
    active_pairs = {}
    commitment_digests = []
    commitment_records = []
    root_pair = None
    depths = []
    iterations = []
    intrinsic_rule_ids = []
    for position, (step, cell) in enumerate(zip(steps, cells, strict=True), 1):
        child_depths = [
            depths[child - 1] for child in step["ordered_child_step_positions"]
        ]
        depths.append(1 if not child_depths else 1 + max(child_depths))
        kind = step["derivation_kind"]
        if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            maximum_items = step["recurrence_parameters"]["maximum_items"]
            iteration = 0 if maximum_items <= 1 else (maximum_items - 1).bit_length()
        elif kind == "ARRAY_STREAM_FOLD":
            iteration = step["recurrence_parameters"]["maximum_items"]
        elif kind == "APPLICATION_SCHEDULE_COUNT":
            iteration = len(
                step["recurrence_parameters"]["ordered_application_invocation_records"]
            )
        else:
            iteration = step["physical_transition_count"]
        iterations.append(_u128(iteration, "ordinary iteration depth"))
        intrinsic_rule_ids.extend(step["ordered_intrinsic_rule_ids"])
        unit = {
            "UNIT.subject_variant": "ORDINARY_STEP",
            "UNIT.logical_derivation_step_position": position,
            "UNIT.logical_derivation_step_id": step["logical_derivation_step_id"],
            "UNIT.derivation_kind": kind,
            "UNIT.effective_canonical_octet_ceiling": ceiling,
            "UNIT.state_signature_id": step["state_signature_id"],
            "UNIT.owner_profile_position": None,
        }
        cell_context = {
            **base,
            **unit,
            "CELL.state_signature_id": step["state_signature_id"],
            "CELL.ordered_state_components": list(cell["state"]),
            "CELL.cell_status": cell["status"],
            "CELL.certified_lower_bound_octets": cell["lower"],
            "CELL.certified_upper_bound_octets": cell["upper"],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        result_cell = events.construct("RESULT_CELL_EMIT", cell_context)
        result_raw = _canonical_bytes(result_cell)
        result_sha = _sha256(result_raw)
        key_context = {
            **base,
            **unit,
            "CELL.ordered_state_components": list(cell["state"]),
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:STEP.derivation_kind|LOCAL:null": kind,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        cache_key = events.construct("CACHE_INSERT", key_context)
        key_raw = _canonical_bytes(cache_key)
        pair = {
            "position": position,
            "key_raw": key_raw,
            "key_sha256": _sha256(key_raw),
            "cell_raw": result_raw,
            "cell_sha256": result_sha,
        }
        transition_subjects = []
        physical = _u128(step["physical_transition_count"], "physical transitions")
        logical = _u128(
            step["logical_unbatched_transition_equivalent_count"], "logical transitions"
        )
        _require(
            physical > 0 and logical >= physical,
            "RESOURCE_DERIVATION_INVALID",
            "transition run differs",
        )
        quotient, remainder = divmod(logical, physical)
        for ordinal in range(1, physical + 1):
            transition_context = {
                **base,
                **unit,
                "TRANSITION.physical_transition_ordinal": ordinal,
                "ORDINARY:ORDINARY_KERNEL_TRANSITION|LOCAL:LOCAL_CONTROLLER_TRANSITION": "ORDINARY_KERNEL_TRANSITION",
                "TRANSITION.source_state_components": list(cell["state"]),
                "TRANSITION.input_symbol": {
                    "derivation_kind": kind,
                    "physical_transition_ordinal": ordinal,
                },
                "TRANSITION.candidate_state_components": list(cell["state"]),
                "TRANSITION.candidate_certified_upper_bound_octets": cell["upper"],
                "ORDINARY:STEP.template_step_position|LOCAL:null": position,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_position": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.source_controller_state_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.target_controller_state_id": None,
            }
            transition_subjects.append(
                (
                    events.construct("TRANSITION_ATTEMPT", transition_context),
                    quotient + int(ordinal <= remainder),
                )
            )
        _require(
            sum(row[1] for row in transition_subjects) == logical,
            "RESOURCE_DERIVATION_INVALID",
            "transition distribution differs",
        )
        batch_subjects = []
        for ordinal in range(1, step["physical_batch_application_count"] + 1):
            batch_subjects.append(
                events.construct(
                    "BATCH_APPLICATION",
                    {
                        **base,
                        "STEP.template_step_position": position,
                        "BATCH.physical_batch_ordinal": ordinal,
                        "STEP.derivation_kind": kind,
                        "STEP.logical_transfer_multiplicity": step[
                            "logical_transfer_multiplicity"
                        ],
                    },
                )
            )
        commitment_context = {
            **base,
            **unit,
            "UNIT.ordered_result_cells.LENGTH": 1,
            "MAXIMUM:UNIT.ordered_result_cells.certified_upper_bound_octets": cell[
                "upper"
            ],
            "UNIT.ordered_result_cells.CANONICAL_SHA256": [result_sha],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:null|LOCAL:PLAN.local_analytic_catalog_id": None,
            "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id": None,
            "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id": None,
        }
        commitment = events.construct("STEP_COMMITMENT_EMIT", commitment_context)
        commitment_raw = _canonical_bytes(commitment)
        commitment_sha = _sha256(commitment_raw)
        commitment_records.append(
            {
                "derivation_unit_ordinal": position,
                "subject_variant": "ORDINARY_STEP",
                "logical_derivation_step_position": position,
                "local_controller_unit_ordinal": None,
                "step_commitment_sha256": commitment_sha,
            }
        )
        descriptor = events.construct("LOGICAL_DESCRIPTOR_VISIT", {**base, **unit})
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            1,
            descriptor,
            {"aggregation_multiplicity": step["logical_descriptor_occurrence_count"]},
            ordinary_step_position=position,
        )
        for ordinal, (subject, logical_count) in enumerate(transition_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                2,
                subject,
                {"logical_unbatched_equivalent_count": logical_count},
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        for ordinal, subject in enumerate(batch_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                3,
                subject,
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            4,
            result_cell,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            5,
            cache_key,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        active_pairs[position] = pair
        retention = events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries(list(active_pairs.values()), commitment_digests),
                "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            ),
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS", 6, retention, ordinary_step_position=position
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            7,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": result_raw},
            ),
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            8,
            commitment,
            derivation_unit_ordinal=position,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            9,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": commitment_raw},
            ),
            ordinary_step_position=position,
        )
        commitment_digests.append(commitment_sha)
        for retained_position in list(active_pairs):
            if last_parent[retained_position] <= position:
                del active_pairs[retained_position]
        retention = events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries(list(active_pairs.values()), commitment_digests),
                "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            ),
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS", 10, retention, ordinary_step_position=position
        )
        if position == plan["root_step_position"]:
            root_pair = pair
    _require(
        root_pair is not None and not active_pairs,
        "RESOURCE_DERIVATION_INVALID",
        "root/release program did not close",
    )
    return {
        "commitment_digests": commitment_digests,
        "commitment_records": commitment_records,
        "root_pair": root_pair,
        "maximum_derivation_depth": max(depths),
        "maximum_iteration_depth": max(
            max(iterations), plan["scope_summary"]["application_invocation_count"]
        ),
        "intrinsic_rule_ids": intrinsic_rule_ids,
    }


def _event_stream_version(seed):
    record = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_EVENT_STREAM"
        ),
        None,
    )
    _require(
        record is not None,
        "AUTHORITY_INVALID",
        "logical event-stream identity is absent",
    )
    return record["version_literal"]


def _finalize_case_events(events, unit_result, seed, manifest):
    base = _base_context(events)
    plan = events.plan
    intrinsic_ids = unit_result["intrinsic_rule_ids"]
    if intrinsic_ids:
        intrinsic = events.construct(
            "INTRINSIC_RULE_EVALUATION",
            {
                **base,
                "ORDINARY:TEMPLATE_STEPS.ordered_intrinsic_rule_ids|LOCAL:LOCAL_METRIC_PROGRAM.metric_12.ordered_authority_values": intrinsic_ids,
                "ORDERED_INTRINSIC_RULE_IDS.LENGTH": len(intrinsic_ids),
            },
        )
        events.add(
            "EXACT_ATTAINER_VALIDATION",
            1,
            intrinsic,
            {"aggregation_multiplicity": len(intrinsic_ids)},
        )
    scope = plan["scope_summary"]
    application_count = _u128(
        scope["application_invocation_count"], "application count"
    )
    cross_count = _u128(scope["cross_rule_evaluation_count"], "cross-rule count")
    _require(
        application_count == cross_count == 0,
        "UNSUPPORTED_CASE",
        "case 5 unexpectedly has scope applications",
    )
    depth = events.construct(
        "DERIVATION_DEPTH_OBSERVATION",
        {
            **base,
            "DEPTH.maximum_derivation_depth": unit_result["maximum_derivation_depth"],
        },
    )
    events.add("DEPTH_AND_RETENTION", 1, depth)
    iteration = events.construct(
        "ITERATION_DEPTH_OBSERVATION",
        {
            **base,
            "DEPTH.maximum_iteration_depth": unit_result["maximum_iteration_depth"],
        },
    )
    events.add("DEPTH_AND_RETENTION", 2, iteration)
    retention = events.construct(
        "RETENTION_OBSERVATION",
        _retention_context(
            events,
            _live_entries([], unit_result["commitment_digests"]),
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        ),
    )
    events.add("DEPTH_AND_RETENTION", 3, retention)
    root_pair = unit_result["root_pair"]
    final_result = events.construct(
        "FINAL_RESULT_EMIT",
        {
            **base,
            "ROOT_RESULT_CELLS.IN_CANONICAL_CELL_KEY_ORDER.DIGEST_RECORDS": [
                {
                    "result_cell_ordinal": 1,
                    "result_cell_sha256": root_pair["cell_sha256"],
                }
            ],
            "DERIVATION_UNITS.IN_POSTORDER.COMMITMENT_DIGEST_RECORDS": unit_result[
                "commitment_records"
            ],
        },
    )
    final_raw = events.add("FINAL_RESULT", 1, final_result)
    events.add(
        "FINAL_RESULT",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": final_raw},
        ),
    )
    preimage_members = events.grammar["stream_finalization_program"][
        "preimage_member_names"
    ]
    stream_payload = {
        "logical_event_stream_version": _event_stream_version(seed),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "ordered_pre_close_logical_event_tokens": list(events.tokens),
    }
    _require(
        list(stream_payload) == preimage_members,
        "RESOURCE_DERIVATION_INVALID",
        "event-stream preimage order differs",
    )
    stream_raw = _canonical_bytes(stream_payload)
    stream_sha = _sha256(stream_raw)
    close = events.construct(
        "EVENT_STREAM_CLOSE",
        {
            **base,
            "EVENT_STREAM_PREIMAGE.RAW_OCTET_COUNT": len(stream_raw),
            "EVENT_STREAM_PREIMAGE.SHA256": stream_sha,
        },
    )
    events.add("STREAM_FINALIZATION", 1, close)
    events.add(
        "STREAM_FINALIZATION",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": stream_raw},
        ),
    )
    _require(
        [row["event_position"] for row in events.tokens]
        == list(range(1, len(events.tokens) + 1)),
        "RESOURCE_DERIVATION_INVALID",
        "event positions differ",
    )

    metric_rows = seed["resource_metric_catalog"]["ordered_metric_records"]
    f2_rows = manifest["ordered_f2_limit_records"]
    _require(
        len(metric_rows) == len(f2_rows) == 18,
        "AUTHORITY_INVALID",
        "resource metric cardinality differs",
    )
    measurements = []
    for position, (metric, limit) in enumerate(
        zip(metric_rows, f2_rows, strict=True), 1
    ):
        _require(
            metric["metric_position"] == limit["metric_position"] == position,
            "AUTHORITY_INVALID",
            "resource metric order differs",
        )
        _require(
            metric["metric_name"] == limit["metric_name"],
            "AUTHORITY_INVALID",
            "resource metric name differs",
        )
        measured = _u128(events.measurements[position], "resource measurement")
        _require(
            measured <= limit["f2_per_case"],
            "RESOURCE_LIMIT_EXCEEDED",
            f"metric {position} exceeds frozen F2",
        )
        measurements.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "measured_value": measured,
            }
        )
    return measurements, stream_sha


def _derive_case5_resources(seed, manifest, plan, template, cells):
    events = _CaseEvents(seed, plan)
    base = _base_context(events)
    events.add("CASE_OPEN", 1, events.construct("CASE_OPEN", base))
    plan_raw = _plan_identity_preimage(seed, plan)
    events.add(
        "BOUND_PLAN_HASH_PREIMAGE",
        1,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": plan_raw},
        ),
    )
    unit_result = _ordinary_case_units(events, template, cells)
    return _finalize_case_events(events, unit_result, seed, manifest)


def _authority_provenance(authorities):
    seed = authorities["seed"]
    rows = {
        row["authority_role"]: row for row in seed["ordered_authority_binding_records"]
    }
    inventory_row = rows["V4_INVENTORY"]
    registry_row = rows["STRUCTURAL_REGISTRY"]
    literal_row = rows["RULE_LITERAL_AUTHORITY"]
    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    inventory_payload = {
        name: value for name, value in inventory.items() if name != "inventory_sha256"
    }
    _require(
        inventory.get("inventory_sha256")
        == _sha256(_canonical_bytes(inventory_payload))
        == inventory_row["semantic_id"],
        "AUTHORITY_INVALID",
        "V4 inventory semantic identity differs",
    )
    registry = authorities["registry"]
    registry_payload = {
        name: value
        for name, value in registry.items()
        if name
        not in {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            "external_schema_registry_id",
        }
    }
    _require(
        registry.get("record_domain") == REGISTRY_DOMAIN
        and registry.get("external_schema_registry_id")
        == _seed_semantic_id(registry, REGISTRY_DOMAIN, registry_payload)
        == registry_row["semantic_id"],
        "AUTHORITY_INVALID",
        "structural registry semantic identity differs",
    )
    _require(
        inventory["external_schema_registry_v2"]["external_schema_registry_id"]
        == registry["external_schema_registry_id"],
        "AUTHORITY_INVALID",
        "inventory/registry identity binding differs",
    )
    return (
        inventory_row["semantic_id"],
        registry_row["semantic_id"],
        literal_row["raw_sha256"],
    )


def _constraint_scope(authorities, case, source_inventory, registry_id, literal_sha):
    binding = case["case_binding"]
    _require(
        binding["row_kind"] == "INTRINSIC_RECORD",
        "UNSUPPORTED_CASE",
        "case 5 row kind differs",
    )
    measurement_binding = {
        "binding_kind": "SELF_RECORD",
        "validation_root_type_name": binding["type_name"],
        "measured_value_typed_member_path": [],
        "sequence_binding_name": None,
        "sequence_ordinal": None,
    }
    payload = {
        "constraint_scope": "INTRINSIC_TYPE",
        "measured_type_name": binding["type_name"],
        "alternative_name": binding["alternative_name"],
        "measurement_binding": measurement_binding,
        "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": None,
        "evaluation_semantics": EVALUATION_SEMANTICS,
    }
    scope_id = _semantic_id(CONSTRAINT_SCOPE_DOMAIN, payload)
    row_context_payload = {
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "constraint_scope_id": scope_id,
        "required_context_object_count": 0,
        "ordered_required_context_object_ids": [],
    }
    return (
        payload["constraint_scope"],
        scope_id,
        _semantic_id(ROW_CONTEXT_DOMAIN, row_context_payload),
    )


def _f2_resource_catalog_id(authorities):
    if authorities["effective_f2_id"] is not None:
        return authorities["effective_f2_id"]
    boundary = authorities["boundary"]
    seed = authorities["seed"]
    manifest = authorities["manifest"]
    catalog = boundary["authority_contract"]["f2_resource_limit_catalog"]
    payload = {
        "catalog_version": catalog["catalog_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "ordered_f2_limit_records": manifest["ordered_f2_limit_records"],
    }
    catalog_id = _semantic_id(catalog["identity_domain"], payload)
    _require(
        catalog_id == catalog["f2_resource_limit_catalog_id"],
        "AUTHORITY_INVALID",
        "F2 resource-limit catalog identity differs",
    )
    return catalog_id


def _build_result(
    authorities, case, plan, witness, witness_raw, descriptor, measurements, stream_sha
):
    boundary = authorities["boundary"]
    output = boundary["verifier_output_contract"]
    source_inventory, registry_id, literal_sha = _authority_provenance(authorities)
    constraint_scope, scope_id, row_context_id = _constraint_scope(
        authorities, case, source_inventory, registry_id, literal_sha
    )
    maximum = len(witness_raw)
    relation = descriptor["codec_byte_bound_relation"]
    codec_limit = descriptor["codec_octet_limit"]
    codec_slack = _checked_sub(codec_limit, maximum + int(relation == "LT"))

    certificate_schema = output["upper_bound_certificate_schema"]
    certificate = {
        "certificate_version": certificate_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": scope_id,
        "upper_bound_mode": plan["upper_bound_mode"],
        "derivation_catalog_id": plan["recurrence_catalog_id"],
        "derivation_plan_id": plan["logical_count_plan_id"],
        "ordered_safe_relaxation_rule_ids": plan["ordered_safe_relaxation_rule_ids"],
        "certified_upper_bound_octets": maximum,
        "streamed_derivation_result_sha256": stream_sha,
    }
    certificate["upper_bound_certificate_id"] = _semantic_id(
        certificate_schema["identity_domain"], certificate
    )

    report_schema = output["proof_resource_report_schema"]
    report = {
        "resource_report_version": report_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": scope_id,
        "derivation_plan_id": plan["logical_count_plan_id"],
        "derivation_certificate_id": certificate["upper_bound_certificate_id"],
        "resource_limit_catalog_id": _f2_resource_catalog_id(authorities),
        "ordered_resource_measurements": measurements,
    }
    report["proof_resource_report_id"] = _semantic_id(
        report_schema["identity_domain"], report
    )

    schema = output["maximum_attainer_schema"]
    result = {
        "artifact_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "type_name": case["case_binding"]["type_name"],
        "alternative_name": case["case_binding"]["alternative_name"],
        "constraint_scope": constraint_scope,
        "constraint_scope_id": scope_id,
        "constraint_scope_profile_id": case["case_binding"][
            "constraint_scope_profile_id"
        ],
        "witness_kind": schema["witness_kind"],
        "canonical_byte_length": maximum,
        "certified_analytic_maximum_octets": maximum,
        "codec_byte_bound_relation": relation,
        "codec_octet_limit": codec_limit,
        "codec_slack_octets": codec_slack,
        "canonical_sha256": _sha256(witness_raw),
        "witness_record": witness,
        "scope_witness_context": None,
        "required_context_object_count": 0,
        "ordered_required_context_object_ids": [],
        "row_context_closure_id": row_context_id,
        "upper_bound_certificate": certificate,
        "proof_resource_report": report,
    }
    _require(
        list(result) == schema["ordered_member_names"][:-1],
        "OUTPUT_SCHEMA_INVALID",
        "maximum result member order differs",
    )
    result["maximum_attainer_id"] = _semantic_id(schema["identity_domain"], result)
    return result


def _build_receipt(authorities, candidate, candidate_raw, result, result_raw):
    boundary = authorities["boundary"]
    output = boundary["verifier_output_contract"]
    schema = output["verification_receipt_schema"]
    receipt = {
        "receipt_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": authorities["effective_seed_id"],
        "finalization_manifest_id": authorities["effective_manifest_id"],
        "case_position": candidate["case_position"],
        "case_kind": candidate["case_kind"],
        "case_binding": candidate["case_binding"],
        "logical_count_plan_id": candidate["logical_count_plan_id"],
        "constructive_candidate_id": candidate["constructive_candidate_id"],
        "candidate_raw_octets": len(candidate_raw),
        "candidate_raw_sha256": _sha256(candidate_raw),
        "verification_status": schema["maximum_status"],
        "result_artifact_kind": "MAXIMUM_ATTAINER",
        "result_artifact_id": result["maximum_attainer_id"],
        "result_repository_relative_path": output["verified_bundle_paths"][
            "maximum_result"
        ],
        "result_raw_octets": len(result_raw),
        "result_raw_sha256": _sha256(result_raw),
        "ordered_verified_context_object_entries": [],
    }
    _require(
        list(receipt) == schema["ordered_member_names"][:-1],
        "OUTPUT_SCHEMA_INVALID",
        "receipt member order differs",
    )
    receipt["verification_receipt_id"] = _semantic_id(
        schema["identity_domain"], receipt
    )
    return receipt


def _write_all(descriptor, raw):
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        _require(
            written > 0, "OUTPUT_ATOMICITY_INVALID", "output write made no progress"
        )
        offset += written


def _write_exclusive(path, raw):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_private_tree(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        for entry in os.scandir(path):
            _remove_private_tree(path / entry.name)
        os.rmdir(path)
    else:
        os.unlink(path)


def _publish_output(output_root, result, receipt, file_limit):
    _require(
        not output_root.exists(),
        "OUTPUT_ATOMICITY_INVALID",
        "output root already exists",
    )
    parent = output_root.parent
    _directory_signature(parent, "output parent")
    temporary = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.private.", dir=parent)
    )
    try:
        os.chmod(temporary, 0o700)
        context = temporary / "context_objects"
        os.mkdir(context, 0o700)
        result_raw = _pretty_bytes(result)
        receipt_raw = _pretty_bytes(receipt)
        _require(
            len(result_raw) < file_limit and len(receipt_raw) < file_limit,
            "OUTPUT_LIMIT_EXCEEDED",
            "verified output file exceeds the frozen individual-file limit",
        )
        _write_exclusive(temporary / "maximum_attainer.json", result_raw)
        _write_exclusive(temporary / "verification_receipt.json", receipt_raw)
        _fsync_directory(context)
        _fsync_directory(temporary)
        _require(
            not output_root.exists(),
            "OUTPUT_ATOMICITY_INVALID",
            "output root appeared during publication",
        )
        os.rename(temporary, output_root)
        _fsync_directory(parent)
        temporary = None
    finally:
        if temporary is not None:
            _remove_private_tree(temporary)


def _lexical_cli_path(value, label):
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    _require(
        all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "INVOCATION_INVALID",
        f"{label} has a forbidden component",
    )
    return path


def _arguments(argv):
    expected_flags = [
        "--repository-root",
        "--boundary",
        "--candidate-root",
        "--output-root",
    ]
    _require(len(argv) == 8, "INVOCATION_INVALID", "expected four option/value pairs")
    _require(
        argv[::2] == expected_flags, "INVOCATION_INVALID", "argument order differs"
    )
    return tuple(
        _lexical_cli_path(value, flag[2:])
        for flag, value in zip(expected_flags, argv[1::2], strict=True)
    )


def _verify(repository_root, boundary_path, candidate_root, output_root):
    _absolute_lexical_path(repository_root, "repository root", True)
    _directory_signature(repository_root, "repository root")
    _absolute_lexical_path(boundary_path, "boundary", True)
    authorities = _load_authorities(repository_root, boundary_path)

    _absolute_lexical_path(candidate_root, "candidate root", True)
    _absolute_lexical_path(output_root, "output root", False)
    _require(
        not output_root.exists(),
        "OUTPUT_ATOMICITY_INVALID",
        "output root already exists",
    )
    candidate_text = os.fspath(candidate_root)
    output_text = os.fspath(output_root)
    _require(
        os.path.commonpath([candidate_text, output_text])
        not in {candidate_text, output_text},
        "OUTPUT_ATOMICITY_INVALID",
        "candidate and output roots overlap",
    )

    snapshot = _candidate_snapshot(candidate_root, authorities)
    candidate = _strict_loads(snapshot["raw"], authorities["limits"])
    _require(
        isinstance(candidate, dict), "SCHEMA_INVALID", "candidate root is not an object"
    )
    case, plan, witness = _validate_candidate(candidate, snapshot["raw"], authorities)
    template, cells, descriptor, witness_raw = _execute_case5_bound(
        authorities["seed"], authorities["registry"], plan, witness
    )
    measurements, stream_sha = _derive_case5_resources(
        authorities["seed"], authorities["manifest"], plan, template, cells
    )
    result = _build_result(
        authorities,
        case,
        plan,
        witness,
        witness_raw,
        descriptor,
        measurements,
        stream_sha,
    )
    result_raw = _pretty_bytes(result)
    receipt = _build_receipt(
        authorities, candidate, snapshot["raw"], result, result_raw
    )

    _candidate_recheck(candidate_root, snapshot, authorities)
    total = _authority_recheck(authorities["authority_records"])
    _require(
        total + len(snapshot["raw"])
        <= authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "rechecked authority bytes exceed F0",
    )
    _require(
        len(authorities["authority_records"]) + 1
        <= authorities["limits"]["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "rechecked input file count exceeds F0",
    )
    _publish_output(
        output_root,
        result,
        receipt,
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
    )


def _entrypoint(argv):
    try:
        arguments = _arguments(argv)
        _verify(*arguments)
        return 0
    except VerifierReject as error:
        line = f"{ERROR_PREFIX}{error.code}: {error.message}\n"
        sys.stderr.write(line)
        return 2 if error.code == "INVOCATION_INVALID" else 1
    except Exception as error:
        message = f"{type(error).__name__}: {error}".replace("\n", " ").replace(
            "\r", " "
        )[:768]
        sys.stderr.write(f"{ERROR_PREFIX}INTERNAL_FAIL_CLOSED: {message}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint(sys.argv[1:]))
