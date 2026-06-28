from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_meta_router_simulator import (
    aggregate_rows,
    apply_candidate_rules,
    load_transfer_frame,
    rule_accept_mask,
    simulate_side_router,
    train_candidate_rules,
)


def test_rule_accept_mask_respects_direction() -> None:
    values = pl.Series([0.1, 0.2, 0.3]).to_numpy()

    assert rule_accept_mask(values, direction="higher_good", threshold=0.2).tolist() == [False, True, True]
    assert rule_accept_mask(values, direction="lower_good", threshold=0.2).tolist() == [True, True, False]


def test_load_transfer_frame_rejects_safe_context_label_leak(tmp_path: Path) -> None:
    run = tmp_path / "diag"
    run.mkdir()
    _write_safe_context(run, extra={"precision": 1.0})
    _write_transfer_table(run)

    with pytest.raises(ValueError, match="current-label columns"):
        load_transfer_frame(run)


def test_train_rules_uses_train_block_only() -> None:
    frame = pl.DataFrame(
        [
            _row("older", 1, feature=0.1, good=True, bad=False, signals=2, tp=2, fp=0),
            _row("older", 2, feature=0.2, good=True, bad=False, signals=2, tp=2, fp=0),
            _row("older", 3, feature=0.8, good=False, bad=True, signals=2, tp=0, fp=2),
            _row("older", 4, feature=0.9, good=False, bad=True, signals=2, tp=0, fp=2),
            # Latest block is intentionally inverted.  It must not change the fitted rule.
            _row("latest", 5, feature=0.1, good=False, bad=True, signals=2, tp=0, fp=2),
            _row("latest", 6, feature=0.9, good=True, bad=False, signals=2, tp=2, fp=0),
        ]
    )

    rules = train_candidate_rules(
        frame,
        feature_columns=["safe_feature"],
        train_source_block="older",
        min_train_good_rows=2,
        min_train_bad_rows=2,
        min_train_signals=1,
    )

    assert len(rules) == 1
    assert rules[0].feature == "safe_feature"
    assert rules[0].direction == "lower_good"
    assert rules[0].threshold < 0.5


def test_apply_rules_and_side_router_select_best_accepted_candidate() -> None:
    frame = pl.DataFrame(
        [
            _row("latest", 10, side="down", candidate="down_none_v1", feature=0.0, good=True, bad=False, signals=3, tp=3, fp=0),
            _row("latest", 10, side="down", candidate="down_rocket_16_diag_v1", feature=0.15, good=True, bad=False, signals=3, tp=2, fp=1),
        ]
    )
    rules = train_candidate_rules(
        pl.DataFrame(
            [
                _row("older", 1, side="down", candidate="down_none_v1", feature=0.1, good=True, bad=False, signals=3, tp=3, fp=0),
                _row("older", 2, side="down", candidate="down_none_v1", feature=0.9, good=False, bad=True, signals=3, tp=0, fp=3),
                _row("older", 3, side="down", candidate="down_rocket_16_diag_v1", feature=0.2, good=True, bad=False, signals=3, tp=2, fp=1),
                _row("older", 4, side="down", candidate="down_rocket_16_diag_v1", feature=0.8, good=False, bad=True, signals=3, tp=0, fp=3),
            ]
        ),
        feature_columns=["safe_feature"],
        train_source_block="older",
        min_train_good_rows=1,
        min_train_bad_rows=1,
        min_train_signals=1,
    )

    accepted = apply_candidate_rules(frame, rules)
    routed = simulate_side_router(accepted)
    selected = routed.row(0, named=True)

    assert selected["selected_candidate"] == "down_none_v1"
    assert selected["predicted_positive_count"] == 3
    assert selected["true_positive_count"] == 3


def test_aggregate_rows_matches_confusion_counts() -> None:
    frame = pl.DataFrame(
        [
            _row("latest", 1, signals=2, tp=1, fp=1, positives=4, rows=10),
            _row("latest", 2, signals=3, tp=3, fp=0, positives=6, rows=10),
        ]
    )

    metrics = aggregate_rows(frame)

    assert metrics["signals"] == 5
    assert metrics["true_positives"] == 4
    assert metrics["false_positives"] == 1
    assert metrics["precision"] == pytest.approx(0.8)
    assert metrics["base_rate"] == pytest.approx(0.5)
    assert metrics["lift"] == pytest.approx(1.6)


def _row(
    source_block: str,
    batch_id: int,
    *,
    side: str = "up",
    candidate: str = "up_none_v1",
    feature: float = 0.0,
    good: bool = False,
    bad: bool = False,
    signals: int = 0,
    tp: int = 0,
    fp: int = 0,
    positives: int = 5,
    rows: int = 10,
) -> dict[str, object]:
    precision = tp / signals if signals else None
    base_rate = positives / rows if rows else None
    return {
        "source_block": source_block,
        "source_role": "comparison_train" if source_block == "older" else "comparison_test",
        "source_run": "run",
        "side": side,
        "candidate_name": candidate,
        "router_step_idx": batch_id,
        "router_pred_batch_id": batch_id,
        "safe_feature": feature,
        "candidate_active": signals > 0,
        "candidate_good": good,
        "candidate_bad": bad,
        "candidate_good_reason": "fixture",
        "predicted_positive_count": signals,
        "true_positive_count": tp,
        "false_positive_count": fp,
        "positive_count": positives,
        "negative_count": max(0, rows - positives),
        "rows": rows,
        "precision": precision,
        "false_discovery_rate": fp / signals if signals else None,
        "precision_lift": precision / base_rate if precision is not None and base_rate else None,
        "base_positive_rate": base_rate,
    }


def _write_safe_context(run: Path, *, extra: dict[str, object] | None = None) -> None:
    row = {
        "source_block": "older",
        "source_role": "comparison_train",
        "source_run": "run",
        "side": "down",
        "candidate_name": "down_none_v1",
        "router_step_idx": 1,
        "router_pred_batch_id": 1,
        "validation_precision_lift": 1.2,
    }
    row.update(extra or {})
    pl.DataFrame([row]).write_parquet(run / "safe_context_features.parquet")


def _write_transfer_table(run: Path) -> None:
    pl.DataFrame(
        [
            {
                "source_block": "older",
                "source_role": "comparison_train",
                "source_run": "run",
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_step_idx": 1,
                "router_pred_batch_id": 1,
                "candidate_good": True,
                "candidate_bad": False,
            }
        ]
    ).write_parquet(run / "candidate_transfer_table.parquet")
