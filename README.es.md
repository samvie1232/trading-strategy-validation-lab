# Trading Strategy Validation Lab (español)

**Un pipeline de punta a punta que extrae datos de mercado desde MetaTrader 5 y trata de demostrar que una estrategia de trading NO funciona (walk-forward, Monte Carlo, stress de costos y criterios definidos de antemano) antes de arriesgar un solo dólar real.**

🇬🇧 [English version](README.md)

## En resumen

- **Pregunta:** ¿puede un algoritmo minorista ganar dinero operando CFD en un bróker real (XM, MT5) cuando se cuentan *todos* los costos?
- **Datos:** 13 mercados (oro, plata, petróleo, divisas, índices de EE. UU. y Europa, cripto). Velas diarias y de 4 horas desde 2015 y de 30 minutos desde 2021: **~1,1 millones de velas con el spread de cada una**, más los swaps reales del bróker.
- **Pruebas:** 3 familias de estrategias con respaldo académico o de practicantes, 17 combinaciones de parámetros y más de 5.300 operaciones fuera de muestra.
- **Respuesta:** **no.** Ninguna sobrevive fuera de muestra con spreads y swaps reales, y el motor muestra por qué en cada caso.

| Familia | Periodo fuera de muestra | Sharpe | Retorno anual | Sin costos de trading | Veredicto |
|---|---|---:|---:|---:|---|
| Tendencia multi-mercado (D1) | 2017 → 2026 | −0,46 | −2,1% | −2,0% | ❌ Sin prima de tendencia después de swaps |
| Momentum intradía índices EE. UU. (M30) | 2023 → 2026 | −1,82 | −10,5% | −4,2% | ❌ Sin efecto, ni siquiera antes de costos |
| Ruptura del rango asiático (M30) | 2023 → 2026 | −1,64 | −7,7% | +2,7%* | ❌ Pierde con costos en todos los mercados |

\* Ese valor coincide con lo que el mismo código produce sobre datos aleatorios (Sharpe 0,57 frente a 0,49): es un artefacto del modelo de llenado, no una ventaja.

## La historia

Empecé construyendo un bot para el oro en MQL5 ([`mql5/GoldGuardian.mq5`](mql5/GoldGuardian.mq5)) con riesgo fijo por operación, interruptores por pérdida diaria y caída máxima, pausa por rachas perdedoras y filtros de spread, sesión y noticias. En el backtest de MT5 ganaba **+6,8%**. Fuera de muestra perdió **−12,6%**, con un factor de beneficio de 0,56.

En lugar de ajustar el bot hasta que la gráfica se viera bonita, construí un laboratorio cuyo único trabajo es **rechazar** estrategias, salvo que la evidencia sea contundente.

## Qué demuestra técnicamente

- **Extracción:** script MQL5 que descarga el historial del servidor y exporta OHLC, el spread de cada vela, especificaciones de contrato y swaps reales.
- **Ingesta y calidad:** limpieza, tabla de calidad de datos y normalización de los distintos tipos de swap a % del nocional por noche.
- **Validación:** walk-forward (2 años de entrenamiento y 6 meses de prueba), Monte Carlo por bloques (2.000 caminos), stress con doble costo usando los mismos parámetros elegidos y diagnóstico sin costos.
- **Criterios de aprobación registrados antes de ver resultados**, todos obligatorios.
- **Tests en CI que validan el propio motor:**
  - Control negativo: con datos aleatorios nada debe aprobar.
  - Control positivo: un efecto sembrado a propósito debe detectarse.
  - Ausencia de sesgo de futuro, verificada con *mutation testing*: detecta 4 de 4 fugas inyectadas.
  - Costos monótonos: más costos nunca mejoran el resultado.
- **Un bug encontrado gracias al control negativo:** llenar las rupturas justo en el nivel hacía que una caminata aleatoria pareciera rentable (Sharpe 1,3). Se corrigió con deslizamiento adverso en órdenes stop.

## Cómo correrlo

```bash
cd research
pip install -r requirements.txt -r requirements-dev.txt
pytest -q tests                      # valida el motor
python make_synthetic.py             # datos de prueba
# PowerShell: $env:XM_DATA_DIR="data_synthetic"; $env:XM_OUT_DIR="output_synthetic"; python run.py
```

Con datos reales: exporta con `mql5/ExportData.mq5`, copia los CSV a `research/data/` y ejecuta `python run.py`.

Informe completo con datos reales: [`results/report_2026-10-22.md`](results/report_2026-10-22.md).

*Proyecto de investigación e ingeniería, no es asesoría de inversión. La conclusión es, explícitamente, que estas estrategias **no** deben operarse.*

**Santiago Martínez** · Data Engineer · [LinkedIn](https://www.linkedin.com/in/santiago-martinez-dataengineer)
