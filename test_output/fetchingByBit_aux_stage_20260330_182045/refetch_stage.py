import importlib.util
from pathlib import Path

repo = Path('/media/przem/linux_data/RiskYieldMM (Copy)')
mod_path = repo / 'fetchingByBit' / 'fetch_bybit_market_data.py'
spec = importlib.util.spec_from_file_location('fbm', mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.BASE_DIR = str((repo / 'test_output' / 'fetchingByBit_aux_stage_20260330_182045').resolve())
mod.SYMBOL = 'BTCUSDT'
mod.CATEGORY = 'linear'
mod.START_DATE = '2021-01-01'
mod.END_DATE = 'now'

intervals = ['1', '5', '15', '60', '240']
for data_type in ['mark', 'index', 'premium']:
    for itv in intervals:
        lbl = mod.LABELS[itv]
        print(f'RUN {data_type} {itv} {lbl}', flush=True)
        mod.fetch_mark_index_premium(mod.SYMBOL, mod.CATEGORY, itv, lbl, mod.START_DATE, mod.END_DATE, data_type)
