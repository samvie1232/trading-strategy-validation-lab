# Resultados H7: carry de funding (4 de noviembre de 2026)
Reglas: [`PREREGISTRO.md`](PREREGISTRO.md). BTC y ETH, fuera de muestra de 2022-01-01 a 2026-04-09. **No aprueba.**

| Criterio | Resultado | Exigido | Pasa |
|---|---:|---:|---|
| Pagos de funding | 2.514 | >= 100 | Sí |
| Sharpe en exceso | 2,32 | >= 0,5 | Sí |
| Sharpe con doble costo | 0,92 | >= 0,2 | Sí |
| Caída p95 Monte Carlo | 0,7 % | <= 25 % | Sí |
| Deflated Sharpe | 1,00 | >= 0,95 | Sí |
| Eficiencia walk-forward | 0,13 | >= 0,5 | No |
| Ventanas positivas | 33 % | >= 55 % | No |
| Exceso últimos 24 meses | -0,1 % | > 0 | No |

Exceso anual sobre 4 %: 0,68 %. Exposición media: 26,9 %.

Corrección posterior a los resultados: la anualización se cambió de 252 a 365 días porque cripto opera todos los días (exceso de 0,47 % a 0,68 %). El veredicto no cambia.

Controles: 0 de 5 corridas sin ventaja aprueban, 2 de 2 con ventaja plantada aprueban, sin fallas de causalidad ni de costos.

Límites: datos de un tercero hasta abril de 2026, comisiones de fuentes secundarias, y sin capturar riesgo de plataforma, auto-deleveraging ni movimientos dentro del día.
