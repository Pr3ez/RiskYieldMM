from __future__ import annotations

import numpy as np

from scripts.target_models.helpers import egarch as egarch_module
from scripts.target_models.helpers import kalman as kalman_module
from scripts.target_models.helpers.base import HelperConfig
from scripts.target_models.helpers.egarch import EGARCHConfig, EGARCHHelper
from scripts.target_models.helpers.kalman import KalmanHelper


def test_kalman_rust_flag_requires_stateful_api() -> None:
    rust_module = getattr(kalman_module, "_rust", None)

    assert kalman_module.HAS_RUST == bool(
        rust_module is not None
        and hasattr(rust_module, "py_kalman_transform_with_state")
    )


def test_egarch_rust_flags_are_capability_specific() -> None:
    rust_module = getattr(egarch_module, "riskyield_rust", None)

    assert egarch_module.HAS_RUST == bool(
        rust_module is not None
        and hasattr(rust_module, "py_egarch_transform_with_state")
    )
    assert egarch_module.HAS_RUST_PARAM_ESTIMATE == bool(
        rust_module is not None and hasattr(rust_module, "py_egarch_estimate_params")
    )


def test_kalman_helper_uses_python_fallback_without_stateful_rust(
    monkeypatch,
) -> None:
    monkeypatch.setattr(kalman_module, "HAS_RUST", False)
    helper = KalmanHelper(HelperConfig(target="target", horizon=1))
    x = np.linspace(1.0, 2.0, 64, dtype=np.float64).reshape(-1, 1)

    helper.fit(x)
    output = helper.transform(x[-16:])

    assert output.features.shape == (16, 7)
    assert helper.get_last_transform_state() is not None


def test_egarch_helper_uses_python_fallback_without_stateful_rust(
    monkeypatch,
) -> None:
    monkeypatch.setattr(egarch_module, "HAS_RUST", False)
    monkeypatch.setattr(egarch_module, "HAS_RUST_PARAM_ESTIMATE", False)
    returns = np.sin(np.linspace(0.0, 4.0, 80, dtype=np.float64)) * 0.001
    helper = EGARCHHelper(
        EGARCHConfig(target="target", horizon=1, returns_col_idx=0)
    )
    x = returns.reshape(-1, 1)

    helper.fit(x)
    output = helper.transform(x[-16:])

    assert output.features.shape == (16, 8)
    assert helper.get_last_transform_state() is not None
