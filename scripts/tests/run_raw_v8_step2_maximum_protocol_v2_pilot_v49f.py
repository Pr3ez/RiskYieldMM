#!/usr/bin/env python3
"""Parent-owned all-or-nothing runner for the frozen V2 six-case pilot."""

import hashlib
import json
import os
import pathlib
import resource
import select
import signal
import stat
import sys
import tempfile
import time

SOURCE_MARKER = "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PILOT_RUNNER_"

BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
PACKED_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
TARGET_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
SUCCESSOR_SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
SUCCESSOR_MANIFEST_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
SUCCESSOR_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
PRODUCER_RELATIVE_PATH = (
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER_RELATIVE_PATH = (
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
RUNNER_RELATIVE_PATH = (
    "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)

BOUNDARY_OCTETS = 27_334
BOUNDARY_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
PACKED_BOUNDARY_OCTETS = 6_049
PACKED_BOUNDARY_SHA256 = (
    "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b"
)
PACKED_BOUNDARY_ID = "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd"
PACKED_BOUNDARY_DOMAIN = "RiskYieldMMStep2Case435ContextPackBoundaryDeltaV1V4_9F_RawV8"
TARGET_OCTETS = 4_768
TARGET_SHA256 = "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b"
TARGET_ID = "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
TARGET_DOMAIN = "RiskYieldMMStep2Case435ExactSixCaseTargetDeltaV1V4_9F_RawV8"
SEED_OCTETS = 13_419_905
SEED_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
MANIFEST_OCTETS = 15_560
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
SUCCESSOR_SEED_OCTETS = 22_976
SUCCESSOR_SEED_SHA256 = (
    "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da"
)
SUCCESSOR_MANIFEST_OCTETS = 2_192
SUCCESSOR_MANIFEST_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_BOUNDARY_OCTETS = 4_806
SUCCESSOR_BOUNDARY_SHA256 = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)

PILOT_CASES = (5, 24, 54, 69, 435, 475)
UINT128_MAX = (1 << 128) - 1
SAFE_INTEGER_MAX = (1 << 53) - 1
POLL_SECONDS = 0.02
TERMINATION_GRACE_NS = 2_000_000_000
CHILD_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
}


class InvocationReject(ValueError):
    """The fixed public CLI differs."""


class RunnerReject(ValueError):
    """The pilot must fail closed."""


def _require(condition, code):
    if not condition:
        raise RunnerReject(code)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")


def _pretty_bytes(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8", errors="strict")


def _pretty_bytes_in_order(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8", errors="strict")


def _semantic_id(domain, payload):
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs):
    result = {}
    for name, value in pairs:
        _require(name not in result, "JSON_DUPLICATE_MEMBER")
        result[name] = value
    return result


def _reject_number(value):
    raise RunnerReject("JSON_NUMBER_DOMAIN_INVALID")


def _strict_loads(raw):
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(not text.startswith("\ufeff"), "JSON_BOM_INVALID")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RunnerReject("JSON_INVALID") from error
    _require(type(value) is dict, "JSON_ROOT_INVALID")
    return value


def _closed(value, names, code):
    _require(type(value) is dict and set(value) == set(names), code)
    return value


def _sha(value, code):
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        code,
    )
    return value


def _safe_integer(value, code):
    _require(type(value) is int and 0 <= value <= SAFE_INTEGER_MAX, code)
    return value


def _checked_add(left, right, code):
    _require(
        type(left) is int
        and type(right) is int
        and 0 <= left <= UINT128_MAX
        and 0 <= right <= UINT128_MAX
        and left <= UINT128_MAX - right,
        code,
    )
    result = left + right
    _require(result <= SAFE_INTEGER_MAX, code)
    return result


def _canonical_absolute(value, code):
    _require(type(value) is str and value != "", code)
    _require(os.path.isabs(value) and os.path.normpath(value) == value, code)
    parts = pathlib.Path(value).parts
    _require(all(part not in {"", ".", ".."} for part in parts[1:]), code)
    return pathlib.Path(value)


def _relative_parts(relative_path):
    path = pathlib.PurePosixPath(relative_path)
    _require(
        not path.is_absolute()
        and path.parts
        and all(part not in {"", ".", ".."} for part in path.parts),
        "AUTHORITY_PATH_INVALID",
    )
    return path.parts


def _open_repository(repository_root):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(repository_root, flags)
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "REPOSITORY_ROOT_INVALID")
    return descriptor


def _read_beneath(repository_descriptor, relative_path, octet_limit):
    parts = _relative_parts(relative_path)
    current = os.dup(repository_descriptor)
    try:
        for component in parts[:-1]:
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            following = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = following
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(parts[-1], flags, dir_fd=current)
        try:
            before = os.fstat(descriptor)
            _require(
                stat.S_ISREG(before.st_mode)
                and before.st_nlink == 1
                and 0 <= before.st_size < octet_limit,
                "AUTHORITY_FILE_INVALID",
            )
            chunks = []
            remaining = before.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, 1 << 20))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            signature = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mode,
                before.st_nlink,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            _require(
                len(raw) == before.st_size
                and os.read(descriptor, 1) == b""
                and signature
                == (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mode,
                    after.st_nlink,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ),
                "AUTHORITY_READ_DRIFT",
            )
            return raw, signature
        finally:
            os.close(descriptor)
    finally:
        os.close(current)


def _authority_value(repository_descriptor, relative_path, expected):
    raw, signature = _read_beneath(
        repository_descriptor, relative_path, expected[0] + 1
    )
    _require(
        len(raw) == expected[0] and _sha256(raw) == expected[1],
        "AUTHORITY_BYTES_INVALID",
    )
    value = _strict_loads(raw)
    _require(raw == _pretty_bytes_in_order(value), "AUTHORITY_ENCODING_INVALID")
    return value, raw, signature


def _role_source(repository_descriptor, relative_path, marker):
    raw, signature = _read_beneath(repository_descriptor, relative_path, 1 << 24)
    _require(marker.encode("utf-8") in raw, "ROLE_SOURCE_MARKER_INVALID")
    return raw, signature


def _authority_record(relative_path, raw, signature):
    return {
        "relative_path": relative_path,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
        "signature": signature,
    }


def _load_context(repository_root, boundary_path):
    repository_root = pathlib.Path(repository_root)
    boundary_path = pathlib.Path(boundary_path)
    _require(
        boundary_path == repository_root / PACKED_BOUNDARY_RELATIVE_PATH,
        "PACKED_BOUNDARY_REQUIRED",
    )
    _require(
        pathlib.Path(os.path.abspath(__file__))
        == repository_root / RUNNER_RELATIVE_PATH,
        "RUNNER_SOURCE_PATH_INVALID",
    )
    repository_descriptor = _open_repository(repository_root)
    try:
        boundary, boundary_raw, boundary_signature = _authority_value(
            repository_descriptor,
            BOUNDARY_RELATIVE_PATH,
            (BOUNDARY_OCTETS, BOUNDARY_SHA256),
        )
        packed, packed_raw, packed_signature = _authority_value(
            repository_descriptor,
            PACKED_BOUNDARY_RELATIVE_PATH,
            (PACKED_BOUNDARY_OCTETS, PACKED_BOUNDARY_SHA256),
        )
        target, target_raw, target_signature = _authority_value(
            repository_descriptor,
            TARGET_RELATIVE_PATH,
            (TARGET_OCTETS, TARGET_SHA256),
        )
        seed, seed_raw, seed_signature = _authority_value(
            repository_descriptor,
            SEED_RELATIVE_PATH,
            (SEED_OCTETS, SEED_SHA256),
        )
        manifest, manifest_raw, manifest_signature = _authority_value(
            repository_descriptor,
            MANIFEST_RELATIVE_PATH,
            (MANIFEST_OCTETS, MANIFEST_SHA256),
        )
        successor_seed, successor_seed_raw, successor_seed_signature = _authority_value(
            repository_descriptor,
            SUCCESSOR_SEED_RELATIVE_PATH,
            (SUCCESSOR_SEED_OCTETS, SUCCESSOR_SEED_SHA256),
        )
        successor_manifest, successor_manifest_raw, successor_manifest_signature = (
            _authority_value(
                repository_descriptor,
                SUCCESSOR_MANIFEST_RELATIVE_PATH,
                (SUCCESSOR_MANIFEST_OCTETS, SUCCESSOR_MANIFEST_SHA256),
            )
        )
        successor_boundary, successor_boundary_raw, successor_boundary_signature = (
            _authority_value(
                repository_descriptor,
                SUCCESSOR_BOUNDARY_RELATIVE_PATH,
                (SUCCESSOR_BOUNDARY_OCTETS, SUCCESSOR_BOUNDARY_SHA256),
            )
        )
        role_rows = {
            row["role_name"]: row
            for row in boundary["implementation_role_contract"]["ordered_role_records"]
        }
        producer_raw, producer_signature = _role_source(
            repository_descriptor,
            PRODUCER_RELATIVE_PATH,
            role_rows["SEPARATE_PRODUCER"]["source_marker"],
        )
        verifier_raw, verifier_signature = _role_source(
            repository_descriptor,
            VERIFIER_RELATIVE_PATH,
            role_rows["INDEPENDENT_VERIFIER"]["source_marker"],
        )
        runner_raw, runner_signature = _role_source(
            repository_descriptor, RUNNER_RELATIVE_PATH, SOURCE_MARKER
        )
    finally:
        os.close(repository_descriptor)

    _require(
        boundary["constructive_boundary_id"]
        == _semantic_id(
            BOUNDARY_DOMAIN,
            {
                name: value
                for name, value in boundary.items()
                if name != "constructive_boundary_id"
            },
        )
        == BOUNDARY_ID,
        "BOUNDARY_ID_INVALID",
    )
    _require(
        packed["case435_context_pack_boundary_delta_id"]
        == _semantic_id(
            PACKED_BOUNDARY_DOMAIN,
            {
                name: value
                for name, value in packed.items()
                if name != "case435_context_pack_boundary_delta_id"
            },
        )
        == PACKED_BOUNDARY_ID,
        "PACKED_BOUNDARY_ID_INVALID",
    )
    _require(
        target["successor_six_case_target_id"]
        == _semantic_id(
            TARGET_DOMAIN,
            {
                name: value
                for name, value in target.items()
                if name != "successor_six_case_target_id"
            },
        )
        == TARGET_ID,
        "TARGET_ID_INVALID",
    )
    effective = packed["unchanged_effective_authorities"]
    _require(
        effective["successor_seed_catalog_id"]
        == successor_seed["successor_seed_catalog_id"]
        == target["successor_seed_delta_authority"]["successor_seed_catalog_id"],
        "SUCCESSOR_SEED_BINDING_INVALID",
    )
    _require(
        effective["successor_manifest_id"]
        == successor_manifest["successor_manifest_id"]
        == target["successor_manifest_delta_authority"]["successor_manifest_id"],
        "SUCCESSOR_MANIFEST_BINDING_INVALID",
    )
    _require(
        effective["maximum_protocol_sha256"] == SUCCESSOR_MANIFEST_SHA256,
        "SUCCESSOR_PROTOCOL_BINDING_INVALID",
    )
    _require(
        packed["predecessor_successor_boundary_authority"]["raw_sha256"]
        == SUCCESSOR_BOUNDARY_SHA256
        == target["successor_boundary_delta_authority"]["raw_sha256"],
        "SUCCESSOR_BOUNDARY_BINDING_INVALID",
    )
    _require(
        [row["case_position"] for row in target["ordered_pilot_case_records"]]
        == list(PILOT_CASES),
        "PILOT_CASE_ORDER_INVALID",
    )
    _require(
        target["protocol_version"] == boundary["protocol_version"],
        "PILOT_PROTOCOL_INVALID",
    )
    for role, path in (
        ("SEPARATE_PRODUCER", PRODUCER_RELATIVE_PATH),
        ("INDEPENDENT_VERIFIER", VERIFIER_RELATIVE_PATH),
        ("PARENT_PILOT_RUNNER", RUNNER_RELATIVE_PATH),
    ):
        _require(
            role_rows[role]["repository_relative_path"] == path
            and type(role_rows[role]["source_marker"]) is str
            and bool(role_rows[role]["source_marker"]),
            "ROLE_CONTRACT_INVALID",
        )
    _require(
        role_rows["PARENT_PILOT_RUNNER"]["source_marker"] == SOURCE_MARKER,
        "ROLE_CONTRACT_INVALID",
    )
    source_identities = {
        (producer_signature[0], producer_signature[1]),
        (verifier_signature[0], verifier_signature[1]),
        (runner_signature[0], runner_signature[1]),
    }
    _require(len(source_identities) == 3, "ROLE_SOURCE_ALIAS_INVALID")

    platform_limits = {
        row["resource_name"]: row["ceiling_value"]
        for row in seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    }
    required_limits = {
        "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS",
        "F1_WALL_CLOCK_SECONDS",
        "F1_CPU_SECONDS",
        "F1_PEAK_RSS_OCTETS",
        "F1_TEMPORARY_STORAGE_OCTETS",
        "PUBLICATION_STAGING_STORAGE_OCTETS",
        "INPUT_FILE_COUNT",
    }
    _require(required_limits <= set(platform_limits), "F0_LIMITS_INVALID")
    f2_rows = manifest["ordered_f2_limit_records"]
    _require(
        type(f2_rows) is list
        and len(f2_rows) == 18
        and [row["metric_position"] for row in f2_rows] == list(range(1, 19)),
        "F2_LIMITS_INVALID",
    )
    for row in f2_rows:
        _safe_integer(row["f2_per_case"], "F2_PER_CASE_INVALID")
        _safe_integer(row["f2_full_run"], "F2_FULL_RUN_INVALID")
        _require(row["full_run_aggregation"] in {"SUM", "MAXIMUM"}, "F2_MODE_INVALID")

    authorities = []
    for relative_path, raw, signature in (
        (BOUNDARY_RELATIVE_PATH, boundary_raw, boundary_signature),
        (PACKED_BOUNDARY_RELATIVE_PATH, packed_raw, packed_signature),
        (TARGET_RELATIVE_PATH, target_raw, target_signature),
        (SEED_RELATIVE_PATH, seed_raw, seed_signature),
        (MANIFEST_RELATIVE_PATH, manifest_raw, manifest_signature),
        (SUCCESSOR_SEED_RELATIVE_PATH, successor_seed_raw, successor_seed_signature),
        (
            SUCCESSOR_MANIFEST_RELATIVE_PATH,
            successor_manifest_raw,
            successor_manifest_signature,
        ),
        (
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            successor_boundary_raw,
            successor_boundary_signature,
        ),
        (PRODUCER_RELATIVE_PATH, producer_raw, producer_signature),
        (VERIFIER_RELATIVE_PATH, verifier_raw, verifier_signature),
        (RUNNER_RELATIVE_PATH, runner_raw, runner_signature),
    ):
        authorities.append(_authority_record(relative_path, raw, signature))
    del successor_boundary
    return {
        "repository_root": repository_root,
        "boundary_path": boundary_path,
        "boundary": boundary,
        "packed": packed,
        "target": target,
        "seed": seed,
        "manifest": manifest,
        "effective": effective,
        "limits": platform_limits,
        "f2_rows": f2_rows,
        "role_rows": role_rows,
        "source_raw": {
            "SEPARATE_PRODUCER": producer_raw,
            "INDEPENDENT_VERIFIER": verifier_raw,
            "PARENT_PILOT_RUNNER": runner_raw,
        },
        "authorities": authorities,
    }


def _recheck_authorities(context):
    repository_descriptor = _open_repository(context["repository_root"])
    try:
        for record in context["authorities"]:
            raw, signature = _read_beneath(
                repository_descriptor,
                record["relative_path"],
                record["raw_octets"] + 1,
            )
            _require(
                len(raw) == record["raw_octets"]
                and _sha256(raw) == record["raw_sha256"]
                and signature == record["signature"],
                "AUTHORITY_DRIFT",
            )
    finally:
        os.close(repository_descriptor)


def _allocated_octets(root):
    if not root.exists():
        return 0
    total = 0
    stack = [root]
    while stack:
        path = stack.pop()
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            # A child may atomically rename or remove its private publication
            # path between the directory scan and this observation. The final
            # closed-root validation remains strict after wait4.
            continue
        _require(not stat.S_ISLNK(metadata.st_mode), "STAGING_SYMLINK_INVALID")
        total = _checked_add(total, metadata.st_blocks * 512, "STAGING_SIZE_OVERFLOW")
        if stat.S_ISDIR(metadata.st_mode):
            try:
                with os.scandir(path) as entries:
                    stack.extend(pathlib.Path(entry.path) for entry in entries)
            except FileNotFoundError:
                continue
        else:
            _require(stat.S_ISREG(metadata.st_mode), "STAGING_FILE_TYPE_INVALID")
    return total


def _set_child_limits(limits):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cpu = limits["F1_CPU_SECONDS"]
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    file_size = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"] - 1
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    address_space = limits["F1_PEAK_RSS_OCTETS"]
    resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
    nofile = limits["INPUT_FILE_COUNT"]
    resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))


def _drain_pipe(descriptor, state, capture_limit):
    while True:
        try:
            raw = os.read(descriptor, 65_536)
        except BlockingIOError:
            return False
        if not raw:
            os.close(descriptor)
            return True
        state["octets"] = _checked_add(
            state["octets"], len(raw), "DIAGNOSTIC_SIZE_OVERFLOW"
        )
        remaining = max(0, capture_limit + 1 - len(state["captured"]))
        if remaining:
            state["captured"].extend(raw[:remaining])


def _signal_group(pid, selected_signal):
    try:
        os.killpg(pid, selected_signal)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, selected_signal)
        except ProcessLookupError:
            pass


def _run_child(context, label, arguments, child_root, staging_root):
    limits = context["limits"]
    capture_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    start_ns = time.monotonic_ns()
    try:
        pid = os.fork()
    except OSError as error:
        for descriptor in (stdout_read, stdout_write, stderr_read, stderr_write):
            os.close(descriptor)
        raise RunnerReject("CHILD_FORK_FAILED") from error
    if pid == 0:
        try:
            os.close(stdout_read)
            os.close(stderr_read)
            os.setsid()
            os.chdir(context["repository_root"])
            os.umask(0o077)
            _set_child_limits(limits)
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            os.close(stdout_write)
            os.close(stderr_write)
            maximum_descriptors = os.sysconf("SC_OPEN_MAX")
            os.closerange(3, min(maximum_descriptors, 1_048_576))
            os.execve(sys.executable, arguments, CHILD_ENVIRONMENT)
        except BaseException:
            try:
                os.write(2, b"PILOT_CHILD_LAUNCH_FAILED\n")
            except OSError:
                pass
            os._exit(127)

    os.close(stdout_write)
    os.close(stderr_write)
    os.set_blocking(stdout_read, False)
    os.set_blocking(stderr_read, False)
    states = {
        stdout_read: {"octets": 0, "captured": bytearray()},
        stderr_read: {"octets": 0, "captured": bytearray()},
    }
    open_descriptors = {stdout_read, stderr_read}
    status = None
    usage = None
    wait_ns = None
    rejection = None
    term_sent_ns = None
    child_exit_ns = None
    wall_limit_ns = limits["F1_WALL_CLOCK_SECONDS"] * 1_000_000_000
    try:
        while status is None or open_descriptors:
            ready, _write, _exceptional = select.select(
                list(open_descriptors), [], [], POLL_SECONDS
            )
            for descriptor in ready:
                if _drain_pipe(descriptor, states[descriptor], capture_limit):
                    open_descriptors.discard(descriptor)
            now = time.monotonic_ns()
            if rejection is None:
                if any(state["octets"] > capture_limit for state in states.values()):
                    rejection = "CHILD_DIAGNOSTIC_LIMIT"
                elif (
                    _allocated_octets(child_root)
                    > limits["F1_TEMPORARY_STORAGE_OCTETS"]
                ):
                    rejection = "CHILD_TEMPORARY_STORAGE_LIMIT"
                elif (
                    _allocated_octets(staging_root)
                    > limits["PUBLICATION_STAGING_STORAGE_OCTETS"]
                ):
                    rejection = "PILOT_STAGING_STORAGE_LIMIT"
                elif now - start_ns > wall_limit_ns:
                    rejection = "CHILD_WALL_LIMIT"
            if rejection is not None and status is None:
                if term_sent_ns is None:
                    _signal_group(pid, signal.SIGTERM)
                    term_sent_ns = now
                elif now - term_sent_ns >= TERMINATION_GRACE_NS:
                    _signal_group(pid, signal.SIGKILL)
            if status is None:
                waited_pid, waited_status, waited_usage = os.wait4(pid, os.WNOHANG)
                if waited_pid == pid:
                    status = waited_status
                    usage = waited_usage
                    wait_ns = time.monotonic_ns()
                    child_exit_ns = wait_ns
            elif open_descriptors and now - child_exit_ns > TERMINATION_GRACE_NS:
                rejection = rejection or "CHILD_DESCENDANT_PIPE_LEAK"
                _signal_group(pid, signal.SIGKILL)
                for descriptor in tuple(open_descriptors):
                    os.close(descriptor)
                    open_descriptors.discard(descriptor)
    except BaseException:
        if status is None:
            _signal_group(pid, signal.SIGKILL)
            try:
                os.wait4(pid, 0)
            except OSError:
                pass
        for descriptor in tuple(open_descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    _require(
        status is not None and usage is not None and wait_ns is not None,
        "WAIT4_INVALID",
    )
    _require(sys.platform == "linux", "WAIT4_PLATFORM_INVALID")
    _require(rejection is None, rejection or "CHILD_RESOURCE_INVALID")
    _require(os.waitstatus_to_exitcode(status) == 0, f"{label}_FAILED")
    _require(
        states[stdout_read]["octets"] == 0 and states[stderr_read]["octets"] == 0,
        f"{label}_NOISY",
    )
    cpu_seconds = usage.ru_utime + usage.ru_stime
    _require(cpu_seconds <= limits["F1_CPU_SECONDS"], "CHILD_CPU_LIMIT")
    _require(
        usage.ru_maxrss * 1024 <= limits["F1_PEAK_RSS_OCTETS"],
        "CHILD_RSS_LIMIT",
    )
    _require(wait_ns - start_ns <= wall_limit_ns, "CHILD_WALL_LIMIT")


def _remove_tree(root):
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        root.unlink()
        return
    with os.scandir(root) as entries:
        children = [pathlib.Path(entry.path) for entry in entries]
    for child in children:
        child_metadata = child.lstat()
        if stat.S_ISDIR(child_metadata.st_mode) and not stat.S_ISLNK(
            child_metadata.st_mode
        ):
            _remove_tree(child)
        else:
            child.unlink()
    root.rmdir()


def _scan_tree(root):
    _require(root.is_dir() and not root.is_symlink(), "OUTPUT_ROOT_INVALID")
    records = []
    identities = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        metadata = directory.lstat()
        _require(
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == 0o700,
            "OUTPUT_DIRECTORY_INVALID",
        )
        with os.scandir(directory) as entries:
            children = sorted(
                (pathlib.Path(entry.path) for entry in entries),
                key=lambda path: path.name,
                reverse=True,
            )
        for path in children:
            child = path.lstat()
            _require(not stat.S_ISLNK(child.st_mode), "OUTPUT_SYMLINK_INVALID")
            if stat.S_ISDIR(child.st_mode):
                stack.append(path)
                continue
            _require(
                stat.S_ISREG(child.st_mode)
                and child.st_nlink == 1
                and stat.S_IMODE(child.st_mode) == 0o600,
                "OUTPUT_FILE_INVALID",
            )
            identity = (child.st_dev, child.st_ino)
            _require(identity not in identities, "OUTPUT_FILE_ALIAS_INVALID")
            identities.add(identity)
            raw = path.read_bytes()
            _require(
                len(raw) < 16_777_216,
                "OUTPUT_FILE_LIMIT",
            )
            records.append(
                (
                    path.relative_to(root).as_posix(),
                    stat.S_IMODE(child.st_mode),
                    len(raw),
                    _sha256(raw),
                )
            )
    return tuple(sorted(records))


def _file_closure(root):
    snapshot = _scan_tree(root)
    rows = [
        {
            "repository_relative_path": path,
            "raw_octets": octets,
            "raw_sha256": digest,
        }
        for path, _mode, octets, digest in snapshot
    ]
    total = 0
    for row in rows:
        total = _checked_add(total, row["raw_octets"], "CLOSURE_SIZE_OVERFLOW")
    return total, _sha256(_canonical_bytes(rows)), snapshot


def _load_output_json(path):
    raw = path.read_bytes()
    value = _strict_loads(raw)
    _require(raw == _pretty_bytes(value), "OUTPUT_JSON_ENCODING_INVALID")
    return value, raw


def _validate_resource_report(context, result, expected):
    schema = context["boundary"]["verifier_output_contract"][
        "proof_resource_report_schema"
    ]
    report = _closed(
        result["proof_resource_report"],
        schema["ordered_member_names"],
        "RESOURCE_REPORT_SCHEMA_INVALID",
    )
    _require(
        report["resource_report_version"] == schema["version_literal"],
        "RESOURCE_REPORT_VERSION_INVALID",
    )
    _require(
        report["maximum_protocol_sha256"]
        == context["effective"]["maximum_protocol_sha256"],
        "RESOURCE_PROTOCOL_INVALID",
    )
    _require(
        report["derivation_plan_id"] == expected["logical_count_plan_id"],
        "RESOURCE_PLAN_INVALID",
    )
    _require(
        report["resource_limit_catalog_id"]
        == context["effective"]["f2_resource_limit_catalog_id"],
        "RESOURCE_F2_CATALOG_INVALID",
    )
    measurements = report["ordered_resource_measurements"]
    _require(
        type(measurements) is list and len(measurements) == 18,
        "RESOURCE_VECTOR_INVALID",
    )
    values = []
    for measurement, limit in zip(measurements, context["f2_rows"], strict=True):
        _closed(
            measurement,
            ["metric_position", "metric_name", "measured_value"],
            "RESOURCE_MEASUREMENT_SCHEMA_INVALID",
        )
        value = _safe_integer(
            measurement["measured_value"], "RESOURCE_MEASUREMENT_INVALID"
        )
        _require(
            measurement["metric_position"] == limit["metric_position"]
            and measurement["metric_name"] == limit["metric_name"]
            and value <= limit["f2_per_case"],
            "RESOURCE_PER_CASE_LIMIT",
        )
        values.append(value)
    payload = {name: report[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        report["proof_resource_report_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "RESOURCE_REPORT_ID_INVALID",
    )
    return tuple(values)


def _validate_case(context, expected, case_root, candidate_before=None):
    _require(
        {path.name for path in case_root.iterdir()} == {"candidate", "verified"},
        "CASE_ROOT_CLOSURE_INVALID",
    )
    candidate_root = case_root / "candidate"
    verified_root = case_root / "verified"
    candidate_octets, candidate_digest, candidate_snapshot = _file_closure(
        candidate_root
    )
    if candidate_before is not None:
        _require(candidate_snapshot == candidate_before, "CANDIDATE_MUTATED")
    candidate, candidate_raw = _load_output_json(candidate_root / "candidate.json")
    candidate_schema = context["boundary"]["candidate_bundle_contract"][
        "candidate_envelope_schema"
    ]
    _closed(
        candidate,
        candidate_schema["ordered_member_names"],
        "CANDIDATE_SCHEMA_INVALID",
    )
    for name, value in (
        ("canonicalization_version", context["boundary"]["canonicalization_version"]),
        (
            "measurement_schema_version",
            context["boundary"]["measurement_schema_version"],
        ),
        ("protocol_version", context["boundary"]["protocol_version"]),
        ("seed_catalog_id", context["effective"]["successor_seed_catalog_id"]),
        ("finalization_manifest_id", context["effective"]["successor_manifest_id"]),
        ("case_position", expected["case_position"]),
        ("case_kind", expected["case_kind"]),
        ("logical_count_plan_id", expected["logical_count_plan_id"]),
    ):
        _require(candidate[name] == value, "CANDIDATE_BINDING_INVALID")
    _sha(candidate["constructive_candidate_id"], "CANDIDATE_ID_INVALID")

    output = context["boundary"]["verifier_output_contract"]
    paths = output["verified_bundle_paths"]
    maximum = expected["case_kind"] == "MAXIMUM_PUBLICATION_ROW"
    result_name = paths["maximum_result"] if maximum else paths["local_result"]
    _require(
        {path.name for path in verified_root.iterdir()}
        == {paths["receipt"], result_name, paths["context_root"]},
        "VERIFIED_ROOT_CLOSURE_INVALID",
    )
    verified_octets, verified_digest, _verified_snapshot = _file_closure(verified_root)
    result, result_raw = _load_output_json(verified_root / result_name)
    receipt, receipt_raw = _load_output_json(verified_root / paths["receipt"])
    if maximum:
        result_schema = output["maximum_attainer_schema"]
        result_id_name = "maximum_attainer_id"
        expected_status = output["verification_receipt_schema"]["maximum_status"]
    else:
        result_schema = output["local_shutdown_result_schema"]
        result_id_name = "local_shutdown_unrepresentable_id"
        expected_status = output["verification_receipt_schema"]["local_status"]
    _closed(result, result_schema["ordered_member_names"], "RESULT_SCHEMA_INVALID")
    _require(
        result["artifact_version"] == result_schema["version_literal"],
        "RESULT_VERSION_INVALID",
    )
    _require(
        result["maximum_protocol_sha256"]
        == context["effective"]["maximum_protocol_sha256"],
        "RESULT_PROTOCOL_INVALID",
    )
    result_payload = {
        name: result[name] for name in result_schema["ordered_member_names"][:-1]
    }
    result_id = _sha(result[result_id_name], "RESULT_ID_INVALID")
    _require(
        result_id == _semantic_id(result_schema["identity_domain"], result_payload),
        "RESULT_IDENTITY_INVALID",
    )
    measurements = _validate_resource_report(context, result, expected)

    receipt_schema = output["verification_receipt_schema"]
    _closed(
        receipt,
        receipt_schema["ordered_member_names"],
        "RECEIPT_SCHEMA_INVALID",
    )
    for name, value in (
        ("receipt_version", receipt_schema["version_literal"]),
        ("canonicalization_version", context["boundary"]["canonicalization_version"]),
        ("protocol_version", context["boundary"]["protocol_version"]),
        ("seed_catalog_id", context["effective"]["successor_seed_catalog_id"]),
        ("finalization_manifest_id", context["effective"]["successor_manifest_id"]),
        ("case_position", expected["case_position"]),
        ("case_kind", expected["case_kind"]),
        ("logical_count_plan_id", expected["logical_count_plan_id"]),
        ("constructive_candidate_id", candidate["constructive_candidate_id"]),
        ("candidate_raw_octets", len(candidate_raw)),
        ("candidate_raw_sha256", _sha256(candidate_raw)),
        ("verification_status", expected_status),
        ("result_artifact_id", result_id),
        ("result_repository_relative_path", result_name),
        ("result_raw_octets", len(result_raw)),
        ("result_raw_sha256", _sha256(result_raw)),
    ):
        _require(receipt[name] == value, "RECEIPT_BINDING_INVALID")
    receipt_payload = {
        name: receipt[name] for name in receipt_schema["ordered_member_names"][:-1]
    }
    receipt_id = _sha(receipt["verification_receipt_id"], "RECEIPT_ID_INVALID")
    _require(
        receipt_id == _semantic_id(receipt_schema["identity_domain"], receipt_payload),
        "RECEIPT_IDENTITY_INVALID",
    )
    return (
        {
            "pilot_position": expected["pilot_position"],
            "case_position": expected["case_position"],
            "case_kind": expected["case_kind"],
            "logical_count_plan_id": expected["logical_count_plan_id"],
            "constructive_candidate_id": candidate["constructive_candidate_id"],
            "candidate_root_raw_octets": candidate_octets,
            "candidate_root_sha256": candidate_digest,
            "verification_receipt_id": receipt_id,
            "verified_result_artifact_id": result_id,
            "verified_result_root_raw_octets": verified_octets,
            "verified_result_root_sha256": verified_digest,
        },
        measurements,
    )


def _execute_case(context, expected, pilot_position, case_root):
    _require(expected["pilot_position"] == pilot_position, "PILOT_POSITION_INVALID")
    os.mkdir(case_root, 0o700)
    candidate_root = case_root / "candidate"
    producer_arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(context["repository_root"] / PRODUCER_RELATIVE_PATH),
        "--repository-root",
        str(context["repository_root"]),
        "--boundary",
        str(context["boundary_path"]),
        "--case-position",
        str(expected["case_position"]),
        "--output-root",
        str(candidate_root),
    ]
    _run_child(
        context,
        f"PRODUCER_CASE_{expected['case_position']}",
        producer_arguments,
        case_root,
        case_root.parents[1],
    )
    _require(candidate_root.is_dir(), "PRODUCER_OUTPUT_ABSENT")
    _candidate_octets, _candidate_digest, candidate_before = _file_closure(
        candidate_root
    )
    _recheck_authorities(context)

    verified_root = case_root / "verified"
    verifier_arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(context["repository_root"] / VERIFIER_RELATIVE_PATH),
        "--repository-root",
        str(context["repository_root"]),
        "--boundary",
        str(context["boundary_path"]),
        "--candidate-root",
        str(candidate_root),
        "--output-root",
        str(verified_root),
    ]
    _run_child(
        context,
        f"VERIFIER_CASE_{expected['case_position']}",
        verifier_arguments,
        case_root,
        case_root.parents[1],
    )
    _require(verified_root.is_dir(), "VERIFIER_OUTPUT_ABSENT")
    entry, measurements = _validate_case(context, expected, case_root, candidate_before)
    _recheck_authorities(context)
    return entry, measurements


def _aggregate_f2(context, vectors):
    _require(len(vectors) == 6, "PILOT_RESOURCE_CASE_COUNT_INVALID")
    aggregate = [0] * 18
    for vector in vectors:
        _require(len(vector) == 18, "PILOT_RESOURCE_VECTOR_INVALID")
        for index, (value, limit) in enumerate(
            zip(vector, context["f2_rows"], strict=True)
        ):
            if limit["full_run_aggregation"] == "SUM":
                aggregate[index] = _checked_add(
                    aggregate[index], value, "PILOT_RESOURCE_SUM_OVERFLOW"
                )
            else:
                aggregate[index] = max(aggregate[index], value)
    for value, limit in zip(aggregate, context["f2_rows"], strict=True):
        _require(value <= limit["f2_full_run"], "PILOT_F2_FULL_RUN_LIMIT")
    return tuple(aggregate)


def _role_authority(context, role):
    row = context["role_rows"][role]
    raw = context["source_raw"][role]
    return {
        "repository_relative_path": row["repository_relative_path"],
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
        "source_marker": row["source_marker"],
    }


def _build_manifest(context, entries):
    pilot = context["boundary"]["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    value = {
        "pilot_version": pilot["pilot_version"],
        "canonicalization_version": context["boundary"]["canonicalization_version"],
        "protocol_version": context["boundary"]["protocol_version"],
        "seed_catalog_id": context["effective"]["successor_seed_catalog_id"],
        "finalization_manifest_id": context["effective"]["successor_manifest_id"],
        "producer_authority": _role_authority(context, "SEPARATE_PRODUCER"),
        "verifier_authority": _role_authority(context, "INDEPENDENT_VERIFIER"),
        "runner_authority": _role_authority(context, "PARENT_PILOT_RUNNER"),
        "ordered_case_result_entries": entries,
        "pilot_status": pilot["pilot_status"],
    }
    value["constructive_pilot_manifest_id"] = _semantic_id(
        schema["identity_domain"], value
    )
    return value


def _validate_manifest(context, root):
    pilot = context["boundary"]["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    _require(
        {path.name for path in root.iterdir()}
        == {"constructive_pilot_manifest.json", "cases"},
        "PILOT_ROOT_CLOSURE_INVALID",
    )
    value, raw = _load_output_json(root / "constructive_pilot_manifest.json")
    _closed(value, schema["ordered_member_names"], "PILOT_MANIFEST_SCHEMA_INVALID")
    for name, expected in (
        ("pilot_version", pilot["pilot_version"]),
        ("canonicalization_version", context["boundary"]["canonicalization_version"]),
        ("protocol_version", context["boundary"]["protocol_version"]),
        ("seed_catalog_id", context["effective"]["successor_seed_catalog_id"]),
        ("finalization_manifest_id", context["effective"]["successor_manifest_id"]),
        ("pilot_status", pilot["pilot_status"]),
    ):
        _require(value[name] == expected, "PILOT_MANIFEST_BINDING_INVALID")
    for member, role in (
        ("producer_authority", "SEPARATE_PRODUCER"),
        ("verifier_authority", "INDEPENDENT_VERIFIER"),
        ("runner_authority", "PARENT_PILOT_RUNNER"),
    ):
        _require(value[member] == _role_authority(context, role), "PILOT_ROLE_INVALID")
    expected_rows = context["target"]["ordered_pilot_case_records"]
    entries = value["ordered_case_result_entries"]
    _require(
        type(entries) is list and len(entries) == len(expected_rows) == 6,
        "PILOT_ENTRY_COUNT_INVALID",
    )
    cases_root = root / "cases"
    expected_names = {
        f"{row['pilot_position']:04d}-{row['case_position']:04d}"
        for row in expected_rows
    }
    _require(
        cases_root.is_dir()
        and {path.name for path in cases_root.iterdir()} == expected_names,
        "PILOT_CASE_DIRECTORY_INVALID",
    )
    vectors = []
    reconstructed = []
    for expected in expected_rows:
        case_root = (
            cases_root
            / f"{expected['pilot_position']:04d}-{expected['case_position']:04d}"
        )
        entry, vector = _validate_case(context, expected, case_root)
        reconstructed.append(entry)
        vectors.append(vector)
    _require(entries == reconstructed, "PILOT_ENTRY_RECONSTRUCTION_INVALID")
    _aggregate_f2(context, vectors)
    payload = {name: value[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        value["constructive_pilot_manifest_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "PILOT_MANIFEST_ID_INVALID",
    )
    _scan_tree(root)
    return raw


def _write_file(path, raw):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            _require(written > 0, "OUTPUT_WRITE_INVALID")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root):
    directories = [root]
    for path in root.rglob("*"):
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        elif path.is_dir():
            directories.append(path)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _validate_output_path(output_root, write):
    parent = output_root.parent
    _require(parent.is_dir() and not parent.is_symlink(), "OUTPUT_PARENT_INVALID")
    if write:
        _require(
            not output_root.exists() and not output_root.is_symlink(), "OUTPUT_EXISTS"
        )
    else:
        _require(
            output_root.is_dir() and not output_root.is_symlink(), "OUTPUT_MISSING"
        )


def _write_pilot(repository_root, boundary_path, output_root):
    repository_root = pathlib.Path(repository_root)
    boundary_path = pathlib.Path(boundary_path)
    output_root = pathlib.Path(output_root)
    _validate_output_path(output_root, True)
    context = _load_context(repository_root, boundary_path)
    parent = output_root.parent
    staging = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.private.", dir=parent)
    )
    published = False
    try:
        cases_root = staging / "cases"
        os.mkdir(cases_root, 0o700)
        entries = []
        vectors = []
        for expected in context["target"]["ordered_pilot_case_records"]:
            case_root = (
                cases_root
                / f"{expected['pilot_position']:04d}-{expected['case_position']:04d}"
            )
            entry, vector = _execute_case(
                context, expected, expected["pilot_position"], case_root
            )
            entries.append(entry)
            vectors.append(vector)
        _aggregate_f2(context, vectors)
        manifest = _build_manifest(context, entries)
        _write_file(
            staging / "constructive_pilot_manifest.json", _pretty_bytes(manifest)
        )
        _validate_manifest(context, staging)
        _recheck_authorities(context)
        _require(
            _allocated_octets(staging)
            <= context["limits"]["PUBLICATION_STAGING_STORAGE_OCTETS"],
            "PILOT_STAGING_STORAGE_LIMIT",
        )
        _fsync_tree(staging)
        _require(not output_root.exists(), "OUTPUT_COLLISION")
        os.rename(staging, output_root)
        published = True
        parent_descriptor = os.open(parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except BaseException:
        if published:
            _remove_tree(output_root)
        else:
            _remove_tree(staging)
        raise


def _check_pilot(repository_root, boundary_path, output_root):
    repository_root = pathlib.Path(repository_root)
    boundary_path = pathlib.Path(boundary_path)
    output_root = pathlib.Path(output_root)
    _validate_output_path(output_root, False)
    before = _scan_tree(output_root)
    context = _load_context(repository_root, boundary_path)
    _validate_manifest(context, output_root)
    _recheck_authorities(context)
    _require(_scan_tree(output_root) == before, "CHECK_MODE_MUTATED_OUTPUT")


def _arguments(arguments):
    _require_arguments = len(arguments) == 6
    if not _require_arguments:
        raise InvocationReject("EXPECTED_THREE_OPTION_VALUE_PAIRS")
    if arguments[0] != "--repository-root" or arguments[2] != "--boundary":
        raise InvocationReject("FIXED_ARGUMENT_ORDER_REQUIRED")
    if arguments[4] not in {"--write-output-root", "--check-output-root"}:
        raise InvocationReject("OUTPUT_MODE_INVALID")
    if any(arguments[index] == "" for index in (1, 3, 5)):
        raise InvocationReject("EMPTY_ARGUMENT_VALUE")
    repository_root = _canonical_absolute(arguments[1], "REPOSITORY_ROOT_INVALID")
    boundary_path = _canonical_absolute(arguments[3], "BOUNDARY_PATH_INVALID")
    output_root = _canonical_absolute(arguments[5], "OUTPUT_ROOT_INVALID")
    if boundary_path != repository_root / PACKED_BOUNDARY_RELATIVE_PATH:
        raise InvocationReject("PACKED_BOUNDARY_PATH_REQUIRED")
    if output_root in {repository_root, boundary_path}:
        raise InvocationReject("OUTPUT_ROOT_OVERLAP")
    return (
        "write" if arguments[4] == "--write-output-root" else "check",
        repository_root,
        boundary_path,
        output_root,
    )


def main(arguments=None):
    if arguments is None:
        arguments = sys.argv[1:]
    try:
        mode, repository_root, boundary_path, output_root = _arguments(arguments)
    except (InvocationReject, RunnerReject):
        sys.stderr.write(ERROR_PREFIX + "INVOCATION_INVALID: FIXED_CLI_REQUIRED\n")
        return 2
    try:
        if mode == "write":
            _write_pilot(repository_root, boundary_path, output_root)
        else:
            _check_pilot(repository_root, boundary_path, output_root)
    except RunnerReject as error:
        sys.stderr.write(ERROR_PREFIX + "REJECTED: " + str(error) + "\n")
        return 1
    except (OSError, ValueError, TypeError, MemoryError):
        sys.stderr.write(ERROR_PREFIX + "REJECTED: FAIL_CLOSED\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
