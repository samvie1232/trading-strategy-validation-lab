# Resultados H8: cambio de mes (4 de noviembre de 2026)
Reglas: [`PREREGISTRO.md`](PREREGISTRO.md). XM D1, fuera de muestra de 2017 a 2026, cuenta demo. **No aprueba.**

| Criterio | Resultado | Exigido | Pasa |
|---|---:|---:|---|
| Operaciones | 468 | >= 100 | Sí |
| Sharpe | 0,25 | >= 0,5 | No |
| Eficiencia walk-forward | 0,77 | >= 0,5 | Sí |
| Ventanas positivas | 55 % | >= 55 % | Sí |
| Caída p95 Monte Carlo | 18,8 % | <= 25 % | Sí |
| Sharpe con doble costo | 0,22 | >= 0,2 | Sí |
| Deflated Sharpe | 0,53 | >= 0,95 | No |
| Mejor que ventanas al azar | 0,081 % vs p95 0,163 % | > p95 | No |

Retorno anual: +1,0 %; aciertos: 56 %; exposición: 19 %. El resultado medio por operación queda en el percentil 57 de ventanas al azar (mediana 0,072 %), así que no se distingue de estar comprado cualquier otro día del mes.

Sin swap: Sharpe 0,38; sigue sin superar el azar (percentil 58).

Contexto: comprar y mantener US500Cash dio Sharpe 0,43 y 6,3 % anual con caída de 34,6 %, usando el swap actual en todo el periodo.

Controles: 0 de 5 corridas barajadas aprueban, 2 de 2 con efecto plantado aprueban, sin fallas de causalidad ni de costos.
