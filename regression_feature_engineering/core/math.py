"""Safe math helpers for causal regression feature formulas."""

from __future__ import annotations

import polars as pl


EPSILON = 1e-12
ZSCORE_CLIP = 8.0
VOL_UNIT_SCALE = 8.0


def safe_div_expr(
    numerator: pl.Expr,
    denominator: pl.Expr,
    *,
    default: float | None = 0.0,
    epsilon: float = EPSILON,
) -> pl.Expr:
    """Return a finite division expression with explicit zero-denominator policy."""

    return (
        pl.when(
            numerator.is_finite()
            & denominator.is_finite()
            & (denominator.abs() > float(epsilon))
        )
        .then(numerator / denominator)
        .otherwise(default)
    )


def pct_change_expr(current: pl.Expr, reference: pl.Expr, *, default: float = 0.0) -> pl.Expr:
    """Return `(current - reference) / reference` with safe division."""

    return safe_div_expr(current - reference, reference, default=default)


def bounded_expr(expr: pl.Expr, *, lower: float, upper: float) -> pl.Expr:
    """Clip an expression into a bounded numeric range."""

    return expr.clip(float(lower), float(upper))


def clipped_zscore_expr(expr: pl.Expr, *, limit: float = ZSCORE_CLIP) -> pl.Expr:
    """Return a finite z-score clipped to a fixed causal range."""

    return bounded_expr(expr, lower=-float(limit), upper=float(limit)).fill_null(0.0)


def positive_vol_unit_bnd_expr(expr: pl.Expr, *, scale: float = VOL_UNIT_SCALE) -> pl.Expr:
    """Compress positive volatility-unit magnitudes into `[0, 1]`.

    The transform is deterministic and does not fit on a sample:
    `x / (x + scale)` for `x >= 0`. It preserves ordering while preventing
    tiny volatility denominators from creating dominant model-facing columns.
    """

    positive = pl.when(expr.is_finite() & (expr > 0.0)).then(expr).otherwise(0.0)
    return bounded_expr(safe_div_expr(positive, positive + float(scale)), lower=0.0, upper=1.0).fill_null(0.0)


def signed_vol_unit_bnd_expr(expr: pl.Expr, *, scale: float = VOL_UNIT_SCALE) -> pl.Expr:
    """Compress signed volatility-unit values into `[-1, 1]`.

    This is a fixed live-safe normalization, not a dataset-fitted scaler:
    `x / (abs(x) + scale)`.
    """

    clean = pl.when(expr.is_finite()).then(expr).otherwise(0.0)
    return bounded_expr(safe_div_expr(clean, clean.abs() + float(scale)), lower=-1.0, upper=1.0).fill_null(0.0)


def positive_part_expr(expr: pl.Expr) -> pl.Expr:
    """Return `max(expr, 0)` as a finite expression."""

    return pl.when(expr.is_finite() & (expr > 0)).then(expr).otherwise(0.0)


def safe_log_ratio_expr(
    numerator: pl.Expr,
    denominator: pl.Expr,
    *,
    default: float = 0.0,
    epsilon: float = EPSILON,
) -> pl.Expr:
    """Return `log(numerator / denominator)` for positive finite inputs."""

    return (
        pl.when(
            numerator.is_finite()
            & denominator.is_finite()
            & (numerator > 0)
            & (denominator > 0)
        )
        .then((numerator + float(epsilon)).log() - (denominator + float(epsilon)).log())
        .otherwise(default)
    )
