"""Binary target definitions for RPF classification."""

from __future__ import annotations

import polars as pl


UP_EXTREME = "target_reg_distance_up_extreme_hvol_v2"
DOWN_EXTREME = "target_reg_distance_down_extreme_hvol_v2"
TARGET_BINARY_UP_2X_DOWN = "target_cls_extreme_up_ge_2x_down_hvol_v2"
TARGET_BINARY_DOWN_2X_UP = "target_cls_extreme_down_ge_2x_up_hvol_v2"
TARGET_BINARY_UP_2X_DOWN_ALIAS = "classification_cls_extreme_up_ge_2x_down_hvol_v2"
TARGET_BINARY_DOWN_2X_UP_ALIAS = "classification_cls_extreme_down_ge_2x_up_hvol_v2"


def canonical_binary_target_col(target_col: str) -> str:
    if target_col in {TARGET_BINARY_UP_2X_DOWN, TARGET_BINARY_UP_2X_DOWN_ALIAS}:
        return TARGET_BINARY_UP_2X_DOWN
    if target_col in {TARGET_BINARY_DOWN_2X_UP, TARGET_BINARY_DOWN_2X_UP_ALIAS}:
        return TARGET_BINARY_DOWN_2X_UP
    raise ValueError(f"Unsupported RPF binary target: {target_col}")


def binary_target_expr(target_col: str = TARGET_BINARY_UP_2X_DOWN) -> pl.Expr:
    canonical = canonical_binary_target_col(target_col)
    if canonical == TARGET_BINARY_UP_2X_DOWN:
        expr = (pl.col(UP_EXTREME) > 0.0) & (pl.col(UP_EXTREME) >= 2.0 * pl.col(DOWN_EXTREME))
    elif canonical == TARGET_BINARY_DOWN_2X_UP:
        expr = (pl.col(DOWN_EXTREME) > 0.0) & (pl.col(DOWN_EXTREME) >= 2.0 * pl.col(UP_EXTREME))
    else:
        raise ValueError(f"Unsupported RPF binary target: {target_col}")
    return expr.cast(pl.Int8).alias(target_col)


def positive_rule_description(target_col: str) -> str:
    canonical = canonical_binary_target_col(target_col)
    if canonical == TARGET_BINARY_UP_2X_DOWN:
        return "up_extreme > 0 and up_extreme >= 2 * down_extreme"
    if canonical == TARGET_BINARY_DOWN_2X_UP:
        return "down_extreme > 0 and down_extreme >= 2 * up_extreme"
    raise ValueError(f"Unsupported RPF binary target: {target_col}")


def side_from_target(target_col: str) -> str:
    canonical = canonical_binary_target_col(target_col)
    if canonical == TARGET_BINARY_UP_2X_DOWN:
        return "up"
    if canonical == TARGET_BINARY_DOWN_2X_UP:
        return "down"
    raise ValueError(f"EMA-regime windows require an UP/DOWN binary target, got: {target_col}")
