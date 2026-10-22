//+------------------------------------------------------------------+
//|                                                 ExportData.mq5   |
//|  Exporta historial OHLC + spread de varios símbolos a CSV        |
//|  para el motor de investigación en Python (xm_research).         |
//|  Los archivos quedan en: <Datos comunes>\Files\xm_research\      |
//+------------------------------------------------------------------+
#property copyright "Santiago - uso personal"
#property version   "1.00"
#property script_show_inputs

input string   InpSymbols       = "";              // Símbolos separados por coma (vacío = todos los de Observación del Mercado)
input string   InpTimeframes    = "D1,H4,M30";     // Temporalidades a exportar
input datetime InpFromDaily     = D'2015.01.01';   // Desde (D1 y H4)
input datetime InpFromIntraday  = D'2021.01.01';   // Desde (M30 y menores)
input string   InpFolder        = "xm_research";   // Subcarpeta dentro de Common\Files
input bool     InpListAllSymbols = true;           // Además, guardar la lista de TODOS los símbolos del bróker

//------------------------------------------------------------------
ENUM_TIMEFRAMES TfFromString(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   StringToUpper(s);
   if(s == "M1")  return PERIOD_M1;
   if(s == "M5")  return PERIOD_M5;
   if(s == "M15") return PERIOD_M15;
   if(s == "M30") return PERIOD_M30;
   if(s == "H1")  return PERIOD_H1;
   if(s == "H4")  return PERIOD_H4;
   if(s == "D1")  return PERIOD_D1;
   if(s == "W1")  return PERIOD_W1;
   return PERIOD_CURRENT;
}

string TfName(ENUM_TIMEFRAMES tf)
{
   string s = EnumToString(tf);          // "PERIOD_D1"
   StringReplace(s, "PERIOD_", "");
   return s;
}

// Fuerza la descarga del historial del servidor (puede tardar la primera vez)
void EnsureHistory(const string sym, ENUM_TIMEFRAMES tf, datetime from)
{
   for(int i = 0; i < 20; i++)
   {
      long firstDate = 0;
      if(SeriesInfoInteger(sym, tf, SERIES_FIRSTDATE, firstDate) && firstDate > 0 && (datetime)firstDate <= from)
         return;
      MqlRates tmp[];
      CopyRates(sym, tf, from, TimeCurrent(), tmp);
      Sleep(300);
   }
}

bool ExportRates(const string sym, ENUM_TIMEFRAMES tf, datetime from)
{
   EnsureHistory(sym, tf, from);

   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int n = CopyRates(sym, tf, from, TimeCurrent(), rates);
   if(n <= 0)
   {
      PrintFormat("[Export] %s %s: sin datos (error %d)", sym, TfName(tf), GetLastError());
      return false;
   }

   string fname = InpFolder + "\\" + sym + "_" + TfName(tf) + ".csv";
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE)
   {
      PrintFormat("[Export] No se pudo crear %s (error %d)", fname, GetLastError());
      return false;
   }

   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   FileWrite(fh, "time", "open", "high", "low", "close", "tick_volume", "spread_points");
   for(int i = 0; i < n; i++)
   {
      FileWrite(fh,
                TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES),
                DoubleToString(rates[i].open,  digits),
                DoubleToString(rates[i].high,  digits),
                DoubleToString(rates[i].low,   digits),
                DoubleToString(rates[i].close, digits),
                (long)rates[i].tick_volume,
                (long)rates[i].spread);
   }
   FileClose(fh);
   PrintFormat("[Export] %s %s: %d barras desde %s", sym, TfName(tf), n,
               TimeToString(rates[0].time, TIME_DATE));
   return true;
}

string Clean(string s)
{
   StringReplace(s, ",", " ");
   StringReplace(s, ";", " ");
   return s;
}

void WriteSpec(int fh, const string sym)
{
   FileWrite(fh,
             sym,
             SymbolInfoInteger(sym, SYMBOL_DIGITS),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_POINT), 10),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 4),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), 10),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 6),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 4),
             SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT),
             SymbolInfoInteger(sym, SYMBOL_SPREAD),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_SWAP_LONG), 4),
             DoubleToString(SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT), 4),
             EnumToString((ENUM_SYMBOL_SWAP_MODE)SymbolInfoInteger(sym, SYMBOL_SWAP_MODE)),
             Clean(SymbolInfoString(sym, SYMBOL_DESCRIPTION)));
}

void ListAllSymbols()
{
   string fname = InpFolder + "\\all_symbols.csv";
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE) return;
   FileWrite(fh, "symbol", "path", "description");
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
   {
      string s = SymbolName(i, false);
      FileWrite(fh, s, Clean(SymbolInfoString(s, SYMBOL_PATH)), Clean(SymbolInfoString(s, SYMBOL_DESCRIPTION)));
   }
   FileClose(fh);
   PrintFormat("[Export] Lista de %d símbolos guardada en %s", total, fname);
}

//------------------------------------------------------------------
void OnStart()
{
   // 1) Lista de símbolos a exportar
   string syms[];
   if(StringLen(InpSymbols) > 0)
   {
      StringSplit(InpSymbols, ',', syms);
   }
   else
   {
      int total = SymbolsTotal(true);
      ArrayResize(syms, total);
      for(int i = 0; i < total; i++) syms[i] = SymbolName(i, true);
   }

   // 2) Temporalidades
   string tfs[];
   StringSplit(InpTimeframes, ',', tfs);

   // 3) Archivo de especificaciones
   string specName = InpFolder + "\\symbols_spec.csv";
   int fs = FileOpen(specName, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(fs != INVALID_HANDLE)
      FileWrite(fs, "symbol", "digits", "point", "contract_size", "tick_size", "tick_value",
                "volume_min", "volume_step", "currency_profit", "spread_now_points",
                "swap_long", "swap_short", "swap_mode", "description");

   int ok = 0;
   for(int i = 0; i < ArraySize(syms); i++)
   {
      string sym = syms[i];
      StringTrimLeft(sym);
      StringTrimRight(sym);
      if(sym == "") continue;
      if(!SymbolSelect(sym, true))
      {
         PrintFormat("[Export] El símbolo '%s' no existe en este bróker. Revisa all_symbols.csv", sym);
         continue;
      }
      if(fs != INVALID_HANDLE) WriteSpec(fs, sym);

      for(int j = 0; j < ArraySize(tfs); j++)
      {
         ENUM_TIMEFRAMES tf = TfFromString(tfs[j]);
         if(tf == PERIOD_CURRENT) { PrintFormat("[Export] Temporalidad no válida: %s", tfs[j]); continue; }
         datetime from = (PeriodSeconds(tf) >= PeriodSeconds(PERIOD_H4)) ? InpFromDaily : InpFromIntraday;
         if(ExportRates(sym, tf, from)) ok++;
      }
   }
   if(fs != INVALID_HANDLE) FileClose(fs);

   if(InpListAllSymbols) ListAllSymbols();

   string common = TerminalInfoString(TERMINAL_COMMONDATA_PATH) + "\\Files\\" + InpFolder;
   PrintFormat("[Export] Listo: %d archivos. Carpeta: %s", ok, common);
   Alert("Exportación terminada: ", ok, " archivos en ", common);
}
//+------------------------------------------------------------------+
