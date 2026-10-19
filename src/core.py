"""Kernlogik: ATR, ZigZag (ohne Look-ahead), Range-Zustand, Ausbruchskriterien, Regime."""
import numpy as np, pandas as pd

def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    a = np.empty_like(tr); a[:] = np.nan
    a[n-1] = tr[:n].mean()
    for i in range(n, len(tr)):
        a[i] = (a[i-1]*(n-1) + tr[i]) / n
    return a, tr

def zigzag(h, l, a, k):
    """Bestätigte Pivots. Ein Hoch gilt erst als bestätigt, wenn der Kurs danach um k*ATR
    vom Extrem gefallen ist (bekannt am Schluss der Bestätigungskerze). Rückgabe:
    Liste (pivot_idx, preis, typ(+1 Hoch/-1 Tief), confirm_idx)."""
    piv = []; d = 0; ehi = h[0]; ehi_i = 0; elo = l[0]; elo_i = 0
    for i in range(1, len(h)):
        if np.isnan(a[i]): 
            ehi, ehi_i, elo, elo_i = (h[i], i, l[i], i) if h[i] > ehi or l[i] < elo else (ehi, ehi_i, elo, elo_i)
            continue
        th = k * a[i]
        if d >= 0:
            if h[i] > ehi: ehi, ehi_i = h[i], i
            elif ehi - l[i] >= th:
                piv.append((ehi_i, ehi, 1, i)); d = -1; elo, elo_i = l[i], i; continue
        if d <= 0:
            if l[i] < elo: elo, elo_i = l[i], i
            elif h[i] - elo >= th:
                piv.append((elo_i, elo, -1, i)); d = 1; ehi, ehi_i = h[i], i; continue
    return piv

def regime(c, a=None, n=60, thr=0.10):
    """Kaufman-Efficiency-Ratio über n H4-Kerzen (nur Vergangenheit). +1 Aufwärts, -1 Abwärts, 0 Seitwärts."""
    c = np.asarray(c); er = np.full(len(c), np.nan); r = np.zeros(len(c), int)
    dc = np.abs(np.diff(c, prepend=c[0])); cs = np.cumsum(dc)
    for i in range(n, len(c)):
        path = cs[i] - cs[i-n]
        er[i] = (c[i] - c[i-n]) / path if path > 0 else 0
        r[i] = 1 if er[i] > thr else (-1 if er[i] < -thr else 0)
    return r, er

BO_CRITERIA = ['W', 'C1', 'C2', 'C3', 'C4', 'C34']
BO_DESC = {'W': 'Nur Docht über/unter der Linie (High/Low)',
           'C1': 'H4-Schlusskurs außerhalb der Linie',
           'C2': 'H4-Schluss außerhalb um ≥0,5×ATR',
           'C3': 'H4-Schluss außerhalb + ATR-Expansion (True Range ≥1,5×ATR)',
           'C4': 'Zwei aufeinanderfolgende H4-Schlüsse außerhalb (Follow-through)',
           'C34': 'C3 ODER C4 (Strategie-Standard)'}

def bo_signal(crit, i, o, h, l, c, tr, U, L, a, prev_out):
    """prev_out: +1/-1 wenn der vorige Schluss bereits außerhalb derselben Range lag."""
    if crit == 'W':
        return 1 if h[i] > U else (-1 if l[i] < L else 0)
    if crit == 'C1':
        return 1 if c[i] > U else (-1 if c[i] < L else 0)
    if crit == 'C2':
        return 1 if c[i] > U + 0.5*a else (-1 if c[i] < L - 0.5*a else 0)
    if crit == 'C3':
        if tr[i] >= 1.5*a:
            return 1 if c[i] > U else (-1 if c[i] < L else 0)
        return 0
    if crit == 'C34':
        x = bo_signal('C3', i, o, h, l, c, tr, U, L, a, prev_out)
        return x if x else bo_signal('C4', i, o, h, l, c, tr, U, L, a, prev_out)
    if crit == 'C4':
        if c[i] > U and prev_out == 1: return 1
        if c[i] < L and prev_out == -1: return -1
        return 0

def range_state(h4, k=2.0, crit='C34', minW=3.0, maxW=20.0, nmem=2):
    """Zustand nach Schluss jeder H4-Kerze i: obere/untere Linie, gültig?, Ausbruch, Range-ID.
    Nur Information bis einschließlich Kerze i wird verwendet."""
    o, h, l, c = (h4[x].values for x in 'ohlc')
    a, tr = atr(h, l, c)
    piv = zigzag(h, l, a, k)
    n = len(c)
    U = np.full(n, np.nan); Lo = np.full(n, np.nan); valid = np.zeros(n, bool)
    bo = np.zeros(n, int); rid = np.zeros(n, int); npiv = np.zeros(n, int)
    by_conf = {}
    for p in piv: by_conf.setdefault(p[3], []).append(p)
    highs, lows = [], []; last_bo = -1; cu = cl = np.nan; cvalid = False; prev_out = 0; cur_id = 0
    for i in range(n):
        # 1) Ausbruchsprüfung gegen die VOR dieser Kerze bekannte Range
        if cvalid and not np.isnan(a[i-1]):
            s = bo_signal(crit, i, o, h, l, c, tr, cu, cl, a[i-1], prev_out)
            prev_out = 1 if c[i] > cu else (-1 if c[i] < cl else 0)
            if s != 0:
                bo[i] = s; last_bo = i; highs, lows = [], []; cvalid = False; prev_out = 0
        # 2) Neue bestätigte Pivots
        for p in by_conf.get(i, []):
            if p[0] >= last_bo:
                (highs if p[2] == 1 else lows).append(p[1])
        highs, lows = highs[-nmem:], lows[-nmem:]
        if highs and lows and not np.isnan(a[i]):
            nu, nl = max(highs), min(lows)
            w = (nu - nl) / a[i]
            ok = nu > nl and minW <= w <= maxW
            if ok and (nu != cu or nl != cl or not cvalid):
                cur_id += 1; prev_out = 0
            if ok:
                cu, cl = nu, nl; cvalid = True
            else:
                cvalid = False
        else:
            cvalid = False
        U[i], Lo[i] = (cu, cl) if cvalid else (np.nan, np.nan)
        valid[i] = cvalid and (cl < c[i] < cu)   # Einstiege nur, wenn Schluss innerhalb
        rid[i] = cur_id if cvalid else -1
        npiv[i] = len(highs) + len(lows)
    return dict(U=U, L=Lo, valid=valid, bo=bo, rid=rid, atr=a, tr=tr, piv=piv)
