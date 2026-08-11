from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
WEB_ROOT = ANALYST_ROOT / "web"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_server as chart_server_module  # noqa: E402


def _javascript_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*{{",
        source,
    )
    if match is None:
        raise AssertionError(f"JavaScript function {name!r} was not found")
    opening_brace = match.end() - 1
    depth = 0
    for position in range(opening_brace, len(source)):
        token = source[position]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : position + 1]
    raise AssertionError(f"JavaScript function {name!r} is not balanced")


def test_replay_api_defaults_to_e0_and_ignores_stale_disabled_bracket_values() -> None:
    default = chart_server_module._parse_replay_request("asset=BTCUSDT&timeframe=1h")
    stale = chart_server_module._parse_replay_request(
        "asset=BTCUSDT&timeframe=1h&protected_bracket=0"
        "&risk_unit_volatility_multiplier=not-a-number"
        "&stop_risk_units=-5&target_risk_units=999999&timeout_target_bars=0"
        "&break_even_safety_margin=not-a-number"
    )

    assert default.protection.enabled is False
    assert default.meta_filter_mode == "off"
    assert stale.protection == default.protection
    assert stale.cache_parameters() == default.cache_parameters()


def test_replay_api_parses_bounded_opt_in_protection_and_cache_identity() -> None:
    request = chart_server_module._parse_replay_request(
        urlencode(
            {
                "asset": "BTCUSDT",
                "timeframe": "4h",
                "protected_bracket": "1",
                "risk_unit_volatility_multiplier": "2.5",
                "stop_risk_units": "1.25",
                "target_risk_units": "2.75",
                "timeout_target_bars": "12",
                "break_even_safety_margin": "0.07",
            }
        )
    )

    assert request.protection.enabled is True
    assert request.protection.risk_unit_volatility_multiplier == 2.5
    assert request.protection.stop_risk_units == 1.25
    assert request.protection.target_risk_units == 2.75
    assert request.protection.timeout_target_bars == 12
    assert request.protection.break_even_safety_margin == 0.07
    finalized = request.protection.as_dict(timeframe="4h")["finalized_target_barrier"]
    assert finalized["timeout_target_bars"] == 12
    assert finalized["target_interval_seconds"] == 4 * 60 * 60
    assert finalized["timeout_clock"] == "accepted_finalized_target_bars"

    e0 = chart_server_module._parse_replay_request(
        "asset=BTCUSDT&timeframe=4h&protected_bracket=0"
    )
    different_margin = chart_server_module._parse_replay_request(
        urlencode(
            {
                "asset": "BTCUSDT",
                "timeframe": "4h",
                "protected_bracket": "1",
                "risk_unit_volatility_multiplier": "2.5",
                "stop_risk_units": "1.25",
                "target_risk_units": "2.75",
                "timeout_target_bars": "12",
                "break_even_safety_margin": "0.08",
            }
        )
    )
    assert request.cache_parameters() != e0.cache_parameters()
    assert request.cache_parameters() != different_margin.cache_parameters()


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("protected_bracket=maybe", "protected_bracket must be 0 or 1"),
        (
            "protected_bracket=1&risk_unit_volatility_multiplier=0",
            "risk_unit_volatility_multiplier must be between 0.1 and 20",
        ),
        (
            "protected_bracket=1&stop_risk_units=21",
            "stop_risk_units must be between 0.1 and 20",
        ),
        (
            "protected_bracket=1&target_risk_units=51",
            "target_risk_units must be between 0.1 and 50",
        ),
        (
            "protected_bracket=1&timeout_target_bars=1001",
            "timeout_target_bars must be between 1 and 1000",
        ),
        (
            "protected_bracket=1&break_even_safety_margin=0.51",
            "break_even_safety_margin must be between 0 and 0.5",
        ),
        ("meta_filter_mode=unknown", "meta_filter_mode must be one of"),
    ],
)
def test_replay_api_rejects_invalid_protected_research_values(
    query: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        chart_server_module._parse_replay_request(f"asset=BTCUSDT&timeframe=1h&{query}")


def test_non_off_meta_mode_fails_before_loading_data_without_server_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chart_server_module,
        "load_canonical_minute_window",
        lambda **_kwargs: pytest.fail("data must not load before artifact validation"),
    )

    with pytest.raises(ValueError, match="compatible server-side model artifact"):
        chart_server_module._build_research_response(
            "asset=BTCUSDT&timeframe=1h&meta_filter_mode=shadow",
            optimize=False,
        )


def test_gate_mode_rejects_candidate_only_artifact_before_loading_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = SimpleNamespace(
        assets=("BTCUSDT",),
        timeframes=("1h",),
        evaluation_metrics={
            "candidate_only": True,
            "auto_promoted": False,
            "walk_forward": {"deployment_eligible": False},
        },
    )
    monkeypatch.setenv(chart_server_module.META_ARTIFACT_ENV, "/server/model.json")
    monkeypatch.setattr(
        chart_server_module,
        "load_artifact_safe",
        lambda *_args, **_kwargs: SimpleNamespace(
            available=True,
            artifact=candidate,
            reason="ok",
            detail=None,
        ),
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_canonical_minute_window",
        lambda **_kwargs: pytest.fail("candidate gate must fail before data loading"),
    )

    with pytest.raises(ValueError, match="explicitly promoted artifact"):
        chart_server_module._build_research_response(
            "asset=BTCUSDT&timeframe=1h&protected_bracket=1&meta_filter_mode=gate",
            optimize=False,
        )


def test_gate_eligibility_requires_exact_promoted_asset_timeframe_scope() -> None:
    promoted = SimpleNamespace(
        assets=("BTCUSDT",),
        timeframes=("1h", "4h"),
        evaluation_metrics={
            "candidate_only": False,
            "auto_promoted": True,
            "walk_forward": {"deployment_eligible": True},
            "deployment_scope": {"eligible_selections": ["BTCUSDT/1h"]},
        },
    )

    assert chart_server_module._artifact_is_gate_eligible(
        promoted,
        asset="BTCUSDT",
        timeframe="1h",
    )
    assert not chart_server_module._artifact_is_gate_eligible(
        promoted,
        asset="BTCUSDT",
        timeframe="4h",
    )
    promoted.evaluation_metrics.pop("deployment_scope")
    assert not chart_server_module._artifact_is_gate_eligible(
        promoted,
        asset="BTCUSDT",
        timeframe="1h",
    )


def test_ui_exposes_opt_in_bracket_and_never_invents_meta_score_or_outcome_time() -> (
    None
):
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    source = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'name="protected_bracket" type="checkbox" value="1"' in html
    assert 'name="protected_bracket" type="checkbox" value="1" checked' not in html
    assert 'name="risk_unit_volatility_multiplier"' in html
    assert 'name="stop_risk_units"' in html
    assert 'name="target_risk_units"' in html
    assert 'name="timeout_target_bars"' in html
    assert 'name="break_even_safety_margin"' in html
    assert "strictly greater than both the model threshold" in html
    assert "decision-time static-stop break-even" in html
    assert 'name="meta_filter_mode"' in html
    assert "no score is fabricated" in html
    assert "Real routing remains off" in html
    assert 'id="replay-protection-legend"' in html
    assert 'id="replay-meta-legend"' in html

    request = _javascript_function(source, "replayRequestParams")
    assert (
        'params.set("protected_bracket", protectedBracketEnabled ? "1" : "0")'
        in request
    )
    assert 'params.set("meta_filter_mode", metaFilterMode)' in request
    assert "if (protectedBracketEnabled)" in request
    assert "timeoutTargetBars > 1000" in request
    assert "breakEvenSafetyMargin > 0.5" in request
    assert 'params.set("break_even_safety_margin"' in request

    overlay = _javascript_function(source, "applyReplayOverlay")
    assert "payload.risk_stop" in overlay
    assert "payload.risk_target" in overlay
    assert "payload.meta_scores" in overlay
    assert "stored P(TP before SL)" in overlay
    assert "decision_threshold" in overlay
    assert "replay_meta_required_probability" in overlay
    assert "strict required P" in overlay
    assert "clearReplayMetaModelThreshold" in overlay
    assert "predict" not in overlay.lower()

    mode_state = _javascript_function(source, "syncProtectedReplayControls")
    assert "artifact_checksum" in mode_state
    assert "loaded_compatible" in mode_state
    assert "replayBreakEvenSafetyMarginInput" in mode_state

    required_probability = _javascript_function(
        source,
        "replayRequiredProbabilityForLoadedChart",
    )
    assert "required_probability" in required_probability
    assert "point.value === null" in required_probability

    contract = _javascript_function(source, "renderReplayContract")
    assert "decision_threshold" in contract
    assert "label_mature_through" in contract
    assert "break_even_safety_margin" in contract
    assert "stored P strictly > max(model threshold" in contract
    assert "decision-time stop/target approximation" in contract

    marker_time = _javascript_function(source, "outcomeMarkerDisplayTime")
    assert "marker?.known_at" in marker_time
    assert "marker?.label_known_at" in marker_time
    assert 'marker?.time_semantics !== "known_at"' in marker_time
    assert "return null" in marker_time

    assert ".replay-protected-research" in styles
    assert ".research-mode-state.error" in styles
