# RPF Feature Diagnostic Inventory

- Manifest: `data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/manifest.json`
- Manifest features: `2530`
- Correlation files read: `158`
- Bin-spread files read: `158`
- Raw manifest feature/target correlation rows: `56259`
- Finite manifest feature/target correlation rows used: `55733`
- Raw manifest feature/target bin-spread rows: `22212`
- Finite manifest feature/target bin-spread rows used: `22212`

## Family Correlation Summary
| family | features_seen | best_abs_spearman | features_abs_ge_0p20 | features_abs_ge_0p10 |
| --- | --- | --- | --- | --- |
| volatility_state | 29 | 0.706017 | 23 | 23 |
| temporal_memory_volatility | 220 | 0.399676 | 34 | 101 |
| structural_room | 180 | 0.363795 | 31 | 118 |
| regime_calendar_state | 172 | 0.291565 | 1 | 27 |
| acceptance_persistence | 201 | 0.29143 | 7 | 108 |
| spike_breakout | 288 | 0.238106 | 11 | 49 |
| unsupervised_factor_layer | 144 | 0.182635 | 0 | 7 |
| liquidity_volume_pressure | 147 | 0.159547 | 0 | 16 |
| interaction_confluence | 270 | 0.152969 | 0 | 6 |
| rejection_chop | 180 | 0.129571 | 0 | 3 |
| sequence_embedding_layer | 30 | 0.121512 | 0 | 2 |
| cross_asset_context | 144 | 0.058081 | 0 | 0 |
| temporal_memory_structural_room | 198 | 0.0528192 | 0 | 0 |
| temporal_memory_acceptance | 275 | 0.0520575 | 0 | 0 |

## Top Family/Timeframe Correlation Slices
| family | timeframe | features_seen | best_abs_spearman | features_abs_ge_0p10 |
| --- | --- | --- | --- | --- |
| volatility_state | global | 11 | 0.706017 | 11 |
| volatility_state | 12h | 3 | 0.589663 | 2 |
| volatility_state | 1d | 3 | 0.57855 | 2 |
| volatility_state | 8h | 3 | 0.520463 | 2 |
| volatility_state | 4h | 3 | 0.50495 | 2 |
| volatility_state | 1h | 3 | 0.49337 | 2 |
| volatility_state | 15m | 3 | 0.488214 | 2 |
| temporal_memory_volatility | global | 88 | 0.399676 | 53 |
| structural_room | 1h | 30 | 0.363795 | 24 |
| structural_room | 4h | 30 | 0.356719 | 23 |
| structural_room | 8h | 30 | 0.356676 | 21 |
| temporal_memory_volatility | 12h | 22 | 0.352641 | 10 |
| structural_room | 15m | 30 | 0.342112 | 16 |
| structural_room | 12h | 30 | 0.317249 | 18 |
| temporal_memory_volatility | 1d | 22 | 0.315218 | 10 |
| temporal_memory_volatility | 8h | 22 | 0.299501 | 9 |
| regime_calendar_state | utc | 5 | 0.291565 | 4 |
| acceptance_persistence | 12h | 33 | 0.29143 | 24 |
| structural_room | 1d | 30 | 0.274033 | 16 |
| spike_breakout | 8h | 48 | 0.238106 | 6 |
| spike_breakout | 1h | 48 | 0.236368 | 10 |
| spike_breakout | 12h | 48 | 0.233794 | 7 |
| spike_breakout | 1d | 48 | 0.230361 | 6 |
| spike_breakout | 4h | 48 | 0.229947 | 10 |
| temporal_memory_volatility | 4h | 22 | 0.226524 | 9 |
| acceptance_persistence | 4h | 33 | 0.212682 | 17 |
| acceptance_persistence | 1h | 33 | 0.209448 | 18 |
| acceptance_persistence | 15m | 33 | 0.206262 | 16 |
| spike_breakout | 15m | 48 | 0.199837 | 10 |
| acceptance_persistence | 8h | 33 | 0.192939 | 17 |
| temporal_memory_volatility | 1h | 22 | 0.186691 | 6 |
| unsupervised_factor_layer | 4h | 24 | 0.182635 | 2 |
| regime_calendar_state | 1h | 27 | 0.180324 | 6 |
| temporal_memory_volatility | 15m | 22 | 0.178293 | 4 |
| regime_calendar_state | 4h | 27 | 0.17705 | 6 |
| unsupervised_factor_layer | 1h | 24 | 0.168943 | 2 |
| regime_calendar_state | 15m | 27 | 0.16032 | 5 |
| liquidity_volume_pressure | 4h | 24 | 0.159547 | 4 |
| interaction_confluence | 4h | 45 | 0.152969 | 3 |
| regime_calendar_state | 12h | 29 | 0.147371 | 2 |

## Top Correlation Features By Target
### target_extreme_total
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.706017 | -0.393281 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.705483 | -0.210812 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.591449 | -0.209947 | 1405427 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.589663 | 0.353671 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.58009 | -0.208124 | 1405427 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.57855 | 0.319517 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 0.555726 | -0.286639 | 1405427 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.520463 | 0.301154 | 1405427 |
| volatility_state | 4h | rpf_vol_4h_range_to_tb_vol | 0.50495 | 0.246468 | 1405427 |
| volatility_state | 15m | rpf_vol_15m_range_to_tb_vol | 0.468458 | 0.149203 | 1405427 |
| volatility_state | 1h | rpf_vol_1h_range_to_tb_vol | 0.461721 | 0.199272 | 1405427 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_z_l1440_lag1 | 0.399676 | -0.399676 | 12549 |

### target_mean_total
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.523367 | -0.29601 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.522372 | -0.116377 | 1405427 |
| volatility_state | 1h | rpf_vol_1h_range_to_tb_vol | 0.49337 | 0.186165 | 1405427 |
| volatility_state | 15m | rpf_vol_15m_range_to_tb_vol | 0.488214 | 0.139131 | 1405427 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.455479 | 0.22733 | 1405427 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.454457 | 0.240898 | 1405427 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.453933 | 0.263841 | 1405427 |
| volatility_state | 4h | rpf_vol_4h_range_to_tb_vol | 0.431096 | 0.211494 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.429592 | -0.130628 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.399416 | -0.103712 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 0.390074 | -0.208668 | 1405427 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_z_l1440_lag1 | 0.308111 | -0.308111 | 12549 |

### target_extreme_up_minus_down
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.268353 | -0.268353 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.21599 | -0.21599 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.200802 | -0.200802 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.200802 | -0.200802 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l16_bnd | 0.172515 | -0.172515 | 47987 |
| acceptance_persistence | 8h | rpf_accept_8h_close_loc_balance_l16_bnd | 0.167704 | -0.167704 | 47987 |
| acceptance_persistence | 8h | rpf_accept_8h_close_loc_avg_l16_bnd | 0.167704 | -0.167704 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l4_bnd | 0.149086 | -0.149086 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.148949 | -0.148949 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l16_bnd | 0.141788 | -0.141788 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l16_bnd | 0.141788 | -0.141788 | 47987 |
| acceptance_persistence | 8h | rpf_accept_8h_value_accept_balance_l48_bnd | 0.140539 | -0.140539 | 47987 |

### target_mean_up_minus_down
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.262433 | -0.262433 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.221842 | -0.221842 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.216982 | -0.216982 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.216982 | -0.216982 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.174864 | -0.174864 | 47987 |
| structural_room | 12h | rpf_room_12h_donchian_pos_l48_bnd | 0.144642 | -0.00437369 | 1405427 |
| acceptance_persistence | 1d | rpf_accept_1d_above_value_share_l16_bnd | 0.14375 | -0.14375 | 47987 |
| acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l48_bnd | 0.14061 | -0.14061 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l16_bnd | 0.139652 | -0.139652 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l4_bnd | 0.138181 | -0.138181 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_down_pullback_shallow_l48_bnd | 0.135974 | 0.135974 | 47987 |
| acceptance_persistence | 8h | rpf_accept_8h_close_loc_avg_l16_bnd | 0.135002 | -0.135002 | 47987 |

### target_reg_distance_up_extreme_hvol_v2
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.344934 | -0.0983016 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.337778 | -0.170941 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.300962 | -0.0993958 | 1405427 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.297357 | 0.145251 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 0.287853 | -0.122405 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.286465 | -0.0962445 | 1405427 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.285618 | -0.285618 | 47987 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.279633 | 0.126356 | 1405427 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.270428 | 0.136927 | 1405427 |
| volatility_state | 4h | rpf_vol_4h_range_to_tb_vol | 0.242316 | 0.110485 | 1405427 |
| volatility_state | 1h | rpf_vol_1h_range_to_tb_vol | 0.238324 | 0.0888006 | 1405427 |
| volatility_state | 15m | rpf_vol_15m_range_to_tb_vol | 0.234416 | 0.0528377 | 1405427 |

### target_reg_distance_down_extreme_hvol_v2
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.281634 | -0.089501 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.279927 | -0.171239 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.266111 | -0.0833213 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.261518 | -0.0827686 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 0.25948 | -0.113482 | 1405427 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.245778 | 0.159641 | 1405427 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.238378 | 0.141789 | 1405427 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.22923 | 0.147799 | 1405427 |
| volatility_state | 4h | rpf_vol_4h_range_to_tb_vol | 0.218488 | 0.103712 | 1405427 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.205797 | 0.205797 | 47987 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_z_l1440_lag1 | 0.19831 | -0.19831 | 12549 |
| volatility_state | 1h | rpf_vol_1h_range_to_tb_vol | 0.197705 | 0.0820162 | 1405427 |

### target_reg_distance_up_mean_high_hvol_v2
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.269077 | -0.269077 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.215466 | -0.215466 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.215466 | -0.215466 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.21482 | -0.21482 | 47987 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.208936 | -0.053993 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.202559 | -0.0955326 | 1405427 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.193269 | 0.0736555 | 1405427 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.189313 | 0.0863766 | 1405427 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.175423 | 0.0764318 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.168985 | -0.0490646 | 1405427 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.166773 | -0.0500549 | 1405427 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.164605 | -0.164605 | 47987 |

### target_reg_distance_down_mean_low_hvol_v2
| family | timeframe | feature | max_abs_spearman | median_spearman | max_rows |
| --- | --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.228487 | 0.228487 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.207673 | 0.207673 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.19123 | 0.19123 | 47987 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.19123 | 0.19123 | 47987 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.178874 | 0.101952 | 1405427 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.168089 | 0.0952165 | 1405427 |
| structural_room | 12h | rpf_room_12h_down_to_low_l48_vol | 0.167043 | 0.0923249 | 1405427 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.158215 | 0.158215 | 47987 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.1576 | -0.0543979 | 1405427 |
| acceptance_persistence | 4h | rpf_accept_4h_close_loc_balance_l48_bnd | 0.157263 | 0.157263 | 47987 |
| acceptance_persistence | 4h | rpf_accept_4h_close_loc_avg_l48_bnd | 0.157263 | 0.157263 | 47987 |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.156848 | -0.105271 | 1405427 |

## Top Directional Candidates
| target | family | timeframe | feature | max_abs_spearman | median_spearman |
| --- | --- | --- | --- | --- | --- |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.268353 | -0.268353 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.262433 | -0.262433 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.221842 | -0.221842 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.216982 | -0.216982 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.216982 | -0.216982 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.21599 | -0.21599 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.200802 | -0.200802 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.200802 | -0.200802 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.174864 | -0.174864 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l16_bnd | 0.172515 | -0.172515 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_close_loc_balance_l16_bnd | 0.167704 | -0.167704 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_close_loc_avg_l16_bnd | 0.167704 | -0.167704 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l4_bnd | 0.149086 | -0.149086 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.148949 | -0.148949 |
| target_mean_up_minus_down | structural_room | 12h | rpf_room_12h_donchian_pos_l48_bnd | 0.144642 | -0.00437369 |
| target_mean_up_minus_down | acceptance_persistence | 1d | rpf_accept_1d_above_value_share_l16_bnd | 0.14375 | -0.14375 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l16_bnd | 0.141788 | -0.141788 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l16_bnd | 0.141788 | -0.141788 |
| target_mean_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l48_bnd | 0.14061 | -0.14061 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_value_accept_balance_l48_bnd | 0.140539 | -0.140539 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l16_bnd | 0.139652 | -0.139652 |
| target_extreme_up_minus_down | structural_room | 12h | rpf_room_12h_donchian_pos_l48_bnd | 0.139295 | 0.000668811 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_return_persist_l4_bnd | 0.138181 | -0.138181 |
| target_extreme_up_minus_down | acceptance_persistence | 4h | rpf_accept_4h_close_loc_balance_l48_bnd | 0.136911 | -0.136911 |
| target_extreme_up_minus_down | acceptance_persistence | 4h | rpf_accept_4h_close_loc_avg_l48_bnd | 0.136911 | -0.136911 |
| target_extreme_up_minus_down | acceptance_persistence | 1d | rpf_accept_1d_value_accept_balance_l16_bnd | 0.136577 | -0.136577 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_down_pullback_shallow_l48_bnd | 0.135974 | 0.135974 |
| target_mean_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_close_loc_avg_l16_bnd | 0.135002 | -0.135002 |
| target_mean_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_close_loc_balance_l16_bnd | 0.135002 | -0.135002 |
| target_mean_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_value_accept_balance_l48_bnd | 0.133729 | -0.133729 |
| target_mean_up_minus_down | acceptance_persistence | 1d | rpf_accept_1d_value_accept_balance_l16_bnd | 0.133636 | -0.133636 |
| target_mean_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_above_value_share_l48_bnd | 0.133615 | -0.133615 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l4_bnd | 0.132557 | -0.132557 |
| target_extreme_up_minus_down | acceptance_persistence | 1d | rpf_accept_1d_above_value_share_l16_bnd | 0.131429 | -0.131429 |
| target_mean_up_minus_down | acceptance_persistence | 4h | rpf_accept_4h_close_loc_avg_l48_bnd | 0.129717 | -0.129717 |
| target_mean_up_minus_down | acceptance_persistence | 4h | rpf_accept_4h_close_loc_balance_l48_bnd | 0.129717 | -0.129717 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l48_bnd | 0.129176 | -0.129176 |
| target_extreme_up_minus_down | acceptance_persistence | 12h | rpf_accept_12h_above_value_share_l4_bnd | 0.128289 | -0.128289 |
| target_extreme_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_value_accept_balance_l4_bnd | 0.125535 | -0.125535 |
| target_mean_up_minus_down | acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l4_bnd | 0.124921 | -0.124921 |

## Family Bin-Spread Summary
| family | features_seen | best_abs_bin_spread | features_spread_ge_0p20 | features_spread_ge_0p10 |
| --- | --- | --- | --- | --- |
| volatility_state | 29 | 1.6303 | 25 | 28 |
| acceptance_persistence | 201 | 1.28989 | 172 | 198 |
| temporal_memory_volatility | 206 | 1.05654 | 109 | 153 |
| structural_room | 130 | 0.960291 | 120 | 128 |
| regime_calendar_state | 137 | 0.74533 | 36 | 78 |
| spike_breakout | 234 | 0.599338 | 58 | 159 |
| unsupervised_factor_layer | 144 | 0.44667 | 18 | 70 |
| interaction_confluence | 270 | 0.406618 | 10 | 122 |
| liquidity_volume_pressure | 144 | 0.400415 | 35 | 87 |
| sequence_embedding_layer | 30 | 0.271481 | 4 | 18 |
| rejection_chop | 180 | 0.243849 | 2 | 42 |
| temporal_memory_acceptance | 213 | 0.222499 | 5 | 62 |
| temporal_memory_structural_room | 198 | 0.219268 | 9 | 90 |
| cross_asset_context | 144 | 0.148567 | 0 | 23 |

## Top Bin-Spread Features By Target
### target_extreme_total
| family | timeframe | feature | max_abs_bin_spread | median_bin_spread |
| --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 1.6303 | -0.602607 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 1.59021 | -1.06423 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 1.35846 | -0.505696 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 1.32119 | -0.723089 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 1.30781 | -0.724488 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 1.27286 | 0.497644 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 1.24266 | 0.517318 |
| volatility_state | global | rpf_vol_tb_vol_chg_l1440 | 1.17195 | -0.568631 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 1.09082 | 0.418247 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_rel_median_l1440_lag1 | 1.05654 | -1.05654 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_z_l1440_lag1 | 1.03444 | -1.03444 |
| temporal_memory_volatility | global | rpf_mem_vol_tb_vol_rel_median_l1440_ewm16 | 1.01116 | -1.01116 |

### target_mean_total
| family | timeframe | feature | max_abs_bin_spread | median_bin_spread |
| --- | --- | --- | --- | --- |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l1440 | 0.806833 | -0.458387 |
| volatility_state | global | rpf_vol_tb_vol_z_l1440 | 0.797874 | -0.233125 |
| volatility_state | global | rpf_vol_tb_vol_chg_l480 | 0.632903 | -0.299117 |
| volatility_state | global | rpf_vol_tb_vol_z_l480 | 0.595089 | -0.192493 |
| volatility_state | global | rpf_vol_tb_vol_rel_median_l480 | 0.594251 | -0.302159 |
| structural_room | 1h | rpf_room_1h_down_to_low_l16_vol | 0.547141 | 0.28498 |
| volatility_state | 12h | rpf_vol_12h_range_to_tb_vol | 0.535707 | 0.204137 |
| volatility_state | 8h | rpf_vol_8h_range_to_tb_vol | 0.525424 | 0.183062 |
| volatility_state | 1d | rpf_vol_1d_range_to_tb_vol | 0.518534 | 0.191723 |
| structural_room | 4h | rpf_room_4h_down_to_low_l4_vol | 0.506824 | 0.262371 |
| structural_room | 8h | rpf_room_8h_down_to_low_l16_vol | 0.482655 | 0.22417 |
| volatility_state | 4h | rpf_vol_4h_range_to_tb_vol | 0.466902 | 0.2272 |

### target_extreme_up_minus_down
| family | timeframe | feature | max_abs_bin_spread | median_bin_spread |
| --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 1.28989 | -1.28989 |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 1.27326 | -1.27326 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.993717 | -0.993717 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.993717 | -0.993717 |
| structural_room | 1h | rpf_room_1h_value_dist_l16_vol | 0.65551 | 0.202173 |
| acceptance_persistence | 1h | rpf_accept_1h_value_dist_l16_vol | 0.653897 | 0.653897 |
| acceptance_persistence | 1d | rpf_accept_1d_body_persist_l48_bnd | 0.652631 | -0.652631 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.651419 | -0.651419 |
| structural_room | 1h | rpf_room_1h_room_balance_l16_vol | 0.630104 | -0.199463 |
| acceptance_persistence | 4h | rpf_accept_4h_value_dist_l4_vol | 0.624266 | 0.624266 |
| structural_room | 4h | rpf_room_4h_value_dist_l4_vol | 0.622077 | 0.178362 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l4_bnd | 0.621742 | -0.621742 |

### target_mean_up_minus_down
| family | timeframe | feature | max_abs_bin_spread | median_bin_spread |
| --- | --- | --- | --- | --- |
| acceptance_persistence | 12h | rpf_accept_12h_body_persist_l48_bnd | 0.789186 | -0.789186 |
| acceptance_persistence | 12h | rpf_accept_12h_return_persist_l48_bnd | 0.762138 | -0.762138 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_avg_l48_bnd | 0.695011 | -0.695011 |
| acceptance_persistence | 12h | rpf_accept_12h_close_loc_balance_l48_bnd | 0.695011 | -0.695011 |
| acceptance_persistence | 12h | rpf_accept_12h_value_accept_balance_l48_bnd | 0.474966 | -0.474966 |
| acceptance_persistence | 12h | rpf_accept_12h_above_value_share_l48_bnd | 0.463575 | -0.463575 |
| acceptance_persistence | 1d | rpf_accept_1d_body_persist_l48_bnd | 0.453336 | -0.453336 |
| acceptance_persistence | 1d | rpf_accept_1d_above_value_share_l16_bnd | 0.422434 | -0.422434 |
| structural_room | 12h | rpf_room_12h_donchian_pos_l48_bnd | 0.407158 | -0.00568458 |
| acceptance_persistence | 15m | rpf_accept_15m_close_loc_avg_l48_bnd | 0.389973 | 0.389973 |
| acceptance_persistence | 15m | rpf_accept_15m_close_loc_balance_l48_bnd | 0.389973 | 0.389973 |
| acceptance_persistence | 8h | rpf_accept_8h_above_value_share_l48_bnd | 0.389954 | -0.389954 |
