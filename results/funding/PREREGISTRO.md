# Preregistro H7: carry de funding (delta neutral)
Fecha: 2026-11-04. Escrito antes de correr esta prueba.

**Conocimiento previo que debo declarar:** antes de escribirlo leí el resumen del repo `zwmjj/funding-rate-arb`, que reporta 9-11 % anual en BTC/ETH y carry bajo en 2025, y del paper BIS 1087. También revisé solo la forma de los datos: columnas, fechas y huecos.

## Fundamento
Compradores apalancados pagan funding para mantener exposición alcista, y el capital de arbitraje es limitado. Largo al contado + corto en el perpetuo por el mismo nocional cobra ese pago sin apostar a la dirección.

## Datos
Binance vía `zwmjj/funding-rate-arb`: funding de 8 h y cierres diarios de contado y perpetuo. BTC y ETH, 2020-01-01 a 2026-04-09. Son datos de un tercero; deben repetirse con descarga propia antes de cualquier decisión.

## Reglas
- Cartera 50/50 BTC y ETH. Corto con apalancamiento 2x: 2/3 del capital en nocional, 1/3 de margen.
- Señal al cierre del día; ejecución a ese cierre. Las liquidaciones de funding se asignan al periodo (00:00, 00:00 siguiente] en UTC, para no cobrar antes de abrir.
- Resultado diario sobre nocional: funding recibido + retorno contado − retorno perpetuo.
- Capital sin usar y ambas patas: sin intereses adicionales. El efectivo fuera de posición se supone al mismo costo de oportunidad, por lo que su exceso es 0.

## Parámetros (5)
1. `always_on`: siempre invertido.
2-5. `threshold`: ventana de media de funding {3, 21} liquidaciones x entrada {1, 2} pb por 8 h; salida con media <= 0,5 pb.

## Costos (por pata, solo ida)
Contado 10 pb, perpetuo 5 pb y 2 pb de deslizamiento por pata: 19 pb por entrada y 19 pb por salida. Son tarifas regulares de Binance según fuentes secundarias; se deben confirmar en la cuenta. Rebalanceo de margen cuando el precio se mueve 25 % desde el último ajuste: 1/3 del nocional x 19 pb. Estrés: costos x2.

## Costo de oportunidad
Todos los criterios se miden sobre el exceso frente a 4 % anual en USD mientras haya posición (supuesto aproximado para 2022-2026).

## Validación
Walk-forward: 2 años de entrenamiento y 6 meses de prueba, con selección por Sharpe en exceso.

## Criterios (todos obligatorios)
1. Liquidaciones de funding con posición OOS >= 100. **Cambio frente al Lab v2:** una estrategia que mantiene una sola posición tendría 0 o 1 operaciones, y aquí la observación repetida es cada pago.
2. Sharpe en exceso OOS >= 0,5
3. Eficiencia walk-forward >= 0,5
4. Ventanas OOS positivas >= 55 %
5. Caída p95 Monte Carlo <= 25 %
6. Sharpe en exceso con doble costo >= 0,2
7. Deflated Sharpe >= 0,95, con N = 49 intentos (44 + 5)
8. Exceso anual de los últimos 24 meses OOS > 0, porque el carry puede estar comprimiéndose

## Controles
- Negativo: funding sin media y barajado, 5 semillas. Ninguna debe aprobar.
- Positivo: el mismo funding más 3 pb por 8 h. Debe aprobar.
- Causalidad y monotonía de costos.

## Lo que esta prueba no puede ver
Quiebra de la plataforma, auto-deleveraging, liquidaciones dentro del día, congelamiento de la interfaz, desanclaje de colateral y restricciones por país. Datos diarios no capturan el evento de octubre de 2025. Por eso aprobar no equivale a recomendar dinero real.
