"""Teil C/D/F: ereignisbasierter Backtest auf M15 (Fills), Signale aus H4 (Range) und H1/M15 (Bestätigung)."""
import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import data, core

FED = {2015: .0013, 2016: .004, 2017: .010, 2018: .018, 2019: .022, 2020: .004, 2021: .001, 2022: .017,
       2023: .050, 2024: .051, 2025: .043}   # ANNAHME: US-Leitzins-Jahresmittel als Swap-Basis

class Ctx:
    def __init__(self):
        d = data.get(); self.m15 = d['m15']; self.h4 = d['h4']
        m = self.m15
        self.t = m.index; self.o, self.h, self.l, self.c = (m[x].values for x in 'ohlc')
        self.sp_o = (m.ao - m.o).values; self.sp_h = (m.ah - m.h).values; self.sp_l = (m.al - m.l).values
        self.hi = np.searchsorted(self.h4.index.values, m.index.values, side='right') - 1
        self.year = m.index.year.values
        sday = (m.index + pd.Timedelta(hours=2)).normalize()  # Server-Tag (UTC+2)
        self.daychg = np.r_[False, sday[1:] != sday[:-1]]
        self.prevwd = np.r_[0, sday[:-1].weekday]
        # H1-Bestätigungskerzen: Ende jeder Stunde
        hr = m.index.floor('h'); last = np.r_[hr[1:] != hr[:-1], True]
        g = m.groupby(hr).agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'))
        gp = g.shift(1)
        self.h1_end = last
        self.h1_o = g.o.reindex(hr).values; self.h1_c = g.c.reindex(hr).values
        self.h1_pl = gp.l.reindex(hr).values; self.h1_ph = gp.h.reindex(hr).values
        self.m15_pl = np.r_[np.nan, self.l[:-1]]; self.m15_ph = np.r_[np.nan, self.h[:-1]]
        self.reg, _ = core.regime(self.h4.c.values)
        self._st = {}
    def state(self, k, crit, minW):
        key = (k, crit, minW)
        if key not in self._st: self._st[key] = core.range_state(self.h4, k=k, crit=crit, minW=minW)
        return self._st[key]

def run(ctx, k=2.0, crit='C34', minW=3.0, slB=1.0, entry='confH1', scale='none', stop='fixed',
        spread=0.30, slip=0.05, comm_lot=7.0, swap=True, risk_cap=None, lev=100, zone=0.25, tp_buf=0.1,
        expiry_h=24, rr_min=1.0, bo_exit=True, start=None, end=None):
    st = ctx.state(k, crit, minW)
    U_, L_, V_, R_, A_, BO_ = st['U'], st['L'], st['valid'], st['rid'], st['atr'], st['bo']
    o, h, l, c, hi = ctx.o, ctx.h, ctx.l, ctx.c, ctx.hi
    n = len(o); units = [1, 2, 4, 8] if scale == 'pyr' else [1, 1, 1, 1] if scale == 'flat' else ([1, 0, 0, 0] if stop == 'step' else [1])
    fr = [0, .25, .5, .75]
    j0 = 0 if start is None else int(np.searchsorted(ctx.t.values, np.datetime64(start)))
    j1 = n if end is None else int(np.searchsorted(ctx.t.values, np.datetime64(end)))
    comm_u = comm_lot / 100.0
    pos = []  # (dir, preis, einheiten)
    bk = None; trades = []; blocked = set(); armed = None; pend = None
    realized = 0.0; peak = 0.0; maxdd = 0.0; peak_margin = 0.0; ambig = 0
    eq_t = []; eq_v = []
    def S(j, which='o'):
        if spread == 'data':
            return max(0.0, {'o': ctx.sp_o, 'h': ctx.sp_h, 'l': ctx.sp_l}[which][j])
        return spread
    def close_all(j, px_bid, reason):
        nonlocal bk, pos, realized
        d = bk['dir']; pnl = 0.0
        for (dd, p, u) in pos:
            ex = px_bid if d == 1 else px_bid + S(j)
            pnl += d*(ex - p)*u
        bk['gross'] += pnl; net = bk['gross'] - bk['comm'] - bk['swap']
        realized += pnl
        bk.update(exit_t=ctx.t[j], reason=reason, net=net, units=sum(u for _, _, u in pos), npos=len(pos))
        trades.append(bk); blocked.add((bk['rid'], d)); bk = None; pos = []
    def open_pos(j, d, px_bid_fill, u):
        nonlocal realized
        p = px_bid_fill + (S(j) if d == 1 else 0.0)
        pos.append((d, p, u)); bk['comm'] += comm_u*u; realized -= comm_u*u
        return p
    for j in range(j0, j1):
        g = hi[j] - 1
        if g < 1: continue
        # Swap an Tageswechsel (Server UTC+2), Mittwoch dreifach
        if ctx.daychg[j] and pos and swap:
            r = FED.get(int(ctx.year[j]), .02); px = o[j]; mult = 3 if ctx.prevwd[j] == 2 else 1
            for (d, p, u) in pos:
                cost = px*(r + .03)/360 if d == 1 else px*max(.03 - r, .005)/360
                bk['swap'] += cost*u*mult; realized -= cost*u*mult
        A = A_[g]
        # ausstehender Markteinstieg (Bestätigung) zur Eröffnung dieser Kerze
        if pend is not None and bk is None:
            d, sl, tp, rid = pend; pend = None
            if V_[g] and R_[g] == rid:
                fill = o[j] + d*slip
                e = fill + (S(j) if d == 1 else 0)
                if d*(tp - e) >= rr_min*d*(e - sl) and d*(tp - e) > 0:
                    bk = dict(dir=d, entry_t=ctx.t[j], E=e, sl=sl, tp=tp, D=abs(tp - e), adds=1, rid=rid, reg=int(ctx.reg[g]),
                              gross=0.0, comm=0.0, swap=0.0, atr=A, U=U_[g], L=L_[g], mode=entry)
                    open_pos(j, d, fill, units[0])
        if bk is not None:
            d = bk['dir']; s_o = S(j); s_h = S(j, 'h'); s_l = S(j, 'l')
            # Ausbruch gegen die Position bestätigt -> Ausstieg zur Eröffnung
            if bo_exit and BO_[g] == -d and ctx.hi[j-1] != hi[j]:
                close_all(j, o[j] - d*slip if d == 1 else o[j] + slip, 'Ausbruch'); 
            else:
                # Gap über SL?
                adv_open = o[j] if d == 1 else o[j] + s_o
                if d*(adv_open - bk['sl']) <= 0:
                    close_all(j, o[j] - slip if d == 1 else o[j] + slip, 'SL(Gap)')
                else:
                    # Nachkäufe (nur in Gewinnrichtung)
                    hit_any_add = False
                    while bk['adds'] < len(units):
                        lvl = bk['E'] + d*fr[bk['adds']]*bk['D']
                        fav = (h[j] + s_h) if d == 1 else l[j]   # Long-Stop kauft am Ask, Short-Stop verkauft am Bid
                        if d*(fav - lvl) < 0: break
                        u = units[bk['adds']]
                        if risk_cap is not None:
                            new_sl = bk['sl'] if stop == 'fixed' else bk['E'] + d*fr[bk['adds']-1]*bk['D']
                            risk = sum(d*(p - new_sl)*uu for _, p, uu in pos) + d*(lvl - new_sl)*u
                            if risk > risk_cap: bk['adds'] = len(units); break
                        fill_b = (lvl - (s_o if d == 1 else 0)) + d*slip
                        if d*(o[j] - lvl) > 0: fill_b = o[j] + d*slip
                        if u > 0: open_pos(j, d, fill_b, u)
                        hit_any_add = True
                        if stop == 'step': bk['sl'] = bk['E'] + d*fr[bk['adds']-1]*bk['D']
                        bk['adds'] += 1
                    adv = l[j] if d == 1 else h[j] + s_h
                    favx = h[j] if d == 1 else l[j] + s_l
                    hit_sl = d*(adv - bk['sl']) <= 0; hit_tp = d*(favx - bk['tp']) >= 0
                    if hit_sl:
                        if hit_tp: ambig += 1
                        px = bk['sl'] - d*slip
                        close_all(j, px if d == 1 else px - s_h, 'SL' if not (stop == 'step' and bk['adds'] > 1) else 'SL(nachgez.)')
                    elif hit_tp:
                        close_all(j, bk['tp'] if d == 1 else bk['tp'] - s_l, 'TP')
        # Einstiegslogik
        if bk is None and pend is None and V_[g]:
            U, L, rid = U_[g], L_[g], R_[g]
            if entry == 'touch':
                for d in (-1, 1):
                    if (rid, d) in blocked: continue
                    line = U if d == -1 else L
                    prev_c = c[j-1]
                    if d == -1 and prev_c < U and h[j] >= U:
                        fill = max(U, o[j])
                    elif d == 1 and prev_c > L and l[j] <= L:
                        fill = min(L, o[j])
                    else: continue
                    sl = line - d*slB*A; tp = (L + tp_buf*A) if d == -1 else (U - tp_buf*A)
                    bk = dict(dir=d, entry_t=ctx.t[j], E=0, sl=sl, tp=tp, D=0, adds=1, rid=rid, reg=int(ctx.reg[g]),
                              gross=0.0, comm=0.0, swap=0.0, atr=A, U=U, L=L, mode=entry)
                    e = open_pos(j, d, fill, units[0]); bk['E'] = e; bk['D'] = abs(tp - e)
                    s_h = S(j, 'h')
                    if (d == -1 and h[j] + s_h >= sl) or (d == 1 and l[j] <= sl):  # konservativ: SL in derselben Kerze
                        close_all(j, (sl + slip - s_h) if d == -1 else sl - slip, 'SL')
                    break
            else:
                if armed is not None and (armed['rid'] != rid or j > armed['exp']): armed = None
                if armed is None:
                    for d in (-1, 1):
                        if (rid, d) in blocked: continue
                        if (d == -1 and h[j] >= U - zone*A) or (d == 1 and l[j] <= L + zone*A):
                            armed = dict(d=d, rid=rid, ext=h[j] if d == -1 else l[j], exp=j + expiry_h*4); break
                else:
                    d = armed['d']
                    armed['ext'] = max(armed['ext'], h[j]) if d == -1 else min(armed['ext'], l[j])
                    if entry == 'confH1':
                        ok_bar = ctx.h1_end[j]; co, cc, pl, ph = ctx.h1_o[j], ctx.h1_c[j], ctx.h1_pl[j], ctx.h1_ph[j]
                    else:
                        ok_bar = True; co, cc, pl, ph = o[j], c[j], ctx.m15_pl[j], ctx.m15_ph[j]
                    if ok_bar:
                        if d == -1 and cc < co and cc < pl and cc < U:
                            pend = (d, max(armed['ext'], U) + slB*A, L + tp_buf*A, rid); armed = None
                        elif d == 1 and cc > co and cc > ph and cc > L:
                            pend = (d, min(armed['ext'], L) - slB*A, U - tp_buf*A, rid); armed = None
        # Equity / Margin
        fl = 0.0; mg = 0.0
        for (d, p, u) in pos:
            fl += d*((c[j] if d == 1 else c[j] + S(j)) - p)*u; mg += u*c[j]/lev
        eqv = realized + fl
        if eqv > peak: peak = eqv
        if peak - eqv > maxdd: maxdd = peak - eqv
        if mg > peak_margin: peak_margin = mg
        if j % 16 == 0: eq_t.append(ctx.t[j]); eq_v.append(eqv)
    tr = pd.DataFrame(trades)
    return dict(trades=tr, maxdd=maxdd, peak_margin=peak_margin, ambig=ambig, eq=pd.Series(eq_v, index=eq_t), final=realized)

def metrics(res, capital=10000.0, lev=100):
    tr = res['trades']
    if len(tr) == 0: return dict(n=0)
    w = tr[tr.net > 0].net; ls = tr[tr.net <= 0].net
    streak = mx = 0
    for v in tr.net:
        streak = streak + 1 if v <= 0 else 0; mx = max(mx, streak)
    from scipy import stats
    t = stats.ttest_1samp(tr.net, 0) if len(tr) > 2 else None
    # Bootstrap-KI der Erwartung
    rng = np.random.default_rng(1); bs = [rng.choice(tr.net.values, len(tr)).mean() for _ in range(2000)]
    m = dict(n=int(len(tr)), win_rate=round(len(w)/len(tr), 3), avg_win=round(w.mean(), 2) if len(w) else 0,
             avg_loss=round(ls.mean(), 2) if len(ls) else 0, expectancy=round(tr.net.mean(), 2),
             exp_ci95=[round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)],
             p_value=round(float(t.pvalue), 4) if t is not None else None,
             profit_factor=round(w.sum()/-ls.sum(), 2) if len(ls) and ls.sum() < 0 else None,
             net_total=round(tr.net.sum(), 2), gross_total=round(tr.gross.sum(), 2), costs_comm=round(tr.comm.sum(), 2),
             costs_swap=round(tr.swap.sum(), 2), max_dd=round(res['maxdd'], 2), max_dd_pct=round(100*res['maxdd']/capital, 2),
             longest_losing_streak=int(mx), peak_margin_1_100=round(res['peak_margin'], 2),
             peak_margin_1_500=round(res['peak_margin']*100/500, 2), max_units=int(tr.units.max()),
             avg_npos=round(tr.npos.mean(), 2), ambiguous_bars=int(res['ambig']))
    by = {}
    for rg, nm in ((1, 'Aufwärtstrend'), (-1, 'Abwärtstrend'), (0, 'Seitwärts')):
        s = tr[tr.reg == rg]
        if len(s):
            ww = s[s.net > 0].net; ll = s[s.net <= 0].net
            by[nm] = dict(n=int(len(s)), win_rate=round(len(ww)/len(s), 3), expectancy=round(s.net.mean(), 2),
                          profit_factor=round(ww.sum()/-ll.sum(), 2) if ll.sum() < 0 else None, net=round(s.net.sum(), 2))
    m['by_regime'] = by
    m['exit_reasons'] = tr.reason.value_counts().to_dict()
    return m

def split(res, t0, t1):
    tr = res['trades']; s = tr[(tr.entry_t >= t0) & (tr.entry_t < t1)]
    eq = s.net.cumsum(); dd = (eq.cummax().clip(lower=0) - eq).max() if len(s) else 0
    r = dict(res); r['trades'] = s.reset_index(drop=True)
    # DD aus Equity-Kurve im Zeitfenster (inkl. offener Positionen)
    e = res['eq'][(res['eq'].index >= t0) & (res['eq'].index < t1)]
    r['maxdd'] = float((e.cummax() - e).max()) if len(e) else 0
    return r
