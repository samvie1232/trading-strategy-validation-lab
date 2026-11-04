//+------------------------------------------------------------------+
//|                                              GoldGuardian.mq5    |
//|        EA personal para GOLD (XM) - v1.3                         |
//|  Estrategia: tendencia H1 + retroceso M15 (EMA + RSI + ADX)      |
//|  Riesgo fijo por operación, interruptores de pérdida,            |
//|  filtros de spread / sesión / noticias y log CSV de operaciones. |
//+------------------------------------------------------------------+
#property copyright "Santiago - uso personal"
#property version   "1.30"
#property description "Tendencia + retroceso en GOLD con riesgo fijo, kill switch y log CSV."

#include <Trade\Trade.mqh>

//==================== PARÁMETROS ====================================
input group "=== Riesgo ==="
input double InpRiskPercent        = 1.0;   // Riesgo por operación (% del balance)
input double InpMaxRiskPercent     = 1.0;   // Riesgo máx. real por operación (%). Si el lote mínimo lo supera, NO opera
input double InpDailyLossPercent   = 5.0;   // Pérdida diaria máx. (%) -> no opera más ese día
input double InpMaxDrawdownPercent = 30.0;  // Caída máx. desde el pico de equity (%) -> APAGA el EA
input int    InpMaxConsecLosses    = 3;     // Pérdidas seguidas antes de pausar
input int    InpPauseHours         = 24;    // Horas de pausa tras la racha perdedora
input int    InpMaxTradesPerDay    = 4;     // Operaciones máx. por día
input bool   InpResetKillSwitch    = false; // true = reinicia el apagado (úsalo una vez y vuelve a false)

input group "=== Estrategia ==="
input ENUM_TIMEFRAMES InpTF      = PERIOD_M15; // Temporalidad de entrada
input ENUM_TIMEFRAMES InpTrendTF = PERIOD_H1;  // Temporalidad de tendencia
input int    InpTrendEMA  = 200;   // EMA de tendencia (en InpTrendTF)
input int    InpFastEMA   = 21;    // EMA rápida (en InpTF)
input int    InpSlowEMA   = 50;    // EMA lenta (en InpTF)
input int    InpRSIPeriod = 14;
input double InpRSIBuy    = 40.0;  // Compra: el RSI debió bajar de este nivel en el retroceso
input double InpRSISell   = 60.0;  // Venta: el RSI debió subir de este nivel en el retroceso
input int    InpPullbackBars = 8;  // Velas hacia atrás donde se busca el retroceso
input int    InpADXPeriod = 14;
input double InpADXMin    = 20.0;  // Fuerza mínima de tendencia (ADX)
input int    InpATRPeriod = 14;
input double InpSL_ATR    = 1.5;   // Stop loss = ATR x este valor
input double InpTP_ATR    = 2.5;   // Take profit = ATR x este valor

input group "=== Gestión de la operación ==="
input double InpBE_R           = 1.0;  // Mover SL a la entrada al ganar X veces el riesgo
input bool   InpUseTrailing    = true; // Trailing stop
input double InpTrail_ATR      = 1.0;  // Distancia del trailing (ATR x)
input bool   InpExitOnReversal = true; // Cerrar si la tendencia se invierte

input group "=== Filtros ==="
input double InpMaxSpreadUSD    = 1.50; // Spread máx. absoluto (USD de precio)
input double InpMaxSpreadPctSL  = 15.0; // Spread máx. como % de la distancia del stop loss
input bool   InpTesterDataBlock = true; // En el probador: no abrir en la ventana de datos de EE.UU.
input int    InpDataBlockFrom   = 1515; // Inicio de la ventana (HHMM, hora servidor)
input int    InpDataBlockTo     = 1630; // Fin de la ventana (HHMM, hora servidor)
input int    InpStartHour       = 10;   // Hora de inicio (hora del SERVIDOR de XM)
input int    InpEndHour         = 21;   // Hora de fin (hora del SERVIDOR de XM)
input bool   InpUseNewsFilter   = true; // Filtro de noticias USD de alto impacto (solo en vivo)
input int    InpNewsBeforeMin   = 30;   // Minutos sin abrir antes de la noticia
input int    InpNewsAfterMin    = 30;   // Minutos sin abrir después de la noticia
input bool   InpCloseFriday     = true; // Cerrar todo el viernes (evita gaps del fin de semana)
input int    InpFridayCloseHour = 21;   // Hora de cierre del viernes (servidor)

input group "=== General ==="
input long   InpMagic   = 20261021;               // Número mágico (identifica las operaciones del EA)
input bool   InpLogCSV  = true;                   // Guardar cada operación en CSV
input string InpCSVName = "GoldGuardian_trades.csv"; // Archivo (carpeta Common\Files)
input bool   InpLogDecisions  = true;                         // Guardar cada señal y qué pasó con ella
input string InpDecisionCSV   = "GoldGuardian_decisions.csv"; // Archivo de decisiones (carpeta Common\Files)
input bool   InpDryRun        = false; // true = solo señales: registra todo pero NO envía órdenes
input bool   InpAllowRealAccount = false; // false = en cuenta REAL funciona solo en modo señales
input bool   InpPushNotify    = true;  // Notificaciones al celular (configurar MetaQuotes ID en MT5)

//==================== ESTADO ========================================
struct Ctx
{
   bool   ok;
   bool   trendUp;
   bool   trendDn;
   bool   emaUp;
   bool   emaDn;
   double atr;
   int    signal;   // 1 compra, -1 venta, 0 nada
};

CTrade   trade;
int      hTrend = INVALID_HANDLE, hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE;
int      hRSI = INVALID_HANDLE, hADX = INVALID_HANDLE, hATR = INVALID_HANDLE;
datetime g_lastBar = 0;
double   g_atr = 0.0;
string   g_prefix;
string   g_lastInfo = "";
datetime g_lastNewsCheck = 0;
bool     g_newsBlocked = false;
bool     g_dryRun = false;
datetime g_lastCloseTry = 0;
datetime g_lastCloseAlert = 0;
double   g_lastRiskMoney = 0.0;

//==================== VARIABLES PERSISTENTES ========================
// Se guardan como variables globales del terminal: sobreviven a reinicios.
string GVName(const string k)              { return g_prefix + k; }
double GVGet(const string k, double def)   { return GlobalVariableCheck(GVName(k)) ? GlobalVariableGet(GVName(k)) : def; }
void   GVSet(const string k, double v)     { GlobalVariableSet(GVName(k), v); }
void   GVDel(const string k)               { if(GlobalVariableCheck(GVName(k))) GlobalVariableDel(GVName(k)); }

//==================== UTILIDADES ====================================
void Notify(const string msg)
{
   Print("[GoldGuardian] ", msg);
   if(InpPushNotify && !MQLInfoInteger(MQL_TESTER))
      SendNotification("GoldGuardian " + _Symbol + ": " + msg);
}

double NormPrice(double p)
{
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts <= 0) ts = _Point;
   return NormalizeDouble(MathRound(p / ts) * ts, _Digits);
}

double MinStopDistance()
{
   long stops  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freeze = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)(MathMax(stops, freeze) + 5) * _Point;
}

bool GetBuf(int handle, int buffer, int shift, int count, double &arr[])
{
   ArraySetAsSeries(arr, true);
   return CopyBuffer(handle, buffer, shift, count, arr) == count;
}

bool IsMine()
{
   return PositionGetString(POSITION_SYMBOL) == _Symbol &&
          PositionGetInteger(POSITION_MAGIC) == InpMagic;
}

int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t != 0 && IsMine()) n++;
   }
   return n;
}

void CloseAll(const string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !IsMine()) continue;
      if(trade.PositionClose(t))
         PrintFormat("Cerrada posición %I64u. Motivo: %s", t, reason);
      else
         PrintFormat("No se pudo cerrar %I64u (%s). Código: %d", t, reason, trade.ResultRetcode());
   }
}

// Si un límite ordenó cerrar y queda algo abierto, reintenta hasta confirmar el cierre.
// Depende de "closePending" (no de dayHalt), así que sobrevive al cambio de día y a reinicios.
void EnforcePendingClose()
{
   if(GVGet("closePending", 0) != 1) return;
   if(CountMyPositions() == 0)
   {
      GVSet("closePending", 0);
      Notify("Cierre confirmado: no quedan posiciones abiertas.");
      return;
   }
   datetime now = TimeCurrent();
   if(now - g_lastCloseTry < 5) return;
   g_lastCloseTry = now;
   CloseAll("reintento tras límite de riesgo");
   if(CountMyPositions() > 0 && now - g_lastCloseAlert >= 300)
   {
      g_lastCloseAlert = now;
      Notify("ATENCION: no se pudo cerrar la posición tras un límite de riesgo. Sigue reintentando; revísala.");
   }
}

datetime DayStart()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   return StructToTime(dt);
}

int TradesToday()
{
   if(g_dryRun) return (int)GVGet("dryTrades", 0);   // en modo señales no hay operaciones reales que contar
   if(!HistorySelect(DayStart(), TimeCurrent() + 86400)) return 0;
   int n = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) n++;
   }
   return n;
}

void PrintSymbolInfo()
{
   double cs   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double p    = 0.0;
   if(bid > 0 && !OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, vmin, bid, bid + 1.0, p)) p = 0.0;
   PrintFormat("[GoldGuardian] %s | contrato: %.2f | lote mín: %.2f | paso: %.2f | con lote mín, cada $1 de movimiento del oro = %.2f %s",
               _Symbol, cs, vmin, step, p, AccountInfoString(ACCOUNT_CURRENCY));
}

//==================== CONTROL DEL DÍA ===============================
void UpdateDay()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   double key = dt.year * 10000.0 + dt.mon * 100.0 + dt.day;
   if(GVGet("day", 0) != key)
   {
      GVSet("day", key);
      GVSet("dayStartBal", AccountInfoDouble(ACCOUNT_BALANCE));
      GVSet("dayHalt", 0);
      GVSet("dryTrades", 0);
   }
}

//==================== INTERRUPTORES DE RIESGO (cada tick) ===========
bool RiskGuards(string &why)
{
   double eq   = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak = GVGet("peak", eq);
   if(eq > peak) { peak = eq; GVSet("peak", peak); }

   if(GVGet("halted", 0) == 1)
   {
      why = "APAGADO por drawdown máximo. Revisa y reinicia con InpResetKillSwitch=true";
      return false;
   }
   if(eq <= peak * (1.0 - InpMaxDrawdownPercent / 100.0))
   {
      CloseAll("drawdown máximo alcanzado");
      if(CountMyPositions() > 0) GVSet("closePending", 1);
      GVSet("halted", 1);
      Notify("Drawdown máximo alcanzado. EA apagado.");
      why = "APAGADO por drawdown máximo";
      Alert("[GoldGuardian] Drawdown máximo alcanzado. EA apagado.");
      return false;
   }

   double ds = GVGet("dayStartBal", eq);
   if(GVGet("dayHalt", 0) == 1)
   {
      why = "Límite de pérdida diaria alcanzado. Vuelve mañana";
      return false;
   }
   if(eq <= ds * (1.0 - InpDailyLossPercent / 100.0))
   {
      CloseAll("límite de pérdida diaria");
      if(CountMyPositions() > 0) GVSet("closePending", 1);
      GVSet("dayHalt", 1);
      Notify("Límite de pérdida diaria alcanzado. Sin operaciones hasta mañana.");
      why = "Límite de pérdida diaria alcanzado";
      return false;
   }

   datetime pauseUntil = (datetime)GVGet("pauseUntil", 0);
   if(TimeCurrent() < pauseUntil)
   {
      why = "Pausa por racha perdedora hasta " + TimeToString(pauseUntil, TIME_DATE | TIME_MINUTES);
      return false;
   }
   return true;
}

//==================== FILTRO DE NOTICIAS ============================
bool NewsBlocked()
{
   if(!InpUseNewsFilter) return false;
   if(MQLInfoInteger(MQL_TESTER)) return false;          // el calendario no existe en el probador
   if(TimeCurrent() - g_lastNewsCheck < 60) return g_newsBlocked;
   g_lastNewsCheck = TimeCurrent();
   g_newsBlocked   = false;

   MqlCalendarValue values[];
   datetime now  = TimeTradeServer();
   datetime from = now - InpNewsAfterMin * 60;
   datetime to   = now + InpNewsBeforeMin * 60;
   if(CalendarValueHistory(values, from, to, NULL, "USD") > 0)
   {
      for(int i = 0; i < ArraySize(values); i++)
      {
         MqlCalendarEvent ev;
         if(CalendarEventById(values[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
         {
            g_newsBlocked = true;
            break;
         }
      }
   }
   return g_newsBlocked;
}

//==================== FILTROS DE ENTRADA ============================
bool EntryFilters(string &why)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(InpCloseFriday && dt.day_of_week == 5 && dt.hour >= InpFridayCloseHour - 2)
   { why = "Viernes tarde: sin nuevas entradas"; return false; }

   bool inSession = (InpStartHour < InpEndHour)
                    ? (dt.hour >= InpStartHour && dt.hour < InpEndHour)
                    : (dt.hour >= InpStartHour || dt.hour < InpEndHour);
   if(!inSession) { why = "Fuera del horario de operación"; return false; }

   // En el probador no existe el calendario: se bloquea la ventana típica de datos de EE.UU. (8:30 ET)
   if(InpTesterDataBlock && MQLInfoInteger(MQL_TESTER))
   {
      int hhmm = dt.hour * 100 + dt.min;
      if(hhmm >= InpDataBlockFrom && hhmm < InpDataBlockTo)
      { why = "Ventana de datos de EE.UU. (probador)"; return false; }
   }

   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk)) { why = "Sin precio"; return false; }
   double spread = tk.ask - tk.bid;
   double slDist = g_atr * InpSL_ATR;
   double maxSpr = InpMaxSpreadUSD;
   if(slDist > 0) maxSpr = MathMin(maxSpr, slDist * InpMaxSpreadPctSL / 100.0);
   if(spread > maxSpr)
   { why = StringFormat("Spread alto (%.2f > %.2f)", spread, maxSpr); return false; }

   if(TradesToday() >= InpMaxTradesPerDay) { why = "Máximo de operaciones del día"; return false; }
   if(NewsBlocked()) { why = "Noticia USD de alto impacto cerca"; return false; }
   return true;
}

//==================== LECTURA DE MERCADO (vela cerrada) =============
Ctx ReadContext()
{
   Ctx c;
   ZeroMemory(c);
   int    look = MathMax(InpPullbackBars, 1);
   double t[], f[], s[], r[], a[], x[];
   if(!GetBuf(hTrend, 0, 1, 1, t) || !GetBuf(hFast, 0, 1, 2, f) || !GetBuf(hSlow, 0, 1, 2, s) ||
      !GetBuf(hRSI, 0, 1, look + 1, r) || !GetBuf(hADX, 0, 1, 1, a) || !GetBuf(hATR, 0, 1, 1, x))
      return c;

   double closeTrend = iClose(_Symbol, InpTrendTF, 1);
   double close1     = iClose(_Symbol, InpTF, 1);
   double close2     = iClose(_Symbol, InpTF, 2);
   if(closeTrend <= 0 || close1 <= 0 || close2 <= 0) return c;

   // ¿Hubo retroceso en las últimas velas? (RSI pasó por debajo de 40 / encima de 60)
   double rsiMin = 100.0, rsiMax = 0.0;
   for(int k = 1; k <= look; k++) { rsiMin = MathMin(rsiMin, r[k]); rsiMax = MathMax(rsiMax, r[k]); }

   c.trendUp = closeTrend > t[0];
   c.trendDn = closeTrend < t[0];
   c.emaUp   = f[0] > s[0];
   c.emaDn   = f[0] < s[0];
   c.atr     = x[0];

   bool adxOk = a[0] >= InpADXMin;
   // Compra: tendencia alcista + hubo retroceso reciente + el precio vuelve a cerrar sobre la EMA rápida
   if(c.trendUp && c.emaUp && adxOk && rsiMin < InpRSIBuy && close2 <= f[1] && close1 > f[0])
      c.signal = 1;
   // Venta: espejo
   else if(c.trendDn && c.emaDn && adxOk && rsiMax > InpRSISell && close2 >= f[1] && close1 < f[0])
      c.signal = -1;

   c.ok = true;
   return c;
}

//==================== TAMAÑO DE POSICIÓN ============================
double CalcLots(int dir, double entry, double sl, string &why)
{
   ENUM_ORDER_TYPE ot = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double profit = 0.0;
   if(!OrderCalcProfit(ot, _Symbol, 1.0, entry, sl, profit) || profit >= 0)
   { why = "No se pudo calcular el riesgo"; return 0; }

   double lossPerLot = -profit;
   double bal  = AccountInfoDouble(ACCOUNT_BALANCE);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = vmin;

   double lots = MathFloor((bal * InpRiskPercent / 100.0) / lossPerLot / step) * step;
   if(lots < vmin)
   {
      double minRiskPct = lossPerLot * vmin / bal * 100.0;
      if(minRiskPct > InpMaxRiskPercent)
      {
         why = StringFormat("Con el lote mínimo arriesgaría %.1f%% del balance (límite %.1f%%). No opera.",
                            minRiskPct, InpMaxRiskPercent);
         return 0;
      }
      lots = vmin;
   }
   lots = NormalizeDouble(MathMin(lots, vmax), 2);

   // Riesgo real de este lote, ya redondeado: debe caber en el máximo por operación...
   double riskMoney = lossPerLot * lots;
   double riskPct   = bal > 0 ? riskMoney / bal * 100.0 : 100.0;
   if(riskPct > InpMaxRiskPercent + 1e-9)
   {
      why = StringFormat("Riesgo %.2f%% supera el máximo por operación (%.2f%%). No opera.", riskPct, InpMaxRiskPercent);
      return 0;
   }
   // ...y en lo que queda del presupuesto de pérdida del día.
   double dayStart  = GVGet("dayStartBal", bal);
   double lostToday = MathMax(0.0, dayStart - AccountInfoDouble(ACCOUNT_EQUITY));
   double remaining = dayStart * InpDailyLossPercent / 100.0 - lostToday;
   if(riskMoney > remaining)
   {
      why = StringFormat("Riesgo %.2f supera lo que queda del límite diario (%.2f). No opera.", riskMoney, remaining);
      return 0;
   }
   g_lastRiskMoney = riskMoney;

   double margin = 0.0;
   if(!OrderCalcMargin(ot, _Symbol, lots, entry, margin) ||
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.8)
   { why = "Margen insuficiente"; return 0; }

   return lots;
}

//==================== REGISTRO DE DECISIONES ========================
// Una fila por cada señal: se abrió, se bloqueó (y por qué) o la rechazó el bróker.
// "position" permite unir este archivo con el CSV de operaciones para medir R y deslizamiento.
void LogDecision(int dir, const string decision, const string reason, double req, double sl, double tp,
                 double lots, double riskMoney, long retcode, double fill, ulong position)
{
   if(!InpLogDecisions) return;
   int fh = FileOpen(InpDecisionCSV, FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI, ';');
   if(fh == INVALID_HANDLE) return;
   if(FileSize(fh) == 0)
      FileWrite(fh, "time", "signal_bar", "mode", "signal", "decision", "reason", "requested", "sl", "tp",
                "lots", "risk_money", "balance", "spread", "atr", "retcode", "fill", "slippage", "position");
   FileSeek(fh, 0, SEEK_END);

   MqlTick tk;
   SymbolInfoTick(_Symbol, tk);
   if(req <= 0) req = (dir > 0) ? tk.ask : tk.bid;
   string slip = "";                                     // positivo = se llenó peor de lo pedido
   if(fill > 0) slip = DoubleToString((dir > 0) ? fill - req : req - fill, _Digits);
   string why = reason;
   StringReplace(why, ";", ",");

   FileWrite(fh,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             TimeToString(iTime(_Symbol, InpTF, 1), TIME_DATE | TIME_MINUTES),
             g_dryRun ? "SIGNAL_ONLY" : "TRADING",
             dir > 0 ? "BUY" : "SELL",
             decision,
             why,
             DoubleToString(req, _Digits),
             DoubleToString(sl, _Digits),
             DoubleToString(tp, _Digits),
             DoubleToString(lots, 2),
             DoubleToString(riskMoney, 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
             DoubleToString(tk.ask - tk.bid, _Digits),
             DoubleToString(g_atr, _Digits),
             retcode,
             fill > 0 ? DoubleToString(fill, _Digits) : "",
             slip,
             position);
   FileClose(fh);
}

//==================== APERTURA ======================================
void TryOpen(const Ctx &c)
{
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk)) return;

   int    dir    = c.signal;
   double entry  = (dir > 0) ? tk.ask : tk.bid;
   double minD   = MinStopDistance();
   double slDist = MathMax(c.atr * InpSL_ATR, minD);
   double tpDist = MathMax(c.atr * InpTP_ATR, minD);
   double sl     = NormPrice((dir > 0) ? entry - slDist : entry + slDist);
   double tp     = NormPrice((dir > 0) ? entry + tpDist : entry - tpDist);

   string why = "";
   double lots = CalcLots(dir, entry, sl, why);
   if(lots <= 0)
   {
      g_lastInfo = why;
      Print("[GoldGuardian] ", why);
      LogDecision(dir, "BLOCKED", why, entry, sl, tp, 0.0, 0.0, 0, 0.0, 0);
      return;
   }

   if(g_dryRun)
   {
      GVSet("dryTrades", GVGet("dryTrades", 0) + 1);
      g_lastInfo = StringFormat("SEÑAL %s %.2f lotes | SL %.2f | TP %.2f (no enviada)", dir > 0 ? "COMPRA" : "VENTA", lots, sl, tp);
      LogDecision(dir, "WOULD_OPEN", "Modo solo señales", entry, sl, tp, lots, g_lastRiskMoney, 0, 0.0, 0);
      Notify(g_lastInfo);
      return;
   }

   bool ok = (dir > 0) ? trade.Buy(lots, _Symbol, entry, sl, tp, "GoldGuardian")
                       : trade.Sell(lots, _Symbol, entry, sl, tp, "GoldGuardian");

   if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      ulong pos = trade.ResultOrder();
      GVSet("R_" + IntegerToString((long)pos), slDist);   // riesgo inicial para break-even/trailing
      g_lastInfo = StringFormat("%s %.2f lotes | SL %.2f | TP %.2f", dir > 0 ? "COMPRA" : "VENTA", lots, sl, tp);
      LogDecision(dir, "OPENED", "", entry, sl, tp, lots, g_lastRiskMoney, trade.ResultRetcode(), trade.ResultPrice(), pos);
      Notify(g_lastInfo);
   }
   else
   {
      string msg = StringFormat("Orden rechazada. Código %d: %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      LogDecision(dir, "REJECTED", msg, entry, sl, tp, lots, g_lastRiskMoney, trade.ResultRetcode(), 0.0, 0);
      Notify(msg);
   }
}

//==================== GESTIÓN EN VIVO (cada tick) ===================
void ManagePositions()
{
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk)) return;
   double minD = MinStopDistance();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !IsMine()) continue;

      long   type = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      double R    = GVGet("R_" + IntegerToString((long)t), g_atr * InpSL_ATR);
      if(R <= 0) continue;

      bool   isBuy = (type == POSITION_TYPE_BUY);
      double price = isBuy ? tk.bid : tk.ask;
      double gain  = isBuy ? price - open : open - price;
      double newSL = sl;

      // 1) Break-even: asegura no perder cuando ya ganó InpBE_R veces el riesgo
      if(gain >= InpBE_R * R)
      {
         double spread = tk.ask - tk.bid;
         double be = isBuy ? open + spread : open - spread;
         if(isBuy && (newSL < be || newSL == 0)) newSL = be;
         if(!isBuy && (newSL > be || newSL == 0)) newSL = be;
      }
      // 2) Trailing: persigue el precio cuando ya ganó 1R
      if(InpUseTrailing && g_atr > 0 && gain >= R)
      {
         double tr = isBuy ? price - g_atr * InpTrail_ATR : price + g_atr * InpTrail_ATR;
         if(isBuy && tr > newSL) newSL = tr;
         if(!isBuy && (tr < newSL || newSL == 0)) newSL = tr;
      }

      newSL = NormPrice(newSL);
      if(MathAbs(newSL - sl) >= _Point && MathAbs(price - newSL) >= minD)
         trade.PositionModify(t, newSL, tp);
   }
}

void ReversalExit(const Ctx &c)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || !IsMine()) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      if(type == POSITION_TYPE_BUY && (c.trendDn || c.emaDn))
      { trade.PositionClose(t); Print("[GoldGuardian] Compra cerrada: la tendencia se invirtió"); }
      if(type == POSITION_TYPE_SELL && (c.trendUp || c.emaUp))
      { trade.PositionClose(t); Print("[GoldGuardian] Venta cerrada: la tendencia se invirtió"); }
   }
}

//==================== LOG CSV =======================================
void LogDeal(ulong deal, double pnl)
{
   int fh = FileOpen(InpCSVName, FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI, ';');
   if(fh == INVALID_HANDLE) return;
   if(FileSize(fh) == 0)
      FileWrite(fh, "time", "deal", "position", "type", "entry", "volume", "price",
                "pnl_total", "balance", "equity", "spread", "atr", "reason");
   FileSeek(fh, 0, SEEK_END);

   MqlTick tk;
   SymbolInfoTick(_Symbol, tk);
   long type  = HistoryDealGetInteger(deal, DEAL_TYPE);
   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);

   FileWrite(fh,
             TimeToString((datetime)HistoryDealGetInteger(deal, DEAL_TIME), TIME_DATE | TIME_SECONDS),
             (long)deal,
             HistoryDealGetInteger(deal, DEAL_POSITION_ID),
             type == DEAL_TYPE_BUY ? "BUY" : "SELL",
             entry == DEAL_ENTRY_IN ? "IN" : "OUT",
             DoubleToString(HistoryDealGetDouble(deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(deal, DEAL_PRICE), _Digits),
             DoubleToString(pnl, 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
             DoubleToString(tk.ask - tk.bid, _Digits),
             DoubleToString(g_atr, _Digits),
             EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(deal, DEAL_REASON)));
   FileClose(fh);
}

//==================== PANEL EN EL GRÁFICO ===========================
void Dashboard(const string status)
{
   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE)) return;
   double eq   = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak = GVGet("peak", eq);
   double dd   = peak > 0 ? (peak - eq) / peak * 100.0 : 0.0;
   MqlTick tk;
   SymbolInfoTick(_Symbol, tk);
   Comment(StringFormat(
      "GoldGuardian v1.3 %s\n"
      "Balance: %.2f | Equity: %.2f\n"
      "Pico: %.2f | Caída desde pico: %.1f%% (límite %.0f%%)\n"
      "Inicio del día: %.2f | Ops hoy: %d/%d | Racha pérdidas: %d\n"
      "Spread: %.2f | ATR: %.2f\n"
      "Estado: %s\n"
      "Última acción: %s",
      g_dryRun ? "[SOLO SEÑALES - no envía órdenes]" : "",
      AccountInfoDouble(ACCOUNT_BALANCE), eq, peak, dd, InpMaxDrawdownPercent,
      GVGet("dayStartBal", eq), TradesToday(), InpMaxTradesPerDay, (int)GVGet("consec", 0),
      tk.ask - tk.bid, g_atr,
      status == "" ? "Operativo" : status,
      g_lastInfo == "" ? "-" : g_lastInfo));
}

//==================== EVENTOS =======================================
int OnInit()
{
   g_prefix = "GG_" + IntegerToString(InpMagic) + "_" + _Symbol + "_";

   if(InpResetKillSwitch)
   {
      GVSet("halted", 0);
      GVSet("peak", AccountInfoDouble(ACCOUNT_EQUITY));
      GVSet("consec", 0);
      GVSet("pauseUntil", 0);
      Print("[GoldGuardian] Interruptores reiniciados. Vuelve a poner InpResetKillSwitch=false.");
   }
   if(!GlobalVariableCheck(GVName("peak"))) GVSet("peak", AccountInfoDouble(ACCOUNT_EQUITY));

   bool isReal = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL;
   g_dryRun = InpDryRun || (isReal && !InpAllowRealAccount);
   if(isReal && !InpAllowRealAccount)
      Print("[GoldGuardian] Cuenta REAL con InpAllowRealAccount=false: funciona solo en modo señales.");
   if(InpPushNotify && !MQLInfoInteger(MQL_TESTER) && !TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED))
      Print("[GoldGuardian] Notificaciones desactivadas en el terminal: configura tu MetaQuotes ID en Herramientas > Opciones.");

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFillingBySymbol(_Symbol);

   hTrend = iMA(_Symbol, InpTrendTF, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hFast  = iMA(_Symbol, InpTF, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   hSlow  = iMA(_Symbol, InpTF, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   hRSI   = iRSI(_Symbol, InpTF, InpRSIPeriod, PRICE_CLOSE);
   hADX   = iADX(_Symbol, InpTF, InpADXPeriod);
   hATR   = iATR(_Symbol, InpTF, InpATRPeriod);
   if(hTrend == INVALID_HANDLE || hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE ||
      hRSI == INVALID_HANDLE || hADX == INVALID_HANDLE || hATR == INVALID_HANDLE)
   {
      Print("[GoldGuardian] Error creando indicadores");
      return INIT_FAILED;
   }

   PrintSymbolInfo();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hTrend); IndicatorRelease(hFast); IndicatorRelease(hSlow);
   IndicatorRelease(hRSI);   IndicatorRelease(hADX);  IndicatorRelease(hATR);
   Comment("");
}

void OnTick()
{
   UpdateDay();
   EnforcePendingClose();                      // reintenta cierres pendientes antes que todo
   string status = "";
   bool riskOk = RiskGuards(status);           // interruptores: cada tick

   // Cierre del viernes
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(InpCloseFriday && dt.day_of_week == 5 && dt.hour >= InpFridayCloseHour && CountMyPositions() > 0)
      CloseAll("cierre de viernes");

   // Nueva vela: leer mercado, salidas por reversión y posibles entradas
   datetime bt = iTime(_Symbol, InpTF, 0);
   if(bt != g_lastBar)
   {
      Ctx c = ReadContext();
      if(c.ok)
      {
         g_lastBar = bt;
         g_atr = c.atr;
         if(InpExitOnReversal) ReversalExit(c);

         string why = "";
         bool canOpen = false;
         if(!riskOk)                       why = status;
         else if(CountMyPositions() != 0)  why = "Ya hay una posición abierta";
         else if(EntryFilters(why))        canOpen = true;
         else                              status = why;

         if(c.signal != 0)
         {
            if(canOpen) TryOpen(c);
            else LogDecision(c.signal, "BLOCKED", why, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0);
         }
      }
   }

   // Gestión de posiciones abiertas: cada tick
   if(CountMyPositions() > 0) ManagePositions();

   Dashboard(status);
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic) return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol) return;

   long   entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   double pnl   = HistoryDealGetDouble(trans.deal, DEAL_PROFIT) +
                  HistoryDealGetDouble(trans.deal, DEAL_SWAP) +
                  HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);

   if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
   {
      Notify(StringFormat("Posición cerrada. Resultado: %.2f", pnl));
      int consec = (int)GVGet("consec", 0);
      consec = (pnl < 0) ? consec + 1 : 0;
      if(consec >= InpMaxConsecLosses)
      {
         GVSet("pauseUntil", (double)(TimeCurrent() + InpPauseHours * 3600));
         Notify(StringFormat("%d pérdidas seguidas. Pausa de %d horas.", consec, InpPauseHours));
         consec = 0;
      }
      GVSet("consec", consec);
      GVDel("R_" + IntegerToString(HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID)));
   }

   if(InpLogCSV) LogDeal(trans.deal, pnl);
}
//+------------------------------------------------------------------+
