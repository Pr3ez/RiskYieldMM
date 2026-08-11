#!/usr/bin/env python3
"""Independent A4-P6-P separate-producer expansion acceptance review."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any

SOURCE_MARKER = "INDEPENDENT_V2_SEPARATE_PRODUCER_EXPANSION_REVIEWER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_ACCEPTANCE_"
REPORT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "separate_producer_expansion_acceptance_report.v1"
)
REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2SeparateProducerExpansionAcceptanceReportV1"
    "V4_9F_RawV8"
)
V_A_REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2IndependentVerifierAcceptanceReportV1V4_9F_RawV8"
)

PRODUCER = pathlib.Path(
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = pathlib.Path(
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
PREDECESSOR_BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
PACKED_BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
SUCCESSOR_TEST = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_separate_producer_expansion_v49f.py"
)
PREDECESSOR_TARGET = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "six_case_qualification_fail_first_v49f.py"
)
IMPLEMENTATION_TARGET = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py"
)
RUNNER = pathlib.Path(
    "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)
HISTORICAL_PRODUCER = pathlib.Path(
    "scripts/tests/Archive/a4_p_predecessor_accepted/"
    "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
HISTORICAL_V_A_TEST = pathlib.Path(
    "tests/Archive/a4_p6_v_a_historical/"
    "test_raw_v8_step2_maximum_protocol_v2_independent_verifier_acceptance_v49f.py"
)
V_A_REVIEWER = pathlib.Path(
    "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py"
)
V_A_REPORT = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_acceptance_report_v49f.json"
)

PILOT_CASES = (5, 24, 54, 69, 435, 475)
EXPECTED_STATIC_ARTIFACTS = {
    PRODUCER: (
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    VERIFIER: (
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    PREDECESSOR_BOUNDARY: (
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    PACKED_BOUNDARY: (
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    SUCCESSOR_TEST: (
        13_119,
        "592780dbb9b211d5b7976be4895e2eb0fc1a0686fa0d81730f9d12a06b2ed7c1",
    ),
    PREDECESSOR_TARGET: (
        60_279,
        "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886",
    ),
    IMPLEMENTATION_TARGET: (
        52_970,
        "10058dabf6b868969a5cad8387ecedbfa42a0e59f6e5a922adffd9cf99c24080",
    ),
    HISTORICAL_PRODUCER: (
        38_318,
        "9a0f2078419920dfaf89b3d2161381881abb07f375aaba94a960fc77576573ed",
    ),
    HISTORICAL_V_A_TEST: (
        9_703,
        "d167ce6c98a6d48960cccbb95b94fddb7f5991adf5481408f3ed125aff2c75c7",
    ),
    V_A_REVIEWER: (
        41_217,
        "d254c9c49c57e2a4207a73d22e2b3ad4a303534249eef4a2373b5c124c2028e9",
    ),
    V_A_REPORT: (
        22_564,
        "1adbc0b1ac3ca2e9c2ad805de6ba79f6ce1b8ea244d6a11e50c086f438c7c45c",
    ),
}
EXPECTED_V_A_REPORT_ID = (
    "1e20c2c1312abe6b3924c96e6979f046325a87d635f728007a157831381b1da1"
)
EXPECTED_LEGACY_CASE5 = {
    "candidate_raw_octets": 1_333,
    "candidate_raw_sha256": (
        "6dfba23c6d18e96eaf826de408f66d4c69980acbd604d3d7c66f29661f74f9f1"
    ),
    "constructive_candidate_id": (
        "048df6d26b0d60f217864c32a1b420a34b8427a513a120185de43d822e73b120"
    ),
}

EXPECTED_CASE_LEDGER = (
    (
        5,
        1_333,
        "9606a27fd1b779c21c04667f20a8dd52a426379a4ad8c31b1f59ae78d722d517",
        "4f6f00ed6ba71719c27eb863e213edeb85a1b1bf9145b525c2638ec389cfa57d",
        1,
        1_333,
        "6bd706c086731de2bec7700ec216a16cf25ce5de7f3768ca53a89bab6819a2eb",
        29,
        5_660,
        "97942eafc2ac7d649d6d0d6498c2a877f61d547fe22c4a75522afae689220c49",
        "f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f",
        "de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba",
        "375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee",
        2,
        7_320,
        "33d5a1fa35049029f2e7371686934e0697eab90c9d1ff7c8ab115379d6012973",
    ),
    (
        24,
        596_731,
        "51828c73e540bdb26dabfa3220e27b99ac670447ba2761d01022030982430f31",
        "2900a75c99c0ed863c6a1388738d9a189ec742043fb7fa2c377fa298455b8a2b",
        2,
        1_121_018,
        "a83f67ffa7e340a8c10a3aa8e6a80f6d221b113b4420fc9f0788d8bed70264f8",
        523_738,
        585_140,
        "f434cc488a4a23d905c44762d56080dcf5e57021f6edbc91f1504ab78ac9d6bb",
        "55b5ecc89c5954d891be187220d649a510a136957d1a1a2f41d98a4766d3555d",
        "65066d0c7c5b45400a79fbc7caae90c79f98a00ba3125f4f890482a127a23096",
        "940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107",
        3,
        1_111_623,
        "5f3d7f142e24e58458cbcead005ac337a7d3bfbbd625749db418ad7877631d31",
    ),
    (
        54,
        3_151_660,
        "88f4c978928823e43a67abed25b662a2253e4cb58075330b3523c79b79bb5b5f",
        "548f836d05e58a4e72e0ceade9f9adfe7ccc85b37cd0a396792ec4b74cca7e0e",
        1,
        3_151_660,
        "f272281d598fd74084a9555fc0c6590942a1dd5982a61567a346d91cfd316dee",
        3_145_728,
        3_155_205,
        "bbc4e8d5526f435df00c4a7b9d493fdde6d74100c20a114c9d0753f71b3e2259",
        "3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1",
        "2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81",
        "bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451",
        2,
        3_156_884,
        "0664ec60e225311523ed699cfb8f843e5bc57a04cbce1e49b9610b7c904ada00",
    ),
    (
        69,
        6_136,
        "3829745d1b0eba5829bf5ca3b6d672ff6d5032d04feb75d96be7d4e3982bafcc",
        "26e51a3d75848c07854a37ca8cf2ea065e6863e9a1ef80bc764528ab6b436149",
        1,
        6_136,
        "1983a65e1b16a092d414fa76946c75b514bbb299c7e4e0f0d061a931b0daf51b",
        2_581,
        10_312,
        "94bfea5cbb351797cb546c97ab72c0931cd1d7be2af76694e20f226c9889d895",
        "1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e",
        "fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e",
        "48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740",
        2,
        12_062,
        "d061629cd8a129e171885ff9ca6db684e665eac1ce50c6453b5139ff928a624d",
    ),
    (
        435,
        385_701,
        "3ddf81163d609d2e5e2a87055073c23510162b2b7032f5f013e0fae5165ad289",
        "3733dcc3ee96435a25e4b432434da6f0e9918f7a72d771625bc31fccbd1ba36a",
        2,
        13_031_318,
        "5eb8d37a0b72741287d7da81b2344f5cbbdf762d57c1f6854780acbd33069c09",
        257_887,
        382_271,
        "90d09148cbbbaef3e7b22530d4fbcf9086d1c74dd5c96470ef5b40d2a3a98d1f",
        "0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f",
        "fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd",
        "3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9",
        69,
        13_030_595,
        "a173607e699b6fff6dc8eff49010e968eec3f1c0452bfb6563dd566bcc79e9da",
    ),
    (
        475,
        614_566,
        "bdf7f8e4213cbf51b70b2dac0bdc97ffd1d55304b37bd3d20b8b9d54ba7977dc",
        "ee38407312f872f0d8dc3f5d6b3ebe9990f294ce245b406ba3e33cce243dcb42",
        1,
        614_566,
        "764110b4a9703da76c8e6daa1cee27693607782db5e5ddaf7bd3f11609009e9d",
        524_380,
        604_156,
        "a1e1316c970e60db198d8775eeb89a1e0eb7e4cdda5ddca64f54c666130fb7f8",
        "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73",
        "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f",
        "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8",
        2,
        607_329,
        "56537793b3c33bf6ce67dbeac9315245f0ef94dec783da3b02e945fd66c03554",
    ),
)

EXPECTED_RESOURCES = {
    5: [1, 3, 4, 8, 8, 0, 4, 2684, 8104, 10384, 33573, 0, 0, 0, 3, 3, 3783, 1359],
    24: [
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
    54: [1, 515, 5, 9, 1031, 1, 5, 3415, 9775, 12712, 41372, 1, 0, 0, 4, 9, 3937, 1589],
    69: [
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
    435: [
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
    475: [
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
}


class ReviewFailure(Exception):
    """A fixed acceptance condition failed."""


def _reject(code: str, message: str) -> None:
    raise ReviewFailure(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _reject(code, message)


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


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _require(name not in result, "JSON_INVALID", f"duplicate member: {name}")
        result[name] = value
    return result


def _strict_loads(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_float=lambda value: _reject("JSON_INVALID", value),
            parse_constant=lambda value: _reject("JSON_INVALID", value),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReviewFailure(f"JSON_INVALID: {error}") from error
    _require(type(value) is dict, "JSON_INVALID", "root is not an object")
    _require(
        _canonical_bytes(value)
        == _canonical_bytes(json.loads(_canonical_bytes(value))),
        "JSON_INVALID",
        "canonical round trip failed",
    )
    return value


def _read_regular(root: pathlib.Path, relative: pathlib.Path) -> bytes:
    path = root / relative
    _require(path.is_file() and not path.is_symlink(), "FILE_INVALID", str(relative))
    metadata = path.stat()
    _require(stat.S_ISREG(metadata.st_mode), "FILE_INVALID", str(relative))
    _require(metadata.st_nlink == 1, "FILE_INVALID", f"aliased: {relative}")
    return path.read_bytes()


def _descriptor(root: pathlib.Path, relative: pathlib.Path) -> dict[str, Any]:
    raw = _read_regular(root, relative)
    return {
        "repository_relative_path": relative.as_posix(),
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }


def _validate_static_artifacts(root: pathlib.Path) -> None:
    for path, (octets, digest) in EXPECTED_STATIC_ARTIFACTS.items():
        descriptor = _descriptor(root, path)
        _require(descriptor["raw_octets"] == octets, "ARTIFACT_DRIFT", f"size: {path}")
        _require(descriptor["raw_sha256"] == digest, "ARTIFACT_DRIFT", f"hash: {path}")
    _require(not (root / RUNNER).exists(), "RUNNER_RELEASED", str(RUNNER))


def _validate_historical_checkpoint(root: pathlib.Path) -> dict[str, Any]:
    report_raw = _read_regular(root, V_A_REPORT)
    report = _strict_loads(report_raw)
    payload = {
        name: value
        for name, value in report.items()
        if name != "independent_verifier_acceptance_report_id"
    }
    report_id = _sha256(
        _canonical_bytes({"domain": V_A_REPORT_DOMAIN, "payload": payload})
    )
    _require(
        report_id
        == report.get("independent_verifier_acceptance_report_id")
        == EXPECTED_V_A_REPORT_ID,
        "HISTORICAL_CHECKPOINT_INVALID",
        "V-A report identity",
    )
    _require(
        report.get("review_decision") == "ACCEPTED"
        and report.get("next_subgate") == "A4-P6-P",
        "HISTORICAL_CHECKPOINT_INVALID",
        "V-A state",
    )
    return {
        "a4_p_predecessor_producer": _descriptor(root, HISTORICAL_PRODUCER),
        "a4_p6_v_a_historical_test": _descriptor(root, HISTORICAL_V_A_TEST),
        "a4_p6_v_a_report_id": report_id,
        "a4_p6_v_a_report": _descriptor(root, V_A_REPORT),
        "a4_p6_v_a_reviewer": _descriptor(root, V_A_REVIEWER),
    }


def _validate_source_isolation(root: pathlib.Path) -> dict[str, Any]:
    source = _read_regular(root, PRODUCER).decode("utf-8", errors="strict")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            _require(
                node.level == 0 and node.module is not None,
                "SOURCE_ISOLATION_INVALID",
                "relative import",
            )
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
    allowed = {
        "__future__",
        "hashlib",
        "itertools",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "typing",
    }
    _require(
        imports <= allowed,
        "SOURCE_ISOLATION_INVALID",
        f"imports: {sorted(imports - allowed)}",
    )
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "execve",
        "fork",
        "popen",
        "system",
    }
    _require(
        calls.isdisjoint(forbidden_calls),
        "SOURCE_ISOLATION_INVALID",
        "dynamic or child execution",
    )
    for forbidden in (
        "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1",
        "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1",
        "construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py",
        "check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py",
        "join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py",
    ):
        _require(forbidden not in source, "SOURCE_ISOLATION_INVALID", forbidden)
    for answer in (
        tuple(row[9] for row in EXPECTED_CASE_LEDGER)
        + tuple(row[10] for row in EXPECTED_CASE_LEDGER)
        + tuple(row[11] for row in EXPECTED_CASE_LEDGER)
        + tuple(row[12] for row in EXPECTED_CASE_LEDGER)
    ):
        _require(
            answer not in source,
            "SOURCE_ISOLATION_INVALID",
            "accepted verifier answer literal",
        )
    _require(
        "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1" in strings,
        "SOURCE_ISOLATION_INVALID",
        "source marker",
    )
    return {
        "allowed_imports": sorted(imports),
        "dynamic_code_loading": False,
        "reviewed_role_imports": False,
        "accepted_verifier_answer_literals": False,
    }


def _environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run(
    command: list[str], root: pathlib.Path, timeout: int = 1_800
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=timeout,
    )


def _run_role(root: pathlib.Path, role: pathlib.Path, arguments: list[str]) -> None:
    completed = _run(
        [sys.executable, "-I", "-S", "-B", str(root / role), *arguments], root
    )
    _require(
        completed.returncode == 0 and completed.stdout == completed.stderr == b"",
        "ROLE_REPLAY_FAILED",
        completed.stderr.decode("utf-8", errors="replace"),
    )


def _snapshot(root: pathlib.Path) -> tuple[tuple[str, int, int, str], ...]:
    rows: list[tuple[str, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        _require(not stat.S_ISLNK(metadata.st_mode), "OUTPUT_INVALID", "symlink")
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            raw = path.read_bytes()
            _require(
                stat.S_IMODE(metadata.st_mode) == 0o600 and metadata.st_nlink == 1,
                "OUTPUT_INVALID",
                relative,
            )
            rows.append(
                (relative, stat.S_IMODE(metadata.st_mode), len(raw), _sha256(raw))
            )
        else:
            _require(
                path.is_dir() and stat.S_IMODE(metadata.st_mode) == 0o700,
                "OUTPUT_INVALID",
                relative,
            )
            rows.append((relative + "/", stat.S_IMODE(metadata.st_mode), 0, ""))
    return tuple(rows)


def _file_closure(root: pathlib.Path) -> dict[str, Any]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        raw = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "mode": stat.S_IMODE(path.stat().st_mode),
                "raw_octets": len(raw),
                "raw_sha256": _sha256(raw),
            }
        )
    return {
        "file_count": len(rows),
        "total_raw_octets": sum(row["raw_octets"] for row in rows),
        "ordered_file_records_sha256": _sha256(_canonical_bytes(rows)),
    }


def _contains_member(value: Any, member: str) -> bool:
    if type(value) is dict:
        return member in value or any(
            _contains_member(child, member) for child in value.values()
        )
    if type(value) is list:
        return any(_contains_member(child, member) for child in value)
    return False


def _case_record(
    root: pathlib.Path, base: pathlib.Path, case_position: int
) -> dict[str, Any]:
    base.mkdir(mode=0o700)
    candidate_root = base / "candidate"
    verified_root = base / "verified"
    _run_role(
        root,
        PRODUCER,
        [
            "--repository-root",
            str(root),
            "--boundary",
            str(root / PACKED_BOUNDARY),
            "--case-position",
            str(case_position),
            "--output-root",
            str(candidate_root),
        ],
    )
    candidate_snapshot = _snapshot(candidate_root)
    candidate_raw = (candidate_root / "candidate.json").read_bytes()
    candidate = _strict_loads(candidate_raw)
    boundary = _strict_loads(_read_regular(root, PREDECESSOR_BOUNDARY))
    for forbidden in boundary["candidate_bundle_contract"][
        "forbidden_producer_claim_member_names"
    ]:
        _require(
            not _contains_member(candidate, forbidden), "CANDIDATE_INVALID", forbidden
        )
    _run_role(
        root,
        VERIFIER,
        [
            "--repository-root",
            str(root),
            "--boundary",
            str(root / PACKED_BOUNDARY),
            "--candidate-root",
            str(candidate_root),
            "--output-root",
            str(verified_root),
        ],
    )
    _require(
        _snapshot(candidate_root) == candidate_snapshot,
        "CANDIDATE_MUTATED",
        str(case_position),
    )
    result_name = (
        "local_shutdown_unrepresentable.json"
        if case_position == 475
        else "maximum_attainer.json"
    )
    result_raw = (verified_root / result_name).read_bytes()
    result = _strict_loads(result_raw)
    receipt = _strict_loads((verified_root / "verification_receipt.json").read_bytes())
    resource = result["proof_resource_report"]
    maximum_octets = (
        result["prospective_result_canonical_byte_length"]
        if case_position == 475
        else result["canonical_byte_length"]
    )
    candidate_closure = _file_closure(candidate_root)
    verified_closure = _file_closure(verified_root)
    return {
        "case_position": case_position,
        "candidate_raw_octets": len(candidate_raw),
        "candidate_raw_sha256": _sha256(candidate_raw),
        "constructive_candidate_id": candidate["constructive_candidate_id"],
        "candidate_closure": candidate_closure,
        "maximum_octets": maximum_octets,
        "result_raw_octets": len(result_raw),
        "result_raw_sha256": _sha256(result_raw),
        "result_artifact_id": receipt["result_artifact_id"],
        "verification_receipt_id": receipt["verification_receipt_id"],
        "proof_resource_report_id": resource["proof_resource_report_id"],
        "resource_vector": [
            row["measured_value"] for row in resource["ordered_resource_measurements"]
        ],
        "verified_closure": verified_closure,
    }


def _expected_case_records() -> list[dict[str, Any]]:
    records = []
    for row in EXPECTED_CASE_LEDGER:
        (
            case,
            candidate_octets,
            candidate_sha,
            candidate_id,
            candidate_files,
            candidate_total,
            candidate_closure_sha,
            maximum_octets,
            result_octets,
            result_sha,
            result_id,
            receipt_id,
            resource_id,
            verified_files,
            verified_total,
            verified_closure_sha,
        ) = row
        records.append(
            {
                "case_position": case,
                "candidate_raw_octets": candidate_octets,
                "candidate_raw_sha256": candidate_sha,
                "constructive_candidate_id": candidate_id,
                "candidate_closure": {
                    "file_count": candidate_files,
                    "total_raw_octets": candidate_total,
                    "ordered_file_records_sha256": candidate_closure_sha,
                },
                "maximum_octets": maximum_octets,
                "result_raw_octets": result_octets,
                "result_raw_sha256": result_sha,
                "result_artifact_id": result_id,
                "verification_receipt_id": receipt_id,
                "proof_resource_report_id": resource_id,
                "resource_vector": EXPECTED_RESOURCES[case],
                "verified_closure": {
                    "file_count": verified_files,
                    "total_raw_octets": verified_total,
                    "ordered_file_records_sha256": verified_closure_sha,
                },
            }
        )
    return records


def _direct_replay(root: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = _expected_case_records()
    first: list[dict[str, Any]] = []
    second: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temporary:
        base = pathlib.Path(temporary)
        legacy_root = base / "legacy"
        _run_role(
            root,
            PRODUCER,
            [
                "--repository-root",
                str(root),
                "--boundary",
                str(root / PREDECESSOR_BOUNDARY),
                "--case-position",
                "5",
                "--output-root",
                str(legacy_root),
            ],
        )
        legacy_raw = (legacy_root / "candidate.json").read_bytes()
        legacy = _strict_loads(legacy_raw)
        legacy_record = {
            "candidate_raw_octets": len(legacy_raw),
            "candidate_raw_sha256": _sha256(legacy_raw),
            "constructive_candidate_id": legacy["constructive_candidate_id"],
        }
        _require(
            legacy_record == EXPECTED_LEGACY_CASE5, "PREDECESSOR_REGRESSION", "case 5"
        )
        for pass_index, destination in ((1, first), (2, second)):
            for case_position in PILOT_CASES:
                destination.append(
                    _case_record(
                        root,
                        base / f"pass-{pass_index}-case-{case_position}",
                        case_position,
                    )
                )
    _require(first == second == expected, "CASE_LEDGER_DRIFT", "two-pass ledger")
    return legacy_record, first


def _parse_green(
    completed: subprocess.CompletedProcess[bytes], expected_passed: int
) -> dict[str, int]:
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    _require(completed.returncode == 0, "QUALIFICATION_FAILED", output)
    match = re.search(rf"\b{expected_passed} passed\b", output)
    _require(
        match is not None and " failed" not in output, "QUALIFICATION_FAILED", output
    )
    return {"passed": expected_passed, "failed": 0, "skipped": 0}


def _parse_expected_red(
    completed: subprocess.CompletedProcess[bytes],
    *,
    passed: int,
    skipped: int,
    failures: tuple[str, ...],
) -> dict[str, Any]:
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    _require(completed.returncode == 1, "EXPECTED_RED_DRIFT", output)
    summary = re.search(r"(\d+) failed, (\d+) passed, (\d+) skipped", output)
    _require(
        summary is not None
        and tuple(map(int, summary.groups())) == (len(failures), passed, skipped),
        "EXPECTED_RED_DRIFT",
        output,
    )
    observed = sorted(set(re.findall(r"A4_(?:P6_)?[A-Z0-9_]+", output)))
    _require(observed == sorted(set(failures)), "EXPECTED_RED_DRIFT", repr(observed))
    return {
        "passed": passed,
        "failed": len(failures),
        "skipped": skipped,
        "ordered_failure_codes": list(failures),
    }


def _runtime_evidence(
    root: pathlib.Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    legacy, cases = _direct_replay(root)
    qualification = _parse_green(
        _run([sys.executable, "-m", "pytest", "-q", str(SUCCESSOR_TEST)], root), 17
    )
    a4_t = _parse_expected_red(
        _run([sys.executable, "-m", "pytest", "-q", str(IMPLEMENTATION_TARGET)], root),
        passed=61,
        skipped=2,
        failures=("A4_T_PARENT_PILOT_RUNNER_MISSING",),
    )
    a4_p6 = _parse_expected_red(
        _run([sys.executable, "-m", "pytest", "-q", str(PREDECESSOR_TARGET)], root),
        passed=13,
        skipped=2,
        failures=(
            "A4_P6_CASE_24_PRODUCER_NOT_QUALIFIED",
            "A4_P6_CASE_54_PRODUCER_NOT_QUALIFIED",
            "A4_P6_CASE_69_PRODUCER_NOT_QUALIFIED",
            "A4_P6_CASE_435_PRODUCER_NOT_QUALIFIED",
            "A4_P6_CASE_475_PRODUCER_NOT_QUALIFIED",
            "A4_P6_PARENT_RUNNER_MISSING",
        ),
    )
    return (
        legacy,
        cases,
        {
            "direct_packed_successor_replay": {
                "case_count": 6,
                "producer_runs": 12,
                "verifier_runs": 12,
                "candidate_immutability": "VERIFIED",
                "byte_determinism": "VERIFIED",
            },
            "successor_qualification": qualification,
            "a4_t_expected_red": a4_t,
            "a4_p6_predecessor_expected_red": a4_p6,
        },
    )


def _seal_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = dict(payload)
    report["separate_producer_acceptance_report_id"] = _sha256(
        _canonical_bytes({"domain": REPORT_DOMAIN, "payload": payload})
    )
    return report


def _validate_report_identity(report: dict[str, Any]) -> None:
    payload = {
        name: value
        for name, value in report.items()
        if name != "separate_producer_acceptance_report_id"
    }
    expected = _sha256(_canonical_bytes({"domain": REPORT_DOMAIN, "payload": payload}))
    _require(
        report.get("separate_producer_acceptance_report_id") == expected,
        "REPORT_IDENTITY_INVALID",
        "semantic ID",
    )


def build_report(root: pathlib.Path, *, execute_runtime: bool) -> dict[str, Any]:
    root = root.resolve()
    _validate_static_artifacts(root)
    historical = _validate_historical_checkpoint(root)
    isolation = _validate_source_isolation(root)
    if execute_runtime:
        legacy, cases, runtime = _runtime_evidence(root)
        decision = "ACCEPTED"
        next_subgate = "A4-P6-R"
    else:
        legacy = None
        cases = _expected_case_records()
        runtime = None
        decision = "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
        next_subgate = "A4-P6-P"
    payload = {
        "acceptance_report_version": REPORT_VERSION,
        "source_marker": SOURCE_MARKER,
        "correction_subgate": "A4-P6-P",
        "review_decision": decision,
        "formal_stage1_state": "NO-GO",
        "next_subgate": next_subgate,
        "parent_runner_state": "ABSENT_AND_HELD",
        "producer_source": _descriptor(root, PRODUCER),
        "verifier_source": _descriptor(root, VERIFIER),
        "qualification_test_source": _descriptor(root, SUCCESSOR_TEST),
        "historical_checkpoint": historical,
        "static_isolation": isolation,
        "predecessor_case5_compatibility": legacy,
        "ordered_case_acceptance_records": cases,
        "runtime_evidence": runtime,
    }
    return _seal_report(payload)


def _publish(path: pathlib.Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=pathlib.Path, required=True)
    parser.add_argument("--report-out", type=pathlib.Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = build_report(arguments.repository_root, execute_runtime=True)
        _validate_report_identity(report)
        _publish(
            arguments.report_out,
            (
                json.dumps(
                    report,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        )
    except (
        ReviewFailure,
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        sys.stderr.write(f"{ERROR_PREFIX}INVALID: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
