from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementArtifactBundleV49F,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F,
)
from tests import test_trading_physical_transport_capacity_measurement_v7_v49f as v7
from tests import test_trading_physical_transport_capacity_measurement_v49f as v6

_ISOLATED_SOURCE_ADVERSARY = r"""
import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

case = sys.argv[1]
repository_root = Path(sys.argv[2])
sys.path.insert(0, str(repository_root))

from riskyieldmm.trading import (  # noqa: E402
    physical_transport_capacity_source_observation_v49f as source,
)

lifecycle_name = "riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f"
if case == "extra":
    name = "riskyieldmm.synthetic_row1_extra"
    path = repository_root / "riskyieldmm/__init__.py"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    specification = importlib.util.spec_from_loader(name, loader)
    if specification is None:
        raise RuntimeError("extra-module specification is absent")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    loader.exec_module(module)
elif case == "alias":
    name = f"{lifecycle_name}_row1_alias"
    path = (
        repository_root
        / "riskyieldmm/trading/physical_transport_capacity_lifecycle_v49f.py"
    )
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    specification = importlib.util.spec_from_loader(name, loader)
    if specification is None:
        raise RuntimeError("lifecycle-alias specification is absent")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    loader.exec_module(module)
elif case == "fileless":
    sys.modules[lifecycle_name] = ModuleType(lifecycle_name)
else:
    raise RuntimeError(f"unknown source adversary: {case}")

try:
    observed = source.observe_current_source_v49f(
        repository_root=repository_root,
        deployment_source_tree_sha256="0" * 64,
    )
except source.SourceObservationV49FError as exc:
    print(type(exc).__name__)
    print(str(exc))
    raise SystemExit(0) from None
else:
    observed.close()
    raise SystemExit("production source observer accepted an adversarial module closure")
"""

_HISTORICAL_RAW_V6_EXACT_40_MEMBER_FINGERPRINTS = {
    "correctness.json": (
        1_433,
        "ec36f1894dd3537769aa6123925423d51e1ec3f1f1f51d4cf74d55c9d404b05e",
    ),
    "integrity.json": (
        1_284,
        "84a559318cd65ef8a9fd25202ac4b724fdfc36355e978b91480bd05285ce4750",
    ),
    "manifest.json": (
        17_763,
        "a7c3190de6dcb75067765abf598f9f0e64ec654404bc0f49c023e194753ee11f",
    ),
    "samples.jsonl": (
        46_017,
        "c3d16cd309d31d8b46a37397ef699794366641ff0beb39b22adaba9737fff64e",
    ),
}


@pytest.mark.parametrize(
    ("case", "expected_detail"),
    (
        ("extra", "riskyieldmm.synthetic_row1_extra"),
        (
            "alias",
            (
                "riskyieldmm.trading."
                "physical_transport_capacity_lifecycle_v49f_row1_alias"
            ),
        ),
        (
            "fileless",
            (
                "riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f "
                "is not an exact file-backed source module"
            ),
        ),
    ),
)
def test_v7_production_source_observer_rejects_isolated_loaded_module_adversary(
    case: str,
    expected_detail: str,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            _ISOLATED_SOURCE_ADVERSARY,
            case,
            str(repository_root),
        ),
        cwd=repository_root,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert lines[0] == "SourceObservationV49FError"
    assert expected_detail in lines[1]
    if case != "fileless":
        assert "outside the frozen release inventory" in lines[1]


def test_historical_exact_40_raw_v6_four_member_fixture_is_decode_only_for_v7() -> None:
    historical_modules = RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F
    roles = tuple(
        sorted(
            (
                *(f"CRITICAL_MODULE:{name}" for name in historical_modules),
                *(f"LOADED_MODULE:{name}" for name in historical_modules),
            )
        )
    )
    manifest = v7._current_v6_predecessor(source_roles=roles)  # noqa: SLF001
    role_values = tuple(
        role for member in manifest.source_observation.members for role in member.roles
    )
    assert (
        tuple(
            sorted(
                role.removeprefix("CRITICAL_MODULE:")
                for role in role_values
                if role.startswith("CRITICAL_MODULE:")
            )
        )
        == historical_modules
    )
    assert (
        tuple(
            sorted(
                role.removeprefix("LOADED_MODULE:")
                for role in role_values
                if role.startswith("LOADED_MODULE:")
            )
        )
        == historical_modules
    )

    samples = v6._samples(manifest)  # noqa: SLF001
    bundle = CapacityMeasurementArtifactBundleV49F.build(
        manifest=manifest,
        samples=samples,
        correctness=v6._unfinalized_correctness(manifest, samples),  # noqa: SLF001
    )
    fixture_bytes = bundle.artifact_bytes()
    fingerprints = {
        name: (len(payload), hashlib.sha256(payload).hexdigest())
        for name, payload in sorted(fixture_bytes.items())
    }
    assert fingerprints == _HISTORICAL_RAW_V6_EXACT_40_MEMBER_FINGERPRINTS

    replayed = CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(fixture_bytes)
    assert replayed == bundle
    assert replayed.artifact_bytes() == fixture_bytes

    current_v7, _ = v7._v7_manifest_and_expectation()  # noqa: SLF001
    with pytest.raises(
        CanonicalizationError,
        match="current exact 41-module source closure",
    ):
        replace(
            current_v7,
            predecessor_manifest_v6=replayed.manifest,
            campaign_manifest_id=None,
        )
