# Trading Strategy Validation Lab (español)

**Un pipeline de punta a punta que extrae datos de mercado desde MetaTrader 5 y trata de demostrar que una estrategia de trading NO funciona (walk-forward, Monte Carlo, stress de costos y criterios definidos de antemano) antes de arriesgar un solo dólar real.**

🇬🇧 [English version](README.md)

## En resumen

- **Pregunta:** ¿puede un algoritmo minorista ganar dinero operando CFD en un bróker real (XM, MT5) cuando se cuentan *todos* los costos?
- **Datos:** 13 mercados (oro, plata, petróleo, divisas, índices de EE. UU. y Europa, cripto). Velas diarias y de 4 horas desde 2015 y de 30 minutos desde 2021: **~1,2 millones de velas con el spread de cada una**, más los swaps actuales del bróker.
- **Pruebas:** 9 familias de estrategias tomadas de investigación, libros y foros de traders, 44 combinaciones de parámetros y más de 11.000 operaciones fuera de muestra.
- **Respuesta:** **no, para estas estrategias.** Ninguna aprueba fuera de muestra con spreads y swaps incluidos. El motor rechaza datos sin ventaja y detecta ventajas sembradas a propósito.

| Familia | Periodo fuera de muestra | Operaciones | Sharpe | Retorno anual | Sharpe sin costos* | Veredicto |
|---|---|---:|---:|---:|---:|---|
| Tendencia multi-mercado (D1) | 2017 → 2026 | 390 | −0,18 | −0,9% | 0,22 | ❌ |
| Momentum intradía índices EE. UU. (M30) | 2023 → 2026 | 2.391 | −1,83 | −10,5% | −0,69 | ❌ |
| Ruptura del rango asiático (M30) | 2023 → 2026 | 2.446 | −1,67 | −7,7% | 0,55† | ❌ |
| RSI(2) de Connors, índices (D1, solo compras) | 2017 → 2026 | 264 | 0,31 | +1,3% | 0,46 | ❌ El más cercano, bajo Sharpe 0,5 |
| RSI(2), oro y US500 (M30) | 2023 → 2026 | 1.234 | −0,63 | −1,7% | 0,53 | ❌ |
| Ruptura de canal, oro (H1) | 2023 → 2026 | 1.084 | −1,52 | −15,3% | −0,74 | ❌ |
| Salidas cortas, 64% de aciertos (M30) | 2023 → 2026 | 2.572 | −2,01 | −8,3% | 0,42 | ❌ |
| Salidas cortas + filtro de costo (M30) | 2023 → 2026 | 1.248 | −0,79 | −2,9% | 0,16 | ❌ |
| Oro/plata relativo (H4) | 2017 → 2026 | 78 | −1,07 | −7,8% | −0,58 | ❌ |

\* Sin spread, deslizamiento ni swap. Solo como referencia; no cuenta para aprobar.

† Coincide con lo que el mismo código produce sobre datos aleatorios (Sharpe 0,55 frente a 0,49): es un artefacto del modelo de llenado, no una ventaja.

## La historia

Empecé construyendo un bot para el oro en MQL5 ([`mql5/GoldGuardian.mq5`](mql5/GoldGuardian.mq5)) con riesgo fijo por operación, interruptores por pérdida diaria y caída máxima, pausa por rachas perdedoras y filtros de spread, sesión y noticias. En el backtest de MT5 ganaba **+6,8%**. Fuera de muestra perdió **−12,6%**, con un factor de beneficio de 0,56. La versión 1.3 refuerza los controles de riesgo sin cambiar las entradas y reproduce el resultado: 32 operaciones, −12,4% y factor de beneficio 0,57. Quedó más segura de operar, no rentable.

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
- **Lab v2:** [preregistro](results/lab2/PREREGISTRO.md) de reglas y criterios, Deflated Sharpe ≥ 0,95 con 44 intentos y comparación con entradas al azar. Con datos barajados, 0 de 18 corridas aprueban; las 6 familias detectan el efecto sembrado.

## Hallazgos del Lab v2

- **Salir rápido no crea ventaja:** las salidas cortas acertaron 64% y aun así perdieron 8,3% al año, sin superar el percentil 95 de entradas al azar.
- **Los costos dominan en plazos cortos:** RSI(2) en M30 pasa de Sharpe 0,53 sin costos a −0,63 con costos.
- **El RSI(2) diario es el más cercano:** Sharpe 0,31; 0,42 sin swap y 0,46 sin costos, todos bajo el mínimo de 0,5.
- **Los bots comerciales no se compraron ni auditaron:** la ruptura H1 prueba una regla pública de ese estilo, no el código de ningún vendedor.

## Corrección del swap (noviembre de 2026)

La primera versión dividía el swap fijo de hoy por cada precio histórico, lo que encarecía de más los años antiguos (oro en 2017: cerca de −22,8% anual frente a −6,4% en 2026). Ahora el swap es un % constante del nocional. Los veredictos no cambian, pero la tendencia pasa de Sharpe −0,46 a −0,18 y se retira la afirmación de que BTCUSD perdía −26% anual. Como las tasas de hoy siguen sobreestimando los años de tasas bajas, también se reporta el caso sin swap.

## Cómo correrlo

```bash
cd research
pip install -r requirements.txt -r requirements-dev.txt
pytest -q tests                      # valida el motor
python make_synthetic.py             # datos de prueba
# PowerShell: $env:XM_DATA_DIR="data_synthetic"; $env:XM_OUT_DIR="output_synthetic"; python run.py
```

Con datos reales: exporta con `mql5/ExportData.mq5`, copia los CSV a `research/data/` y ejecuta `python run.py`.

Informes: [resultados del Lab v2](results/lab2/RESULTADOS.md) · [familias originales, nov. 2026](results/report_2026-11-04.md) · [informe original, oct. 2026](results/report_2026-10-22.md).

**Límites:** estos resultados cubren las estrategias probadas con los costos de este bróker, usando spreads de cuenta demo y swaps actuales; no demuestran que no exista ninguna estrategia rentable. El preregistro es un registro interno, no certificado por un tercero.

*Proyecto de investigación e ingeniería, no es asesoría de inversión. La conclusión es, explícitamente, que estas estrategias **no** deben operarse.*

**Santiago Martínez** · Data Engineer · [LinkedIn](https://www.linkedin.com/in/santiago-martinez-dataengineer)
