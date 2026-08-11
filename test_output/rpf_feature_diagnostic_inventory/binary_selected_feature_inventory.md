# Binary Selected Feature Inventory

- Selected feature rows: `652808`
- Runs scanned: `27`

## Family Frequency
| target_col | family | selected_count | unique_features | runs_seen | pred_batches_seen |
| --- | --- | --- | --- | --- | --- |
| classification_cls_extreme_down_ge_2x_up_hvol_v2 | interaction_confluence | 142867 | 239 | 8 | 40 |
| classification_cls_extreme_down_ge_2x_up_hvol_v2 | structural_room | 77229 | 166 | 8 | 40 |
| classification_cls_extreme_down_ge_2x_up_hvol_v2 | liquidity_volume_pressure | 69947 | 132 | 6 | 40 |
| classification_cls_extreme_up_ge_2x_down_hvol_v2 | interaction_confluence | 139492 | 221 | 5 | 40 |
| classification_cls_extreme_up_ge_2x_down_hvol_v2 | structural_room | 112689 | 157 | 5 | 40 |
| classification_cls_extreme_up_ge_2x_down_hvol_v2 | liquidity_volume_pressure | 60365 | 113 | 5 | 40 |
| target_cls_extreme_down_ge_2x_up_hvol_v2 | interaction_confluence | 14429 | 173 | 4 | 50 |
| target_cls_extreme_down_ge_2x_up_hvol_v2 | structural_room | 8572 | 113 | 4 | 50 |
| target_cls_extreme_down_ge_2x_up_hvol_v2 | liquidity_volume_pressure | 4239 | 99 | 4 | 50 |
| target_cls_extreme_up_ge_2x_down_hvol_v2 | interaction_confluence | 11018 | 124 | 5 | 20 |
| target_cls_extreme_up_ge_2x_down_hvol_v2 | structural_room | 9311 | 89 | 5 | 20 |
| target_cls_extreme_up_ge_2x_down_hvol_v2 | liquidity_volume_pressure | 2551 | 60 | 5 | 20 |
| target_cls_extreme_up_ge_2x_down_hvol_v2 | volatility_state | 99 | 29 | 5 | 1 |

## Top Features: target_cls_extreme_down_ge_2x_up_hvol_v2
| family | feature | selected_count | runs_seen | pred_batches_seen |
| --- | --- | --- | --- | --- |
| interaction_confluence | rpf_conf_1h_up_trend_accept_l16_bnd | 337 | 4 | 50 |
| interaction_confluence | rpf_conf_1h_up_volume_impulse_l48_bnd | 315 | 3 | 49 |
| interaction_confluence | rpf_conf_12h_up_clean_persist_l16_bnd | 308 | 4 | 49 |
| structural_room | rpf_room_8h_up_to_high_l16_vol | 306 | 3 | 46 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l4_bnd | 304 | 4 | 50 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l16_bnd | 280 | 3 | 40 |
| interaction_confluence | rpf_conf_1h_volume_impulse_balance_l48_bnd | 279 | 3 | 28 |
| interaction_confluence | rpf_conf_1d_squeeze_break_balance_l48_bnd | 272 | 4 | 50 |
| interaction_confluence | rpf_conf_12h_squeeze_break_balance_l48_bnd | 271 | 4 | 45 |
| interaction_confluence | rpf_conf_8h_up_trend_accept_l16_bnd | 271 | 3 | 40 |
| interaction_confluence | rpf_conf_1h_down_trend_accept_l48_bnd | 266 | 3 | 38 |
| interaction_confluence | rpf_conf_12h_down_volume_impulse_l48_bnd | 266 | 3 | 48 |
| interaction_confluence | rpf_conf_8h_trend_accept_balance_l4_bnd | 262 | 3 | 18 |
| structural_room | rpf_room_1d_breakout_above_l48_vol | 258 | 4 | 30 |
| structural_room | rpf_room_12h_down_to_low_l16_vol | 257 | 3 | 48 |
| structural_room | rpf_room_1d_break_balance_l48_vol | 255 | 4 | 30 |
| interaction_confluence | rpf_conf_8h_volume_impulse_balance_l48_bnd | 254 | 3 | 26 |
| structural_room | rpf_room_1d_up_to_high_l16_vol | 250 | 3 | 43 |
| interaction_confluence | rpf_conf_8h_volume_impulse_balance_l4_bnd | 243 | 4 | 21 |
| structural_room | rpf_room_12h_up_to_high_l48_vol | 235 | 3 | 32 |
| structural_room | rpf_room_12h_value_dist_l16_vol | 232 | 2 | 18 |
| structural_room | rpf_room_1d_break_balance_l16_vol | 230 | 3 | 48 |
| interaction_confluence | rpf_conf_8h_volume_impulse_balance_l16_bnd | 230 | 3 | 22 |
| interaction_confluence | rpf_conf_8h_up_volume_impulse_l4_bnd | 228 | 4 | 28 |
| structural_room | rpf_room_12h_up_to_high_l4_vol | 226 | 4 | 45 |

## Top Features: target_cls_extreme_up_ge_2x_down_hvol_v2
| family | feature | selected_count | runs_seen | pred_batches_seen |
| --- | --- | --- | --- | --- |
| interaction_confluence | rpf_conf_1h_up_volume_impulse_l48_bnd | 288 | 5 | 20 |
| interaction_confluence | rpf_conf_1h_down_trend_accept_l48_bnd | 288 | 5 | 20 |
| interaction_confluence | rpf_conf_4h_squeeze_break_balance_l4_bnd | 286 | 5 | 20 |
| interaction_confluence | rpf_conf_1h_trend_accept_balance_l16_bnd | 286 | 4 | 20 |
| interaction_confluence | rpf_conf_1h_up_trend_accept_l16_bnd | 283 | 5 | 20 |
| structural_room | rpf_room_12h_up_to_high_l4_vol | 282 | 5 | 20 |
| interaction_confluence | rpf_conf_4h_squeeze_break_balance_l16_bnd | 277 | 5 | 20 |
| structural_room | rpf_room_1d_up_to_high_l4_vol | 276 | 5 | 20 |
| structural_room | rpf_room_8h_down_to_low_l16_vol | 272 | 4 | 20 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l4_bnd | 270 | 4 | 20 |
| interaction_confluence | rpf_conf_8h_trend_accept_balance_l4_bnd | 268 | 4 | 18 |
| structural_room | rpf_room_12h_down_to_low_l48_vol | 268 | 4 | 20 |
| interaction_confluence | rpf_conf_12h_down_clean_persist_l4_bnd | 263 | 5 | 20 |
| interaction_confluence | rpf_conf_12h_up_clean_persist_l4_bnd | 258 | 4 | 20 |
| interaction_confluence | rpf_conf_12h_up_trend_accept_l4_bnd | 258 | 3 | 20 |
| liquidity_volume_pressure | rpf_liq_8h_obv_slope_l4_bnd | 256 | 4 | 17 |
| liquidity_volume_pressure | rpf_liq_8h_up_volume_share_l4_bnd | 256 | 4 | 17 |
| liquidity_volume_pressure | rpf_liq_8h_down_volume_share_l4_bnd | 256 | 4 | 17 |
| liquidity_volume_pressure | rpf_liq_8h_volume_pressure_balance_l4_bnd | 256 | 4 | 17 |
| structural_room | rpf_room_8h_room_balance_l16_vol | 256 | 4 | 20 |
| structural_room | rpf_room_8h_breakdown_below_l16_vol | 254 | 3 | 20 |
| structural_room | rpf_room_4h_down_to_low_l16_vol | 254 | 3 | 19 |
| structural_room | rpf_room_12h_up_to_high_l16_vol | 251 | 4 | 20 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l16_bnd | 247 | 4 | 20 |
| structural_room | rpf_room_1d_break_balance_l16_vol | 245 | 3 | 20 |

## Top Features: classification_cls_extreme_down_ge_2x_up_hvol_v2
| family | feature | selected_count | runs_seen | pred_batches_seen |
| --- | --- | --- | --- | --- |
| interaction_confluence | rpf_conf_1h_up_trend_accept_l16_bnd | 2258 | 8 | 40 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l4_bnd | 2253 | 8 | 40 |
| liquidity_volume_pressure | rpf_liq_4h_volume_z_l4 | 2229 | 5 | 40 |
| structural_room | rpf_room_1d_breakout_above_l16_vol | 2146 | 4 | 40 |
| liquidity_volume_pressure | rpf_liq_12h_money_flow_balance_l16_bnd | 2114 | 6 | 40 |
| structural_room | rpf_room_12h_down_to_low_l16_vol | 2108 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_1d_money_flow_balance_l48_bnd | 2088 | 5 | 40 |
| interaction_confluence | rpf_conf_12h_down_volume_impulse_l16_bnd | 2084 | 5 | 40 |
| interaction_confluence | rpf_conf_1d_squeeze_break_balance_l48_bnd | 2047 | 6 | 40 |
| liquidity_volume_pressure | rpf_liq_15m_up_volume_share_l48_bnd | 1988 | 3 | 30 |
| interaction_confluence | rpf_conf_1h_up_volume_impulse_l48_bnd | 1970 | 7 | 40 |
| liquidity_volume_pressure | rpf_liq_12h_money_flow_balance_l4_bnd | 1960 | 5 | 40 |
| interaction_confluence | rpf_conf_1d_down_clean_persist_l16_bnd | 1955 | 5 | 40 |
| interaction_confluence | rpf_conf_1d_down_trend_accept_l16_bnd | 1924 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_8h_volume_wakeup_l4_bnd | 1914 | 4 | 31 |
| structural_room | rpf_room_12h_up_to_high_l4_vol | 1851 | 6 | 40 |
| interaction_confluence | rpf_conf_12h_down_volume_impulse_l48_bnd | 1842 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_8h_dollar_volume_rel_l4_bnd | 1826 | 4 | 31 |
| interaction_confluence | rpf_conf_8h_down_clean_persist_l4_bnd | 1826 | 3 | 30 |
| interaction_confluence | rpf_conf_12h_up_clean_persist_l16_bnd | 1822 | 8 | 40 |
| liquidity_volume_pressure | rpf_liq_1d_money_flow_balance_l4_bnd | 1804 | 5 | 38 |
| interaction_confluence | rpf_conf_4h_volume_impulse_balance_l16_bnd | 1762 | 5 | 40 |
| interaction_confluence | rpf_conf_4h_down_clean_persist_l16_bnd | 1728 | 4 | 31 |
| structural_room | rpf_room_8h_up_to_high_l16_vol | 1726 | 5 | 40 |
| interaction_confluence | rpf_conf_8h_up_trend_accept_l4_bnd | 1726 | 8 | 40 |

## Top Features: classification_cls_extreme_up_ge_2x_down_hvol_v2
| family | feature | selected_count | runs_seen | pred_batches_seen |
| --- | --- | --- | --- | --- |
| interaction_confluence | rpf_conf_1h_up_volume_impulse_l48_bnd | 2898 | 5 | 40 |
| interaction_confluence | rpf_conf_8h_clean_persist_balance_l16_bnd | 2833 | 5 | 40 |
| structural_room | rpf_room_4h_room_balance_l16_vol | 2813 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_4h_volume_wakeup_l16_bnd | 2808 | 5 | 40 |
| structural_room | rpf_room_8h_down_to_low_l16_vol | 2769 | 5 | 40 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l16_bnd | 2705 | 5 | 40 |
| structural_room | rpf_room_8h_value_dist_l16_vol | 2642 | 5 | 40 |
| structural_room | rpf_room_12h_down_to_low_l48_vol | 2600 | 5 | 40 |
| structural_room | rpf_room_1d_down_to_low_l16_vol | 2555 | 5 | 39 |
| interaction_confluence | rpf_conf_1h_down_trend_accept_l48_bnd | 2524 | 5 | 40 |
| interaction_confluence | rpf_conf_4h_up_room_pressure_l16_bnd | 2405 | 5 | 40 |
| structural_room | rpf_room_12h_breakout_above_l4_vol | 2384 | 5 | 40 |
| interaction_confluence | rpf_conf_12h_up_clean_persist_l16_bnd | 2377 | 5 | 40 |
| structural_room | rpf_room_12h_up_to_high_l4_vol | 2307 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_1h_volume_wakeup_l48_bnd | 2300 | 5 | 40 |
| structural_room | rpf_room_4h_value_dist_l16_vol | 2283 | 5 | 40 |
| interaction_confluence | rpf_conf_4h_squeeze_break_balance_l48_bnd | 2261 | 5 | 40 |
| interaction_confluence | rpf_conf_4h_squeeze_break_balance_l4_bnd | 2223 | 5 | 40 |
| interaction_confluence | rpf_conf_8h_up_clean_persist_l4_bnd | 2208 | 5 | 40 |
| liquidity_volume_pressure | rpf_liq_1d_money_flow_balance_l48_bnd | 2184 | 5 | 40 |
| interaction_confluence | rpf_conf_8h_down_volume_impulse_l16_bnd | 2184 | 5 | 40 |
| structural_room | rpf_room_4h_down_to_low_l48_vol | 2096 | 5 | 40 |
| structural_room | rpf_room_1d_up_to_high_l4_vol | 2096 | 5 | 40 |
| interaction_confluence | rpf_conf_1h_trend_accept_balance_l16_bnd | 2086 | 5 | 40 |
| structural_room | rpf_room_1d_break_balance_l4_vol | 2079 | 5 | 40 |
