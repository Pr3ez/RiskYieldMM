"""Fixed RPF feature-family ablation masks."""

from __future__ import annotations


FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "volatility_state": ("rpf_vol_",),
    "structural_room": ("rpf_room_",),
    "acceptance_persistence": ("rpf_accept_",),
    "temporal_memory_transforms": ("rpf_mem_",),
    "rejection_chop": ("rpf_chop_",),
    "spike_breakout": ("rpf_spike_",),
    "liquidity_volume_pressure": ("rpf_liq_",),
    "regime_calendar_state": ("rpf_regime_",),
    "interaction_confluence": ("rpf_conf_",),
    "cross_asset_context": ("rpf_xasset_",),
    "unsupervised_factor_layer": ("rpf_factor_",),
    "sequence_embedding_layer": ("rpf_seq_",),
}


def select_ablation_features(feature_columns: tuple[str, ...], ablation: str = "all") -> tuple[str, ...]:
    spec = str(ablation or "all").strip()
    if spec == "all":
        return tuple(feature_columns)
    mode, families = _parse_ablation(spec)
    prefixes = tuple(prefix for family in families for prefix in FAMILY_PREFIXES[family])
    if mode in {"only", "group"}:
        selected = tuple(feature for feature in feature_columns if feature.startswith(prefixes))
    elif mode == "minus":
        selected = tuple(feature for feature in feature_columns if not feature.startswith(prefixes))
    else:  # pragma: no cover
        raise ValueError(f"Unsupported RPF ablation mode: {mode}")
    if not selected:
        raise ValueError(f"RPF ablation {spec!r} selected zero features")
    return selected


def _parse_ablation(spec: str) -> tuple[str, tuple[str, ...]]:
    for mode in ("only", "minus", "group"):
        prefix = f"{mode}_"
        if spec.startswith(prefix):
            families = tuple(part for part in spec[len(prefix) :].split("+") if part)
            unknown = [family for family in families if family not in FAMILY_PREFIXES]
            if unknown:
                known = ", ".join(sorted(FAMILY_PREFIXES))
                raise ValueError(f"Unknown RPF ablation family {unknown[0]!r}; expected one of: {known}")
            if not families:
                raise ValueError(f"RPF ablation {spec!r} does not name a family")
            return mode, families
    raise ValueError(
        "RPF ablation must be 'all', 'only_<family>[+family]', "
        "'group_<family>[+family]', or 'minus_<family>[+family]'"
    )
