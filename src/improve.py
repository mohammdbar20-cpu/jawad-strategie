import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import backtest as B
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(os.path.dirname(__file__), '..', 'out')
T0, TS, T1 = pd.Timestamp('2015-01-01'), pd.Timestamp('2022-01-01'), pd.Timestamp('2026-01-01')
ctx = B.Ctx(); dp = dict(k=2.0, slB=1.0, minW=3.0, entry='confH1')
RANGES = {'2×ATR': {}, '40 $': dict(thr=('usd', 40), maxW=1e9), '2 %': dict(thr=('pct', 2), maxW=1e9), '3 %': dict(thr=('pct', 3), maxW=1e9)}
V = {}
for fam, extra in (('V1 Ausbruch', dict(mode='breakout')), ('V2 Ausbruch+Trendfilter', dict(mode='breakout', trend_filter=True)), ('V3 Retest', dict(mode='retest'))):
    for crit in ('C3', 'C4'):
        for rn, rk in RANGES.items():
            V[f'{fam} | {crit} | {rn}'] = (fam, dict(dp, crit=crit, **rk, **extra))
V['V2 Umkehr+Trendfilter'] = ('V2u', dict(dp, trend_filter=True))
V['V4 Umkehr 1-1-1-1, SL ab ½'] = ('V4', dict(dp, scale='flat', stop='late'))
V['V5 Umkehr swapfrei'] = ('V5', dict(dp, swap=False))
V['V5 Umkehr, Schließen vor Rollover'] = ('V5', dict(dp, rollover_close=True))
BASE = {'Basis: Umkehr Standard': dict(dp)}
R = {}; runs = {}
def p1(m):
    p = m.get('p_value')
    if p is None: return 1.0
    return p/2 if m['expectancy'] > 0 else 1 - p/2
for nm, (fam, kw) in list(V.items()) + [(k, ('base', v)) for k, v in BASE.items()]:
    r = B.run(ctx, **kw); runs[nm] = r
    d = {'IS 2015–2021': B.metrics(B.split(r, T0, TS)), 'OOS 2022–2025': B.metrics(B.split(r, TS, T1)), 'Gesamt': B.metrics(r)}
    tr = r['trades']
    if len(tr):
        d['Richtung'] = {('Long' if x == 1 else 'Short'): dict(n=int((tr.dir == x).sum()), net=round(float(tr[tr.dir == x].net.sum()), 2),
                          expectancy=round(float(tr[tr.dir == x].net.mean()), 2) if (tr.dir == x).any() else None) for x in (1, -1)}
    for per in ('IS 2015–2021', 'OOS 2022–2025', 'Gesamt'): d[per]['p_one_sided'] = round(p1(d[per]), 4)
    d['family'] = fam; R[nm] = d
    print(nm, {p: (d[p].get('n'), d[p].get('win_rate'), d[p].get('expectancy'), d[p].get('profit_factor'), d[p]['p_one_sided']) for p in ('IS 2015–2021', 'OOS 2022–2025')}, d.get('Richtung'))
def holm(ps):
    ps = np.array(ps, float); o = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0
    for r_, i in enumerate(o):
        run = max(run, min(1.0, (m - r_)*ps[i])); adj[i] = run
    return adj
names = list(V)
for per in ('IS 2015–2021', 'OOS 2022–2025', 'Gesamt'):
    for n, a in zip(names, holm([R[n][per]['p_one_sided'] for n in names])): R[n][per]['p_holm'] = round(float(a), 4)
# Walk-forward je Familie
WF = {}
for fam in ('V1 Ausbruch', 'V2 Ausbruch+Trendfilter', 'V3 Retest'):
    mem = [n for n in names if R[n]['family'] == fam]; parts = []; yrs = []
    for y in range(2018, 2026):
        a0, a1, a2 = pd.Timestamp(f'{y-3}-01-01'), pd.Timestamp(f'{y}-01-01'), pd.Timestamp(f'{y+1}-01-01')
        sc = []
        for n in mem:
            m = B.metrics(B.split(runs[n], a0, a1))
            if m['n'] >= 10: sc.append((m['profit_factor'] or 0, n))
        sc.sort(reverse=True); pick = sc[0][1]
        s = B.split(runs[pick], a1, a2); tm = B.metrics(s); parts.append(s['trades'])
        yrs.append(dict(year=y, pick=pick.split(' | ', 1)[1], train_pf=round(sc[0][0], 2), n=tm['n'], pf=tm.get('profit_factor'), net=tm.get('net_total')))
    wt = pd.concat(parts, ignore_index=True); eq = wt.net.cumsum(); dd = float((eq.cummax().clip(lower=0) - eq).max())
    tot = B.metrics(dict(trades=wt, maxdd=dd, peak_margin=0, ambig=0)); tot['p_one_sided'] = round(p1(tot), 4)
    WF[fam] = dict(years=yrs, total=tot)
    print('WF', fam, tot['n'], tot['expectancy'], tot['profit_factor'], tot['net_total'], tot['p_one_sided'])
# Robustheitsprüfung
rob = {}
for n in names:
    fam = R[n]['family']; wfpf = WF[fam]['total']['profit_factor'] if fam in WF else None
    ok = ((R[n]['IS 2015–2021'].get('profit_factor') or 0) > 1 and (R[n]['OOS 2022–2025'].get('profit_factor') or 0) > 1
          and (wfpf is None or wfpf > 1) and R[n]['OOS 2022–2025']['p_holm'] < 0.05)
    rob[n] = dict(robust=bool(ok), IS_pf=R[n]['IS 2015–2021'].get('profit_factor'), OOS_pf=R[n]['OOS 2022–2025'].get('profit_factor'),
                  WF_pf=wfpf, p_oos=R[n]['OOS 2022–2025']['p_one_sided'], p_holm_oos=R[n]['OOS 2022–2025']['p_holm'])
# Drift-Referenz: Buy&Hold 0,01 Lot
c = ctx.h4.c; bh = {'IS': round(float(c[:TS].iloc[-1] - c.iloc[0]), 2), 'OOS': round(float(c.iloc[-1] - c[TS:].iloc[0]), 2)}
out = dict(results=R, walkforward=WF, robust=rob, buy_hold_0_01lot_usd=bh, any_robust=any(v['robust'] for v in rob.values()))
def js(x):
    if isinstance(x, dict): return {str(k): js(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [js(v) for v in x]
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, np.floating): return float(x)
    if isinstance(x, np.bool_): return bool(x)
    return x
json.dump(js(out), open(OUT + '/improve.json', 'w'), indent=1, ensure_ascii=False, default=str)
print('ROBUST:', [n for n, v in rob.items() if v['robust']]); print('buy&hold', bh)
for n, v in rob.items(): print(n, v)
# Chart: Equity der Familien-Bestwerte + Basis
fig, ax = plt.subplots(figsize=(11, 4.5))
for n in ['Basis: Umkehr Standard', 'V1 Ausbruch | C4 | 2×ATR', 'V1 Ausbruch | C3 | 2×ATR', 'V2 Ausbruch+Trendfilter | C4 | 2×ATR', 'V3 Retest | C4 | 2×ATR', 'V2 Umkehr+Trendfilter', 'V5 Umkehr swapfrei']:
    ax.plot(runs[n]['eq'].index, runs[n]['eq'].values, label=n)
ax.axvline(TS, c='k', ls='--'); ax.axhline(0, c='#999', lw=.5); ax.legend(fontsize=7); ax.set_title('Equity ausgewählter Varianten (USD, 0,01 Lot, nach Kosten)')
fig.tight_layout(); fig.savefig(OUT + '/charts/improve.png', dpi=110)
