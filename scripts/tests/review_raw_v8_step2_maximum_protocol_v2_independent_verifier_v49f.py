#!/usr/bin/env python3
"""Independent V0-V4 verifier acceptance review.

This process never imports the verifier, producer, or their pytest fixtures.
It reconstructs the pinned authority and F0/F2 ledgers, audits source
isolation, then executes the exact immutable verifier and expected-red suites
as child processes.  The resulting report excludes timing and other ambient
data so identical accepted bytes produce an identical report.
"""

from __future__ import annotations

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

SOURCE_MARKER = "INDEPENDENT_V0_V4_VERIFIER_ACCEPTANCE_REVIEWER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_ACCEPTANCE_"
REPORT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "independent_verifier_acceptance_report.v1"
)
REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2IndependentVerifierAcceptanceReportV1V4_9F_RawV8"
)

VERIFIER = pathlib.Path(
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
CONTROL = pathlib.Path("docs/research/stage1_execution_control_2026-08-08.md")
BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SEED = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
SUCCESSOR_BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SEED_DELTA = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
MANIFEST_DELTA = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
TARGET_DELTA = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
PACKED_BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
PREDECESSOR_TARGET = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "six_case_qualification_fail_first_v49f.py"
)
IMPLEMENTATION_TARGET = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py"
)
TYPED_RUNTIME = pathlib.Path(
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
PRODUCER = pathlib.Path(
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
RUNNER = pathlib.Path(
    "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)

PINNED_FIXED_ARTIFACTS = {
    VERIFIER: (
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    BOUNDARY: (
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    SEED: (
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    MANIFEST: (
        15_560,
        "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0",
    ),
    SUCCESSOR_BOUNDARY: (
        4_806,
        "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c",
    ),
    SEED_DELTA: (
        22_976,
        "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da",
    ),
    MANIFEST_DELTA: (
        2_192,
        "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf",
    ),
    TARGET_DELTA: (
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    PACKED_BOUNDARY: (
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    PREDECESSOR_TARGET: (
        60_279,
        "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886",
    ),
    IMPLEMENTATION_TARGET: (
        52_970,
        "10058dabf6b868969a5cad8387ecedbfa42a0e59f6e5a922adffd9cf99c24080",
    ),
    TYPED_RUNTIME: (
        249_268,
        "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    ),
    PRODUCER: (
        38_318,
        "9a0f2078419920dfaf89b3d2161381881abb07f375aaba94a960fc77576573ed",
    ),
}

PINNED_REPLAY_TESTS = (
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py"
        ),
        13_851,
        "c8b2c3380701b362251af1e4f6d331d9421ac64c6fe4fe635c7e719be6ac0bbe",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "independent_verifier_expansion_v49f.py"
        ),
        13_463,
        "49d116d91f78fb65c4b7449adc00075565b5824ea761b77f04dce06309045511",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "independent_verifier_expansion_v1_v49f.py"
        ),
        25_633,
        "94d25b649310d4eef96f76e125e468e4028fc334b445fcc6bb47970d8c3b9bff",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "v1_runtime_differential_v49f.py"
        ),
        4_357,
        "44a8935a1760cb3eb5ca0697c2642e011b66f986bcb6b321d3e4b91102c6deb1",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "independent_verifier_expansion_v2_v49f.py"
        ),
        26_421,
        "80d29d39a777c653240c34a0f078ac02a919f6798e3b149e86057fb8e24f7bb5",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "v2_runtime_differential_v49f.py"
        ),
        4_737,
        "520c81cd76d074cfd40298483553d78566abf9da247192db54014f761e8baff9",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "case435_context_pack_boundary_v49f.py"
        ),
        9_658,
        "a81db42f06bb592d47b67513a8bf9b8e99cddb00cc90ead7d7cabe398d46daf4",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "independent_verifier_expansion_v3_v49f.py"
        ),
        39_302,
        "cbadeab9b6c7404d1330858b8deff009f1ab8e67c610818b12f7ebc1ed91ffc7",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "v3_runtime_differential_v49f.py"
        ),
        14_726,
        "dda0f1c5b7ae1fa3dc698679b976952a70627884d245b87bf0bc8d8dc04f89d3",
    ),
    (
        pathlib.Path(
            "tests/test_raw_v8_step2_maximum_protocol_v2_"
            "independent_verifier_expansion_v4_v49f.py"
        ),
        24_380,
        "fe5721c92b73b4fd357a0be453581cfbe7a305722c840493d7540ae3f289941b",
    ),
)

EXPECTED_REPLAY_PASSED = 128
EXPECTED_AUTHORITY_FILE_COUNT = 39
EXPECTED_AUTHORITY_OCTETS = 29_004_595
F0_FILE_COUNT_LIMIT = 64
F0_TOTAL_OCTETS_LIMIT = 67_108_864
F0_INDIVIDUAL_FILE_STRICT_UPPER = 16_777_216

PREDECESSOR_SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
PREDECESSOR_MANIFEST_ID = (
    "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
)
SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"

CASE_LEDGER = (
    {
        "authority_mode": "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "case_position": 5,
        "maximum_octets": 29,
        "logical_count_plan_id": (
            "d8149e3965dbdb9ed708860af0599463eafcfe2d428404ec7dea9aa20873cbe0"
        ),
        "stream_sha256": (
            "79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314"
        ),
        "resource_vector": [
            1,
            3,
            4,
            8,
            8,
            0,
            4,
            2_684,
            8_104,
            10_384,
            33_573,
            0,
            0,
            0,
            3,
            3,
            3_783,
            1_359,
        ],
        "upper_bound_certificate_id": (
            "a5bc2c237e25cc76a92aa5ec50e2d73ff9a428e5e97ee14adf69b6045219be59"
        ),
        "proof_resource_report_id": (
            "e0bcabae55dba9f0b1e14b370c31aeb8ea93124a4ac2b2ac7754d4e1cbcbee37"
        ),
        "result_artifact_id": (
            "ae6b76bc72b20531f8e72b5ccc40ef9450329d5d0165698a7230a982f5725272"
        ),
        "verification_receipt_id": (
            "2b270c5b6f5df06cd5b3c781642d4a8878d62be6e5014db95d1eaa72970150fd"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        "case_position": 5,
        "maximum_octets": 29,
        "logical_count_plan_id": (
            "d8149e3965dbdb9ed708860af0599463eafcfe2d428404ec7dea9aa20873cbe0"
        ),
        "stream_sha256": (
            "79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314"
        ),
        "resource_vector": [
            1,
            3,
            4,
            8,
            8,
            0,
            4,
            2_684,
            8_104,
            10_384,
            33_573,
            0,
            0,
            0,
            3,
            3,
            3_783,
            1_359,
        ],
        "upper_bound_certificate_id": (
            "4b9d3463c5e25bfabbb78e53548d4adf924725167c940c3859d5b5e521070f36"
        ),
        "proof_resource_report_id": (
            "375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee"
        ),
        "result_artifact_id": (
            "f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f"
        ),
        "verification_receipt_id": (
            "de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        "case_position": 24,
        "maximum_octets": 523_738,
        "logical_count_plan_id": (
            "428ff735837b841e66103d64cbcd4af7ceaf88d009c38229ad5e4cde0ab30d67"
        ),
        "stream_sha256": (
            "bf6a4886b3bc7110a61a5170e2b03f5de402a08e5bd78eccafb54b719d99cbcd"
        ),
        "resource_vector": [
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
        ],
        "upper_bound_certificate_id": (
            "29b129af22320a61e33c4576d5eb81d0baa90c3c9f49b1d5309b955ccd242950"
        ),
        "proof_resource_report_id": (
            "940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107"
        ),
        "result_artifact_id": (
            "2c9054a363632a7f0da2dace72677155df9bbf2f4527bc5ff3ab952f96d32876"
        ),
        "verification_receipt_id": (
            "46d69394ea4b0a1ef555b9cd0e097fe5827b67b9a64aa573595adba29e45510d"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        "case_position": 54,
        "maximum_octets": 3_145_728,
        "logical_count_plan_id": (
            "4eeedde2c223693e62a2b89a2016b43f9954496771189616ad68ac8cf21e6da1"
        ),
        "stream_sha256": (
            "9a9b153f3fee7073849416c8ccc3f419bda471b1c541165b20f49989cb6b379f"
        ),
        "resource_vector": [
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
        ],
        "upper_bound_certificate_id": (
            "ff0d46f36841897477570ce066d5f1a5ee0fce3208d906ac9e60708e0a80e521"
        ),
        "proof_resource_report_id": (
            "bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451"
        ),
        "result_artifact_id": (
            "3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1"
        ),
        "verification_receipt_id": (
            "2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        "case_position": 69,
        "maximum_octets": 2_581,
        "logical_count_plan_id": (
            "b991ffb7f0ea927d854228bcc52524e39fee7e88080d9171753b03cc59589fcb"
        ),
        "stream_sha256": (
            "7965e977eca8aa43ce84c97391a1ae4c51dfd2f79fa20e80ea7b6110ea5c808f"
        ),
        "resource_vector": [
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
        ],
        "upper_bound_certificate_id": (
            "12f0e8d7559859a815671dd10e0d26d398b2531eef5bb14ef939bb9acc9fc5c9"
        ),
        "proof_resource_report_id": (
            "48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740"
        ),
        "result_artifact_id": (
            "1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e"
        ),
        "verification_receipt_id": (
            "fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        "case_position": 435,
        "maximum_octets": 257_887,
        "logical_count_plan_id": (
            "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
        ),
        "stream_sha256": (
            "b35d70426261fc07da100f3d0f9486ccdd03a21e1699ab2008f97d58ecc3fc83"
        ),
        "resource_vector": [
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
        ],
        "upper_bound_certificate_id": (
            "7a36dcb15bd3fae4125c51b88010793fa63f7a2c5f03421b343eea0cd9aa0c25"
        ),
        "proof_resource_report_id": (
            "3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9"
        ),
        "result_artifact_id": (
            "0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f"
        ),
        "verification_receipt_id": (
            "fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd"
        ),
    },
    {
        "authority_mode": "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        "case_position": 475,
        "maximum_octets": 524_380,
        "predecessor_maximum_octets": 524_112,
        "logical_count_plan_id": (
            "2d46a1b71c9466fd3268b93dbc3e4a62a4855dd0324f4cfecfbb60d4589bbbc0"
        ),
        "stream_sha256": (
            "5f2f61d0f9f09174d3bb17288c02f36d9ec7ec358468d36ed19a2e44958cbbb3"
        ),
        "resource_vector": [
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
        ],
        "upper_bound_certificate_id": (
            "bc4594ce40f5ba4d80276ae1eec89c34f2e9eaff8328834093fa1e2cfa4dd118"
        ),
        "minimality_certificate_id": (
            "62c6c97f9af5a8f4924f45a4c4e2d144d93eb17cd84d5b17b0cd06af6eb15792"
        ),
        "proof_resource_report_id": (
            "ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8"
        ),
        "result_artifact_id": (
            "937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73"
        ),
        "verification_receipt_id": (
            "eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f"
        ),
    },
)

EXPECTED_A4_T_FAILURES = ("A4_T_PARENT_PILOT_RUNNER_MISSING",)
EXPECTED_A4_P6_FAILURES = (
    "A4_P6_CASE_24_PRODUCER_NOT_QUALIFIED",
    "A4_P6_CASE_54_PRODUCER_NOT_QUALIFIED",
    "A4_P6_CASE_69_PRODUCER_NOT_QUALIFIED",
    "A4_P6_CASE_435_PRODUCER_NOT_QUALIFIED",
    "A4_P6_CASE_475_PRODUCER_NOT_QUALIFIED",
    "A4_P6_PARENT_RUNNER_MISSING",
)


class ReviewFailure(RuntimeError):
    """A fail-closed V-A review result."""


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


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            _reject("JSON_INVALID", f"duplicate member {name!r}")
        result[name] = value
    return result


def _reject_float(value: str) -> Any:
    _reject("JSON_INVALID", f"floating-point token is forbidden: {value}")


def _reject_constant(value: str) -> Any:
    _reject("JSON_INVALID", f"non-finite token is forbidden: {value}")


def _strict_loads(raw: bytes) -> Any:
    _require(not raw.startswith(b"\xef\xbb\xbf"), "JSON_INVALID", "BOM is forbidden")
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _reject("JSON_INVALID", str(exc))


def _relative_path(value: pathlib.Path | str) -> pathlib.Path:
    relative = pathlib.Path(value)
    _require(
        not relative.is_absolute()
        and relative.parts
        and all(part not in {"", ".", ".."} for part in relative.parts),
        "PATH_INVALID",
        f"non-lexical repository-relative path: {value}",
    )
    return relative


def _read_regular(
    root: pathlib.Path,
    relative_value: pathlib.Path | str,
    *,
    limit: int = F0_INDIVIDUAL_FILE_STRICT_UPPER,
) -> tuple[bytes, dict[str, Any]]:
    relative = _relative_path(relative_value)
    current = root
    for part in relative.parts:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            _reject("FILE_INVALID", f"cannot stat {relative}: {exc}")
        _require(
            not stat.S_ISLNK(info.st_mode),
            "FILE_INVALID",
            f"symlink is forbidden: {relative}",
        )
    _require(
        stat.S_ISREG(info.st_mode),
        "FILE_INVALID",
        f"not a regular file: {relative}",
    )
    _require(
        info.st_nlink == 1,
        "FILE_INVALID",
        f"hardlink alias is forbidden: {relative}",
    )
    _require(
        info.st_size < limit,
        "FILE_INVALID",
        f"individual file limit exceeded: {relative}",
    )
    try:
        raw = current.read_bytes()
        after = current.stat()
    except OSError as exc:
        _reject("FILE_INVALID", f"cannot read {relative}: {exc}")
    signature = (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
    )
    after_signature = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )
    _require(
        signature == after_signature and len(raw) == info.st_size,
        "FILE_CHANGED",
        f"file changed while read: {relative}",
    )
    return raw, {
        "repository_relative_path": relative.as_posix(),
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }


def _validate_descriptor(
    descriptor: dict[str, Any], expected_octets: int, expected_sha256: str
) -> None:
    _require(
        descriptor["raw_octets"] == expected_octets
        and descriptor["raw_sha256"] == expected_sha256,
        "ARTIFACT_DRIFT",
        f"artifact drifted: {descriptor['repository_relative_path']}",
    )


def _load_json(root: pathlib.Path, relative: pathlib.Path) -> dict[str, Any]:
    raw, _ = _read_regular(root, relative)
    value = _strict_loads(raw)
    _require(isinstance(value, dict), "JSON_INVALID", f"object required: {relative}")
    return value


def _validate_fixed_artifacts(root: pathlib.Path) -> list[dict[str, Any]]:
    records = []
    for relative, (octets, digest) in sorted(
        PINNED_FIXED_ARTIFACTS.items(), key=lambda item: item[0].as_posix()
    ):
        _, descriptor = _read_regular(root, relative)
        _validate_descriptor(descriptor, octets, digest)
        records.append(descriptor)
    for relative, octets, digest in PINNED_REPLAY_TESTS:
        _, descriptor = _read_regular(root, relative)
        _validate_descriptor(descriptor, octets, digest)
        records.append(descriptor)
    return records


def _claimed_descriptor_matches(
    root: pathlib.Path,
    row: dict[str, Any],
    *,
    octet_member: str,
) -> pathlib.Path:
    relative = _relative_path(row["repository_relative_path"])
    _, descriptor = _read_regular(root, relative)
    _validate_descriptor(
        descriptor,
        row[octet_member],
        row["raw_sha256"],
    )
    return relative


def _authority_closure(root: pathlib.Path) -> dict[str, Any]:
    seed = _load_json(root, SEED)
    boundary = _load_json(root, BOUNDARY)
    seed_delta = _load_json(root, SEED_DELTA)
    paths = {
        VERIFIER,
        BOUNDARY,
        SEED,
        MANIFEST,
        SUCCESSOR_BOUNDARY,
        SEED_DELTA,
        MANIFEST_DELTA,
        TARGET_DELTA,
        PACKED_BOUNDARY,
        PREDECESSOR_TARGET,
        TYPED_RUNTIME,
    }
    for row in seed["ordered_authority_binding_records"]:
        paths.add(
            _claimed_descriptor_matches(
                root,
                row,
                octet_member="raw_octet_count",
            )
        )
    legacy = boundary["legacy_v1_exclusion_contract"]
    for name in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        paths.add(
            _claimed_descriptor_matches(
                root,
                legacy[name],
                octet_member="raw_octets",
            )
        )
    theorem = seed_delta["exactness_theorem_authority"]
    for row in theorem["ordered_source_authority_records"]:
        paths.add(
            _claimed_descriptor_matches(
                root,
                row,
                octet_member="raw_octets",
            )
        )
    records = []
    for relative in sorted(paths, key=lambda item: item.as_posix()):
        _, descriptor = _read_regular(root, relative)
        records.append(descriptor)
    total = sum(row["raw_octets"] for row in records)
    _require(
        len(records) == EXPECTED_AUTHORITY_FILE_COUNT
        and total == EXPECTED_AUTHORITY_OCTETS,
        "F0_DRIFT",
        "successor authority closure differs",
    )
    _require(
        len(records) <= F0_FILE_COUNT_LIMIT
        and total <= F0_TOTAL_OCTETS_LIMIT
        and all(row["raw_octets"] < F0_INDIVIDUAL_FILE_STRICT_UPPER for row in records),
        "F0_EXCEEDED",
        "successor authority closure exceeds immutable F0",
    )
    return {
        "input_file_count": len(records),
        "input_file_headroom": F0_FILE_COUNT_LIMIT - len(records),
        "total_pinned_input_octets": total,
        "total_pinned_input_octet_headroom": F0_TOTAL_OCTETS_LIMIT - total,
        "ordered_authority_records": records,
        "authority_closure_sha256": _sha256(_canonical_bytes(records)),
    }


def _control_snapshot(root: pathlib.Path) -> dict[str, Any]:
    raw, _ = _read_regular(root, CONTROL)
    text = raw.decode("utf-8", errors="strict")
    start_marker = "<!-- STAGE1_CONTROL_JSON_START\n"
    end_marker = "\nSTAGE1_CONTROL_JSON_END -->"
    _require(
        text.count(start_marker) == text.count(end_marker) == 1,
        "CONTROL_INVALID",
        "control JSON markers differ",
    )
    encoded = text.split(start_marker, 1)[1].split(end_marker, 1)[0].encode()
    control = _strict_loads(encoded)
    _require(isinstance(control, dict), "CONTROL_INVALID", "control is not an object")
    v4 = control.get("s1_a4_verifier_expansion_v4_snapshot")
    _require(isinstance(v4, dict), "CONTROL_INVALID", "V4 snapshot absent")
    _require(
        control.get("formal_stage1_state") == "NO-GO"
        and control.get("offline_stage2_state") == "BLOCKED"
        and control.get("live_activation_state") == "BLOCKED"
        and control.get("active_gate") == "S1-A4"
        and control["gate_states"]["S1-A4"]["state"] == "ACTIVE",
        "CONTROL_INVALID",
        "formal Stage 1 boundary differs",
    )
    _require(
        v4.get("correction_subgate") == "A4-P6-V4"
        and v4.get("acceptance_state")
        == "LOCAL_MINIMALITY_CASE_475_AND_CONSOLIDATED_F2_ACCEPTED"
        and v4.get("next_subgate") == "A4-P6-V-A"
        and v4.get("accepted_case_positions") == [5, 24, 54, 69, 435, 475]
        and v4.get("ordered_remaining_case_positions") == []
        and v4.get("verifier_raw_sha256") == PINNED_FIXED_ARTIFACTS[VERIFIER][1]
        and v4.get("successor_authority_file_count") == EXPECTED_AUTHORITY_FILE_COUNT
        and v4.get("successor_authority_octets") == EXPECTED_AUTHORITY_OCTETS
        and v4.get("producer_expansion_state") == "HOLD_UNTIL_A4_P6_V_ACCEPTED"
        and v4.get("runner_state")
        == "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED",
        "CONTROL_INVALID",
        "accepted V4 checkpoint differs",
    )
    return {
        "active_gate": control["active_gate"],
        "formal_stage1_state": control["formal_stage1_state"],
        "accepted_case_positions": v4["accepted_case_positions"],
        "verifier_raw_sha256": v4["verifier_raw_sha256"],
        "v4_acceptance_state": v4["acceptance_state"],
        "v4_next_subgate": v4["next_subgate"],
        "producer_expansion_state": v4["producer_expansion_state"],
        "runner_state": v4["runner_state"],
    }


def _validate_verifier_source(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        _reject("SOURCE_ISOLATION_INVALID", str(exc))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    expected_imports = {
        "hashlib",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "tempfile",
    }
    _require(
        imports == expected_imports
        and not from_imports
        and calls.isdisjoint({"__import__", "compile", "eval", "exec"})
        and "subprocess" not in source
        and "importlib" not in source
        and "runpy" not in source,
        "SOURCE_ISOLATION_INVALID",
        "verifier import/dynamic-execution surface differs",
    )
    for marker in (
        'SOURCE_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"',
        "V4_SUCCESSOR_CASE_POSITIONS",
        "def _load_authorities",
        "def _candidate_snapshot",
        "def _candidate_recheck",
        "def _derive_case_resources",
        "def _derive_local_case_resources",
        "def _publish_output",
        'measured <= limit["f2_per_case"]',
        '"RESOURCE_LIMIT_EXCEEDED"',
    ):
        _require(
            marker in source, "SOURCE_ISOLATION_INVALID", f"marker absent: {marker}"
        )
    for forbidden in (
        "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        "solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py",
        "construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py",
        "join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py",
    ):
        _require(
            forbidden not in source,
            "SOURCE_ISOLATION_INVALID",
            f"forbidden source dependency: {forbidden}",
        )
    return {
        "allowed_imports": sorted(imports),
        "dynamic_code_loading": False,
        "producer_or_proof_checker_imports": False,
        "resource_limit_enforcement": "MEASURED_LE_F2_PER_CASE",
    }


def _static_isolation(root: pathlib.Path) -> dict[str, Any]:
    verifier_raw, _ = _read_regular(root, VERIFIER)
    verifier_result = _validate_verifier_source(
        verifier_raw.decode("utf-8", errors="strict")
    )
    reviewed = []
    for relative, _, _ in PINNED_REPLAY_TESTS:
        raw, descriptor = _read_regular(root, relative)
        source = raw.decode("utf-8", errors="strict")
        tree = ast.parse(source)
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        _require(
            all(
                "verify_raw_v8_step2_maximum_protocol_v2_candidate" not in name
                for name in imported_modules
            )
            and "scripts.tests.verify_raw_v8_step2_maximum_protocol_v2_candidate"
            not in source,
            "FIXTURE_ISOLATION_INVALID",
            f"fixture imports verifier: {relative}",
        )
        reviewed.append(descriptor)
    return {
        "verifier": verifier_result,
        "reviewed_fixture_source_count": len(reviewed),
        "reviewed_fixture_sources_sha256": _sha256(_canonical_bytes(reviewed)),
    }


def _validate_case_ledger(
    manifest: dict[str, Any],
    ledger: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    limits = manifest.get("ordered_f2_limit_records")
    _require(
        isinstance(limits, list) and len(limits) == 18,
        "F2_INVALID",
        "F2 limit catalog differs",
    )
    _require(
        len(ledger) == 7
        and [(row["authority_mode"], row["case_position"]) for row in ledger]
        == [
            ("PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1", 5),
            ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 5),
            ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 24),
            ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 54),
            ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 69),
            ("SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1", 435),
            ("SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1", 475),
        ],
        "CASE_LEDGER_INVALID",
        "authority-mode/case order differs",
    )
    result = []
    for row in ledger:
        vector = row.get("resource_vector")
        _require(
            isinstance(vector, list)
            and len(vector) == len(limits)
            and all(type(value) is int and value >= 0 for value in vector),
            "F2_INVALID",
            f"resource vector invalid for case {row.get('case_position')}",
        )
        margins = []
        for measured, limit in zip(vector, limits, strict=True):
            ceiling = limit["f2_per_case"]
            _require(
                measured <= ceiling,
                "F2_EXCEEDED",
                f"case {row['case_position']} exceeds metric {limit['metric_position']}",
            )
            margins.append(ceiling - measured)
        result.append({**row, "f2_margins": margins})
    return result


def _subprocess_environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def _run_pytest(
    root: pathlib.Path, paths: list[pathlib.Path]
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *map(str, paths)],
        cwd=root,
        check=False,
        capture_output=True,
        env=_subprocess_environment(),
    )


def _parse_green_replay(
    completed: subprocess.CompletedProcess[bytes],
) -> dict[str, Any]:
    _require(
        completed.returncode == 0 and completed.stderr == b"",
        "REPLAY_FAILED",
        completed.stderr.decode("utf-8", errors="replace")[-1_000:],
    )
    output = completed.stdout.decode("utf-8", errors="strict")
    match = re.search(r"(?m)^(\d+) passed in [0-9.]+s(?: \([^)]+\))?$", output)
    _require(match is not None, "REPLAY_FAILED", "green replay summary absent")
    passed = int(match.group(1))
    _require(
        passed == EXPECTED_REPLAY_PASSED
        and " failed" not in output
        and " error" not in output.lower()
        and " skipped" not in output,
        "REPLAY_FAILED",
        "green replay count differs",
    )
    return {
        "passed": passed,
        "failed": 0,
        "skipped": 0,
        "test_artifact_count": len(PINNED_REPLAY_TESTS),
    }


def _parse_expected_red(
    completed: subprocess.CompletedProcess[bytes],
    *,
    expected_passed: int,
    expected_skipped: int,
    expected_failures: tuple[str, ...],
) -> dict[str, Any]:
    _require(completed.returncode == 1, "EXPECTED_RED_DRIFT", "red suite exit differs")
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="strict")
    summary = re.search(
        r"(?m)^(\d+) failed, (\d+) passed, (\d+) skipped in [0-9.]+s$",
        output,
    )
    _require(summary is not None, "EXPECTED_RED_DRIFT", "red summary absent")
    failed, passed, skipped = map(int, summary.groups())
    _require(
        failed == len(expected_failures)
        and passed == expected_passed
        and skipped == expected_skipped
        and "ERROR " not in output,
        "EXPECTED_RED_DRIFT",
        "red counts differ",
    )
    for code in expected_failures:
        _require(
            output.count(code) >= 1,
            "EXPECTED_RED_DRIFT",
            f"expected failure absent: {code}",
        )
    known_codes = set(re.findall(r"A4_(?:T|P6)_[A-Z0-9_]+", output))
    _require(
        known_codes == set(expected_failures),
        "EXPECTED_RED_DRIFT",
        "unexpected red failure code",
    )
    return {
        "failed": failed,
        "passed": passed,
        "skipped": skipped,
        "ordered_failure_codes": list(expected_failures),
    }


def _runtime_review(root: pathlib.Path) -> dict[str, Any]:
    replay = _parse_green_replay(
        _run_pytest(root, [row[0] for row in PINNED_REPLAY_TESTS])
    )
    a4_t = _parse_expected_red(
        _run_pytest(root, [IMPLEMENTATION_TARGET]),
        expected_passed=61,
        expected_skipped=2,
        expected_failures=EXPECTED_A4_T_FAILURES,
    )
    a4_p6 = _parse_expected_red(
        _run_pytest(root, [PREDECESSOR_TARGET]),
        expected_passed=13,
        expected_skipped=2,
        expected_failures=EXPECTED_A4_P6_FAILURES,
    )
    return {
        "verifier_replay": replay,
        "a4_t_expected_red": a4_t,
        "a4_p6_expected_red": a4_p6,
    }


def build_report(root: pathlib.Path, *, execute_runtime: bool = True) -> dict[str, Any]:
    root = root.resolve(strict=True)
    _validate_fixed_artifacts(root)
    control = _control_snapshot(root)
    authority = _authority_closure(root)
    isolation = _static_isolation(root)
    manifest = _load_json(root, MANIFEST)
    case_ledger = _validate_case_ledger(manifest, list(CASE_LEDGER))
    reviewer_raw = pathlib.Path(__file__).read_bytes()
    report = {
        "acceptance_report_version": REPORT_VERSION,
        "source_marker": SOURCE_MARKER,
        "review_decision": (
            "ACCEPTED" if execute_runtime else "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
        ),
        "reviewer_source": {
            "repository_relative_path": pathlib.Path(__file__)
            .resolve()
            .relative_to(root)
            .as_posix(),
            "raw_octets": len(reviewer_raw),
            "raw_sha256": _sha256(reviewer_raw),
        },
        "verifier_source": {
            "repository_relative_path": VERIFIER.as_posix(),
            "raw_octets": PINNED_FIXED_ARTIFACTS[VERIFIER][0],
            "raw_sha256": PINNED_FIXED_ARTIFACTS[VERIFIER][1],
        },
        "control_checkpoint": control,
        "authority_closure": authority,
        "static_isolation": isolation,
        "predecessor_seed_catalog_id": PREDECESSOR_SEED_ID,
        "predecessor_finalization_manifest_id": PREDECESSOR_MANIFEST_ID,
        "successor_seed_catalog_id": SUCCESSOR_SEED_ID,
        "successor_finalization_manifest_id": SUCCESSOR_MANIFEST_ID,
        "successor_f2_resource_limit_catalog_id": SUCCESSOR_F2_ID,
        "ordered_case_acceptance_records": case_ledger,
        "runtime_evidence": (
            _runtime_review(root)
            if execute_runtime
            else {
                "verifier_replay": None,
                "a4_t_expected_red": None,
                "a4_p6_expected_red": None,
            }
        ),
        "candidate_and_context_immutability": (
            "VERIFIED_BY_PINNED_DOUBLE_RUN_AND_HOSTILE_REPLAY"
            if execute_runtime
            else "NOT_EXECUTED"
        ),
        "producer_expansion_state": "HELD",
        "parent_runner_state": "ABSENT_AND_HELD",
        "formal_stage1_state": "NO-GO",
        "next_subgate": "A4-P6-P" if execute_runtime else "A4-P6-V-A",
    }
    report["independent_verifier_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN, report
    )
    return report


def _validate_report_identity(report: dict[str, Any]) -> None:
    claimed = report.get("independent_verifier_acceptance_report_id")
    payload = {
        name: value
        for name, value in report.items()
        if name != "independent_verifier_acceptance_report_id"
    }
    _require(
        claimed == _semantic_id(REPORT_DOMAIN, payload),
        "REPORT_IDENTITY_INVALID",
        "acceptance report identity differs",
    )


def _publish_report(path: pathlib.Path, raw: bytes) -> None:
    _require(path.is_absolute(), "OUTPUT_INVALID", "report path must be absolute")
    parent = path.parent
    _require(
        parent.is_dir() and not parent.is_symlink(), "OUTPUT_INVALID", "parent invalid"
    )
    _require(
        not path.exists() and not path.is_symlink(), "OUTPUT_INVALID", "output exists"
    )
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=".v-a-review-", dir=parent))
    try:
        temporary.chmod(0o700)
        staged = temporary / "report.json"
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(descriptor, raw[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(staged, path)
        parent_descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        try:
            temporary.rmdir()
        except OSError:
            pass


def _arguments(argv: list[str]) -> tuple[pathlib.Path, pathlib.Path]:
    _require(
        len(argv) == 5 and argv[1] == "--repository-root" and argv[3] == "--report-out",
        "INVOCATION_INVALID",
        "expected --repository-root ROOT --report-out ABSENT_PATH",
    )
    root = pathlib.Path(argv[2])
    output = pathlib.Path(argv[4])
    _require(
        root.is_absolute() and output.is_absolute(),
        "INVOCATION_INVALID",
        "paths must be absolute",
    )
    return root, output


def main(argv: list[str]) -> int:
    try:
        root, output = _arguments(argv)
        report = build_report(root, execute_runtime=True)
        _validate_report_identity(report)
        _publish_report(output, _pretty_bytes(report))
        return 0
    except (ReviewFailure, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"{ERROR_PREFIX}INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
