"""Zero-target validation contract.

Zero values are valid when the raw future path distance is exactly zero. They
are suspicious only when raw distance is positive, volatility is invalid, or the
future window metadata cannot explain the value.
"""

VALIDATION_NAME = "zero_targets"

