from __future__ import annotations

import pytest

from regression_feature_engineering.experiments.acceptance_persistence_lookback_sweep import (
    parse_lookback_sets as parse_acceptance_lookback_sets,
)
from regression_feature_engineering.experiments.structural_room_lookback_sweep import parse_lookback_sets


def test_parse_structural_room_lookback_sets() -> None:
    assert parse_lookback_sets("2,4,8;4,16,48;8,8,24") == ((2, 4, 8), (4, 16, 48), (8, 24))


def test_parse_structural_room_lookback_sets_rejects_empty_or_bad_values() -> None:
    with pytest.raises(ValueError):
        parse_lookback_sets("")
    with pytest.raises(ValueError):
        parse_lookback_sets("4,0,8")


def test_parse_acceptance_lookback_sets() -> None:
    assert parse_acceptance_lookback_sets("2,4,8;4,16,48;8,8,24") == ((2, 4, 8), (4, 16, 48), (8, 24))


def test_parse_acceptance_lookback_sets_rejects_empty_or_bad_values() -> None:
    with pytest.raises(ValueError):
        parse_acceptance_lookback_sets("")
    with pytest.raises(ValueError):
        parse_acceptance_lookback_sets("4,-1,8")
