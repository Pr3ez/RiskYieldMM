from __future__ import annotations

import argparse
import importlib.util
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
    assert "--end-date" in yfinance_cmd
    assert "--start-date" not in yfinance_cmd


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
