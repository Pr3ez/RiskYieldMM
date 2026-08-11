from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_root_update_data():
    spec = importlib.util.spec_from_file_location(
        "root_update_data",
        PROJECT_ROOT / "update_data.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selected_sources_keep_fixed_execution_order() -> None:
    module = _load_root_update_data()

    assert module.selected_sources("") == ("bybit", "multiasset")
    assert module.selected_sources("multiasset,bybit") == ("bybit", "multiasset")
    assert module.selected_sources("databento,bybit") == ("bybit", "databento")
    assert module.selected_sources("twelvedata") == ("twelvedata",)
    assert module.selected_sources("yfinance") == ("yfinance",)

    with pytest.raises(argparse.ArgumentTypeError):
        module.selected_sources("unknown")


def test_core_defaults_match_full_bybit_period_with_full_history_guards() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(["--core"])

    assert args.start_date == "2021-01-01"
    assert args.end_date == "now"
    assert args.max_twelve_requests == 2000
    assert args.max_databento_cost_usd == 50.0
    assert args.canonical_assets == "core"
    assert args.derived_ohlcv_timeframes == "15m,1h,4h,8h,12h,1d"
    assert module.should_refresh_canonical(args) is True


def test_root_orchestrator_accepts_documented_htf_only_flag() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(["--core", "--dry-run", "--htf-only"])

    assert args.htf_only is True


def test_root_orchestrator_builds_same_period_commands() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(
        [
            "--core",
            "--dry-run",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-02-01",
            "--max-twelve-requests",
            "300",
            "--max-databento-cost-usd",
            "5",
        ]
    )

    bybit_cmd, _ = module.build_bybit_cmd(args)
    twelve_cmd, _ = module.build_twelve_cmd(args)
    multiasset_cmd, _ = module.build_multiasset_cmd(args)
    databento_cmd, _ = module.build_databento_cmd(args)
    yfinance_cmd, _ = module.build_yfinance_cmd(args)

    for cmd in (bybit_cmd, twelve_cmd, multiasset_cmd, databento_cmd):
        assert "--start-date" in cmd
        assert "--end-date" in cmd
        assert "2024-01-01" in cmd
        assert "2024-02-01" in cmd
        assert "--dry-run" in cmd

    assert "--fetch-only" in bybit_cmd
    assert "twelvedata" in twelve_cmd
    assert "auto" in multiasset_cmd
    assert "databento" in databento_cmd
    assert "yfinance" in yfinance_cmd
    assert "--start-date" in yfinance_cmd
    assert "--end-date" in yfinance_cmd


def test_root_estimate_only_does_not_build_write_commands() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(
        [
            "--core",
            "--estimate-only",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-02-01",
        ]
    )

    bybit_cmd, _ = module.build_bybit_cmd(args)
    twelve_cmd, _ = module.build_twelve_cmd(args)
    multiasset_cmd, _ = module.build_multiasset_cmd(args)
    databento_cmd, _ = module.build_databento_cmd(args)
    yfinance_cmd, _ = module.build_yfinance_cmd(args)

    assert "--dry-run" in bybit_cmd
    assert "--estimate-only" in twelve_cmd
    assert "--estimate-only" in multiasset_cmd
    assert "--estimate-only" in databento_cmd
    assert "--estimate-only" in yfinance_cmd
    assert module.should_refresh_canonical(args) is False


def test_build_refresh_canonical_cmd_refreshes_source_and_derived_bars() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(["--core"])

    cmd, cwd = module.build_refresh_canonical_cmd(args)

    assert cwd == module.PROJECT_ROOT
    assert "scripts/feature_engineering/materialize_canonical_ohlcv.py" in cmd
    assert "--refresh-1m-from-raw" in cmd
    assert "--assets" in cmd
    assert "core" in cmd
    assert "--timeframes" in cmd
    assert "15m,1h,4h,8h,12h,1d" in cmd
    assert "--start-date" in cmd
    assert "2021-01-01" in cmd
    assert cmd[cmd.index("--end-date") + 1] == "now"


def test_build_refresh_canonical_cmd_inherits_or_overrides_source_end() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()

    inherited = parser.parse_args(["--core", "--end-date", "2024-02-01T00:00:00Z"])
    inherited_cmd, _ = module.build_refresh_canonical_cmd(inherited)
    assert inherited_cmd[inherited_cmd.index("--end-date") + 1] == (
        "2024-02-01T00:00:00Z"
    )

    overridden = parser.parse_args(
        [
            "--core",
            "--end-date",
            "2024-02-01T00:00:00Z",
            "--canonical-end-date",
            "2024-01-15T00:00:00Z",
        ]
    )
    overridden_cmd, _ = module.build_refresh_canonical_cmd(overridden)
    assert overridden_cmd[overridden_cmd.index("--end-date") + 1] == (
        "2024-01-15T00:00:00Z"
    )


def test_root_orchestrator_runs_canonical_refresh_after_core_sources(
    monkeypatch,
) -> None:
    module = _load_root_update_data()
    calls = []

    def fake_run_step(name, cmd, cwd):
        calls.append((name, cmd, cwd))
        return True

    monkeypatch.setattr(module, "_run_step", fake_run_step)

    assert module.main(["--core"]) == 0

    assert [name for name, _, _ in calls] == [
        "BYBIT",
        "MULTIASSET",
        "REFRESH CANONICAL OHLCV",
    ]
    assert "--refresh-1m-from-raw" in calls[-1][1]


def test_root_orchestrator_can_skip_canonical_refresh(monkeypatch) -> None:
    module = _load_root_update_data()
    calls = []

    def fake_run_step(name, cmd, cwd):
        calls.append((name, cmd, cwd))
        return True

    monkeypatch.setattr(module, "_run_step", fake_run_step)

    assert module.main(["--core", "--skip-canonical-refresh"]) == 0

    assert [name for name, _, _ in calls] == ["BYBIT", "MULTIASSET"]


def test_allow_free_fresh_tail_is_noop_for_auto_core_source() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(["--core", "--allow-free-fresh-tail"])

    sources = module.selected_sources(args.sources)
    if (
        args.allow_free_fresh_tail
        and "multiasset" not in sources
        and "yfinance" not in sources
    ):
        sources = tuple(
            source for source in module.SOURCE_ORDER if source in {*sources, "yfinance"}
        )

    assert sources == ("bybit", "multiasset")


def test_allow_free_fresh_tail_still_extends_explicit_databento_source() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(
        ["--core", "--sources", "databento", "--allow-free-fresh-tail"]
    )

    sources = module.selected_sources(args.sources)
    if (
        args.allow_free_fresh_tail
        and "multiasset" not in sources
        and "yfinance" not in sources
    ):
        sources = tuple(
            source for source in module.SOURCE_ORDER if source in {*sources, "yfinance"}
        )

    assert sources == ("databento", "yfinance")


def test_demo_uses_free_sources_and_yahoo_safe_window() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(
        ["--demo", "--dry-run", "--end-date", "2026-05-08T12:00:30Z"]
    )

    start, end = module.resolve_demo_window(args.end_date)
    assert start == "2026-05-01T12:00:00Z"
    assert end == "2026-05-08T11:59:00Z"

    args.start_date = start
    args.end_date = end
    assert module.selected_sources_for_args(args) == ("bybit", "yfinance")

    bybit_cmd, _ = module.build_bybit_cmd(args)
    yfinance_cmd, _ = module.build_yfinance_cmd(args)

    assert "--demo" in yfinance_cmd
    assert "--providers" not in yfinance_cmd
    assert "databento" not in yfinance_cmd
    assert "twelvedata" not in yfinance_cmd
    for cmd in (bybit_cmd, yfinance_cmd):
        assert "2026-05-01T12:00:00Z" in cmd
        assert "2026-05-08T11:59:00Z" in cmd


def test_live_cli_defaults_cover_all_assets_and_canonical_timeframes() -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(["--live-start"])

    assert args.live_assets == "core"
    assert args.live_timeframes == "1m,15m,1h,4h,8h,12h,1d"
    assert args.live_poll_seconds == 60.0
    assert args.live_fee_bps == 1.0
    assert args.live_slippage_bps == 1.0
    assert args.live_spread_bps == 0.0
    assert args.live_execution_latency_minutes == 1
    assert args.live_strategy_manifest == ""
    assert args.require_live_feeds is False


def test_live_child_command_preserves_frozen_paper_assumptions(tmp_path: Path) -> None:
    module = _load_root_update_data()
    parser = module.build_arg_parser()
    args = parser.parse_args(
        [
            "--live-start",
            "--live-assets",
            "BTCUSDT,ETHUSDT",
            "--live-timeframes",
            "1m,1h",
            "--live-poll-seconds",
            "30",
            "--live-state-dir",
            str(tmp_path),
            "--live-strategy-manifest",
            str(tmp_path / "strategy.json"),
            "--live-fee-bps",
            "2",
            "--live-slippage-bps",
            "3",
            "--live-spread-bps",
            "4",
            "--live-execution-latency-minutes",
            "2",
            "--require-live-feeds",
        ]
    )

    command = module.build_live_child_cmd(args)

    assert command[1] == "-u"
    assert command[2] == str((module.PROJECT_ROOT / "update_data.py").resolve())
    assert "--live-1m" in command
    assert "--live-child" in command
    assert command[command.index("--live-assets") + 1] == "BTCUSDT,ETHUSDT"
    assert command[command.index("--live-timeframes") + 1] == "1m,1h"
    assert command[command.index("--live-state-dir") + 1] == str(tmp_path)
    assert command[command.index("--live-strategy-manifest") + 1] == str(
        tmp_path / "strategy.json"
    )
    assert command[command.index("--live-spread-bps") + 1] == "4.0"
    assert "--require-live-feeds" in command


def test_live_strategy_manifest_accepts_only_digest_verified_optimizer_winner(
    tmp_path: Path,
) -> None:
    module = _load_root_update_data()
    live = module._live_imports()
    expected = live["IndicatorStrategyConfig"]()
    best_config = {**expected.as_dict(), "horizon_template": "balanced"}
    encoded = json.dumps(
        best_config,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload = {
        "status": "accepted_for_paper_trading",
        "best_config": best_config,
        "best_config_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    path = tmp_path / "accepted-strategy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = module._live_strategy_from_manifest(str(path), live=live)

    assert loaded == expected
    assert (
        module._live_research_status_from_manifest(str(path))
        == "optimizer_accepted_forward_validation"
    )
    payload["status"] = "rejected"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not accepted_for_paper_trading"):
        module._live_strategy_from_manifest(str(path), live=live)


def test_plain_frozen_strategy_manifest_remains_observe_only(tmp_path: Path) -> None:
    module = _load_root_update_data()
    live = module._live_imports()
    expected = live["IndicatorStrategyConfig"]()
    path = tmp_path / "frozen-strategy.json"
    path.write_text(
        json.dumps(
            {
                "strategy": expected.as_dict(),
                "strategy_digest": expected.digest(),
            }
        ),
        encoding="utf-8",
    )

    assert module._live_strategy_from_manifest(str(path), live=live) == expected
    assert (
        module._live_research_status_from_manifest(str(path))
        == "frozen_strategy_observe_only"
    )

    path.write_text(json.dumps({"strategy": expected.as_dict()}), encoding="utf-8")
    with pytest.raises(ValueError, match="requires a strategy_digest"):
        module._live_strategy_from_manifest(str(path), live=live)


def test_live_mode_dispatches_without_running_batch_sources(monkeypatch) -> None:
    module = _load_root_update_data()
    calls: list[object] = []

    def fake_live(args, parser):
        calls.append((args.live_status, parser))
        return 7

    monkeypatch.setattr(module, "_run_live_command", fake_live)
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: pytest.fail("batch source must not run"),
    )

    assert module.main(["--live-status"]) == 7
    assert calls and calls[0][0] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["--core", "--live-start"],
        ["--live-start", "--live-status"],
        ["--live-start", "--once"],
    ],
)
def test_live_cli_rejects_ambiguous_or_invalid_mode_combinations(argv) -> None:
    module = _load_root_update_data()
    with pytest.raises(SystemExit):
        module.main(argv)


def test_live_selection_parsers_preserve_order_and_reject_unknowns() -> None:
    module = _load_root_update_data()
    assets = ("BTCUSDT", "ETHUSDT", "ES")
    timeframes = ("1m", "15m", "1h")

    assert module._resolved_live_assets(
        "ethusdt,BTCUSDT,ethusdt", known_assets=assets
    ) == ("ETHUSDT", "BTCUSDT")
    assert module._resolved_live_timeframes(
        "1H,1m,1h", known_timeframes=timeframes
    ) == ("1h", "1m")
    with pytest.raises(ValueError, match="Unknown or empty --live-assets"):
        module._resolved_live_assets("GC", known_assets=assets)
    with pytest.raises(ValueError, match="Unknown or empty --live-timeframes"):
        module._resolved_live_timeframes("4h", known_timeframes=timeframes)
