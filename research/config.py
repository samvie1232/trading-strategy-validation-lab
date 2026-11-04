"""
Configuración del motor de investigación.

REGLA DE ORO: los criterios de aprobación (APPROVAL) se fijan ANTES de ver resultados.
No los cambies después de correr el motor para que una estrategia "pase".
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Copia en "data" los CSV exportados desde MT5. Para probar con datos falsos: XM_DATA_DIR=data_synthetic
DATA_DIR = BASE_DIR / os.environ.get("XM_DATA_DIR", "data")
OUT_DIR = BASE_DIR / os.environ.get("XM_OUT_DIR", "output")   # Reporte, gráficos y CSV de resultados

# ------------------------------------------------------------------
# Costos
# ------------------------------------------------------------------
# El spread se toma de los datos exportados (columna spread_points de cada vela).
# Si una vela trae spread 0 o falta, se usa el spread actual del símbolo (symbols_spec.csv).
COST_MULTIPLIER = 1.0          # 1.0 = spread real. El "stress test" usa STRESS_COST_MULTIPLIER
STRESS_COST_MULTIPLIER = 2.0   # Se repite todo con el doble de costos
SLIPPAGE_FRAC_OF_SPREAD = 0.25 # Deslizamiento extra = 25% del spread por operación
STOP_FILL_SLIPPAGE = 0.5       # Órdenes stop (rupturas y stop loss): se llenan 0.5 spread peor que el nivel
USE_REAL_SWAPS = True          # Usa los swaps reales de XM (symbols_spec.csv) para posiciones de varios días
FINANCING_ANNUAL = 0.06        # Solo si no hay swaps reales: costo aprox. anual del nocional
# Cómo se lleva el swap actual del bróker al pasado (no hay swap histórico):
#   constant_pct: el % sobre el nocional de hoy se aplica a toda la historia (por defecto).
#   legacy_fixed: el swap en puntos/moneda se fija y se divide por el precio de cada fecha.
#                 Sobreestima el costo cuando el precio era menor (oro 2017: -22.8%/año vs -6.4% en 2026).
#   zero:         sin swap (diagnóstico).
SWAP_MODEL = os.environ.get("XM_SWAP_MODEL", "constant_pct")

# ------------------------------------------------------------------
# Walk-forward y Monte Carlo
# ------------------------------------------------------------------
WF_TRAIN_YEARS = 2.0           # Ventana de entrenamiento (se elige el mejor parámetro aquí)
WF_TEST_MONTHS = 6             # Ventana de prueba fuera de muestra
MC_SIMULATIONS = 2000          # Simulaciones Monte Carlo (bootstrap por bloques)
MC_BLOCK_DAYS = 10             # Tamaño de bloque en días
RANDOM_SEED = 42

# ------------------------------------------------------------------
# Familia 1: seguimiento de tendencia multi-mercado (velas diarias)
# ------------------------------------------------------------------
# Usa todos los símbolos con archivo *_D1.csv, salvo que pongas una lista.
TREND = {
    "enabled": True,
    "timeframe": "D1",
    "symbols": [],                 # [] = todos los que haya en data/
    "target_vol_annual": 0.10,     # Volatilidad objetivo por mercado (10% anual)
    "vol_lookback": 60,            # Días para estimar la volatilidad
    "max_leverage": 4.0,
    "param_grid": [
        {"type": "ema", "fast": 20, "slow": 100, "long_only": False},
        {"type": "ema", "fast": 50, "slow": 200, "long_only": False},
        {"type": "donchian", "entry": 20, "exit": 10, "long_only": False},
        {"type": "donchian", "entry": 55, "exit": 20, "long_only": False},
        {"type": "donchian", "entry": 100, "exit": 50, "long_only": False},
        {"type": "tsmom", "lookback": 126, "long_only": False},
        {"type": "tsmom", "lookback": 252, "long_only": False},
    ],
}

# ------------------------------------------------------------------
# Familia 2: momentum intradía en índices de EE.UU. (velas M30)
# Gao, Han, Li, Zhou: el retorno de la 1ª media hora predice la última media hora.
# Horas en HORA DEL SERVIDOR de XM (≈ hora de Nueva York + 7).
# ------------------------------------------------------------------
INTRADAY_MOM = {
    "enabled": True,
    "timeframe": "M30",
    "symbols": ["US500Cash", "US100Cash", "US30Cash"],   # Ajusta a los nombres reales de XM (ver all_symbols.csv)
    "first_bar": "16:30",          # Vela de 9:30-10:00 Nueva York
    "last_bar": "22:30",           # Vela de 15:30-16:00 Nueva York
    "target_trade_vol": 0.005,     # Riesgo típico por operación: 0.5% del capital
    "vol_lookback": 60,
    "max_leverage": 6.0,
    "param_grid": [
        {"threshold": 0.0, "from_prev_close": True},
        {"threshold": 0.001, "from_prev_close": True},
        {"threshold": 0.002, "from_prev_close": True},
        {"threshold": 0.0, "from_prev_close": False},
        {"threshold": 0.001, "from_prev_close": False},
    ],
}

# ------------------------------------------------------------------
# Familia 3: ruptura del rango asiático (velas M30)
# ------------------------------------------------------------------
ASIAN_BREAKOUT = {
    "enabled": True,
    "timeframe": "M30",
    "symbols": ["GOLD", "EURUSD", "GBPUSD"],
    "range_start": "01:00",        # Inicio del rango (hora servidor)
    "range_end": "10:00",          # Fin del rango = apertura de Londres
    "entry_end": "14:00",          # Hasta esta hora se acepta la ruptura
    "exit_time": "22:00",          # Cierre forzado del día
    "risk_per_trade": 0.005,       # 0.5% del capital por operación
    "param_grid": [
        {"tp_mult": 1.0, "stop": "opposite"},
        {"tp_mult": 1.5, "stop": "opposite"},
        {"tp_mult": 1.0, "stop": "mid"},
        {"tp_mult": 1.5, "stop": "mid"},
        {"tp_mult": 2.0, "stop": "mid"},
    ],
}

# ------------------------------------------------------------------
# Criterios de aprobación (definidos ANTES de ver resultados)
# ------------------------------------------------------------------
APPROVAL = {
    "min_trades_oos": 100,          # Operaciones fuera de muestra
    "min_oos_sharpe": 0.5,
    "min_wfe": 0.5,                 # Eficiencia walk-forward: retorno OOS / retorno IS
    "min_pct_positive_windows": 0.55,
    "max_mc_p95_drawdown": 0.25,    # El 95% de los escenarios con caída < 25%
    "min_stress_sharpe": 0.2,       # Con el doble de costos sigue positivo
}
