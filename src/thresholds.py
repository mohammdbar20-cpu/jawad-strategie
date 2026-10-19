"""Nachtrag: ZigZag mit Mindest-Swinggröße (fest in $ bzw. % vom Preis) – Analyse A + Backtest."""
import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import data, core, analysis as AN, backtest as B
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(os.path.dirname(__file__), '..', 'out')
T0, TS, T1 = pd.Timestamp('2015-01-01'), pd.Timestamp('2022-01-01'), pd.Timestamp('2026-01-01')
CFG = [('2×ATR (Basis)', None), ('10 $', ('usd', 10)), ('20 $', ('usd', 20)), ('40 $', ('usd', 40)), ('100 $', ('usd', 100)),
       ('200 $', ('usd', 200)), ('1 %', ('pct', 1)), ('2 %', ('pct', 2)), ('3 %', ('pct', 3))]
NSUR = 10
h4 = data.get()['h4']; surs = [AN.surrogate(h4, s) for s in range(NSUR)]
ctx = B.Ctx()

def legs(df, thr):
    o, h, l, c = (df[x].values for x in 'ohlc'); a, _ = core.atr(h, l, c)
    piv = core.zigzag(h, l, a, 2.0, thr)
    sz = np.array([abs(b[1]-a_[1]) for a_, b in zip(piv[:-1], piv[1:])])
    pc = np.array([abs(b[1]-a_[1])/a_[1]*100 for a_, b in zip(piv[:-1], piv[1:])])
    bars = np.array([b[0]-a_[0] for a_, b in zip(piv[:-1], piv[1:])])
    yrs = (df.index[-1]-df.index[0]).days/365.25
    return dict(per_year=round(len(sz)/yrs, 1), n=int(len(sz)), usd_p25=round(float(np.percentile(sz, 25)), 1), usd_med=round(float(np.median(sz)), 1),
                usd_p75=round(float(np.percentile(sz, 75)), 1), pct_med=round(float(np.median(pc)), 2), bars_med=float(np.median(bars)),
                days_med=round(float(np.median(bars))/6, 1))

def excess(ev):
    return float(ev.win.mean() - ev.p0.mean()) if len(ev) else np.nan

R = {}; rows = []
for nm, thr in CFG:
    kw = {} if thr is None else dict(thr=thr, maxW=1e9)
    r = {'thr': thr}
    r['legs'] = legs(h4, thr)
    r['legs_null_per_year'] = round(float(np.mean([legs(s, thr)['per_year'] for s in surs[:3]])), 1)
    ev = AN.touch_events(h4, **kw)
    r['touch'] = {'Alle': AN.edge_test(ev), 'IS': AN.edge_test(ev[ev.t < TS]), 'OOS': AN.edge_test(ev[ev.t >= TS])}
    nul = [excess(AN.touch_events(s, **kw)) for s in surs]; nul = [x for x in nul if not np.isnan(x)]
    ex = excess(ev)
    r['touch_null'] = dict(real_excess=round(ex, 3), null_mean=round(float(np.mean(nul)), 3), null_sd=round(float(np.std(nul)), 3),
                           z_vs_null=round(float((ex - np.mean(nul))/np.std(nul)), 2) if np.std(nul) > 0 else None)
    bb = AN.between_breakouts(h4, **kw)
    r['between'] = {k: v for k, v in bb.items() if not k.startswith('_')}
    r['between_null_median'] = float(np.mean([AN.between_breakouts(s, **kw)['changes_median'] for s in surs[:5]]))
    bt = {}
    for snm, sc in (('ohne Skalierung', 'none'), ('1-1-1-1, fester SL', 'flat')):
        res = B.run(ctx, k=2.0, slB=1.0, minW=3.0, entry='confH1', scale=sc, stop='fixed', **kw)
        bt[snm] = {'IS 2015–2021': B.metrics(B.split(res, T0, TS)), 'OOS 2022–2025': B.metrics(B.split(res, TS, T1)), 'Gesamt': B.metrics(res)}
    r['backtest'] = bt
    R[nm] = r
    print(nm, r['legs'], r['legs_null_per_year'], r['touch']['Alle'], r['touch_null'], r['between']['changes_median'], r['between_null_median'])
    for snm, d in bt.items(): print('   ', snm, {p: (m.get('n'), m.get('win_rate'), m.get('expectancy'), m.get('profit_factor'), m.get('p_value'), m.get('max_dd')) for p, m in d.items()})

# Mehrfachtest-Korrektur (Holm) – Grenztest (9 Tests) und Backtests OOS (18 Tests)
def holm(ps):
    ps = np.array(ps, float); o = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0
    for r_, i in enumerate(o):
        run = max(run, min(1.0, (m - r_)*ps[i])); adj[i] = run
    return adj
names = list(R)
pt = [R[n]['touch']['Alle']['p_value'] for n in names]
for n, a in zip(names, holm(pt)): R[n]['touch']['Alle']['p_holm'] = round(float(a), 4)
keys = [(n, s) for n in names for s in R[n]['backtest']]
for per in ('IS 2015–2021', 'OOS 2022–2025', 'Gesamt'):
    pb = [R[n]['backtest'][s][per].get('p_value') or 1.0 for n, s in keys]
    for (n, s), a in zip(keys, holm(pb)): R[n]['backtest'][s][per]['p_holm'] = round(float(a), 4)
R['_meta'] = dict(n_surrogates=NSUR, note='touch: SL 1 ATR hinter Linie, Ziel Range-Mitte; Backtest: Standard (bestätigt H1, SL 1 ATR, Mindestbreite 3 ATR, keine Höchstbreite bei Schwellen-Varianten), Basiskosten')
def js(x):
    if isinstance(x, dict): return {str(k): js(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [js(v) for v in x]
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, np.floating): return float(x)
    return x
json.dump(js(R), open(OUT + '/thresholds.json', 'w'), indent=1, ensure_ascii=False, default=str)
# Chart
fig, ax = plt.subplots(1, 2, figsize=(12, 4))
x = np.arange(len(names))
ax[0].bar(x - .2, [R[n]['touch']['Alle']['win_rate']*100 for n in names], .4, label='echt: Umkehr bis Mitte', color='#c9a227')
ax[0].bar(x + .2, [R[n]['touch']['Alle']['expected_random']*100 for n in names], .4, label='Zufallserwartung', color='#999')
ax[0].set_xticks(x); ax[0].set_xticklabels(names, rotation=45, ha='right'); ax[0].set_ylabel('%'); ax[0].legend(); ax[0].set_title('Umkehrquote an der Range-Grenze')
for s, col in (('ohne Skalierung', '#3060b0'), ('1-1-1-1, fester SL', '#b03030')):
    ax[1].plot(x, [R[n]['backtest'][s]['IS 2015–2021'].get('profit_factor') or 0 for n in names], 'o--', c=col, label=s + ' IS')
    ax[1].plot(x, [R[n]['backtest'][s]['OOS 2022–2025'].get('profit_factor') or 0 for n in names], 's-', c=col, label=s + ' OOS')
ax[1].axhline(1, c='k', lw=.7); ax[1].set_xticks(x); ax[1].set_xticklabels(names, rotation=45, ha='right'); ax[1].legend(fontsize=8); ax[1].set_title('Profitfaktor nach Kosten')
fig.tight_layout(); fig.savefig(OUT + '/charts/thresholds.png', dpi=110)
