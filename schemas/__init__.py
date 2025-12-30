"""
Pandera schema validation system for time-series ML data.

Implements Aristotelian classification with Platonic ideal forms.
Each schema represents the "perfect" data structure against which
real data is validated.
"""

from .base_schemas import (
    TimeSeriesBaseSchema,
    OHLCVSchema,
    FundingRateSchema,
    OpenInterestSchema,
    MarkPriceSchema,
    IndexPriceSchema,
    PremiumIndexSchema
)

__all__ = [
    "TimeSeriesBaseSchema",
    "OHLCVSchema",
    "FundingRateSchema",
    "OpenInterestSchema",
    "MarkPriceSchema",
    "IndexPriceSchema",
    "PremiumIndexSchema"
]
