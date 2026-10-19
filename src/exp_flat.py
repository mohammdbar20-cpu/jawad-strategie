import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import backtest as B
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(os.path.dirname(__file__), '..', 'out')
T0, TS, T1 = pd.Timestamp('2015-01-01'), pd.Timestamp('2022-01-01'), pd.Timestamp('2026-01-01')
ctx = B.Ctx(); dp = dict(k=2.0, slB=1.0, minW=3.0, entry='confH1')
V = {'S0: 1 Position, fester SL': dict(scale='none', stop='fixed'),
     'S0b: 1 Position, SL stufenweise nachgezogen': dict(scale='none', stop='step'),
     'F1: 1-1-1-1, fester SL': dict(scale='flat', stop='fixed'),
     'F2: 1-1-1-1, SL stufenweise nachgezogen': dict(scale='flat', stop='step')}
R = {}; fig, ax = plt.subplots(figsize=(11, 4))
for nm, kw in V.items():
    r = B.run(ctx, **dp, **kw)
    R[nm] = {'IS 2015–2021': B.metrics(B.split(r, T0, TS)), 'OOS 2022–2025': B.metrics(B.split(r, TS, T1)), 'Gesamt': B.metrics(r)}
    ax.plot(r['eq'].index, r['eq'].values, label=nm.split(':')[0])
ax.axvline(TS, c='k', ls='--'); ax.axhline(0, c='#999', lw=.5); ax.legend(); ax.set_title('Equity: 1-1-1-1-Skalierung vs. ohne Skalierung (USD, nach Kosten)')
fig.tight_layout(); fig.savefig(OUT + '/charts/equity_flat.png', dpi=110)
def js(x):
    if isinstance(x, dict): return {str(k): js(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [js(v) for v in x]
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, np.floating): return float(x)
    return x
json.dump(js(R), open(OUT + '/flat.json', 'w'), indent=1, ensure_ascii=False, default=str)
K = ('n','win_rate','avg_win','avg_loss','expectancy','exp_ci95','profit_factor','net_total','max_dd','max_dd_pct','longest_losing_streak','peak_margin_1_100','peak_margin_1_500','max_units','costs_comm','costs_swap','ambiguous_bars')
for nm, d in R.items():
    print('==', nm)
    for p, m in d.items(): print('  ', p, {k: m.get(k) for k in K}, m['exit_reasons']); print('     ', {k: (v['n'], v['expectancy'], v['profit_factor']) for k, v in m['by_regime'].items()})
