#!/usr/bin/env python3
"""Capture the reviewed Raw-V8 Step-2 rule-literal authority snapshot.

This is an explicit one-way production provenance capture helper, not the
independent generator/validator required for technical acceptance.  The
standard-library-only validator pins and securely reads its output without
importing production.  Focused differential tests independently compare every
selected literal back to current production constructors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from riskyieldmm.trading.physical_transport_capacity_contracts_v49f_v8 import (  # noqa: E402
    RAW_V8_MARKER_CONTRACT_V49F,
    RAW_V8_OPERATION_COUNTER_SCHEMA_V49F,
    capacity_measurement_target_field_registry_v49f_v8,
)

CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
COMPONENT_STATUS = "RULE_LITERAL_AUTHORITY_ONLY_NOT_FULL_REGISTRY"
AUTHORITY_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.rule_literal_authority.v1"
)
AUTHORITY_DOMAIN = "RiskYieldMMA2MStep2RuleLiteralAuthorityV1V4_9F_RawV8"
DEFAULT_OUTPUT = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _record_canonical_bytes(value: Any) -> bytes:
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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_authority() -> dict[str, Any]:
    marker_contract = RAW_V8_MARKER_CONTRACT_V49F.as_dict()
    counter_schema = RAW_V8_OPERATION_COUNTER_SCHEMA_V49F.as_dict()
    target_registry = capacity_measurement_target_field_registry_v49f_v8().as_dict()
    payload = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "component_status": COMPONENT_STATUS,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "rule_literal_authority_version": AUTHORITY_VERSION,
        "marker_contract": marker_contract,
        "operation_counter_schema": counter_schema,
        "target_field_registry": target_registry,
        "selected_literal_canonical_sha256": {
            "marker_contract": _sha256(_record_canonical_bytes(marker_contract)),
            "operation_counter_schema": _sha256(
                _record_canonical_bytes(counter_schema)
            ),
            "target_field_registry": _sha256(_record_canonical_bytes(target_registry)),
        },
    }
    identity = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": AUTHORITY_DOMAIN,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )
    return {**payload, "rule_literal_authority_sha256": identity}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_pretty_bytes(build_authority()))
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output.read_bytes()),
                "status": COMPONENT_STATUS,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
