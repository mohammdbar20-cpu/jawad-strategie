//+------------------------------------------------------------------+
//|                                             JawadStrategie.mq5   |
//|  ZigZag-/Range-System für XAUUSD (H4-Range, H1/M15-Bestätigung)   |
//|                                                                  |
//|  WICHTIG: Der Backtest 2015–2025 (Dukascopy-Daten) zeigte KEINE   |
//|  positive Erwartung nach Kosten. Dieser EA ist ein Forschungs-    |
//|  und Demo-Werkzeug. Standardmäßig verweigert er Echtgeld-Konten.  |
//+------------------------------------------------------------------+
#property copyright "Jawad Strategie – Forschungsprototyp"
#property version   "1.00"

#include <Trade\Trade.mqh>

enum ENUM_ENTRY_MODE { ENTRY_TOUCH = 0, ENTRY_CONFIRM_H1 = 1, ENTRY_CONFIRM_M15 = 2 };
enum ENUM_BO_CRIT    { BO_C1 = 1, BO_C2 = 2, BO_C3 = 3, BO_C4 = 4, BO_C34 = 34 };
enum ENUM_STOP_MODE  { STOP_FIXED = 0, STOP_STEP = 1 };

//--- Sicherheit
input bool              InpAllowLive          = false;   // Echtgeld-Konto erlauben (Standard: NEIN)
input long              InpMagic              = 20261019;
//--- Signal-Parameter (wie im Python-Backtest)
input int               InpH4Bars             = 1500;    // H4-Historie für die Zustandsberechnung
input int               InpATRPeriod          = 14;
input double            InpZigK               = 2.0;     // ZigZag-Umkehr in ATR (Pivot erst bestätigt nach k*ATR Gegenbewegung)
input double            InpMinWidthATR        = 3.0;     // Mindestbreite der Range in ATR
input double            InpMaxWidthATR        = 20.0;    // Höchstbreite der Range in ATR
input ENUM_BO_CRIT      InpBreakout           = BO_C34;  // Ausbruchskriterium
input ENUM_ENTRY_MODE   InpEntryMode          = ENTRY_CONFIRM_H1;
input double            InpZoneATR            = 0.25;    // Zone vor der Linie, die einen Setup "scharf" schaltet
input double            InpSLBufATR           = 1.0;     // SL-Abstand hinter Linie/Extrem in ATR
input double            InpTPBufATR           = 0.1;     // TP: Gegenlinie minus Puffer in ATR
input double            InpMinRR              = 1.0;     // Mindest-Chance/Risiko
input int               InpExpiryHours        = 24;      // Setup verfällt nach Stunden
input bool              InpBreakoutExit       = true;    // Bestätigter Ausbruch gegen die Position => schließen
input int               InpERPeriod           = 60;      // Regime: Efficiency-Ratio-Periode (H4)
input double            InpERThreshold        = 0.10;    // Regime-Schwelle
//--- Positionsgröße & Skalierung
input double            InpBaseLot            = 0.01;
input bool              InpUsePyramid         = false;   // 1-2-4-8-Pyramide (Backtest: erhöht Risiko, KEIN Vorteil)
input ENUM_STOP_MODE    InpStopMode           = STOP_FIXED;
input int               InpMaxPositions       = 15;
//--- Risiko-Grenzen
input double            InpMaxBasketRiskUSD   = 200.0;   // max. Verlust des gesamten Korbs bei SL (Kontowährung)
input double            InpMaxBasketRiskPct   = 2.0;     // ... bzw. in % der Equity (strengere Grenze gilt)
input double            InpDailyLossLimitPct  = 3.0;     // Tagesverlust-Limit => keine neuen Einstiege
input double            InpMaxDrawdownPct     = 20.0;    // Equity-Drawdown vom Hoch => EA stoppt Einstiege
input double            InpMinMarginLevelPct  = 300.0;   // Mindest-Margin-Level nach Order
input int               InpMaxSpreadPoints    = 60;      // max. Spread in Punkten
input int               InpSlippagePoints     = 30;
input bool              InpDrawObjects        = true;
input bool              InpLogToFile          = true;

//--- Globale Zustände
CTrade   trade;
double   g_point, g_tickSize, g_tickValue, g_volMin, g_volMax, g_volStep, g_contract;
int      g_digits, g_stopsLevel, g_freezeLevel;
datetime g_lastH4 = 0, g_lastConf = 0, g_dayStart = 0;
double   g_dayStartEquity = 0, g_peakEquity = 0;
int      g_logHandle = INVALID_HANDLE;

// Range-Zustand (nach der letzten geschlossenen H4-Kerze)
double   st_U = 0, st_L = 0, st_ATR = 0;
bool     st_valid = false, st_haveRange = false;
int      st_bo = 0, st_regime = 0;
string   st_rid = "";
// Blockierte Richtungen in der aktuellen Range (nach einem Trade)
string   blk_rid = ""; bool blk_long = false, blk_short = false;
// Setup (Bestätigungsmodus)
int      arm_dir = 0; string arm_rid = ""; double arm_ext = 0; datetime arm_time = 0;
// Korb
int      bk_dir = 0, bk_adds = 0; double bk_E = 0, bk_D = 0, bk_TP = 0, bk_SL = 0;
const int    UNITS[4] = {1, 2, 4, 8};
const double FRAC[4]  = {0.0, 0.25, 0.5, 0.75};

//+------------------------------------------------------------------+
void Log(string ev, string msg)
{
   string line = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + ";" + ev + ";" + msg;
   Print("[Jawad] ", ev, " | ", msg);
   if(InpLogToFile && g_logHandle != INVALID_HANDLE) { FileWrite(g_logHandle, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), ev, msg); FileFlush(g_logHandle); }
}
string D2S(double v, int d = -1) { return DoubleToString(v, d < 0 ? g_digits : d); }
double NP(double p) { if(g_tickSize > 0) p = MathRound(p / g_tickSize) * g_tickSize; return NormalizeDouble(p, g_digits); }
double NV(double v)
{
   v = MathFloor(v / g_volStep + 1e-9) * g_volStep;
   if(v < g_volMin) v = 0;  // zu klein -> nicht handelbar
   if(v > g_volMax) v = g_volMax;
   return NormalizeDouble(v, 8);
}
// Geldwert einer Preisdifferenz für Volumen (Kontowährung)
double MoneyFor(double dist, double vol) { if(g_tickSize <= 0) return 0; return dist / g_tickSize * g_tickValue * vol; }

//+------------------------------------------------------------------+
int OnInit()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   bool tester = (bool)MQLInfoInteger(MQL_TESTER);
   if(mode == ACCOUNT_TRADE_MODE_REAL && !tester && !InpAllowLive)
   {
      Alert("JawadStrategie: Echtgeld-Konto erkannt. Der EA ist standardmäßig nur für Demo/Backtest freigegeben (InpAllowLive=false).");
      return(INIT_FAILED);
   }
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("[Jawad] WARNUNG: Symbol ", _Symbol, " ist offenbar kein Gold. Der EA wurde nur für XAUUSD untersucht.");
   g_digits     = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   g_point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_tickSize   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   g_tickValue  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   g_volMin     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   g_volMax     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   g_volStep    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   g_contract   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   g_stopsLevel = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   g_freezeLevel= (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   if(g_volStep <= 0) g_volStep = 0.01;

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   long fm = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((fm & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((fm & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) trade.SetTypeFilling(ORDER_FILLING_IOC);
   else trade.SetTypeFilling(ORDER_FILLING_RETURN);

   if(InpLogToFile)
   {
      g_logHandle = FileOpen("JawadStrategie_log.csv", FILE_READ|FILE_WRITE|FILE_CSV|FILE_SHARE_READ|FILE_ANSI, ';');
      if(g_logHandle != INVALID_HANDLE) FileSeek(g_logHandle, 0, SEEK_END);
   }
   Log("INIT", StringFormat("Symbol=%s Digits=%d Point=%s TickSize=%s TickValue=%.4f Kontrakt=%.1f VolMin=%.2f Step=%.2f StopsLevel=%d FreezeLevel=%d Hebel=1:%d Modus=%s SwapLong=%.2f SwapShort=%.2f",
       _Symbol, g_digits, D2S(g_point, 5), D2S(g_tickSize, 5), g_tickValue, g_contract, g_volMin, g_volStep, g_stopsLevel, g_freezeLevel,
       (int)AccountInfoInteger(ACCOUNT_LEVERAGE), (mode == ACCOUNT_TRADE_MODE_REAL ? "REAL" : (mode == ACCOUNT_TRADE_MODE_DEMO ? "DEMO" : "CONTEST")),
       SymbolInfoDouble(_Symbol, SYMBOL_SWAP_LONG), SymbolInfoDouble(_Symbol, SYMBOL_SWAP_SHORT)));
   if(NV(InpBaseLot) <= 0) { Log("ERROR", "Basislot kleiner als Mindestvolumen des Brokers."); return(INIT_PARAMETERS_INCORRECT); }
   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   LoadBasket();
   ComputeState();
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason)
{
   Log("DEINIT", "Grund=" + IntegerToString(reason));
   if(g_logHandle != INVALID_HANDLE) FileClose(g_logHandle);
   ObjectsDeleteAll(0, "JW_");
}

//+------------------------------------------------------------------+
//| Kernalgorithmus: identisch zum Python-Backtest (core.py)          |
//+------------------------------------------------------------------+
int BoSignal(int crit, int i, const MqlRates &r[], const double &tr[], double U, double L, double a, int prevOut)
{
   double c = r[i].close;
   switch(crit)
   {
      case BO_C1: return (c > U ? 1 : (c < L ? -1 : 0));
      case BO_C2: return (c > U + 0.5 * a ? 1 : (c < L - 0.5 * a ? -1 : 0));
      case BO_C3: if(tr[i] >= 1.5 * a) return (c > U ? 1 : (c < L ? -1 : 0)); return 0;
      case BO_C4: if(c > U && prevOut == 1) return 1; if(c < L && prevOut == -1) return -1; return 0;
      case BO_C34: { int x = BoSignal(BO_C3, i, r, tr, U, L, a, prevOut); if(x != 0) return x; return BoSignal(BO_C4, i, r, tr, U, L, a, prevOut); }
   }
   return 0;
}

bool ComputeState()
{
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_H4, 1, InpH4Bars, r);   // nur GESCHLOSSENE H4-Kerzen, r[0]=älteste
   if(n < InpATRPeriod + 50) { Log("WARN", "Zu wenig H4-Historie: " + IntegerToString(n)); return false; }
   double tr[], a[];
   ArrayResize(tr, n); ArrayResize(a, n); ArrayInitialize(a, 0);
   for(int i = 0; i < n; i++)
   {
      double pc = (i > 0 ? r[i-1].close : r[i].close);
      tr[i] = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - pc), MathAbs(r[i].low - pc)));
   }
   double s = 0; for(int i = 0; i < InpATRPeriod; i++) s += tr[i];
   a[InpATRPeriod-1] = s / InpATRPeriod;
   for(int i = InpATRPeriod; i < n; i++) a[i] = (a[i-1] * (InpATRPeriod - 1) + tr[i]) / InpATRPeriod;

   // ZigZag mit Bestätigung: pivot (Index, Preis, Typ) wird erst bei confIdx bekannt
   int    pIdx[], pType[], pConf[]; double pPrice[]; int np = 0;
   ArrayResize(pIdx, n); ArrayResize(pType, n); ArrayResize(pConf, n); ArrayResize(pPrice, n);
   int d = 0; double ehi = r[0].high, elo = r[0].low; int ehiI = 0, eloI = 0;
   for(int i = 1; i < n; i++)
   {
      if(i < InpATRPeriod) { if(r[i].high > ehi) { ehi = r[i].high; ehiI = i; } if(r[i].low < elo) { elo = r[i].low; eloI = i; } continue; }
      double th = InpZigK * a[i];
      bool done = false;
      if(d >= 0)
      {
         if(r[i].high > ehi) { ehi = r[i].high; ehiI = i; }
         else if(ehi - r[i].low >= th) { pIdx[np] = ehiI; pPrice[np] = ehi; pType[np] = 1; pConf[np] = i; np++; d = -1; elo = r[i].low; eloI = i; done = true; }
      }
      if(!done && d <= 0)
      {
         if(r[i].low < elo) { elo = r[i].low; eloI = i; }
         else if(r[i].high - elo >= th) { pIdx[np] = eloI; pPrice[np] = elo; pType[np] = -1; pConf[np] = i; np++; d = 1; ehi = r[i].high; ehiI = i; }
      }
   }
   // Range-Zustand Kerze für Kerze (keine Zukunftsinformation)
   double hs[2], ls[2]; int nh = 0, nl = 0; int lastBo = -1; double cu = 0, cl = 0; bool cvalid = false; int prevOut = 0;
   int pk = 0; int bo = 0; bool validNow = false;
   for(int i = 0; i < n; i++)
   {
      bo = 0;
      if(cvalid && i > 0 && a[i-1] > 0)
      {
         int sgn = BoSignal((int)InpBreakout, i, r, tr, cu, cl, a[i-1], prevOut);
         prevOut = (r[i].close > cu ? 1 : (r[i].close < cl ? -1 : 0));
         if(sgn != 0) { bo = sgn; lastBo = i; nh = 0; nl = 0; cvalid = false; prevOut = 0; }
      }
      while(pk < np && pConf[pk] == i)
      {
         if(pIdx[pk] >= lastBo)
         {
            if(pType[pk] == 1) { if(nh == 2) { hs[0] = hs[1]; nh = 1; } hs[nh++] = pPrice[pk]; }
            else               { if(nl == 2) { ls[0] = ls[1]; nl = 1; } ls[nl++] = pPrice[pk]; }
         }
         pk++;
      }
      if(nh > 0 && nl > 0 && a[i] > 0)
      {
         double nu = hs[0]; if(nh == 2) nu = MathMax(hs[0], hs[1]);
         double nlw = ls[0]; if(nl == 2) nlw = MathMin(ls[0], ls[1]);
         double w = (nu - nlw) / a[i];
         bool ok = (nu > nlw && w >= InpMinWidthATR && w <= InpMaxWidthATR);
         if(ok && (nu != cu || nlw != cl || !cvalid)) prevOut = 0;
         if(ok) { cu = nu; cl = nlw; cvalid = true; } else cvalid = false;
      }
      else cvalid = false;
      validNow = cvalid && r[i].close > cl && r[i].close < cu;
   }
   int last = n - 1;
   st_haveRange = cvalid; st_U = cu; st_L = cl; st_valid = validNow; st_bo = bo; st_ATR = a[last];
   st_rid = cvalid ? (D2S(cu) + "|" + D2S(cl)) : "";
   // Regime (Efficiency Ratio)
   st_regime = 0;
   if(n > InpERPeriod + 1)
   {
      double path = 0; for(int i = last - InpERPeriod + 1; i <= last; i++) path += MathAbs(r[i].close - r[i-1].close);
      double er = (path > 0 ? (r[last].close - r[last-InpERPeriod].close) / path : 0);
      st_regime = (er > InpERThreshold ? 1 : (er < -InpERThreshold ? -1 : 0));
   }
   if(st_rid != blk_rid) { blk_rid = st_rid; blk_long = false; blk_short = false; }
   Log("H4", StringFormat("Range=%s U=%s L=%s gueltig=%s Ausbruch=%d ATR=%.2f Regime=%d Pivots=%d",
       (st_haveRange ? "ja" : "nein"), D2S(st_U), D2S(st_L), (st_valid ? "ja" : "nein"), st_bo, st_ATR, st_regime, np));
   if(InpDrawObjects) DrawState(r, n, pIdx, pPrice, np);
   return true;
}

void DrawState(const MqlRates &r[], int n, const int &pIdx[], const double &pPrice[], int np)
{
   ObjectsDeleteAll(0, "JW_");
   if(st_haveRange)
   {
      ObjectCreate(0, "JW_U", OBJ_HLINE, 0, 0, st_U); ObjectSetInteger(0, "JW_U", OBJPROP_COLOR, clrRed);
      ObjectCreate(0, "JW_L", OBJ_HLINE, 0, 0, st_L); ObjectSetInteger(0, "JW_L", OBJPROP_COLOR, clrLime);
   }
   int from = MathMax(1, np - 30);
   for(int k = from; k < np; k++)
   {
      string nm = "JW_Z" + IntegerToString(k);
      ObjectCreate(0, nm, OBJ_TREND, 0, r[pIdx[k-1]].time, pPrice[k-1], r[pIdx[k]].time, pPrice[k]);
      ObjectSetInteger(0, nm, OBJPROP_COLOR, clrGold); ObjectSetInteger(0, nm, OBJPROP_WIDTH, 2); ObjectSetInteger(0, nm, OBJPROP_RAY_RIGHT, false);
   }
}

//+------------------------------------------------------------------+
//| Positionen / Korb                                                |
//+------------------------------------------------------------------+
int CountPositions(int &dir, double &vol, double &riskAtSL, double sl)
{
   int cnt = 0; dir = 0; vol = 0; riskAtSL = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      cnt++; double v = PositionGetDouble(POSITION_VOLUME); vol += v;
      double op = PositionGetDouble(POSITION_PRICE_OPEN);
      int dd = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1); dir = dd;
      if(sl > 0) riskAtSL += MoneyFor(dd * (op - sl), v);
   }
   return cnt;
}
string GVN(string k) { return "JW_" + IntegerToString(InpMagic) + "_" + k; }
void SaveBasket()
{
   GlobalVariableSet(GVN("dir"), bk_dir); GlobalVariableSet(GVN("adds"), bk_adds); GlobalVariableSet(GVN("E"), bk_E);
   GlobalVariableSet(GVN("D"), bk_D); GlobalVariableSet(GVN("TP"), bk_TP); GlobalVariableSet(GVN("SL"), bk_SL);
}
void LoadBasket()
{
   int dir; double vol, risk; int c = CountPositions(dir, vol, risk, 0);
   if(c > 0 && GlobalVariableCheck(GVN("dir")))
   {
      bk_dir = (int)GlobalVariableGet(GVN("dir")); bk_adds = (int)GlobalVariableGet(GVN("adds")); bk_E = GlobalVariableGet(GVN("E"));
      bk_D = GlobalVariableGet(GVN("D")); bk_TP = GlobalVariableGet(GVN("TP")); bk_SL = GlobalVariableGet(GVN("SL"));
      Log("RESTORE", StringFormat("Korb wiederhergestellt: dir=%d adds=%d E=%s TP=%s SL=%s", bk_dir, bk_adds, D2S(bk_E), D2S(bk_TP), D2S(bk_SL)));
   }
   else if(c > 0) Log("WARN", "Offene Positionen ohne gespeicherten Korbzustand – nur serverseitige SL/TP aktiv, keine Nachkäufe.");
   else bk_dir = 0;
}
void ResetBasket(string why)
{
   if(bk_dir != 0)
   {
      if(bk_dir == 1) blk_long = true; else blk_short = true;   // keine Wiederholung in derselben Range
      Log("BASKET_END", why);
   }
   bk_dir = 0; bk_adds = 0; SaveBasket();
}
void CloseAll(string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(!trade.PositionClose(t)) Log("ERROR", "Schließen fehlgeschlagen #" + IntegerToString((long)t) + " rc=" + IntegerToString((int)trade.ResultRetcode()));
   }
   ResetBasket(why);
}
void ModifyAllSL(double sl)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      double tp = PositionGetDouble(POSITION_TP);
      if(!trade.PositionModify(t, NP(sl), tp)) Log("ERROR", "SL-Änderung fehlgeschlagen rc=" + IntegerToString((int)trade.ResultRetcode()));
   }
}

//+------------------------------------------------------------------+
//| Risiko-Prüfungen                                                 |
//+------------------------------------------------------------------+
double MaxRiskMoney()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double r1 = InpMaxBasketRiskUSD, r2 = eq * InpMaxBasketRiskPct / 100.0;
   return MathMin(r1, r2);
}
bool RiskGateOpen(string &why)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_peakEquity) g_peakEquity = eq;
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt); dt.hour = 0; dt.min = 0; dt.sec = 0; datetime today = StructToTime(dt);
   if(today != g_dayStart) { g_dayStart = today; g_dayStartEquity = eq; }
   if(g_dayStartEquity > 0 && eq < g_dayStartEquity * (1 - InpDailyLossLimitPct / 100.0)) { why = "Tagesverlust-Limit erreicht"; return false; }
   if(g_peakEquity > 0 && eq < g_peakEquity * (1 - InpMaxDrawdownPct / 100.0)) { why = "Max. Drawdown erreicht – EA pausiert"; return false; }
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints) { why = "Spread zu hoch (" + IntegerToString(spread) + ")"; return false; }
   return true;
}
bool MarginOK(ENUM_ORDER_TYPE type, double vol, double price)
{
   double m = 0;
   if(!OrderCalcMargin(type, _Symbol, vol, price, m)) { Log("ERROR", "OrderCalcMargin fehlgeschlagen"); return false; }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY), used = AccountInfoDouble(ACCOUNT_MARGIN), fm = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double lvl = (used + m > 0 ? eq / (used + m) * 100.0 : 1e9);
   if(m > fm || lvl < InpMinMarginLevelPct) { Log("BLOCK", StringFormat("Margin: benötigt %.2f frei %.2f Margin-Level danach %.0f%%", m, fm, lvl)); return false; }
   return true;
}
bool StopsOK(double price, double sl, double tp)
{
   double minD = (g_stopsLevel + 2) * g_point;
   if(MathAbs(price - sl) < minD || MathAbs(price - tp) < minD) { Log("BLOCK", "SL/TP näher als StopsLevel – kein Einstieg (Linien werden NICHT verschoben)"); return false; }
   return true;
}

//+------------------------------------------------------------------+
//| Einstieg                                                         |
//+------------------------------------------------------------------+
void TryOpen(int dir, double sl, double tp, string reason)
{
   string why;
   if(!RiskGateOpen(why)) { Log("BLOCK", why); return; }
   MqlTick tk; if(!SymbolInfoTick(_Symbol, tk)) return;
   double price = (dir == 1 ? tk.ask : tk.bid);
   double vol = NV(InpBaseLot * UNITS[0]);
   if(vol <= 0) { Log("BLOCK", "Volumen < Mindestvolumen"); return; }
   double risk = dir * (price - sl), reward = dir * (tp - price);
   if(risk <= 0 || reward <= 0 || reward < InpMinRR * risk) { Log("SKIP", StringFormat("%s: CRV unzureichend (Risiko %.2f, Chance %.2f)", reason, risk, reward)); return; }
   double money = MoneyFor(risk, vol);
   if(money > MaxRiskMoney()) { Log("BLOCK", StringFormat("Risiko %.2f > Limit %.2f", money, MaxRiskMoney())); return; }
   if(!StopsOK(price, sl, tp)) return;
   ENUM_ORDER_TYPE ot = (dir == 1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   if(!MarginOK(ot, vol, price)) return;
   bool ok = (dir == 1 ? trade.Buy(vol, _Symbol, 0, NP(sl), NP(tp), "JW entry") : trade.Sell(vol, _Symbol, 0, NP(sl), NP(tp), "JW entry"));
   if(!ok || (trade.ResultRetcode() != TRADE_RETCODE_DONE && trade.ResultRetcode() != TRADE_RETCODE_PLACED))
   { Log("ERROR", "Order fehlgeschlagen rc=" + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription()); return; }
   double fill = trade.ResultPrice(); if(fill <= 0) fill = price;
   bk_dir = dir; bk_adds = 1; bk_E = fill; bk_D = MathAbs(tp - fill); bk_TP = tp; bk_SL = sl; SaveBasket();
   Log("OPEN", StringFormat("%s %s vol=%.2f Fill=%s SL=%s TP=%s Risiko=%.2f Range U=%s L=%s Regime=%d", reason, (dir == 1 ? "LONG" : "SHORT"), vol, D2S(fill), D2S(sl), D2S(tp), money, D2S(st_U), D2S(st_L), st_regime));
}

void ManageBasket()
{
   int dir; double vol, risk; int cnt = CountPositions(dir, vol, risk, bk_SL);
   if(cnt == 0) { if(bk_dir != 0) ResetBasket("Korb geschlossen (SL/TP serverseitig)"); return; }
   if(bk_dir == 0 || (!InpUsePyramid && InpStopMode == STOP_FIXED)) return;
   MqlTick tk; if(!SymbolInfoTick(_Symbol, tk)) return;
   while(bk_adds < 4)
   {
      double lvl = bk_E + bk_dir * FRAC[bk_adds] * bk_D;
      double px = (bk_dir == 1 ? tk.ask : tk.bid);
      if(bk_dir * (px - lvl) < 0) break;                     // Nachkauf NUR in Gewinnrichtung
      double newSL = (InpStopMode == STOP_STEP ? bk_E + bk_dir * FRAC[bk_adds - 1] * bk_D : bk_SL);
      if(InpUsePyramid)
      {
         double v = NV(InpBaseLot * UNITS[bk_adds]);
         string why;
         int c2; double vol2, risk2; int n2 = CountPositions(c2, vol2, risk2, newSL);
         double riskAfter = risk2 + MoneyFor(bk_dir * (px - newSL), v);
         int unitsNow = (int)MathRound(vol2 / InpBaseLot);
         if(n2 + 1 > InpMaxPositions || unitsNow + UNITS[bk_adds] > 15) { Log("BLOCK", "Max. Positionen erreicht"); bk_adds = 4; SaveBasket(); break; }
         if(riskAfter > MaxRiskMoney()) { Log("BLOCK", StringFormat("Nachkauf %d gesperrt: Korbrisiko %.2f > Limit %.2f", bk_adds, riskAfter, MaxRiskMoney())); bk_adds = 4; SaveBasket(); break; }
         if(!RiskGateOpen(why)) { Log("BLOCK", "Nachkauf: " + why); break; }
         ENUM_ORDER_TYPE ot = (bk_dir == 1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
         if(v <= 0 || !MarginOK(ot, v, px)) { bk_adds = 4; SaveBasket(); break; }
         bool ok = (bk_dir == 1 ? trade.Buy(v, _Symbol, 0, NP(newSL), NP(bk_TP), "JW add " + IntegerToString(bk_adds))
                                : trade.Sell(v, _Symbol, 0, NP(newSL), NP(bk_TP), "JW add " + IntegerToString(bk_adds)));
         if(!ok) { Log("ERROR", "Nachkauf fehlgeschlagen rc=" + IntegerToString((int)trade.ResultRetcode())); break; }
         Log("ADD", StringFormat("Stufe %d/4 (%.0f%% des Ziels) vol=%.2f Preis=%s neuer SL=%s Korbrisiko=%.2f", bk_adds, FRAC[bk_adds] * 100, v, D2S(px), D2S(newSL), riskAfter));
      }
      if(InpStopMode == STOP_STEP && bk_dir * (newSL - bk_SL) > 0)  // SL nur in Gewinnrichtung
      { bk_SL = newSL; ModifyAllSL(bk_SL); Log("SL_STEP", "SL nachgezogen auf " + D2S(bk_SL)); }
      bk_adds++; SaveBasket();
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   // 1) Neue H4-Kerze -> Zustand neu berechnen
   datetime h4 = iTime(_Symbol, PERIOD_H4, 0);
   if(h4 != g_lastH4)
   {
      g_lastH4 = h4; ComputeState();
      if(InpBreakoutExit && bk_dir != 0 && st_bo == -bk_dir) { Log("BREAKOUT_EXIT", "Bestätigter Ausbruch gegen die Position"); CloseAll("Ausbruch gegen Position"); }
      if(st_bo != 0) { arm_dir = 0; Log("BREAKOUT", StringFormat("Bestätigter Ausbruch %s – keine Gegentrend-Einstiege bis neue Range", st_bo > 0 ? "nach OBEN" : "nach UNTEN")); }
   }
   // 2) Korb verwalten
   ManageBasket();
   int dir; double vol, risk; if(CountPositions(dir, vol, risk, 0) > 0) return;
   if(!st_valid || st_ATR <= 0) { arm_dir = 0; return; }
   MqlTick tk; if(!SymbolInfoTick(_Symbol, tk)) return;
   double U = st_U, L = st_L, A = st_ATR;
   // 3) Einstieg
   if(InpEntryMode == ENTRY_TOUCH)
   {
      double prevC = iClose(_Symbol, PERIOD_M15, 1);
      if(!blk_short && prevC < U && tk.bid >= U) TryOpen(-1, U + InpSLBufATR * A, L + InpTPBufATR * A, "TOUCH Oberkante");
      else if(!blk_long && prevC > L && tk.bid <= L) TryOpen(1, L - InpSLBufATR * A, U - InpTPBufATR * A, "TOUCH Unterkante");
      return;
   }
   if(arm_dir != 0 && (arm_rid != st_rid || TimeCurrent() > arm_time + InpExpiryHours * 3600)) { Log("DISARM", "Setup verfallen/Range geändert"); arm_dir = 0; }
   if(arm_dir == 0)
   {
      if(!blk_short && tk.bid >= U - InpZoneATR * A) { arm_dir = -1; arm_rid = st_rid; arm_ext = tk.bid; arm_time = TimeCurrent(); Log("ARM", "Short-Setup an Oberkante " + D2S(U)); }
      else if(!blk_long && tk.bid <= L + InpZoneATR * A) { arm_dir = 1; arm_rid = st_rid; arm_ext = tk.bid; arm_time = TimeCurrent(); Log("ARM", "Long-Setup an Unterkante " + D2S(L)); }
   }
   if(arm_dir == 0) return;
   arm_ext = (arm_dir == -1 ? MathMax(arm_ext, tk.bid) : MathMin(arm_ext, tk.bid));
   ENUM_TIMEFRAMES ctf = (InpEntryMode == ENTRY_CONFIRM_H1 ? PERIOD_H1 : PERIOD_M15);
   datetime cb = iTime(_Symbol, ctf, 0);
   if(cb == g_lastConf) return;
   g_lastConf = cb;
   double o1 = iOpen(_Symbol, ctf, 1), c1 = iClose(_Symbol, ctf, 1), h1 = iHigh(_Symbol, ctf, 1), l1 = iLow(_Symbol, ctf, 1);
   double l2 = iLow(_Symbol, ctf, 2), h2 = iHigh(_Symbol, ctf, 2);
   if(arm_dir == -1) arm_ext = MathMax(arm_ext, h1); else arm_ext = MathMin(arm_ext, l1);
   if(arm_dir == -1 && c1 < o1 && c1 < l2 && c1 < U)
   { TryOpen(-1, MathMax(arm_ext, U) + InpSLBufATR * A, L + InpTPBufATR * A, "BESTÄTIGTE UMKEHR Oberkante"); arm_dir = 0; }
   else if(arm_dir == 1 && c1 > o1 && c1 > h2 && c1 > L)
   { TryOpen(1, MathMin(arm_ext, L) - InpSLBufATR * A, U - InpTPBufATR * A, "BESTÄTIGTE UMKEHR Unterkante"); arm_dir = 0; }
}
//+------------------------------------------------------------------+
