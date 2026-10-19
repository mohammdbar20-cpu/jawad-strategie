"""Teil A + E: statistische Analyse der H4-Swings, Ranges, Grenzberührungen und Ausbruchskriterien."""
import sys, os, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import data, core
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(os.path.dirname(__file__), '..', 'out'); CH = OUT + '/charts'
IS_END = pd.Timestamp('2022-01-01')
RES = {}

def surrogate(h4, seed):
    """Nullmodell: Kerzen (relativ zum Open) zufällig permutiert -> gleiche Kerzenverteilung,
    aber keine zeitliche Struktur (keine Autokorrelation, keine Volatilitäts-Cluster)."""
    rng = np.random.default_rng(seed)
    o, h, l, c = (h4[x].values for x in 'ohlc')
    po = np.r_[c[0], c[:-1]]
    g = np.log(o/po); rh = np.log(h/o); rl = np.log(l/o); rc = np.log(c/o)
    idx = rng.permutation(len(o))
    g, rh, rl, rc = g[idx], rh[idx], rl[idx], rc[idx]
    oo = np.empty(len(o)); cc = np.empty(len(o)); prev = c[0]
    for i in range(len(o)):
        oo[i] = prev*np.exp(g[i]); cc[i] = oo[i]*np.exp(rc[i]); prev = cc[i]
    df = pd.DataFrame({'o': oo, 'h': oo*np.exp(rh), 'l': oo*np.exp(rl), 'c': cc}, index=h4.index)
    return df

def legs_table(h4, k):
    o, h, l, c = (h4[x].values for x in 'ohlc')
    a, tr = core.atr(h, l, c); piv = core.zigzag(h, l, a, k)
    reg, _ = core.regime(c)
    rows = []
    for p0, p1 in zip(piv[:-1], piv[1:]):
        i0, i1 = p0[0], p1[0]
        rows.append(dict(t0=h4.index[i0], dir=1 if p1[2] == 1 else -1, size=abs(p1[1]-p0[1]),
                         atr=a[i0], bars=i1-i0, reg=reg[i0], hour=h4.index[i1].hour, conf_lag=p1[3]-p1[0]))
    df = pd.DataFrame(rows); df['size_atr'] = df['size']/df['atr']
    return df, piv, a

def part_a_swings(h4):
    out = {}
    for k in (2.0, 3.0):
        df, piv, a = legs_table(h4, k)
        df = df.dropna()
        r = {'n_legs': int(len(df)), 'legs_per_year': round(len(df)/11.0, 1),
             'size_usd_median': round(df['size'].median(), 2), 'size_usd_mean': round(df['size'].mean(), 2),
             'size_atr_median': round(df.size_atr.median(), 2), 'bars_median': float(df.bars.median()),
             'conf_lag_median_bars': float(df.conf_lag.median())}
        byreg = {}
        for rg, nm in ((1, 'Aufwärtstrend'), (-1, 'Abwärtstrend'), (0, 'Seitwärts')):
            s = df[df.reg == rg]
            byreg[nm] = {'legs': int(len(s)), 'up_legs': int((s.dir == 1).sum()), 'down_legs': int((s.dir == -1).sum()),
                         'up_size_atr': round(s[s.dir == 1].size_atr.median(), 2), 'down_size_atr': round(s[s.dir == -1].size_atr.median(), 2),
                         'up_bars': float(s[s.dir == 1].bars.median()), 'down_bars': float(s[s.dir == -1].bars.median())}
        r['by_regime'] = byreg
        # Korrekturen nach starken Bewegungen
        sz = df.size_atr.values; nxt = np.r_[sz[1:], np.nan] / sz
        strong = sz >= np.nanpercentile(sz, 75)
        corr = {}
        for nm, m in (('stark (oberstes Quartil)', strong), ('übrige', ~strong)):
            x = nxt[m]; x = x[~np.isnan(x)]
            corr[nm] = {'n': int(len(x)), **{f'retr_ge_{q}': round(float((x >= q).mean()), 3) for q in (0.382, 0.5, 0.618, 1.0)},
                        'median_retr': round(float(np.median(x)), 3)}
        r['corrections'] = corr
        # Zeit des Tages: Stunde der Pivot-Kerze
        r['pivot_hour_share'] = (df.hour.value_counts(normalize=True).sort_index().round(3)).to_dict()
        r['_df'] = df
        out[k] = r
    return out

def zigzag_repeat(h4, k=2.0, tol=1.0):
    o, h, l, c = (h4[x].values for x in 'ohlc')
    a, _ = core.atr(h, l, c); piv = core.zigzag(h, l, a, k)
    runs = []; run = 0; lastH = lastL = None
    for p in piv:
        ref = lastH if p[2] == 1 else lastL
        if ref is not None and abs(p[1]-ref) <= tol*a[p[3]]: run += 1
        else:
            if run: runs.append(run)
            run = 0
        if p[2] == 1: lastH = p[1]
        else: lastL = p[1]
    runs.append(run)
    runs = np.array([r for r in runs if r > 0])
    share = runs.sum()/len(piv)
    return dict(n_pivots=len(piv), share_repeating=round(float(share), 3), runs=int(len(runs)),
                run_median=float(np.median(runs)) if len(runs) else 0, run_p90=float(np.percentile(runs, 90)) if len(runs) else 0)

def between_breakouts(h4, k=2.0, crit='C34', **kw):
    st = core.range_state(h4, k=k, crit=crit, **kw)
    bos = np.where(st['bo'] != 0)[0]; conf = np.array([p[3] for p in st['piv']])
    cnt = [int(((conf > b0) & (conf <= b1)).sum()) for b0, b1 in zip(bos[:-1], bos[1:])]
    dur = np.diff(bos)
    return dict(n_breakouts=int(len(bos)), per_year=round(len(bos)/11, 1), changes_median=float(np.median(cnt)),
                changes_p25=float(np.percentile(cnt, 25)), changes_p75=float(np.percentile(cnt, 75)),
                bars_between_median=float(np.median(dur)), _cnt=cnt)

def touch_events(h4, k=2.0, crit='C34', sl_atr=1.0, target='mid', **kw):
    """Jede Berührung einer gültigen Range-Grenze (Kurs erreicht die Linie). Ergebnis: wird zuerst das
    Ziel (Mitte bzw. Gegenlinie) oder der Stop (Linie ± sl_atr*ATR) erreicht? Konservativ: beide in
    derselben Kerze = Verlust. p0 = Trefferwahrscheinlichkeit einer driftfreien Irrfahrt = SL/(SL+TP)."""
    o, h, l, c = (h4[x].values for x in 'ohlc'); n = len(c)
    st = core.range_state(h4, k=k, crit=crit, **kw); a = st['atr']
    reg, _ = core.regime(c); volr = a / pd.Series(a).rolling(100).mean().values
    ev = []; i = 1; used = set()
    while i < n:
        if st['valid'][i-1]:
            U, L, A = st['U'][i-1], st['L'][i-1], a[i-1]; key = st['rid'][i-1]
            for d in (-1, 1):  # -1 = Short an der Oberkante, +1 = Long an der Unterkante
                if (key, d) in used: continue
                if (d == -1 and h[i] >= U) or (d == 1 and l[i] <= L):
                    used.add((key, d))
                    e = U if d == -1 else L
                    tp = ((U+L)/2 if target == 'mid' else (L + 0.1*A if d == -1 else U - 0.1*A))
                    sl = e - d*sl_atr*A
                    res = None
                    for j in range(i, min(n, i+300)):
                        hit_sl = (h[j] >= sl) if d == -1 else (l[j] <= sl)
                        hit_tp = (l[j] <= tp) if d == -1 else (h[j] >= tp)
                        if j == i: hit_tp = hit_tp and (c[i] < e if d == -1 else c[i] > e) and False
                        if hit_sl: res = 0; break
                        if hit_tp: res = 1; break
                    if res is None: continue
                    dtp, dsl = abs(e-tp), abs(sl-e)
                    ev.append(dict(t=h4.index[i], d=d, win=res, p0=dsl/(dsl+dtp), rr=dtp/dsl, reg=reg[i-1],
                                   with_trend=int(reg[i-1] == d), counter=int(reg[i-1] == -d), hour=h4.index[i].hour,
                                   volr=volr[i-1], R=(dtp/dsl if res else -1.0)))
        i += 1
    return pd.DataFrame(ev)

def edge_test(df):
    if len(df) == 0: return {}
    n = len(df); w = df.win.sum(); e = df.p0.sum(); var = (df.p0*(1-df.p0)).sum()
    z = (w - e)/np.sqrt(var); p = 2*(1-stats.norm.cdf(abs(z)))
    t = stats.ttest_1samp(df.R, 0)
    return dict(n=int(n), win_rate=round(w/n, 3), expected_random=round(e/n, 3), z=round(float(z), 2), p_value=round(float(p), 4),
                mean_R_gross=round(float(df.R.mean()), 3), t_R=round(float(t.statistic), 2), p_R=round(float(t.pvalue), 4))

def breakout_eval(h4, k=2.0):
    o, h, l, c = (h4[x].values for x in 'ohlc'); n = len(c)
    reg, _ = core.regime(c)
    out = {}
    for crit in core.BO_CRITERIA:
        st = core.range_state(h4, k=k, crit=crit); a = st['atr']
        rows = []
        for i in np.where(st['bo'] != 0)[0]:
            d = st['bo'][i]
            # Range vor dem Ausbruch rekonstruieren: letzte gültige Werte vor i
            j = i-1
            while j > 0 and np.isnan(st['U'][j]): j -= 1
            U, L, A = st['U'][j], st['L'][j], a[i-1]
            if np.isnan(U): continue
            line = U if d == 1 else L
            ent = c[i]; tgt = ent + d*2*A; back = line - d*0.5*A
            # Verzögerung: erste Kerze, deren Docht die Linie überschritt
            f = i
            while f > j and ((h[f-1] > U) if d == 1 else (l[f-1] < L)): f -= 1
            res = None
            for m in range(i+1, min(n, i+300)):
                hb = (l[m] <= back) if d == 1 else (h[m] >= back)
                ht = (h[m] >= tgt) if d == 1 else (l[m] <= tgt)
                if hb: res = 0; break
                if ht: res = 1; break
            if res is None: continue
            dist_back = abs(ent-back)
            after = c[min(n-1, i+30)]
            rows.append(dict(t=h4.index[i], d=d, win=res, p0=dist_back/(dist_back+2*A), lag=i-f,
                             beyond_atr=abs(ent-line)/A, counter=int(reg[i-1] == -d),
                             cont30=int((after-line)*d > 0)))
        df = pd.DataFrame(rows)
        res = {}
        for nm, s in (('IS', df[df.t < IS_END]), ('OOS', df[df.t >= IS_END]), ('Alle', df)):
            if len(s) == 0: continue
            w = s.win.sum(); e = s.p0.sum(); z = (w-e)/np.sqrt((s.p0*(1-s.p0)).sum())
            res[nm] = dict(n=int(len(s)), follow_through=round(w/len(s), 3), random=round(e/len(s), 3), z=round(float(z), 2),
                           lag_bars=round(float(s.lag.mean()), 2), beyond_atr=round(float(s.beyond_atr.mean()), 2),
                           cont30=round(float(s.cont30.mean()), 3),
                           counter_trend_cont30=round(float(s[s.counter == 1].cont30.mean()), 3) if (s.counter == 1).any() else None,
                           with_or_neutral_cont30=round(float(s[s.counter == 0].cont30.mean()), 3))
        out[crit] = res
    return out

def main():
    d = data.get(); h4 = d['h4']
    A = part_a_swings(h4)
    RES['swings'] = {str(k): {kk: vv for kk, vv in v.items() if not kk.startswith('_')} for k, v in A.items()}
    nulls = [part_a_swings(surrogate(h4, s)) for s in range(10)]
    for k in (2.0, 3.0):
        RES['swings'][str(k)]['corrections_null'] = {nm: {q: round(float(np.mean([nl[k]['corrections'][nm][q] for nl in nulls])), 3)
            for q in nulls[0][k]['corrections'][nm]} for nm in nulls[0][k]['corrections']}
        RES['swings'][str(k)]['null_legs_per_year'] = round(float(np.mean([nl[k]['legs_per_year'] for nl in nulls])), 1)
        RES['swings'][str(k)]['null_size_atr_median'] = round(float(np.mean([nl[k]['size_atr_median'] for nl in nulls])), 2)
    # Wiederholende ZigZags: echt vs Nullmodell
    rz = zigzag_repeat(h4); sur = [zigzag_repeat(surrogate(h4, s)) for s in range(20)]
    RES['zigzag_repeat'] = dict(real=rz, null_mean=round(float(np.mean([s['share_repeating'] for s in sur])), 3),
                                null_sd=round(float(np.std([s['share_repeating'] for s in sur])), 3))
    bb = between_breakouts(h4); bbs = [between_breakouts(surrogate(h4, s))['changes_median'] for s in range(20)]
    RES['between_breakouts'] = {k: v for k, v in bb.items() if not k.startswith('_')}; RES['between_breakouts']['null_median_mean'] = float(np.mean(bbs))
    # Grenzberührungen (Kern-Edge-Test)
    touch = {}
    for k in (2.0, 3.0):
        for tg in ('mid', 'opp'):
            ev = touch_events(h4, k=k, target=tg)
            key = f'k{k}_{tg}'
            r = {'Alle': edge_test(ev), 'IS': edge_test(ev[ev.t < IS_END]), 'OOS': edge_test(ev[ev.t >= IS_END])}
            for rg, nm in ((1, 'Aufwärtstrend'), (-1, 'Abwärtstrend'), (0, 'Seitwärts')):
                r['Regime: '+nm] = edge_test(ev[ev.reg == rg])
            r['Mit Trend'] = edge_test(ev[ev.with_trend == 1]); r['Gegen Trend'] = edge_test(ev[ev.counter == 1])
            q = ev.volr.quantile([1/3, 2/3]).values
            r['Vola niedrig'] = edge_test(ev[ev.volr <= q[0]]); r['Vola mittel'] = edge_test(ev[(ev.volr > q[0]) & (ev.volr <= q[1])]); r['Vola hoch'] = edge_test(ev[ev.volr > q[1]])
            for hr in sorted(ev.hour.unique()):
                r[f'Uhrzeit {hr:02d}-{hr+4:02d} UTC'] = edge_test(ev[ev.hour == hr])
            r['Short (Oberkante)'] = edge_test(ev[ev.d == -1]); r['Long (Unterkante)'] = edge_test(ev[ev.d == 1])
            touch[key] = r
            if key == 'k2.0_mid':
                sres = [edge_test(touch_events(surrogate(h4, s), k=k, target=tg))['win_rate'] - edge_test(touch_events(surrogate(h4, s), k=k, target=tg))['expected_random'] for s in range(10)]
                touch['null_k2_mid_excess'] = dict(mean=round(float(np.mean(sres)), 3), sd=round(float(np.std(sres)), 3))
    RES['touch'] = touch
    RES['breakout'] = breakout_eval(h4)
    json.dump(RES, open(OUT+'/analysis.json', 'w'), indent=1, ensure_ascii=False, default=str)
    charts(h4, A, bb)
    print(json.dumps(RES, indent=1, ensure_ascii=False, default=str)[:20000])

def charts(h4, A, bb):
    df = A[2.0]['_df']
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
    ax[0].hist(df.size_atr.clip(upper=15), bins=60, color='#c9a227'); ax[0].set_title('Swing-Größe (k=2) in ATR(14,H4)'); ax[0].set_xlabel('ATR-Vielfache')
    sz = df.size_atr.values; nxt = sz[1:]/sz[:-1]; strong = sz[:-1] >= np.percentile(sz, 75)
    ax[1].hist(np.clip(nxt[strong], 0, 3), bins=40, alpha=.7, label='nach starkem Swing', color='#b03030', density=True)
    ax[1].hist(np.clip(nxt[~strong], 0, 3), bins=40, alpha=.5, label='nach übrigen', color='#3060b0', density=True)
    for q in (0.382, 0.5, 0.618): ax[1].axvline(q, ls=':', c='k')
    ax[1].legend(); ax[1].set_title('Gegenbewegung / vorheriger Swing'); fig.tight_layout(); fig.savefig(CH+'/swings.png', dpi=110); plt.close()
    fig, ax = plt.subplots(figsize=(6, 3.4)); ax.hist(np.clip(bb['_cnt'], 0, 30), bins=30, color='#555')
    ax.set_title('Richtungswechsel (Pivots) zwischen zwei Ausbrüchen (C3/C4)'); fig.tight_layout(); fig.savefig(CH+'/changes.png', dpi=110); plt.close()
    # Beispielchart
    s = h4.loc['2019-03-01':'2019-07-15']; st = core.range_state(h4, k=2.0, crit='C34')
    off = h4.index.get_loc(s.index[0]); m = len(s)
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(m)
    ax.vlines(x, s.l, s.h, color='#999', lw=1); ax.plot(x, s.c.values, c='#333', lw=.7)
    pv = [p for p in st['piv'] if off <= p[0] < off+m]
    ax.plot([p[0]-off for p in pv], [p[1] for p in pv], c='#c9a227', lw=2, marker='o', ms=4, label='ZigZag (bestätigte Pivots)')
    ax.plot(x, st['U'][off:off+m], c='#b03030', lw=1.5, label='Oberkante (dyn.)'); ax.plot(x, st['L'][off:off+m], c='#2a8a3a', lw=1.5, label='Unterkante (dyn.)')
    b = np.where(st['bo'][off:off+m] != 0)[0]
    ax.scatter(b, s.c.values[b], marker='*', s=160, c=['g' if st['bo'][off+i] > 0 else 'r' for i in b], zorder=5, label='bestätigter Ausbruch (C3/C4)')
    ticks = x[::60]; ax.set_xticks(ticks); ax.set_xticklabels([s.index[i].strftime('%d.%m.%y') for i in ticks])
    ax.legend(loc='upper left', fontsize=8); ax.set_title('XAUUSD H4 – ZigZag, dynamische Range und Ausbrüche (Beispiel 2019)')
    fig.tight_layout(); fig.savefig(CH+'/example_2019.png', dpi=110); plt.close()

if __name__ == '__main__':
    main()
