"""
Walk-Forward Analysis & Reporting Functions
Extracts analysis logic from main script to reduce clutter.
"""

import numpy as np
import pandas as pd
import json
from sklearn.metrics import roc_auc_score


def print_multi_config_summary(config_results, config_scorer, MULTI_CONFIG_TRACKING):
    """Print multi-config comparison summary."""
    if not MULTI_CONFIG_TRACKING:
        return
    
    print("\n" + "="*100)
    print("MULTI-CONFIG COMPARISON (All configurations evaluated in parallel)")
    print("="*100)
    
    # Calculate metrics for each config
    config_metrics = []
    for cfg_name, results in config_results.items():
        n_total = results['total_predictions']
        if n_total == 0:
            continue
        
        tp = results['rolling_tp']
        fp = results['rolling_fp']
        tn = results['rolling_tn']
        fn = results['rolling_fn']
        
        accuracy = results['total_correct'] / n_total if n_total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        tp_fp_ratio = tp / fp if fp > 0 else float('inf') if tp > 0 else 0
        
        rolling_preds = list(results['rolling_pred_types'])
        rolling_tp = sum(1 for r in rolling_preds if r == 'TP')
        rolling_fp = sum(1 for r in rolling_preds if r == 'FP')
        rolling_ratio = rolling_tp / rolling_fp if rolling_fp > 0 else float('inf') if rolling_tp > 0 else 0
        
        config_metrics.append({
            'name': cfg_name,
            'config': results['config'],
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp,
            'tn': tn,
            'fn': fn,
            'tp_fp_ratio': tp_fp_ratio,
            'rolling_tp_fp': rolling_ratio,
            'total': n_total,
        })
    
    config_metrics.sort(key=lambda x: x['tp_fp_ratio'] if x['tp_fp_ratio'] != float('inf') else 999, reverse=True)
    
    print(f"\n{'Rank':<5} {'Config Name':<40} {'Acc':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'TP':>5} {'FP':>5} {'TN':>5} {'FN':>5} {'TP/FP':>7}")
    print("-"*100)
    
    for rank, m in enumerate(config_metrics[:20], 1):
        tp_fp_str = f"{m['tp_fp_ratio']:.2f}" if m['tp_fp_ratio'] != float('inf') else "∞"
        print(f"{rank:<5} {m['name']:<40} {m['accuracy']:6.1%} {m['precision']:6.1%} {m['recall']:6.1%} {m['f1']:6.3f} {m['tp']:5} {m['fp']:5} {m['tn']:5} {m['fn']:5} {tp_fp_str:>7}")
    
    print("\n" + "-"*100)
    print("BEST CONFIGS BY METRIC:")
    
    best_ratio = max(config_metrics, key=lambda x: x['tp_fp_ratio'] if x['tp_fp_ratio'] != float('inf') else -1)
    print(f"  Best TP/FP Ratio:  {best_ratio['name']} → {best_ratio['tp_fp_ratio']:.2f}")
    
    best_acc = max(config_metrics, key=lambda x: x['accuracy'])
    print(f"  Best Accuracy:     {best_acc['name']} → {best_acc['accuracy']:.1%}")
    
    best_prec = max(config_metrics, key=lambda x: x['precision'])
    print(f"  Best Precision:    {best_prec['name']} → {best_prec['precision']:.1%}")
    
    best_f1 = max(config_metrics, key=lambda x: x['f1'])
    print(f"  Best F1 Score:     {best_f1['name']} → {best_f1['f1']:.3f}")
    
    # Adaptive config selection summary
    print("\n" + "-"*100)
    print("ADAPTIVE CONFIG SELECTION SUMMARY (V3 Scorer):")
    print(f"  Final Selected Config: {config_scorer.current_config}")
    print(f"  Total Switches:        {len(config_scorer.switch_history)}")
    
    if config_scorer.switch_history:
        print(f"\n  Switch History:")
        for (sw_iter, from_cfg, to_cfg, reason) in config_scorer.switch_history[-10:]:
            print(f"    Iter {sw_iter:3}: {from_cfg[:20]} → {to_cfg[:20]} ({reason})")
        if len(config_scorer.switch_history) > 10:
            print(f"    ... ({len(config_scorer.switch_history) - 10} earlier switches omitted)")
    
    if config_scorer.current_config:
        selected_metrics = next((m for m in config_metrics if m['name'] == config_scorer.current_config), None)
        if selected_metrics:
            print(f"\n  Selected Config Performance:")
            print(f"    TP: {selected_metrics['tp']}, FP: {selected_metrics['fp']}, Ratio: {selected_metrics['tp_fp_ratio']:.2f}")
            print(f"    Accuracy: {selected_metrics['accuracy']:.1%}, Precision: {selected_metrics['precision']:.1%}")
            
            if best_ratio and best_ratio['name'] != config_scorer.current_config:
                print(f"\n  ⚠️  Best static config was: {best_ratio['name']} (ratio={best_ratio['tp_fp_ratio']:.2f})")
            else:
                print(f"\n  ✅ Adaptive selection matched best static config!")
    
    # Save to JSON
    config_metrics_serializable = []
    for m in config_metrics:
        m_copy = m.copy()
        m_copy['tp_fp_ratio'] = float(m_copy['tp_fp_ratio']) if m_copy['tp_fp_ratio'] != float('inf') else 999.0
        m_copy['rolling_tp_fp'] = float(m_copy['rolling_tp_fp']) if m_copy['rolling_tp_fp'] != float('inf') else 999.0
        config_metrics_serializable.append(m_copy)
    
    with open('multi_config_results.json', 'w') as f:
        json.dump(config_metrics_serializable, f, indent=2, default=str)
    print(f"\n  Results saved to: multi_config_results.json")
    print("="*100)


def print_walkforward_summary(walkforward_prediction_df, walkforward_iteration_df, 
                               iteration, WF_TRAIN, WF_VAL, WF_CAL, 
                               USE_AUTOMATIC_WINDOWS, DIAGNOSTICS, drift_alerts):
    """Print main walk-forward summary statistics."""
    print("\n" + "="*80)
    print("WALK-FORWARD TRAINING COMPLETE")
    print("="*80)
    
    if walkforward_prediction_df is None or len(walkforward_prediction_df) == 0:
        print("ERROR: No predictions generated!")
        return
    
    n_predictions = len(walkforward_prediction_df)
    
    print(f"\n  Iterations completed:     {iteration}")
    print(f"  Predictions generated:    {n_predictions:,}")
    
    print(f"\n  Window Configuration (Evidence-Based):")
    print(f"    W_train: {WF_TRAIN} rows")
    print(f"    W_val:   {WF_VAL} rows")
    print(f"    W_cal:   {WF_CAL} rows")
    if USE_AUTOMATIC_WINDOWS and DIAGNOSTICS:
        print(f"    M (memory):      {DIAGNOSTICS['M_memory_days']} days")
        print(f"    R (regime):      {DIAGNOSTICS['R_days_since_break']} days since break")
        print(f"    S (seasonality): {DIAGNOSTICS['S_seasonality_days']} days")
        print(f"    V (vol cycle):   {DIAGNOSTICS['V_vol_cycle_days']} days")
        print(f"    p (pos rate):    {DIAGNOSTICS['p_positive_rate']:.3f}")
    
    # Timing
    total_time = walkforward_iteration_df['iter_time_sec'].sum()
    avg_time = walkforward_iteration_df['iter_time_sec'].mean()
    print(f"\n  Timing Summary:")
    print(f"    Total time:     {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"    Avg per iter:   {avg_time:.1f}s")
    
    # Drift alerts
    if drift_alerts:
        print(f"\n  ⚠️ DRIFT ALERTS: {len(drift_alerts)} detected")
        for alert in drift_alerts[-5:]:
            print(f"    Iter {alert['iteration']}: PSI max={alert['max_psi']:.3f}, "
                  f"avg={alert['avg_psi']:.3f}, {alert['n_drifted']} features drifted")
    else:
        print(f"\n  ✅ No significant drift detected")
    
    # Calibration summary
    print(f"\n  Calibration Methods Used (ENSEMBLE):")
    if 'cb_cal_method' in walkforward_prediction_df.columns:
        cb_methods = walkforward_prediction_df['cb_cal_method'].value_counts()
        print(f"    CatBoost:")
        for method, count in cb_methods.items():
            print(f"      {method}: {count} predictions ({count/n_predictions*100:.1f}%)")
    if 'lgb_cal_method' in walkforward_prediction_df.columns:
        lgb_methods = walkforward_prediction_df['lgb_cal_method'].value_counts()
        print(f"    LightGBM:")
        for method, count in lgb_methods.items():
            print(f"      {method}: {count} predictions ({count/n_predictions*100:.1f}%)")
    print(f"    HistGradientBoosting: (same Platt method as LightGBM)")
    if 'meta_type' in walkforward_prediction_df.columns:
        meta_types = walkforward_prediction_df['meta_type'].value_counts()
        print(f"    Meta Stacker:")
        for method, count in meta_types.items():
            print(f"      {method}: {count} predictions ({count/n_predictions*100:.1f}%)")
    
    # Metrics summary
    print(f"\n  Direction Model (ENSEMBLE: CatBoost + LightGBM + HistGB):")
    print(f"    ─── Validation AUC by Model ───")
    if 'cb_val_auc' in walkforward_iteration_df.columns:
        print(f"    CatBoost:  mean={walkforward_iteration_df['cb_val_auc'].mean():.3f}")
    if 'lgb_val_auc' in walkforward_iteration_df.columns:
        print(f"    LightGBM:  mean={walkforward_iteration_df['lgb_val_auc'].mean():.3f}")
    print(f"    Ensemble:  mean={walkforward_iteration_df['val_auc'].mean():.3f}")
    print(f"    ─── Prediction Metrics ───")
    print(f"    Logloss:  mean={walkforward_iteration_df['pred_logloss'].mean():.4f}")
    print(f"    Accuracy: mean={walkforward_iteration_df['pred_accuracy'].mean()*100:.1f}%")
    
    if n_predictions >= 50:
        cumulative_pred_auc = roc_auc_score(
            walkforward_prediction_df['direction_actual'],
            walkforward_prediction_df['direction_proba']
        ) if len(walkforward_prediction_df['direction_actual'].unique()) > 1 else 0.5
        print(f"    Cumulative AUC: {cumulative_pred_auc:.4f}")
    
    print(f"\n  Volatility Model:")
    print(f"    Train R²: mean={walkforward_iteration_df['train_r2'].mean():.3f}")
    print(f"    Val R²:   mean={walkforward_iteration_df['val_r2'].mean():.3f}")
    print(f"    MAE:      mean={walkforward_iteration_df['pred_vol_mae'].mean():.5f}")
    
    # Returns prediction
    if 'returns_pred' in walkforward_prediction_df.columns and 'returns_actual' in walkforward_prediction_df.columns:
        returns_df = walkforward_prediction_df.dropna(subset=['returns_pred', 'returns_actual'])
        if len(returns_df) > 0:
            returns_mae = np.mean(np.abs(returns_df['returns_pred'] - returns_df['returns_actual']))
            returns_corr = returns_df['returns_pred'].corr(returns_df['returns_actual'])
            returns_sign_match = ((returns_df['returns_pred'] > 0) == (returns_df['returns_actual'] > 0)).mean()
            
            print(f"\n  Returns Prediction Model (Ridge: CB + LGB + Vol + Lagged):")
            print(f"    MAE:              {returns_mae:.5f}")
            print(f"    Correlation:      {returns_corr:.4f}")
            print(f"    Sign Accuracy:    {returns_sign_match*100:.1f}%")
            
            if 'lagged_returns' in returns_df.columns:
                naive_mae = np.mean(np.abs(returns_df['lagged_returns'] - returns_df['returns_actual']))
                naive_sign = ((returns_df['lagged_returns'] > 0) == (returns_df['returns_actual'] > 0)).mean()
                improvement = (naive_mae - returns_mae) / naive_mae * 100 if naive_mae > 0 else 0
                print(f"    ─── vs Naive (lagged) ───")
                print(f"    Naive MAE:        {naive_mae:.5f}")
                print(f"    Naive Sign Acc:   {naive_sign*100:.1f}%")
                print(f"    Improvement:      {improvement:+.1f}%")
    
    # Overfitting check
    avg_train_auc = walkforward_iteration_df['train_auc'].mean()
    avg_val_auc = walkforward_iteration_df['val_auc'].mean()
    gap = avg_train_auc - avg_val_auc
    
    print(f"\n  Overfitting Check:")
    print(f"    Train-Val AUC Gap: {gap:.3f}")
    if gap > 0.20:
        print(f"    ⚠️ WARNING: Large gap suggests overfitting!")
    elif gap > 0.10:
        print(f"    ⚡ MODERATE gap - some overfitting present")
    else:
        print(f"    ✅ Gap is acceptable")
    
    # Final summary
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  FINAL CUMULATIVE METRICS (n={n_predictions})")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    pred_positive = walkforward_prediction_df['direction_pred'].sum()
    actual_positive = walkforward_prediction_df['direction_actual'].sum()
    true_positives = ((walkforward_prediction_df['direction_pred'] == 1) & 
                      (walkforward_prediction_df['direction_actual'] == 1)).sum()
    false_positives = ((walkforward_prediction_df['direction_pred'] == 1) & 
                       (walkforward_prediction_df['direction_actual'] == 0)).sum()
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    
    print(f"    Predicted UP:  {pred_positive} ({pred_positive/n_predictions*100:.1f}%)")
    print(f"    Actual UP:     {actual_positive} ({actual_positive/n_predictions*100:.1f}%)")
    print(f"    Precision:     {precision*100:.1f}%")
    print(f"    True Pos:      {true_positives}")
    print(f"    False Pos:     {false_positives}")
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_ensemble_signal_summary(walkforward_iteration_df, walkforward_prediction_df, MULTI_CONFIG_TRACKING):
    """Print ensemble position signal analysis."""
    if not MULTI_CONFIG_TRACKING or 'ensemble_signal' not in walkforward_iteration_df.columns:
        return
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  ENSEMBLE POSITION SIGNAL ANALYSIS")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    signals = walkforward_iteration_df['ensemble_signal'].dropna()
    probs = walkforward_iteration_df['ensemble_probability'].dropna() if 'ensemble_probability' in walkforward_iteration_df.columns else None
    
    if len(signals) > 0:
        print(f"    Signal Statistics:")
        print(f"      Mean:   {signals.mean():.3f}  (1.0 = neutral)")
        print(f"      Std:    {signals.std():.3f}")
        print(f"      Min:    {signals.min():.3f}")
        print(f"      Max:    {signals.max():.3f}")
        
        strong_long = (signals >= 1.5).sum()
        long_pos = ((signals >= 1.1) & (signals < 1.5)).sum()
        neutral = ((signals >= 0.9) & (signals < 1.1)).sum()
        short_pos = ((signals >= 0.5) & (signals < 0.9)).sum()
        strong_short = (signals < 0.5).sum()
        
        print(f"\n    Signal Distribution:")
        print(f"      STRONG_LONG (>=1.5):  {strong_long:4} ({strong_long/len(signals)*100:5.1f}%)")
        print(f"      LONG (1.1-1.5):       {long_pos:4} ({long_pos/len(signals)*100:5.1f}%)")
        print(f"      NEUTRAL (0.9-1.1):    {neutral:4} ({neutral/len(signals)*100:5.1f}%)")
        print(f"      SHORT (0.5-0.9):      {short_pos:4} ({short_pos/len(signals)*100:5.1f}%)")
        print(f"      STRONG_SHORT (<0.5):  {strong_short:4} ({strong_short/len(signals)*100:5.1f}%)")
        
        if probs is not None and len(probs) > 0:
            print(f"\n    Probability Statistics:")
            print(f"      Mean P(UP):  {probs.mean():.1%}")
            print(f"      Std:         {probs.std():.1%}")
        
        if 'returns_actual' in walkforward_prediction_df.columns:
            returns_by_iter = walkforward_prediction_df.groupby('iteration')['returns_actual'].mean()
            common_iters = list(set(walkforward_iteration_df['iteration']) & set(returns_by_iter.index))
            if len(common_iters) > 10:
                sig_aligned = walkforward_iteration_df.set_index('iteration').loc[common_iters, 'ensemble_signal']
                ret_aligned = returns_by_iter.loc[common_iters]
                corr = sig_aligned.corr(ret_aligned)
                print(f"\n    Signal-Return Correlation:")
                print(f"      Correlation: {corr:.4f}")
                if corr > 0.1:
                    print(f"      ✅ Positive correlation with returns - signal is predictive")
                elif corr < -0.1:
                    print(f"      ⚠️ Negative correlation - signal may be contrarian")
                else:
                    print(f"      ⚡ Weak correlation - signal needs improvement")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_hull_score_summary(hull_scorer_benchmark, hull_scorer_baseline, MULTI_CONFIG_TRACKING):
    """Print Hull competition score analysis."""
    if not MULTI_CONFIG_TRACKING or hull_scorer_baseline is None:
        return
    if len(hull_scorer_baseline.history) < hull_scorer_baseline.min_samples:
        return
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  HULL COMPETITION SCORE ANALYSIS")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    # Benchmark summary
    hull_bench_summary = hull_scorer_benchmark.get_summary()
    print(f"\n  --- BENCHMARK (gates-only) ---")
    if hull_bench_summary.get('status') != 'no_scores':
        print(f"    Final Adjusted Sharpe:  {hull_bench_summary['final_score']:.4f}")
        print(f"    Mean Adjusted Sharpe:   {hull_bench_summary['mean_score']:.4f}")
        print(f"    Score Trend:            {hull_bench_summary['score_trend']}")
    
    # Baseline summary
    hull_base_summary = hull_scorer_baseline.get_summary()
    print(f"\n  --- BASELINE (gates + EMA) ---")
    if hull_base_summary.get('status') != 'no_scores':
        print(f"    Final Adjusted Sharpe:  {hull_base_summary['final_score']:.4f}")
        print(f"    Mean Adjusted Sharpe:   {hull_base_summary['mean_score']:.4f}")
        print(f"    Score Trend:            {hull_base_summary['score_trend']}")
        print(f"    Evaluations:            {hull_base_summary['n_evaluations']}")
        
        final_score, final_meta = hull_scorer_baseline.get_latest_score()
        if not np.isnan(final_score):
            print(f"\n    Final Baseline Metrics:")
            print(f"      Raw Sharpe:       {final_meta.get('sharpe', 0):.4f}")
            print(f"      Vol Penalty:      {final_meta.get('vol_penalty', 1):.4f}")
            print(f"      Ret Penalty:      {final_meta.get('return_penalty', 1):.4f}")
            print(f"      Strategy Return:  {final_meta.get('strategy_return', 0)*100:.2f}%")
            print(f"      Market Return:    {final_meta.get('market_return', 0)*100:.2f}%")
            print(f"      Vol Ratio:        {final_meta.get('vol_ratio', 1):.4f}")
            print(f"      Avg Position:     {final_meta.get('avg_position', 1):.3f}")
            print(f"      Position Std:     {final_meta.get('position_std', 0):.3f}")
        
        print(f"\n    Interpretation:")
        if hull_base_summary['final_score'] > 1.0:
            print(f"      ✅ Excellent: Sharpe > 1.0 after penalties")
        elif hull_base_summary['final_score'] > 0.5:
            print(f"      📈 Good: Solid risk-adjusted returns")
        elif hull_base_summary['final_score'] > 0.0:
            print(f"      ⚡ Moderate: Positive but room for improvement")
        else:
            print(f"      ⚠️ Negative Sharpe: Strategy underperforming risk-free")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_signal_aggregation_summary(walkforward_prediction_df, USE_SIGNAL_AGGREGATION, aggregated_feature_cols):
    """Print signal aggregation analysis."""
    if not USE_SIGNAL_AGGREGATION or not aggregated_feature_cols:
        return
    
    n_predictions = len(walkforward_prediction_df)
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  SIGNAL AGGREGATION ANALYSIS")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    if 'agg_net_signal' in walkforward_prediction_df.columns:
        net_signal = walkforward_prediction_df['agg_net_signal']
        actual = walkforward_prediction_df['direction_actual']
        
        corr = net_signal.corr(actual)
        print(f"    Net Signal ↔ Actual Direction: {corr:+.4f}")
        
        if 'agg_agreement_ratio' in walkforward_prediction_df.columns:
            agreement = walkforward_prediction_df['agg_agreement_ratio']
            high_conf_mask = agreement > 0.6
            low_conf_mask = agreement <= 0.6
            
            high_conf_accuracy = walkforward_prediction_df.loc[high_conf_mask, 'direction_correct'].mean()
            low_conf_accuracy = walkforward_prediction_df.loc[low_conf_mask, 'direction_correct'].mean()
            
            print(f"\n    High Confidence (agreement > 60%):")
            print(f"      Samples:  {high_conf_mask.sum()} ({high_conf_mask.sum()/n_predictions*100:.1f}%)")
            print(f"      Accuracy: {high_conf_accuracy*100:.1f}%")
            
            print(f"\n    Low Confidence (agreement ≤ 60%):")
            print(f"      Samples:  {low_conf_mask.sum()} ({low_conf_mask.sum()/n_predictions*100:.1f}%)")
            print(f"      Accuracy: {low_conf_accuracy*100:.1f}%")
        
        bullish_mask = net_signal > 0
        bearish_mask = net_signal < 0
        
        if bullish_mask.sum() > 0:
            bullish_acc = walkforward_prediction_df.loc[bullish_mask, 'direction_correct'].mean()
            print(f"\n    Bullish Net Signal (net > 0): {bullish_mask.sum()} samples, {bullish_acc*100:.1f}% accuracy")
        if bearish_mask.sum() > 0:
            bearish_acc = walkforward_prediction_df.loc[bearish_mask, 'direction_correct'].mean()
            print(f"    Bearish Net Signal (net < 0): {bearish_mask.sum()} samples, {bearish_acc*100:.1f}% accuracy")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_volatility_regime_summary(walkforward_prediction_df):
    """Print volatility regime analysis."""
    if 'volatility_regime' not in walkforward_prediction_df.columns:
        return
    
    n_predictions = len(walkforward_prediction_df)
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  VOLATILITY REGIME ANALYSIS")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    regime_counts = walkforward_prediction_df['volatility_regime'].value_counts()
    print(f"\n    Predicted Regime Distribution:")
    for regime in ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH', 'EXTREME']:
        if regime in regime_counts.index:
            count = regime_counts[regime]
            pct = count / n_predictions * 100
            print(f"      {regime:10s}: {count:4d} ({pct:5.1f}%)")
    
    print(f"\n    Direction Accuracy by Vol Regime:")
    for regime in ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH', 'EXTREME']:
        mask = walkforward_prediction_df['volatility_regime'] == regime
        if mask.sum() > 0:
            acc = walkforward_prediction_df.loc[mask, 'direction_correct'].mean() * 100
            n_samples = mask.sum()
            print(f"      {regime:10s}: {acc:5.1f}% (n={n_samples})")
    
    print(f"\n    Volatility MAE by Predicted Regime:")
    for regime in ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH', 'EXTREME']:
        mask = walkforward_prediction_df['volatility_regime'] == regime
        if mask.sum() > 0:
            mae = walkforward_prediction_df.loc[mask, 'volatility_ae'].mean()
            avg_actual = walkforward_prediction_df.loc[mask, 'volatility_actual'].mean()
            print(f"      {regime:10s}: MAE={mae:.5f}, Avg Actual={avg_actual:.5f}")
    
    print(f"\n    ═══ TRADING SIGNAL INTERPRETATION ═══")
    print(f"    LOW vol + Bullish:  Good for directional long")
    print(f"    LOW vol + Bearish:  Good for directional short")
    print(f"    HIGH+ vol:          Consider options/hedging, reduce size")
    print(f"    EXTREME vol:        Defensive mode, avoid new positions")
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_precision_zone_summary(walkforward_prediction_df):
    """Print precision zone analysis."""
    if 'precision_zone' not in walkforward_prediction_df.columns:
        return
    
    n_predictions = len(walkforward_prediction_df)
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  ⭐ PRECISION ZONE ANALYSIS (Signal Agreement)")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    zone_counts = walkforward_prediction_df['precision_zone'].value_counts()
    print(f"\n    Zone Distribution:")
    for zone in ['HIGH_CONF_LONG', 'HIGH_CONF_SHORT', 'MODERATE', 'NEUTRAL', 'LOW_CONF']:
        if zone in zone_counts.index:
            count = zone_counts[zone]
            pct = count / n_predictions * 100
            print(f"      {zone:15s}: {count:4d} ({pct:5.1f}%)")
    
    print(f"\n    DIRECTION METRICS BY PRECISION ZONE:")
    print(f"    {'Zone':<16} {'N':<6} {'Accuracy':<10} {'Precision':<10} {'Recall':<10}")
    print(f"    {'-'*16} {'-'*6} {'-'*10} {'-'*10} {'-'*10}")
    
    for zone in ['HIGH_CONF_LONG', 'HIGH_CONF_SHORT', 'MODERATE', 'NEUTRAL', 'LOW_CONF']:
        mask = walkforward_prediction_df['precision_zone'] == zone
        if mask.sum() > 0:
            zone_df = walkforward_prediction_df[mask]
            n_zone = mask.sum()
            
            acc = zone_df['direction_correct'].mean() * 100
            
            pred_up = zone_df['direction_pred'] == 1
            if pred_up.sum() > 0:
                precision = (zone_df.loc[pred_up, 'direction_actual'] == 1).mean() * 100
            else:
                precision = np.nan
            
            actual_up = zone_df['direction_actual'] == 1
            if actual_up.sum() > 0:
                recall = (zone_df.loc[actual_up, 'direction_pred'] == 1).mean() * 100
            else:
                recall = np.nan
            
            print(f"    {zone:<16} {n_zone:<6} {acc:>6.1f}%    {precision:>6.1f}%    {recall:>6.1f}%")
    
    print(f"\n    Signal Count Distribution:")
    bearish_counts_all = walkforward_prediction_df['n_bearish_signals']
    bullish_counts_all = walkforward_prediction_df['n_bullish_signals']
    print(f"      Bearish signals: mean={bearish_counts_all.mean():.2f}, max={bearish_counts_all.max()}")
    print(f"      Bullish signals: mean={bullish_counts_all.mean():.2f}, max={bullish_counts_all.max()}")
    
    high_conf = walkforward_prediction_df['precision_zone'].isin(['HIGH_CONF_LONG', 'HIGH_CONF_SHORT'])
    n_high_conf = high_conf.sum()
    if n_high_conf > 0:
        high_conf_accuracy = walkforward_prediction_df.loc[high_conf, 'direction_correct'].mean() * 100
        print(f"\n    ═══ HIGH CONFIDENCE ZONES (trading signal) ═══")
        print(f"    Samples with high signal agreement: {n_high_conf} ({n_high_conf/n_predictions*100:.1f}%)")
        print(f"    Combined accuracy: {high_conf_accuracy:.1f}%")
        print(f"    → Use these zones for higher conviction trades")
    
    low_conf_mask = walkforward_prediction_df['precision_zone'] == 'LOW_CONF'
    if low_conf_mask.sum() > 0:
        low_conf_accuracy = walkforward_prediction_df.loc[low_conf_mask, 'direction_correct'].mean() * 100
        print(f"\n    ═══ LOW CONFIDENCE ZONES (avoid) ═══")
        print(f"    Samples with conflicting signals: {low_conf_mask.sum()} ({low_conf_mask.sum()/n_predictions*100:.1f}%)")
        print(f"    Accuracy: {low_conf_accuracy:.1f}%")
        print(f"    → Consider skipping trades in this zone")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_calibration_diagnostics_summary(calibration_diagnostics):
    """Print calibration diagnostics summary."""
    if not calibration_diagnostics:
        return
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  ⭐ CALIBRATION DIAGNOSTICS (Brier & ECE)")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    cal_df = pd.DataFrame(calibration_diagnostics)
    n_cal_iters = len(cal_df)
    
    print(f"\n    Calibration active for {n_cal_iters} iterations")
    print(f"    Average buffer size: {cal_df['cal_samples'].mean():.0f} samples")
    
    # Per-model summaries
    for model, prefix in [('CatBoost', 'cb'), ('LightGBM', 'lgb'), ('HistGradientBoosting', 'hgb')]:
        print(f"\n    ─── {model} Calibration ───")
        brier_before = cal_df[f'{prefix}_brier_before'].mean()
        brier_after = cal_df[f'{prefix}_brier_after'].mean()
        ece_before = cal_df[f'{prefix}_ece_before'].mean()
        ece_after = cal_df[f'{prefix}_ece_after'].mean()
        print(f"    Brier Score:  {brier_before:.4f} → {brier_after:.4f} (avg improvement: {brier_before - brier_after:+.4f})")
        print(f"    ECE Score:    {ece_before:.4f} → {ece_after:.4f} (avg improvement: {ece_before - ece_after:+.4f})")
    
    # Interpretation
    print(f"\n    ─── INTERPRETATION ───")
    for model, prefix in [('CatBoost', 'cb'), ('LightGBM', 'lgb'), ('HistGradientBoosting', 'hgb')]:
        avg_brier = cal_df[f'{prefix}_brier_after'].mean()
        avg_ece = cal_df[f'{prefix}_ece_after'].mean()
        
        if avg_brier < 0.20:
            print(f"    {model} Brier {avg_brier:.4f}: ✅ Good calibration")
        elif avg_brier < 0.25:
            print(f"    {model} Brier {avg_brier:.4f}: ⚡ Moderate calibration")
        else:
            print(f"    {model} Brier {avg_brier:.4f}: ⚠️ Poor calibration (worse than random)")
        
        if avg_ece < 0.05:
            print(f"    {model} ECE {avg_ece:.4f}: ✅ Well calibrated")
        elif avg_ece < 0.10:
            print(f"    {model} ECE {avg_ece:.4f}: ⚡ Moderately calibrated")
        else:
            print(f"    {model} ECE {avg_ece:.4f}: ⚠️ Poorly calibrated")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_model_diversity_summary(model_diversity_metrics):
    """Print model diversity summary."""
    if not model_diversity_metrics:
        return
    
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  ⭐ ENSEMBLE DIVERSITY METRICS (CatBoost + LightGBM + HistGradientBoosting)")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    div_df = pd.DataFrame(model_diversity_metrics)
    n_div_iters = len(div_df)
    
    avg_corr = div_df['avg_correlation'].mean()
    avg_disagree = div_df['disagreement_rate'].mean()
    avg_spread = div_df['pred_spread'].mean()
    avg_cb_auc = div_df['cb_val_auc'].mean()
    avg_lgb_auc = div_df['lgb_val_auc'].mean()
    avg_hgb_auc = div_df['hgb_val_auc'].mean()
    
    print(f"\n    Diversity tracked for {n_div_iters} iterations")
    print(f"\n    ─── CORRELATION & AGREEMENT ───")
    print(f"    Average Pairwise Correlation: {avg_corr:.3f} (lower = more diverse)")
    print(f"    Disagreement Rate (any):      {avg_disagree:.1%} (higher = more diverse)")
    print(f"    Average Prediction Spread:    {avg_spread:.4f}")
    
    print(f"\n    ─── PAIRWISE CORRELATIONS ───")
    print(f"    CB ↔ LGB:  {div_df['corr_cb_lgb'].mean():.3f}")
    print(f"    CB ↔ HGB:  {div_df['corr_cb_hgb'].mean():.3f}")
    print(f"    LGB ↔ HGB: {div_df['corr_lgb_hgb'].mean():.3f}")
    
    print(f"\n    ─── PER-MODEL PERFORMANCE ───")
    print(f"    CatBoost VAL AUC:           {avg_cb_auc:.4f}")
    print(f"    LightGBM VAL AUC:           {avg_lgb_auc:.4f}")
    print(f"    HistGradientBoosting AUC:   {avg_hgb_auc:.4f}")
    best_model = 'CB' if avg_cb_auc >= avg_lgb_auc and avg_cb_auc >= avg_hgb_auc else ('LGB' if avg_lgb_auc >= avg_hgb_auc else 'HGB')
    print(f"    Best Single Model:          {best_model}")
    
    lr_usage = (div_df['meta_type'] == 'lr').mean() * 100
    print(f"\n    ─── META STACKER USAGE ───")
    print(f"    LogisticRegression Meta: {lr_usage:.1f}% of iterations")
    print(f"    Simple Average:          {100-lr_usage:.1f}% of iterations")
    
    print(f"\n    ─── INTERPRETATION ───")
    if avg_corr < 0.5:
        print(f"    ✅ Low correlation ({avg_corr:.3f}): Models are diverse, ensemble benefits")
    elif avg_corr < 0.7:
        print(f"    ⚡ Moderate correlation ({avg_corr:.3f}): Some diversity, ensemble may help")
    else:
        print(f"    ⚠️ High correlation ({avg_corr:.3f}): Models similar, consider different architectures")
    
    if avg_disagree > 0.20:
        print(f"    ✅ Good disagreement ({avg_disagree:.1%}): Models complement each other")
    elif avg_disagree > 0.10:
        print(f"    ⚡ Moderate disagreement ({avg_disagree:.1%}): Some complementarity")
    else:
        print(f"    ⚠️ Low disagreement ({avg_disagree:.1%}): Models are redundant")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def print_benchmark_baseline_summary(benchmark_tracker, baseline_tracker):
    """Print benchmark vs baseline final summary."""
    print(f"\n  ═══════════════════════════════════════════════════════════════")
    print(f"  ⭐ BENCHMARK vs BASELINE FINAL SUMMARY")
    print(f"  ═══════════════════════════════════════════════════════════════")
    
    print(f"\n  ─── BENCHMARK (Gates-only, works from iteration 1) ───")
    bench_total = benchmark_tracker['tp'] + benchmark_tracker['fp'] + benchmark_tracker['tn'] + benchmark_tracker['fn']
    bench_correct = benchmark_tracker['tp'] + benchmark_tracker['tn']
    bench_acc = bench_correct / bench_total if bench_total > 0 else 0.0
    bench_prec = benchmark_tracker['tp'] / (benchmark_tracker['tp'] + benchmark_tracker['fp']) if (benchmark_tracker['tp'] + benchmark_tracker['fp']) > 0 else 0.0
    bench_signal_rate = benchmark_tracker['signals'] / bench_total if bench_total > 0 else 0.0
    print(f"    Total Iterations:     {bench_total}")
    print(f"    TP: {benchmark_tracker['tp']:4d}  |  FP: {benchmark_tracker['fp']:4d}  |  TN: {benchmark_tracker['tn']:4d}  |  FN: {benchmark_tracker['fn']:4d}")
    print(f"    Accuracy:             {bench_acc:.2%}")
    print(f"    Precision (TP/TP+FP): {bench_prec:.2%}")
    print(f"    Signal Rate:          {bench_signal_rate:.2%} ({benchmark_tracker['signals']} signals)")
    
    print(f"\n  ─── BASELINE (Gates + EMA, valid after ~194 iters) ───")
    base_total = baseline_tracker['tp'] + baseline_tracker['fp'] + baseline_tracker['tn'] + baseline_tracker['fn']
    base_correct = baseline_tracker['tp'] + baseline_tracker['tn']
    base_acc = base_correct / base_total if base_total > 0 else 0.0
    base_prec = baseline_tracker['tp'] / (baseline_tracker['tp'] + baseline_tracker['fp']) if (baseline_tracker['tp'] + baseline_tracker['fp']) > 0 else 0.0
    base_signal_rate = baseline_tracker['signals'] / base_total if base_total > 0 else 0.0
    print(f"    Total Iterations:     {base_total}")
    print(f"    TP: {baseline_tracker['tp']:4d}  |  FP: {baseline_tracker['fp']:4d}  |  TN: {baseline_tracker['tn']:4d}  |  FN: {baseline_tracker['fn']:4d}")
    print(f"    Accuracy:             {base_acc:.2%}")
    print(f"    Precision (TP/TP+FP): {base_prec:.2%}")
    print(f"    Signal Rate:          {base_signal_rate:.2%} ({baseline_tracker['signals']} signals)")
    print(f"    Warmup Signals (no EMA): {baseline_tracker['warmup_signals']}")
    print(f"    Full Signals (with EMA): {baseline_tracker['full_signals']}")
    
    print(f"\n  ─── COMPARISON ───")
    acc_diff = base_acc - bench_acc
    prec_diff = base_prec - bench_prec
    print(f"    Accuracy Δ (Baseline - Benchmark): {acc_diff:+.2%}")
    print(f"    Precision Δ (Baseline - Benchmark): {prec_diff:+.2%}")
    if baseline_tracker['full_signals'] > 50:
        print(f"    Note: {baseline_tracker['full_signals']} signals had EMA scaling (after warmup)")
        if prec_diff > 0.01:
            print(f"    ✅ EMA scaling improving precision by {prec_diff:.2%}")
        elif prec_diff < -0.01:
            print(f"    ⚠️ EMA scaling reducing precision by {abs(prec_diff):.2%}")
        else:
            print(f"    ⚡ EMA scaling has minimal effect on precision")
    else:
        print(f"    ⚠️ Only {baseline_tracker['full_signals']} full signals - need more data for comparison")
    
    print(f"  ═══════════════════════════════════════════════════════════════")


def run_all_analysis(
    config_results, config_scorer, MULTI_CONFIG_TRACKING,
    walkforward_prediction_df, walkforward_iteration_df,
    iteration, WF_TRAIN, WF_VAL, WF_CAL,
    USE_AUTOMATIC_WINDOWS, DIAGNOSTICS, drift_alerts,
    hull_scorer_benchmark, hull_scorer_baseline,
    USE_SIGNAL_AGGREGATION, aggregated_feature_cols,
    calibration_diagnostics, model_diversity_metrics,
    benchmark_tracker, baseline_tracker
):
    """
    Run all analysis functions. Call this at the end of the walk-forward loop.
    """
    print_multi_config_summary(config_results, config_scorer, MULTI_CONFIG_TRACKING)
    
    print_walkforward_summary(
        walkforward_prediction_df, walkforward_iteration_df,
        iteration, WF_TRAIN, WF_VAL, WF_CAL,
        USE_AUTOMATIC_WINDOWS, DIAGNOSTICS, drift_alerts
    )
    
    print_ensemble_signal_summary(walkforward_iteration_df, walkforward_prediction_df, MULTI_CONFIG_TRACKING)
    
    print_hull_score_summary(hull_scorer_benchmark, hull_scorer_baseline, MULTI_CONFIG_TRACKING)
    
    print_signal_aggregation_summary(walkforward_prediction_df, USE_SIGNAL_AGGREGATION, aggregated_feature_cols)
    
    print_volatility_regime_summary(walkforward_prediction_df)
    
    print_precision_zone_summary(walkforward_prediction_df)
    
    print_calibration_diagnostics_summary(calibration_diagnostics)
    
    print_model_diversity_summary(model_diversity_metrics)
    
    print_benchmark_baseline_summary(benchmark_tracker, baseline_tracker)
    
    # ════════════════════════════════════════════════════════════════════════
    # SAVE DATA FOR POST-HOC ANALYSIS
    # ════════════════════════════════════════════════════════════════════════
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save predictions DataFrame
    pred_path = f'/media/przem/w/kaggle/analysis_data/walkforward_predictions_{timestamp}.csv'
    walkforward_prediction_df.to_csv(pred_path, index=False)
    print(f"\n  📊 Predictions saved: {pred_path}")
    
    # Save iterations DataFrame  
    iter_path = f'/media/przem/w/kaggle/analysis_data/walkforward_iterations_{timestamp}.csv'
    walkforward_iteration_df.to_csv(iter_path, index=False)
    print(f"  📊 Iterations saved:  {iter_path}")
    
    # Save config tracker data
    if MULTI_CONFIG_TRACKING and config_results:
        config_tracker_path = f'/media/przem/w/kaggle/analysis_data/config_tracker_{timestamp}.json'
        import json
        # Serialize config results
        config_data = {}
        for cfg_name, results in config_results.items():
            config_data[cfg_name] = {
                'config': results['config'],
                'total_predictions': results['total_predictions'],
                'total_correct': results['total_correct'],
                'rolling_tp': results['rolling_tp'],
                'rolling_fp': results['rolling_fp'],
                'rolling_tn': results['rolling_tn'],
                'rolling_fn': results['rolling_fn'],
            }
        with open(config_tracker_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"  📊 Config tracker:    {config_tracker_path}")
    
    print("\n" + "="*80)
