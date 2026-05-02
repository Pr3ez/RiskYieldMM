# Archive

This directory stores legacy implementations and historical documentation. It is
kept for context, not as the active source of truth.

| Location | Contents |
|---|---|
| [`2-Pipeline/`](2-Pipeline/) | Kaggle/Hull Tactical pipeline documentation |
| [`3-Walk_Forward_System/`](3-Walk_Forward_System/) | Older walk-forward system documentation |
| [`htf_stage1/`](htf_stage1/) | Archived Stage-1 notebook/scripts |
| [`backtest_backup_pre_refactor_2026-01-19/`](backtest_backup_pre_refactor_2026-01-19/) | Pre-refactor backtest module backup |
| [`previous_work/`](previous_work/) | Older experimental scripts and utilities |
| [`root_cleanup_20260429/`](root_cleanup_20260429/) | Prior root-cleanup artifacts |

Do not import from `Archive/` in current code. If legacy code contains API keys
or personal paths, treat it as historical only and rotate/revoke any exposed
secrets before public reuse.
