# Preregistro de hipótesis — Lab v2
Fecha: 2026-11-04. Escrito ANTES de correr cualquier hipótesis con datos reales de XM.
Regla: no se cambian reglas, parámetros, mercados ni criterios después de ver resultados. Un cambio sería una nueva hipótesis y suma al conteo.

## Datos
Export de XM (cuenta demo): D1/H4 desde 2015, M30 desde 2021, con spread por vela y swaps actuales. H1 = agregado desde M30. M15 no disponible.

## Costos (los del laboratorio original)
Spread de cada vela + 25 % de deslizamiento; órdenes stop 0,5 spread peor; swap real por noche. Estrés: costos x2 (criterio). Diagnóstico: costos x0.

## Hipótesis (27 conjuntos de parámetros)
- **H1 RSI(2) diario, índices** (US500Cash, US100Cash, US30Cash, GER40Cash; solo compras; sin stop; 10 % de vol objetivo). Entrada: cierre>SMA200 y RSI2<umbral, a la apertura siguiente. Salida: `sma5` (cierre>SMA5) o `rsi70` (RSI2>70). Parámetros: umbral {5,10} x salida {sma5,rsi70} = 4.
- **H2 RSI(2) M30** (GOLD, US500Cash; compras y ventas; 0,5 % de riesgo). V1, V2 y V3 tal como las describe el artículo 17636 de MQL5 = 3.
- **H3 Ruptura H1** (GOLD; 0,5 % de riesgo; máx. 72 velas). Canal N {20,50} x SL ATR {1.5,2} x TP ATR {2,3} = 8.
- **H4 Salidas cortas con entrada RSI2** (GOLD, US500Cash, M30; 0,5 % de riesgo; máx. 16 velas). RSI2<10 con cierre>EMA50 (compra) o RSI2>90 con cierre<EMA50 (venta). (TP,SL) en ATR: (0.5,0.5), (0.5,1.5), (1,1), (1,2) = 4.
- **H5 H4 + filtro de costo** (mismas reglas). Solo si ATR/spread >= k. (TP,SL) {(1,1),(1,2)} x k {8,15} = 4.
- **H6 Oro/plata** (H4; relativo con beta móvil; 10 % de vol objetivo). z de spread log; ventana {360,720} velas x entrada |z| {1.5,2}; salida |z|<0.5, stop |z|>4, máx. 240 velas = 4.

## Validación
Walk-forward del laboratorio: 2 años de entrenamiento, 6 meses de prueba; se elige por Sharpe de entrenamiento. Solo cuentan los tramos fuera de muestra.

## Criterios (todos obligatorios)
1. Operaciones OOS >= 100
2. Sharpe OOS >= 0,5
3. Eficiencia walk-forward >= 0,5
4. Ventanas OOS positivas >= 55 %
5. Caída p95 Monte Carlo <= 25 %
6. Sharpe con doble costo >= 0,2
7. Deflated Sharpe >= 0,95, con N = 44 intentos (27 + 17 del laboratorio original)
8. Solo H4 y H5: resultado medio en R por encima del percentil 95 de entradas al azar con las mismas salidas

## Controles (antes de creer cualquier resultado)
- Negativo: datos reales con retornos barajados. Ninguna familia debe aprobar.
- Positivo: efecto plantado a propósito. El motor debe detectarlo.
- Causalidad: truncar el futuro no cambia decisiones pasadas.
- Monotonía: más costo nunca mejora el resultado.

## Contexto (no decide el veredicto)
H1 se compara con comprar y mantener con swap real.

## Enmiendas anteriores a ver resultados reales
Hechas el 2026-11-04 después de correr solo los controles con datos barajados o plantados; aún no se había corrido ninguna hipótesis con datos reales.
1. **H6:** el control positivo falló porque el z mezclaba betas distintas en el tiempo. Ahora z es el residuo de la regresión móvil con la beta actual.
2. **Deflated Sharpe:** la varianza entre intentos se mide con los 27 intentos sobre datos barajados, para que refleje solo azar. La variante con los intentos reales se reporta como sensibilidad, sin decidir el veredicto.
