import sys, os, json, itertools, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import backtest as B
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(os.path.dirname(__file__), '..', 'out'); CH = OUT + '/charts'
T0, TS, T1 = pd.Timestamp('2015-01-01'), pd.Timestamp('2022-01-01'), pd.Timestamp('2026-01-01')
ctx = B.Ctx(); R = {}

def mm(res):
    return {'IS 2015–2021': B.metrics(B.split(res, T0, TS)), 'OOS 2022–2025': B.metrics(B.split(res, TS, T1)), 'Gesamt': B.metrics(res)}

def js(x):
    if isinstance(x, dict): return {str(k): js(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [js(v) for v in x]
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return float(x)
    return x

# 1) Parameter-Gitter (bewusst klein: 2x2x2x3 = 24 Varianten)
grid = list(itertools.product([2.0, 3.0], [0.5, 1.0], [3.0, 5.0], ['touch', 'confH1', 'confM15']))
G = []; runs = {}
for k, slB, minW, ent in grid:
    r = B.run(ctx, k=k, slB=slB, minW=minW, entry=ent); runs[(k, slB, minW, ent)] = r
    a = B.metrics(B.split(r, T0, TS)); b = B.metrics(B.split(r, TS, T1))
    G.append(dict(k=k, slB=slB, minW=minW, entry=ent, IS_n=a['n'], IS_exp=a['expectancy'], IS_pf=a['profit_factor'], IS_net=a['net_total'],
                  OOS_n=b['n'], OOS_exp=b['expectancy'], OOS_pf=b['profit_factor'], OOS_net=b['net_total']))
G = pd.DataFrame(G); R['grid'] = G.to_dict('records')
print(G.to_string())
best = G.sort_values('IS_pf', ascending=False).iloc[0]
bp = dict(k=best.k, slB=best.slB, minW=best.minW, entry=best.entry); R['best_IS_params'] = bp
R['share_IS_pf_gt1'] = float((G.IS_pf > 1).mean()); R['share_OOS_pf_gt1'] = float((G.OOS_pf > 1).mean())
dp = dict(k=2.0, slB=1.0, minW=3.0, entry='confH1'); R['default_params'] = dp

R['main'] = {}
for ent in ('touch', 'confH1', 'confM15'):
    R['main'][ent] = mm(runs[(2.0, 1.0, 3.0, ent)])
R['best_IS_run'] = mm(runs[(bp['k'], bp['slB'], bp['minW'], bp['entry'])])

wf = []; parts = []
for y in range(2018, 2026):
    a0, a1 = pd.Timestamp(f'{y-3}-01-01'), pd.Timestamp(f'{y}-01-01')
    sc = []
    for key, r in runs.items():
        m = B.metrics(B.split(r, a0, a1))
        if m['n'] >= 15: sc.append((m['profit_factor'] or 0, key))
    sc.sort(reverse=True); key = sc[0][1]
    s = B.split(runs[key], a1, pd.Timestamp(f'{y+1}-01-01'))
    tm = B.metrics(s); parts.append(s['trades'])
    wf.append(dict(year=y, params=dict(k=key[0], slB=key[1], minW=key[2], entry=key[3]), train_pf=round(sc[0][0], 2),
                   test_n=tm['n'], test_pf=tm.get('profit_factor'), test_net=tm.get('net_total'), test_exp=tm.get('expectancy')))
wt = pd.concat(parts, ignore_index=True)
eq = wt.net.cumsum(); wdd = float((eq.cummax().clip(lower=0) - eq).max())
R['walkforward'] = dict(years=wf, total=B.metrics(dict(trades=wt, maxdd=wdd, peak_margin=0, ambig=0)))

SC = {}
for nm, kw in (('S0: 1 Position, fester SL', dict(scale='none', stop='fixed')),
               ('S0b: 1 Position, SL stufenweise nachgezogen', dict(scale='none', stop='step')),
               ('S1: Pyramide 1-2-4-8, fester SL', dict(scale='pyr', stop='fixed')),
               ('S2: Pyramide 1-2-4-8, SL stufenweise nachgezogen', dict(scale='pyr', stop='step')),
               ('S3: wie S1 + Risiko-Limit 200 $ je Korb (Nachkauf nur, wenn Verlust bei SL ≤ 200 $)', dict(scale='pyr', stop='fixed', risk_cap=200.0))):
    SC[nm] = mm(B.run(ctx, **dp, **kw))
SC['S2-touch: Pyramide, nachgezogen, Touch-Einstieg'] = mm(B.run(ctx, k=2.0, slB=1.0, minW=3.0, entry='touch', scale='pyr', stop='step'))
R['scaling'] = SC

CS = {}
for nm, kw in (('Spread 0,20 $ / Slippage 0,05', dict(spread=0.20)), ('Spread 0,30 $ / Slippage 0,05 (Basis)', dict(spread=0.30)),
               ('Spread 0,35 $ / Slippage 0,10', dict(spread=0.35, slip=0.10)), ('Echter Dukascopy-Spread (Ask-Daten) / Slip 0,05', dict(spread='data')),
               ('Ohne jegliche Kosten (nur Referenz)', dict(spread=0.0, slip=0.0, comm_lot=0.0, swap=False))):
    CS[nm] = mm(B.run(ctx, **dp, **kw))
R['costs'] = CS
BC = {}
for crit in ('C1', 'C2', 'C3', 'C4', 'C34'):
    BC[crit] = mm(B.run(ctx, k=2.0, slB=1.0, minW=3.0, entry='confH1', crit=crit))
R['crit_in_strategy'] = BC
json.dump(js(R), open(OUT + '/backtest.json', 'w'), indent=1, ensure_ascii=False, default=str)

fig, ax = plt.subplots(figsize=(11, 4))
for ent, colr in (('touch', '#b03030'), ('confH1', '#c9a227'), ('confM15', '#3060b0')):
    r = runs[(2.0, 1.0, 3.0, ent)]; ax.plot(r['eq'].index, r['eq'].values, label={'touch': 'Touch-Einstieg', 'confH1': 'Bestätigte Umkehr (H1)', 'confM15': 'Bestätigte Umkehr (M15)'}[ent], c=colr)
ax.axvline(TS, c='k', ls='--'); ax.text(TS, ax.get_ylim()[1]*0.9, '  Out-of-Sample →'); ax.axhline(0, c='#999', lw=.5)
ax.set_title('Equity (USD, 0,01 Lot je Trade, nach Kosten) – Standardparameter'); ax.legend(); fig.tight_layout(); fig.savefig(CH + '/equity_entries.png', dpi=110); plt.close()
fig, ax = plt.subplots(figsize=(11, 4))
for nm, kw in (('S0 1 Position', dict(scale='none')), ('S1 Pyramide fester SL', dict(scale='pyr')), ('S2 Pyramide nachgez. SL', dict(scale='pyr', stop='step')), ('S3 S1 + Risiko-Limit 200 $', dict(scale='pyr', stop='fixed', risk_cap=200.0))):
    r = B.run(ctx, **dp, **kw); ax.plot(r['eq'].index, r['eq'].values, label=nm)
ax.axvline(TS, c='k', ls='--'); ax.axhline(0, c='#999', lw=.5); ax.set_title('Equity der Skalierungsvarianten (USD, nach Kosten)'); ax.legend(); fig.tight_layout(); fig.savefig(CH + '/equity_scaling.png', dpi=110); plt.close()
fig, ax = plt.subplots(figsize=(11, 3.5)); ax.plot(pd.to_datetime(wt.exit_t), eq.values, c='#555')
ax.set_title('Walk-Forward 2018–2025: kumulierter Netto-Gewinn (USD), Parameter jeweils aus den 3 Vorjahren'); ax.axhline(0, c='#999', lw=.5)
fig.tight_layout(); fig.savefig(CH + '/walkforward.png', dpi=110); plt.close()
print(json.dumps(js({k: R[k] for k in ('best_IS_params', 'share_IS_pf_gt1', 'share_OOS_pf_gt1', 'walkforward')}), indent=1, default=str))
