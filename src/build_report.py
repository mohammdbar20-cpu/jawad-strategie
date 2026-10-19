import os, json, shutil, html, numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
BASE = os.path.join(os.path.dirname(__file__), '..'); OUT = BASE + '/out'; SITE = BASE + '/site'
A = json.load(open(OUT + '/analysis.json')); B = json.load(open(OUT + '/backtest.json'))
os.makedirs(SITE + '/charts', exist_ok=True)
for f in os.listdir(OUT + '/charts'): shutil.copy(OUT + '/charts/' + f, SITE + '/charts/' + f)
shutil.copy(BASE + '/mql5/JawadStrategie.mq5', SITE + '/JawadStrategie.mq5')
shutil.copy(OUT + '/analysis.json', SITE + '/analysis.json'); shutil.copy(OUT + '/backtest.json', SITE + '/backtest.json')

def de(x, d=2):
    if x is None: return '–'
    if isinstance(x, (int,)) and not isinstance(x, bool): return f'{x:,}'.replace(',', '.')
    if isinstance(x, float): return f'{x:,.{d}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return html.escape(str(x))
def pct(x): return '–' if x is None else de(100*x, 1) + ' %'

# Analytische Skalierung
u = np.array([1, 2, 4, 8]); f = np.array([0, .25, .5, .75])
rows = []
for k in range(1, 5):
    uu, ff = u[:k], f[:k]; avg = (uu*ff).sum()/uu.sum()
    tp = (uu*(1-ff)).sum(); be = avg
    sl_fixed = -(uu*(ff+0.4)).sum()
    sl_step = (uu*((f[k-2] if k >= 2 else -0.4) - ff)).sum()
    rows.append((k, int(uu.sum()), uu.sum()*0.01, avg, tp, be, sl_fixed, sl_step, uu.sum()*0.42))
x = np.linspace(-0.4, 1.0, 300)
fig, ax = plt.subplots(figsize=(10, 4))
def pl_path(xs, pyr):
    out = []
    for xv in xs:
        out.append(sum(ui*(xv-fi) for ui, fi in zip(u, f) if fi <= 0.75) if pyr else xv)
    return np.array(out)
ax.plot(x, x, label='1 Position (0,01 Lot)', c='#3060b0')
ax.plot(x[x >= .75], pl_path(x[x >= .75], True), c='#b03030', lw=2, label='Pyramide voll (15×0,01) – Rücklauf ab ≥¾')
ax.axhline(0, c='#999', lw=.6); ax.axvline(8.5/15, c='#b03030', ls=':'); ax.text(8.5/15, 2, ' Break-even 0,567·D', color='#b03030')
for fi in f[1:]: ax.axvline(fi, c='#ccc', ls='--', lw=.7)
ax.set_xlabel('Kursposition relativ zum Ziel (0 = Einstieg, 1 = TP)'); ax.set_ylabel('Brutto-G/V in D × 0,01 Lot')
ax.set_title('Wirkung eines Rücklaufs auf den voll ausgebauten 1-2-4-8-Korb'); ax.legend(); fig.tight_layout(); fig.savefig(SITE + '/charts/scaling_profile.png', dpi=110); plt.close()

KEYS = [('n', 'Trades', None), ('win_rate', 'Trefferquote', 'p'), ('avg_win', 'Ø Gewinn ($)', 2), ('avg_loss', 'Ø Verlust ($)', 2),
        ('expectancy', 'Erwartung je Trade nach Kosten ($)', 2), ('exp_ci95', '95 %-Bootstrap-KI Erwartung', 'ci'), ('p_value', 't-Test p-Wert (H0: Erwartung=0)', 3),
        ('profit_factor', 'Profitfaktor', 2), ('net_total', 'Netto gesamt ($)', 2), ('gross_total', 'Brutto vor Komm./Swap ($)', 2), ('costs_comm', 'Kommission ($)', 2), ('costs_swap', 'Swap ($)', 2),
        ('max_dd', 'Max. Drawdown ($, inkl. offener Pos.)', 2), ('max_dd_pct', 'Max. DD in % von 10.000 $', 1), ('longest_losing_streak', 'Längste Verlustserie', None),
        ('peak_margin_1_100', 'Spitzen-Margin 1:100 ($)', 2), ('peak_margin_1_500', 'Spitzen-Margin 1:500 ($)', 2), ('max_units', 'Max. Positionen (×0,01)', None)]
def mtab(d, keys=KEYS):
    cols = list(d.keys())
    h = '<table><tr><th>Kennzahl</th>' + ''.join(f'<th>{html.escape(c)}</th>' for c in cols) + '</tr>'
    for k, nm, fmt in keys:
        h += f'<tr><td>{nm}</td>'
        for c in cols:
            v = d[c].get(k)
            s = pct(v) if fmt == 'p' else ('[' + de(v[0]) + ' ; ' + de(v[1]) + ']' if fmt == 'ci' and v else (de(v, fmt) if isinstance(fmt, int) else de(v)))
            h += f'<td>{s}</td>'
        h += '</tr>'
    return h + '</table>'
def regtab(d):
    h = '<table><tr><th>Zeitraum</th><th>Regime</th><th>Trades</th><th>Trefferquote</th><th>Erwartung ($)</th><th>PF</th><th>Netto ($)</th></tr>'
    for per, m in d.items():
        for rg, r in m.get('by_regime', {}).items():
            h += f'<tr><td>{per}</td><td>{rg}</td><td>{r["n"]}</td><td>{pct(r["win_rate"])}</td><td>{de(r["expectancy"])}</td><td>{de(r["profit_factor"])}</td><td>{de(r["net"])}</td></tr>'
    return h + '</table>'
def short(d, per):
    return {k: v[per] for k, v in d.items()}

S2 = A['swings']['2.0']; S3 = A['swings']['3.0']
touch = A['touch']['k2.0_mid']
def touch_tab(r):
    h = '<table><tr><th>Teilmenge</th><th>n</th><th>Treffer (Mitte zuerst)</th><th>Erwartet bei Zufall</th><th>z</th><th>p</th><th>Ø R brutto</th></tr>'
    for k, e in r.items():
        if not e: continue
        h += f'<tr><td>{html.escape(k)}</td><td>{e["n"]}</td><td>{pct(e["win_rate"])}</td><td>{pct(e["expected_random"])}</td><td>{de(e["z"])}</td><td>{de(e["p_value"], 3)}</td><td>{de(e["mean_R_gross"], 3)}</td></tr>'
    return h + '</table>'
BO_DESC = {'W': 'Nur Docht außerhalb', 'C1': 'H4-Schluss außerhalb', 'C2': 'H4-Schluss ≥0,5 ATR außerhalb', 'C3': 'Schluss außerhalb + True Range ≥1,5 ATR',
           'C4': '2 H4-Schlüsse außerhalb (Follow-through)', 'C34': 'C3 oder C4 (Strategie-Standard)'}
def bo_tab():
    h = '<table><tr><th>Kriterium</th><th>Zeitraum</th><th>n</th><th>Follow-through (+2 ATR vor Rückkehr)</th><th>Zufallserwartung</th><th>z</th><th>Ø Verzögerung (H4-Kerzen)</th><th>Ø Abstand zur Linie bei Bestätigung (ATR)</th><th>nach 30 Kerzen noch jenseits der Linie</th></tr>'
    for c, r in A['breakout'].items():
        for per in ('IS', 'OOS'):
            e = r.get(per)
            if e: h += f'<tr><td>{c}: {BO_DESC[c]}</td><td>{per}</td><td>{e["n"]}</td><td>{pct(e["follow_through"])}</td><td>{pct(e["random"])}</td><td>{de(e["z"])}</td><td>{de(e["lag_bars"])}</td><td>{de(e["beyond_atr"])}</td><td>{pct(e["cont30"])}</td></tr>'
    return h + '</table>'
grid = B['grid']
gtab = '<table><tr><th>k</th><th>SL-Puffer (ATR)</th><th>Mindestbreite (ATR)</th><th>Einstieg</th><th>IS n</th><th>IS Erwartung</th><th>IS PF</th><th>OOS n</th><th>OOS Erwartung</th><th>OOS PF</th></tr>' + ''.join(
    f'<tr><td>{g["k"]}</td><td>{g["slB"]}</td><td>{g["minW"]}</td><td>{g["entry"]}</td><td>{g["IS_n"]}</td><td>{de(g["IS_exp"])}</td><td>{de(g["IS_pf"])}</td><td>{g["OOS_n"]}</td><td>{de(g["OOS_exp"])}</td><td>{de(g["OOS_pf"])}</td></tr>' for g in grid) + '</table>'
wf = B['walkforward']
wftab = '<table><tr><th>Testjahr</th><th>gewählte Parameter (aus 3 Vorjahren)</th><th>PF Training</th><th>Trades Test</th><th>PF Test</th><th>Netto Test ($)</th></tr>' + ''.join(
    f'<tr><td>{w["year"]}</td><td>k={w["params"]["k"]}, SL={w["params"]["slB"]}, Breite={w["params"]["minW"]}, {w["params"]["entry"]}</td><td>{de(w["train_pf"])}</td><td>{w["test_n"]}</td><td>{de(w["test_pf"])}</td><td>{de(w["test_net"])}</td></tr>' for w in wf['years']) + '</table>'
sctab = '<table><tr><th>Stufe</th><th>Positionen gesamt</th><th>Volumen (Lot)</th><th>Ø Einstieg (Anteil von D)</th><th>Brutto bei TP (D×0,01 Lot)</th><th>Break-even-Kurs (Anteil von D)</th><th>G/V bei Rücklauf auf festen SL (SL=0,4·D hinter Einstieg)</th><th>G/V bei Rücklauf auf nachgezogenen SL</th><th>Kosten Spread 0,30+Komm.+Slip ($)</th></tr>' + ''.join(
    f'<tr><td>{r[0]} ({["Einstieg", "¼ Ziel", "½ Ziel", "¾ Ziel"][r[0]-1]})</td><td>{r[1]}</td><td>{de(r[2])}</td><td>{de(r[3], 3)}</td><td>{de(r[4], 2)}</td><td>{de(r[5], 3)}</td><td>{de(r[6], 2)}</td><td>{de(r[7], 2)}</td><td>{de(r[8], 2)}</td></tr>' for r in rows) + '</table>'
cost_tab = mtab({k: v['OOS 2022–2025'] for k, v in B['costs'].items()}, [x for x in KEYS if x[0] in ('n', 'win_rate', 'expectancy', 'profit_factor', 'net_total', 'max_dd')])
cost_tab_is = mtab({k: v['IS 2015–2021'] for k, v in B['costs'].items()}, [x for x in KEYS if x[0] in ('n', 'win_rate', 'expectancy', 'profit_factor', 'net_total', 'max_dd')])
crit_tab = mtab({k: v['OOS 2022–2025'] for k, v in B['crit_in_strategy'].items()}, [x for x in KEYS if x[0] in ('n', 'win_rate', 'expectancy', 'profit_factor', 'net_total')])
crit_tab_is = mtab({k: v['IS 2015–2021'] for k, v in B['crit_in_strategy'].items()}, [x for x in KEYS if x[0] in ('n', 'win_rate', 'expectancy', 'profit_factor', 'net_total')])
M = B['main']; SC = B['scaling']

FL = json.load(open(OUT + '/flat.json')); shutil.copy(OUT + '/flat.json', SITE + '/flat.json')
FK = [x for x in KEYS if x[0] not in ('gross_total',)]
fl_is = mtab({k.split(':')[0]: v['IS 2015–2021'] for k, v in FL.items()}, FK)
fl_oos = mtab({k.split(':')[0]: v['OOS 2022–2025'] for k, v in FL.items()}, FK)
fl_reg = regtab({k.split(':')[0] + ' ' + p: v[p] for k, v in FL.items() for p in ('IS 2015–2021', 'OOS 2022–2025')})
fl_names = ''.join(f'<li><b>{html.escape(k.split(":")[0])}</b>: {html.escape(k.split(":", 1)[1])}</li>' for k in FL)
FLAT = f'''<h3 id="d2">Nachtrag: Gleichmäßige Skalierung 1-1-1-1 (max. 4 Positionen = 0,04 Lot)</h3>
<p>Gleiche Standardparameter und Kosten wie oben; Nachkauf je 0,01 Lot bei ¼, ½ und ¾ des Ziels, nur in Gewinnrichtung.</p>
<ul>{fl_names}</ul>
<p>Mathematik: Ø-Einstieg = (0 + ¼ + ½ + ¾)/4 = 0,375·D; Brutto bei TP 2,5·D (×0,01 Lot) statt 1·D. Nach dem letzten Nachkauf ist der Korb erst bei 0,375·D wieder bei null (Rücklauf 0,375·D möglich, gegenüber nur 0,183·D bei 1-2-4-8). Mit nachgezogenem SL: Rücklauf nach Stufe 2 (SL auf Einstieg) = −0,25·D, nach Stufe 3 (SL auf ¼) = 0, nach Stufe 4 (SL auf ½) = +0,5·D – das Risikoprofil ist also deutlich gutmütiger als bei 1-2-4-8.</p>
<h4>In-Sample 2015–2021</h4>{fl_is}
<h4>Out-of-Sample 2022–2025</h4>{fl_oos}
<h4>Nach Regime</h4>{fl_reg}
<img src="charts/equity_flat.png" alt="Equity 1-1-1-1">
<p><b>Bewertung:</b> 1-1-1-1 ist weniger riskant als 1-2-4-8, aber <b>kein Vorteil</b>: Mit festem SL (F1) bleibt die Erwartung negativ (IS {de(FL["F1: 1-1-1-1, fester SL"]["IS 2015–2021"]["expectancy"])} $, OOS {de(FL["F1: 1-1-1-1, fester SL"]["OOS 2022–2025"]["expectancy"])} $ je Korb), der Drawdown steigt gegenüber einer Position etwa auf das 2,3-Fache, und der Swap wächst stark (mehr Volumen über Nacht). Der Profitfaktor ist leicht höher als ohne Skalierung (Gesamt {de(FL["F1: 1-1-1-1, fester SL"]["Gesamt"]["profit_factor"])} vs. {de(FL["S0: 1 Position, fester SL"]["Gesamt"]["profit_factor"])}), das 95 %-Konfidenzintervall der Erwartung umfasst aber klar die Null – nicht signifikant. Mit nachgezogenem SL (F2) wird es deutlich schlechter (PF {de(FL["F2: 1-1-1-1, SL stufenweise nachgezogen"]["Gesamt"]["profit_factor"])}), weil die meisten Körbe nach Stufe 2 am Einstieg ausgestoppt werden. Hinweis: Der MQL5-EA unterstützt aktuell nur 1-2-4-8 bzw. 1 Position; 1-1-1-1 wurde nur im Python-Backtest getestet.</p>
'''

mq5 = html.escape(open(BASE + '/mql5/JawadStrategie.mq5').read())
regA = ''.join(f'<tr><td>{nm}</td><td>{r["legs"]}</td><td>{r["up_legs"]}</td><td>{r["down_legs"]}</td><td>{de(r["up_size_atr"])}</td><td>{de(r["down_size_atr"])}</td><td>{de(r["up_bars"],0)}</td><td>{de(r["down_bars"],0)}</td></tr>' for nm, r in S2['by_regime'].items())
corrA = ''.join(f'<tr><td>{nm}</td><td>{r["n"]}</td><td>{pct(r["retr_ge_0.382"])}</td><td>{pct(r["retr_ge_0.5"])}</td><td>{pct(r["retr_ge_0.618"])}</td><td>{pct(r["retr_ge_1.0"])}</td><td>{pct(S2["corrections_null"][nm]["retr_ge_0.5"])}</td><td>{pct(S2["corrections_null"][nm]["retr_ge_1.0"])}</td></tr>' for nm, r in S2['corrections'].items())
hours = ' · '.join(f'{int(h):02d}–{int(h)+4:02d} UTC: {pct(v)}' for h, v in S2['pivot_hour_share'].items())
zr = A['zigzag_repeat']; bb = A['between_breakouts']
s0 = SC['S0: 1 Position, fester SL']; s1 = SC['S1: Pyramide 1-2-4-8, fester SL']; s2 = SC['S2: Pyramide 1-2-4-8, SL stufenweise nachgezogen']
sc_sum = mtab({k.split(':')[0]: v['Gesamt'] for k, v in SC.items()})
sc_oos = mtab({k.split(':')[0]: v['OOS 2022–2025'] for k, v in SC.items()}, [x for x in KEYS if x[0] in ('n', 'win_rate', 'avg_win', 'avg_loss', 'expectancy', 'profit_factor', 'net_total', 'max_dd', 'longest_losing_streak', 'peak_margin_1_100', 'peak_margin_1_500')])
sc_names = ''.join(f'<li><b>{html.escape(k.split(":")[0])}</b>: {html.escape(k.split(":", 1)[1])}</li>' for k in SC)
cf = B['costs']['Ohne jegliche Kosten (nur Referenz)']

page = f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jawad Strategie – XAUUSD ZigZag/Range-Studie</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1150px;margin:0 auto;padding:16px 20px 60px;color:#222;line-height:1.5;background:#fcfbf7}}
h1{{color:#8a6d0b}} h2{{border-bottom:2px solid #c9a227;padding-bottom:4px;margin-top:42px}} h3{{margin-top:26px}}
table{{border-collapse:collapse;margin:10px 0 18px;font-size:13px;display:block;overflow-x:auto}} td,th{{border:1px solid #ddd;padding:4px 8px;text-align:right}} th{{background:#f3ecd6}} td:first-child,th:first-child{{text-align:left}}
.verdict{{background:#fdecea;border-left:6px solid #b03030;padding:12px 16px;margin:16px 0}} .ok{{background:#eef6ee;border-left:6px solid #2a8a3a;padding:10px 16px}}
.note{{background:#fff8e1;border-left:6px solid #c9a227;padding:10px 16px;margin:12px 0}} img{{max-width:100%;border:1px solid #eee;margin:8px 0}}
pre{{background:#1e1e1e;color:#ddd;padding:12px;overflow:auto;max-height:600px;font-size:12px}} code{{background:#f1efe6;padding:1px 4px}}
nav a{{margin-right:12px}} .btn{{display:inline-block;background:#8a6d0b;color:#fff;padding:8px 14px;border-radius:6px;text-decoration:none}}
</style></head><body>
<h1>Jawad Strategie – XAUUSD ZigZag-/Range-Handelssystem</h1>
<p><b>Forschungsbericht</b> · Stand 19.10.2026 · Daten: XAUUSD M15/H1/H4 (Bid+Ask), 01.01.2015–31.12.2025 (UTC).</p>
<nav><a href="#fazit">Fazit</a><a href="#daten">Daten</a><a href="#a">A Analyse</a><a href="#b">B Algorithmus</a><a href="#c">C Regeln</a><a href="#d">D Skalierung</a><a href="#e">E Ausbruch</a><a href="#f">F Backtest</a><a href="#risiken">Risiken</a><a href="#g">G MQL5</a><a href="#install">Installation</a></nav>

<h2 id="fazit">Fazit in Klartext</h2>
<div class="verdict"><b>Die Daten zeigen KEINE positive Erwartung nach Kosten.</b> Keine der 24 getesteten Parameter-Kombinationen hatte im In-Sample-Zeitraum (2015–2021) einen Profitfaktor über 1; im Out-of-Sample-Zeitraum (2022–2025) lag nur 1 von 24 knapp darüber (Zufallstreffer zu erwarten). Die Standardvariante (bestätigte Umkehr auf H1) verlor nach Kosten im Schnitt {de(M["confH1"]["Gesamt"]["expectancy"])} $ je Trade à 0,01 Lot (PF {de(M["confH1"]["Gesamt"]["profit_factor"])}); selbst <i>ohne jegliche Kosten</i> liegt sie praktisch bei null (PF {de(cf["Gesamt"]["profit_factor"])}). Der Walk-Forward-Test (Parameter jährlich neu aus den 3 Vorjahren gewählt) ergab PF {de(wf["total"]["profit_factor"])} und {de(wf["total"]["net_total"])} $.</div>
<div class="verdict"><b>Die gewünschte 1-2-4-8-Skalierung verschlechtert das Ergebnis und vervielfacht das Risiko.</b> Da 8 von 15 Positionen erst bei ¾ des Ziels eröffnet werden, liegt der Durchschnittseinstieg bei 56,7 % des Weges: Ein Rücklauf von nur ~18 % der Zielstrecke nach dem letzten Nachkauf löscht den gesamten Buchgewinn. Mit festem SL stieg der maximale Drawdown von {de(s0["Gesamt"]["max_dd"])} $ auf {de(s1["Gesamt"]["max_dd"])} $ bei schlechterer Erwartung.</div>
<p>Was die Daten <i>bestätigen</i>: Gold bildet auf H4 tatsächlich ständig Zickzack-Bewegungen (≈{de(S2["legs_per_year"],0)} Swings/Jahr bei k=2·ATR), starke Bewegungen werden meist teilweise korrigiert, und zwischen zwei bestätigten Ausbrüchen liegen typischerweise ~{de(bb["changes_median"],0)} Richtungswechsel. <b>Aber</b>: Genau dieselben Werte erzeugt auch ein Zufallsmodell ohne jede Struktur (permutierte Kerzen). Das Muster ist also real sichtbar, aber nicht vorhersagbar genug, um Spread, Kommission und Swap zu bezahlen. An den Range-Grenzen dreht der Kurs <i>nicht</i> häufiger als zufällig – eher etwas seltener (leichter Ausbruchs-Impuls).</p>
<p><a class="btn" href="JawadStrategie.mq5" download>JawadStrategie.mq5 herunterladen</a> &nbsp; <a href="analysis.json">Rohdaten Analyse (JSON)</a> · <a href="backtest.json">Rohdaten Backtest (JSON)</a></p>

<h2 id="daten">Daten und Annahmen</h2>
<ul>
<li><b>Quelle:</b> EV Trading Labs (evtradelabs.com/data), Jahresdateien XAUUSD, „aggregiert aus Dukascopy-Ticks mit Bid und Ask“, UTC, ohne Sommerzeit. M15 = 259.857 Kerzen, H1/H4 aus M15 nachgebildet und gegen die gelieferten H1/H4-Dateien geprüft (Abweichung 0,00). Zeitraum <b>01.01.2015 23:00 – 31.12.2025 21:45 UTC</b>.</li>
<li>Der direkte Dukascopy-Download (<code>dukascopy-node</code>) war von unserem Server aus nicht erreichbar (Timeout/HTTP 202). Das Jahr 2026 ist bei EV Trading Labs nur mit Konto verfügbar und fehlt deshalb.</li>
<li>Gemessener Dukascopy-Spread (Ask–Bid): Median 0,32 $, Mittel 0,37 $, 90 %-Quantil 0,53 $.</li>
<li><b>Annahme „Punkte“:</b> 1 Punkt = 0,01 $ (2-stellige Gold-Kurse). 20–35 Punkte = 0,20–0,35 $. Bei Brokern mit 3 Nachkommastellen ist 1 Punkt 0,001 $ – bitte prüfen.</li>
<li><b>Kosten (Basis):</b> Spread fest 0,30 $, Kommission 7 $ je Lot Round-Turn (0,07 $ je 0,01 Lot), Slippage 0,05 $ bei Markt-/Stop-Ausführung (Einstieg nach Bestätigung, Nachkäufe, SL), keine bei Limit (Touch-Einstieg, TP).</li>
<li><b>Annahme Swap</b> (nicht vom Broker bestätigt): Long zahlt Preis×(US-Zins+3 %)/360 je Unze und Nacht, Short zahlt Preis×max(3 %−Zins; 0,5 %)/360; Mittwoch dreifach; Zins = Jahresmittel Fed Funds. Echte Broker-Swaps weichen ab.</li>
<li>Kontrakt 100 oz/Lot; Margin = Volumen×100×Preis/Hebel (1:100 und 1:500). Referenzkonto für %-Drawdown: 10.000 $ (Annahme).</li>
<li><b>Intrabar-Reihenfolge:</b> Fills auf M15; wenn SL und TP in derselben M15-Kerze erreichbar sind, wird der SL gewertet (konservativ). Nachkäufe werden in einer Kerze vor der SL-Prüfung ausgeführt (konservativ). Mehrdeutige Kerzen traten 0–1 mal auf.</li>
<li><b>Regime</b> (Aufwärts/Abwärts/Seitwärts) = Kaufman-Efficiency-Ratio über 60 H4-Kerzen, Schwelle ±0,10 (nur Vergangenheit). Ergibt ca. 36 % / 25 % / 39 % der Zeit.</li>
<li>In-Sample (IS) 2015–2021, Out-of-Sample (OOS) 2022–2025; zusätzlich Walk-Forward 2018–2025.</li>
</ul>

<h2 id="a">A. Statistische Analyse (H4)</h2>
<h3>Swings (ZigZag mit Bestätigung)</h3>
<p>Ein Hoch gilt erst als bestätigt, wenn der Kurs danach um k×ATR(14) gefallen ist (analog Tief). k=2: <b>{S2["n_legs"]}</b> Swings in 11 Jahren (≈{de(S2["legs_per_year"],0)}/Jahr), Median {de(S2["size_usd_median"])} $ bzw. {de(S2["size_atr_median"])} ATR, Median-Dauer {de(S2["bars_median"],0)} H4-Kerzen; die Bestätigung kommt im Median {de(S2["conf_lag_median_bars"],0)} Kerzen nach dem Extrem. k=3: {S3["n_legs"]} Swings, Median {de(S3["size_usd_median"])} $ ({de(S3["size_atr_median"])} ATR). Zufallsmodell (permutierte Kerzen): {de(S2["null_legs_per_year"],0)} Swings/Jahr, Median {de(S2["null_size_atr_median"])} ATR – also praktisch identisch.</p>
<table><tr><th>Regime (k=2)</th><th>Swings</th><th>aufwärts</th><th>abwärts</th><th>Ø Größe auf (ATR, Median)</th><th>Ø Größe ab</th><th>Dauer auf (Kerzen)</th><th>Dauer ab</th></tr>{regA}</table>
<p>Im Aufwärtstrend gibt es mehr Abwärts-Swings (Korrekturen) als Aufwärts-Swings, aber die Aufwärts-Swings sind größer – so entsteht der Trend. Spiegelbildlich im Abwärtstrend.</p>
<img src="charts/swings.png" alt="Swing-Verteilung">
<h3>Korrekturen nach starken Bewegungen</h3>
<table><tr><th>Swing-Typ (k=2)</th><th>n</th><th>Gegenbewegung ≥38,2 %</th><th>≥50 %</th><th>≥61,8 %</th><th>≥100 %</th><th>Zufallsmodell ≥50 %</th><th>Zufallsmodell ≥100 %</th></tr>{corrA}</table>
<p class="note">Hinweis: Weil ein Swing per Definition mindestens k×ATR lang ist, sind kleine Swings fast immer „voll korrigiert“ – das ist ein Konstruktionseffekt. Entscheidend ist der Vergleich mit dem Zufallsmodell: Die echten Korrekturquoten liegen <b>nicht über</b> den Zufallswerten (starke Swings: 48 % vs. 52 % für ≥50 %-Korrektur).</p>
<h3>Wiederholende ZigZags, Richtungswechsel vor Ausbruch</h3>
<p>Anteil der Pivots, die innerhalb ±1 ATR am vorigen gleichartigen Pivot liegen (Range-Zickzack): <b>{pct(zr["real"]["share_repeating"])}</b>; Zufallsmodell {pct(zr["null_mean"])} ± {pct(zr["null_sd"])}. Typische Länge einer Wiederholungsserie: Median {de(zr["real"]["run_median"],0)}, 90 %-Quantil {de(zr["real"]["run_p90"],0)} Wiederholungen.</p>
<p>Bestätigte Ausbrüche (Kriterium C3/C4): {bb["n_breakouts"]} (≈{de(bb["per_year"],0)}/Jahr). Richtungswechsel (bestätigte Pivots) zwischen zwei Ausbrüchen: Median <b>{de(bb["changes_median"],0)}</b> (Quartile {de(bb["changes_p25"],0)}–{de(bb["changes_p75"],0)}), Median-Abstand {de(bb["bars_between_median"],0)} H4-Kerzen (~{de(bb["bars_between_median"]/6,0)} Handelstage). Zufallsmodell: ebenfalls Median {de(bb["null_median_mean"],0)}.</p>
<img src="charts/changes.png" alt="Richtungswechsel">
<h3>Tageszeit</h3><p>Anteil der Swing-Extreme je H4-Kerze: {hours}. Die Kerze 12–16 UTC (US-Eröffnung, US-Daten) trägt ~39 % aller Wendepunkte – weil dort die Volatilität am größten ist.</p>
<h3>Edge-Test an den Range-Grenzen (Kern der Idee)</h3>
<p>Für jede erste Berührung einer gültigen Range-Grenze: Wird zuerst die Range-Mitte erreicht (Umkehr) oder zuerst Linie ± 1 ATR (Ausbruch)? Bei einer driftfreien Zufallsbewegung ist die Trefferquote = SL-Abstand/(SL+TP-Abstand). Ein echter Vorteil müsste deutlich darüber liegen.</p>
{touch_tab(touch)}
<p><b>Ergebnis:</b> In keiner Teilmenge (Regime, Volatilität, Tageszeit, Richtung) zeigt sich ein signifikant positiver Vorteil. Insgesamt liegt die Umkehrquote <i>unter</i> der Zufallserwartung (z={de(touch["Alle"]["z"])}). Gegen den Trend an der Linie zu handeln ist sogar signifikant schlechter (p≈{de(touch["Gegen Trend"]["p_value"],3)}). Einzelne Teilmengen mit positivem z (z. B. „mit Trend“, z={de(touch["Mit Trend"]["z"])}) sind nicht signifikant und bei so vielen Tests als Zufall zu erwarten (Mehrfachtest-Problem). Mit k=3 ist der Befund noch negativer (z={de(A["touch"]["k3.0_mid"]["Alle"]["z"])}).</p>

<h2 id="b">B. Algorithmus (ohne Look-ahead)</h2>
<ol>
<li><b>ATR</b>(14, Wilder) auf H4.</li>
<li><b>ZigZag</b>: Suche Hoch; sobald Tief ≤ Extremhoch − k·ATR, ist das Hoch bestätigt (bekannt am Schluss dieser Kerze), dann Suche Tief usw. Ein Pivot wird erst ab seiner Bestätigungskerze verwendet. Standard k=2.</li>
<li><b>Dynamische Range</b>: Oberkante U = Maximum der letzten 2 bestätigten Hochs, Unterkante L = Minimum der letzten 2 bestätigten Tiefs – nur Pivots seit dem letzten bestätigten Ausbruch (mind. je 1 Hoch und 1 Tief). Gültig, wenn 3 ≤ (U−L)/ATR ≤ 20. Einstiege nur, wenn der letzte H4-Schluss innerhalb liegt.</li>
<li><b>Zustand</b>: „in Range“ / „Ausbruch nach oben/unten“ (Kriterium siehe E) / „keine Range“ (nach Ausbruch, bis neue Pivots eine neue Range bilden). Richtung, Stärke (Swing-Größe in ATR) und Dauer (Kerzen) aus dem letzten Swing; Regime aus Efficiency-Ratio.</li>
<li><b>Linien werden nie für offene Trades verschoben</b>: SL/TP werden beim Einstieg fixiert; die Range selbst aktualisiert sich nur durch neue bestätigte Pivots.</li>
</ol>
<img src="charts/example_2019.png" alt="Beispielchart">
<p><b>Reicht H4?</b> Für die Struktur (Range/Ausbruch) ja. Für Einstieg und Ausführung nicht: Ohne niedrigeren Zeitrahmen ist die Reihenfolge von SL/TP innerhalb einer H4-Kerze unbekannt. Getestet wurden Touch (reine H4-Linie, Fill auf M15), Bestätigung auf H1 und auf M15. Die Bestätigung reduziert die Zahl der Trades und Verlustserien, erzeugt aber keinen Vorteil (siehe F).</p>

<h2 id="c">C. Exakte Handelsregeln</h2>
<table>
<tr><th>Regel</th><th>Short an der Oberkante</th><th>Long an der Unterkante</th></tr>
<tr><td>Voraussetzung</td><td colspan="2">gültige Range, letzter H4-Schluss innerhalb, kein bestätigter Ausbruch, Richtung in dieser Range noch nicht gehandelt (keine „Rache“-Trades)</td></tr>
<tr><td>Touch-Einstieg</td><td>Verkauf, sobald Bid U erreicht (vorige M15 schloss darunter)</td><td>Kauf, sobald Bid L erreicht</td></tr>
<tr><td>Bestätigter Einstieg</td><td>Setup scharf, wenn Hoch ≥ U − 0,25·ATR; dann H1-Kerze (bzw. M15) bärisch, Schluss &lt; Tief der Vorkerze und &lt; U ⇒ Verkauf zur nächsten Eröffnung. Verfall nach 24 h.</td><td>spiegelbildlich: Tief ≤ L + 0,25·ATR, bullische Kerze schließt über Vorkerzenhoch und &gt; L</td></tr>
<tr><td>Stop-Loss</td><td>max(U, höchster Kurs seit Setup) + 1,0·ATR (Touch: U + 1,0·ATR)</td><td>min(L, tiefster Kurs) − 1,0·ATR</td></tr>
<tr><td>Take-Profit</td><td>L + 0,1·ATR</td><td>U − 0,1·ATR</td></tr>
<tr><td>Filter</td><td colspan="2">Chance/Risiko ≥ 1; Spread-, Margin- und Risiko-Limits (EA)</td></tr>
<tr><td>Vorzeitiger Ausstieg</td><td colspan="2">Bestätigter Ausbruch gegen die Position ⇒ Schließen zur nächsten Eröffnung. Danach keine Gegentrend-Einstiege bis neue Range.</td></tr>
</table>
<h3>Touch vs. bestätigte Umkehr (Standardparameter, nach Kosten)</h3>
{mtab({"Touch": M["touch"]["Gesamt"], "Bestätigt H1": M["confH1"]["Gesamt"], "Bestätigt M15": M["confM15"]["Gesamt"]})}
<img src="charts/equity_entries.png" alt="Equity Einstiegsarten">
<p>Touch hat viele kleine Verluste (Trefferquote ~14 %), Bestätigung höhere Trefferquoten (~25–27 %) aber größere Verluste – alle drei sind negativ.</p>

<h2 id="d">D. Skalierung 1-2-4-8 (0,01 Lot je Position)</h2>
<p>D = Abstand Einstieg → TP. Nachkäufe nur, wenn der Kurs in Gewinnrichtung ¼, ½ und ¾ von D erreicht – nie bei Gegenbewegung. Alle Positionen teilen TP und SL. Gesamt: 15 Positionen = 0,15 Lot.</p>
{sctab}
<p>Mathematik: Ø-Einstieg = (1·0 + 2·¼ + 4·½ + 8·¾)/15 = 8,5/15 = 0,567·D. Bei TP: Brutto 6,5·D (×0,01 Lot) gegenüber 1·D ohne Skalierung. Bei Rücklauf nach dem letzten Nachkauf ist der Korb schon bei 0,567·D wieder bei null – nur 0,183·D unter dem letzten Einstieg. Mit nachgezogenem SL (½-Linie) endet ein solcher Rücklauf bei −1,0·D, also <b>schlechter als ein Verlust-Trade ohne Skalierung</b>. Frühe Gewinne decken spätere Verluste nur dann, wenn das Ziel tatsächlich erreicht wird; genau das ist an den Range-Grenzen nicht häufiger als zufällig.</p>
<img src="charts/scaling_profile.png" alt="Skalierungsprofil">
<p><b>Margin</b> für 0,15 Lot: bei Gold 2.000 $ → 300 $ (1:100) bzw. 60 $ (1:500); bei 4.000 $ → 600 $ bzw. 120 $. Gemessene Spitze im Backtest: {de(s1["Gesamt"]["peak_margin_1_100"])} $ (1:100) / {de(s1["Gesamt"]["peak_margin_1_500"])} $ (1:500). Die Margin ist nicht der Engpass – das Verlustrisiko ist es.</p>
<h3>Backtest der Varianten (Standardparameter, bestätigt H1)</h3>
<ul>{sc_names}</ul>
<h4>Gesamtzeitraum 2015–2025</h4>{sc_sum}
<h4>Out-of-Sample 2022–2025</h4>{sc_oos}
<img src="charts/equity_scaling.png" alt="Equity Skalierung">
<p><b>Bewertung:</b> Die Skalierung erhöht das Risiko deutlich (Drawdown ×5–8) und verbessert die Erwartung nicht; mit nachgezogenem SL sinkt die Trefferquote auf ~3 %, weil fast jeder Rücklauf den Korb mit Verlust schließt. Empfohlene Grenzen, falls überhaupt getestet: max. 15 Positionen, max. Korbrisiko 2 % der Equity bzw. 200 $, Tagesverlust-Limit 3 %, EA-Stopp bei 20 % Drawdown (alles im EA umgesetzt).</p>

{FLAT}
<h2 id="e">E. Ausbruchserkennung</h2>
<p>Ein einzelner Docht/Touch gilt nie als bestätigt. Bewertet: Erreicht der Kurs nach der Bestätigung +2 ATR in Ausbruchsrichtung, bevor er 0,5 ATR zurück in die Range läuft? Vergleich mit Zufallserwartung.</p>
{bo_tab()}
<p><b>Ergebnis:</b> Reine Dochte (W) sind kaum besser als Zufall – ein Docht ist kein Ausbruch. Schlusskurs-basierte Kriterien mit Filter (C3: ATR-Expansion, C4: zwei Schlüsse) haben die beste Follow-through-Quote über Zufall (gesamt z≈3), kosten aber Verzögerung (C4: 1 Kerze, ~1 ATR Abstand). Die Strategie nutzt C3 ODER C4 (im IS vorab gewählt). „Trendwechsel vs. Korrektur“: nach 30 H4-Kerzen liegt der Kurs in ~57–64 % der bestätigten Ausbrüche noch jenseits der Linie; bei Ausbrüchen gegen den bisherigen Trend ähnlich (~63 %) – die Daten erlauben keine zuverlässige Unterscheidung im Moment des Ausbruchs.</p>
<h4>Wirkung des Kriteriums in der Strategie (IS)</h4>{crit_tab_is}
<h4>… und OOS</h4>{crit_tab}

<h2 id="f">F. Backtest-Ergebnisse (Standard: k=2, SL 1 ATR, Mindestbreite 3 ATR, bestätigt H1, 1 Position)</h2>
{mtab(M["confH1"])}
<h3>Nach Regime</h3>{regtab(M["confH1"])}
<h3>Kostenszenarien (IS)</h3>{cost_tab_is}
<h3>Kostenszenarien (OOS)</h3>{cost_tab}
<h3>Alle 24 Parameter-Kombinationen</h3>
<p>Bewusst kleines Gitter (k ∈ {{2;3}}, SL-Puffer ∈ {{0,5;1,0}} ATR, Mindestbreite ∈ {{3;5}} ATR, Einstieg ∈ {{Touch; H1; M15}}). Anteil mit PF&gt;1: IS {pct(B["share_IS_pf_gt1"])}, OOS {pct(B["share_OOS_pf_gt1"])}. Bester IS-Kandidat: k={B["best_IS_params"]["k"]}, SL={B["best_IS_params"]["slB"]}, Breite={B["best_IS_params"]["minW"]}, {B["best_IS_params"]["entry"]} – IS PF {de(B["best_IS_run"]["IS 2015–2021"]["profit_factor"])}, OOS PF {de(B["best_IS_run"]["OOS 2022–2025"]["profit_factor"])}.</p>
{gtab}
<h3>Walk-Forward 2018–2025</h3>{wftab}
{mtab({"Walk-Forward gesamt": wf["total"]}, [x for x in KEYS if x[0] in ("n","win_rate","avg_win","avg_loss","expectancy","exp_ci95","p_value","profit_factor","net_total","max_dd","longest_losing_streak")])}
<img src="charts/walkforward.png" alt="Walk-Forward">

<h2 id="risiken">Größte Risiken</h2>
<ol>
<li><b>Keine nachgewiesene Erwartung</b>: Die Idee „an der Linie umkehren“ ist in 11 Jahren Gold-Daten nicht besser als Zufall; Kosten machen sie negativ.</li>
<li><b>Ausbrüche</b>: Gold trendet stark (2019–2020, 2024–2025). Range-Strategien verlieren in genau diesen Phasen; Gaps über das Wochenende überspringen den SL.</li>
<li><b>Inverse Pyramide</b>: 1-2-4-8 legt das meiste Volumen ans Ende – kleine Rückläufe kosten viel. Martingale-ähnliches Risikoprofil (nicht Verdopplung im Verlust, aber Konzentration auf späte Einstiege).</li>
<li><b>Swap</b>: Long-Positionen über Nacht kosten bei 4–5 % Zins spürbar (hier rund die Hälfte der Gesamtkosten der Standardvariante: Swap ≈115 $ vs. Spread+Slippage ≈85 $ und Kommission ≈15 $); echte Broker-Swaps prüfen.</li>
<li><b>Modellgrenzen</b>: Swap-Modell geschätzt, Spread fest bzw. Dukascopy-Spread (Broker-Spreads anders, v. a. bei News), M15-Auflösung statt Ticks, Serverzeit des Brokers ≠ UTC (H4-Kerzen anders geschnitten), Daten ohne 2026.</li>
<li><b>Überanpassung</b>: Mit vielen Varianten findet man zufällig einzelne positive (OOS 1 von 24) – das ist kein Beweis.</li>
<li><b>Der EA wurde nicht in MetaEditor kompiliert</b> (auf unserem Server nicht verfügbar). Vor Nutzung kompilieren und im Strategietester prüfen.</li>
</ol>

<h2 id="g">G. MQL5 Expert Advisor</h2>
<div class="note">Der EA setzt exakt die oben getesteten Regeln um. Er ist ein <b>Forschungs-/Demo-Werkzeug</b>: Die Backtests zeigen keinen Vorteil. Standard: Echtgeld-Konten werden blockiert (<code>ACCOUNT_TRADE_MODE_REAL</code> ⇒ Start verweigert, solange <code>InpAllowLive=false</code>). Skalierung ist standardmäßig AUS (<code>InpUsePyramid=false</code>) und kann für Tests eingeschaltet werden.</div>
<p>Funktionen: H4-Analyse aus geschlossenen Kerzen, ZigZag mit Bestätigung, dynamische Range, Ausbruchskriterien C1–C4/C34, Touch- oder bestätigter Einstieg (H1/M15), SL/TP serverseitig, 1-2-4-8-Nachkäufe nur in Gewinnrichtung, fester oder stufenweise nachgezogener SL (nur in Gewinnrichtung), Ausstieg bei Gegen-Ausbruch, Limits (max. Positionen, Korbrisiko $/%, Tagesverlust, Max-Drawdown, Margin-Level via <code>OrderCalcMargin</code>, Spread), Broker-Eigenschaften (Digits, Point, Tick-Wert, Volumenschritt, StopsLevel, Kontraktgröße, Filling-Modus), Protokoll aller Entscheidungen in <code>MQL5/Files/JawadStrategie_log.csv</code> und im Journal.</p>
<p><a class="btn" href="JawadStrategie.mq5" download>JawadStrategie.mq5 herunterladen</a></p>
<details><summary>Quellcode anzeigen</summary><pre>{mq5}</pre></details>

<h2 id="install">Installation und Test in MetaTrader 5</h2>
<ol>
<li>MT5 öffnen → <i>Datei → Dateiordner öffnen</i> → <code>MQL5\\Experts\\</code> → <code>JawadStrategie.mq5</code> hineinkopieren.</li>
<li>MetaEditor (F4) → Datei öffnen → <b>Kompilieren</b> (F7). Fehler/Warnungen prüfen (der Code wurde nicht vorab kompiliert).</li>
<li><b>Strategietester</b> (Strg+R): Expert „JawadStrategie“, Symbol XAUUSD (bzw. Broker-Name, z. B. XAUUSDm/GOLD), Zeitraum z. B. 2015–2025, Chart-Periode egal (EA nutzt H4/H1/M15 intern), Modell <b>„Jeder Tick basierend auf echten Ticks“</b>, Einzahlung 10.000 $, Hebel 1:100 bzw. 1:500.</li>
<li>Eingaben: zuerst Standard (bestätigt H1, ohne Pyramide) testen, dann <code>InpUsePyramid=true</code> und <code>InpStopMode</code> vergleichen. Ergebnisse mit diesem Bericht vergleichen; Abweichungen entstehen u. a. durch Serverzeit (H4-Schnitt), echte Spreads und Swaps.</li>
<li>Danach höchstens auf einem <b>Demokonto</b> (Chart XAUUSD, „Algo-Trading“ aktivieren). Für Echtgeld müsste <code>InpAllowLive=true</code> bewusst gesetzt werden – <b>auf Basis dieser Daten nicht empfohlen</b>.</li>
<li>Protokoll: <i>Werkzeuge → Journal/Experten</i> sowie <code>MQL5\\Files\\JawadStrategie_log.csv</code>.</li>
</ol>
<p style="color:#777;font-size:12px;margin-top:40px">Keine Anlageberatung. Ergebnisse vergangener Daten sind kein Hinweis auf zukünftige Ergebnisse. Code und Rohdaten: <code>src/</code> im Repository (Python: data.py, core.py, analysis.py, backtest.py, experiments.py).</p>
</body></html>'''
open(SITE + '/index.html', 'w').write(page)
print('ok', len(page))
