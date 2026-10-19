"""Lädt XAUUSD-Daten (EV Trading Labs, aggregiert aus Dukascopy-Ticks, Bid+Ask, UTC)."""
import gzip, json, glob, os
import pandas as pd, numpy as np
BASE = os.path.join(os.path.dirname(__file__), '..', 'data')

def load_tf(tf):
    fr = []
    for f in sorted(glob.glob(f'{BASE}/ev/{tf}/*.json.gz')):
        fr.append(pd.DataFrame(json.loads(gzip.open(f).read())))
    df = pd.concat(fr, ignore_index=True)
    df['time'] = pd.to_datetime(df.ts, unit='s')
    df = df.drop_duplicates('ts').sort_values('ts').set_index('time')
    return df[['o','h','l','c','ao','ah','al','ac','v']]

def resample(m15, rule):
    agg = {'o':'first','h':'max','l':'min','c':'last','ao':'first','ah':'max','al':'min','ac':'last','v':'sum'}
    r = m15.resample(rule, origin='epoch').agg(agg).dropna(subset=['o'])
    return r

def build():
    m15 = load_tf('M15')
    h4f = load_tf('H4'); h1f = load_tf('H1')
    h1 = resample(m15, '1h'); h4 = resample(m15, '4h')
    # Konsistenzprüfung gegen gelieferte H4/H1
    j = h4.join(h4f, rsuffix='_f', how='inner')
    print('H4 aus M15 vs. geliefertes H4: Bars', len(h4), len(h4f), 'gemeinsam', len(j),
          'max|dClose|', (j.c - j.c_f).abs().max(), 'median|dHigh|', (j.h - j.h_f).abs().median())
    j1 = h1.join(h1f, rsuffix='_f', how='inner')
    print('H1 vs geliefert: max|dClose|', (j1.c - j1.c_f).abs().max())
    pd.to_pickle({'m15': m15, 'h1': h1, 'h4': h4, 'h4_file': h4f, 'h1_file': h1f}, f'{BASE}/xau.pkl')
    sp = (m15.ao - m15.o)
    print('M15', m15.index.min(), m15.index.max(), len(m15))
    print('Spread (Ask-Bid an M15-Open) Median %.3f Mittel %.3f P90 %.3f' % (sp.median(), sp.mean(), sp.quantile(.9)))
    # Lücken
    gaps = m15.index.to_series().diff()
    print('Größte Lücken:', gaps.sort_values().tail(5).to_dict())

def get():
    return pd.read_pickle(f'{BASE}/xau.pkl')

if __name__ == '__main__':
    build()
